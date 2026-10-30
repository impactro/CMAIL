"""Migration acceptance with synthetic references; never reads a credential."""
import copy
import json
import os
from dataclasses import fields

import pytest
from fastapi.testclient import TestClient

from cmail import CmailConfiguration, Config, Principal
from cmail.api import create_component_api
from cmail.appearance import Appearance
from cmail.web import create_component_app
from helpers import config_payload, config_payload_v11


REFERENCES = (
    ('state', 'directory'), ('microsoft', 'clientSecretFile'),
    ('google', 'clientSecretFile'), ('imap', 'passwordFile'), ('gmailFile', 'tokenFile'),
)


@pytest.mark.parametrize('schema,mode,transport', [
    ('1.0', 'imap', None), ('1.0', 'microsoft', None),
    ('1.1', 'gmail', None), ('1.2', 'gmail-file', None),
    ('1.3', 'gmail-file', 'smtp'),
])
def test_move_json_preserves_all_effective_values_and_appearance_roots(tmp_path, schema, mode, transport):
    document = config_payload(mode) if schema == '1.0' else config_payload_v11(mode)
    document['schemaVersion'] = schema
    document['state']['directory'] = '.state/original'
    document['microsoft'].update(clientId='synthetic-client', tenantId='synthetic-tenant',
                                 clientSecretFile='private/microsoft.txt',
                                 redirectUri='https://example.test/auth/callback')
    document['imap'].update(account='synthetic@example.test', username='synthetic',
                            passwordFile='private/imap.txt', imapHost='imap.example.test',
                            smtpHost='smtp.example.test')
    if 'google' in document:
        document['google'].update(clientId='synthetic-google',
                                  clientSecretFile='private/google.txt',
                                  redirectUri='https://example.test/auth/google/callback')
    if schema in {'1.2', '1.3'}:
        document['gmailFile'] = {'account': 'synthetic@example.test',
                                 'tokenFile': 'private/authorized-user.json'}
    if transport:
        document['gmailFile']['transport'] = transport
    old_path = tmp_path / 'cmail.json'
    old_path.write_text(json.dumps(document), encoding='utf-8')
    before = Config.from_file(old_path, root=tmp_path)
    new_path = tmp_path / 'config' / 'cmail.config.json'
    candidate = copy.deepcopy(document)
    for section, key in REFERENCES:
        raw = candidate.get(section, {}).get(key)
        if raw:
            target = (old_path.parent / raw).resolve()
            candidate[section][key] = os.path.relpath(target, new_path.parent)
    after = Config.from_mapping(candidate, path=new_path, root=tmp_path)
    for field in fields(Config):
        if field.name not in {'config_file', 'source_revision'}:
            assert getattr(after, field.name) == getattr(before, field.name), field.name
    old_appearance = Appearance(before.root, before.state_dir)
    new_appearance = Appearance(after.root, after.state_dir)
    assert old_appearance.company_root == new_appearance.company_root
    assert old_appearance.user_root('') == new_appearance.user_root('')
    assert old_appearance.user_root('synthetic-owner') == new_appearance.user_root('synthetic-owner')
    assert not new_path.exists()  # Validation alone has no persistence or discovery.
    assert not before.state_dir.exists()
    assert not (tmp_path / 'private').exists()


def test_official_setup_bootstrap_supports_factories_but_not_embedded_setup_ui(tmp_path):
    path = tmp_path / 'config' / 'cmail.config.json'
    editor = CmailConfiguration(path, root=tmp_path)
    initial = editor.initialize()
    api = create_component_api(tmp_path, {'configFile': path})
    assert api.service.config.mode == 'setup'
    assert api.service.auth is None
    assert not api.service.config.state_dir.exists()
    assert initial['document']['microsoft']['account'] == ''
    assert initial['document']['google']['account'] == ''
    app = create_component_app(tmp_path, {
        'configFile': path,
        'principalResolver': lambda _request: {
            'identifier': 'synthetic-owner', 'capabilities': ['mail.read'],
        },
    })
    with TestClient(app) as client:
        assert client.get('/health').json()['configured'] is False
        assert client.get('/setup').status_code == 404
        response = client.get('/', follow_redirects=False)
        assert response.status_code == 303 and response.headers['location'] == '/setup'
    with pytest.raises(PermissionError, match='Configure'):
        api.folders(Principal('', '', frozenset({'mail.read'}), 'synthetic-owner'))
    assert not api.service.config.state_dir.exists()
