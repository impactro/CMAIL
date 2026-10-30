"""Trusted-host editing without providers, tokens or live instance changes."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from cmail import CmailConfiguration, ConfigurationConflict
from cmail.config import Config, ConfigError
from cmail.configuration import _edit_lock
from helpers import PROJECT_ROOT, config_payload, config_payload_v11


def test_initialize_creates_one_explicit_pair_and_never_overwrites(tmp_path):
    path = tmp_path / 'config' / 'cmail.config.json'
    editor = CmailConfiguration(path, root=tmp_path)
    snapshot = editor.initialize()
    selected = Config.from_file(path, root=tmp_path)
    assert selected.mode == 'setup'
    assert selected.state_dir == tmp_path / '.state' / 'cmail'
    assert editor.markdown_path == path.with_suffix('.md')
    assert editor.markdown_path.is_file()
    assert snapshot['source']['jsonPath'] == str(path)
    assert snapshot['source']['markdownAvailable'] is True
    assert snapshot['effective']['known'] is False
    assert not (tmp_path / '.env').exists()
    assert not selected.state_dir.exists()
    with pytest.raises(ConfigurationConflict):
        editor.initialize()
    assert editor.read()['revision'] == snapshot['revision']


@pytest.mark.parametrize('schema', ['1.0', '1.1', '1.2', '1.3'])
def test_mapping_and_file_share_validation_and_relative_paths(tmp_path, schema):
    document = config_payload() if schema == '1.0' else config_payload_v11()
    document['schemaVersion'] = schema
    if schema in {'1.2', '1.3'}:
        document['gmailFile'] = {'account': '', 'tokenFile': ''}
    if schema == '1.3':
        document['gmailFile']['transport'] = 'api'
    path = tmp_path / 'config' / 'cmail.config.json'
    path.parent.mkdir()
    path.write_text(json.dumps(document), encoding='utf-8')
    mapped = Config.from_mapping(document, path=path, root=tmp_path)
    assert mapped == Config.from_file(path, root=tmp_path)
    assert mapped.state_dir == (path.parent / document['state']['directory']).resolve()


def test_validation_does_not_read_secret_create_state_or_write_config(tmp_path):
    editor = CmailConfiguration(tmp_path / 'config' / 'cmail.config.json', root=tmp_path)
    document = config_payload()
    document['mode'] = 'imap'
    document['imap'].update(account='owner@example.com', username='owner@example.com',
                            passwordFile='../private/password.txt',
                            imapHost='imap.example.com', smtpHost='smtp.example.com')
    selected = editor.validate(document)
    assert selected.password_file == tmp_path / 'private' / 'password.txt'
    assert list(tmp_path.iterdir()) == []
    invalid = copy.deepcopy(document)
    invalid['imap']['password'] = 'do-not-write-this'
    with pytest.raises(ConfigError):
        editor.validate(invalid)
    assert list(tmp_path.iterdir()) == []


def test_save_requires_revision_and_reports_saved_vs_active(tmp_path):
    editor = CmailConfiguration(tmp_path / 'config' / 'cmail.config.json', root=tmp_path)
    initial = editor.initialize()
    running = Config.from_file(editor.path, root=tmp_path)
    editor = CmailConfiguration.from_config(running)
    assert editor.read()['effective']['matchesSaved'] is True
    document = initial['document']
    document['server']['port'] = 8031
    saved = editor.save(document, expected_revision=initial['revision'])
    assert saved['revision'] != initial['revision']
    assert saved['effective']['matchesSaved'] is False
    assert saved['effective']['restartRequired'] is True
    assert saved['effective']['revision'] == initial['revision']
    assert saved['saved'] is True and saved['applied'] is False
    assert saved['pendingRestart'] is True
    assert running.port == 8020
    rebuilt = CmailConfiguration.from_config(Config.from_file(editor.path, root=tmp_path))
    assert rebuilt.read()['effective']['matchesSaved'] is True
    assert rebuilt.read()['effective']['revision'] == saved['revision']
    with pytest.raises(ConfigurationConflict):
        editor.save(document, expected_revision=initial['revision'])
    with pytest.raises(ConfigError, match='SHA-256'):
        editor.save(document, expected_revision='')


def test_revision_hashes_exact_bytes_including_bom_and_formatting(tmp_path):
    editor = CmailConfiguration(tmp_path / 'cmail.json')
    snapshot = editor.initialize()
    raw = b'\xef\xbb\xbf' + json.dumps(snapshot['document']).encode()
    editor.path.write_bytes(raw)
    fresh = editor.read()
    assert fresh['revision'] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ConfigurationConflict):
        editor.save(snapshot['document'], expected_revision=snapshot['revision'])


def test_competing_editors_only_save_once(tmp_path):
    path = tmp_path / 'cmail.json'
    snapshot = CmailConfiguration(path).initialize()

    def attempt(port):
        document = copy.deepcopy(snapshot['document'])
        document['server']['port'] = port
        try:
            CmailConfiguration(path).save(document, expected_revision=snapshot['revision'])
            return 'saved'
        except ConfigurationConflict:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (8041, 8042)))
    assert sorted(results) == ['conflict', 'saved']
    assert Config.from_file(path).port in (8041, 8042)


def test_lock_also_excludes_a_separate_process(tmp_path):
    editor = CmailConfiguration(tmp_path / 'cmail.json')
    snapshot = editor.initialize()
    script = """
import sys
from cmail import CmailConfiguration, ConfigurationConflict
editor = CmailConfiguration(sys.argv[1])
value = editor.read()
try:
    editor.save(value['document'], expected_revision=value['revision'])
except ConfigurationConflict:
    print('locked')
else:
    raise AssertionError('cross-process lock was bypassed')
"""
    with _edit_lock(editor.path):
        completed = subprocess.run(
            [sys.executable, '-s', '-B', '-c', script, str(editor.path)],
            cwd=PROJECT_ROOT, env={**os.environ, 'PYTHONNOUSERSITE': '1'},
            capture_output=True, text=True, check=True, timeout=15,
        )
    assert completed.stdout.strip() == 'locked'
    assert editor.read()['revision'] == snapshot['revision']


def test_invalid_document_and_replace_failure_preserve_previous_file(tmp_path, monkeypatch):
    editor = CmailConfiguration(tmp_path / 'cmail.json')
    initial = editor.initialize()
    before = editor.path.read_bytes()
    document = copy.deepcopy(initial['document'])
    document['unexpected'] = True
    with pytest.raises(ConfigError):
        editor.save(document, expected_revision=initial['revision'])
    assert editor.path.read_bytes() == before
    document.pop('unexpected')
    document['server']['port'] = 8050

    def fail(*_args):
        raise OSError('synthetic replace failure')

    monkeypatch.setattr('cmail.configuration.os.replace', fail)
    with pytest.raises(OSError, match='synthetic'):
        editor.save(document, expected_revision=initial['revision'])
    assert editor.path.read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))


def test_companion_notes_preserved_and_catalog_does_not_create_second_source(tmp_path):
    editor = CmailConfiguration(tmp_path / 'config' / 'mail' / 'cmail.config.json')
    snapshot = editor.initialize()
    editor.markdown_path.write_text('Instance notes', encoding='utf-8')
    editor.save(snapshot['document'], expected_revision=snapshot['revision'])
    assert editor.markdown_path.read_text(encoding='utf-8') == 'Instance notes'
    assert len(list(tmp_path.rglob('*.json'))) == 1
    assert editor.describe()['application']['automatic'] is False


def test_ces_catalog_entry_uses_actual_schema_relative_paths_and_host_reload_mode(tmp_path):
    config_root = tmp_path / 'config'
    editor = CmailConfiguration(config_root / 'cmail' / 'cmail.config.json')
    editor.initialize()
    entry = editor.catalog_entry(config_root, consumers=('cmail', 'cwh'),
                                 apply_mode='component-reload')
    assert entry['id'] == 'cmail.settings'
    assert entry['moduleId'] == 'cmail'
    assert entry['path'] == 'cmail/cmail.config.json'
    assert entry['documentation'] == 'cmail/cmail.config.md'
    assert entry['schemaVersion'] == '1.3'
    assert entry['applyMode'] == 'component-reload'
    with pytest.raises(ConfigError):
        editor.catalog_entry(config_root, apply_mode='immediate')
    with pytest.raises(ConfigError):
        editor.catalog_entry(config_root, consumers=('cwh', 'cwh'))
    with pytest.raises(ConfigError):
        editor.catalog_entry(config_root / 'another')


def test_legacy_file_still_readable_but_not_published_as_canonical_catalog(tmp_path):
    editor = CmailConfiguration(tmp_path / 'legacy.json')
    editor.initialize()
    assert editor.read()['document']['mode'] == 'setup'
    with pytest.raises(ConfigError, match='Migre'):
        editor.catalog_entry(tmp_path / 'config')


def test_catalog_rejects_wrong_root_invalid_metadata_and_missing_companion(tmp_path):
    editor = CmailConfiguration(tmp_path / 'config' / 'cmail.json')
    editor.initialize()
    with pytest.raises(ConfigError):
        editor.catalog_entry(editor.path)
    with pytest.raises(ConfigError):
        editor.catalog_entry(editor.path.parent, consumers=({'unhashable': True},))
    with pytest.raises(ConfigError):
        editor.catalog_entry(editor.path.parent, apply_mode=[])
    editor.markdown_path.unlink()
    with pytest.raises(ConfigError, match='Markdown'):
        editor.catalog_entry(editor.path.parent)


def test_oversize_and_wrong_active_instance_are_rejected(tmp_path):
    editor = CmailConfiguration(tmp_path / 'cmail.json')
    snapshot = editor.initialize()
    document = copy.deepcopy(snapshot['document'])
    document['mode'] = 'x' * (512 * 1024)
    with pytest.raises(ConfigError, match='512 KiB'):
        editor.validate(document)
    active = Config.from_file(editor.path)
    with pytest.raises(ConfigError, match='outra instância'):
        CmailConfiguration(tmp_path / 'another.json', active_config=active)
    assert editor.read()['revision'] == snapshot['revision']
