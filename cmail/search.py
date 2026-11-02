"""Native folder search plus bounded approximate matching of recent summaries."""
from datetime import datetime
from difflib import SequenceMatcher
import re
import unicodedata


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(c))


def approximate(row, query):
    addresses = [row.get('from', {}), *(row.get('to') or []), *(row.get('cc') or [])]
    text = fold(' '.join([str(row.get(k) or '') for k in ('subject', 'body', 'preview')]
                        + [str(v.get(k) or '') for v in addresses if isinstance(v, dict) for k in ('name', 'address')]))
    words = re.findall(r'[\w@.+-]+', text)
    terms = re.findall(r'[\w@.+-]+', fold(query))
    return bool(terms) and all(term in text or len(term) >= 4 and any(
        abs(len(term)-len(word)) <= 1 and SequenceMatcher(None, term, word).ratio() >= .8
        for word in words) for term in terms)


def recent_key(row):
    try:
        return datetime.fromisoformat(str(row.get('receivedAt') or '').replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        return float('-inf')


def search_messages(provider, folder, query, limit, recent=()):
    query = str(query).strip()
    if not 1 <= len(query) <= 200:
        raise ValueError('A busca deve ter entre um e duzentos caracteres.')
    native = getattr(provider, 'search_messages', None)
    if not callable(native):
        raise ValueError('Este provedor não oferece busca na pasta.')
    rows = native(folder, query, limit)
    candidates = list(recent)
    if len(rows) < limit and not candidates:
        candidates = provider.messages(folder, 40)
    combined = {str(row['id']): row for row in rows}
    for row in candidates:
        if approximate(row, query):
            combined.setdefault(str(row['id']), row)
    return {'messages': sorted(combined.values(), key=lambda row: (recent_key(row), str(row['id'])), reverse=True)[:limit],
            'search': {'native': True, 'fuzzyWindow': len(candidates), 'order': 'received-desc',
                       'scope': 'selected-folder', 'approximation': 'recent-summaries-only'}}
