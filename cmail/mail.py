"""Adaptadores de e-mail sem dependência do CraniaAgent."""

from __future__ import annotations

import email
import html
import imaplib
import re
import smtplib
import ssl
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.policy import default
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Callable, Protocol

from .config import Config
from .inline_images import add_body, normalize as normalize_inline_images
from .store import EMAIL


class MailError(ValueError):
    pass


def _mailbox(value: str) -> str:
    if not value or any(ord(char) < 32 for char in value):
        raise MailError("Pasta de e-mail inválida.")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


class Provider(Protocol):
    def status(self) -> dict[str, object]: ...
    def folders(self) -> list[dict[str, object]]: ...
    def messages(self, folder: str, limit: int = 50) -> list[dict[str, object]]: ...
    def message(self, folder: str, identifier: str) -> dict[str, object]: ...
    def send(self, recipients: list[str], subject: str, body: str, *, body_html: str = "", inline_images=None) -> dict[str, object]: ...


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


class DemoProvider:
    def status(self) -> dict[str, object]:
        return {"provider": "demo", "connected": True, "externalEffects": False}

    def folders(self) -> list[dict[str, object]]:
        return [{"id": "INBOX", "name": "Caixa de entrada"}, {"id": "Sent", "name": "Enviados"}]

    def messages(self, folder: str, limit: int = 50) -> list[dict[str, object]]:
        return []

    def message(self, folder: str, identifier: str) -> dict[str, object]:
        raise MailError("Mensagem não existe no modo demo.")

    def send(self, recipients: list[str], subject: str, body: str, *, body_html: str = "", inline_images=None) -> dict[str, object]:
        normalize_inline_images([] if inline_images is None else inline_images, body_html)
        return {"accepted": False, "demo": True, "recipientCount": len(recipients)}


class ImapSmtpProvider:
    def __init__(self, config: Config, *, imap_ssl_factory: Callable[..., object] = imaplib.IMAP4_SSL,
                 imap_factory: Callable[..., object] = imaplib.IMAP4,
                 smtp_ssl_factory: Callable[..., object] = smtplib.SMTP_SSL,
                 smtp_factory: Callable[..., object] = smtplib.SMTP):
        self.config = config
        self.imap_ssl_factory = imap_ssl_factory
        self.imap_factory = imap_factory
        self.smtp_ssl_factory = smtp_ssl_factory
        self.smtp_factory = smtp_factory

    def _imap(self):
        password = self.config.password()
        client = self.imap_ssl_factory(self.config.imap_host, self.config.imap_port, timeout=20) if self.config.imap_security == "ssl" else self.imap_factory(self.config.imap_host, self.config.imap_port, timeout=20)
        try:
            if self.config.imap_security == "starttls":
                client.starttls(ssl_context=ssl.create_default_context())
            client.login(self.config.username, password)
            return client
        except Exception:
            try: client.logout()
            except Exception: pass
            raise

    def status(self) -> dict[str, object]:
        client = self._imap()
        try:
            return {"provider": "imap", "connected": True, "account": self.config.account, "externalEffects": True}
        finally:
            client.logout()

    def folders(self) -> list[dict[str, object]]:
        client = self._imap()
        try:
            status, rows = client.list()
            if status != "OK":
                raise MailError("Servidor recusou a lista de pastas.")
            result = []
            for raw in rows or []:
                text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                match = re.fullmatch(r'\(([^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(.+)', text)
                if not match or "\\noselect" in match[1].casefold().split():
                    continue
                name = match[2].strip()
                if name.startswith('"') and name.endswith('"'):
                    name = re.sub(r'\\(["\\])', r'\1', name[1:-1])
                roles = {"\\inbox": "inbox", "\\sent": "sent", "\\drafts": "drafts",
                         "\\trash": "trash", "\\junk": "junk", "\\archive": "archive"}
                role = next((roles[flag.casefold()] for flag in match[1].split()
                             if flag.casefold() in roles), "inbox" if name.casefold() == "inbox" else "")
                if name:
                    result.append({"id": name, "name": name, "wellKnownName": role})
            return result
        finally:
            client.logout()

    def messages(self, folder: str, limit: int = 50) -> list[dict[str, object]]:
        client = self._imap()
        try:
            if client.select(_mailbox(folder), readonly=True)[0] != "OK":
                raise MailError("Pasta de e-mail inválida.")
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise MailError("Servidor recusou a listagem de mensagens.")
            identifiers = (data[0] or b"").split()[-max(1, min(int(limit), 100)):]
            result = []
            for raw_id in reversed(identifiers):
                identifier = raw_id.decode("ascii", errors="ignore")
                status, fetched = client.uid("fetch", identifier, "(RFC822 FLAGS)")
                if status != "OK" or not fetched:
                    continue
                entry = next((item for item in fetched if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
                if entry:
                    result.append(_dto(email.message_from_bytes(entry[1], policy=default), identifier, False, entry[0]))
            return result
        finally:
            client.logout()

    def message(self, folder: str, identifier: str) -> dict[str, object]:
        if not str(identifier).isdigit():
            raise MailError("Identificador de mensagem inválido.")
        client = self._imap()
        try:
            if client.select(_mailbox(folder), readonly=True)[0] != "OK":
                raise MailError("Pasta de e-mail inválida.")
            status, fetched = client.uid("fetch", identifier, "(RFC822 FLAGS)")
            entry = next((item for item in fetched or [] if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
            if status != "OK" or not entry:
                raise MailError("Mensagem não encontrada.")
            return _dto(email.message_from_bytes(entry[1], policy=default), identifier, True, entry[0])
        finally:
            client.logout()

    def message_actions(self) -> dict[str, bool]:
        client = self._imap()
        try:
            capabilities = {item.decode("ascii") if isinstance(item, bytes) else str(item)
                            for item in client.capabilities}
            movable = bool({"MOVE", "UIDPLUS"} & {item.upper() for item in capabilities})
            return {"setRead": True, "move": movable}
        finally:
            client.logout()

    def reply(self, identifier: str, comment: str, *, reply_all: bool = False, folder: str = "INBOX") -> dict[str, object]:
        original = self.message(folder, identifier)
        sender = original.get("replyTo") or [original["from"]]
        recipients = [item["address"] for item in sender]
        if reply_all:
            recipients.extend(item["address"] for item in original["to"] + original["cc"])
        own = {self.config.account.casefold(), self.config.username.casefold()}
        recipients = list(dict.fromkeys(address.strip().casefold() for address in recipients
                                        if not reply_all or address.strip().casefold() not in own))
        if not recipients or any(not EMAIL.fullmatch(address) for address in recipients):
            raise MailError("A mensagem não possui destinatário de resposta válido.")
        subject = str(original["subject"])
        if not subject.casefold().startswith("re:"):
            subject = "Re: " + subject
        result = self.send(recipients, subject, comment, reply_message_id=str(original.get("internetMessageId") or ""))
        return {**result, "action": "replyAll" if reply_all else "reply"}

    def forward(self, identifier: str, recipients: list[str], comment: str, *, folder: str = "INBOX") -> dict[str, object]:
        original = self.message(folder, identifier)
        sender = original["from"]
        body = (f"{comment}\n\n---------- Mensagem encaminhada ----------\n"
                f"De: {sender['name']} <{sender['address']}>\nAssunto: {original['subject']}\n\n{original['body']}")
        result = self.send(recipients, "Enc: " + str(original["subject"]), body)
        return {**result, "action": "forward"}

    @staticmethod
    def _select_message(client, folder: str, identifier: str) -> None:
        if not str(identifier).isascii() or not str(identifier).isdigit():
            raise MailError("Identificador de mensagem inválido.")
        if client.select(_mailbox(folder), readonly=False)[0] != "OK":
            raise MailError("Pasta de e-mail inválida.")

    def set_read(self, identifier: str, is_read: bool, *, folder: str = "INBOX") -> dict[str, object]:
        client = self._imap()
        try:
            self._select_message(client, folder, identifier)
            operation = "+FLAGS.SILENT" if is_read else "-FLAGS.SILENT"
            if client.uid("STORE", identifier, operation, "(\\Seen)")[0] != "OK":
                raise MailError("O servidor recusou a alteração de leitura.")
            return {"id": identifier, "isRead": is_read}
        finally:
            client.logout()

    def move(self, identifier: str, destination_id: str, *, folder: str = "INBOX") -> dict[str, object]:
        if not destination_id or any(ord(char) < 32 for char in destination_id):
            raise MailError("Pasta de destino inválida.")
        if destination_id == folder:
            raise MailError("Escolha uma pasta diferente da atual.")
        client = self._imap()
        try:
            self._select_message(client, folder, identifier)
            capabilities = {item.decode("ascii").upper() if isinstance(item, bytes) else str(item).upper()
                            for item in client.capabilities}
            # Quote mailbox names: names may contain spaces, quotes or backslashes.
            destination = _mailbox(destination_id)
            if "MOVE" in capabilities:
                if client.uid("MOVE", identifier, destination)[0] != "OK":
                    raise MailError("O servidor recusou a movimentação.")
            elif "UIDPLUS" in capabilities:
                if client.uid("COPY", identifier, destination)[0] != "OK":
                    raise MailError("O servidor recusou a cópia para o destino.")
                if client.uid("STORE", identifier, "+FLAGS.SILENT", "(\\Deleted)")[0] != "OK":
                    raise MailError("Mensagem copiada; remoção da origem não confirmada. Atualize antes de tentar novamente.")
                # Never EXPUNGE the whole mailbox: other messages may be marked deleted.
                if client.uid("EXPUNGE", identifier)[0] != "OK":
                    raise MailError("Mensagem copiada; remoção da origem incerta. Atualize antes de tentar novamente.")
            else:
                raise MailError("Este servidor não oferece movimentação segura por UID.")
            return {"id": identifier, "moved": True}
        finally:
            client.logout()

    def send(self, recipients: list[str], subject: str, body: str, *, body_html: str = "", inline_images=None, reply_message_id: str = "") -> dict[str, object]:
        message = EmailMessage()
        message["From"] = self.config.account
        if len(recipients) == 1:
            message["To"] = recipients[0]
        else:
            # send_message usa Bcc no envelope SMTP e remove esse cabeçalho dos
            # bytes transmitidos, evitando expor a lista entre destinatários.
            message["To"] = self.config.account
            message["Bcc"] = ", ".join(recipients)
        message["Subject"] = subject[:500]
        if reply_message_id and re.fullmatch(r"<[^<>\s]+>", reply_message_id):
            message["In-Reply-To"] = reply_message_id
            message["References"] = reply_message_id
        add_body(message, body, body_html, inline_images)
        password = self.config.password()
        client = self.smtp_ssl_factory(self.config.smtp_host, self.config.smtp_port, timeout=30) if self.config.smtp_security == "ssl" else self.smtp_factory(self.config.smtp_host, self.config.smtp_port, timeout=30)
        try:
            if self.config.smtp_security == "starttls":
                client.starttls(context=ssl.create_default_context())
            client.login(self.config.username, password)
            refused = client.send_message(message)
            if refused:
                raise MailError("Servidor recusou um ou mais destinatários.")
            return {"accepted": True, "recipientCount": len(recipients)}
        finally:
            try: client.quit()
            except Exception: pass


def provider(config: Config) -> Provider:
    if config.mode == "demo":
        return DemoProvider()
    if config.mode == "imap":
        return ImapSmtpProvider(config)
    raise MailError("O provedor OAuth exige uma identidade autenticada.")
