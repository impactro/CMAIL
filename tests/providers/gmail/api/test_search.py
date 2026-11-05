from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from cmail.search import search_messages
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider




def test_gmail_search_is_sent_to_the_provider_with_its_folder_scope():
    provider = GmailProvider(None, 'identity')
    calls = []
    provider._call = lambda method,path: calls.append(path) or {'messages': []}
    assert provider.search_messages('Label_private', 'cliente antigo', 10) == []
    params = parse_qs(urlsplit(calls[0]).query)
    assert params['q'] == ['cliente antigo'] and params['labelIds'] == ['Label_private']
    assert params['maxResults'] == ['10']

