from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from cmail.search import search_messages
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider




def test_outlook_search_targets_subject_body_and_recipient_without_incompatible_orderby():
    provider = MicrosoftGraphProvider(None, 'identity')
    calls = []
    provider._call = lambda method,path,**kw: calls.append(path) or {'value': []}
    assert provider.search_messages('inbox', 'proposta', 10) == []
    params = parse_qs(urlsplit(calls[0]).query)
    assert 'subject:proposta' in params['$search'][0]
    assert 'body:proposta' in params['$search'][0] and 'to:proposta' in params['$search'][0]
    assert '$orderby' not in params
