import base64
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail.annotation_reader import AnnotationReader
from cmail.gmail import GmailProvider
from cmail.principal import Principal, READ_MAIL




def test_gmail_nested_parts_page_and_attachments_are_get_only():
    content = base64.urlsafe_b64encode(b'proposta de teste').decode()
    payload = {'parts': [{'mimeType': 'multipart/mixed', 'parts': [
        {'partId': '1.0', 'mimeType': 'text/plain', 'body': {'data': content}},
        {'partId': '1.1', 'filename': 'proposal.txt', 'mimeType': 'text/plain',
         'body': {'size': 17, 'attachmentId': 'attachment-id'}}]}]}
    message = {'id': 'message-id', 'internalDate': '1793707200000', 'payload': payload}
    calls = []
    def call(method, path, *args, **kwargs):
        assert method == 'GET'
        calls.append(path)
        if '/attachments/' in path:
            return {'data': content}
        if path.startswith('/messages?'):
            params = parse_qs(urlsplit(path).query)
            assert params['pageToken'] == ['opaque-next']
            assert 'after:' in params['q'][0]
            return {'messages': [{'id': 'message-id'}], 'nextPageToken': 'third-page'}
        return message
    provider = GmailProvider(None, 'test')
    provider._call = call
    result = provider.annotation_page(since='2026-11-02T00:00:00+00:00',
        until='2026-11-03T00:00:00+00:00', cursor='opaque-next')
    assert result['nextCursor'] == 'third-page'
    dto = provider.message('INBOX', 'message-id')
    assert dto['body'] == 'proposta de teste'
    assert dto['attachments'][0]['id'] == 'part:1.1'
    value = provider.attachment('message-id', 'attachment-id')
    assert base64.b64decode(value['contentBase64']) == b'proposta de teste'
    with pytest.raises(ValueError, match='não pertence'):
        provider.attachment('message-id', 'other-id')
