"""Descritor CM 2 do CMAIL."""

from pathlib import Path

from . import __version__


def describe() -> dict[str, object]:
    root = Path(__file__).resolve().parent / "skills"

    def skill(name: str) -> Path:
        return (root / name / "SKILL.md").resolve()

    return {
        "id": "cmail", "contractVersion": 2, "version": __version__, "pythonModule": "cmail",
        "description": "Webmail independente com Microsoft SSO/Graph, API Python, listas e envio confirmado.",
        "skillGroups": [
            {"id": "webmail", "name": "Webmail", "description": "Consulta e gestão de conta, pastas e mensagens.",
             "skills": [{"path": skill("consultar-email"), "operations": ["check-config", "status", "list-folders", "list-messages", "serve"]}]},
            {"id": "mailing", "name": "Listas e disparos", "description": "Gestão local de listas e envio com confirmação.",
             "skills": [{"path": skill("gerir-listas-email"), "operations": ["lists"]},
                        {"path": skill("enviar-email"), "operations": ["send-prepare", "send-execute"]}]},
        ],
        "operations": {
            "check-config": {"description": "Valida referências sem abrir conexão.", "argv": ["check-config"], "effects": []},
            "status": {"description": "Mostra configuração e estado local.", "argv": ["status"], "effects": ["read-files"]},
            "list-folders": {"description": "Lista pastas da conta configurada.", "argv": ["list-folders"], "effects": ["read-files", "network-read"]},
            "list-messages": {"description": "Lista mensagens sem executar ação externa.", "argv": ["list-messages"], "effects": ["read-files", "network-read"]},
            "lists": {"description": "Lista ou atualiza listas locais de destinatários.", "argv": ["lists"], "effects": ["read-files", "write-files"]},
            "send-prepare": {"description": "Cria prévia e confirmação de envio, sem enviar.", "argv": ["send-prepare"], "effects": ["read-files", "write-files"]},
            "send-execute": {"description": "Envia um rascunho confirmado e não repete falha incerta.", "argv": ["send-execute"], "effects": ["read-files", "write-files", "network-and-external-write-with-execute"]},
            "serve": {"description": "Abre webmail Flask exclusivamente local.", "argv": ["serve"], "effects": ["network-listen:loopback", "read-files", "write-files", "network-read", "external-write-with-confirmation"]},
        },
    }
