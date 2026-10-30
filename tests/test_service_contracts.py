"""Focused service contracts regression tests."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from cmail.service import READ_MAIL, MailService, Principal
from cmail.store import Store
from cmail.web import create_app
from helpers import (FakeMail, PROJECT_ROOT, config)


def test_lists_and_confirmed_send(tmp_path):
    selected = config(tmp_path)
    fake = FakeMail()
    service = MailService(selected, fake)
    saved = service.store.save_list("Equipe", [{"name": "A", "address": "a@example.com"}])
    preview = service.prepare({"listId": saved["id"], "subject": "Teste", "body": "Conteúdo"})
    result = service.execute(preview["draftId"], preview["confirmationToken"])
    assert result["accepted"] is True
    assert len(fake.sent) == 1
    with pytest.raises(ValueError):
        service.execute(preview["draftId"], preview["confirmationToken"])


def test_web_requires_csrf(tmp_path):
    selected = config(tmp_path)
    app = create_app(selected, MailService(selected, FakeMail()))
    client = TestClient(app, follow_redirects=False)
    assert client.get("/health").json()["ok"] is True
    assert client.post("/api/send/prepare", json={}).status_code == 403
    page = client.get("/")
    token = page.text.split('data-csrf="', 1)[1].split('"', 1)[0]
    response = client.post("/api/send/prepare", headers={"X-CSRF-Token": token},
                           json={"recipients": ["a@example.com"], "subject": "A", "body": "B"})
    assert response.json()["ok"] is True


def test_frontend_does_not_render_api_values_with_inner_html():
    script = (PROJECT_ROOT / "cmail/static/app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "textContent" in script


def test_capability_is_required_before_provider_access(tmp_path):
    selected = config(tmp_path)
    service = MailService(selected, FakeMail())
    principal = Principal("limited", "limited@example.com", frozenset({READ_MAIL}))
    with pytest.raises(PermissionError):
        service.prepare({"recipients": ["a@example.com"], "subject": "A", "body": "B"}, principal)


def test_reply_and_forward_require_explicit_confirmation(tmp_path):
    selected = config(tmp_path)
    service = MailService(selected, FakeMail())
    principal = Principal("sender", "sender@example.com", frozenset({"mail.send"}))
    with pytest.raises(ValueError, match="confirmação explícita"):
        service.reply(principal, "message-1", "Resposta")
    with pytest.raises(ValueError, match="confirmação explícita"):
        service.forward(principal, "message-1", ["a@example.com"], "Encaminhando")


def test_fastapi_app_can_be_mounted_under_host_prefix(tmp_path):
    selected = config(tmp_path)
    app = create_app(selected, MailService(selected, FakeMail()), url_prefix="/tools/mail")
    client = TestClient(app, follow_redirects=False)
    page = client.get("/tools/mail/")
    assert page.status_code == 200
    assert 'data-base="/tools/mail"' in page.text
    assert client.get("/tools/mail/static/style.css").status_code == 200
    assert client.get("/tools/mail/health").json()["framework"] == "fastapi"


def test_legacy_local_lists_are_migrated_to_anonymous_owner(tmp_path):
    state = tmp_path / "state"; state.mkdir()
    with sqlite3.connect(state / "cmail.sqlite3") as db:
        db.executescript("""
          CREATE TABLE recipient_lists(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
          CREATE TABLE recipients(list_id INTEGER NOT NULL,address TEXT NOT NULL,name TEXT NOT NULL DEFAULT '',PRIMARY KEY(list_id,address));
          INSERT INTO recipient_lists VALUES(1,'Legado','2026-09-11T00:00:00+00:00');
          INSERT INTO recipients VALUES(1,'a@example.com','A');
        """)
    store = Store(state)
    assert store.lists()[0]["name"] == "Legado"
    assert store.list_recipients(1) == ["a@example.com"]
