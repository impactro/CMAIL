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


def imap_provider(tmp_path, capabilities=(b"IMAP4rev1", b"MOVE")):
    selected = replace(config(tmp_path), mode="imap")
    client = Mock()
    client.capabilities = capabilities
    client.capability.return_value = ("OK", [b" ".join(capabilities)])
    client.select.return_value = ("OK", [])
    client.uid.return_value = ("OK", [])
    provider = ImapSmtpProvider(selected)
    provider._imap = Mock(return_value=client)
    return selected, provider, client


def test_imap_lists_quoted_unquoted_and_special_use_folders(tmp_path):
    _, provider, client = imap_provider(tmp_path)
    client.list.return_value = ("OK", [
        b'(\\HasNoChildren) "." INBOX',
        b'(\\Archive) "." "INBOX.Archive"',
        b'(\\Trash) "/" "Deleted Messages"',
        b'(\\Noselect) "/" "Container"',
        b'(\\HasNoChildren) "/" "Quotes \\"test\\""',
    ])
    folders = provider.folders()
    assert [item["id"] for item in folders] == ["INBOX", "INBOX.Archive", "Deleted Messages", 'Quotes "test"']
    assert [item["wellKnownName"] for item in folders[:3]] == ["inbox", "archive", "trash"]


@pytest.mark.parametrize("is_read,operation", [(True, "+FLAGS.SILENT"), (False, "-FLAGS.SILENT")])
def test_imap_read_flag_uses_selected_folder_and_uid(tmp_path, is_read, operation):
    _, provider, client = imap_provider(tmp_path)
    assert provider.set_read("42", is_read, folder="Projects 2026")["isRead"] == is_read
    client.select.assert_called_once_with('"Projects 2026"', readonly=False)
    client.uid.assert_called_once_with("STORE", "42", operation, "(\\Seen)")


@pytest.mark.parametrize("capabilities,expected", [
    ((b"MOVE",), [call("MOVE", "42", '"Deleted Messages"')]),
    ((b"UIDPLUS",), [call("COPY", "42", '"Deleted Messages"'), call("STORE", "42", "+FLAGS.SILENT", "(\\Deleted)"), call("EXPUNGE", "42")]),
])
def test_imap_moves_only_selected_uid_never_expunge_mailbox(tmp_path, capabilities, expected):
    _, provider, client = imap_provider(tmp_path, capabilities)
    assert provider.move("42", "Deleted Messages", folder="Archive")["moved"]
    client.select.assert_called_once_with('"Archive"', readonly=False)
    assert client.uid.call_args_list == expected
    client.expunge.assert_not_called()


def test_imap_without_safe_move_support_never_copies_or_deletes(tmp_path):
    _, provider, client = imap_provider(tmp_path, (b"IMAP4rev1",))
    assert provider.message_actions() == {"setRead": True, "move": False, "trash": True, "deletePermanently": False}
    with pytest.raises(MailError, match="segura"):
        provider.move("42", "Trash")
    client.uid.assert_not_called()


@pytest.mark.parametrize("failed_step,expected_commands", [(0, ["COPY"]), (1, ["COPY", "STORE"]), (2, ["COPY", "STORE", "EXPUNGE"])])
def test_imap_move_failure_stops_without_retry(tmp_path, failed_step, expected_commands):
    _, provider, client = imap_provider(tmp_path, (b"UIDPLUS",))
    client.uid.side_effect = [("OK", [])] * failed_step + [("NO", [])]
    with pytest.raises(MailError):
        provider.move("42", "Trash")
    assert [args[0][0] for args in client.uid.call_args_list] == expected_commands
    client.expunge.assert_not_called()


def test_api_actions_respect_principal_and_web_mutations_require_csrf(tmp_path):
    selected, provider, imap = imap_provider(tmp_path)
    service = MailService(selected, provider)
    api = CmailApi(service)
    readonly = Principal("", "", frozenset({"mail.read"}))
    actions = api.message_actions(readonly)
    assert actions == {"setRead": False, "move": False, "reply": False, "forward": False, "trash": False, "deletePermanently": False, "send": False, "lists": False}
    with pytest.raises(PermissionError):
        api.move(readonly, "42", "Trash")
    imap.uid.assert_not_called()
    web = TestClient(create_app(selected, service))
    csrf = web.get("/").text.split('data-csrf="', 1)[1].split('"', 1)[0]
    assert web.get("/api/message-actions").json()["actions"]["move"]
    assert web.post("/api/messages/42/move", json={"destinationId": "Trash"}).status_code == 403
    response = web.patch("/api/messages/42/read", headers={"X-CSRF-Token": csrf}, json={"isRead": True, "folder": "Projects"})
    assert response.status_code == 200
    imap.select.assert_called_with('"Projects"', readonly=False)
    assert web.post("/api/messages/42/move", headers={"X-CSRF-Token": csrf}, json={"destinationId": "Trash", "folder": "Projects"}).status_code == 200
    assert service.history(Principal("local-imap", "", frozenset({"mail.read"})))[0]["action"] == "move"


def test_imap_capabilities_are_queried_after_login_instead_of_cached(tmp_path):
    _, provider, client = imap_provider(tmp_path, (b"IMAP4rev1",))
    client.capability.return_value = ("OK", [b"IMAP4rev1 MOVE UIDPLUS"])
    assert provider.message_actions()["move"]
    assert provider.message_actions()["deletePermanently"]
    provider.move("42", "Trash")
    client.uid.assert_called_once_with("MOVE", "42", '"Trash"')


def test_imap_permanent_delete_only_expunge_selected_trash_uid(tmp_path):
    _, provider, client = imap_provider(tmp_path, (b"UIDPLUS",))
    provider.folders = Mock(return_value=[{"id": "INBOX.Trash", "name": "INBOX.Trash"}])
    with pytest.raises(MailError, match="lixeira"):
        provider.delete_permanently("42", folder="INBOX")
    client.uid.assert_not_called()
    assert provider.delete_permanently("42", folder="INBOX.Trash")["deletedPermanently"]
    assert client.uid.call_args_list == [call("STORE", "42", "+FLAGS.SILENT", "(\\Deleted)"), call("EXPUNGE", "42")]
    client.expunge.assert_not_called()


@pytest.mark.parametrize("capabilities,failed_step", [((b"MOVE",), -1), ((b"UIDPLUS",), 0), ((b"UIDPLUS",), 1)])
def test_imap_permanent_delete_fails_without_broad_expunge_or_retry(tmp_path, capabilities, failed_step):
    _, provider, client = imap_provider(tmp_path, capabilities)
    provider.folders = Mock(return_value=[{"id": "Trash", "name": "Trash"}])
    if failed_step >= 0:
        client.uid.side_effect = [("OK", [])] * failed_step + [("NO", [])]
    with pytest.raises(MailError):
        provider.delete_permanently("42", folder="Trash")
    assert client.uid.call_count == max(0, failed_step + 1)
    client.expunge.assert_not_called()


def test_imap_reply_all_uses_original_folder_and_excludes_own_account(tmp_path):
    selected, provider, _ = imap_provider(tmp_path)
    provider.config = replace(selected, account="team@example.test", username="team@example.test")
    provider.message = Mock(return_value={"from": {"address": "sender@example.test"}, "replyTo": [{"address": "reply@example.test"}], "to": [{"address": "team@example.test"}], "cc": [{"address": "colleague@example.test"}], "subject": "Planning", "internetMessageId": "<original@example.test>"})
    provider.send = Mock(return_value={"accepted": True})
    assert provider.reply("42", "Confirmed", reply_all=True, folder="Projects")["accepted"]
    provider.message.assert_called_once_with("Projects", "42")
    provider.send.assert_called_once_with(["reply@example.test", "colleague@example.test"], "Re: Planning", "Confirmed", reply_message_id="<original@example.test>")


def test_imap_forward_is_text_only_and_requires_confirmation_in_service(tmp_path):
    selected, provider, _ = imap_provider(tmp_path)
    provider.message = Mock(return_value={"from": {"name": "Sender", "address": "sender@example.test"}, "subject": "Planning", "body": "Original text", "attachments": [{"name": "not-forwarded.pdf"}]})
    provider.send = Mock(return_value={"accepted": True})
    service = MailService(selected, provider)
    with pytest.raises(ValueError, match="confirmação"):
        service.forward(Principal.local_operator(), "42", ["recipient@example.test"], "See below", folder="Projects")
    provider.send.assert_not_called()
    service.forward(Principal.local_operator(), "42", ["recipient@example.test"], "See below", folder="Projects", confirmed=True)
    provider.message.assert_called_once_with("Projects", "42")
    assert "Original text" in provider.send.call_args.args[2]
    assert "not-forwarded.pdf" not in provider.send.call_args.args[2]


def test_gmail_exposes_trash_and_can_restore_to_inbox():
    provider = GmailProvider(Mock(), "synthetic")
    provider._call = Mock(return_value={"labels": [{"id": "TRASH", "name": "TRASH"}, {"id": "SENT", "name": "SENT"}]})
    assert provider.folders()[0]["id"] == "TRASH"
    assert provider.folders()[0]["canMoveTo"] is True
    assert provider.folders()[1]["canMoveTo"] is False
    provider.move("42", "INBOX")
    assert provider._call.call_args.args[2] == {"addLabelIds": ["INBOX"], "removeLabelIds": ["TRASH"]}
    provider.move("42", "Label_Target", folder="Label_Source")
    assert provider._call.call_args.args[2] == {"addLabelIds": ["Label_Target"], "removeLabelIds": ["Label_Source", "TRASH"]}


def test_graph_resolves_archive_and_trash_by_id_independent_of_language():
    from cmail.graph import MicrosoftGraphProvider
    provider = MicrosoftGraphProvider(Mock(), "synthetic")
    def response(method, path):
        if path.startswith("/me/mailFolders?"):
            return {"value": [{"id": "entry", "displayName": "Boîte de réception"}, {"id": "archive", "displayName": "Archiv"}, {"id": "deleted", "displayName": "Gelöscht"}]}
        return {"id": {"inbox": "entry", "archive": "archive", "deleteditems": "deleted"}[path.split("/")[-1].split("?")[0]]}
    provider._call = response
    assert [item["wellKnownName"] for item in provider.folders()] == ["inbox", "archive", "trash"]
