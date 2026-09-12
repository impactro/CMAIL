"""Configuração inicial local de uma única conta CMAIL."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .config import Config
from .store import EMAIL, Store


class SetupError(ValueError):
    pass


def _required(values: Mapping[str, str], key: str, label: str, maximum: int = 500) -> str:
    value = str(values.get(key) or "").strip()
    if not value:
        raise SetupError(f"{label} é obrigatório.")
    if len(value) > maximum:
        raise SetupError(f"{label} excede o limite permitido.")
    return value


def _account(values: Mapping[str, str]) -> str:
    value = _required(values, "account", "Conta de e-mail", 320).casefold()
    if not EMAIL.fullmatch(value):
        raise SetupError("Informe uma conta de e-mail válida.")
    return value


def _port(values: Mapping[str, str], key: str, label: str) -> int:
    try:
        value = int(_required(values, key, label, 5))
    except ValueError as exc:
        raise SetupError(f"{label} deve ser numérica.") from exc
    if not 1 <= value <= 65535:
        raise SetupError(f"{label} deve ficar entre 1 e 65535.")
    return value


def _security(values: Mapping[str, str], key: str, label: str) -> str:
    value = _required(values, key, label, 20).casefold()
    if value not in {"ssl", "starttls"}:
        raise SetupError(f"{label} deve ser SSL ou STARTTLS.")
    return value


def _restrict_to_current_user(path: Path) -> bool:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        return False
    if os.name != "nt":
        return True
    try:
        identity = subprocess.run(
            ["whoami"], check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        ).stdout.strip()
        if not identity:
            return False
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(F)"],
            check=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _write_secret(path: Path, value: str) -> None:
    if not value or len(value) > 16_384:
        raise SetupError("O segredo está vazio ou excede o limite permitido.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(temporary, flags, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if not _restrict_to_current_user(temporary):
            raise SetupError("Não foi possível restringir o arquivo de segredo ao usuário atual.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _reference(config: Config, path: Path) -> str:
    try:
        return os.path.relpath(path, config.config_file.parent).replace("\\", "/")
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class SetupResult:
    provider: str
    account: str
    restart_required: bool = True


class SetupService:
    """Atualiza somente o JSON apontado pela instância e segredos referenciados."""

    def __init__(self, config: Config):
        self.config = config

    def save(self, values: Mapping[str, str]) -> SetupResult:
        provider = _required(values, "provider", "Provedor", 20).casefold()
        if provider not in {"imap", "outlook", "gmail"}:
            raise SetupError("Escolha IMAP, Outlook ou Gmail.")
        state = self.config.state_dir
        base = {
            "schemaVersion": "1.1",
            "mode": "microsoft" if provider == "outlook" else provider,
            "server": {
                "host": self.config.host,
                "port": self.config.port,
                "openBrowser": self.config.open_browser,
                "sessionHours": self.config.session_hours,
                "cookieSecure": self.config.cookie_secure,
            },
            "state": {"directory": _reference(self.config, state)},
            "microsoft": {
                "account": "", "clientId": "", "tenantId": "",
                "clientSecretFile": "", "redirectUri": "",
            },
            "google": {
                "account": "", "clientId": "", "clientSecretFile": "",
                "redirectUri": "",
            },
            "imap": {
                "account": "", "username": "", "passwordFile": "",
                "imapHost": "", "imapPort": 993, "imapSecurity": "ssl",
                "smtpHost": "", "smtpPort": 587, "smtpSecurity": "starttls",
                "sentFolder": "Sent",
            },
        }
        if provider == "imap":
            account = _account(values)
            supplied_password = str(values.get("password") or "")
            password_path = state / "security" / "imap" / "password.txt"
            if supplied_password:
                _write_secret(password_path, supplied_password)
            elif self.config.mode == "imap" and self.config.password_file and self.config.password_file.is_file():
                password_path = self.config.password_file
            else:
                raise SetupError("Senha é obrigatória na primeira configuração IMAP.")
            base["imap"] = {
                "account": account,
                "username": _required(values, "username", "Usuário IMAP", 320),
                "passwordFile": _reference(self.config, password_path),
                "imapHost": _required(values, "imapHost", "Servidor IMAP", 255),
                "imapPort": _port(values, "imapPort", "Porta IMAP"),
                "imapSecurity": _security(values, "imapSecurity", "Segurança IMAP"),
                "smtpHost": _required(values, "smtpHost", "Servidor SMTP", 255),
                "smtpPort": _port(values, "smtpPort", "Porta SMTP"),
                "smtpSecurity": _security(values, "smtpSecurity", "Segurança SMTP"),
                "sentFolder": _required(values, "sentFolder", "Pasta de enviados", 255),
            }
        elif provider == "outlook":
            secret_path = state / "security" / "microsoft" / "client-secret.txt"
            supplied_secret = str(values.get("clientSecret") or "")
            if supplied_secret:
                _write_secret(secret_path, supplied_secret)
            elif (
                self.config.mode == "microsoft"
                and self.config.microsoft_client_secret_file
                and self.config.microsoft_client_secret_file.is_file()
            ):
                secret_path = self.config.microsoft_client_secret_file
            else:
                raise SetupError("Segredo do aplicativo é obrigatório na primeira configuração Microsoft.")
            base["microsoft"] = {
                "account": "",
                "clientId": _required(values, "clientId", "Client ID", 255),
                "tenantId": _required(values, "tenantId", "Tenant ID", 255),
                "clientSecretFile": _reference(self.config, secret_path),
                "redirectUri": f"http://localhost:{self.config.port}/auth/callback",
            }
        else:
            secret_path = state / "security" / "google" / "client-secret.txt"
            supplied_secret = str(values.get("clientSecret") or "")
            if supplied_secret:
                _write_secret(secret_path, supplied_secret)
            elif (
                self.config.mode == "gmail"
                and self.config.google_client_secret_file
                and self.config.google_client_secret_file.is_file()
            ):
                secret_path = self.config.google_client_secret_file
            else:
                raise SetupError("Segredo do aplicativo é obrigatório na primeira configuração Google.")
            base["google"] = {
                "account": "",
                "clientId": _required(values, "clientId", "Client ID", 255),
                "clientSecretFile": _reference(self.config, secret_path),
                "redirectUri": f"http://{self.config.host}:{self.config.port}/auth/google/callback",
            }

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.config.config_file.with_name(
            f"{self.config.config_file.stem}.before-setup-{timestamp}{self.config.config_file.suffix}"
        )
        shutil.copy2(self.config.config_file, backup)
        temporary = self.config.config_file.with_suffix(f".{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.config.config_file)
            try:
                Config.load(self.config.root)
                Store(state).reset_oauth_identities()
            except Exception:
                shutil.copy2(backup, self.config.config_file)
                raise
        finally:
            temporary.unlink(missing_ok=True)
        return SetupResult(provider, account if provider == "imap" else "Conta definida no login OAuth")
