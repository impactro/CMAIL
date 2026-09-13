"""Casos de uso de leitura, listas e envio confirmado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .auth import MicrosoftAuthService
from .config import Config
from .gmail import GmailProvider, GoogleAuthService
from .graph import MicrosoftGraphProvider
from .mail import Provider, provider
from .store import EMAIL, Store


READ_MAIL = "mail.read"
MANAGE_MAIL = "mail.manage"
SEND_MAIL = "mail.send"
MANAGE_LISTS = "lists.manage"


@dataclass(frozen=True)
class Principal:
    """Identidade afirmada pelo host; nunca contém cookie ou token OAuth."""

    identity_id: str
    email: str
    capabilities: frozenset[str]
    owner_id: str = ""

    @property
    def storage_owner(self) -> str:
        return self.owner_id or self.identity_id

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise PermissionError(f"A identidade não possui a capacidade {capability}.")

    @classmethod
    def local_operator(cls) -> "Principal":
        return cls("", "", frozenset({READ_MAIL, MANAGE_MAIL, SEND_MAIL, MANAGE_LISTS}))


class MailService:
    def __init__(
        self,
        config: Config,
        mail_provider: Provider | None = None,
        *,
        auth: MicrosoftAuthService | GoogleAuthService | None = None,
        graph_factory: Callable[[MicrosoftAuthService, str], Provider] | None = None,
        gmail_factory: Callable[[GoogleAuthService, str], Provider] | None = None,
    ):
        self.config = config
        self.store = Store(config.state_dir)
        self.auth = auth or (
            MicrosoftAuthService(config, self.store) if config.mode == "microsoft"
            else GoogleAuthService(config, self.store) if config.mode == "gmail"
            else None
        )
        self._provider = mail_provider or (
            None if config.mode in {"setup", "microsoft", "gmail"} else provider(config)
        )
        self.graph_factory = graph_factory or (lambda selected_auth, identity_id: MicrosoftGraphProvider(selected_auth, identity_id))
        self.gmail_factory = gmail_factory or (
            lambda selected_auth, identity_id: GmailProvider(selected_auth, identity_id)
        )

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            if self.config.mode == "setup":
                raise PermissionError("Configure a única conta desta instância antes de usar o e-mail.")
            raise PermissionError("O provedor OAuth exige uma identidade autenticada.")
        return self._provider

    def provider_for(self, principal: Principal) -> Provider:
        if self.config.mode not in {"microsoft", "gmail"}:
            return self.provider
        if not principal.identity_id or self.auth is None:
            raise PermissionError("Identidade OAuth autenticada ausente.")
        if self.config.mode == "microsoft":
            return self.graph_factory(self.auth, principal.identity_id)  # type: ignore[arg-type]
        return self.gmail_factory(self.auth, principal.identity_id)  # type: ignore[arg-type]

    def principal_for_owner(
        self,
        owner_id: str,
        capabilities: frozenset[str] | None = None,
    ) -> Principal:
        """Resolve a conta vinculada a um workspace sem aceitar identidade do chamador."""
        selected_capabilities = capabilities or frozenset(
            {READ_MAIL, MANAGE_MAIL, SEND_MAIL, MANAGE_LISTS}
        )
        owner = str(owner_id or "").strip()
        if self.config.mode in {"demo", "imap"}:
            return Principal(
                "local-" + self.config.mode,
                self.config.account,
                selected_capabilities,
                owner,
            )
        provider_name = "microsoft" if self.config.mode == "microsoft" else "google"
        identity = self.store.bound_identity(provider_name, owner)
        identity_id = str((identity or {}).get("id") or "")
        if not identity_id or self.auth is None or not self.auth.is_connected(identity_id):
            raise PermissionError("A conta de e-mail do workspace precisa ser autorizada.")
        return Principal(
            identity_id,
            str((identity or {}).get("email") or ""),
            selected_capabilities,
            owner,
        )

    def invalidate_owner(self, owner_id: str) -> None:
        """Revoga a conta OAuth vinculada ao owner; IMAP não possui vínculo por workspace."""
        if self.config.mode not in {"microsoft", "gmail"}:
            return
        provider_name = "microsoft" if self.config.mode == "microsoft" else "google"
        identity = self.store.bound_identity(provider_name, str(owner_id or "").strip())
        if identity and self.auth is not None:
            self.auth.disconnect(str(identity["id"]))

    def connection_status(self, owner_id: str) -> dict[str, object]:
        """Expõe somente o estado público da conexão e da interface Webmail."""
        owner = str(owner_id or "").strip()
        if not owner or len(owner) > 256:
            raise ValueError("O proprietário do CMAIL é inválido.")
        provider_name = (
            "outlook" if self.config.mode == "microsoft" else
            "gmail" if self.config.mode == "gmail" else self.config.mode
        )
        webmail_enabled = self.store.webmail_enabled(owner)
        if self.config.mode in {"demo", "imap"}:
            return {
                "provider": provider_name,
                "state": "connected",
                "authorized": True,
                "requiresReconnect": False,
                "email": self.config.account,
                "webmailEnabled": webmail_enabled,
                "canAuthorize": False,
            }
        if self.config.mode == "setup":
            return {
                "provider": provider_name,
                "state": "unconfigured",
                "authorized": False,
                "requiresReconnect": False,
                "email": "",
                "webmailEnabled": webmail_enabled,
                "canAuthorize": False,
            }
        provider_key = "microsoft" if self.config.mode == "microsoft" else "google"
        identity = self.store.bound_identity(provider_key, owner)
        identity_id = str((identity or {}).get("id") or "")
        connection = self.store.connection(identity_id) if identity_id else None
        stored_state = str((connection or {}).get("status") or "")
        authorized = bool(identity_id and self.auth and self.auth.is_connected(identity_id))
        if authorized:
            state = "connected"
        elif stored_state == "reauthorize" or (identity_id and stored_state == "authorized"):
            state = "reauthorize"
        elif stored_state == "revoked":
            state = "disabled"
        else:
            state = "disconnected"
        return {
            "provider": provider_name,
            "state": state,
            "authorized": authorized,
            "requiresReconnect": state == "reauthorize",
            "email": str((identity or {}).get("email") or ""),
            "webmailEnabled": webmail_enabled,
            "canAuthorize": True,
        }

    def set_webmail_enabled(self, owner_id: str, enabled: bool) -> dict[str, object]:
        self.store.set_webmail_enabled(owner_id, enabled)
        return self.connection_status(owner_id)

    def disconnect_owner(self, owner_id: str) -> dict[str, object]:
        self.invalidate_owner(owner_id)
        return self.connection_status(owner_id)

    def status(self, live: bool = False, principal: Principal | None = None) -> dict[str, object]:
        owner = principal.storage_owner if principal else ""
        result = {"config": self.config.public(), "state": self.store.status(owner)}
        if live:
            selected = principal or Principal.local_operator()
            selected.require(READ_MAIL)
            result["provider"] = self.provider_for(selected).status()
        return result

    def folders(self, principal: Principal) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        return self.provider_for(principal).folders()

    def messages(self, principal: Principal, folder: str, limit: int = 50) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        return self.provider_for(principal).messages(folder, limit)

    def message(self, principal: Principal, folder: str, identifier: str) -> dict[str, object]:
        principal.require(READ_MAIL)
        return self.provider_for(principal).message(folder, identifier)

    def lists(self, principal: Principal) -> list[dict[str, object]]:
        principal.require(MANAGE_LISTS)
        return self.store.lists(principal.storage_owner)

    def history(self, principal: Principal, limit: int = 50) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        return self.store.history(principal.storage_owner, limit)

    def save_list(self, principal: Principal, name: str, recipients: list[dict[str, str]]) -> dict[str, object]:
        principal.require(MANAGE_LISTS)
        return self.store.save_list(name, recipients, principal.storage_owner)

    def prepare(self, payload: dict[str, object], principal: Principal | None = None) -> dict[str, object]:
        selected = principal or Principal.local_operator()
        selected.require(SEND_MAIL)
        return self.store.prepare(payload, selected.storage_owner)

    def execute(self, identifier: str, token: str, principal: Principal | None = None) -> dict[str, object]:
        selected = principal or Principal.local_operator()
        selected.require(SEND_MAIL)
        payload = self.store.claim(identifier, token, selected.storage_owner)
        recipients = list(payload["recipients"])
        try:
            result = self.provider_for(selected).send(recipients, str(payload["subject"]), str(payload["body"]))
        except Exception as exc:
            uncertain = {"accepted": False, "uncertain": True, "error": str(exc)[:240],
                         "recipientCount": len(recipients)}
            self.store.finish(identifier, "uncertain", uncertain, selected.storage_owner)
            raise
        self.store.finish(
            identifier,
            "sent" if result.get("accepted") else "demo",
            result,
            selected.storage_owner,
        )
        return {"draftId": identifier, **result}

    def set_read(self, principal: Principal, identifier: str, is_read: bool) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "set_read"):
            raise NotImplementedError("O provedor atual não permite alterar leitura.")
        result = selected.set_read(identifier, is_read)  # type: ignore[attr-defined]
        self.store.record_action(
            "mark-read" if is_read else "mark-unread", "completed",
            {"messageId": str(identifier)[:1024]}, principal.storage_owner,
        )
        return result

    def move(self, principal: Principal, identifier: str, destination_id: str) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "move"):
            raise NotImplementedError("O provedor atual não permite mover mensagens.")
        result = selected.move(identifier, destination_id)  # type: ignore[attr-defined]
        self.store.record_action(
            "move", "completed",
            {"messageId": str(identifier)[:1024], "destinationId": str(destination_id)[:1024]},
            principal.storage_owner,
        )
        return result

    def reply(
        self, principal: Principal, identifier: str, comment: str, *,
        reply_all: bool = False, confirmed: bool = False,
    ) -> dict[str, object]:
        principal.require(SEND_MAIL)
        if not confirmed:
            raise ValueError("Responder exige confirmação explícita.")
        if not str(comment).strip():
            raise ValueError("A resposta não pode estar vazia.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "reply"):
            raise NotImplementedError("O provedor atual não permite responder mensagens.")
        result = selected.reply(identifier, comment, reply_all=reply_all)  # type: ignore[attr-defined]
        self.store.record_action(
            "reply-all" if reply_all else "reply", "completed",
            {"messageId": str(identifier)[:1024]}, principal.storage_owner,
        )
        return result

    def forward(
        self, principal: Principal, identifier: str, recipients: list[str], comment: str, *,
        confirmed: bool = False,
    ) -> dict[str, object]:
        principal.require(SEND_MAIL)
        if not confirmed:
            raise ValueError("Encaminhar exige confirmação explícita.")
        clean = list(dict.fromkeys(str(item).strip().casefold() for item in recipients if str(item).strip()))
        if not clean or len(clean) > 100 or any(not EMAIL.fullmatch(item) for item in clean):
            raise ValueError("Destinatários do encaminhamento são inválidos.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "forward"):
            raise NotImplementedError("O provedor atual não permite encaminhar mensagens.")
        result = selected.forward(identifier, clean, comment)  # type: ignore[attr-defined]
        self.store.record_action(
            "forward", "completed",
            {"messageId": str(identifier)[:1024], "recipientCount": len(clean)},
            principal.storage_owner,
        )
        return result

    def attachments(self, principal: Principal, identifier: str) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "attachments"):
            message = selected.message("INBOX", identifier)
            return list(message.get("attachments") or [])
        return selected.attachments(identifier)  # type: ignore[attr-defined]

    def attachment(self, principal: Principal, identifier: str, attachment_id: str) -> dict[str, object]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "attachment"):
            raise NotImplementedError("O provedor atual não permite baixar anexos.")
        return selected.attachment(identifier, attachment_id)  # type: ignore[attr-defined]

    def contacts(self, principal: Principal, query: str = "", limit: int = 25) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "contacts"):
            raise NotImplementedError("O provedor atual não oferece contatos.")
        return selected.contacts(query, limit)  # type: ignore[attr-defined]

    def directory(self, principal: Principal, query: str = "", limit: int = 20) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "directory"):
            raise NotImplementedError("O provedor atual não oferece diretório.")
        return selected.directory(query, limit)  # type: ignore[attr-defined]

    def calendars(self, principal: Principal) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "calendars"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.calendars()  # type: ignore[attr-defined]

    def calendar_view(self, principal: Principal, start: str, end: str, time_zone: str, *, calendar_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "calendar_view"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.calendar_view(start, end, time_zone, calendar_id, limit)  # type: ignore[attr-defined]

    def availability(
        self,
        principal: Principal,
        schedules: list[str],
        start: str,
        end: str,
        time_zone: str,
        interval_minutes: int = 30,
    ) -> dict[str, object]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "availability"):
            raise NotImplementedError("O provedor atual não oferece disponibilidade.")
        return selected.availability(  # type: ignore[attr-defined]
            schedules, start, end, time_zone, interval_minutes,
        )

    def event(self, principal: Principal, identifier: str) -> dict[str, object]:
        principal.require(READ_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.event(identifier)  # type: ignore[attr-defined]

    def create_event(self, principal: Principal, event: dict[str, object], *, calendar_id: str = "", confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A criação do evento exige confirmação explícita.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "create_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.create_event(event, calendar_id=calendar_id)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-create", "completed",
            {"calendarId": str(calendar_id)[:1024]}, principal.storage_owner,
        )
        return result

    def update_event(self, principal: Principal, identifier: str, changes: dict[str, object], *, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A alteração do evento exige confirmação explícita.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "update_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.update_event(identifier, changes)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-update", "completed",
            {"eventId": str(identifier)[:1024], "fields": sorted(str(key) for key in changes)},
            principal.storage_owner,
        )
        return result

    def delete_event(self, principal: Principal, identifier: str, *, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A remoção do evento exige confirmação explícita.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "delete_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.delete_event(identifier)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-delete", "completed",
            {"eventId": str(identifier)[:1024]}, principal.storage_owner,
        )
        return result

    def respond_event(self, principal: Principal, identifier: str, response: str, *, comment: str = "", send_response: bool = True, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A resposta ao evento exige confirmação explícita.")
        selected = self.provider_for(principal)
        if not hasattr(selected, "respond_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.respond_event(identifier, response, comment, send_response)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-respond", "completed",
            {"eventId": str(identifier)[:1024], "response": str(response)[:32]},
            principal.storage_owner,
        )
        return result
