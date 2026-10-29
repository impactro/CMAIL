"""Deletion contracts, synthetic providers only; no real mailbox mutations."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from cmail.api import CmailApi
from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import MailError
from cmail.service import MailService, Principal
from cmail.web import create_app
from test_cmail import config
from test_frontend_playwright import ContextMailbox


def test_api_trash_and_permanent_delete_are_separate_confirmed_operations(tmp_path):
    mailbox = ContextMailbox()
    service = MailService(config(tmp_path), mailbox)
    api, operator = CmailApi(service), Principal.local_operator()
    for operation in (api.trash_message, api.delete_permanently):
        with pytest.raises(ValueError, match="confirmação"):
            operation(operator, "one", folder="INBOX")
    with pytest.raises(ValueError, match="lixeira"):
        api.delete_permanently(operator, "one", folder="INBOX", confirmed=True)
    assert mailbox.moves == [] and mailbox.deleted == []
    assert api.trash_message(operator, "one", confirmed=True)["trashed"]
    assert mailbox.locations["one"] == "Trash" and mailbox.deleted == []
    with pytest.raises(ValueError, match="separada"):
        api.trash_message(operator, "one", folder="Trash", confirmed=True)
    assert api.delete_permanently(operator, "one", folder="Trash", confirmed=True)["deletedPermanently"]
    assert mailbox.deleted == ["one"]
    assert [item["action"] for item in api.history(operator)] == ["delete-permanently", "trash"]


def test_deletion_requires_manage_capability_before_touching_provider(tmp_path):
    mailbox = ContextMailbox()
    mailbox.folders = Mock()
    api = CmailApi(MailService(config(tmp_path), mailbox))
    principal = Principal("", "", frozenset({"mail.read"}))
    for operation in (api.trash_message, api.delete_permanently):
        with pytest.raises(PermissionError):
            operation(principal, "one", folder="Trash", confirmed=True)
    mailbox.folders.assert_not_called()


def test_no_trash_never_falls_back_to_permanent_delete(tmp_path):
    mailbox = ContextMailbox()
    mailbox.folders = lambda: [{"id": "INBOX", "name": "INBOX"}]
    api = CmailApi(MailService(config(tmp_path), mailbox))
    with pytest.raises(ValueError, match="lixeira"):
        api.trash_message(Principal.local_operator(), "one", confirmed=True)
    assert mailbox.deleted == [] and mailbox.moves == []


def test_opaque_draft_values_remain_cli_safe_with_leading_hyphen_randomness(tmp_path, monkeypatch):
    from cmail.store import Store
    monkeypatch.setattr("cmail.store.secrets.token_urlsafe", lambda size: "-random")
    store = Store(tmp_path)
    draft = store.prepare({"recipients": ["person@example.test"], "subject": "Synthetic", "body": "Synthetic"})
    assert not draft["draftId"].startswith("-")
    assert not draft["confirmationToken"].startswith("-")
    assert store.claim(draft["draftId"], draft["confirmationToken"])["body"] == "Synthetic"


def test_distinct_http_routes_require_csrf_and_explicit_confirmation(tmp_path):
    mailbox = ContextMailbox()
    client = TestClient(create_app(config(tmp_path), MailService(config(tmp_path), mailbox)))
    page = client.get("/")
    csrf = page.text.split('data-csrf="', 1)[1].split('"', 1)[0]
    headers = {"X-CSRF-Token": csrf}
    for operation in ("trash", "delete-permanently"):
        route = f"/api/messages/one/{operation}"
        assert client.post(route, json={"folder": "Trash", "confirmed": True}).status_code == 403
        assert client.post(route, headers=headers, json={"folder": "Trash"}).status_code == 400
    assert client.post("/api/messages/one/delete-permanently", headers=headers, json={"folder": "INBOX", "confirmed": True}).status_code == 400
    assert mailbox.moves == [] and mailbox.deleted == []
    assert client.post("/api/messages/one/trash", headers=headers, json={"folder": "INBOX", "confirmed": True}).status_code == 200
    assert mailbox.deleted == []
    assert client.post("/api/messages/one/delete-permanently", headers=headers, json={"folder": "Trash", "confirmed": True}).status_code == 200
    assert mailbox.deleted == ["one"]


def test_gmail_soft_delete_uses_trash_and_permanent_delete_checks_real_membership():
    auth = SimpleNamespace(granted_scopes=lambda identity: {"https://mail.google.com/"})
    provider = GmailProvider(auth, "synthetic")
    provider._call = Mock(return_value={"labelIds": ["TRASH"]})
    assert provider.trash("one", "TRASH")["trashed"]
    provider._call.assert_called_once_with("POST", "/messages/one/trash")
    provider._call.reset_mock()
    assert provider.delete_permanently("one", folder="TRASH")["deletedPermanently"]
    assert [item.args[:2] for item in provider._call.call_args_list] == [("GET", "/messages/one?format=minimal"), ("DELETE", "/messages/one")]
    provider._call.reset_mock()
    provider._call.return_value = {"labelIds": ["INBOX"]}
    with pytest.raises(ValueError, match="lixeira"):
        provider.delete_permanently("one", folder="TRASH")
    assert provider._call.call_count == 1


def test_gmail_modify_grant_does_not_allow_permanent_deletion_or_expand_scopes():
    auth = SimpleNamespace(granted_scopes=lambda identity: {"https://www.googleapis.com/auth/gmail.modify"})
    provider = GmailProvider(auth, "synthetic")
    provider._call = Mock()
    assert provider.message_actions() == {"trash": True, "deletePermanently": False}
    with pytest.raises(PermissionError, match="autorização"):
        provider.delete_permanently("one", folder="TRASH")
    provider._call.assert_not_called()


@pytest.mark.parametrize("parent", ["Inbox-ID", "Trash-ID"])
def test_graph_permanent_delete_verifies_real_parent_and_uses_permanent_action(parent):
    provider = MicrosoftGraphProvider(Mock(), "synthetic")
    provider._call = Mock(side_effect=[{"id": "Trash-ID"}, {"parentFolderId": parent}, {}])
    if parent != "Trash-ID":
        with pytest.raises(MailError, match="lixeira"):
            provider.delete_permanently("one", folder="Trash-ID")
        assert provider._call.call_count == 2
    else:
        assert provider.delete_permanently("one", folder="Trash-ID")["deletedPermanently"]
        assert provider._call.call_args.args == ("POST", "/me/messages/one/permanentDelete")
        assert provider._call.call_args.kwargs == {"expected": (204,)}
