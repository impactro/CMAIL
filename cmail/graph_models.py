"""Microsoft Graph response normalization; no credentials or network."""
from __future__ import annotations

import urllib.parse
from .mail import MailError


def _identifier(value: object, label: str) -> str:
    selected = str(value or "").strip()
    if not selected or len(selected) > 1024 or any(ord(char) < 32 for char in selected):
        raise MailError(f"{label} inválido.")
    return urllib.parse.quote(selected, safe="")


def _address(item: object) -> dict[str, str]:
    value = item if isinstance(item, dict) else {}
    address = value.get("emailAddress")
    address = address if isinstance(address, dict) else {}
    return {
        "name": str(address.get("name") or "")[:160],
        "address": str(address.get("address") or "")[:320],
    }


def _recipients(values: object) -> list[dict[str, str]]:
    return [_address(item) for item in values] if isinstance(values, list) else []


def _summary(item: object, *, include_body: bool = False) -> dict[str, object]:
    value = item if isinstance(item, dict) else {}
    sender = _address(value.get("from"))
    body_value = value.get("body")
    body_value = body_value if isinstance(body_value, dict) else {}
    body = str(body_value.get("content") or "")[:200_000] if include_body else ""
    attachments = value.get("attachments")
    return {
        "id": str(value.get("id") or ""),
        "subject": str(value.get("subject") or "")[:500],
        "from": sender,
        "to": _recipients(value.get("toRecipients")),
        "cc": _recipients(value.get("ccRecipients")),
        "receivedAt": str(value.get("receivedDateTime") or value.get("sentDateTime") or ""),
        "isRead": bool(value.get("isRead")),
        "importance": str(value.get("importance") or "normal"),
        "preview": str(value.get("bodyPreview") or "")[:500],
        "body": body,
        "bodyType": "text",
        "hasAttachments": bool(value.get("hasAttachments")),
        "attachments": attachments if isinstance(attachments, list) else [],
    }


def _contact(item: object) -> dict[str, object]:
    value = item if isinstance(item, dict) else {}
    emails = []
    for raw in value.get("emailAddresses") if isinstance(value.get("emailAddresses"), list) else []:
        row = raw if isinstance(raw, dict) else {}
        address = str(row.get("address") or "").strip()
        if address:
            emails.append({"name": str(row.get("name") or "")[:160], "address": address[:320]})
    phones = [
        str(number).strip()[:80]
        for number in value.get("businessPhones") if isinstance(value.get("businessPhones"), list)
        if str(number).strip()
    ]
    mobile = str(value.get("mobilePhone") or "").strip()
    if mobile:
        phones.append(mobile[:80])
    return {
        "id": str(value.get("id") or ""),
        "name": str(value.get("displayName") or "")[:200],
        "givenName": str(value.get("givenName") or "")[:100],
        "surname": str(value.get("surname") or "")[:100],
        "company": str(value.get("companyName") or "")[:200],
        "jobTitle": str(value.get("jobTitle") or "")[:160],
        "emails": emails[:10],
        "phones": list(dict.fromkeys(phones))[:10],
    }


def _event(item: object, *, include_body: bool = False) -> dict[str, object]:
    value = item if isinstance(item, dict) else {}
    start = value.get("start") if isinstance(value.get("start"), dict) else {}
    end = value.get("end") if isinstance(value.get("end"), dict) else {}
    location = value.get("location") if isinstance(value.get("location"), dict) else {}
    result: dict[str, object] = {
        "id": str(value.get("id") or ""),
        "subject": str(value.get("subject") or "(sem assunto)")[:500],
        "start": {"dateTime": str(start.get("dateTime") or ""), "timeZone": str(start.get("timeZone") or "")},
        "end": {"dateTime": str(end.get("dateTime") or ""), "timeZone": str(end.get("timeZone") or "")},
        "location": str(location.get("displayName") or "")[:255],
        "isOrganizer": bool(value.get("isOrganizer")),
        "isOnlineMeeting": bool(value.get("isOnlineMeeting")),
        "onlineMeetingUrl": str(value.get("onlineMeetingUrl") or ""),
        "webLink": str(value.get("webLink") or ""),
        "attendeeCount": len(value.get("attendees")) if isinstance(value.get("attendees"), list) else 0,
    }
    if include_body:
        body = value.get("body") if isinstance(value.get("body"), dict) else {}
        result["body"] = str(body.get("content") or "")[:200_000]
        result["bodyType"] = str(body.get("contentType") or "text")
        result["attendees"] = value.get("attendees") if isinstance(value.get("attendees"), list) else []
    return result
