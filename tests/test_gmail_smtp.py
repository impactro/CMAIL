"""Synthetic SMTP/OAuth only; no real credentials, network or delivery."""
import json
import smtplib
import ssl
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail import Config, Principal, create_api
from cmail.auth import AuthenticationError
from cmail.config import ConfigError
from cmail.gmail import GOOGLE_TOKEN
from cmail.gmail_file import create_file_auth, main as gmail_main
from cmail.gmail_smtp import GmailSmtpAuth, GmailSmtpProvider
from cmail.gmail_consent import GmailFileConsent
from test_gmail_file import credentials


@pytest.fixture
def settings(tmp_path):
    value = json.loads((Path(__file__).parents[1] / 'config.gmail-file.example.json').read_text(encoding='utf-8'))
    value['schemaVersion'] = '1.3'
    value['gmailFile']['transport'] = 'smtp'
    value['gmailFile']['account'] = 'sender@example.com'
    value['gmailFile']['tokenFile'] = 'authorized.json'
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return Config.from_file(path)


@pytest.fixture
def smtp(monkeypatch):
    client = Mock()
    client.ehlo.return_value = (250, b'ok')
    client.auth.return_value = (235, b'ok')
    client.noop.return_value = (250, b'ok')
    client.send_message.return_value = {}
    factory = Mock(return_value=client)
    monkeypatch.setattr('cmail.gmail_smtp.smtplib.SMTP', factory)
    return factory, client


def test_explicit_transport_pins_tls_and_validates_account_without_rest(settings, smtp):
    original = credentials(settings)
    http = Mock()
    auth = GmailSmtpAuth(settings, requester=http)
    assert auth.status()['account'] == 'sender@example.com'
    factory, client = smtp
    factory.assert_called_once_with('smtp.gmail.com', 587, timeout=20)
    tls = client.starttls.call_args.kwargs['context']
    assert tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED
    assert [x[0] for x in client.mock_calls[:4]] == ['ehlo', 'starttls', 'ehlo', 'auth']
    mechanism, challenge = client.auth.call_args.args
    assert mechanism == 'XOAUTH2'
    assert challenge() == 'user=sender@example.com\x01auth=Bearer fake-access\x01\x01'
    assert challenge(b'failure') == ''
    client.send_message.assert_not_called()
    http.assert_not_called()
    assert settings.gmail_token_file.read_bytes() == original


def test_smtp_refresh_in_memory_uses_shared_fixed_token_endpoint(settings, smtp):
    original = credentials(settings, expiry='2000-01-01T00:00:00Z')
    http = Mock(return_value=(200, {'access_token': 'renewed-fake', 'expires_in': 3600}))
    auth = GmailSmtpAuth(settings, requester=http)
    assert auth.access_token() == auth.access_token() == 'renewed-fake'
    assert http.call_count == 1 and http.call_args.args[1] == GOOGLE_TOKEN
    assert settings.gmail_token_file.read_bytes() == original


@pytest.mark.parametrize('operation', ['ehlo', 'starttls', 'auth', 'noop'])
def test_auth_tls_or_identity_failure_is_sanitized_and_never_sends(settings, smtp, operation):
    credentials(settings)
    _, client = smtp
    getattr(client, operation).side_effect = RuntimeError('fake-secret-provider-response')
    with pytest.raises(AuthenticationError) as error:
        GmailSmtpAuth(settings).status()
    assert 'fake-secret' not in str(error.value)
    client.send_message.assert_not_called()


def test_non_success_auth_is_not_identity_validation(settings, smtp):
    credentials(settings)
    smtp[1].auth.return_value = (503, b'already authenticated')
    with pytest.raises(AuthenticationError): GmailSmtpAuth(settings).status()


def test_two_phase_api_preserves_html_sender_bcc_and_no_replay(settings, smtp):
    credentials(settings)
    api = create_api(settings)
    principal = Principal.local_operator()
    payload = {'recipients': ['one@example.com', 'two@example.com'], 'subject': 'Ação',
               'body': 'Olá, São Paulo', 'bodyHtml': '<p>Olá, São Paulo</p>'}
    draft = api.prepare_send(principal, payload)
    smtp[0].assert_not_called()
    result = api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert result['accepted'] and result['delivery'] == 'submitted'
    _, client = smtp
    message = client.send_message.call_args.args[0]
    assert message['From'] == settings.gmail_file_account
    assert str(message['To']) == 'undisclosed-recipients:;'
    assert message['Bcc'] is None
    assert message.get_body(preferencelist=('html',)).get_content().strip() == payload['bodyHtml']
    assert client.send_message.call_args.kwargs['to_addrs'] == payload['recipients']
    with pytest.raises(ValueError): api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert client.send_message.call_count == 1


@pytest.mark.parametrize('failure', ['disconnect', 'partial'])
def test_uncertain_data_never_replays(settings, smtp, failure):
    credentials(settings)
    client = smtp[1]
    if failure == 'disconnect':
        client.send_message.side_effect = smtplib.SMTPServerDisconnected('fake-secret')
    else:
        client.send_message.return_value = {'one@example.com': (550, b'fake-secret')}
    api = create_api(settings)
    principal = Principal.local_operator()
    draft = api.prepare_send(principal, {'recipients': ['one@example.com'], 'subject': 'A', 'body': 'Olá'})
    with pytest.raises(ValueError) as error:
        api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert 'fake-secret' not in str(error.value)
    with pytest.raises(ValueError): api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert client.send_message.call_count == 1


def test_post_data_quit_failure_does_not_reclassify_accepted_message(settings, smtp):
    credentials(settings)
    smtp[1].quit.side_effect = smtplib.SMTPServerDisconnected('after DATA')
    assert GmailSmtpProvider(GmailSmtpAuth(settings)).send(['one@example.com'], 'A', 'Olá')['accepted']
    assert smtp[1].send_message.call_count == 1


def test_rest_remains_default_and_transport_change_cannot_claim_old_draft(settings):
    api_config = replace(settings, gmail_file_transport='api')
    assert type(create_file_auth(api_config)).__name__ == 'GmailFileAuth'
    with pytest.raises(ValueError): GmailSmtpAuth(api_config)
    api = create_api(api_config)
    principal = Principal.local_operator()
    draft = api.prepare_send(principal, {'recipients': ['one@example.com'], 'subject': 'A', 'body': 'B'})
    with pytest.raises(ValueError): create_api(settings).execute_send(principal, draft['draftId'], draft['confirmationToken'])


@pytest.mark.parametrize('transport', ['auto', 'http://evil.example', '', 7])
def test_schema_rejects_bad_transport(settings, transport):
    value = json.loads(settings.config_file.read_text(encoding='utf-8'))
    value['gmailFile']['transport'] = transport
    settings.config_file.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ConfigError): Config.from_file(settings.config_file)


def test_cli_status_uses_smtp_without_rest(settings, smtp, capsys):
    credentials(settings)
    assert gmail_main(['status', '--config-file', str(settings.config_file)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['connected'] and value['transport'] == 'smtp'
    for action in (lambda: GmailSmtpProvider(GmailSmtpAuth(settings)).folders(),
                   lambda: GmailSmtpProvider(GmailSmtpAuth(settings)).messages('INBOX'),
                   lambda: GmailSmtpProvider(GmailSmtpAuth(settings)).message('INBOX', 'id')):
        with pytest.raises(NotImplementedError): action()


@pytest.mark.parametrize('accepted', [True, False])
def test_smtp_consent_scope_and_identity_before_new_token(settings, smtp, tmp_path, accepted):
    client = tmp_path / 'desktop.json'
    client.write_text(json.dumps({'installed': {'client_id': 'fake', 'client_secret': 'fake'}}))
    output = tmp_path / 'new.json'
    http = Mock(return_value=(200, {'access_token': 'fake-token', 'refresh_token': 'fake-refresh', 'expires_in': 3600}))
    flow = GmailFileConsent(client, output, 'sender@example.com',
        'http://127.0.0.1:54321/auth/callback', requester=http, transport='smtp')
    query = parse_qs(urlsplit(flow.authorization_url()).query)
    assert query['scope'] == ['https://mail.google.com/']
    assert query['code_challenge_method'] == ['S256']
    callback = flow.redirect_uri + '?state=' + query['state'][0] + '&code=fake'
    if accepted:
        assert flow.complete(callback)['authorized']
        assert json.loads(output.read_text())['scopes'] == ['https://mail.google.com/']
    else:
        smtp[1].auth.side_effect = smtplib.SMTPAuthenticationError(535, b'wrong mailbox')
        with pytest.raises(AuthenticationError): flow.complete(callback)
        assert not output.exists()
    assert http.call_count == 1 and http.call_args.args[1] == GOOGLE_TOKEN
    smtp[1].send_message.assert_not_called()
