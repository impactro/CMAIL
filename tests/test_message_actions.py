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




















