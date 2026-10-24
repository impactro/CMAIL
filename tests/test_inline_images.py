"""Synthetic assets/providers only: no real account, network or email."""
import base64
import copy
import hashlib
import json
import smtplib
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.inline_images import MAX_BYTES, add_body, normalize
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import ImapSmtpProvider
from cmail.store import Store
from cmail import Principal, create_api
from cmail.enviar import main as enviar_main
from test_gmail_smtp import settings, smtp
from test_gmail_file import credentials


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhZkAAAAASUVORK5CYII=')
HTML = '<p>Olá, ação</p><img src="cid:mark">'


def image(identifier='mark', raw=PNG):
    return {'contentId': identifier, 'contentType': 'image/png',
            'contentBase64': base64.b64encode(raw).decode('ascii'), 'name': 'marca.png'}


def payload():
    return {'recipients': ['recipient@example.test'], 'subject': 'Apresentação',
            'body': 'Olá, ação', 'bodyHtml': HTML, 'inlineImages': [image()]}


def assert_mime(message):
    roundtrip = message_from_bytes(message.as_bytes(), policy=default)
    assert roundtrip.get_body(preferencelist=('plain',)).get_content().strip() == 'Olá, ação'
    assert roundtrip.get_body(preferencelist=('html',)).get_content().strip() == HTML
    parts = [part for part in roundtrip.walk() if part.get_content_type() == 'image/png']
    assert len(parts) == 1
    assert str(parts[0]['Content-ID']) == '<mark>'
    assert parts[0].get_content_disposition() == 'inline'
    assert parts[0].get_filename() == 'marca.png'
    assert parts[0].get_payload(decode=True) == PNG
    assert any(part.get_content_type() == 'multipart/related' for part in roundtrip.walk())


def test_mime_related_roundtrips_exact_public_body_and_image():
    message = EmailMessage()
    add_body(message, 'Olá, ação', HTML, [image()])
    assert_mime(message)


def test_confirmed_snapshot_keeps_assets_immutable_and_single_claim(tmp_path):
    store = Store(tmp_path)
    original = payload(); expected = copy.deepcopy(original)
    draft = store.prepare(original, 'operator')
    original['inlineImages'][0]['contentBase64'] = 'changed-after-preview'
    assert draft['inlineImageSummary'] == [{'contentId': 'mark', 'contentType': 'image/png',
        'name': 'marca.png', 'bytes': len(PNG), 'sha256': hashlib.sha256(PNG).hexdigest()}]
    assert 'contentBase64' not in draft['inlineImageSummary'][0]
    assert store.claim(draft['draftId'], draft['confirmationToken'], 'operator') == expected
    with pytest.raises(ValueError):store.claim(draft['draftId'], draft['confirmationToken'], 'operator')


@pytest.mark.parametrize('change', [
    {'contentId': 'bad\r\nHeader'}, {'contentType': 'image/svg+xml'},
    {'contentBase64': 'not base64!'}, {'contentBase64': base64.b64encode(b'not an image').decode()},
    {'file': '/private/file.png'}, {'name': '../file.png'}, {'name': 'bad\x00.png'},
])
def test_invalid_images_fail_before_journal(tmp_path, change):
    store = Store(tmp_path); value = payload(); value['inlineImages'][0].update(change)
    with pytest.raises(ValueError):store.prepare(value, 'operator')
    with store.connect() as db:assert db.execute('SELECT count(*) FROM mail_drafts').fetchone()[0] == 0


@pytest.mark.parametrize('images,html', [
    ([], HTML), ([image()], '<p>No image reference</p>'),
    ([image(), image()], HTML), (None, HTML),
    ([image(str(i)) for i in range(9)], '<p>Too many</p>'),
    ([image()], '<img src="cid:invalid/id">'),
])
def test_cid_bijection_count_and_type_are_required(images, html):
    with pytest.raises(ValueError):normalize(images, html)


def test_byte_limit_per_message_not_per_individual_image():
    raw = b'\x89PNG\r\n\x1a\n' + b'x' * (MAX_BYTES // 2)
    with pytest.raises(ValueError):normalize([image('one', raw), image('two', raw)],
        '<img src="cid:one"><img src="cid:two">')
    with pytest.raises(ValueError):normalize([image(raw=b'\x89PNG\r\n\x1a\n' + b'x' * MAX_BYTES)], HTML)


def test_no_images_and_ordinary_external_images_preserve_old_route():
    assert normalize([], '<img src="https://example.test/logo.png"><img src>') == []
    assert normalize([], '') == []
    with pytest.raises(ValueError):normalize([], 'x' * 200001)


def test_gmail_api_mime_contains_related_image_without_new_http_route():
    provider = object.__new__(GmailProvider); calls = []
    provider._call = lambda *args: calls.append(args) or {'id': 'synthetic'}
    provider.send(['recipient@example.test'], 'Apresentação', 'Olá, ação',
                  body_html=HTML, inline_images=[image()])
    assert calls[0][:2] == ('POST', '/messages/send')
    raw = calls[0][2]['raw']
    assert_mime(message_from_bytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)), policy=default))


def test_graph_native_inline_image_matches_snapshot():
    provider = object.__new__(MicrosoftGraphProvider); provider._call = Mock()
    provider.send(['recipient@example.test'], 'Apresentação', 'Olá, ação',
                  body_html=HTML, inline_images=[image()])
    submitted = provider._call.call_args.args[2]['message']
    assert submitted['body'] == {'contentType': 'HTML', 'content': HTML}
    assert submitted['attachments'] == [{'@odata.type': '#microsoft.graph.fileAttachment',
        'name': 'marca.png', 'contentType': 'image/png', 'contentId': 'mark',
        'isInline': True, 'contentBytes': image()['contentBase64']}]


def test_imap_smtp_uses_same_related_mime_builder():
    captured = []
    client = SimpleNamespace(login=lambda *a: None,
        send_message=lambda m: captured.append(m) or {}, quit=lambda: None)
    config = SimpleNamespace(account='sender@example.test', password=lambda: 'fake',
        username='fake', smtp_security='ssl', smtp_host='fake', smtp_port=465)
    provider = ImapSmtpProvider(config, smtp_ssl_factory=lambda *a, **k: client)
    provider.send(['recipient@example.test'], 'Apresentação', 'Olá, ação',
                  body_html=HTML, inline_images=[image()])
    assert_mime(captured[0])


def test_gmail_smtp_two_phase_inline_and_no_repeat(settings, smtp):
    credentials(settings)
    api = create_api(settings); principal = Principal.local_operator()
    draft = api.prepare_send(principal, payload())
    smtp[0].assert_not_called()
    result = api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert result['delivery'] == 'submitted'
    assert_mime(smtp[1].send_message.call_args.args[0])
    with pytest.raises(ValueError):api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert smtp[1].send_message.call_count == 1


def test_inline_uncertain_smtp_never_replays(settings, smtp):
    credentials(settings)
    api = create_api(settings); principal = Principal.local_operator()
    draft = api.prepare_send(principal, payload())
    smtp[1].send_message.side_effect = smtplib.SMTPServerDisconnected('fake-provider-secret')
    with pytest.raises(ValueError, match='incerto'):api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    with pytest.raises(ValueError):api.execute_send(principal, draft['draftId'], draft['confirmationToken'])
    assert smtp[1].send_message.call_count == 1


def test_cli_preparation_passes_explicit_images_and_execute_refuses_replacement(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'images.json'; path.write_text(json.dumps([image()]))
    html = tmp_path / 'body.html'; html.write_text(HTML, encoding='utf-8')
    monkeypatch.setattr('cmail.enviar.Config.from_file', lambda p: SimpleNamespace(mode='gmail-file'))
    api = Mock(); api.prepare_send.return_value = {'draftId': 'synthetic-draft'}
    factory = Mock(return_value=api); monkeypatch.setattr('cmail.enviar.create_api', factory)
    args = ['--gmail', '--config-file', 'synthetic', '--to', 'recipient@example.test',
        '--subject', 'Apresentação', '--body', 'Olá, ação', '--html-file', str(html),
        '--inline-images-json', str(path)]
    assert enviar_main(args) == 0
    assert api.prepare_send.call_args.args[1]['inlineImages'] == [image()]
    api.execute_send.assert_not_called()
    factory.reset_mock()
    assert enviar_main(['--gmail', '--config-file', 'synthetic', '--execute', '--draft-id', 'old',
        '--confirmation-token', 'fake', '--inline-images-json', str(path)]) == 1
    factory.assert_not_called()
