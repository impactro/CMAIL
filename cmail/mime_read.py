"""MIME text and message DTO decoding; no network or authentication."""
from __future__ import annotations

import html
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime


def _decoded(value: object) -> str:
    try:
        return str(make_header(decode_header(str(value or ""))))
    except (LookupError, UnicodeDecodeError):
        return str(value or "")


def _addresses(values: list[str]) -> list[dict[str, str]]:
    return [{"name": name, "address": address} for name, address in getaddresses(values) if address]


def _plain_body(message: Message) -> str:
    plain = ""
    rich = ""
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content())
        except (LookupError, UnicodeDecodeError):
            content = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and not plain:
            plain = content
        elif not rich:
            rich = content
    if plain:
        return plain[:200_000]
    clean = re.sub(r"<[^>]+>", " ", rich)
    return html.unescape(re.sub(r"\s+", " ", clean)).strip()[:200_000]


def _dto(message: Message, identifier: str, include_body: bool, flags: bytes = b"") -> dict[str, object]:
    sender_name, sender_address = parseaddr(_decoded(message.get("From")))
    received = ""
    try:
        parsed = parsedate_to_datetime(str(message.get("Date") or ""))
        received = parsed.isoformat() if parsed else ""
    except (TypeError, ValueError, OverflowError):
        pass
    attachments = []
    for part in message.walk() if message.is_multipart() else []:
        name = part.get_filename()
        if name:
            raw = part.get_payload(decode=True) or b""
            attachments.append({"name": _decoded(name), "contentType": part.get_content_type(), "size": len(raw)})
    body = _plain_body(message) if include_body else ""
    return {
        "id": identifier, "subject": _decoded(message.get("Subject")),
        "from": {"name": sender_name, "address": sender_address},
        "to": _addresses(message.get_all("To", [])), "cc": _addresses(message.get_all("Cc", [])),
        "replyTo": _addresses(message.get_all("Reply-To", [])),
        "internetMessageId": str(message.get("Message-ID") or "")[:1024],
        "receivedAt": received, "isRead": b"\\Seen" in flags, "preview": body[:240] if body else "",
        "body": body, "bodyType": "text", "attachments": attachments,
        "hasAttachments": bool(attachments),
    }
