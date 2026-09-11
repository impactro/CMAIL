"""Autenticação Microsoft própria do CMAIL, sem dependência do CraniaAgent."""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

from .config import Config
from .store import Store


MAIL_SCOPES = ("Mail.ReadWrite", "Mail.Send", "User.Read", "email")
IDENTITY_SCOPES = ("openid", "profile", "email")
FLOW_TTL_SECONDS = 10 * 60


class AuthenticationError(RuntimeError):
    """Falha de autenticação que pode ser mostrada sem revelar segredo."""


class OAuthClient(Protocol):
    def initiate_auth_code_flow(self, scopes: list[str], redirect_uri: str) -> dict[str, object]: ...
    def acquire_token_by_auth_code_flow(
        self, flow: dict[str, object], auth_response: dict[str, str]
    ) -> dict[str, object]: ...
    def get_accounts(self, username: str | None = None) -> list[dict[str, object]]: ...
    def acquire_token_silent(self, scopes: list[str], account: dict[str, object]) -> dict[str, object] | None: ...


OAuthClientFactory = Callable[[Config, Path], OAuthClient]


def build_microsoft_client(config: Config, cache_path: Path) -> OAuthClient:
    """Cria MSAL com cache DPAPI do usuário Windows que executa o CMAIL."""
    try:
        import msal
        from msal_extensions import FilePersistenceWithDataProtection, PersistedTokenCache
    except ImportError as exc:
        raise AuthenticationError(
            "Instale as dependências Microsoft do CMAIL para habilitar o login."
        ) from exc
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    persistence = FilePersistenceWithDataProtection(str(cache_path))
    cache = PersistedTokenCache(persistence)
    return msal.ConfidentialClientApplication(
        config.microsoft_client_id,
        authority=f"https://login.microsoftonline.com/{config.microsoft_tenant_id}",
        client_credential=config.microsoft_client_secret(),
        token_cache=cache,
        # MSAL adiciona openid/profile ao fluxo. O refresh implícito
        # offline_access fica deliberadamente excluído do consentimento.
        exclude_scopes=["offline_access"],
    )


class MicrosoftAuthService:
    """Une SSO e consentimento de e-mail em um fluxo isolado por identidade."""

    def __init__(
        self,
        config: Config,
        store: Store,
        *,
        client_factory: OAuthClientFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.store = store
        self.client_factory = client_factory or build_microsoft_client
        self.clock = clock
        self._pending: dict[str, dict[str, object]] = {}
        self._lock = threading.RLock()

    @property
    def required(self) -> bool:
        return self.config.mode == "microsoft"

    def _pending_cache(self, key: str) -> Path:
        return self.config.state_dir / "security" / "microsoft" / "pending" / f"{key}.bin"

    def _identity_cache(self, identity_id: str) -> Path:
        identity = self.store.identity(identity_id)
        if not identity:
            raise AuthenticationError("Identidade Microsoft não encontrada.")
        owner = f"{identity['tenant_id']}:{identity['subject_id']}"
        key = hashlib.sha256(owner.encode()).hexdigest()[:32]
        return self.config.state_dir / "security" / "microsoft" / "tokens" / f"{key}.bin"

    def _prune(self) -> None:
        cutoff = self.clock() - FLOW_TTL_SECONDS
        expired = [state for state, item in self._pending.items() if float(item["created"]) < cutoff]
        for state in expired:
            item = self._pending.pop(state)
            Path(item["cachePath"]).unlink(missing_ok=True)

    def begin(self) -> tuple[str, str]:
        if not self.required:
            raise AuthenticationError("Login Microsoft não está habilitado.")
        cache_key = secrets.token_urlsafe(18)
        cache_path = self._pending_cache(cache_key)
        try:
            flow = self.client_factory(self.config, cache_path).initiate_auth_code_flow(
                scopes=list(MAIL_SCOPES),
                redirect_uri=self.config.microsoft_redirect_uri,
            )
        except Exception as exc:
            raise AuthenticationError("Não foi possível iniciar o login Microsoft.") from exc
        state = str(flow.get("state") or "").strip()
        url = str(flow.get("auth_uri") or "").strip()
        if not state or not url:
            raise AuthenticationError("A Microsoft devolveu um fluxo de login inválido.")
        browser_nonce = secrets.token_urlsafe(24)
        with self._lock:
            self._prune()
            if len(self._pending) >= 128:
                raise AuthenticationError("Há muitos logins pendentes. Aguarde e tente novamente.")
            self._pending[state] = {
                "created": self.clock(),
                "flow": flow,
                "cachePath": cache_path,
                "browserHash": hashlib.sha256(browser_nonce.encode()).hexdigest(),
            }
        return url, browser_nonce

    def complete(self, response: dict[str, str], browser_nonce: str) -> tuple[str, str, dict[str, str]]:
        state = str(response.get("state") or "").strip()
        with self._lock:
            self._prune()
            pending = self._pending.pop(state, None)
        if pending is None:
            raise AuthenticationError("Login ausente ou expirado.")
        cache_path = Path(pending["cachePath"])
        browser_hash = hashlib.sha256(str(browser_nonce or "").encode()).hexdigest()
        if not secrets.compare_digest(str(pending["browserHash"]), browser_hash):
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError("O navegador que iniciou o login não corresponde ao retorno.")
        try:
            result = self.client_factory(self.config, cache_path).acquire_token_by_auth_code_flow(
                dict(pending["flow"]), response
            )
        except Exception as exc:
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError("A Microsoft não concluiu o login.") from exc
        if result.get("error") or not result.get("access_token"):
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError("A Microsoft não autorizou o acesso ao e-mail.")
        claims = result.get("id_token_claims")
        claims = claims if isinstance(claims, dict) else {}
        tenant = str(claims.get("tid") or "").strip()
        subject = str(claims.get("oid") or claims.get("sub") or "").strip()
        email = str(claims.get("preferred_username") or claims.get("email") or "").strip().casefold()
        if not tenant or not subject or "@" not in email:
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError("A Microsoft não devolveu uma identidade de e-mail válida.")
        if self.config.microsoft_account and not secrets.compare_digest(
            email, self.config.microsoft_account.casefold()
        ):
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError(
                "A conta Microsoft escolhida não corresponde a esta instância."
            )
        if not secrets.compare_digest(tenant.casefold(), self.config.microsoft_tenant_id.casefold()):
            cache_path.unlink(missing_ok=True)
            raise AuthenticationError("Esta conta pertence a outro diretório Microsoft.")
        identity = self.store.save_identity(
            tenant, subject, email, str(claims.get("name") or email).strip()[:160]
        )
        destination = self._identity_cache(identity["id"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cache_path.is_file():
            raise AuthenticationError("O cache protegido da autorização não foi criado.")
        os.replace(cache_path, destination)
        session_token, csrf_token = self.store.create_session(identity["id"], self.config.session_hours)
        return session_token, csrf_token, identity

    def current(self, session_token: str) -> dict[str, str] | None:
        identity = self.store.session(session_token)
        if not identity or not self.is_connected(str(identity["id"])):
            return None
        return identity

    def session_identity(self, session_token: str) -> dict[str, str] | None:
        return self.store.session(session_token)

    def is_connected(self, identity_id: str) -> bool:
        connection = self.store.connection(identity_id)
        return bool(
            connection and connection.get("status") == "authorized"
            and self._identity_cache(identity_id).is_file()
        )

    def access_token(self, identity_id: str) -> str:
        identity = self.store.identity(identity_id)
        connection = self.store.connection(identity_id)
        if not identity or not connection or connection.get("status") != "authorized":
            raise AuthenticationError("A conta Microsoft precisa ser autorizada novamente.")
        cache_path = self._identity_cache(identity_id)
        if not cache_path.is_file():
            self.store.set_connection_status(identity_id, "reauthorize", "cache-missing")
            raise AuthenticationError("A conta Microsoft precisa ser autorizada novamente.")
        try:
            client = self.client_factory(self.config, cache_path)
            accounts = client.get_accounts(username=identity["email"]) or client.get_accounts()
            result = client.acquire_token_silent(list(MAIL_SCOPES), accounts[0]) if accounts else None
        except Exception as exc:
            raise AuthenticationError("Não foi possível renovar a sessão Microsoft.") from exc
        if not result or not result.get("access_token"):
            self.store.set_connection_status(identity_id, "reauthorize", "silent-token")
            raise AuthenticationError("A conta Microsoft precisa ser autorizada novamente.")
        return str(result["access_token"])

    def logout(self, session_token: str) -> None:
        self.store.revoke_session(session_token)

    def disconnect(self, identity_id: str) -> None:
        self._identity_cache(identity_id).unlink(missing_ok=True)
        self.store.set_connection_status(identity_id, "revoked")
        self.store.revoke_identity_sessions(identity_id)
