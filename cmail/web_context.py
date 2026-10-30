"""Shared HTTP boundary: identity, CSRF, bounded input and sync work off the loop."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .appearance import preview_html
from .preview_cache import PreviewCache
from .service import MailService, Principal

MAX_REQUEST_BYTES = 8 * 1024 * 1024


def base_path(request: Request) -> str:
    return str(request.scope.get('root_path') or '').rstrip('/')


def module_path(request: Request, suffix='/') -> str:
    return f'{base_path(request)}{suffix}' or '/'


async def read_payload(request: Request) -> dict[str, object]:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise ValueError('JSON excede o limite de oito MiB.')
        body.extend(chunk)
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError('JSON deve ser um objeto.')
    return value


@dataclass(frozen=True)
class WebContext:
    service: MailService
    principal: Callable[[Request], Principal]
    csrf: Callable[[Request, Principal], None]
    previews: PreviewCache

    async def write(self, request: Request, operation):
        def authorize():
            selected = self.principal(request)
            self.csrf(request, selected)
            return selected

        selected = await run_in_threadpool(authorize)
        value = await read_payload(request)
        return await run_in_threadpool(operation, selected, value)

    def preview_url(self, request, principal, packet):
        token = self.previews.put(principal.storage_owner, preview_html(packet))
        return module_path(request, '/api/appearance/previews/' + token)
