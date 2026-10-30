"""Bounded, thread-safe, owner-scoped transient HTML; no disk or background worker."""
from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Preview:
    owner: str
    expires: float
    content: bytes


class PreviewCache:
    def __init__(self, *, max_entries=64, max_bytes=16 * 1024 * 1024,
                 max_entry_bytes=4 * 1024 * 1024, per_owner=8, ttl_seconds=600,
                 clock: Callable[[], float] = time.monotonic):
        if min(max_entries, max_bytes, max_entry_bytes, per_owner, ttl_seconds) <= 0:
            raise ValueError('Limites de prévia devem ser positivos.')
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.max_entry_bytes, self.per_owner = min(max_entry_bytes, max_bytes), per_owner
        self.ttl_seconds, self.clock = ttl_seconds, clock
        self._entries: OrderedDict[str, Preview] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    def _remove(self, token):
        self._bytes -= len(self._entries.pop(token).content)

    def _expire(self, now):
        for token, entry in list(self._entries.items()):
            if entry.expires <= now:
                self._remove(token)

    def put(self, owner: str, content: str | bytes) -> str:
        encoded = content.encode('utf-8') if isinstance(content, str) else content
        if not isinstance(encoded, bytes) or len(encoded) > self.max_entry_bytes:
            raise ValueError('Prévia excede o limite de memória por mensagem.')
        with self._lock:
            now = self.clock()
            self._expire(now)
            owned = [token for token, entry in self._entries.items() if entry.owner == owner]
            while len(owned) >= self.per_owner:
                self._remove(owned.pop(0))
            while self._entries and (len(self._entries) >= self.max_entries
                                     or self._bytes + len(encoded) > self.max_bytes):
                self._remove(next(iter(self._entries)))
            token = secrets.token_urlsafe(24)
            self._entries[token] = Preview(owner, now + self.ttl_seconds, encoded)
            self._bytes += len(encoded)
            return token

    def get(self, owner: str, token: str) -> bytes | None:
        with self._lock:
            self._expire(self.clock())
            entry = self._entries.get(token)
            return entry.content if entry and entry.owner == owner else None

    def stats(self):
        with self._lock:
            self._expire(self.clock())
            return {'entries': len(self._entries), 'bytes': self._bytes,
                    'maxBytes': self.max_bytes, 'maxEntries': self.max_entries}
