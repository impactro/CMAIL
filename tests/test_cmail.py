from pathlib import Path

import pytest

from cmail.cm import describe
from cmail.config import Config
from cmail.service import MailService
from cmail.store import Store
from cmail.web import create_app


class FakeMail:
    def __init__(self): self.sent = []
    def status(self): return {"connected": True}
    def folders(self): return [{"id": "INBOX", "name": "Entrada"}]
    def messages(self, folder, limit=50): return []
    def message(self, folder, identifier): return {}
    def send(self, recipients, subject, body):
        self.sent.append((recipients, subject, body))
        return {"accepted": True, "recipientCount": len(recipients)}


def config(tmp_path: Path) -> Config:
    (tmp_path / ".env").write_text("CMAIL_MODE=demo\nCMAIL_STATE_DIR=.state\n", encoding="utf-8")
    return Config.load(tmp_path)


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


def test_component_descriptor_uses_packaged_skills():
    value = describe()
    assert value["id"] == "cmail"
    assert value["contractVersion"] == 2
    assert all(skill["path"].is_file() for group in value["skillGroups"] for skill in group["skills"])


def test_web_requires_csrf(tmp_path):
    selected = config(tmp_path)
    app = create_app(selected, MailService(selected, FakeMail()))
    app.testing = True
    client = app.test_client()
    assert client.get("/health").json["ok"] is True
    assert client.post("/api/send/prepare", json={}).status_code == 400
    page = client.get("/")
    token = page.text.split('data-csrf="', 1)[1].split('"', 1)[0]
    response = client.post("/api/send/prepare", headers={"X-CSRF-Token": token},
                           json={"recipients": ["a@example.com"], "subject": "A", "body": "B"})
    assert response.json["ok"] is True
