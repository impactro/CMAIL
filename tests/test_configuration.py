"""Focused configuration regression tests."""
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from cmail.config import Config, ConfigError
from cmail.service import MailService, Principal
from cmail.web import create_app
from cmail.__main__ import _serve
from helpers import (FakeMail, config, config_payload, config_payload_v11, microsoft_config, write_config)


def test_standalone_server_reloads_config_without_replacing_process():
    first = SimpleNamespace(host="127.0.0.1", port=8020, open_browser=False)
    second = SimpleNamespace(host="127.0.0.1", port=8020, open_browser=False)
    created = []

    class ImmediateTimer:
        daemon = False
        def __init__(self, _delay, callback): self.callback = callback
        def start(self): self.callback()

    class FakeServer:
        def __init__(self, restart_callback, index):
            self.restart_callback = restart_callback
            self.index = index
            self.closed = False
            self.task_dispatcher = SimpleNamespace(shutdown=lambda: None)
        def run(self):
            if self.index == 0:
                self.restart_callback()
        def close(self): self.closed = True

    def app_factory(config, _service, *, restart_callback):
        created.append(config)
        return restart_callback

    servers = []
    def server_factory(restart_callback, **_kwargs):
        server = FakeServer(restart_callback, len(servers))
        servers.append(server)
        return server

    assert _serve(
        first,
        config_loader=lambda: second,
        service_factory=lambda _config: object(),
        app_factory=app_factory,
        server_factory=server_factory,
        timer_factory=ImmediateTimer,
    ) == 0
    assert created == [first, second]
    assert servers[0].closed is True


def test_setup_configures_one_imap_account_without_secret_in_json(tmp_path):
    write_config(tmp_path, config_payload_v11())
    selected = Config.load(tmp_path)
    with pytest.raises(PermissionError, match="Configure a única conta"):
        MailService(selected).folders(Principal.local_operator())
    restarted = []
    app = create_app(selected, restart_callback=lambda: restarted.append(True))
    client = TestClient(app, follow_redirects=False)
    assert client.get("/").headers["location"].endswith("/setup")
    page = client.get("/setup")
    csrf = page.text.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    result = client.post("/setup", data={
        "csrf": csrf, "provider": "imap", "account": "pessoa@example.com",
        "username": "pessoa@example.com", "password": "senha-de-teste",
        "imapHost": "imap.example.com", "imapPort": "993", "imapSecurity": "ssl",
        "smtpHost": "smtp.example.com", "smtpPort": "587", "smtpSecurity": "starttls",
        "sentFolder": "Sent",
    })
    assert result.status_code == 202
    assert restarted == [True]
    configured = Config.load(tmp_path)
    assert configured.mode == "imap"
    assert configured.account == "pessoa@example.com"
    assert configured.password() == "senha-de-teste"
    raw = configured.config_file.read_text(encoding="utf-8")
    assert "senha-de-teste" not in raw
    assert configured.public()["singleAccount"] is True
    webmail = create_app(configured, MailService(configured, FakeMail()))
    imap_client = TestClient(webmail, follow_redirects=False)
    assert imap_client.get("/").status_code == 200
    assert imap_client.get("/api/folders").status_code == 200
    assert imap_client.get("/setup").status_code == 200


def test_setup_rejects_mutation_without_csrf(tmp_path):
    write_config(tmp_path, config_payload_v11())
    app = create_app(Config.load(tmp_path))
    response = TestClient(app, follow_redirects=False).post("/setup", data={})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "sessão de configuração expirou" in response.text


def test_configured_microsoft_setup_uses_dedicated_session_csrf(tmp_path):
    selected = microsoft_config(tmp_path, account="antiga@empresa.test")
    original_secret = selected.microsoft_client_secret()
    restarted = []
    app = create_app(selected, restart_callback=lambda: restarted.append(True))
    client = TestClient(app, follow_redirects=False)

    page = client.get("/setup")
    token = page.text.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    assert token
    assert 'value="client-test"' in page.text
    assert 'value="tenant-lakatos"' in page.text
    assert "antiga@empresa.test" in page.text
    assert "Não é necessário digitar o e-mail" in page.text
    result = client.post("/setup", data={
        "csrf": token, "provider": "outlook",
        "clientId": "client-test", "clientSecret": "",
        "tenantId": "tenant-lakatos",
    })
    assert result.status_code == 202
    assert restarted == [True]
    configured = Config.load(tmp_path)
    assert configured.microsoft_account == ""
    assert configured.microsoft_client_secret() == original_secret


def test_config_is_closed_and_env_contains_only_pointer(tmp_path):
    write_config(tmp_path)
    with (tmp_path / ".env").open("a", encoding="utf-8") as stream:
        stream.write("CMAIL_PORT=9999\n")
    with pytest.raises(ConfigError, match="somente CMAIL_CONFIG_FILE"):
        Config.load(tmp_path)
    write_config(tmp_path)
    payload = config_payload(); payload["unexpected"] = True
    (tmp_path / "cmail.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="Contrato fechado"):
        Config.load(tmp_path)


def test_config_paths_are_relative_to_json_file(tmp_path):
    config_dir = tmp_path / "external-config"; config_dir.mkdir()
    (tmp_path / ".env").write_text("CMAIL_CONFIG_FILE=external-config/cmail.json\n", encoding="utf-8")
    (config_dir / "cmail.json").write_text(json.dumps(config_payload()), encoding="utf-8")
    selected = Config.load(tmp_path)
    assert selected.state_dir == (config_dir / ".state").resolve()
    assert "config_file" not in selected.public()
    assert "tenant" not in json.dumps(selected.public()).casefold()



@pytest.mark.parametrize("offline_access", [False, True])
def test_config_explicit_offline_access_is_publicly_nonsecret_and_optional(tmp_path, offline_access):
    payload = config_payload_v11()
    payload["microsoft"]["offlineAccess"] = offline_access
    write_config(tmp_path, payload)
    assert Config.load(tmp_path).microsoft_offline_access is offline_access
    del payload["microsoft"]["offlineAccess"]
    write_config(tmp_path, payload)
    assert Config.load(tmp_path).microsoft_offline_access is False


@pytest.mark.parametrize("value", ["true", 1, None])
def test_config_rejects_nonboolean_offline_access(tmp_path, value):
    payload = config_payload_v11()
    payload["microsoft"]["offlineAccess"] = value
    write_config(tmp_path, payload)
    with pytest.raises(ConfigError, match="offlineAccess"):
        Config.load(tmp_path)


def test_setup_preserves_explicit_microsoft_refresh_opt_in(tmp_path):
    from dataclasses import replace
    from cmail.setup import SetupService
    selected = replace(microsoft_config(tmp_path), microsoft_offline_access=True)
    SetupService(selected).save({"provider": "outlook", "clientId": "client-test",
                                 "tenantId": "tenant-lakatos", "clientSecret": ""})
    assert Config.load(tmp_path).microsoft_offline_access is True
