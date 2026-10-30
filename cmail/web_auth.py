"""OAuth, session and initial webmail routes."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import __version__
from .auth import AuthenticationError
from .web_context import base_path as _base_path, module_path as _module_path
from .web_security import SESSION_COOKIE, CSRF_COOKIE, BROWSER_COOKIE, _web_principal

_cookie_path = _module_path


def register_auth_routes(app: FastAPI, ctx, security, templates, *, oauth_success_path=''):
    current, config, principal_resolver = ctx.service, ctx.service.config, security.resolver
    TEMPLATES = templates
    csrf = security.csrf
    require_principal, require_csrf = security.require_principal, security.require_csrf

    @app.get("/", response_class=HTMLResponse, name="cmail.index")
    def index(request: Request):
        if config.mode == "setup":
            return RedirectResponse(_module_path(request, "/setup"), status_code=303)
        principal = _web_principal(current, request, principal_resolver)
        owner_id = principal.storage_owner if principal else ""
        webmail_enabled = (
            current.store.webmail_enabled(owner_id)
            if principal_resolver is not None and owner_id else True
        )
        connected = bool(
            principal
            and (config.mode not in {"microsoft", "gmail"} or principal.identity_id)
        )
        if principal_resolver is None and config.mode == "microsoft" and not connected:
            return RedirectResponse(_module_path(request, "/auth/microsoft"), status_code=303)
        if principal_resolver is None and config.mode == "gmail" and not connected:
            return RedirectResponse(_module_path(request, "/auth/google"), status_code=303)
        auth_state = "demo" if config.mode == "demo" else "connected" if connected else "disconnected"
        if principal_resolver is not None and principal:
            auth_state = str(current.connection_status(principal.storage_owner)["state"])
        elif config.mode in {"microsoft", "gmail"} and not connected and current.auth:
            if current.auth.session_identity(str(request.cookies.get(SESSION_COOKIE) or "")):
                auth_state = "reauthorize"
        return TEMPLATES.TemplateResponse(
            request=request, name="index.html",
            context={
                "csrf": csrf(request, principal),
                "authenticated": connected and webmail_enabled,
                "identity": {"email": principal.email} if principal else None,
                "mode": config.mode, "auth_state": auth_state,
                "base_path": _base_path(request), "embedded": principal_resolver is not None,
                "webmail_enabled": webmail_enabled,
            },
        )

    @app.get("/health")
    async def health():
        return {
            "ok": True, "component": "cmail", "mode": config.mode,
            "configured": config.mode != "setup",
            "singleAccount": principal_resolver is None,
            "workspaceIsolated": principal_resolver is not None,
            "version": __version__, "framework": "fastapi",
        }

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        principal = _web_principal(current, request, principal_resolver)
        connected = bool(
            principal
            and (config.mode not in {"microsoft", "gmail"} or principal.identity_id)
        )
        return {
            "ok": True, "required": config.mode in {"microsoft", "gmail"},
            "authenticated": connected,
            "identity": {"email": principal.email} if principal else None,
            "connection": (
                current.connection_status(principal.storage_owner)
                if principal_resolver is not None and principal else None
            ),
        }

    def begin_oauth(request: Request, provider: str):
        if config.mode != provider or current.auth is None:
            raise AuthenticationError("Login OAuth não está habilitado.")
        host_principal = (
            _web_principal(current, request, principal_resolver)
            if principal_resolver is not None else None
        )
        owner_id = host_principal.storage_owner if host_principal else ""
        url, browser_nonce = current.auth.begin(owner_id)
        response = RedirectResponse(url, status_code=302)
        callback = "/auth/callback" if provider == "microsoft" else "/auth/google/callback"
        response.set_cookie(
            BROWSER_COOKIE, browser_nonce, httponly=True, secure=config.cookie_secure,
            samesite="lax", max_age=600, path=_cookie_path(request, callback),
        )
        return response

    @app.get("/auth/microsoft", name="cmail.microsoft_login")
    def microsoft_login(request: Request):
        return begin_oauth(request, "microsoft")

    @app.get("/auth/google", name="cmail.google_login")
    def google_login(request: Request):
        return begin_oauth(request, "gmail")

    def complete_oauth(request: Request, callback: str):
        if current.auth is None:
            raise AuthenticationError("Login OAuth não está habilitado.")
        response_values = {key: str(value) for key, value in request.query_params.items()}
        host_principal = (
            _web_principal(current, request, principal_resolver)
            if principal_resolver is not None else None
        )
        owner_id = host_principal.storage_owner if host_principal else ""
        session_token, csrf_token, _identity = current.auth.complete(
            response_values,
            str(request.cookies.get(BROWSER_COOKIE) or ""),
            owner_id,
        )
        destination = oauth_success_path if principal_resolver is not None and oauth_success_path else _module_path(request)
        response = RedirectResponse(destination, status_code=303)
        root = _cookie_path(request)
        if principal_resolver is None:
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
    def google_callback(request: Request):
        if config.mode != "gmail":
            raise AuthenticationError("Login Google não está habilitado.")
        return complete_oauth(request, "/auth/google/callback")

    @app.get("/auth/callback", name="cmail.microsoft_callback")
    def microsoft_callback(request: Request):
        if config.mode != "microsoft":
            raise AuthenticationError("Login Microsoft não está habilitado.")
        return complete_oauth(request, "/auth/callback")

    @app.post("/auth/logout")
    def logout(request: Request):
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
    def disconnect(request: Request):
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
