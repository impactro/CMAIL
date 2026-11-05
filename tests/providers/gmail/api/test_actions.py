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

