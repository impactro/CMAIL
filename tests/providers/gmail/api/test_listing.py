"""List summaries must not download full messages or attachment payloads."""
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from cmail.gmail import GmailProvider
from cmail.imap_listing import HEADER_BYTES, PREVIEW_BYTES, LIST_FETCH, list_summary, recent_uids
from cmail.mail import ImapSmtpProvider




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

