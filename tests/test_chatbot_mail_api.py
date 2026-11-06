"""Public API delegation and folder safety, with synthetic providers only."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.api import CmailApi
from cmail.principal import Principal
from cmail.service import MailService
from helpers import config


def test_search_public_api_preserves_native_scope_and_read_gate(tmp_path):
    native = Mock(return_value=[{'id': 'old', 'subject': 'proposta'}])
    service = MailService(config(tmp_path), SimpleNamespace(search_messages=native, messages=lambda *args: []))
    api = CmailApi(service)
    reader = Principal('', '', frozenset({'mail.read'}))
    result = api.search_messages(reader, 'Archive', 'proposta', 7)
    assert api.describe()['operations']['search-messages']['capability'] == 'mail.read'
    assert result['messages'][0]['id'] == 'old'
    assert result['search']['scope'] == 'selected-folder'
    native.assert_called_once_with('Archive', 'proposta', 7)
    with pytest.raises(PermissionError):
        api.search_messages(Principal('', '', frozenset({'mail.send'})), 'Archive', 'proposta')
    assert native.call_count == 1


def test_microsoft_imap_mark_read_preserves_selected_folder(tmp_path):
    provider = SimpleNamespace(set_read=Mock(return_value={'isRead': True}))
    service = MailService(replace(config(tmp_path), mode='microsoft-imap'), provider)
    CmailApi(service).set_read(Principal.local_operator(), '42', True, folder='Projects')
    provider.set_read.assert_called_once_with('42', True, folder='Projects')
