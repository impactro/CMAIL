"""Appearance HTTP boundary and authenticated, transient preview documents."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from .service import SEND_MAIL
from .web_context import WebContext


def register_appearance_routes(app: FastAPI, ctx: WebContext):
    @app.get('/api/appearance')
    def appearance_settings(request: Request):
        return {'ok': True, **ctx.service.appearance_settings(ctx.principal(request))}

    @app.put('/api/appearance')
    async def appearance_save(request: Request):
        return await ctx.write(request, lambda principal, value:
            {'ok': True, **ctx.service.save_appearance(principal, value)})

    @app.post('/api/appearance/preview')
    async def appearance_preview(request: Request):
        def perform(principal, value):
            packet = ctx.service.render_appearance(principal, value, profile=value.get('profile'))
            return {'ok': True, 'previewUrl': ctx.preview_url(request, principal, packet),
                    'sources': packet['appearanceSources']}

        return await ctx.write(request, perform)

    @app.get('/api/appearance/previews/{token}', response_class=HTMLResponse)
    def appearance_preview_document(token: str, request: Request):
        principal = ctx.principal(request)
        principal.require(SEND_MAIL)
        content = ctx.previews.get(principal.storage_owner, token)
        if content is None:
            raise HTTPException(404, 'Prévia ausente ou expirada.')
        return HTMLResponse(content, headers={'Content-Security-Policy':
            "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox; frame-ancestors 'self'"})
