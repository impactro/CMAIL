"""Portable suite selection. Real accounts are opt-in, never autodiscovered."""
import json
from pathlib import Path
import pytest


def pytest_addoption(parser):
    parser.addoption('--run-cmail-live', action='store_true', default=False,
                     help='Autoriza somente os probes de leitura/status do plano local explícito.')
    parser.addoption('--cmail-live-plan', help='JSON privado com referências a configurações autorizadas.')


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = item.path.as_posix()
        if '/live/' in path:
            item.add_marker('live')
            continue
        item.add_marker('simulated')
        name = item.name.lower()
        group = ('gmail_file_smtp' if '/oauth_smtp/' in path else
                 'gmail_file_api' if '/oauth_file/' in path else
                 'gmail_api' if '/gmail/api/' in path or 'gmail' in name or 'hosted_setup' in path else
                 'outlook' if '/outlook/' in path or 'graph' in name or 'microsoft' in name or 'msal' in name else
                 'imap' if '/imap/' in path or 'imap' in name else 'shared')
        item.add_marker(getattr(pytest.mark, group))
        if any(k in path for k in ('_browser.py', '_playwright.py', 'test_webmail_layout.py')):
            item.add_marker('browser')


def pytest_generate_tests(metafunc):
    if 'live_case' not in metafunc.fixturenames:
        return
    if not metafunc.config.getoption('--run-cmail-live'):
        metafunc.parametrize('live_case', [pytest.param(None, marks=pytest.mark.skip(
            reason='Homologação real requer --run-cmail-live e plano privado autorizado.'))])
        return
    path = metafunc.config.getoption('--cmail-live-plan')
    if not path:
        raise pytest.UsageError('--cmail-live-plan é obrigatório; contas não são descobertas automaticamente.')
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if (not isinstance(data, dict) or set(data) != {'schemaVersion', 'accounts'}
                or type(data['schemaVersion']) is not int or data['schemaVersion'] != 1
                or not isinstance(data['accounts'], list) or not data['accounts']):
            raise ValueError()
        cases, ids = [], set()
        for value in data['accounts']:
            if (not isinstance(value, dict) or set(value)-{'id','profile','configFile','root','connectorId',
                    'ownerId','folder','messageId','attachmentId','attachmentSha256'} or
                    not {'id','profile','configFile'} <= set(value)):
                raise ValueError()
            if not isinstance(value['id'], str) or not value['id'].isascii() or not value['id'].replace('-','').replace('_','').isalnum() or value['id'] in ids:
                raise ValueError()
            if value['profile'] not in {'gmail_api','gmail_file_api','gmail_file_smtp','imap','outlook'}:
                raise ValueError()
            if not Path(value['configFile']).is_absolute():
                raise ValueError()
            ids.add(value['id'])
            cases.append(pytest.param(value, id=value['id'], marks=getattr(pytest.mark,value['profile'])))
    except (OSError, ValueError, TypeError, KeyError):
        raise pytest.UsageError('Plano live inválido; conferir o contrato, sem publicar seu conteúdo.') from None
    metafunc.parametrize('live_case', cases)
