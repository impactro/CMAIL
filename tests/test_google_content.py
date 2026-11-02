"""Synthetic Google content contracts; never contact a provider."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail import (CmailApi, GoogleRead, GoogleWrite, ReadOperation as R,
                   WriteOperation as W, Principal, ConsentRequired)
from cmail.google_auth import GoogleAuthService, ProtectedJsonFile, CONTENT_SCOPES, GMAIL_SCOPES
from cmail.google_content import ContentError, MAX_BYTES, request as transport
from cmail.service import MailService
from cmail.store import Store
from helpers import gmail_config


@pytest.fixture
def context(tmp_path, monkeypatch):
    selected = gmail_config(tmp_path)
    store = Store(selected.state_dir)
    identity = store.save_identity('https://accounts.google.com', 'subject',
                                   'pessoa@gmail.test', 'Synthetic', provider='google',
                                   owner_id='owner-a', scopes=[])
    tokens = {}
    monkeypatch.setattr(ProtectedJsonFile, 'save', lambda self, value: tokens.__setitem__(str(self.path), copy.deepcopy(value)))
    monkeypatch.setattr(ProtectedJsonFile, 'load', lambda self: copy.deepcopy(tokens.get(str(self.path))))
    auth_calls, calls = [], []

    def auth_http(*args):
        auth_calls.append(args)
        raise AssertionError('Unexpected OAuth HTTP')

    auth = GoogleAuthService(selected, store, requester=auth_http)
    auth._token_file(identity['id']).save({'scope': ' '.join(scope for scopes in CONTENT_SCOPES.values() for scope in scopes),
                                         'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
                                         'expires_at': 9999999999})

    def http(*args):
        calls.append(args)
        return 200, {'id': 'file-id'}

    api = CmailApi(MailService(selected, auth=auth), content_requester=http)
    principal = Principal(identity['id'], identity['email'], frozenset(CONTENT_SCOPES), 'owner-a')
    return api, principal, auth, calls, auth_calls, tokens


def set_scopes(auth, p, scopes):
    file = auth._token_file(p.identity_id)
    token = file.load()
    token['scope'] = ' '.join(scopes)
    file.save(token)


def test_content_only_google_connection_does_not_require_mailbox(context, monkeypatch):
    api, _, _, calls, _, _ = context
    config = replace(api.service.config, mode='demo', google_account='')
    content_api = CmailApi(MailService(config), content_requester=lambda *args: (200, {'files': []}))
    auth = content_api._google().auth
    bootstrap = Principal('', '', frozenset({'google.drive.read'}), 'content-owner')
    url, nonce = content_api.google_content_begin_consent(bootstrap, 'google.drive.read')
    parameters = parse_qs(urlsplit(url).query)
    assert not any('gmail' in scope for scope in parameters['scope'][0].split())
    assert not calls
    seen = []

    def http(method, url, headers, body):
        seen.append(url)
        if url.endswith('/token'):
            assert b'client_secret=' in body
            return 200, {'access_token': 'synthetic-content', 'refresh_token': 'synthetic-refresh',
                         'scope': CONTENT_SCOPES['google.drive.read'][0]}
        assert 'userinfo' in url
        return 200, {'sub': 'content-only-subject', 'email': 'content@example.test', 'email_verified': True}

    auth.requester = http
    sessions, create_session = [], auth.store.create_session

    def session(*args):
        value = create_session(*args)
        sessions.append(value[0])
        return value

    monkeypatch.setattr(auth.store, 'create_session', session)
    result = content_api.google_content_complete_consent(
        {'state': parameters['state'][0], 'code': 'synthetic'}, nonce, 'content-owner')
    assert result['connected'] and result['ownerId'] == 'content-owner'
    assert result['authorizedCapabilities'] == ['google.drive.read']
    assert not any('gmail' in endpoint for endpoint in seen)
    assert 'synthetic-' not in json.dumps(result) and 'Token' not in json.dumps(result)
    assert sessions and auth.current(sessions[0]) is None  # No Webmail session granted.
    monkeypatch.setattr(auth, 'is_connected', lambda identity: bool(auth._token_file(identity).load()))
    principal = content_api.google_content_principal_for_owner('content-owner', frozenset({'google.drive.read'}))
    assert principal.owner_id == 'content-owner' and principal.identity_id == result['identityId']
    assert content_api.google_content_read(principal, GoogleRead(R.DRIVE_LIST))['complete']
    with pytest.raises(PermissionError):
        content_api.google_content_principal_for_owner('other-owner', frozenset({'google.drive.read'}))


def test_content_initial_consent_requires_owner_and_refresh_grant(context):
    api, _, auth, _, _, _ = context
    auth.config = replace(auth.config, google_account='')
    with pytest.raises(PermissionError):
        api.google_content_begin_consent(Principal('', '', frozenset({'google.drive.read'})), 'google.drive.read')
    url, nonce = api.google_content_begin_consent(
        Principal('', '', frozenset({'google.drive.read'}), 'new-owner'), 'google.drive.read')
    state = parse_qs(urlsplit(url).query)['state'][0]
    auth.requester = lambda method, url, headers, body: (200,
        {'access_token': 'synthetic'} if url.endswith('/token') else
        {'sub': 'new-subject', 'email': 'new@example.test', 'email_verified': True})
    with pytest.raises(Exception, match='permanente'):
        api.google_content_complete_consent({'state': state, 'code': 'synthetic'}, nonce, 'new-owner')
    assert not auth.store.bound_identity('google', 'new-owner')


def format_change(**overrides):
    changes = {'sheetId': 7, 'startRowIndex': 0, 'endRowIndex': 5,
               'startColumnIndex': 0, 'endColumnIndex': 3,
               'format': {'bold': True, 'fontSize': 12, 'numberFormat': {'type': 'NUMBER', 'pattern': '0.00'}}}
    changes.update(overrides)
    return GoogleWrite(W.SHEETS_FORMAT, 'sheet-file', changes)


def test_sheets_metadata_and_bounded_formatting_use_canonical_http(context):
    api, p, _, calls, _, _ = context
    api.google_content_read(p, GoogleRead(R.SHEETS_METADATA, 'sheet-file'))
    params = parse_qs(urlsplit(calls[-1][1]).query)
    assert 'charts(chartId,spec,position)' in params['fields'][0]
    assert 'includeGridData' not in params and 'data(' not in params['fields'][0]
    calls.clear()
    preview = api.google_content_prepare(p, format_change())
    assert not calls
    receipt = api.google_content_execute(p, preview['previewId'], preview['confirmationToken'], confirmed=True)
    assert receipt['status'] == 'completed' and len(calls) == 1
    method, url, _, body = calls[0]
    assert method == 'POST' and url.endswith('/sheet-file:batchUpdate')
    update = json.loads(body)['requests'][0]['repeatCell']
    assert update['range']['sheetId'] == 7 and update['range']['endRowIndex'] == 5
    assert update['cell']['userEnteredFormat']['textFormat']['bold'] is True
    assert '*' not in update['fields'] and 'userEnteredValue' not in str(update)


@pytest.mark.parametrize('changes', [
    {'endRowIndex': 101}, {'endColumnIndex': 27}, {'startRowIndex': 5},
    {'sheetId': True}, {'format': {}}, {'format': {'bold': 'true'}},
    {'format': {'fontSize': 200}}, {'format': {'horizontalAlignment': 'invalid'}},
    {'format': {'numberFormat': {'type': 'invalid'}}}, {'format': {'deleteSheet': True}},
])
def test_sheets_format_rejects_unbounded_or_unrelated_changes(context, changes):
    api, p, _, calls, _, _ = context
    with pytest.raises(ValueError):
        api.google_content_prepare(p, format_change(**changes))
    assert not calls


def write(operation=W.DRIVE_UPDATE):
    if operation == W.SHEETS_FORMAT:
        return format_change()
    if operation == W.DRIVE_UPDATE:
        return GoogleWrite(operation, 'file-id', {'name': 'Synthetic'})
    if operation == W.DRIVE_FOLDER:
        return GoogleWrite(operation, changes={'name': 'Synthetic', 'parent': 'parent-id'})
    if operation == W.SHEETS_UPDATE:
        return GoogleWrite(operation, 'sheet-id', {'range': 'A1:B1', 'values': [['=not-a-formula', 2]]})
    insert = {'text': 'Synthetic', 'location': {'index': 1}} if operation == W.DOCS_BATCH else {
        'text': 'Synthetic', 'objectId': 'shape-id', 'insertionIndex': 0}
    return GoogleWrite(operation, 'document-id', {'requests': [{'insertText': insert}]})


@pytest.mark.parametrize('owner,identity', [('owner-b', None), ('owner-a', 'fake'), ('', None)])
def test_cross_owner_denied_before_http(context, owner, identity):
    api, p, auth, calls, auth_calls, _ = context
    bad = replace(p, owner_id=owner, identity_id=identity or p.identity_id)
    with pytest.raises(PermissionError):
        api.google_content_read(bad, GoogleRead(R.DRIVE_GET, 'file-id'))
    with pytest.raises(PermissionError):
        api.google_content_prepare(bad, write())
    with pytest.raises(PermissionError):
        api.google_content_begin_consent(bad, 'google.drive.read')
    assert not calls and not auth_calls


def test_gmail_scope_is_not_drive_consent_no_silent_auth(context):
    api, p, auth, calls, auth_calls, _ = context
    set_scopes(auth, p, GMAIL_SCOPES)
    with pytest.raises(ConsentRequired) as error:
        api.google_content_read(p, GoogleRead(R.DRIVE_GET, 'file-id'))
    assert error.value.scopes == CONTENT_SCOPES['google.drive.read']
    with pytest.raises(ConsentRequired):
        api.google_content_prepare(p, write())
    assert not calls and not auth_calls


def test_read_write_capabilities_independent(context):
    api, p, auth, calls, auth_calls, _ = context
    read = replace(p, capabilities=frozenset({'google.drive.read'}))
    api.google_content_read(read, GoogleRead(R.DRIVE_GET, 'file-id'))
    with pytest.raises(PermissionError):
        api.google_content_prepare(read, write())
    with pytest.raises(PermissionError):
        api.google_content_read(replace(p, capabilities=frozenset({'google.drive.write'})), GoogleRead(R.DRIVE_GET, 'file-id'))
    set_scopes(auth, p, CONTENT_SCOPES['google.drive.read'])
    with pytest.raises(ConsentRequired):
        api.google_content_prepare(p, write())
    assert len(calls) == 1 and not auth_calls


def test_incremental_consent_parameters_and_no_network(context):
    api, p, auth, calls, auth_calls, _ = context
    url, nonce = api.google_content_begin_consent(p, 'google.sheets.write')
    params = parse_qs(urlsplit(url).query)
    assert params['include_granted_scopes'] == ['true']
    assert params['prompt'] == ['consent']
    assert set(params['scope'][0].split()) == {'openid', 'email', *CONTENT_SCOPES['google.sheets.write']}
    assert 'gmail' not in params['scope'][0]
    assert nonce and not calls and not auth_calls
    legacy, _ = auth.begin('owner-a')
    assert set(parse_qs(urlsplit(legacy).query)['scope'][0].split()) == set(GMAIL_SCOPES)


@pytest.mark.parametrize('wrong_owner,wrong_subject', [(False, False), (True, False), (False, True)])
def test_incremental_complete_preserves_identity_and_refresh(context, wrong_owner, wrong_subject):
    api, p, auth, calls, auth_calls, _ = context
    url, nonce = api.google_content_begin_consent(p, 'google.docs.read')
    state = parse_qs(urlsplit(url).query)['state'][0]
    def http(method, url, headers, body):
        auth_calls.append(url)
        if url.endswith('/token'):
            return 200, {'access_token': 'new-synthetic', 'scope': CONTENT_SCOPES['google.docs.read'][0]}
        assert 'userinfo' in url
        return 200, {'sub': 'other-subject' if wrong_subject else 'subject',
                     'email': p.email, 'email_verified': True}
    auth.requester = http
    if wrong_owner or wrong_subject:
        with pytest.raises(Exception):
            auth.complete({'state': state, 'code': 'synthetic'}, nonce, 'owner-b' if wrong_owner else 'owner-a')
        assert auth._token_file(p.identity_id).load()['access_token'] == 'synthetic-access'
    else:
        _, _, identity = auth.complete({'state': state, 'code': 'synthetic'}, nonce, 'owner-a')
        assert identity['id'] == p.identity_id
        assert auth._token_file(p.identity_id).load()['refresh_token'] == 'synthetic-refresh'
        assert auth.granted_scopes(p.identity_id) == set(CONTENT_SCOPES['google.docs.read'])
    assert not any('gmail' in url for url in auth_calls)
    assert not calls


def test_pagination_empty_partial_pages_and_resume(context):
    api, p, _, calls, _, _ = context
    pages = iter([{'files': [], 'nextPageToken': 'two'}, {'files': [{'id': 'x'}], 'nextPageToken': 'three'}, {'files': [{'id': 'y'}]}])
    def http(*args):
        calls.append(args)
        return 200, next(pages)
    api._content.requester = http
    result = api.google_content_read(p, GoogleRead(R.DRIVE_LIST, max_pages=2, page_size=2))
    assert result['nextPageToken'] == 'three' and not result['complete']
    assert parse_qs(urlsplit(calls[1][1]).query)['pageToken'] == ['two']
    final = api.google_content_read(p, GoogleRead(R.DRIVE_LIST, page_token='three'))
    assert final['complete'] and len(calls) == 3


@pytest.mark.parametrize('query', [GoogleRead(R.DRIVE_LIST, max_pages=11), GoogleRead(R.DRIVE_LIST, page_size=101),
                                  GoogleRead(R.DRIVE_GET, '../bad'), GoogleRead(R.DRIVE_LIST, query='x'*2049),
                                  GoogleRead('drive.get', 'file-id')])
def test_invalid_read_before_http(context, query):
    api, p, _, calls, auth_calls, _ = context
    with pytest.raises(ValueError):
        api.google_content_read(p, query)
    assert not calls and not auth_calls


@pytest.mark.parametrize('result', [{'files': [1, 2], 'nextPageToken': 'x'}, {'files': 'invalid'}, {'files': [], 'nextPageToken': 1}])
def test_page_limits(context, result):
    api, p, *_ = context
    api._content.requester = lambda *args: (200, result)
    with pytest.raises(ContentError):
        api.google_content_read(p, GoogleRead(R.DRIVE_LIST, page_size=1))


def test_pagination_cycle_and_incomplete(context):
    api, p, *_ = context
    api._content.requester = lambda *args: (200, {'files': [], 'nextPageToken': 'same'})
    with pytest.raises(ContentError):
        api.google_content_read(p, GoogleRead(R.DRIVE_LIST, max_pages=3))
    api._content.requester = lambda *args: (200, {'files': [], 'incompleteSearch': True})
    assert not api.google_content_read(p, GoogleRead(R.DRIVE_LIST))['complete']


@pytest.mark.parametrize('op', [R.DRIVE_GET, R.DOCS_GET, R.SHEETS_GET, R.SLIDES_GET])
def test_read_endpoints_and_bounds(context, op):
    api, p, _, calls, _, _ = context
    api.google_content_read(p, GoogleRead(op, 'valid-id', range='Tab!A1:B2'))
    assert calls[-1][0] == 'GET' and 'valid-id' in calls[-1][1]
    api._content.requester = lambda *args: (200, {'data': 'x' * MAX_BYTES})
    with pytest.raises(ContentError):
        api.google_content_read(p, GoogleRead(op, 'valid-id'))


@pytest.mark.parametrize('export,mime', [(False, 'text/plain'), (True, 'application/vnd.google-apps.document')])
def test_bounded_text(context, export, mime):
    api, p, _, calls, _, _ = context
    def http(*args):
        calls.append(args)
        return (200, 'Synthetic text') if args[2]['Accept'] == 'text/plain' else (200, {'mimeType': mime})
    api._content.requester = http
    assert api.google_content_read(p, GoogleRead(R.DRIVE_TEXT, 'file-id', export=export)) == {'text': 'Synthetic text'}
    assert len(calls) == 2
    assert '/export?' in calls[-1][1] if export else 'alt=media' in calls[-1][1]


@pytest.mark.parametrize('op', list(W))
def test_write_preview_no_http_execute_exact_once(context, op):
    api, p, auth, calls, auth_calls, _ = context
    draft = api.google_content_prepare(p, write(op))
    assert not calls and not auth_calls
    with pytest.raises(PermissionError):
        api.google_content_execute(p, draft['previewId'], draft['confirmationToken'])
    result = api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert result['status'] == 'completed' and len(calls) == 1
    if op == W.DOCS_BATCH:
        assert calls[0][0] == 'POST' and '/v1/documents/document-id:batchUpdate' in calls[0][1]
    if op == W.SHEETS_UPDATE:
        assert 'valueInputOption=RAW' in calls[0][1]
    with pytest.raises(PermissionError):
        api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert len(calls) == 1


def test_snapshot_owner_expiry_token_and_capability(context):
    api, p, _, calls, _, _ = context
    change = write()
    draft = api.google_content_prepare(p, change)
    change.changes['name'] = 'Changed after preview'
    for bad, token in [(replace(p, owner_id='other'), draft['confirmationToken']),
                       (replace(p, capabilities=frozenset()), draft['confirmationToken']), (p, 'wrong')]:
        with pytest.raises(PermissionError):
            api.google_content_execute(bad, draft['previewId'], token, confirmed=True)
    api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert json.loads(calls[0][3])['name'] == 'Synthetic'
    draft = api.google_content_prepare(p, write())
    api._content.clock = lambda: draft['expiresAt'] + 1
    with pytest.raises(PermissionError):
        api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert len(calls) == 1


def test_concurrent_durable_claim_across_instances(context):
    api, p, auth, calls, _, _ = context
    gate = threading.Barrier(2)
    other = CmailApi(api.service, content_requester=api._content.requester)
    draft = api.google_content_prepare(p, write())
    def execute(target):
        gate.wait(timeout=5)
        try:
            return target.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)['status']
        except PermissionError:
            return 'denied'
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(execute, [api, other]))
    assert sorted(results) == ['completed', 'denied'] and len(calls) == 1


@pytest.mark.parametrize('failure', ['timeout', 'http', 'large'])
def test_uncertain_consumes_preview_no_retry_or_secret(context, failure):
    api, p, _, calls, _, _ = context
    def http(*args):
        calls.append(args)
        if failure == 'timeout':
            raise TimeoutError('secret-token-and-provider-body')
        return (503, {'error': 'secret-token'}) if failure == 'http' else (200, {'data': 'x'*MAX_BYTES})
    api._content.requester = http
    draft = api.google_content_prepare(p, write())
    result = api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert result['status'] == 'uncertain' and not result['retryAllowed']
    assert 'secret-token' not in json.dumps(result)
    with pytest.raises(PermissionError):
        CmailApi(api.service, content_requester=http).google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert len(calls) == 1


@pytest.mark.parametrize('change', [GoogleWrite(W.DRIVE_UPDATE, 'file-id', {'trashed': True}),
    GoogleWrite(W.DRIVE_FOLDER, changes={'name': 'x', 'permissions': []}),
    GoogleWrite(W.DOCS_BATCH, 'file-id', {'requests': [{'deleteContentRange': {}}]}),
    GoogleWrite(W.SLIDES_BATCH, 'file-id', {'requests': []}),
    GoogleWrite(W.SHEETS_UPDATE, 'file-id', {'range': 'A1', 'values': [[{}]]}),
    GoogleWrite(W.DRIVE_UPDATE, 'https://evil.test', {'name': 'x'}),
    GoogleWrite(W.DRIVE_UPDATE, 'file-id', {'name': 'x'*70000})])
def test_write_allowlist(context, change):
    api, p, _, calls, auth_calls, _ = context
    with pytest.raises(ValueError):
        api.google_content_prepare(p, change)
    assert not calls and not auth_calls


def test_revoked_owner_and_refreshed_scope_denied_before_content_http(context):
    api, p, auth, calls, _, _ = context
    old = auth.access_token
    def narrowed(identity):
        set_scopes(auth, p, GMAIL_SCOPES)
        return 'synthetic-access'
    auth.access_token = narrowed
    with pytest.raises(ConsentRequired):
        api.google_content_read(p, GoogleRead(R.DRIVE_GET, 'file-id'))
    assert not calls
    auth.access_token = old
    api.service.store.set_connection_status(p.identity_id, 'revoked')
    with pytest.raises(PermissionError):
        api.google_content_begin_consent(p, 'google.drive.read')


def test_transport_bounded_bytes_and_timeout(monkeypatch):
    import cmail.google_content as module
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read1(self, amount): return b'x' * amount
    class Opener:
        def open(self, req, timeout):
            assert timeout == 20
            assert req.full_url == 'https://docs.googleapis.com/v1/documents/synthetic'
            return Response()
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(ContentError):
        transport('GET', 'https://docs.googleapis.com/v1/documents/synthetic', {}, None)


def test_contract_cli_does_not_load_configuration(monkeypatch, capsys):
    from cmail.__main__ import main
    from cmail.config import Config
    monkeypatch.setattr(Config, 'load', lambda: pytest.fail('No configuration access permitted'))
    assert main(['google-content-contract']) == 0
    assert json.loads(capsys.readouterr().out)['readOperations']['drive.list'] == 'google.drive.read'

def test_prepare_expired_token_never_refreshes(context):
    api, p, auth, calls, auth_calls, _ = context
    file = auth._token_file(p.identity_id)
    token = file.load()
    token['expires_at'] = 0
    file.save(token)
    draft = api.google_content_prepare(p, write())
    assert draft['status'] == 'prepared' and not calls and not auth_calls


def test_scope_omission_is_not_inferred_and_full_scope_satisfies_read(context):
    api, p, auth, calls, _, _ = context
    set_scopes(auth, p, CONTENT_SCOPES['google.drive.write'])
    api.google_content_read(p, GoogleRead(R.DRIVE_GET, 'file-id'))
    token = auth._token_file(p.identity_id).load()
    token.pop('scope')
    auth._token_file(p.identity_id).save(token)
    with pytest.raises(ConsentRequired):
        api.google_content_read(p, GoogleRead(R.DRIVE_GET, 'file-id'))
    assert len(calls) == 1


def test_no_redirects_and_transport_errors_sanitized(context):
    from cmail.google_content import _NoRedirect
    assert _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://untrusted.test') is None
    api, p, *_ = context
    def bad(*args):
        raise PermissionError('synthetic-secret-must-not-leak')
    api._content.requester = bad
    with pytest.raises(ContentError) as exc:
        api.google_content_read(p, GoogleRead(R.DRIVE_GET, 'file-id'))
    assert 'secret' not in str(exc.value) and exc.value.__suppress_context__


def test_missing_scope_at_execute_keeps_preview_unclaimed(context):
    api, p, auth, calls, auth_calls, _ = context
    draft = api.google_content_prepare(p, write())
    set_scopes(auth, p, GMAIL_SCOPES)
    with pytest.raises(ConsentRequired):
        api.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert not calls and not auth_calls
    with api.service.store.connect() as db:
        assert db.execute('SELECT status FROM google_content_previews WHERE id=?', (draft['previewId'],)).fetchone()[0] == 'prepared'


def test_persisted_claim_survives_restart(context):
    api, p, auth, calls, _, _ = context
    draft = api.google_content_prepare(p, write())
    with api.service.store.connect() as db:
        db.execute("UPDATE google_content_previews SET status='claimed' WHERE id=?", (draft['previewId'],))
    fresh = CmailApi(MailService(api.service.config, auth=auth), content_requester=api._content.requester)
    with pytest.raises(PermissionError):
        fresh.google_content_execute(p, draft['previewId'], draft['confirmationToken'], confirmed=True)
    assert not calls


def test_text_download_denies_binary_and_oversize(context):
    api, p, *_ = context
    api._content.requester = lambda *args: (200, {'mimeType': 'application/pdf'})
    with pytest.raises(ValueError):
        api.google_content_read(p, GoogleRead(R.DRIVE_TEXT, 'file-id'))
    def large(*args):
        return (200, 'x' * MAX_BYTES) if args[2]['Accept'] == 'text/plain' else (200, {'mimeType': 'text/plain'})
    api._content.requester = large
    with pytest.raises(ContentError):
        api.google_content_read(p, GoogleRead(R.DRIVE_TEXT, 'file-id'))
