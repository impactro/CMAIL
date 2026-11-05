"""Authorized machine probes; no consent UI, sends, mutation or inferred accounts."""
import base64
import hashlib
import pytest


@pytest.mark.live
def test_authorized_mailbox_readonly(live_case):
    from cmail import Config, CmailApi, Principal, ConnectorConfig, ConnectorRegistry
    case = live_case
    if case.get('connectorId'):
        registry = ConnectorRegistry(ConnectorConfig.from_file(case['configFile'], root=case.get('root')))
        api = registry.native_api(case['connectorId'])
    else:
        api = CmailApi.from_config(Config.from_file(case['configFile'], root=case.get('root')))
    cfg = api.service.config
    expected = {'gmail_api':('gmail','api'), 'gmail_file_api':('gmail-file','api'),
                'gmail_file_smtp':('gmail-file','smtp'), 'imap':('imap','api'), 'outlook':('microsoft','api')}
    mode, transport = expected[case['profile']]
    assert cfg.mode == mode
    if mode == 'gmail-file':
        assert cfg.gmail_file_transport == transport and not case.get('ownerId')
        principal = Principal.local_operator()
    else:
        assert isinstance(case.get('ownerId'), str) and case['ownerId']
        principal = api.principal_for_owner(case['ownerId'], frozenset({'mail.read'}))
    status = api.status(principal, live=True)
    assert isinstance(status, dict) and status.get('provider', {}).get('connected') is True
    if case['profile'] == 'gmail_file_smtp':
        return  # Status/NOOP only: this transport cannot read mail or prove DATA delivery.
    folders = api.folders(principal)
    assert isinstance(folders, list) and folders
    folder = case.get('folder', 'INBOX')
    assert isinstance(api.messages(principal, folder, limit=3), list)
    if case.get('messageId'):
        assert api.message(principal, folder, case['messageId'])['id'] == case['messageId']
    if case.get('attachmentId'):
        assert case.get('messageId') and case.get('attachmentSha256')
        value = api.attachment(principal, case['messageId'], case['attachmentId'])
        raw = base64.b64decode(value['contentBase64'], validate=True)
        assert hashlib.sha256(raw).hexdigest() == case['attachmentSha256']
