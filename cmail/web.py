"""Factory Flask/Blueprint do webmail individual CMAIL."""

from __future__ import annotations

import secrets
from functools import wraps
from typing import Callable

from flask import Blueprint, Flask, Response, abort, jsonify, make_response, redirect, render_template, request, session, url_for

from .auth import AuthenticationError
from . import __version__
from .config import Config, ConfigError
from .service import MANAGE_LISTS, MANAGE_MAIL, READ_MAIL, SEND_MAIL, MailService, Principal
from .setup import SetupError, SetupService


SESSION_COOKIE = "cmail_session"
CSRF_COOKIE = "cmail_csrf"
BROWSER_COOKIE = "cmail_oauth_browser"


def _web_principal(service: MailService) -> Principal | None:
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


def create_blueprint(
    config: Config, service: MailService | None = None,
    *, restart_callback: Callable[[], None] | None = None,
) -> Blueprint:
    """Expõe o CMAIL para app Flask próprio ou host consumidor."""
    current = service or MailService(config)
    app = Blueprint(
        "cmail", __name__, template_folder="templates", static_folder="static", static_url_path="/static"
    )

    def csrf(principal: Principal | None) -> str:
        if config.mode in {"demo", "imap", "setup"}:
            return session.setdefault("cmail_csrf", secrets.token_urlsafe(24))
        return str(request.cookies.get(CSRF_COOKIE) or "") if principal else ""

    def require_principal() -> Principal:
        principal = _web_principal(current)
        if principal is None:
            raise AuthenticationError("Autentique a conta de e-mail desta instância.")
        return principal

    def require_csrf(principal: Principal) -> None:
        supplied = str(request.headers.get("X-CSRF-Token") or "")
        if config.mode in {"demo", "imap", "setup"}:
            if not supplied or not secrets.compare_digest(supplied, csrf(principal)):
                raise PermissionError("CSRF_INVALID")
            return
        identity = current.auth.current(str(request.cookies.get(SESSION_COOKIE) or "")) if current.auth else None
        if not identity or not current.store.csrf_valid(identity, supplied):
            raise PermissionError("CSRF_INVALID")

    def protected(effect: bool = False) -> Callable:
        def decorate(function: Callable) -> Callable:
            @wraps(function)
            def wrapped(*args, **kwargs):
                principal = require_principal()
                if effect:
                    require_csrf(principal)
                return function(principal, *args, **kwargs)
            return wrapped
        return decorate

    def payload() -> dict[str, object]:
        value = request.get_json(force=True, silent=False)
        if not isinstance(value, dict):
            raise ValueError("JSON deve ser um objeto.")
        return value

    @app.get("/")
    def index():
        if config.mode == "setup":
            return redirect(url_for("cmail.setup_page"))
        principal = _web_principal(current)
        if config.mode == "microsoft" and principal is None:
            return redirect(url_for("cmail.microsoft_login"))
        if config.mode == "gmail" and principal is None:
            return redirect(url_for("cmail.google_login"))
        auth_state = "demo" if config.mode == "demo" else "connected" if principal else "disconnected"
        if config.mode in {"microsoft", "gmail"} and principal is None and current.auth:
            stale = current.auth.session_identity(str(request.cookies.get(SESSION_COOKIE) or ""))
            if stale:
                auth_state = "reauthorize"
        return render_template(
            "index.html", csrf=csrf(principal), authenticated=principal is not None,
            identity={"email": principal.email} if principal else None, mode=config.mode,
            auth_state=auth_state,
        )

    @app.get("/health")
    def health():
        return {
            "ok": True, "component": "cmail", "mode": config.mode,
            "configured": config.mode != "setup", "singleAccount": True,
            "version": __version__,
        }

    @app.get("/api/auth/status")
    def auth_status():
        principal = _web_principal(current)
        return jsonify({
            "ok": True, "required": config.mode in {"microsoft", "gmail"},
            "authenticated": principal is not None,
            "identity": {"email": principal.email} if principal else None,
        })

    @app.get("/auth/microsoft")
    def microsoft_login():
        if config.mode != "microsoft" or current.auth is None:
            raise AuthenticationError("Login Microsoft não está habilitado.")
        url, browser_nonce = current.auth.begin()
        response = make_response(redirect(url, code=302))
        callback_path = url_for("cmail.microsoft_callback")
        response.set_cookie(
            BROWSER_COOKIE, browser_nonce, httponly=True, secure=config.cookie_secure,
            samesite="Lax", max_age=600, path=callback_path,
        )
        return response

    @app.get("/auth/google")
    def google_login():
        if config.mode != "gmail" or current.auth is None:
            raise AuthenticationError("Login Google não está habilitado.")
        url, browser_nonce = current.auth.begin()
        response = make_response(redirect(url, code=302))
        callback_path = url_for("cmail.google_callback")
        response.set_cookie(
            BROWSER_COOKIE, browser_nonce, httponly=True, secure=config.cookie_secure,
            samesite="Lax", max_age=600, path=callback_path,
        )
        return response

    def complete_oauth(callback_path: str):
        if current.auth is None:
            raise AuthenticationError("Login OAuth não está habilitado.")
        response_values = {key: str(value) for key, value in request.args.items()}
        session_token, csrf_token, _identity = current.auth.complete(
            response_values, str(request.cookies.get(BROWSER_COOKIE) or "")
        )
        response = make_response(redirect(url_for("cmail.index"), code=303))
        root_path = url_for("cmail.index")
        response.set_cookie(
            SESSION_COOKIE, session_token, httponly=True, secure=config.cookie_secure,
            samesite="Lax", max_age=config.session_hours * 3600, path=root_path,
        )
        response.set_cookie(
            CSRF_COOKIE, csrf_token, httponly=False, secure=config.cookie_secure,
            samesite="Strict", max_age=config.session_hours * 3600, path=root_path,
        )
        response.delete_cookie(BROWSER_COOKIE, path=callback_path)
        return response

    @app.get("/auth/google/callback")
    def google_callback():
        if config.mode != "gmail":
            raise AuthenticationError("Login Google não está habilitado.")
        return complete_oauth(url_for("cmail.google_callback"))

    @app.get("/setup")
    def setup_page():
        return render_template(
            "setup.html", csrf=csrf(None), port=config.port,
            error=str(request.args.get("error") or "")[:240],
        )

    @app.post("/setup")
    def setup_save():
        supplied = str(request.form.get("csrf") or "")
        if not supplied or not secrets.compare_digest(supplied, csrf(None)):
            raise PermissionError("CSRF_INVALID")
        try:
            result = SetupService(config).save(
                {key: str(value) for key, value in request.form.items()}
            )
        except SetupError as error:
            return render_template(
                "setup.html", csrf=csrf(None), port=config.port, error=str(error)[:240],
            ), 400
        if restart_callback is not None:
            restart_callback()
        return render_template(
            "setup_saved.html", provider=result.provider, account=result.account,
            automatic=restart_callback is not None,
        ), 202

    @app.get("/auth/microsoft/callback")
    def microsoft_callback():
        if current.auth is None:
            raise AuthenticationError("Login Microsoft não está habilitado.")
        response_values = {key: str(value) for key, value in request.args.items()}
        session_token, csrf_token, _identity = current.auth.complete(
            response_values, str(request.cookies.get(BROWSER_COOKIE) or "")
        )
        response = make_response(redirect(url_for("cmail.index"), code=303))
        root_path = url_for("cmail.index")
        callback_path = url_for("cmail.microsoft_callback")
        response.set_cookie(
            SESSION_COOKIE, session_token, httponly=True, secure=config.cookie_secure,
            samesite="Lax", max_age=config.session_hours * 3600, path=root_path,
        )
        response.set_cookie(
            CSRF_COOKIE, csrf_token, httponly=False, secure=config.cookie_secure,
            samesite="Strict", max_age=config.session_hours * 3600, path=root_path,
        )
        response.delete_cookie(BROWSER_COOKIE, path=callback_path)
        return response

    @app.post("/auth/logout")
    @protected(effect=True)
    def logout(principal: Principal):
        del principal
        if current.auth:
            current.auth.logout(str(request.cookies.get(SESSION_COOKIE) or ""))
        response = make_response(jsonify({"ok": True}))
        root_path = url_for("cmail.index")
        response.delete_cookie(SESSION_COOKIE, path=root_path)
        response.delete_cookie(CSRF_COOKIE, path=root_path)
        return response

    @app.post("/api/auth/disconnect")
    @protected(effect=True)
    def disconnect(principal: Principal):
        if current.auth is None:
            raise AuthenticationError("Conta OAuth não está conectada.")
        current.auth.disconnect(principal.identity_id)
        response = make_response(jsonify({"ok": True}))
        root_path = url_for("cmail.index")
        response.delete_cookie(SESSION_COOKIE, path=root_path)
        response.delete_cookie(CSRF_COOKIE, path=root_path)
        return response

    @app.get("/api/status")
    @protected()
    def status(principal: Principal):
        return jsonify({"ok": True, **current.status(False, principal)})

    @app.get("/api/folders")
    @protected()
    def folders(principal: Principal):
        return jsonify({"ok": True, "folders": current.folders(principal)})

    @app.get("/api/messages")
    @protected()
    def messages(principal: Principal):
        folder = str(request.args.get("folder") or "INBOX")[:512]
        try:
            limit = min(100, max(1, int(request.args.get("limit") or 50)))
        except ValueError as exc:
            raise ValueError("Limite inválido.") from exc
        return jsonify({"ok": True, "folder": folder, "messages": current.messages(principal, folder, limit)})

    @app.get("/api/messages/<identifier>")
    @protected()
    def message(principal: Principal, identifier: str):
        folder = str(request.args.get("folder") or "INBOX")[:512]
        return jsonify({"ok": True, "message": current.message(principal, folder, identifier)})

    @app.patch("/api/messages/<identifier>/read")
    @protected(effect=True)
    def message_read(principal: Principal, identifier: str):
        value = payload()
        if not isinstance(value.get("isRead"), bool):
            raise ValueError("isRead deve ser booleano.")
        return jsonify({"ok": True, "message": current.set_read(principal, identifier, bool(value["isRead"]))})

    @app.post("/api/messages/<identifier>/move")
    @protected(effect=True)
    def message_move(principal: Principal, identifier: str):
        value = payload()
        return jsonify({"ok": True, "message": current.move(principal, identifier, str(value.get("destinationId") or ""))})

    @app.post("/api/messages/<identifier>/reply")
    @protected(effect=True)
    def message_reply(principal: Principal, identifier: str):
        value = payload()
        return jsonify({"ok": True, "result": current.reply(
            principal, identifier, str(value.get("comment") or ""),
            reply_all=value.get("replyAll") is True, confirmed=value.get("confirmed") is True,
        )})

    @app.post("/api/messages/<identifier>/forward")
    @protected(effect=True)
    def message_forward(principal: Principal, identifier: str):
        value = payload()
        recipients = [str(item) for item in value.get("recipients", [])] if isinstance(value.get("recipients"), list) else []
        return jsonify({"ok": True, "result": current.forward(
            principal, identifier, recipients, str(value.get("comment") or ""),
            confirmed=value.get("confirmed") is True,
        )})

    @app.get("/api/lists")
    @protected()
    def lists(principal: Principal):
        return jsonify({"ok": True, "lists": current.lists(principal)})

    @app.post("/api/lists")
    @protected(effect=True)
    def save_list(principal: Principal):
        value = payload()
        recipients = value.get("recipients") if isinstance(value.get("recipients"), list) else []
        return jsonify({"ok": True, "list": current.save_list(principal, str(value.get("name") or ""), recipients)})

    @app.post("/api/send/prepare")
    @protected(effect=True)
    def prepare(principal: Principal):
        return jsonify({"ok": True, "preview": current.prepare(payload(), principal)})

    @app.post("/api/send/execute")
    @protected(effect=True)
    def execute(principal: Principal):
        value = payload()
        if value.get("confirmed") is not True:
            raise ValueError("Envio exige confirmação explícita.")
        return jsonify({"ok": True, "result": current.execute(
            str(value.get("draftId") or ""), str(value.get("confirmationToken") or ""), principal
        )})

    @app.after_request
    def security_headers(response: Response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        )
        return response

    @app.errorhandler(AuthenticationError)
    def authentication_failure(error: AuthenticationError):
        return jsonify({"ok": False, "error": str(error)}), 401

    @app.errorhandler(PermissionError)
    def permission_failure(error: PermissionError):
        return jsonify({"ok": False, "error": str(error)}), 403

    @app.errorhandler(ValueError)
    def validation_failure(error: ValueError):
        return jsonify({"ok": False, "error": str(error)[:300]}), 400

    @app.errorhandler(Exception)
    def failure(error: Exception):
        app.logger.exception("CMAIL request failed: %s", type(error).__name__)
        return jsonify({"ok": False, "error": "Falha interna do CMAIL."}), 500

    return app


def create_app(
    config: Config, service: MailService | None = None, *, url_prefix: str = "",
    restart_callback: Callable[[], None] | None = None,
) -> Flask:
    """Cria aplicação standalone; hosts Flask podem registrar o Blueprint diretamente."""
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_bytes(32), SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=config.cookie_secure,
    )
    app.register_blueprint(
        create_blueprint(config, service, restart_callback=restart_callback),
        url_prefix=url_prefix,
    )
    return app
