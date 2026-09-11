"""Configuração única e referências externas de segredo do CMAIL."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Linha {number} do .env não possui '='.")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not key.replace("_", "").isalnum():
            raise ConfigError(f"Chave inválida na linha {number} do .env.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _path(root: Path, raw: str, default: str = "") -> Path:
    candidate = Path(raw or default).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _bool(value: str, default: bool) -> bool:
    selected = str(value or "").strip().casefold()
    if not selected:
        return default
    if selected in {"1", "true", "yes", "on", "sim"}:
        return True
    if selected in {"0", "false", "no", "off", "nao", "não"}:
        return False
    raise ConfigError("Valor booleano inválido.")


@dataclass(frozen=True)
class Config:
    root: Path
    mode: str
    state_dir: Path
    host: str
    port: int
    open_browser: bool
    account: str
    username: str
    password_file: Path | None
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    sent_folder: str

    @classmethod
    def load(cls, root: str | Path | None = None) -> "Config":
        base = Path(root or os.getcwd()).resolve()
        values = dict(os.environ)
        values.update(parse_env(base / ".env"))
        mode = values.get("CMAIL_MODE", "demo").strip().casefold()
        if mode not in {"demo", "imap"}:
            raise ConfigError("CMAIL_MODE deve ser demo ou imap.")
        host = values.get("CMAIL_HOST", "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ConfigError("CMAIL_HOST suporta somente loopback nesta versão.")
        imap_security = values.get("CMAIL_IMAP_SECURITY", "ssl").strip().casefold()
        smtp_security = values.get("CMAIL_SMTP_SECURITY", "starttls").strip().casefold()
        if imap_security not in {"ssl", "starttls"} or smtp_security not in {"ssl", "starttls"}:
            raise ConfigError("Segurança de e-mail deve ser ssl ou starttls.")
        try:
            port = int(values.get("CMAIL_PORT", "7420"))
            imap_port = int(values.get("CMAIL_IMAP_PORT", "993"))
            smtp_port = int(values.get("CMAIL_SMTP_PORT", "587"))
        except ValueError as exc:
            raise ConfigError("Porta inválida.") from exc
        if any(not 1 <= item <= 65535 for item in (port, imap_port, smtp_port)):
            raise ConfigError("Porta fora da faixa permitida.")
        password_raw = values.get("CMAIL_PASSWORD_FILE", "").strip()
        config = cls(
            root=base, mode=mode, state_dir=_path(base, values.get("CMAIL_STATE_DIR", ".state")),
            host=host, port=port, open_browser=_bool(values.get("CMAIL_OPEN_BROWSER", ""), True),
            account=values.get("CMAIL_ACCOUNT", "").strip(),
            username=values.get("CMAIL_USERNAME", values.get("CMAIL_ACCOUNT", "")).strip(),
            password_file=_path(base, password_raw) if password_raw else None,
            imap_host=values.get("CMAIL_IMAP_HOST", "").strip(), imap_port=imap_port,
            imap_security=imap_security, smtp_host=values.get("CMAIL_SMTP_HOST", "").strip(),
            smtp_port=smtp_port, smtp_security=smtp_security,
            sent_folder=values.get("CMAIL_SENT_FOLDER", "Sent").strip() or "Sent",
        )
        if mode == "imap" and not all((config.account, config.username, config.password_file,
                                        config.imap_host, config.smtp_host)):
            raise ConfigError("Conta IMAP exige account, username, password file e hosts IMAP/SMTP.")
        return config

    def password(self) -> str:
        if self.mode != "imap" or self.password_file is None:
            return ""
        if not self.password_file.is_file():
            raise ConfigError("CMAIL_PASSWORD_FILE não está disponível.")
        value = self.password_file.read_text(encoding="utf-8-sig").strip()
        if not value:
            raise ConfigError("Arquivo de senha está vazio.")
        return value

    def public(self) -> dict[str, object]:
        return {"mode": self.mode, "configured": self.mode == "demo" or bool(
                    self.account and self.username and self.password_file and self.imap_host and self.smtp_host),
                "credentialAvailable": bool(self.password_file and self.password_file.is_file()),
                "account": self.account, "host": self.host, "port": self.port}
