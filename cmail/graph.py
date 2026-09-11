"""Adaptador Microsoft Graph do webmail CMAIL."""

from __future__ import annotations

import json
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
            "$select": "id,displayName,totalItemCount,unreadItemCount,wellKnownName",
            "includeHiddenFolders": "false",
        })
        result = self._call("GET", f"/me/mailFolders?{query}")
        values = result.get("value") if isinstance(result, dict) else []
        return [
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("displayName") or "")[:200],
                "wellKnownName": str(item.get("wellKnownName") or ""),
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
