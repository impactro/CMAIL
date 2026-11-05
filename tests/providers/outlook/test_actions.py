"""Contextual controls and safe IMAP mutations, using synthetic mailboxes only."""
from dataclasses import replace
from unittest.mock import Mock, call

import pytest
from fastapi.testclient import TestClient

from cmail.api import CmailApi
from cmail.gmail import GmailProvider
from cmail.mail import ImapSmtpProvider, MailError
from cmail.service import MailService, Principal
from cmail.web import create_app
from helpers import config




def test_graph_resolves_archive_and_trash_by_id_independent_of_language():
    from cmail.graph import MicrosoftGraphProvider
    provider = MicrosoftGraphProvider(Mock(), "synthetic")
    def response(method, path):
        if path.startswith("/me/mailFolders?"):
            return {"value": [{"id": "entry", "displayName": "Boîte de réception"}, {"id": "archive", "displayName": "Archiv"}, {"id": "deleted", "displayName": "Gelöscht"}]}
        return {"id": {"inbox": "entry", "archive": "archive", "deleteditems": "deleted"}[path.split("/")[-1].split("?")[0]]}
    provider._call = response
    assert [item["wellKnownName"] for item in provider.folders()] == ["inbox", "archive", "trash"]


@pytest.mark.parametrize("destination", ["deleteditems", "archive", "custom-folder"])
def test_graph_move_accepts_created_and_preserves_new_message_id(destination):
    from cmail.graph import MicrosoftGraphProvider
    auth = Mock()
    auth.access_token.return_value = "synthetic-token"
    requester = Mock(return_value=(201, {"id": "moved-message"}))
    provider = MicrosoftGraphProvider(auth, "synthetic", requester=requester)
    result = (provider.trash("original", destination) if destination == "deleteditems"
              else provider.move("original", destination))
    assert result == {"id": "moved-message", "moved": True, **({"trashed": True} if destination == "deleteditems" else {})}
    requester.assert_called_once_with("POST", "/me/messages/original/move", "synthetic-token", {"destinationId": destination}, None)


@pytest.mark.parametrize("status", [400, 403, 429, 500])
def test_graph_move_still_rejects_provider_errors_without_retry(status):
    from cmail.graph import MicrosoftGraphProvider
    requester = Mock(return_value=(status, {}))
    provider = MicrosoftGraphProvider(Mock(), "synthetic", requester=requester)
    with pytest.raises(MailError, match=str(status)):
        provider.move("original", "deleteditems")
    assert requester.call_count == 1


def test_graph_move_unauthorized_still_requires_reconnection():
    from cmail.auth import AuthenticationError
    from cmail.graph import MicrosoftGraphProvider
    auth = Mock()
    requester = Mock(return_value=(401, {}))
    provider = MicrosoftGraphProvider(auth, "synthetic", requester=requester)
    with pytest.raises(AuthenticationError) as raised:
        provider.trash("original", "deleteditems")
    assert raised.value.requires_reconnect
    auth.store.set_connection_status.assert_called_once_with("synthetic", "reauthorize", "provider-401")
    assert requester.call_count == 1

