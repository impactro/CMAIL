"""Lightweight IMAP summaries: bounded PEEK sections, never full attachments."""
from __future__ import annotations

import email
import re
from email.policy import default

from .mime_read import _dto, _plain_body

HEADER_BYTES = 16 * 1024
PREVIEW_BYTES = 4 * 1024
LIST_FETCH = (f'(FLAGS BODYSTRUCTURE BODY.PEEK[HEADER]<0.{HEADER_BYTES}> '
              f'BODY.PEEK[TEXT]<0.{PREVIEW_BYTES}>)')
WHITESPACE = b' \r\n\t\v\f'


def recent_uids(raw: bytes, limit=50):
    """Read only the tail without allocating one object for every UID in a mailbox."""
    end = len(raw)
    result = []
    for _ in range(max(1, min(int(limit), 100))):
        while end and raw[end - 1] in WHITESPACE:
            end -= 1
        if not end:
            break
        start = end
        while start and raw[start - 1] not in WHITESPACE:
            start -= 1
        result.append(raw[start:end])
        end = start
    return result


def list_summary(fetched, identifier):
    header, text, metadata = None, b'', []
    for entry in fetched:
        if isinstance(entry, tuple) and isinstance(entry[0], bytes) and isinstance(entry[1], bytes):
            metadata.append(entry[0])
            label = entry[0].upper()
            if b'BODY[HEADER]' in label:
                header = entry[1]
            elif b'BODY[TEXT]' in label:
                text = entry[1]
        elif isinstance(entry, bytes):
            metadata.append(entry)
    if header is None:
        return None
    if len(header) > HEADER_BYTES or len(text) > PREVIEW_BYTES:
        raise ValueError('Servidor IMAP excedeu o limite da prévia solicitada.')
    attributes = b' '.join(metadata)
    if len(attributes) > 64 * 1024:
        raise ValueError('Metadados IMAP excedem o limite permitido.')
    message = email.message_from_bytes(header.rstrip(b'\r\n') + b'\r\n\r\n' + text, policy=default)
    result = _dto(message, identifier, False, attributes)
    result['preview'] = _plain_body(message)[:240]
    result['hasAttachments'] = bool(re.search(rb'"(?:attachment|filename|name)"', attributes, re.I))
    result['attachments'] = []
    return result
