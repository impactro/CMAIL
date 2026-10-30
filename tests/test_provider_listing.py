"""List summaries must not download full messages or attachment payloads."""
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail.gmail import GmailProvider
from cmail.imap_listing import HEADER_BYTES, PREVIEW_BYTES, LIST_FETCH, list_summary, recent_uids
from cmail.mail import ImapSmtpProvider


def fetched(identifier='2'):
    header = (b'From: Example <sender@example.test>\r\nSubject: Planning\r\n'
              b'Content-Type: text/plain; charset=utf-8\r\n\r\n')
    return [(identifier.encode()+b' (FLAGS (\\Seen) BODYSTRUCTURE (("TEXT" "PLAIN") '
             b'("APPLICATION" "PDF" ("NAME" "file.pdf")) "MIXED") BODY[HEADER]<0> {100}',header),
            (b' BODY[TEXT]<0> {20}',b'Preview without attachment bytes'),b')']


def test_uid_tail_keeps_newest_first_without_whole_mailbox_split():
    assert recent_uids(b'1 2\t3\r\n4  ',2) == [b'4',b'3']
    assert recent_uids(b'',50) == []
    assert len(recent_uids(b' '.join(str(n).encode() for n in range(10000)),999)) == 100


def test_imap_summary_has_metadata_and_attachment_flag_without_payload():
    summary = list_summary(fetched(),'2')
    assert summary['subject'] == 'Planning'
    assert summary['from']['address'] == 'sender@example.test'
    assert summary['isRead'] and summary['hasAttachments']
    assert summary['attachments'] == [] and summary['body'] == ''
    assert summary['preview'] == 'Preview without attachment bytes'


def test_imap_listing_uses_bounded_peek_and_preserves_folder_context():
    client = Mock(); client.select.return_value = ('OK',[])
    client.uid.side_effect = lambda command,*args: ('OK',[b'1 2 3']) if command == 'search' else ('OK',fetched(args[0]))
    provider = ImapSmtpProvider(SimpleNamespace())
    provider._imap = Mock(return_value=client)
    messages = provider.messages('Projects',2)
    assert [item['id'] for item in messages] == ['3','2']
    assert client.uid.call_count == 3
    client.select.assert_called_once_with('"Projects"',readonly=True)
    assert 'RFC822' not in LIST_FETCH and 'BODY.PEEK[HEADER]<0.16384>' in LIST_FETCH
    assert 'BODY.PEEK[TEXT]<0.4096>' in LIST_FETCH
    client.logout.assert_called_once()


def test_oversized_imap_preview_is_not_parsed_or_retained():
    with pytest.raises(ValueError,match='limite'):
        list_summary([(b'BODY[HEADER]',b'x'*(HEADER_BYTES+1))],'1')
    with pytest.raises(ValueError,match='limite'):
        list_summary([(b'BODY[HEADER]',b''),(b'BODY[TEXT]',b'x'*(PREVIEW_BYTES+1))],'1')


def test_gmail_listing_requests_only_needed_headers_and_enforces_result_limit():
    provider = object.__new__(GmailProvider)
    calls = []

    def request(method,path):
        calls.append(path)
        if path.startswith('/messages?'):
            return {'messages':[{'id':str(n)} for n in range(10)]}
        return {'id':'test','payload':{'headers':[]}}

    provider._call = request
    assert len(provider.messages('INBOX',2)) == 2 and len(calls) == 3
    for path in calls[1:]:
        query = parse_qs(urlsplit(path).query)
        assert query['format'] == ['metadata']
        assert set(query['metadataHeaders']) == {'From','To','Cc','Reply-To','Subject','Date','Message-ID'}
