"""Adaptador Microsoft Graph do webmail CMAIL."""

from __future__ import annotations

import json
import base64
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .auth import MicrosoftAuthService
from .mail import MailError, Provider


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
GraphRequester = Callable[[str, str, str, dict[str, object] | None, dict[str, str] | None], tuple[int, object]]


def graph_request(
    method: str,
    path: str,
    access_token: str,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    if not path.startswith("/me/"):
        raise MailError("Rota Microsoft Graph não permitida.")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    selected_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if body is not None:
        selected_headers["Content-Type"] = "application/json; charset=utf-8"
    selected_headers.update(headers or {})
    request = urllib.request.Request(
        GRAPH_ROOT + path, data=body, headers=selected_headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, raw = int(response.status), response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        status, raw = int(exc.code), exc.read(256 * 1024)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MailError("O Microsoft Graph não respondeu.") from exc
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {}


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


class MicrosoftGraphProvider(Provider):
    """Opera somente a caixa da identidade autenticada recebida."""

    def __init__(
        self,
        auth: MicrosoftAuthService,
        identity_id: str,
        *,
        requester: GraphRequester = graph_request,
    ) -> None:
        self.auth = auth
        self.identity_id = identity_id
        self.requester = requester

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> object:
        status, result = self.requester(
            method, path, self.auth.access_token(self.identity_id), payload, headers
        )
        if status not in expected:
            raise MailError(f"O Microsoft Graph recusou a operação ({status}).")
        return result

    def status(self) -> dict[str, object]:
        identity = self.auth.store.identity(self.identity_id) or {}
        connection = self.auth.store.connection(self.identity_id) or {}
        return {
            "provider": "microsoft",
            "connected": connection.get("status") == "authorized",
            "account": identity.get("email", ""),
            "externalEffects": True,
        }

    def folders(self) -> list[dict[str, object]]:
        query = urllib.parse.urlencode({
            "$top": "100",
            "$select": "id,displayName,totalItemCount,unreadItemCount",
            "includeHiddenFolders": "false",
        })
        result = self._call("GET", f"/me/mailFolders?{query}")
        values = result.get("value") if isinstance(result, dict) else []
        try:
            inbox = self._call("GET", "/me/mailFolders/inbox?%24select=id")
        except MailError:
            inbox = {}
        inbox_id = str(inbox.get("id") or "") if isinstance(inbox, dict) else ""
        return [
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("displayName") or "")[:200],
                "wellKnownName": (
                    "inbox" if inbox_id and str(item.get("id") or "") == inbox_id else ""
                ),
                "total": int(item.get("totalItemCount") or 0),
                "unread": int(item.get("unreadItemCount") or 0),
            }
            for item in values or [] if isinstance(item, dict) and item.get("id")
        ]

    def messages(self, folder: str, limit: int = 50) -> list[dict[str, object]]:
        selected = _identifier(folder, "Pasta")
        query = urllib.parse.urlencode({
            "$top": str(max(1, min(int(limit), 100))),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,importance,bodyPreview,hasAttachments",
        })
        result = self._call("GET", f"/me/mailFolders/{selected}/messages?{query}")
        values = result.get("value") if isinstance(result, dict) else []
        return [_summary(item) for item in values or []]

    def message(self, folder: str, identifier: str) -> dict[str, object]:
        del folder
        selected = _identifier(identifier, "Mensagem")
        query = urllib.parse.urlencode({
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,isRead,importance,body,bodyPreview,hasAttachments"
        })
        result = self._call(
            "GET", f"/me/messages/{selected}?{query}",
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        return _summary(result, include_body=True)

    def send(self, recipients: list[str], subject: str, body: str) -> dict[str, object]:
        message = {
            "subject": subject[:500],
            "body": {"contentType": "Text", "content": body[:200_000]},
            "toRecipients": [
                {"emailAddress": {"address": address}} for address in recipients
            ],
        }
        self._call("POST", "/me/sendMail", {"message": message, "saveToSentItems": True}, expected=(202,))
        return {"accepted": True, "recipientCount": len(recipients)}

    def set_read(self, identifier: str, is_read: bool) -> dict[str, object]:
        selected = _identifier(identifier, "Mensagem")
        result = self._call("PATCH", f"/me/messages/{selected}", {"isRead": bool(is_read)})
        return {"id": str(result.get("id") or identifier), "isRead": bool(result.get("isRead", is_read))} if isinstance(result, dict) else {"id": identifier, "isRead": is_read}

    def move(self, identifier: str, destination_id: str) -> dict[str, object]:
        selected = _identifier(identifier, "Mensagem")
        destination = _identifier(destination_id, "Pasta de destino")
        result = self._call("POST", f"/me/messages/{selected}/move", {"destinationId": urllib.parse.unquote(destination)})
        return {"id": str(result.get("id") or ""), "moved": True} if isinstance(result, dict) else {"moved": True}

    def reply(self, identifier: str, comment: str, *, reply_all: bool = False) -> dict[str, object]:
        selected = _identifier(identifier, "Mensagem")
        action = "replyAll" if reply_all else "reply"
        self._call("POST", f"/me/messages/{selected}/{action}", {"comment": str(comment)[:200_000]}, expected=(202,))
        return {"accepted": True, "action": action}

    def forward(self, identifier: str, recipients: list[str], comment: str) -> dict[str, object]:
        selected = _identifier(identifier, "Mensagem")
        payload = {
            "comment": str(comment)[:200_000],
            "toRecipients": [{"emailAddress": {"address": address}} for address in recipients],
        }
        self._call("POST", f"/me/messages/{selected}/forward", payload, expected=(202,))
        return {"accepted": True, "action": "forward", "recipientCount": len(recipients)}

    def attachments(self, identifier: str) -> list[dict[str, object]]:
        selected = _identifier(identifier, "Mensagem")
        query = urllib.parse.urlencode({"$top": "100", "$select": "id,name,contentType,size,isInline,contentId"})
        result = self._call("GET", f"/me/messages/{selected}/attachments?{query}")
        values = result.get("value") if isinstance(result, dict) else []
        return [
            {
                "id": str(item.get("id") or ""), "name": str(item.get("name") or "")[:255],
                "contentType": str(item.get("contentType") or "application/octet-stream")[:160],
                "size": int(item.get("size") or 0), "isInline": bool(item.get("isInline")),
                "contentId": str(item.get("contentId") or "")[:512],
            }
            for item in values or [] if isinstance(item, dict) and item.get("id")
        ]

    def attachment(self, identifier: str, attachment_id: str) -> dict[str, object]:
        selected = _identifier(identifier, "Mensagem")
        attachment = _identifier(attachment_id, "Anexo")
        result = self._call("GET", f"/me/messages/{selected}/attachments/{attachment}")
        value = result if isinstance(result, dict) else {}
        encoded = str(value.get("contentBytes") or "")
        try:
            size = len(base64.b64decode(encoded, validate=True)) if encoded else 0
        except ValueError as exc:
            raise MailError("O Microsoft Graph devolveu um anexo inválido.") from exc
        if size > 25 * 1024 * 1024:
            raise MailError("O anexo excede o limite de 25 MiB.")
        return {
            "id": str(value.get("id") or attachment_id), "name": str(value.get("name") or "anexo")[:255],
            "contentType": str(value.get("contentType") or "application/octet-stream")[:160],
            "size": size, "contentBase64": encoded,
        }

    def contacts(self, query: str = "", limit: int = 25) -> list[dict[str, object]]:
        selected_query = " ".join(str(query or "").split())[:100]
        selected_limit = max(1, min(int(limit), 100))
        params = urllib.parse.urlencode({
            "$select": "id,displayName,givenName,surname,companyName,jobTitle,emailAddresses,businessPhones,mobilePhone",
            "$top": str(100 if selected_query else selected_limit), "$orderby": "displayName",
        })
        result = self._call("GET", f"/me/contacts?{params}")
        values = result.get("value") if isinstance(result, dict) else []
        contacts = [_contact(item) for item in values or []]
        if selected_query:
            needle = selected_query.casefold()
            contacts = [item for item in contacts if needle in json.dumps(item, ensure_ascii=False).casefold()]
        return contacts[:selected_limit]

    def directory(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        selected = " ".join(str(query or "").split())
        if selected and len(selected) < 2 or len(selected) > 100:
            raise MailError("A busca no diretório exige zero ou ao menos 2 caracteres.")
        params: dict[str, str] = {
            "$select": "id,displayName,mail,userPrincipalName,department,jobTitle",
            "$top": str(max(1, min(int(limit), 50))),
        }
        headers = None
        if selected:
            clean = selected.replace('"', "").replace("\\", "")
            params.update({"$search": f'"displayName:{clean}" OR "mail:{clean}"', "$count": "true"})
            headers = {"ConsistencyLevel": "eventual"}
        else:
            params["$orderby"] = "displayName"
        result = self._call("GET", "/me/people?" + urllib.parse.urlencode(params), headers=headers)
        values = result.get("value") if isinstance(result, dict) else []
        return [
            {
                "id": str(item.get("id") or ""), "name": str(item.get("displayName") or "")[:200],
                "email": str(item.get("mail") or item.get("userPrincipalName") or "")[:320],
                "department": str(item.get("department") or "")[:160], "jobTitle": str(item.get("jobTitle") or "")[:160],
            }
            for item in values or [] if isinstance(item, dict)
        ]

    def calendars(self) -> list[dict[str, object]]:
        params = urllib.parse.urlencode({"$top": "50", "$select": "id,name,color,isDefaultCalendar,canEdit,owner"})
        result = self._call("GET", f"/me/calendars?{params}")
        values = result.get("value") if isinstance(result, dict) else []
        return [dict(item) for item in values or [] if isinstance(item, dict)]

    def calendar_view(self, start: str, end: str, time_zone: str, calendar_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        if not start or not end or not time_zone:
            raise MailError("Início, fim e fuso são obrigatórios.")
        prefix = "/me/calendar/calendarView" if not calendar_id else f"/me/calendars/{_identifier(calendar_id, 'Calendário')}/calendarView"
        params = urllib.parse.urlencode({
            "startDateTime": start, "endDateTime": end, "$top": str(max(1, min(int(limit), 200))),
            "$orderby": "start/dateTime",
        })
        result = self._call("GET", f"{prefix}?{params}", headers={"Prefer": f'outlook.timezone="{time_zone[:128]}"'})
        values = result.get("value") if isinstance(result, dict) else []
        return [_event(item) for item in values or []]

    def availability(
        self,
        schedules: list[str],
        start: str,
        end: str,
        time_zone: str,
        interval_minutes: int = 30,
    ) -> dict[str, object]:
        selected = list(dict.fromkeys(
            str(item).strip().casefold() for item in schedules if str(item).strip()
        ))
        interval = int(interval_minutes)
        if not selected or len(selected) > 50:
            raise MailError("Informe de 1 a 50 agendas.")
        if not start or not end or not time_zone:
            raise MailError("Início, fim e fuso são obrigatórios.")
        if interval < 5 or interval > 1440:
            raise MailError("Intervalo de disponibilidade inválido.")
        result = self._call("POST", "/me/calendar/getSchedule", {
            "schedules": selected,
            "startTime": {"dateTime": str(start), "timeZone": str(time_zone)[:128]},
            "endTime": {"dateTime": str(end), "timeZone": str(time_zone)[:128]},
            "availabilityViewInterval": interval,
        })
        values = result.get("value") if isinstance(result, dict) else []
        rows = []
        for raw in values or []:
            item = raw if isinstance(raw, dict) else {}
            schedule_items = item.get("scheduleItems")
            rows.append({
                "schedule": str(item.get("scheduleId") or "")[:320],
                "availabilityView": str(item.get("availabilityView") or ""),
                "items": [
                    {
                        "status": str(entry.get("status") or ""),
                        "start": entry.get("start") if isinstance(entry.get("start"), dict) else {},
                        "end": entry.get("end") if isinstance(entry.get("end"), dict) else {},
                    }
                    for entry in schedule_items or [] if isinstance(entry, dict)
                ] if isinstance(schedule_items, list) else [],
            })
        return {
            "schedules": rows,
            "count": len(rows),
            "timeZone": str(time_zone)[:128],
            "intervalMinutes": interval,
        }

    def event(self, identifier: str) -> dict[str, object]:
        result = self._call("GET", f"/me/events/{_identifier(identifier, 'Evento')}", headers={"Prefer": 'outlook.body-content-type="text"'})
        return _event(result, include_body=True)

    def create_event(self, event: dict[str, object], *, calendar_id: str = "") -> dict[str, object]:
        prefix = "/me/events" if not calendar_id else f"/me/calendars/{_identifier(calendar_id, 'Calendário')}/events"
        return {"created": True, "event": _event(self._call("POST", prefix, event, expected=(201,)))}

    def update_event(self, identifier: str, changes: dict[str, object]) -> dict[str, object]:
        result = self._call("PATCH", f"/me/events/{_identifier(identifier, 'Evento')}", changes)
        return {"updated": True, "event": _event(result)}

    def delete_event(self, identifier: str) -> dict[str, object]:
        self._call("DELETE", f"/me/events/{_identifier(identifier, 'Evento')}", expected=(204,))
        return {"deleted": True}

    def respond_event(self, identifier: str, response: str, comment: str = "", send_response: bool = True) -> dict[str, object]:
        action = {"accept": "accept", "tentative": "tentativelyAccept", "decline": "decline"}.get(str(response).casefold())
        if not action:
            raise MailError("Resposta deve ser accept, tentative ou decline.")
        self._call("POST", f"/me/events/{_identifier(identifier, 'Evento')}/{action}", {"comment": str(comment)[:2000], "sendResponse": bool(send_response)}, expected=(202,))
        return {"responded": True, "response": str(response).casefold()}
