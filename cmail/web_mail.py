"""Mailbox, contacts, lists and confirmed sends."""
from fastapi import FastAPI, Request

from .web_context import WebContext


def register_mail_routes(app: FastAPI, ctx: WebContext):
    @app.get('/api/status')
    def status(request: Request):
        return {'ok': True, **ctx.service.status(False, ctx.principal(request))}

    @app.get('/api/folders')
    def folders(request: Request):
        return {'ok': True, 'folders': ctx.service.folders(ctx.principal(request))}

    @app.get('/api/message-actions')
    def message_actions(request: Request):
        return {'ok': True, 'actions': ctx.service.message_actions(ctx.principal(request))}

    @app.get('/api/messages')
    def messages(request: Request):
        folder = str(request.query_params.get('folder') or 'INBOX')[:512]
        try:
            limit = min(100, max(1, int(request.query_params.get('limit') or 50)))
        except ValueError as error:
            raise ValueError('Limite inválido.') from error
        principal = ctx.principal(request)
        return {'ok': True, 'folder': folder, 'messages': ctx.service.messages(principal, folder, limit)}

    @app.get('/api/messages/{identifier}')
    def message(identifier: str, request: Request):
        folder = str(request.query_params.get('folder') or 'INBOX')[:512]
        return {'ok': True, 'message': ctx.service.message(ctx.principal(request), folder, identifier)}

    @app.patch('/api/messages/{identifier}/read')
    async def message_read(identifier: str, request: Request):

        def perform(principal, value):
            if not isinstance(value.get('isRead'), bool):
                raise ValueError('isRead deve ser booleano.')
            folder = str(value.get('folder') or 'INBOX')[:512]
            return {'ok': True, 'message': ctx.service.set_read(
                principal, identifier, bool(value['isRead']), folder=folder,
            )}
        return await ctx.write(request, perform)

    @app.post('/api/messages/{identifier}/move')
    async def message_move(identifier: str, request: Request):

        def perform(principal, value):
            folder = str(value.get('folder') or 'INBOX')[:512]
            return {'ok': True, 'message': ctx.service.move(
                principal, identifier, str(value.get('destinationId') or ''), folder=folder,
            )}
        return await ctx.write(request, perform)

    @app.post('/api/messages/{identifier}/reply')
    async def message_reply(identifier: str, request: Request):

        def perform(principal, value):
            return {'ok': True, 'result': ctx.service.reply(
                principal, identifier, str(value.get('comment') or ''),
                reply_all=value.get('replyAll') is True,
                confirmed=value.get('confirmed') is True,
                folder=str(value.get('folder') or 'INBOX')[:512],
            )}
        return await ctx.write(request, perform)

    @app.post('/api/messages/{identifier}/trash')
    async def message_trash(identifier: str, request: Request):

        def perform(principal, value):
            return {'ok': True, 'message': ctx.service.trash_message(
                principal, identifier, folder=str(value.get('folder') or 'INBOX')[:512],
            )}
        return await ctx.write(request, perform)

    @app.post('/api/messages/{identifier}/delete-permanently')
    async def message_delete_permanently(identifier: str, request: Request):

        def perform(principal, value):
            return {'ok': True, 'message': ctx.service.delete_permanently(
                principal, identifier, folder=str(value.get('folder') or '')[:512],
                confirmed=value.get('confirmed') is True,
            )}
        return await ctx.write(request, perform)

    @app.post('/api/messages/{identifier}/forward')
    async def message_forward(identifier: str, request: Request):

        def perform(principal, value):
            recipients = [str(item) for item in value.get('recipients', [])] if isinstance(value.get('recipients'), list) else []
            return {'ok': True, 'result': ctx.service.forward(
                principal, identifier, recipients, str(value.get('comment') or ''),
                confirmed=value.get('confirmed') is True,
                folder=str(value.get('folder') or 'INBOX')[:512],
            )}
        return await ctx.write(request, perform)

    @app.get('/api/messages/{identifier}/attachments')
    def message_attachments(identifier: str, request: Request):
        return {'ok': True, 'attachments': ctx.service.attachments(ctx.principal(request), identifier)}

    @app.get('/api/messages/{identifier}/attachments/{attachment_id}')
    def message_attachment(identifier: str, attachment_id: str, request: Request):
        return {'ok': True, 'attachment': ctx.service.attachment(ctx.principal(request), identifier, attachment_id)}

    @app.get('/api/contacts')
    def contacts(request: Request):
        query = str(request.query_params.get('q') or '')
        limit = min(100, max(1, int(request.query_params.get('limit') or 25)))
        return {'ok': True, 'contacts': ctx.service.contacts(ctx.principal(request), query, limit)}

    @app.get('/api/directory')
    def directory(request: Request):
        query = str(request.query_params.get('q') or '')
        limit = min(50, max(1, int(request.query_params.get('limit') or 20)))
        return {'ok': True, 'people': ctx.service.directory(ctx.principal(request), query, limit)}

    @app.get('/api/lists')
    def lists(request: Request):
        return {'ok': True, 'lists': ctx.service.lists(ctx.principal(request))}

    @app.post('/api/lists')
    async def save_list(request: Request):

        def perform(principal, value):
            recipients = value.get('recipients') if isinstance(value.get('recipients'), list) else []
            return {'ok': True, 'list': ctx.service.save_list(principal, str(value.get('name') or ''), recipients)}
        return await ctx.write(request, perform)

    @app.post('/api/send/execute')
    async def execute(request: Request):

        def perform(principal, value):
            if value.get('confirmed') is not True:
                raise ValueError('Envio exige confirmação explícita.')
            return {'ok': True, 'result': ctx.service.execute(
                str(value.get('draftId') or ''), str(value.get('confirmationToken') or ''),
                principal,
            )}
        return await ctx.write(request, perform)

    def prepared(request, principal, result):
        return {'ok': True, 'preview': result,
                'previewUrl': ctx.preview_url(request, principal, result['preview'])}

    @app.post('/api/send/prepare')
    async def prepare(request: Request):
        return await ctx.write(request, lambda principal, value:
            prepared(request, principal, ctx.service.prepare(value, principal)))

    @app.post('/api/messages/{identifier}/prepare')
    async def prepare_message_action(identifier: str, request: Request):
        return await ctx.write(request, lambda principal, value:
            prepared(request, principal, ctx.service.prepare_message_action(principal, identifier, value)))
