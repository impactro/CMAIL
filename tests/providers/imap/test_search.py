"""Exchange charset compatibility and sender search; synthetic IMAP only."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.mail import ImapSmtpProvider, MailError, SearchCharsetUnsupported
from cmail.search import search_messages


def provider(status='OK', data=None):
    client = Mock()
    client.select.return_value = ('OK', [])
    client.uid.return_value = (status, data or [b''])
    selected = ImapSmtpProvider(SimpleNamespace())
    selected._imap = Mock(return_value=client)
    return selected, client


def test_ascii_search_omits_charset_and_includes_sender():
    selected, client = provider()
    assert selected.search_messages('Archive', 'fulano@example.test', 7) == []
    client.uid.assert_called_once_with('search', 'OR', 'OR', 'OR', 'FROM', b'"fulano@example.test"',
        'SUBJECT', b'"fulano@example.test"', 'BODY', b'"fulano@example.test"', 'TO', b'"fulano@example.test"')
    client.select.assert_called_once_with('"Archive"', readonly=True)
    client.logout.assert_called_once()


def test_unicode_charset_rejection_is_explicitly_partial():
    selected, client = provider('NO', [b'[BADCHARSET (US-ASCII)] Unsupported'])
    selected.messages = Mock(return_value=[{'id': '42', 'from': {'name': 'Fábio'}, 'subject': 'Proposta'}])
    result = search_messages(selected, 'INBOX', 'Fábio', 7)
    assert result['messages'][0]['id'] == '42'
    assert result['search']['native'] is False and result['search']['incomplete']
    assert result['search']['scope'] == 'recent-summaries-only'
    selected.messages.assert_called_once_with('INBOX', 40)
    assert client.uid.call_args.args[1:3] == ('CHARSET', 'UTF-8')


def test_generic_search_failure_is_not_hidden_by_fallback():
    selected, client = provider('NO', [b'Server unavailable'])
    selected.messages = Mock()
    with pytest.raises(MailError):
        search_messages(selected, 'INBOX', 'proposta', 7)
    selected.messages.assert_not_called()


def test_search_control_characters_never_reach_imap():
    selected, client = provider()
    with pytest.raises(ValueError):
        selected.search_messages('INBOX', 'test\r\nDELETE')
    client.uid.assert_not_called()


def test_microsoft_unicode_uses_explicit_partial_search_without_malformed_command():
    selected, client = provider()
    selected.config = SimpleNamespace(mode='microsoft-imap')
    selected.messages = Mock(return_value=[{'id': '42', 'subject': 'Fábio'}])
    result = search_messages(selected, 'INBOX', 'Fábio', 7)
    assert result['search']['native'] is False and result['search']['incomplete']
    assert result['messages'][0]['id'] == '42'
    selected._imap.assert_not_called()
