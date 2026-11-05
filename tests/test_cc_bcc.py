"""Synthetic recipient routing; no real accounts, network or mail delivery."""
import base64
import smtplib
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.store import Store
from cmail.service import MailService
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import ImapSmtpProvider
from cmail.gmail_smtp import GmailSmtpProvider

BASE = {'recipients': ['to@example.test'], 'cc': ['cc@example.test'],
        'bcc': ['hidden@example.test'], 'subject': 'Teste', 'body': 'Corpo'}


def test_preview_freezes_groups_and_single_claim(tmp_path):
    store = Store(tmp_path)
    draft = store.prepare(BASE, 'owner')
    assert draft['preview'] == BASE
    assert draft['recipientCount'] == 3
    with pytest.raises(ValueError):
        store.claim(draft['draftId'], draft['confirmationToken'], 'other')
    assert store.claim(draft['draftId'], draft['confirmationToken'], 'owner') == BASE
    with pytest.raises(ValueError):
        store.claim(draft['draftId'], draft['confirmationToken'], 'owner')


@pytest.mark.parametrize('value', ['x@example.test', [1], ['bad'], ['a@example.test\r\nBcc: b@example.test'], ['a@example.test,b@example.test'], None, ['']])
@pytest.mark.parametrize('key', ['cc', 'bcc'])
def test_invalid_copies_rejected(tmp_path, key, value):
    with pytest.raises(ValueError):
        Store(tmp_path).prepare({**BASE, key: value})


def test_deduplication_precedence_and_total_limit(tmp_path):
    store = Store(tmp_path)
    draft = store.prepare({**BASE, 'cc': ['TO@example.test', 'CC@example.test'],
                           'bcc': ['cc@example.test', 'hidden@example.test']})
    assert draft['preview'] == BASE
    with pytest.raises(ValueError):
        store.prepare({**BASE, 'bcc': [f'p{i}@example.test' for i in range(999)]})


def test_service_dispatch_and_legacy_compatibility(tmp_path):
    provider = SimpleNamespace(send=Mock(return_value={'accepted': True}))
    service = MailService(SimpleNamespace(mode='demo', state_dir=tmp_path), provider)
    draft = service.prepare(BASE)
    service.execute(draft['draftId'], draft['confirmationToken'])
    provider.send.assert_called_once_with(BASE['recipients'], BASE['subject'], BASE['body'], cc=BASE['cc'], bcc=BASE['bcc'])
    provider.send.reset_mock()
    legacy = {k: v for k, v in BASE.items() if k not in {'cc', 'bcc'}}
    draft = service.prepare(legacy)
    service.execute(draft['draftId'], draft['confirmationToken'])
    provider.send.assert_called_once_with(legacy['recipients'], legacy['subject'], legacy['body'])


def test_gmail_and_graph_native_groups():
    gmail = object.__new__(GmailProvider)
    gmail._call = Mock(return_value={'id': 'synthetic'})
    result = gmail.send(BASE['recipients'], 'Teste', 'Corpo', cc=BASE['cc'], bcc=BASE['bcc'])
    raw = gmail._call.call_args.args[2]['raw']
    msg = message_from_bytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)), policy=default)
    assert str(msg['To']) == BASE['recipients'][0]
    assert str(msg['Cc']) == BASE['cc'][0]
    assert str(msg['Bcc']) == BASE['bcc'][0]  # Provider submission, not delivered MIME.
    assert result['recipientCount'] == 3
    graph = object.__new__(MicrosoftGraphProvider)
    graph._call = Mock()
    graph.send(BASE['recipients'], 'Teste', 'Corpo', cc=BASE['cc'], bcc=BASE['bcc'])
    payload = graph._call.call_args.args[2]['message']
    for key, addresses in [('toRecipients', BASE['recipients']), ('ccRecipients', BASE['cc']), ('bccRecipients', BASE['bcc'])]:
        assert payload[key] == [{'emailAddress': {'address': a}} for a in addresses]


def test_smtp_envelope_contains_bcc_but_wire_does_not():
    # Exercise the real stdlib send_message serialization without a socket.
    client = object.__new__(smtplib.SMTP)
    client.ehlo_or_helo_if_needed = lambda: None
    client.sendmail = Mock(return_value={})
    client.login = Mock()
    client.quit = Mock()
    config = SimpleNamespace(account='sender@example.test', username='sender', password=lambda: 'synthetic',
                             smtp_security='ssl', smtp_host='fake', smtp_port=465)
    provider = ImapSmtpProvider(config, smtp_ssl_factory=lambda *a, **k: client)
    provider.send(BASE['recipients'], 'Teste', 'Corpo', cc=BASE['cc'], bcc=BASE['bcc'])
    sender, envelope, wire = client.sendmail.call_args.args[:3]
    assert set(envelope) == set(BASE['recipients'] + BASE['cc'] + BASE['bcc'])
    msg = message_from_bytes(wire, policy=default)
    assert msg['Bcc'] is None
    assert b'hidden@example.test' not in wire
    assert str(msg['Cc']) == BASE['cc'][0]


def test_gmail_smtp_uses_explicit_envelope_without_bcc_header():
    client = Mock()
    client.send_message.return_value = {}
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    auth = SimpleNamespace(config=SimpleNamespace(gmail_file_account='sender@example.test'),
                           access_token=lambda: 'synthetic', connection=lambda token: context)
    GmailSmtpProvider(auth).send(BASE['recipients'], 'Teste', 'Corpo', cc=BASE['cc'], bcc=BASE['bcc'])
    assert client.send_message.call_args.kwargs['to_addrs'] == BASE['recipients'] + BASE['cc'] + BASE['bcc']
    msg = client.send_message.call_args.args[0]
    assert msg['Bcc'] is None
    assert str(msg['Cc']) == BASE['cc'][0]
