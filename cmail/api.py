"""API Python estável para runtimes agentes incorporarem o CMAIL."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

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
                "attachments": {"capability": "mail.read", "effect": "network-read"},
                "attachment": {"capability": "mail.read", "effect": "network-read"},
                "contacts": {"capability": "mail.read", "effect": "network-read"},
                "directory": {"capability": "mail.read", "effect": "network-read"},
                "calendars": {"capability": "mail.read", "effect": "network-read"},
                "calendar-view": {"capability": "mail.read", "effect": "network-read"},
                "event": {"capability": "mail.read", "effect": "network-read"},
                "event-create": {"capability": "mail.manage", "effect": "external-write-confirmed"},
                "event-update": {"capability": "mail.manage", "effect": "external-write-confirmed"},
                "event-delete": {"capability": "mail.manage", "effect": "external-write-confirmed"},
                "event-respond": {"capability": "mail.manage", "effect": "external-write-confirmed"},
                "owner-invalidate": {"capability": "host.security", "effect": "credential-revoke"},
                "system-send": {"capability": "host.recovery", "effect": "external-write"},
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

    def principal_for_owner(self, owner_id: str, capabilities: frozenset[str] | None = None) -> Principal:
        return self.service.principal_for_owner(owner_id, capabilities)

    def invalidate_owner(self, owner_id: str) -> None:
        self.service.invalidate_owner(owner_id)

    def system_send(self, owner_id: str, recipient: str, subject: str, body: str) -> dict[str, object]:
        principal = self.service.principal_for_owner(owner_id, frozenset({"mail.send"}))
        draft = self.service.prepare({"recipients": [recipient], "subject": subject, "body": body}, principal)
        return self.service.execute(str(draft["draftId"]), str(draft["confirmationToken"]), principal)

    def attachments(self, principal: Principal, identifier: str) -> list[dict[str, object]]:
        return self.service.attachments(principal, identifier)

    def attachment(self, principal: Principal, identifier: str, attachment_id: str) -> dict[str, object]:
        return self.service.attachment(principal, identifier, attachment_id)

    def contacts(self, principal: Principal, query: str = "", limit: int = 25) -> list[dict[str, object]]:
        return self.service.contacts(principal, query, limit)

    def directory(self, principal: Principal, query: str = "", limit: int = 20) -> list[dict[str, object]]:
        return self.service.directory(principal, query, limit)

    def calendars(self, principal: Principal) -> list[dict[str, object]]:
        return self.service.calendars(principal)

    def calendar_view(self, principal: Principal, start: str, end: str, time_zone: str, *, calendar_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        return self.service.calendar_view(principal, start, end, time_zone, calendar_id=calendar_id, limit=limit)

    def event(self, principal: Principal, identifier: str) -> dict[str, object]:
        return self.service.event(principal, identifier)

    def create_event(self, principal: Principal, event: dict[str, object], *, calendar_id: str = "", confirmed: bool = False) -> dict[str, object]:
        return self.service.create_event(principal, event, calendar_id=calendar_id, confirmed=confirmed)

    def update_event(self, principal: Principal, identifier: str, changes: dict[str, object], *, confirmed: bool = False) -> dict[str, object]:
        return self.service.update_event(principal, identifier, changes, confirmed=confirmed)

    def delete_event(self, principal: Principal, identifier: str, *, confirmed: bool = False) -> dict[str, object]:
        return self.service.delete_event(principal, identifier, confirmed=confirmed)

    def respond_event(self, principal: Principal, identifier: str, response: str, *, comment: str = "", send_response: bool = True, confirmed: bool = False) -> dict[str, object]:
        return self.service.respond_event(principal, identifier, response, comment=comment, send_response=send_response, confirmed=confirmed)


def create_api(config: Config) -> CmailApi:
    return CmailApi.from_config(config)


def create_component_api(
    agent_root: str | Path,
    host_services: Mapping[str, object] | None = None,
) -> CmailApi:
    services = dict(host_services or {})
    config_file = services.get("configFile")
    config = (
        Config.from_file(Path(config_file), root=agent_root)
        if config_file is not None
        else Config.load(Path(agent_root))
    )
    return create_api(config)
