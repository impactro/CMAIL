"""Host-asserted identity and capabilities shared by all adapters."""
from __future__ import annotations

from dataclasses import dataclass


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
