"""FastAPI/ASGI application factory for standalone and embedded CMAIL."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any, Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .auth import AuthenticationError
from .config import Config
from .service import MANAGE_LISTS, MANAGE_MAIL, READ_MAIL, SEND_MAIL, MailService, Principal
from .setup import SetupError, SetupService


SESSION_COOKIE = "cmail_session"
CSRF_COOKIE = "cmail_csrf"
BROWSER_COOKIE = "cmail_oauth_browser"
PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
LOGGER = logging.getLogger(__name__)


def _base_path(request: Request) -> str:
    return str(request.scope.get("root_path") or "").rstrip("/")


def _cookie_path(request: Request, suffix: str = "/") -> str:
    prefix = _base_path(request)
    return f"{prefix}{suffix}" or "/"


def _web_principal(service: MailService, request: Request) -> Principal | None:
    if service.config.mode == "demo":
        return Principal.local_operator()
    if service.config.mode == "imap":
        return Principal(
            "local-imap", service.config.account,
            frozenset({READ_MAIL, MANAGE_MAIL, SEND_MAIL, MANAGE_LISTS}),
        )
    if service.auth is None:
        return None
    identity = service.auth.current(str(request.cookies.get(SESSION_COOKIE) or ""))
    if not identity:
        return None
    return Principal(
        str(identity["id"]), str(identity["email"]),
        frozenset({READ_MAIL, MANAGE_MAIL, SEND_MAIL, MANAGE_LISTS}),
    )


async def _payload(request: Request) -> dict[str, object]:
    value = await request.json()
    if not isinstance(value, dict):
        raise ValueError("JSON deve ser um objeto.")
    return value


def _create_module_app(
    config: Config,
    service: MailService | None = None,
    *,
    restart_callback: Callable[[], None] | None = None,
) -> FastAPI:
    current = service or MailService(config)
    app = FastAPI(title="CMAIL", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_hex(32),
        same_site="strict",
        https_only=config.cookie_secure,
        session_cookie="cmail_setup_session",
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="cmail.static")

    def csrf(request: Request, principal: Principal | None) -> str:
        if config.mode in {"demo", "imap", "setup"}:
            return request.session.setdefault("cmail_csrf", secrets.token_urlsafe(24))
        return str(request.cookies.get(CSRF_COOKIE) or "") if principal else ""

    def setup_csrf(request: Request) -> str:
        return request.session.setdefault("cmail_setup_csrf", secrets.token_urlsafe(24))

    def setup_values() -> dict[str, object]:
        provider = (
            "outlook" if config.mode == "microsoft" else
            "gmail" if config.mode == "gmail" else
            "imap" if config.mode == "imap" else "outlook"
        )
        bound = (
            current.store.bound_identity("microsoft") if provider == "outlook" else
            current.store.bound_identity("google") if provider == "gmail" else None
        )
        return {
            "provider": provider,
            "oauthAccount": str(bound.get("email") if bound else (
                config.microsoft_account if provider == "outlook" else config.google_account
            ) or ""),
            "account": config.account if provider == "imap" else "",
            "clientId": config.microsoft_client_id if provider == "outlook" else config.google_client_id,
            "tenantId": config.microsoft_tenant_id if provider == "outlook" else "",
            "hasOAuthSecret": bool(
                config.microsoft_client_secret_file and config.microsoft_client_secret_file.is_file()
                if provider == "outlook" else
                config.google_client_secret_file and config.google_client_secret_file.is_file()
            ),
            "username": config.username if provider == "imap" else "",
            "hasImapPassword": bool(config.password_file and config.password_file.is_file()),
            "imapHost": config.imap_host,
            "imapPort": config.imap_port,
            "imapSecurity": config.imap_security,
            "smtpHost": config.smtp_host,
            "smtpPort": config.smtp_port,
            "smtpSecurity": config.smtp_security,
            "sentFolder": config.sent_folder,
        }

    def render_setup(request: Request, error: str = "", status_code: int = 200):
        return TEMPLATES.TemplateResponse(
            request=request, name="setup.html", status_code=status_code,
            context={
                "csrf": setup_csrf(request), "port": config.port,
                "error": error[:240], "values": setup_values(),
                "base_path": _base_path(request),
            },
        )

    def require_principal(request: Request) -> Principal:
        principal = _web_principal(current, request)
        if principal is None:
            raise AuthenticationError("Autentique a conta de e-mail desta instância.")
        return principal

    def require_csrf(request: Request, principal: Principal) -> None:
        supplied = str(request.headers.get("X-CSRF-Token") or "")
        if config.mode in {"demo", "imap", "setup"}:
            if not supplied or not secrets.compare_digest(supplied, csrf(request, principal)):
                raise PermissionError("CSRF_INVALID")
            return
        identity = current.auth.current(str(request.cookies.get(SESSION_COOKIE) or "")) if current.auth else None
        if not identity or not current.store.csrf_valid(identity, supplied):
            raise PermissionError("CSRF_INVALID")

    @app.get("/", response_class=HTMLResponse, name="cmail.index")
    async def index(request: Request):
        if config.mode == "setup":
            return RedirectResponse(str(request.url_for("cmail.setup")), status_code=303)
        principal = _web_principal(current, request)
        if config.mode == "microsoft" and principal is None:
            return RedirectResponse(str(request.url_for("cmail.microsoft_login")), status_code=303)
        if config.mode == "gmail" and principal is None:
            return RedirectResponse(str(request.url_for("cmail.google_login")), status_code=303)
        auth_state = "demo" if config.mode == "demo" else "connected" if principal else "disconnected"
        if config.mode in {"microsoft", "gmail"} and principal is None and current.auth:
            if current.auth.session_identity(str(request.cookies.get(SESSION_COOKIE) or "")):
                auth_state = "reauthorize"
        return TEMPLATES.TemplateResponse(
            request=request, name="index.html",
            context={
                "csrf": csrf(request, principal), "authenticated": principal is not None,
                "identity": {"email": principal.email} if principal else None,
                "mode": config.mode, "auth_state": auth_state,
                "base_path": _base_path(request),
            },
        )

    @app.get("/health")
    async def health():
        return {
            "ok": True, "component": "cmail", "mode": config.mode,
            "configured": config.mode != "setup", "singleAccount": True,
            "version": __version__, "framework": "fastapi",
        }

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        principal = _web_principal(current, request)
        return {
            "ok": True, "required": config.mode in {"microsoft", "gmail"},
            "authenticated": principal is not None,
            "identity": {"email": principal.email} if principal else None,
        }

    def begin_oauth(request: Request, provider: str):
        if config.mode != provider or current.auth is None:
            raise AuthenticationError("Login OAuth não está habilitado.")
        url, browser_nonce = current.auth.begin()
        response = RedirectResponse(url, status_code=302)
        callback = "/auth/callback" if provider == "microsoft" else "/auth/google/callback"
        response.set_cookie(
            BROWSER_COOKIE, browser_nonce, httponly=True, secure=config.cookie_secure,
            samesite="lax", max_age=600, path=_cookie_path(request, callback),
        )
        return response

    @app.get("/auth/microsoft", name="cmail.microsoft_login")
    async def microsoft_login(request: Request):
        return begin_oauth(request, "microsoft")

    @app.get("/auth/google", name="cmail.google_login")
    async def google_login(request: Request):
        return begin_oauth(request, "gmail")

    def complete_oauth(request: Request, callback: str):
        if current.auth is None:
            raise AuthenticationError("Login OAuth não está habilitado.")
        response_values = {key: str(value) for key, value in request.query_params.items()}
        session_token, csrf_token, _identity = current.auth.complete(
            response_values, str(request.cookies.get(BROWSER_COOKIE) or "")
        )
        response = RedirectResponse(str(request.url_for("cmail.index")), status_code=303)
        root = _cookie_path(request)
        response.set_cookie(
            SESSION_COOKIE, session_token, httponly=True, secure=config.cookie_secure,
            samesite="lax", max_age=config.session_hours * 3600, path=root,
        )
        response.set_cookie(
            CSRF_COOKIE, csrf_token, httponly=False, secure=config.cookie_secure,
            samesite="strict", max_age=config.session_hours * 3600, path=root,
        )
        response.delete_cookie(BROWSER_COOKIE, path=_cookie_path(request, callback))
        return response

    @app.get("/auth/google/callback", name="cmail.google_callback")
    async def google_callback(request: Request):
        if config.mode != "gmail":
            raise AuthenticationError("Login Google não está habilitado.")
        return complete_oauth(request, "/auth/google/callback")

    @app.get("/auth/callback", name="cmail.microsoft_callback")
    async def microsoft_callback(request: Request):
        if config.mode != "microsoft":
            raise AuthenticationError("Login Microsoft não está habilitado.")
        return complete_oauth(request, "/auth/callback")

    @app.get("/setup", response_class=HTMLResponse, name="cmail.setup")
    async def setup_page(request: Request):
        return render_setup(request, str(request.query_params.get("error") or ""))

    @app.post("/setup", response_class=HTMLResponse, name="cmail.setup_save")
    async def setup_save(request: Request):
        form = await request.form()
        supplied = str(form.get("csrf") or "")
        if not supplied or not secrets.compare_digest(supplied, setup_csrf(request)):
            return render_setup(
                request, "Sua sessão de configuração expirou. Recarregue a página e tente novamente.", 403
            )
        try:
            result = SetupService(config).save({key: str(value) for key, value in form.items()})
        except SetupError as error:
            return render_setup(request, str(error), 400)
        request.session.pop("cmail_setup_csrf", None)
        if restart_callback is not None:
            restart_callback()
        return TEMPLATES.TemplateResponse(
            request=request, name="setup_saved.html", status_code=202,
            context={
                "provider": result.provider, "account": result.account,
                "automatic": restart_callback is not None, "base_path": _base_path(request),
            },
        )

    @app.post("/auth/logout")
    async def logout(request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        if current.auth:
            current.auth.logout(str(request.cookies.get(SESSION_COOKIE) or ""))
        response = JSONResponse({"ok": True})
        root = _cookie_path(request)
        response.delete_cookie(SESSION_COOKIE, path=root)
        response.delete_cookie(CSRF_COOKIE, path=root)
        return response

    @app.post("/api/auth/disconnect")
    async def disconnect(request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        if current.auth is None:
            raise AuthenticationError("Conta OAuth não está conectada.")
        current.auth.disconnect(principal.identity_id)
        response = JSONResponse({"ok": True})
        root = _cookie_path(request)
        response.delete_cookie(SESSION_COOKIE, path=root)
        response.delete_cookie(CSRF_COOKIE, path=root)
        return response

    @app.get("/api/status")
    async def status(request: Request):
        return {"ok": True, **current.status(False, require_principal(request))}

    @app.get("/api/folders")
    async def folders(request: Request):
        return {"ok": True, "folders": current.folders(require_principal(request))}

    @app.get("/api/messages")
    async def messages(request: Request):
        folder = str(request.query_params.get("folder") or "INBOX")[:512]
        try:
            limit = min(100, max(1, int(request.query_params.get("limit") or 50)))
        except ValueError as error:
            raise ValueError("Limite inválido.") from error
        principal = require_principal(request)
        return {"ok": True, "folder": folder, "messages": current.messages(principal, folder, limit)}

    @app.get("/api/messages/{identifier}")
    async def message(identifier: str, request: Request):
        folder = str(request.query_params.get("folder") or "INBOX")[:512]
        return {"ok": True, "message": current.message(require_principal(request), folder, identifier)}

    @app.patch("/api/messages/{identifier}/read")
    async def message_read(identifier: str, request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        if not isinstance(value.get("isRead"), bool):
            raise ValueError("isRead deve ser booleano.")
        return {"ok": True, "message": current.set_read(principal, identifier, bool(value["isRead"]))}

    @app.post("/api/messages/{identifier}/move")
    async def message_move(identifier: str, request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        return {"ok": True, "message": current.move(principal, identifier, str(value.get("destinationId") or ""))}

    @app.post("/api/messages/{identifier}/reply")
    async def message_reply(identifier: str, request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        return {"ok": True, "result": current.reply(
            principal, identifier, str(value.get("comment") or ""),
            reply_all=value.get("replyAll") is True, confirmed=value.get("confirmed") is True,
        )}

    @app.post("/api/messages/{identifier}/forward")
    async def message_forward(identifier: str, request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        recipients = [str(item) for item in value.get("recipients", [])] if isinstance(value.get("recipients"), list) else []
        return {"ok": True, "result": current.forward(
            principal, identifier, recipients, str(value.get("comment") or ""),
            confirmed=value.get("confirmed") is True,
        )}

    @app.get("/api/lists")
    async def lists(request: Request):
        return {"ok": True, "lists": current.lists(require_principal(request))}

    @app.post("/api/lists")
    async def save_list(request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        recipients = value.get("recipients") if isinstance(value.get("recipients"), list) else []
        return {"ok": True, "list": current.save_list(principal, str(value.get("name") or ""), recipients)}

    @app.post("/api/send/prepare")
    async def prepare(request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        return {"ok": True, "preview": current.prepare(await _payload(request), principal)}

    @app.post("/api/send/execute")
    async def execute(request: Request):
        principal = require_principal(request)
        require_csrf(request, principal)
        value = await _payload(request)
        if value.get("confirmed") is not True:
            raise ValueError("Envio exige confirmação explícita.")
        return {"ok": True, "result": current.execute(
            str(value.get("draftId") or ""), str(value.get("confirmationToken") or ""), principal
        )}

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        )
        return response

    @app.exception_handler(AuthenticationError)
    async def authentication_failure(request: Request, error: AuthenticationError):
        message = str(error)[:300]
        if request.url.path.startswith(f"{_base_path(request)}/api/"):
            return JSONResponse({"ok": False, "error": message}, status_code=401)
        account_mismatch = "não corresponde a esta instância" in message.casefold()
        base = _base_path(request)
        retry_path = "/auth/microsoft" if config.mode == "microsoft" else "/auth/google" if config.mode == "gmail" else "/"
        response = TEMPLATES.TemplateResponse(
            request=request, name="auth_error.html", status_code=401,
            context={
                "title": "Conta diferente da configurada" if account_mismatch else "Não foi possível entrar",
                "message": message, "retry_url": f"{base}{retry_path}",
                "setup_url": f"{base}/setup", "base_path": base,
            },
        )
        callback = "/auth/callback" if config.mode == "microsoft" else "/auth/google/callback" if config.mode == "gmail" else "/"
        response.delete_cookie(BROWSER_COOKIE, path=_cookie_path(request, callback))
        return response

    @app.exception_handler(PermissionError)
    async def permission_failure(request: Request, error: PermissionError):
        del request
        return JSONResponse({"ok": False, "error": str(error)}, status_code=403)

    @app.exception_handler(ValueError)
    async def validation_failure(request: Request, error: ValueError):
        del request
        return JSONResponse({"ok": False, "error": str(error)[:300]}, status_code=400)

    @app.exception_handler(Exception)
    async def failure(request: Request, error: Exception):
        LOGGER.exception("CMAIL request failed: %s", type(error).__name__)
        del request
        return JSONResponse({"ok": False, "error": "Falha interna do CMAIL."}, status_code=500)

    return app


def create_app(
    config: Config,
    service: MailService | None = None,
    *,
    url_prefix: str = "",
    restart_callback: Callable[[], None] | None = None,
) -> FastAPI:
    """Create a mountable CMAIL ASGI app or a prefixed standalone host."""
    module = _create_module_app(config, service, restart_callback=restart_callback)
    prefix = "/" + str(url_prefix or "").strip("/") if str(url_prefix or "").strip("/") else ""
    if not prefix:
        return module
    host = FastAPI(title="CMAIL host", docs_url=None, redoc_url=None, openapi_url=None)
    host.mount(prefix, module, name="cmail")
    return host


def create_component_app(
    agent_root: str | Path,
    host_services: Mapping[str, object] | None = None,
) -> FastAPI:
    """Entry-point factory used by generic ASGI hosts."""
    services = dict(host_services or {})
    config_file = services.get("configFile")
    config = (
        Config.from_file(Path(config_file), root=agent_root)
        if config_file is not None
        else Config.load(Path(agent_root))
    )
    return create_app(config)
