"""Owner-bound read-only ingress facade for consumers such as CCI.

No CCI/host imports, OAuth/session copy or mailbox mutations. Version 1.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .principal import READ_MAIL


class AnnotationReader:
    contract_version = 1

    def __init__(self, api, owner_id: str):
        self._api, self._owner = api, owner_id
        self._binding = self._identity()
        self.account_id = hashlib.sha256(json.dumps(self._binding).encode()).hexdigest()

    def _identity(self):
        principal = self._api.principal_for_owner(self._owner, frozenset({READ_MAIL}))
        return [self._api.service.config.mode, principal.storage_owner,
                principal.identity_id, principal.email.casefold()]

    def _principal(self):
        if self._identity() != self._binding:
            raise PermissionError('CMAIL_ANNOTATION_ACCOUNT_CHANGED')
        return self._api.principal_for_owner(self._owner, frozenset({READ_MAIL}))

    def page(self, *, since: str, until: str, cursor: str = '', limit: int = 50) -> dict:
        principal = self._principal()
        principal.require(READ_MAIL)
        for value in (since, until):
            if datetime.fromisoformat(value).tzinfo is None:
                raise ValueError('CMAIL_ANNOTATION_DATE_INVALID')
        if datetime.fromisoformat(since) >= datetime.fromisoformat(until):
            raise ValueError('CMAIL_ANNOTATION_WINDOW_INVALID')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('CMAIL_ANNOTATION_LIMIT_INVALID')
        selected = self._api.service.provider_for(principal)
        method = getattr(selected, 'annotation_page', None)
        if not callable(method):
            raise NotImplementedError('CMAIL_ANNOTATION_PAGINATION_UNAVAILABLE')
        result = method(since=since, until=until, cursor=cursor, limit=limit)
        self._principal()  # A concurrent disconnect/rebind must not leak into the consumer.
        return result

    def message(self, identifier: str) -> dict:
        value = self._api.message(self._principal(), 'INBOX', identifier)
        self._principal()
        return value

    def attachment(self, identifier: str, attachment_id: str) -> dict:
        value = self._api.attachment(self._principal(), identifier, attachment_id)
        self._principal()
        return value
