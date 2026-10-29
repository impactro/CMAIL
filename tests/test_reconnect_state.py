"""Distinguish an invalid Microsoft grant from a transient transport failure."""
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from cmail.auth import AuthenticationError, MicrosoftAuthService
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import MailError
from cmail.service import MailService
from cmail.web import create_app
from test_cmail import config


def auth_stub(tmp_path, result=None, error=None):
    cache = tmp_path / 'protected-cache'; cache.write_bytes(b'synthetic')
    auth = object.__new__(MicrosoftAuthService)
    auth.store = Mock()
    auth.store.identity.return_value = {'email':'operator@example.test'}
    auth.store.connection.return_value = {'status':'authorized'}
    auth._identity_cache = Mock(return_value=cache)
    auth.config = SimpleNamespace()
    client = Mock()
    client.get_accounts.return_value = [{'id':'synthetic'}]
    client.acquire_token_silent.return_value = result
    client.acquire_token_silent.side_effect = error
    auth.client_factory = lambda *args: client
    return auth


def test_silent_token_failure_persists_reconnect_state(tmp_path):
    auth = auth_stub(tmp_path,{'error':'invalid_grant'})
    with pytest.raises(AuthenticationError) as raised:
        auth.access_token('identity')
    assert raised.value.requires_reconnect
    auth.store.set_connection_status.assert_called_once_with('identity','reauthorize','silent-token')


@pytest.mark.parametrize('result,error', [({'error':'temporarily_unavailable'},None),
                                         ({'error':'server_error'},None),(None,TimeoutError())])
def test_transient_failure_does_not_revoke_or_request_new_login(tmp_path, result, error):
    auth = auth_stub(tmp_path,result,error)
    with pytest.raises(AuthenticationError) as raised:
        auth.access_token('identity')
    assert not raised.value.requires_reconnect
    auth.store.set_connection_status.assert_not_called()


def test_graph_401_changes_shared_connection_state_but_403_and_503_do_not():
    for status in (401,403,503):
        auth = Mock(); auth.access_token.return_value = 'synthetic'
        provider = MicrosoftGraphProvider(auth,'identity',requester=lambda *args:(status,{}))
        with pytest.raises(AuthenticationError if status == 401 else MailError):
            provider._call('GET','/me/mailFolders')
        if status == 401:
            auth.store.set_connection_status.assert_called_once_with('identity','reauthorize','provider-401')
        else:
            auth.store.set_connection_status.assert_not_called()


def test_http_reports_reconnect_without_sending_or_automatic_retry(tmp_path):
    provider = Mock()
    provider.folders.side_effect = AuthenticationError('Reconecte sua conta.',requires_reconnect=True)
    service = MailService(config(tmp_path),provider)
    client = TestClient(create_app(service.config,service,url_prefix='/cm/cmail'))
    result = client.get('/cm/cmail/api/folders')
    assert result.status_code == 401
    assert result.json()['requiresReconnect'] is True
    assert result.json()['reauthorizeUrl'] == '/cm/cmail/auth/microsoft'
    assert provider.folders.call_count == 1
    provider.send.assert_not_called()
