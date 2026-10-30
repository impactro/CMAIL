"""Bounded Microsoft Graph HTTP transport and route policy."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .mail import MailError
from .http_io import read_limited, GRAPH_RESPONSE_BYTES, ERROR_RESPONSE_BYTES

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
GraphRequester = Callable[[str, str, str, dict[str, object] | None, dict[str, str] | None], tuple[int, object]]


def allowed_graph_route(method: str, path: str) -> bool:
    """Keep the provider constrained to a mailbox or a bounded directory read."""

    return path.startswith("/me/") or (
        str(method).upper() == "GET" and path.startswith("/users?")
    )


def graph_request(
    method: str,
    path: str,
    access_token: str,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    if not allowed_graph_route(method, path):
        raise MailError("Rota Microsoft Graph não permitida.")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    selected_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if body is not None:
        selected_headers["Content-Type"] = "application/json; charset=utf-8"
    selected_headers.update(headers or {})
    request = urllib.request.Request(
        GRAPH_ROOT + path, data=body, headers=selected_headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, raw = int(response.status), read_limited(response, GRAPH_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        status, raw = int(exc.code), read_limited(exc, ERROR_RESPONSE_BYTES)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MailError("O Microsoft Graph não respondeu.") from exc
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {}
