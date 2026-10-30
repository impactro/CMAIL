"""Calendar HTTP boundary; synchronous providers run in the worker pool."""
from fastapi import FastAPI, Request

from .web_context import WebContext


def register_calendar_routes(app: FastAPI, ctx: WebContext):
    @app.get('/api/calendars')
    def calendars(request: Request):
        return {'ok': True, 'calendars': ctx.service.calendars(ctx.principal(request))}

    @app.get('/api/calendar-view')
    def calendar_view(request: Request):
        return {'ok': True, 'events': ctx.service.calendar_view(
            ctx.principal(request), str(request.query_params.get('start') or ''),
            str(request.query_params.get('end') or ''),
            str(request.query_params.get('timeZone') or 'UTC'),
            calendar_id=str(request.query_params.get('calendarId') or ''),
            limit=min(200, max(1, int(request.query_params.get('limit') or 100))),
        )}

    @app.get('/api/events/{identifier}')
    def event(identifier: str, request: Request):
        return {'ok': True, 'event': ctx.service.event(ctx.principal(request), identifier)}

    @app.post('/api/events')
    async def event_create(request: Request):

        def perform(principal, value):
            event_value = value.get('event') if isinstance(value.get('event'), dict) else {}
            return {'ok': True, **ctx.service.create_event(
                principal, event_value, calendar_id=str(value.get('calendarId') or ''),
                confirmed=value.get('confirmed') is True,
            )}
        return await ctx.write(request, perform)

    @app.patch('/api/events/{identifier}')
    async def event_update(identifier: str, request: Request):

        def perform(principal, value):
            changes = value.get('changes') if isinstance(value.get('changes'), dict) else {}
            return {'ok': True, **ctx.service.update_event(
                principal, identifier, changes, confirmed=value.get('confirmed') is True,
            )}
        return await ctx.write(request, perform)

    @app.delete('/api/events/{identifier}')
    async def event_delete(identifier: str, request: Request):

        def perform(principal, value):
            return {'ok': True, **ctx.service.delete_event(
                principal, identifier, confirmed=value.get('confirmed') is True,
            )}
        return await ctx.write(request, perform)

    @app.post('/api/events/{identifier}/respond')
    async def event_respond(identifier: str, request: Request):

        def perform(principal, value):
            return {'ok': True, **ctx.service.respond_event(
                principal, identifier, str(value.get('response') or ''),
                comment=str(value.get('comment') or ''),
                send_response=value.get('sendResponse') is not False,
                confirmed=value.get('confirmed') is True,
            )}
        return await ctx.write(request, perform)
