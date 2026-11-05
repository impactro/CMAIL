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
