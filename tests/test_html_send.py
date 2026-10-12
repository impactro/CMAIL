"""Contrato HTML sem acessar provedores reais."""
import base64
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace

import pytest

from cmail.gmail import GmailProvider
from cmail.graph import MicrosoftGraphProvider
from cmail.mail import ImapSmtpProvider
from cmail.service import MailService
from cmail.store import Store


def test_html_draft_preserved_and_claimed_once(tmp_path):
    store = Store(tmp_path)
    payload = {"recipients": ["test@example.com"], "subject": "Ação",
               "body": "Olá, Fábio", "bodyHtml": "<p>Olá, <b>Fábio</b></p>"}
    draft = store.prepare(payload, "owner")
    assert draft["bodyType"] == "html"
    assert store.claim(draft["draftId"], draft["confirmationToken"], "owner") == payload
    with pytest.raises(ValueError):
        store.claim(draft["draftId"], draft["confirmationToken"], "owner")


def test_invalid_html_or_attachment_fails_before_preparation(tmp_path):
    store = Store(tmp_path)
    base = {"recipients": ["test@example.com"], "subject": "Ação", "body": "Texto"}
    for extra in ({"bodyHtml": 123}, {"bodyHtml": "x" * 200_001}, {"attachments": ["nota.pdf"]}):
        with pytest.raises(ValueError):
            store.prepare({**base, **extra})


def test_service_routes_html_and_keeps_plain_provider_compatibility(tmp_path):
    calls = []
    provider = SimpleNamespace(send=lambda *args, **kwargs: (calls.append((args, kwargs)) or {"accepted": True}))
    service = MailService(SimpleNamespace(mode="demo", state_dir=tmp_path), provider)
    for extra in ({}, {"bodyHtml": "<p>Olá</p>"}):
        draft = service.prepare({"recipients": ["test@example.com"], "subject": "Ação", "body": "Olá", **extra})
        service.execute(draft["draftId"], draft["confirmationToken"])
    assert calls[0][1] == {}
    assert calls[1][1] == {"body_html": "<p>Olá</p>"}


def test_gmail_mime_contains_plain_and_html():
    provider = object.__new__(GmailProvider)
    calls = []
    provider._call = lambda *args: (calls.append(args) or {"id": "fake"})
    provider.send(["test@example.com"], "Ação", "Olá", body_html="<p>Olá</p>")
    encoded = calls[0][2]["raw"]
    message = message_from_bytes(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)), policy=default)
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Olá"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>Olá</p>"


def test_graph_uses_html_body_and_saves_sent():
    provider = object.__new__(MicrosoftGraphProvider)
    calls = []
    provider._call = lambda *args, **kwargs: calls.append((args, kwargs))
    provider.send(["test@example.com"], "Ação", "Olá", body_html="<p>Olá</p>")
    assert calls[0][0][2]["message"]["body"] == {"contentType": "HTML", "content": "<p>Olá</p>"}
    assert calls[0][0][2]["saveToSentItems"] is True


def test_smtp_mime_preserves_accents_and_hidden_recipients():
    captured = []
    smtp = SimpleNamespace(login=lambda *args: None, send_message=lambda message: (captured.append(message) or {}), quit=lambda: None)
    config = SimpleNamespace(account="sender@example.com", password=lambda: "fake", username="fake",
                             smtp_security="ssl", smtp_host="fake", smtp_port=465)
    provider = ImapSmtpProvider(config, smtp_ssl_factory=lambda *args, **kwargs: smtp)
    provider.send(["one@example.com", "two@example.com"], "Ação", "Olá", body_html="<p>Olá</p>")
    assert captured[0].get_body(preferencelist=("html",)).get_content().strip() == "<p>Olá</p>"
    assert "one@example.com" not in captured[0]["To"]
