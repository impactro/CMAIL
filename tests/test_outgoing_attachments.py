"""Synthetic bytes/accounts/providers only. No network, OAuth or delivery."""
import base64
import copy
import hashlib
import json
import smtplib
from dataclasses import replace
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.api import CmailApi, create_api
from cmail.store import Store
from cmail.service import MailService
from cmail.principal import Principal
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import ImapSmtpProvider
from cmail.outgoing_attachments import normalize, MAX_BYTES
from helpers import config, FakeMail
from test_inline_images import image, HTML, PNG
from providers.gmail.oauth_smtp.test_smtp import settings, smtp
from providers.gmail.oauth_file.test_api import credentials


def file(raw=b'%PDF-1.4 synthetic', name='Proposta.pdf'):
    return {'name': name, 'contentType': 'application/pdf', 'contentBase64': base64.b64encode(raw).decode()}


def packet():
    return {'recipients': ['recipient@example.test'], 'subject': 'Proposta', 'body': 'Arquivo de teste',
            'bodyHtml': HTML, 'inlineImages': [image()], 'attachments': [file()]}


def assert_files(message):
    msg = message_from_bytes(message.as_bytes(), policy=default)
    assert msg.get_content_type() == 'multipart/mixed'
    ordinary = [p for p in msg.walk() if p.get_content_disposition() == 'attachment']
    assert len(ordinary) == 1
    assert ordinary[0].get_filename() == 'Proposta.pdf'
    assert ordinary[0].get_payload(decode=True) == b'%PDF-1.4 synthetic'
    inline = [p for p in msg.walk() if p.get_content_disposition() == 'inline']
    assert inline[0].get_payload(decode=True) == PNG
    assert str(inline[0]['Content-ID']) == '<mark>'


def test_snapshot_freezes_bytes_and_preview_contains_only_file_metadata(tmp_path):
    store = Store(tmp_path)
    original = packet()
    draft = store.prepare(original, 'owner')
    original['attachments'][0]['contentBase64'] = 'changed'
    assert draft['attachmentSummary'][0]['sha256'] == hashlib.sha256(b'%PDF-1.4 synthetic').hexdigest()
    assert 'attachments' not in draft['preview']
    assert 'contentBase64' not in json.dumps(draft['attachmentSummary'])
    claimed = store.claim(draft['draftId'], draft['confirmationToken'], 'owner')
    assert claimed['attachments'] == [file()]
    with pytest.raises(ValueError):
        store.claim(draft['draftId'], draft['confirmationToken'], 'owner')


@pytest.mark.parametrize('tamper', ['bytes', 'remove', 'remove-manifest'])
def test_hash_or_missing_file_rejects_before_claim(tmp_path, tamper):
    store = Store(tmp_path)
    draft = store.prepare(packet(), 'owner')
    with store.connect() as db:
        value = json.loads(db.execute('SELECT payload_json FROM mail_drafts').fetchone()[0])
        if tamper == 'bytes': value['attachments'][0] = file(b'changed')
        else: value['attachments'] = []
        if tamper == 'remove-manifest': value.pop('attachmentManifest')
        db.execute('UPDATE mail_drafts SET payload_json=?', (json.dumps(value),))
    with pytest.raises(ValueError, match='Integridade'):
        store.claim(draft['draftId'], draft['confirmationToken'], 'owner')
    with store.connect() as db:
        assert db.execute('SELECT status FROM mail_drafts').fetchone()[0] == 'prepared-files-v1'


@pytest.mark.parametrize('value', [None, [file()] * 9, [file(b'')], [file(b'x'*(MAX_BYTES+1))],
    [{**file(), 'path': 'secret'}], [file(name='../secret')], [file(name='a\nb')],
    [{**file(), 'contentBase64': '!bad'}], [{**file(), 'contentType': 'application/pdf\r\nX:y'}]])
def test_invalid_payloads_rejected(value):
    with pytest.raises(ValueError): normalize(value)


def test_combined_inline_limit_and_reply_rejection(tmp_path):
    value = packet()
    value['attachments'] = [file(b'x'*MAX_BYTES)]
    with pytest.raises(ValueError, match='somados'):
        Store(tmp_path).prepare(value)
    with pytest.raises(ValueError, match='resposta'):
        Store(tmp_path).prepare(packet(), message_action={'kind': 'reply'})


def test_gmail_and_graph_file_plus_inline_are_distinct():
    gmail = object.__new__(GmailProvider)
    gmail._call = Mock(return_value={'id':'synthetic'})
    gmail.send(['a@example.test'], 'S', 'B', body_html=HTML, inline_images=[image()], attachments=[file()])
    raw = gmail._call.call_args.args[2]['raw']
    assert_files(message_from_bytes(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)), policy=default))
    graph = object.__new__(MicrosoftGraphProvider)
    graph._call = Mock()
    graph.send(['a@example.test'], 'S', 'B', body_html=HTML, inline_images=[image()], attachments=[file()])
    assets = graph._call.call_args.args[2]['message']['attachments']
    assert assets[0]['isInline'] is True and assets[1]['isInline'] is False
    assert assets[1]['contentBytes'] == file()['contentBase64']


def test_imap_smtp_mime_and_no_network_before_validation():
    messages = []
    client = SimpleNamespace(login=lambda *a:None, quit=lambda:None,
                             send_message=lambda m: messages.append(m) or {})
    factory = Mock(return_value=client)
    cfg = SimpleNamespace(account='sender@example.test', password=lambda:'synthetic',
                          username='sender', smtp_security='ssl', smtp_host='test', smtp_port=465)
    provider = ImapSmtpProvider(cfg, smtp_ssl_factory=factory)
    provider.send(['a@example.test'], 'S', 'B', body_html=HTML, inline_images=[image()], attachments=[file()])
    assert_files(messages[0])
    with pytest.raises(ValueError):
        provider.send(['a@example.test'], 'S', 'B', attachments=[file(name='../invalid')])
    assert factory.call_count == 1


def test_gmail_smtp_snapshot_single_claim_and_uncertain(settings, smtp):
    credentials(settings)
    api = create_api(settings)
    p = Principal.local_operator()
    draft = api.prepare_send(p, packet())
    smtp[0].assert_not_called()
    api.execute_send(p, draft['draftId'], draft['confirmationToken'])
    assert_files(smtp[1].send_message.call_args.args[0])
    with pytest.raises(ValueError): api.execute_send(p, draft['draftId'], draft['confirmationToken'])
    next_draft = api.prepare_send(p, packet())
    smtp[1].send_message.side_effect = smtplib.SMTPServerDisconnected('synthetic')
    with pytest.raises(ValueError): api.execute_send(p, next_draft['draftId'], next_draft['confirmationToken'])
    with pytest.raises(ValueError): api.execute_send(p, next_draft['draftId'], next_draft['confirmationToken'])
    assert smtp[1].send_message.call_count == 2


def test_account_change_and_unsupported_provider_reject(tmp_path):
    service = MailService(config(tmp_path))
    api = CmailApi(service)
    p = service.principal_for_owner('owner', frozenset({'mail.send'}))
    draft = api.prepare_send(p, packet())
    changed = replace(p, identity_id='different')
    with pytest.raises(ValueError, match='conta'):
        api.execute_send(changed, draft['draftId'], draft['confirmationToken'])
    unsupported = MailService(service.config, FakeMail())
    with pytest.raises(ValueError, match='provedor'):
        unsupported.prepare(packet(), p)


def test_graph_direct_request_limit_rejects_before_http():
    graph = object.__new__(MicrosoftGraphProvider)
    graph._call = Mock()
    with pytest.raises(ValueError, match='limite'):
        graph.send(['x'*4_200_000+'@example.test'], 'S', 'B', attachments=[file()])
    graph._call.assert_not_called()


def test_attachment_drafts_cannot_be_claimed_as_legacy_text_only(tmp_path):
    store = Store(tmp_path)
    store.prepare(packet(), 'owner')
    store.prepare({'recipients':['a@example.test'], 'subject':'S', 'body':'B'}, 'owner')
    with store.connect() as db:
        # Pre-attachment executors accept only status=prepared. Their view must
        # contain the plain draft only, avoiding silent file loss on rollback.
        rows = db.execute("SELECT payload_json FROM mail_drafts WHERE status='prepared'").fetchall()
        assert len(rows) == 1 and 'attachments' not in json.loads(rows[0][0])
