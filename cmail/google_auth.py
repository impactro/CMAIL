"""Google OAuth and protected token storage; independent of Gmail mailbox operations."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .auth import AuthenticationError, FLOW_TTL_SECONDS
from .config import Config
from .store import Store
from .http_io import read_limited, GMAIL_RESPONSE_BYTES, ERROR_RESPONSE_BYTES


GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
GOOGLE_ISSUER = "https://accounts.google.com"
GMAIL_SCOPES = (
    "openid", "email",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
)


HttpRequester = Callable[[str, str, dict[str, str], bytes | None], tuple[int, object]]


def _request(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, object]:
    selected = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(selected, timeout=20) as response:
            raw = read_limited(response, GMAIL_RESPONSE_BYTES)
            return int(response.status), json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(read_limited(exc, ERROR_RESPONSE_BYTES).decode("utf-8"))
        except Exception:
            value = {}
        return int(exc.code), value
    except urllib.error.URLError as exc:
        raise AuthenticationError("O Google não respondeu.") from exc


class ProtectedJsonFile:
    """Persistência JSON protegida por DPAPI no perfil Windows atual."""

    def __init__(self, path: Path):
        self.path = path

    def save(self, value: dict[str, object]) -> None:
        try:
            from msal_extensions import FilePersistenceWithDataProtection
        except ImportError as exc:
            raise AuthenticationError("Proteção DPAPI indisponível para o Gmail.") from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        persistence = FilePersistenceWithDataProtection(
            str(self.path), entropy="cmail-google-v1"
        )
        try:
            persistence.save(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        except Exception as exc:
            raise AuthenticationError("Não foi possível proteger a autorização Gmail.") from exc

    def load(self) -> dict[str, object] | None:
        if not self.path.is_file():
            return None
        try:
            from msal_extensions import FilePersistenceWithDataProtection
            raw = FilePersistenceWithDataProtection(
                str(self.path), entropy="cmail-google-v1"
            ).load()
            value = json.loads(raw)
        except Exception as exc:
            raise AuthenticationError("A autorização Gmail protegida é inválida.") from exc
        if not isinstance(value, dict):
            raise AuthenticationError("A autorização Gmail protegida é incompatível.")
        return value

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


class GoogleAuthService:
    """OAuth Gmail de uma única conta, vinculado ao navegador iniciador."""

    def __init__(
        self, config: Config, store: Store, *, requester: HttpRequester | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.store = store
        self.requester = requester or _request
        self.clock = clock
        self._pending: dict[str, dict[str, object]] = {}
        self._lock = threading.RLock()

    def _token_file(self, identity_id: str) -> ProtectedJsonFile:
        identity = self.store.identity(identity_id)
        if not identity or identity.get("provider") != "google":
            raise AuthenticationError("Identidade Gmail não encontrada.")
        owner = f"{identity['tenant_id']}:{identity['subject_id']}"
        key = hashlib.sha256(owner.encode()).hexdigest()[:32]
        return ProtectedJsonFile(
            self.config.state_dir / "security" / "google" / "tokens" / f"{key}.bin"
        )

    def _prune(self) -> None:
        cutoff = self.clock() - FLOW_TTL_SECONDS
        self._pending = {
            state: item for state, item in self._pending.items()
            if float(item["created"]) >= cutoff
        }

    def granted_scopes(self, identity_id: str) -> set[str]:
        value = self._token_file(identity_id).load() or {}
        scopes = value.get("scope", value.get("scopes", []))
        return set(scopes.split() if isinstance(scopes, str) else scopes) if isinstance(scopes, (str, list, tuple)) else set()

    def begin(self, owner_id: str = "") -> tuple[str, str]:
        if self.config.mode != "gmail":
            raise AuthenticationError("Login Google não está habilitado.")
        state = secrets.token_urlsafe(32)
        browser_nonce = secrets.token_urlsafe(24)
        with self._lock:
            self._prune()
            if len(self._pending) >= 128:
                raise AuthenticationError("Há muitos logins pendentes. Aguarde e tente novamente.")
            self._pending[state] = {
                "created": self.clock(),
                "browserHash": hashlib.sha256(browser_nonce.encode()).hexdigest(),
                "ownerId": str(owner_id or "").strip(),
            }
        parameters = {
            "client_id": self.config.google_client_id,
            "redirect_uri": self.config.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        if self.config.google_account:
            parameters["login_hint"] = self.config.google_account
        return GOOGLE_AUTH + "?" + urllib.parse.urlencode(parameters), browser_nonce

    def complete(
        self,
        response: dict[str, str],
        browser_nonce: str,
        owner_id: str = "",
    ) -> tuple[str, str, dict[str, str]]:
        state = str(response.get("state") or "")
        with self._lock:
            self._prune()
            pending = self._pending.pop(state, None)
        if not pending:
            raise AuthenticationError("Login Google ausente ou expirado.")
        owner = str(owner_id or "").strip()
        if not secrets.compare_digest(str(pending.get("ownerId") or ""), owner):
            raise AuthenticationError(
                "O workspace que iniciou o login não corresponde ao retorno."
            )
        supplied = hashlib.sha256(str(browser_nonce or "").encode()).hexdigest()
        if not secrets.compare_digest(str(pending["browserHash"]), supplied):
            raise AuthenticationError("O navegador que iniciou o login não corresponde ao retorno.")
        code = str(response.get("code") or "").strip()
        if not code:
            raise AuthenticationError("O Google não devolveu o código de autorização.")
        body = urllib.parse.urlencode({
            "client_id": self.config.google_client_id,
            "client_secret": self.config.google_client_secret(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.google_redirect_uri,
        }).encode("ascii")
        status, token = self.requester(
            "POST", GOOGLE_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, body
        )
        if status >= 300 or not isinstance(token, dict) or not token.get("refresh_token"):
            raise AuthenticationError("O Google não autorizou acesso permanente ao Gmail.")
        access_token = str(token.get("access_token") or "")
        status, userinfo = self.requester(
            "GET", GOOGLE_USERINFO,
            {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, None,
        )
        if status >= 300 or not isinstance(userinfo, dict):
            raise AuthenticationError("O Google não confirmou a identidade da conta.")
        subject = str(userinfo.get("sub") or "").strip()
        email = str(userinfo.get("email") or "").strip().casefold()
        if not subject or userinfo.get("email_verified") is not True or "@" not in email:
            raise AuthenticationError("O Google não devolveu uma identidade de e-mail válida.")
        if self.config.google_account and not secrets.compare_digest(
            email, self.config.google_account.casefold()
        ):
            raise AuthenticationError("A conta Google escolhida não corresponde a esta instância.")
        profile_status, profile = self.requester(
            "GET", GMAIL_API + "/profile",
            {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, None,
        )
        mailbox = str(profile.get("emailAddress") or "").strip().casefold() if isinstance(profile, dict) else ""
        if profile_status >= 300 or not mailbox or not secrets.compare_digest(mailbox, email):
            raise AuthenticationError("O Gmail não confirmou a mesma caixa de e-mail.")
        token["expires_at"] = int(time.time()) + int(token.get("expires_in") or 3600)
        token["email"] = email
        identity = self.store.save_identity(
            GOOGLE_ISSUER, subject, email, str(userinfo.get("name") or email)[:160],
            provider="google", scopes=list(GMAIL_SCOPES), enforce_single_account=True,
            owner_id=owner,
        )
        if not identity:
            raise AuthenticationError("A conta Google escolhida não corresponde a esta instância.")
        self._token_file(identity["id"]).save(token)
        session_token, csrf_token = self.store.create_session(
            identity["id"], self.config.session_hours
        )
        return session_token, csrf_token, identity

    def current(self, session_token: str) -> dict[str, str] | None:
        identity = self.store.session(session_token)
        if not identity or identity.get("provider") != "google":
            return None
        return identity if self.is_connected(identity["id"]) else None

    def session_identity(self, session_token: str) -> dict[str, str] | None:
        return self.store.session(session_token)

    def is_connected(self, identity_id: str) -> bool:
        connection = self.store.connection(identity_id)
        return bool(
            connection and connection.get("status") == "authorized"
            and self._token_file(identity_id).path.is_file()
        )

    def access_token(self, identity_id: str) -> str:
        connection = self.store.connection(identity_id)
        value = self._token_file(identity_id).load()
        if not connection or connection.get("status") != "authorized" or not value:
            raise AuthenticationError("A conta Gmail precisa ser autorizada novamente.")
        if int(value.get("expires_at") or 0) > int(time.time()) + 60 and value.get("access_token"):
            return str(value["access_token"])
        body = urllib.parse.urlencode({
            "client_id": self.config.google_client_id,
            "client_secret": self.config.google_client_secret(),
            "refresh_token": str(value.get("refresh_token") or ""),
            "grant_type": "refresh_token",
        }).encode("ascii")
        status, refreshed = self.requester(
            "POST", GOOGLE_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, body
        )
        if status >= 300 or not isinstance(refreshed, dict) or not refreshed.get("access_token"):
            self.store.set_connection_status(identity_id, "reauthorize", "refresh-token")
            raise AuthenticationError("A conta Gmail precisa ser autorizada novamente.")
        value.update(refreshed)
        value["expires_at"] = int(time.time()) + int(refreshed.get("expires_in") or 3600)
        self._token_file(identity_id).save(value)
        return str(value["access_token"])

    def logout(self, session_token: str) -> None:
        self.store.revoke_session(session_token)

    def disconnect(self, identity_id: str) -> None:
        value = self._token_file(identity_id).load() or {}
        selected = str(value.get("refresh_token") or value.get("access_token") or "")
        if selected:
            body = urllib.parse.urlencode({"token": selected}).encode("ascii")
            try:
                self.requester(
                    "POST", GOOGLE_REVOKE,
                    {"Content-Type": "application/x-www-form-urlencoded"}, body,
                )
            except Exception:
                pass
        self._token_file(identity_id).delete()
        self.store.set_connection_status(identity_id, "revoked")
        self.store.revoke_identity_sessions(identity_id)
