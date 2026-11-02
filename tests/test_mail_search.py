from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from cmail.search import search_messages
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider


def row(identifier, date, **values):
    return {'id': identifier, 'receivedAt': date, 'subject': '', 'preview': '', **values}


def test_native_body_hits_and_approximate_recipient_hits_keep_recency_order():
    older = row('old-body', '2026-01-01T00:00:00Z')
    recent = row('new-typo', '2026-02-01T00:00:00Z', to=[{'address': 'financeiro@example.test'}])
    calls = []
    provider = SimpleNamespace(search_messages=lambda folder, query, limit: calls.append((folder,query,limit)) or [older])
    result = search_messages(provider, 'INBOX', 'financeir', 25, [recent])
    assert [r['id'] for r in result['messages']] == ['new-typo', 'old-body']
    assert calls == [('INBOX', 'financeir', 25)]
    assert result['search']['native'] and result['search']['fuzzyWindow'] == 1


def test_gmail_search_is_sent_to_the_provider_with_its_folder_scope():
    provider = GmailProvider(None, 'identity')
    calls = []
    provider._call = lambda method,path: calls.append(path) or {'messages': []}
    assert provider.search_messages('Label_private', 'cliente antigo', 10) == []
    params = parse_qs(urlsplit(calls[0]).query)
    assert params['q'] == ['cliente antigo'] and params['labelIds'] == ['Label_private']
    assert params['maxResults'] == ['10']


def test_outlook_search_targets_subject_body_and_recipient_without_incompatible_orderby():
    provider = MicrosoftGraphProvider(None, 'identity')
    calls = []
    provider._call = lambda method,path,**kw: calls.append(path) or {'value': []}
    assert provider.search_messages('inbox', 'proposta', 10) == []
    params = parse_qs(urlsplit(calls[0]).query)
    assert 'subject:proposta' in params['$search'][0]
    assert 'body:proposta' in params['$search'][0] and 'to:proposta' in params['$search'][0]
    assert '$orderby' not in params
