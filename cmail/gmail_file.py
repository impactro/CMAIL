"""Single-account Gmail credentials by external authorized_user file; no SSO."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .auth import AuthenticationError
from .config import Config
from .gmail import GMAIL_API, GOOGLE_TOKEN

MAX_CREDENTIAL_BYTES = 65536
TOKEN_URIS = {GOOGLE_TOKEN, "https://accounts.google.com/o/oauth2/token"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuthenticationError("O Google recusou a autenticação por arquivo.")


def _request(method, url, headers, body):
    """Fixed TLS endpoints; never follow redirects carrying credentials."""
    if url != GOOGLE_TOKEN and not url.startswith(GMAIL_API + "/"):
        raise AuthenticationError("Endpoint Gmail não autorizado.")
    try:
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as error:
        return error.code, {}  # Never propagate provider bodies or raw tokens.
    except Exception:
        raise AuthenticationError("A comunicação com o Gmail falhou.") from None


def _read_json(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CREDENTIAL_BYTES + 1)
        value = json.loads(raw.decode("utf-8-sig"))
        if len(raw) > MAX_CREDENTIAL_BYTES or not isinstance(value, dict):
            raise ValueError()
        return value
    except Exception:
        raise AuthenticationError("Arquivo de credenciais Gmail ausente ou inválido.") from None


def _field(value, key, *, required=True):
    item = value.get(key, "")
    if not isinstance(item, str) or len(item) > 16384 or any(ord(c) < 32 for c in item):
        raise AuthenticationError("Credenciais Gmail inválidas.")
    if required and not item.strip():
        raise AuthenticationError("Credenciais Gmail incompletas.")
    return item


def _expiry(value):
    if not value:
        return 0.0  # Same conservative behavior as authorized_user without expiry.
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        raise AuthenticationError("Validade das credenciais Gmail inválida.") from None


def _duration(value):
    if type(value) is not int or not 0 < value <= 86400:
        raise AuthenticationError("Validade retornada pelo Google inválida.")
    return value


class GmailFileAuth:
    """Read source credentials, refresh only in memory, verify real mailbox."""
    def __init__(self, config: Config, *, requester=None):
        if config.mode != "gmail-file":
            raise ValueError("Configuração não é gmail-file.")
        self.config = config
        self._http = requester or _request
        self._lock = threading.RLock()
        self._digest = ""
        self._token = ""
        self._expires = 0.0
        self._validated = ""

    def requester(self, method, url, headers, body):
        if url != GOOGLE_TOKEN and not url.startswith(GMAIL_API + "/"):
            raise AuthenticationError("Endpoint Gmail não autorizado.")
        try:
            return self._http(method, url, headers, body)
        except Exception:
            raise AuthenticationError("A comunicação com o Gmail falhou.") from None

    def _credentials(self):
        value = _read_json(self.config.gmail_token_file)
        if value.get("type", "authorized_user") != "authorized_user":
            raise AuthenticationError("O arquivo não contém credenciais authorized_user.")
        if not isinstance(value.get("token_uri", GOOGLE_TOKEN), str) or value.get("token_uri", GOOGLE_TOKEN) not in TOKEN_URIS:
            raise AuthenticationError("Endpoint de renovação Gmail não autorizado.")
        for key in ("client_id", "client_secret", "refresh_token"):
            _field(value, key)
        token = _field(value, "token", required=False)
        expires = _expiry(value.get("expiry"))
        fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        if fingerprint != self._digest:
            self._digest, self._token, self._expires = fingerprint, token, expires
            self._validated = ""
        return value

    def _profile(self, token):
        status, profile = self.requester("GET", GMAIL_API + "/profile", {
            "Authorization": "Bearer " + token, "Accept": "application/json",
        }, None)
        email = str(profile.get("emailAddress") or "").strip().casefold() if isinstance(profile, dict) else ""
        if status != 200 or not email.isascii() or not secrets.compare_digest(email, self.config.gmail_file_account):
            raise AuthenticationError("O Gmail não confirmou a conta configurada.")

    def access_token(self, identity_id="", *, force_refresh=False):
        if identity_id:
            raise AuthenticationError("gmail-file não aceita identidade web.")
        with self._lock:
            value = self._credentials()
            if force_refresh or not self._token or self._expires <= time.time() + 60:
                body = urllib.parse.urlencode({
                    "client_id": value["client_id"], "client_secret": value["client_secret"],
                    "refresh_token": value["refresh_token"], "grant_type": "refresh_token",
                }).encode("ascii")
                status, result = self.requester("POST", GOOGLE_TOKEN, {
                    "Content-Type": "application/x-www-form-urlencoded",
                }, body)
                if status != 200 or not isinstance(result, dict):
                    raise AuthenticationError("Gmail exige nova autorização explícita.")
                self._token = _field(result, "access_token")
                self._expires = time.time() + _duration(result.get("expires_in", 3600))
                self._validated = ""
            if self._validated != self._token:
                self._profile(self._token)
                self._validated = self._token
            return self._token

    def status(self, *, refresh=False):
        self.access_token(force_refresh=refresh)
        return {"connected": True, "account": self.config.gmail_file_account,
                "provider": "gmail-file", "expiresAtIso": datetime.fromtimestamp(
                    self._expires, timezone.utc).isoformat(), "persisted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gmail por arquivo, sem SSO do CA.")
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("status", "refresh"):
        actions.add_parser(name).add_argument("--config-file", required=True)
    auth = actions.add_parser("auth", aliases=["init"])
    auth.add_argument("--client-file", required=True)
    auth.add_argument("--token-file", required=True)
    auth.add_argument("--account", required=True)
    auth.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.action in {"auth", "init"}:
            from .gmail_consent import authorize
            result = authorize(Path(args.client_file), Path(args.token_file), args.account,
                               timeout=args.timeout)
        else:
            result = GmailFileAuth(Config.from_file(args.config_file)).status(
                refresh=args.action == "refresh")
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except (AuthenticationError, ValueError, OSError):
        print(json.dumps({"ok": False, "error": "gmail_file_operation_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
