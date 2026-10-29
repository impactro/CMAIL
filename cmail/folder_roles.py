"""Provider-neutral folder roles, preserving the provider's exact identifiers."""
import re

ALIASES = {
    "inbox": {"inbox", "caixa de entrada", "entrada"},
    "sent": {"sent", "sentitems", "sent items", "sent mail", "enviados", "itens enviados"},
    "drafts": {"draft", "drafts", "rascunhos"},
    "archive": {"archive", "archives", "arquivo", "arquivados"},
    "trash": {"trash", "deleteditems", "deleted items", "deleted messages", "bin", "lixeira", "itens excluídos", "itens eliminados"},
    "junk": {"junk", "junkemail", "junk e-mail", "spam", "lixo eletrônico"},
}


def folder_role(item: dict) -> str:
    explicit = str(item.get("wellKnownName") or "").casefold()
    if explicit in ALIASES:
        return explicit
    leaf = re.split(r"[/\.]", str(item.get("name") or item.get("id") or ""))[-1].strip().casefold()
    return next((role for role, names in ALIASES.items() if leaf in names), "")
