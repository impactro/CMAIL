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

    def status(self, live: bool = False, principal: Principal | None = None) -> dict[str, object]:
        owner = principal.identity_id if principal else ""
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
        return self.store.lists(principal.identity_id)

    def save_list(self, principal: Principal, name: str, recipients: list[dict[str, str]]) -> dict[str, object]:
        principal.require(MANAGE_LISTS)
        return self.store.save_list(name, recipients, principal.identity_id)

    def prepare(self, payload: dict[str, object], principal: Principal | None = None) -> dict[str, object]:
        selected = principal or Principal.local_operator()
        selected.require(SEND_MAIL)
        return self.store.prepare(payload, selected.identity_id)

    def execute(self, identifier: str, token: str, principal: Principal | None = None) -> dict[str, object]:
        selected = principal or Principal.local_operator()
        selected.require(SEND_MAIL)
        payload = self.store.claim(identifier, token, selected.identity_id)
        recipients = list(payload["recipients"])
        try:
            result = self.provider_for(selected).send(recipients, str(payload["subject"]), str(payload["body"]))
        except Exception as exc:
            uncertain = {"accepted": False, "uncertain": True, "error": str(exc)[:240],
                         "recipientCount": len(recipients)}
            self.store.finish(identifier, "uncertain", uncertain, selected.identity_id)
            raise
        self.store.finish(identifier, "sent" if result.get("accepted") else "demo", result, selected.identity_id)
        return {"draftId": identifier, **result}

    def set_read(self, principal: Principal, identifier: str, is_read: bool) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "set_read"):
            raise NotImplementedError("O provedor atual não permite alterar leitura.")
        return selected.set_read(identifier, is_read)  # type: ignore[attr-defined]

    def move(self, principal: Principal, identifier: str, destination_id: str) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        selected = self.provider_for(principal)
        if not hasattr(selected, "move"):
            raise NotImplementedError("O provedor atual não permite mover mensagens.")
        return selected.move(identifier, destination_id)  # type: ignore[attr-defined]

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
        return selected.reply(identifier, comment, reply_all=reply_all)  # type: ignore[attr-defined]

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
        return selected.forward(identifier, clean, comment)  # type: ignore[attr-defined]
