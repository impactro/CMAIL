"""API Python estável para runtimes agentes incorporarem o CMAIL."""

from __future__ import annotations

from .config import Config
from .service import MailService, Principal


class CmailApi:
    """Fachada sem cookies web, tokens OAuth ou dependência de ``ca.*``."""

    def __init__(self, service: MailService) -> None:
        self.service = service

    @staticmethod
    def describe() -> dict[str, object]:
        """Contrato estruturado da API, separado do descritor rígido CM 2."""
        return {
            "schemaVersion": "1.0",
            "factory": "cmail:create_api",
            "principalType": "cmail:Principal",
            "operations": {
                "status": {"capability": "mail.read", "effect": "read-local"},
                "folders": {"capability": "mail.read", "effect": "network-read"},
                "messages": {"capability": "mail.read", "effect": "network-read"},
                "message": {"capability": "mail.read", "effect": "network-read"},
                "set-read": {"capability": "mail.manage", "effect": "external-write"},
                "move": {"capability": "mail.manage", "effect": "external-write"},
                "lists": {"capability": "lists.manage", "effect": "read-local"},
                "save-list": {"capability": "lists.manage", "effect": "write-local"},
                "prepare-send": {"capability": "mail.send", "effect": "write-local"},
                "execute-send": {"capability": "mail.send", "effect": "external-write-confirmed"},
                "reply": {"capability": "mail.send", "effect": "external-write-confirmed"},
                "forward": {"capability": "mail.send", "effect": "external-write-confirmed"},
            },
        }

    @classmethod
    def from_config(cls, config: Config) -> "CmailApi":
        return cls(MailService(config))

    def status(self, principal: Principal, *, live: bool = False) -> dict[str, object]:
        return self.service.status(live, principal)

    def folders(self, principal: Principal) -> list[dict[str, object]]:
        return self.service.folders(principal)

    def messages(self, principal: Principal, folder: str, limit: int = 50) -> list[dict[str, object]]:
        return self.service.messages(principal, folder, limit)

    def message(self, principal: Principal, folder: str, identifier: str) -> dict[str, object]:
        return self.service.message(principal, folder, identifier)

    def set_read(self, principal: Principal, identifier: str, is_read: bool) -> dict[str, object]:
        return self.service.set_read(principal, identifier, is_read)

    def move(self, principal: Principal, identifier: str, destination_id: str) -> dict[str, object]:
        return self.service.move(principal, identifier, destination_id)

    def lists(self, principal: Principal) -> list[dict[str, object]]:
        return self.service.lists(principal)

    def save_list(self, principal: Principal, name: str, recipients: list[dict[str, str]]) -> dict[str, object]:
        return self.service.save_list(principal, name, recipients)

    def prepare_send(self, principal: Principal, payload: dict[str, object]) -> dict[str, object]:
        return self.service.prepare(payload, principal)

    def execute_send(self, principal: Principal, draft_id: str, confirmation_token: str) -> dict[str, object]:
        return self.service.execute(draft_id, confirmation_token, principal)

    def reply(
        self, principal: Principal, identifier: str, comment: str, *,
        reply_all: bool = False, confirmed: bool = False,
    ) -> dict[str, object]:
        return self.service.reply(principal, identifier, comment, reply_all=reply_all, confirmed=confirmed)

    def forward(
        self, principal: Principal, identifier: str, recipients: list[str], comment: str, *,
        confirmed: bool = False,
    ) -> dict[str, object]:
        return self.service.forward(principal, identifier, recipients, comment, confirmed=confirmed)


def create_api(config: Config) -> CmailApi:
    return CmailApi.from_config(config)
