"""Interface Flask individual do CMAIL."""

from __future__ import annotations

import secrets

from flask import Flask, jsonify, render_template, request, session

from .config import Config
from .service import MailService


def create_app(config: Config, service: MailService | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_bytes(32), SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict")
    current = service or MailService(config)

    def csrf() -> str:
        return session.setdefault("csrf", secrets.token_urlsafe(24))

    def require_csrf() -> None:
        if not secrets.compare_digest(str(request.headers.get("X-CSRF-Token") or ""), csrf()):
            raise ValueError("CSRF_INVALID")

    @app.get("/")
    def index(): return render_template("index.html", csrf=csrf())

    @app.get("/health")
    def health(): return {"ok": True, "component": "cmail", "mode": config.mode}

    @app.get("/api/status")
    def status(): return jsonify({"ok": True, **current.status(False)})

    @app.get("/api/folders")
    def folders(): return jsonify({"ok": True, "folders": current.provider.folders()})

    @app.get("/api/messages")
    def messages():
        folder = str(request.args.get("folder") or "INBOX")[:200]
        limit = min(100, max(1, int(request.args.get("limit") or 50)))
        return jsonify({"ok": True, "folder": folder, "messages": current.provider.messages(folder, limit)})

    @app.get("/api/messages/<identifier>")
    def message(identifier: str):
        folder = str(request.args.get("folder") or "INBOX")[:200]
        return jsonify({"ok": True, "message": current.provider.message(folder, identifier)})

    @app.get("/api/lists")
    def lists(): return jsonify({"ok": True, "lists": current.store.lists()})

    @app.post("/api/lists")
    def save_list():
        require_csrf()
        payload = request.get_json(force=True, silent=False)
        return jsonify({"ok": True, "list": current.store.save_list(str(payload.get("name") or ""), payload.get("recipients") or [])})

    @app.post("/api/send/prepare")
    def prepare():
        require_csrf()
        return jsonify({"ok": True, "preview": current.prepare(request.get_json(force=True, silent=False))})

    @app.post("/api/send/execute")
    def execute():
        require_csrf()
        payload = request.get_json(force=True, silent=False)
        if payload.get("confirmed") is not True:
            raise ValueError("Envio exige confirmação explícita.")
        return jsonify({"ok": True, "result": current.execute(str(payload.get("draftId") or ""), str(payload.get("confirmationToken") or ""))})

    @app.errorhandler(Exception)
    def failure(error: Exception):
        app.logger.exception("CMAIL request failed")
        return jsonify({"ok": False, "error": str(error)[:300]}), 400

    return app
