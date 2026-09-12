"""Configuração JSON única e estrita do CMAIL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


ROOT_KEYS_V1 = {"schemaVersion", "mode", "server", "state", "microsoft", "imap"}
ROOT_KEYS_V11 = ROOT_KEYS_V1 | {"google"}
SERVER_KEYS = {"host", "port", "openBrowser", "sessionHours", "cookieSecure"}
STATE_KEYS = {"directory"}
MICROSOFT_KEYS = {"clientId", "tenantId", "clientSecretFile", "redirectUri"}
MICROSOFT_KEYS_V11 = MICROSOFT_KEYS | {"account"}
GOOGLE_KEYS = {"account", "clientId", "clientSecretFile", "redirectUri"}
IMAP_KEYS = {
    "account", "username", "passwordFile", "imapHost", "imapPort", "imapSecurity",
    "smtpHost", "smtpPort", "smtpSecurity", "sentFolder",
}


def parse_env_pointer(path: Path) -> str:
    if not path.is_file():
        raise ConfigError("O .env do CMAIL não foi encontrado.")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Linha {number} do .env não possui '='.")
        key, value = (item.strip() for item in line.split("=", 1))
        if key in values:
            raise ConfigError(f"Chave duplicada no .env: {key}.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    if set(values) != {"CMAIL_CONFIG_FILE"}:
        raise ConfigError("O .env deve conter somente CMAIL_CONFIG_FILE.")
    if not values["CMAIL_CONFIG_FILE"]:
        raise ConfigError("CMAIL_CONFIG_FILE não pode estar vazio.")
    return values["CMAIL_CONFIG_FILE"]


def _object(value: object, label: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} deve ser um objeto JSON.")
    actual = set(value)
    if actual != keys:
        missing, extra = sorted(keys - actual), sorted(actual - keys)
        details = []
        if missing:
            details.append("faltando " + ", ".join(missing))
        if extra:
            details.append("desconhecido " + ", ".join(extra))
        raise ConfigError(f"Contrato fechado inválido em {label}: {'; '.join(details)}.")
    return value


def _text(value: object, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{label} deve ser texto.")
    selected = value.strip()
    if required and not selected:
        raise ConfigError(f"{label} é obrigatório.")
    return selected


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigError(f"{label} deve ser inteiro entre {minimum} e {maximum}.")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} deve ser booleano.")
    return value


def _path(config_root: Path, value: object, label: str, *, required: bool = False) -> Path | None:
    selected = _text(value, label, required=required)
    if not selected:
        return None
    candidate = Path(selected)
    return candidate.resolve() if candidate.is_absolute() else (config_root / candidate).resolve()


def _redirect(value: object, label: str, suffix: str) -> str:
    selected = _text(value, label)
    if not selected:
        return ""
    parsed = urlparse(selected)
    loopback_http = (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    )
    if (
        not (parsed.scheme == "https" or loopback_http)
        or not parsed.path.endswith(suffix)
        or ".." in parsed.path.split("/")
    ):
        raise ConfigError(
            f"{label} deve usar HTTPS ou HTTP loopback e terminar em {suffix}."
        )
    return selected


@dataclass(frozen=True)
class Config:
    root: Path
    config_file: Path
    schema_version: str
    mode: str
    state_dir: Path
    host: str
    port: int
    open_browser: bool
    session_hours: int
    cookie_secure: bool
    microsoft_client_id: str
    microsoft_tenant_id: str
    microsoft_client_secret_file: Path | None
    microsoft_redirect_uri: str
    microsoft_account: str
    google_client_id: str
    google_client_secret_file: Path | None
    google_redirect_uri: str
    google_account: str
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
        base = Path(root or Path.cwd()).resolve()
        pointer = Path(parse_env_pointer(base / ".env"))
        config_file = pointer.resolve() if pointer.is_absolute() else (base / pointer).resolve()
        return cls.from_file(config_file, root=base)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        root: str | Path | None = None,
    ) -> "Config":
        """Load the JSON directly when an embedding host owns the agent .env."""
        config_file = Path(path).expanduser().resolve()
        execution_root = Path(root).resolve() if root is not None else config_file.parent
        if not config_file.is_file():
            raise ConfigError("O JSON indicado por CMAIL_CONFIG_FILE não foi encontrado.")
        if config_file.stat().st_size > 512 * 1024:
            raise ConfigError("O JSON de configuração excede 512 KiB.")
        try:
            raw = json.loads(config_file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConfigError("O JSON de configuração é inválido.") from exc
        if not isinstance(raw, dict):
            raise ConfigError("raiz deve ser um objeto JSON.")
        schema_version = str(raw.get("schemaVersion") or "")
        if schema_version not in {"1.0", "1.1"}:
            raise ConfigError("schemaVersion deve ser 1.0 ou 1.1.")
        value = _object(
            raw, "raiz", ROOT_KEYS_V1 if schema_version == "1.0" else ROOT_KEYS_V11
        )
        mode = _text(value["mode"], "mode", required=True).casefold()
        allowed_modes = {"demo", "imap", "microsoft"}
        if schema_version == "1.1":
            allowed_modes.update({"setup", "gmail"})
        if mode not in allowed_modes:
            raise ConfigError("mode deve ser setup, demo, imap, microsoft ou gmail.")
        server = _object(value["server"], "server", SERVER_KEYS)
        state = _object(value["state"], "state", STATE_KEYS)
        microsoft = _object(
            value["microsoft"], "microsoft",
            MICROSOFT_KEYS if schema_version == "1.0" else MICROSOFT_KEYS_V11,
        )
        google = (
            _object(value["google"], "google", GOOGLE_KEYS)
            if schema_version == "1.1"
            else {"account": "", "clientId": "", "clientSecretFile": "", "redirectUri": ""}
        )
        imap = _object(value["imap"], "imap", IMAP_KEYS)
        config_root = config_file.parent
        host = _text(server["host"], "server.host", required=True)
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ConfigError("server.host suporta somente loopback nesta versão.")
        imap_security = _text(imap["imapSecurity"], "imap.imapSecurity", required=True).casefold()
        smtp_security = _text(imap["smtpSecurity"], "imap.smtpSecurity", required=True).casefold()
        if imap_security not in {"ssl", "starttls"} or smtp_security not in {"ssl", "starttls"}:
            raise ConfigError("Segurança IMAP/SMTP deve ser ssl ou starttls.")
        redirect_uri = _redirect(
            microsoft["redirectUri"], "microsoft.redirectUri", "/auth/callback"
        )
        google_redirect_uri = _redirect(
            google["redirectUri"], "google.redirectUri", "/auth/google/callback"
        )
        state_dir = _path(config_root, state["directory"], "state.directory", required=True)
        config = cls(
            root=execution_root, config_file=config_file, schema_version=schema_version,
            mode=mode, state_dir=state_dir,
            host=host, port=_integer(server["port"], "server.port", 1, 65535),
            open_browser=_boolean(server["openBrowser"], "server.openBrowser"),
            session_hours=_integer(server["sessionHours"], "server.sessionHours", 1, 168),
            cookie_secure=_boolean(server["cookieSecure"], "server.cookieSecure"),
            microsoft_client_id=_text(microsoft["clientId"], "microsoft.clientId"),
            microsoft_tenant_id=_text(microsoft["tenantId"], "microsoft.tenantId"),
            microsoft_client_secret_file=_path(config_root, microsoft["clientSecretFile"], "microsoft.clientSecretFile"),
            microsoft_redirect_uri=redirect_uri,
            microsoft_account=_text(microsoft.get("account", ""), "microsoft.account"),
            google_client_id=_text(google["clientId"], "google.clientId"),
            google_client_secret_file=_path(
                config_root, google["clientSecretFile"], "google.clientSecretFile"
            ),
            google_redirect_uri=google_redirect_uri,
            google_account=_text(google["account"], "google.account"),
            account=_text(imap["account"], "imap.account"), username=_text(imap["username"], "imap.username"),
            password_file=_path(config_root, imap["passwordFile"], "imap.passwordFile"),
            imap_host=_text(imap["imapHost"], "imap.imapHost"),
            imap_port=_integer(imap["imapPort"], "imap.imapPort", 1, 65535),
            imap_security=imap_security, smtp_host=_text(imap["smtpHost"], "imap.smtpHost"),
            smtp_port=_integer(imap["smtpPort"], "imap.smtpPort", 1, 65535),
            smtp_security=smtp_security,
            sent_folder=_text(imap["sentFolder"], "imap.sentFolder", required=True),
        )
        if mode == "imap" and not all((config.account, config.username, config.password_file, config.imap_host, config.smtp_host)):
            raise ConfigError("Modo IMAP exige conta, usuário, passwordFile e hosts IMAP/SMTP.")
        if mode == "microsoft" and not all((config.microsoft_client_id, config.microsoft_tenant_id, config.microsoft_client_secret_file, config.microsoft_redirect_uri)):
            raise ConfigError("Modo Microsoft exige clientId, tenantId, clientSecretFile e redirectUri.")
        if mode == "gmail" and not all((
            config.google_client_id, config.google_client_secret_file,
            config.google_redirect_uri,
        )):
            raise ConfigError("Modo Gmail exige clientId, clientSecretFile e redirectUri.")
        return config

    def password(self) -> str:
        if self.mode != "imap" or self.password_file is None:
            return ""
        if not self.password_file.is_file():
            raise ConfigError("A referência imap.passwordFile não está disponível.")
        value = self.password_file.read_text(encoding="utf-8-sig").strip()
        if not value:
            raise ConfigError("O arquivo de senha IMAP está vazio.")
        return value

    def microsoft_client_secret(self) -> str:
        if self.mode != "microsoft" or self.microsoft_client_secret_file is None:
            return ""
        if not self.microsoft_client_secret_file.is_file():
            raise ConfigError("A referência microsoft.clientSecretFile não está disponível.")
        value = self.microsoft_client_secret_file.read_text(encoding="utf-8-sig").strip()
        if not value:
            raise ConfigError("O arquivo de segredo Microsoft está vazio.")
        return value

    def google_client_secret(self) -> str:
        if self.mode != "gmail" or self.google_client_secret_file is None:
            return ""
        if not self.google_client_secret_file.is_file():
            raise ConfigError("A referência google.clientSecretFile não está disponível.")
        value = self.google_client_secret_file.read_text(encoding="utf-8-sig").strip()
        if not value:
            raise ConfigError("O arquivo de segredo Google está vazio.")
        return value

    def public(self) -> dict[str, object]:
        credential = (
            self.password_file if self.mode == "imap"
            else self.microsoft_client_secret_file if self.mode == "microsoft"
            else self.google_client_secret_file if self.mode == "gmail"
            else None
        )
        return {
            "schemaVersion": self.schema_version, "mode": self.mode,
            "configured": self.mode not in {"setup"},
            "credentialAvailable": bool(credential and credential.is_file()),
            "host": self.host, "port": self.port,
            "authenticationRequired": self.mode in {"microsoft", "gmail"},
            "singleAccount": True,
        }
