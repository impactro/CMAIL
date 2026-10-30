"""Standalone configuration routes."""
from __future__ import annotations

import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from .setup import SetupError, SetupService
from .web_context import base_path as _base_path


def register_setup_routes(app: FastAPI, ctx, security, templates, *, restart_callback=None):
    current, config, principal_resolver = ctx.service, ctx.service.config, security.resolver
    TEMPLATES = templates
    setup_csrf = security.setup_csrf

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

    @app.get("/setup", response_class=HTMLResponse, name="cmail.setup")
    def setup_page(request: Request):
        if principal_resolver is not None:
            raise HTTPException(404, "Página não encontrada.")
        return render_setup(request, str(request.query_params.get("error") or ""))

    @app.post("/setup", response_class=HTMLResponse, name="cmail.setup_save")
    async def setup_save(request: Request):
        if principal_resolver is not None:
            raise HTTPException(404, "Página não encontrada.")
        form = await request.form()
        supplied = str(form.get("csrf") or "")
        if not supplied or not secrets.compare_digest(supplied, setup_csrf(request)):
            return render_setup(
                request, "Sua sessão de configuração expirou. Recarregue a página e tente novamente.", 403
            )
        try:
            result = await run_in_threadpool(SetupService(config).save, {key: str(value) for key, value in form.items()})
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
