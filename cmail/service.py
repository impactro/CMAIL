"""Casos de uso de leitura, listas e envio confirmado."""

from __future__ import annotations

from .config import Config
from .mail import Provider, provider
from .store import Store


class MailService:
    def __init__(self, config: Config, mail_provider: Provider | None = None):
        self.config = config
        self.provider = mail_provider or provider(config)
        self.store = Store(config.state_dir)

    def status(self, live: bool = False) -> dict[str, object]:
        result = {"config": self.config.public(), "state": self.store.status()}
        if live:
            result["provider"] = self.provider.status()
        return result

    def prepare(self, payload: dict[str, object]) -> dict[str, object]:
        return self.store.prepare(payload)

    def execute(self, identifier: str, token: str) -> dict[str, object]:
        payload = self.store.claim(identifier, token)
        recipients = list(payload["recipients"])
        try:
            result = self.provider.send(recipients, str(payload["subject"]), str(payload["body"]))
        except Exception as exc:
            uncertain = {"accepted": False, "uncertain": True, "error": str(exc)[:240],
                         "recipientCount": len(recipients)}
            self.store.finish(identifier, "uncertain", uncertain)
            raise
        self.store.finish(identifier, "sent" if result.get("accepted") else "demo", result)
        return {"draftId": identifier, **result}
