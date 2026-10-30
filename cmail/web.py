"""FastAPI/ASGI application factory for standalone and embedded CMAIL."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import AuthenticationError, MICROSOFT_STATE_PREFIX
from .config import Config
from .service import MailService
from .preview_cache import PreviewCache
from .web_context import WebContext, base_path as _base_path, module_path as _module_path
from .web_security import WebSecurity, HostPrincipalResolver, BROWSER_COOKIE
from .web_security import SESSION_COOKIE, CSRF_COOKIE, _web_principal
from .web_auth import register_auth_routes
from .web_setup import register_setup_routes

from .web_mail import register_mail_routes
from .web_calendar import register_calendar_routes
from .web_appearance import register_appearance_routes
from .appearance import Appearance


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
LOGGER = logging.getLogger(__name__)
_cookie_path = _module_path


def _create_module_app(
    config: Config,
    service: MailService | None = None,
    *,
    restart_callback: Callable[[], None] | None = None,
    principal_resolver: HostPrincipalResolver | None = None,
    oauth_success_path: str = "",
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
    previews = PreviewCache()
    app.state.preview_cache = previews


    security = WebSecurity(current, principal_resolver)
    context = WebContext(current, security.require_principal, security.require_csrf, previews)
    register_auth_routes(app, context, security, TEMPLATES, oauth_success_path=oauth_success_path)
    register_setup_routes(app, context, security, TEMPLATES, restart_callback=restart_callback)
    register_mail_routes(app, context)
    register_calendar_routes(app, context)
    register_appearance_routes(app, context)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        ))
        return response

    @app.exception_handler(AuthenticationError)
    async def authentication_failure(request: Request, error: AuthenticationError):
        message = str(error)[:300]
        if request.url.path.startswith(f"{_base_path(request)}/api/"):
            reconnect = error.requires_reconnect
            retry = '/auth/google' if config.mode == 'gmail' else '/auth/microsoft'
            return JSONResponse({'ok': False, 'error': message, 'requiresReconnect': reconnect,
                'state': 'reauthorize' if reconnect else 'unavailable',
                'reauthorizeUrl': _module_path(request, retry) if reconnect else ''}, status_code=401)
        account_mismatch = "não corresponde a esta instância" in message.casefold()
        base = _base_path(request)
        retry_path = "/auth/microsoft" if config.mode == "microsoft" else "/auth/google" if config.mode == "gmail" else "/"
        response = TEMPLATES.TemplateResponse(
            request=request, name="auth_error.html", status_code=401,
            context={
                "title": "Conta diferente da configurada" if account_mismatch else "Não foi possível entrar",
                "message": message, "retry_url": f"{base}{retry_path}",
                "setup_url": f"{base}/setup", "base_path": base,
                "embedded": principal_resolver is not None,
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
    principal_resolver: HostPrincipalResolver | None = None,
    oauth_success_path: str = "",
) -> FastAPI:
    """Create a mountable CMAIL ASGI app or a prefixed standalone host."""
    if config.mode == "gmail-file":
        raise ValueError("gmail-file é headless: use CLI ou API Python local.")
    module = _create_module_app(
        config,
        service,
        restart_callback=restart_callback,
        principal_resolver=principal_resolver,
        oauth_success_path=oauth_success_path,
    )
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
    workspace_resolver = services.get('mailWorkspaceRootResolver')
    if workspace_resolver is not None and not callable(workspace_resolver):
        raise ValueError('mailWorkspaceRootResolver deve ser chamável.')
    config_file = services.get("configFile")
    config = (
        Config.from_file(Path(config_file), root=agent_root)
        if config_file is not None
        else Config.load(Path(agent_root))
    )
    resolvers = services.get("principalResolvers")
    resolver = (
        resolvers.get("cmail")
        if isinstance(resolvers, Mapping) else services.get("principalResolver")
    )
    if resolver is not None and not callable(resolver):
        raise ValueError("principalResolver do CMAIL deve ser chamável.")
    callback_registrar = services.get("registerOAuthCallback")
    if callback_registrar is not None and not callable(callback_registrar):
        raise ValueError("registerOAuthCallback do host deve ser chamável.")
    if (
        callable(callback_registrar)
        and resolver is not None
        and config.mode == "microsoft"
        and urlparse(config.microsoft_redirect_uri).path == "/auth/callback"
    ):
        callback_registrar(
            component_id="cmail",
            state_prefix=MICROSOFT_STATE_PREFIX,
            callback_path="/cm/cmail/auth/callback",
        )
    oauth_success_path = str(services.get("oauthSuccessPath") or "").strip()
    parsed_success = urlparse(oauth_success_path)
    if oauth_success_path and (
        not oauth_success_path.startswith("/") or oauth_success_path.startswith("//")
        or parsed_success.scheme or parsed_success.netloc
    ):
        raise ValueError("oauthSuccessPath do host deve ser um caminho relativo à origem.")
    return create_app(
        config,
        service=MailService(config, appearance=Appearance(
            config.root, config.state_dir, company_root=services.get('mailCompanyRoot'),
            workspace_resolver=services.get('mailWorkspaceRootResolver'),
        )),
        principal_resolver=resolver,
        oauth_success_path=oauth_success_path,
    )
