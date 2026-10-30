"""Gmail mailbox API. OAuth names are re-exported for existing integrations."""
from __future__ import annotations

import base64
import html
import json
import urllib.parse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

from .google_auth import (
    GMAIL_API, GMAIL_SCOPES, GOOGLE_AUTH, GOOGLE_ISSUER, GOOGLE_REVOKE,
    GOOGLE_TOKEN, GOOGLE_USERINFO, GoogleAuthService, HttpRequester,
    ProtectedJsonFile, _request,
)


class GmailProvider:
    def __init__(self, auth: GoogleAuthService, identity_id: str):
        self.auth = auth
        self.identity_id = identity_id

    def _call(
        self, method: str, path: str, payload: dict[str, object] | None = None,
        *, expected: tuple[int, ...] = (200,),
    ) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        status, value = self.auth.requester(
            method, GMAIL_API + path,
            {"Authorization": f"Bearer {self.auth.access_token(self.identity_id)}", "Content-Type": "application/json"},
            body,
        )
        if status not in expected or not isinstance(value, dict):
            raise ValueError("A API Gmail recusou a operação.")
        return value

    def status(self) -> dict[str, object]:
        profile = self._call("GET", "/profile")
        return {"provider": "gmail", "connected": True, "account": str(profile.get("emailAddress") or ""), "externalEffects": True}

    def message_actions(self) -> dict[str, bool]:
        getter = getattr(self.auth, "granted_scopes", None)
        scopes = getter(self.identity_id) if callable(getter) else set()
        return {"trash": True, "deletePermanently": isinstance(scopes, (set, frozenset)) and "https://mail.google.com/" in scopes}

    def trash(self, identifier: str, destination_id: str, *, folder: str = "INBOX") -> dict[str, object]:
        if destination_id != "TRASH":
            raise ValueError("A pasta de destino não é a lixeira Gmail.")
        selected = urllib.parse.quote(str(identifier or ""), safe="")
        if not selected:
            raise ValueError("Mensagem Gmail inválida.")
        self._call("POST", f"/messages/{selected}/trash")
        return {"id": identifier, "trashed": True}

    def delete_permanently(self, identifier: str, *, folder: str = "INBOX") -> dict[str, object]:
        if not self.message_actions()["deletePermanently"]:
            raise PermissionError("A autorização Gmail atual não permite exclusão definitiva; exige https://mail.google.com/.")
        selected = urllib.parse.quote(str(identifier or ""), safe="")
        if not selected or folder != "TRASH":
            raise ValueError("A exclusão definitiva exige uma mensagem na lixeira.")
        message = self._call("GET", f"/messages/{selected}?format=minimal")
        if "TRASH" not in message.get("labelIds", []):
            raise ValueError("A mensagem não está na lixeira.")
        self._call("DELETE", f"/messages/{selected}", expected=(200, 204))
        return {"id": identifier, "deletedPermanently": True}

    def folders(self) -> list[dict[str, object]]:
        value = self._call("GET", "/labels")
        return [
            {"id": str(item.get("id") or ""), "name": str(item.get("name") or ""), "unread": int(item.get("messagesUnread") or 0),
             "canMoveTo": item.get("id") not in {"SENT", "DRAFT", "DRAFTS"}}
            for item in value.get("labels", []) if isinstance(item, dict)
        ]

    def messages(self, folder: str, limit: int = 50) -> list[dict[str, object]]:
        selected_limit = max(1, min(int(limit), 100))
        params = urllib.parse.urlencode({'maxResults': selected_limit, 'labelIds': str(folder or 'INBOX')})
        value = self._call('GET', '/messages?' + params)
        references = [item for item in value.get('messages', [])
                      if isinstance(item, dict) and item.get('id')][:selected_limit]
        metadata = urllib.parse.urlencode({'format': 'metadata', 'metadataHeaders':
            ['From', 'To', 'Cc', 'Reply-To', 'Subject', 'Date', 'Message-ID']}, doseq=True)
        return [self._dto(self._call('GET', '/messages/' + urllib.parse.quote(str(item['id']), safe='')
                                    + '?' + metadata), False) for item in references]

    def message(self, folder: str, identifier: str) -> dict[str, object]:
        del folder
        selected = urllib.parse.quote(str(identifier or ""), safe="")
        if not selected:
            raise ValueError("Mensagem Gmail inválida.")
        return self._dto(self._call("GET", f"/messages/{selected}?format=full"), True)

    def send(self, recipients: list[str], subject: str, body: str, *, body_html: str = "", inline_images=None) -> dict[str, object]:
        from .inline_images import add_body
        message = EmailMessage()
        message["To"] = ", ".join(recipients)
        message["Subject"] = str(subject)[:500]
        add_body(message, str(body)[:200_000], body_html, inline_images)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
        result = self._call("POST", "/messages/send", {"raw": raw})
        return {"accepted": True, "id": str(result.get("id") or ""), "recipientCount": len(recipients)}

    def set_read(self, identifier: str, is_read: bool) -> dict[str, object]:
        selected = urllib.parse.quote(str(identifier or ""), safe="")
        payload = {"addLabelIds": [] if is_read else ["UNREAD"], "removeLabelIds": ["UNREAD"] if is_read else []}
        self._call("POST", f"/messages/{selected}/modify", payload)
        return {"id": identifier, "isRead": bool(is_read)}

    def move(self, identifier: str, destination_id: str, *, folder: str = "INBOX") -> dict[str, object]:
        selected = urllib.parse.quote(str(identifier or ""), safe="")
        destination = str(destination_id or "").strip()
        if not selected or not destination:
            raise ValueError("Mensagem e destino Gmail são obrigatórios.")
        removable = folder in {"INBOX", "TRASH", "SPAM"} or folder.startswith("Label_")
        remove = [folder] if removable and folder != destination else []
        payload = {"addLabelIds": [destination], "removeLabelIds": remove}
        if destination != "TRASH":
            payload["removeLabelIds"].append("TRASH")
        payload["removeLabelIds"] = list(dict.fromkeys(payload["removeLabelIds"]))
        self._call("POST", f"/messages/{selected}/modify", payload)
        return {"id": identifier, "moved": True}

    def reply(self, identifier: str, comment: str, *, reply_all: bool = False, body_html: str = "", inline_images=None, reply_recipients=None) -> dict[str, object]:
        original = self.message("", identifier)
        recipients = [str(original.get("from", {}).get("address") or "")]
        if reply_all:
            recipients.extend(str(item.get("address") or "") for item in original.get("to", []))
        recipients = list(dict.fromkeys(item for item in recipients if item))
        if reply_recipients is not None:
            recipients = list(reply_recipients)
        options = {'body_html': body_html, 'inline_images': inline_images} if body_html else {}
        result = self.send(recipients, "Re: " + str(original.get("subject") or ""), comment, **options)
        return {**result, "action": "replyAll" if reply_all else "reply"}

    def forward(self, identifier: str, recipients: list[str], comment: str, *, body_html: str = "", inline_images=None) -> dict[str, object]:
        original = self.message("", identifier)
        body = f"{comment}\n\n---------- Mensagem encaminhada ----------\n{original.get('body') or original.get('preview') or ''}"
        options = {}
        if body_html:
            options = {'body_html': body_html + '<hr><blockquote>' + html.escape(body[len(comment):]).replace('\n', '<br>') + '</blockquote>', 'inline_images': inline_images}
        result = self.send(recipients, "Enc: " + str(original.get("subject") or ""), body, **options)
        return {**result, "action": "forward"}

    @staticmethod
    def _dto(value: dict[str, object], include_body: bool) -> dict[str, object]:
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        headers = {
            str(item.get("name") or "").casefold(): str(item.get("value") or "")
            for item in payload.get("headers", []) if isinstance(item, dict)
        }
        sender_name, sender_address = parseaddr(headers.get("from", ""))
        labels = {str(item) for item in value.get("labelIds", [])}
        try:
            received = datetime.fromtimestamp(int(str(value.get("internalDate") or "0")) / 1000, timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            received = ""

        def addresses(name: str) -> list[dict[str, str]]:
            return [{"name": person, "address": address} for person, address in getaddresses([headers.get(name, "")]) if address]

        def content(part: object) -> str:
            if not isinstance(part, dict):
                return ""
            mime = str(part.get("mimeType") or "")
            body = part.get("body") if isinstance(part.get("body"), dict) else {}
            encoded = str(body.get("data") or "")
            if encoded and mime in {"text/plain", "text/html"}:
                try:
                    decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8", errors="replace")
                    if mime == "text/html":
                        import re
                        decoded = html.unescape(re.sub(r"<[^>]+>", " ", decoded))
                    return decoded[:200_000]
                except (ValueError, TypeError):
                    return ""
            for child in part.get("parts", []) if isinstance(part.get("parts"), list) else []:
                selected = content(child)
                if selected:
                    return selected
            return ""

        body_text = content(payload) if include_body else ""
        attachments = [
            {"name": str(item.get("filename") or ""), "contentType": str(item.get("mimeType") or ""), "size": int((item.get("body") or {}).get("size") or 0)}
            for item in payload.get("parts", []) if isinstance(item, dict) and item.get("filename")
        ]
        return {
            "id": str(value.get("id") or ""), "subject": headers.get("subject", ""),
            "from": {"name": sender_name, "address": sender_address},
            "to": addresses("to"), "cc": addresses("cc"), "receivedAt": received,
            "isRead": "UNREAD" not in labels, "preview": str(value.get("snippet") or ""),
            "body": body_text, "bodyType": "text", "attachments": attachments,
            "hasAttachments": bool(attachments),
        }
