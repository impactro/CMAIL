"""Web identity, sessions and CSRF; no provider calls or host imports."""
from __future__ import annotations

import secrets
from typing import Callable, Mapping
from fastapi import Request
from .auth import AuthenticationError
from .service import MANAGE_LISTS, MANAGE_MAIL, READ_MAIL, SEND_MAIL, MailService, Principal

SESSION_COOKIE = "cmail_session"
CSRF_COOKIE = "cmail_csrf"
BROWSER_COOKIE = "cmail_oauth_browser"
HostPrincipalResolver = Callable[[Request], Mapping[str, object]]


def _web_principal(
    service: MailService,
    request: Request,
    resolver: HostPrincipalResolver | None = None,
) -> Principal | None:
    if resolver is not None:
        raw = resolver(request)
        if not isinstance(raw, Mapping):
            raise AuthenticationError("O host não devolveu uma identidade válida.")
        owner_id = str(raw.get("identifier") or "").strip()
        if not owner_id or len(owner_id) > 256:
            raise AuthenticationError("O host não confirmou o workspace atual.")
        raw_capabilities = raw.get("capabilities")
        capabilities = frozenset(
            str(item).strip()
            for item in raw_capabilities
            if str(item).strip() in {READ_MAIL, MANAGE_MAIL, SEND_MAIL, MANAGE_LISTS}
        ) if isinstance(raw_capabilities, (list, tuple, set, frozenset)) else frozenset()
        provider_name = (
            "microsoft" if service.config.mode == "microsoft" else
            "google" if service.config.mode == "gmail" else ""
        )
        bound = service.store.bound_identity(provider_name, owner_id) if provider_name else None
        identity_id = str((bound or {}).get("id") or "")
        if identity_id and service.auth and not service.auth.is_connected(identity_id):
            identity_id = ""
        email = str((bound or {}).get("email") or raw.get("email") or "").strip()
        return Principal(identity_id, email, capabilities, owner_id)
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


class WebSecurity:
    def __init__(self, service, resolver=None):
        self.service, self.config, self.resolver = service, service.config, resolver

    def csrf(self, request: Request, principal: Principal | None) -> str:
        if self.resolver is not None or self.config.mode in {'demo', 'imap', 'setup'}:
            return request.session.setdefault('cmail_csrf', secrets.token_urlsafe(24))
        return str(request.cookies.get(CSRF_COOKIE) or '') if principal else ''

    def setup_csrf(self, request: Request) -> str:
        return request.session.setdefault('cmail_setup_csrf', secrets.token_urlsafe(24))

    def require_principal(self, request: Request) -> Principal:
        principal = _web_principal(self.service, request, self.resolver)
        if principal is None or (self.config.mode in {'microsoft', 'gmail'} and (not principal.identity_id)):
            raise AuthenticationError('Autentique a conta de e-mail desta instância.', requires_reconnect=self.config.mode in {'microsoft', 'gmail'})
        if self.resolver is not None and (not self.service.store.webmail_enabled(principal.storage_owner)):
            raise PermissionError('O Webmail está desabilitado para este workspace.')
        return principal

    def require_csrf(self, request: Request, principal: Principal) -> None:
        supplied = str(request.headers.get('X-CSRF-Token') or '')
        if self.resolver is not None or self.config.mode in {'demo', 'imap', 'setup'}:
            if not supplied or not secrets.compare_digest(supplied, self.csrf(request, principal)):
                raise PermissionError('CSRF_INVALID')
            return
        identity = self.service.auth.current(str(request.cookies.get(SESSION_COOKIE) or '')) if self.service.auth else None
        if not identity or not self.service.store.csrf_valid(identity, supplied):
            raise PermissionError('CSRF_INVALID')
