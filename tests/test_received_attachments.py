"""Regressões encontradas na validação real, reproduzidas sem rede ou contas."""
import base64
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cmail.gmail import GmailProvider
from cmail.mail import ImapSmtpProvider, MailError


def test_gmail_resolves_rotating_download_id_from_stable_part():
    provider = GmailProvider(None, 'test')
    calls = []
    def call(method, path):
        assert method == 'GET'
        calls.append(path)
        if '/attachments/' in path:
            assert path.endswith('/fresh-id')
            return {'data': base64.urlsafe_b64encode(b'pdf-data').decode()}
        download_id = 'first-id' if len(calls) == 1 else 'fresh-id'
        return {'id':'m', 'payload':{'parts':[{'partId':'1.2', 'filename':'test.pdf',
            'mimeType':'application/pdf', 'body':{'attachmentId':download_id,'size':8}}]}}
    provider._call = call
    row = provider.message('INBOX', 'm')['attachments'][0]
    assert row['id'] == 'part:1.2'
    assert base64.b64decode(provider.attachment('m', row['id'])['contentBase64']) == b'pdf-data'
    with pytest.raises(ValueError, match='não pertence'):
        provider.attachment('m','part:9')


def test_imap_nested_inline_and_file_download_are_peek_only():
    message = EmailMessage()
    message.set_content('Texto')
    message.add_alternative('<p>HTML</p><img src="cid:img">', subtype='html')
    message.get_payload()[1].add_related(b'image', maintype='image', subtype='png', cid='<img>', filename='img.png')
    message.add_attachment(b'pdf-data', maintype='application', subtype='pdf', filename='test.pdf')
    client = Mock()
    client.select.return_value = ('OK', [])
    client.uid.return_value = ('OK', [(b'1 (FLAGS ())', message.as_bytes())])
    provider = ImapSmtpProvider(SimpleNamespace())
    provider._imap = lambda: client
    rows = provider.message('INBOX','42')['attachments']
    assert [r['name'] for r in rows] == ['img.png','test.pdf']
    for row, expected in zip(rows, [b'image', b'pdf-data']):
        value = provider.attachment('42', row['id'])
        assert base64.b64decode(value['contentBase64']) == expected
    assert all(c.args == ('"INBOX"',) and c.kwargs == {'readonly':True} for c in client.select.call_args_list)
    assert all(c.args == ('fetch','42','(BODY.PEEK[] FLAGS)') for c in client.uid.call_args_list)
    with pytest.raises(MailError, match='não pertence'):
        provider.attachment('42','part:999')
    with pytest.raises(MailError, match='inválido'):
        provider.attachment('42','../file')
    client.logout.assert_called()
