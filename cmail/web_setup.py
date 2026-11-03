"""Standalone configuration routes."""
from __future__ import annotations

import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from .setup import SetupError, SetupService
from .configuration import ConfigurationConflict
from .web_context import base_path as _base_path


def register_setup_routes(app: FastAPI, ctx, security, templates, *, restart_callback=None,
                          setup_authorizer=None, setup_origin=''):
    current, config, principal_resolver = ctx.service, ctx.service.config, security.resolver
    TEMPLATES = templates
    setup_csrf = security.setup_csrf
    hosted = principal_resolver is not None

    def authorize(request):
        if not hosted:
            return
        if setup_authorizer is None:
            raise HTTPException(404, 'Página não encontrada.')
        from .web_security import _web_principal
        if _web_principal(current, request, principal_resolver) is None or setup_authorizer(request) is not True:
            raise HTTPException(403, 'Configuração exige administrador autenticado do host.')
        if config.mode != 'setup':
            raise HTTPException(409, 'Configuração inicial já concluída.')

    def setup_values() -> dict[str, object]:
        provider = (
            "outlook" if config.mode == "microsoft" else
            "gmail" if config.mode == "gmail" else
            "imap" if config.mode == "imap" else "outlook"
        )
        bound = None if config.mode == 'setup' else (
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
                "base_path": _base_path(request), "hosted": hosted,
                "setup_revision": config.source_revision,
                "google_callback": callback(request) if hosted else '',
            },
        )

    @app.get("/setup", response_class=HTMLResponse, name="cmail.setup")
    def setup_page(request: Request):
        authorize(request)
        return render_setup(request, str(request.query_params.get("error") or ""))

    def callback(request):
        from .hosted_setup import callback_uri
        return callback_uri(setup_origin, _base_path(request))

    async def hosted_form(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 98304:
                raise HTTPException(413, 'Formulário OAuth acima do limite.')
        async def receive():
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
        parsed = Request(request.scope, receive)
        return await parsed.form(max_files=1, max_fields=8)

    @app.post("/setup", response_class=HTMLResponse, name="cmail.setup_save")
    async def setup_save(request: Request):
        authorize(request)
        form = await hosted_form(request) if hosted else await request.form()
        supplied = str(form.get("csrf") or "")
        if not supplied or not secrets.compare_digest(supplied, setup_csrf(request)):
            await form.close()
            return render_setup(
                request, "Sua sessão de configuração expirou. Recarregue a página e tente novamente.", 403
            )
        try:
            if hosted:
                from .hosted_setup import save_initial_gmail
                from .setup import SetupResult
                upload = form.get('oauthClientFile')
                if (str(form.get('provider')) != 'gmail' or not hasattr(upload, 'read') or
                    set(form) - {'csrf', 'provider', 'revision', 'oauthClientFile'}):
                    raise SetupError('Carregue o JSON do cliente Google Web.')
                content = await upload.read(65537)
                await upload.close()
                await run_in_threadpool(save_initial_gmail, config, content, callback(request), str(form.get('revision', '')))
                result = SetupResult('gmail', 'Autorize sua conta Google após aplicar a configuração')
            else:
                result = await run_in_threadpool(SetupService(config).save, {key: str(value) for key, value in form.items()})
        except ConfigurationConflict:
            await form.close()
            return render_setup(request, 'Configuração mudou; recarregue o componente.', 409)
        except SetupError as error:
            await form.close()
            return render_setup(request, str(error), 400)
        await form.close()
        request.session.pop("cmail_setup_csrf", None)
        if restart_callback is not None and not hosted:
            restart_callback()
        return TEMPLATES.TemplateResponse(
            request=request, name="setup_saved.html", status_code=202,
            context={
                "provider": result.provider, "account": result.account,
                "automatic": restart_callback is not None and not hosted, "base_path": _base_path(request),
                "hosted": hosted,
            },
        )
