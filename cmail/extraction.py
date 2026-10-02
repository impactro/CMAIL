"""Read-only extraction from recent messages through any CMAIL provider."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
import unicodedata
import time


class AmbiguousExtraction(ValueError):
    """The newest matching message contains more than one distinct value."""


@dataclass(frozen=True)
class Extraction:
    message_id: str
    received_at: datetime
    value: str = field(repr=False)


def _normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


def find_recent_value(mail, *, subject_contains, pattern, last_minutes,
                      after=None, sender=None, folder='INBOX', group=0,
                      now=None, limit=100):
    """Return a unique regex value in the newest matching recent message.

    The time window intersects ``after`` (e.g. the current run's start).
    No message is marked read, no token is persisted or logged. ``pattern``
    belongs to trusted application configuration, not to email content.
    """
    if not subject_contains or not isinstance(last_minutes, (int, float)) or last_minutes <= 0:
        raise ValueError('Informe título e janela positiva em minutos.')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or (after is not None and after.tzinfo is None):
        raise ValueError('Datas precisam ter fuso horário.')
    lower = now - timedelta(minutes=last_minutes)
    if after is not None:
        lower = max(lower, after)
    regex = re.compile(pattern)
    if not ((type(group) is int and 0 <= group <= regex.groups) or
            (isinstance(group, str) and group in regex.groupindex)):
        raise ValueError('Grupo de REGEX inexistente.')
    candidates = []
    for message in mail.messages(folder, limit):
        if _normalized(subject_contains) not in _normalized(message.get('subject', '')):
            continue
        if sender and message.get('from', {}).get('address', '').casefold() != sender.casefold():
            continue
        try:
            received = datetime.fromisoformat(message['receivedAt'])
        except (KeyError, TypeError, ValueError):
            continue
        if received.tzinfo is None or not lower <= received <= now:
            continue
        candidates.append((received, message))
    if not candidates:
        return None
    received, newest = max(candidates, key=lambda item: item[0])
    content = mail.message(folder, newest['id']).get('body', '')
    values = list(dict.fromkeys(match.group(group) for match in regex.finditer(content)))
    values = [value for value in values if value]
    if len(values) > 1:
        raise AmbiguousExtraction('A mensagem mais recente contém valores ambíguos.')
    return Extraction(str(newest['id']), received, values[0]) if values else None


def wait_for_recent_value(mail, *, poll_seconds=30, timeout_seconds=300,
                          wait=None, **query):
    """Poll using the caller's cancellable wait, returning None on timeout."""
    if poll_seconds <= 0 or timeout_seconds <= 0:
        raise ValueError('Intervalos precisam ser positivos.')
    pause = wait or time.sleep
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = find_recent_value(mail, **query)
        if result:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        pause(min(poll_seconds, remaining))
