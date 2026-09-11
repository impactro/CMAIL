import json
import re
import sqlite3
import sys
import tomllib
import types
from pathlib import Path

import pytest

from cmail.cm import describe
from cmail.auth import MAIL_SCOPES, MicrosoftAuthService, build_microsoft_client
from cmail.api import CmailApi
from cmail.config import Config, ConfigError
from cmail.graph import MicrosoftGraphProvider
from cmail.gmail import GMAIL_SCOPES, GoogleAuthService
from cmail.service import MANAGE_LISTS, READ_MAIL, MailService, Principal
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
    write_config(tmp_path)
    return Config.load(tmp_path)


def config_payload(mode="demo"):
    return {
        "schemaVersion": "1.0", "mode": mode,
        "server": {"host": "127.0.0.1", "port": 8020, "openBrowser": False, "sessionHours": 12, "cookieSecure": False},
        "state": {"directory": ".state"},
        "microsoft": {"clientId": "", "tenantId": "", "clientSecretFile": "", "redirectUri": ""},
        "imap": {"account": "", "username": "", "passwordFile": "", "imapHost": "", "imapPort": 993,
                 "imapSecurity": "ssl", "smtpHost": "", "smtpPort": 587, "smtpSecurity": "starttls", "sentFolder": "Sent"},
    }


def config_payload_v11(mode="setup"):
    value = config_payload("demo")
    value["schemaVersion"] = "1.1"
    value["mode"] = mode
    value["microsoft"]["account"] = ""
    value["google"] = {
        "account": "", "clientId": "", "clientSecretFile": "", "redirectUri": "",
    }
    return value


def write_config(tmp_path: Path, payload=None):
    (tmp_path / ".env").write_text("CMAIL_CONFIG_FILE=cmail.json\n", encoding="utf-8")
    (tmp_path / "cmail.json").write_text(json.dumps(payload or config_payload()), encoding="utf-8")


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
    assert set(value) == {"id", "contractVersion", "version", "pythonModule", "description", "skillGroups", "operations"}
    accepted_id = re.compile(r"^[a-z][a-z0-9_-]*$")
    assert all(accepted_id.fullmatch(operation) for operation in value["operations"])
    assert all(set(contract) == {"description", "argv", "effects"} for contract in value["operations"].values())
    assert all(skill["path"].is_file() for group in value["skillGroups"] for skill in group["skills"])
    assert all(
        operation in value["operations"]
        for group in value["skillGroups"] for skill in group["skills"] for operation in skill["operations"]
    )


def test_python_api_contract_is_separate_from_cm2_descriptor():
    cm_contract = describe()
    api_contract = CmailApi.describe()
    assert "structuredOperations" not in cm_contract
    assert "pythonApi" not in cm_contract
    assert api_contract["schemaVersion"] == "1.0"
    assert api_contract["factory"] == "cmail:create_api"
    assert set(api_contract["operations"]) >= {"folders", "messages", "move", "execute-send"}


def test_component_and_python_api_have_separate_entry_points():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    entry_points = project["entry-points"]
    assert entry_points["crania_agent.components"] == {"cmail": "cmail.cm:describe"}
    assert entry_points["crania_agent.component_apis"] == {"cmail": "cmail.api:create_api"}
    assert callable(describe)
    assert callable(__import__("cmail.api", fromlist=["create_api"]).create_api)


def test_web_requires_csrf(tmp_path):
    selected = config(tmp_path)
    app = create_app(selected, MailService(selected, FakeMail()))
    app.testing = True
    client = app.test_client()
    assert client.get("/health").json["ok"] is True
    assert client.post("/api/send/prepare", json={}).status_code == 403
    page = client.get("/")
    token = page.text.split('data-csrf="', 1)[1].split('"', 1)[0]
    response = client.post("/api/send/prepare", headers={"X-CSRF-Token": token},
                           json={"recipients": ["a@example.com"], "subject": "A", "body": "B"})
    assert response.json["ok"] is True


def test_setup_configures_one_imap_account_without_secret_in_json(tmp_path):
    write_config(tmp_path, config_payload_v11())
    selected = Config.load(tmp_path)
    with pytest.raises(PermissionError, match="Configure a única conta"):
        MailService(selected).folders(Principal.local_operator())
    restarted = []
    app = create_app(selected, restart_callback=lambda: restarted.append(True))
    app.testing = True
    client = app.test_client()
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
    webmail.testing = True
    imap_client = webmail.test_client()
    assert imap_client.get("/").status_code == 200
    assert imap_client.get("/api/folders").status_code == 200
    assert imap_client.get("/setup").status_code == 200


def test_setup_rejects_mutation_without_csrf(tmp_path):
    write_config(tmp_path, config_payload_v11())
    app = create_app(Config.load(tmp_path)); app.testing = True
    assert app.test_client().post("/setup", data={}).status_code == 403


class FakeOAuthClient:
    def __init__(self, path: Path, tenant: str = "tenant-lakatos"):
        self.path = path
        self.tenant = tenant
        self.requested_scopes = []

    def initiate_auth_code_flow(self, scopes, redirect_uri):
        self.requested_scopes = list(scopes)
        return {"state": "state-123", "auth_uri": "https://login.microsoft.test/authorize", "redirect_uri": redirect_uri}

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"protected-fake-cache")
        return {"access_token": "access-never-persisted", "id_token_claims": {
            "tid": self.tenant, "oid": "person-1", "preferred_username": "pessoa@empresa.test", "name": "Pessoa"
        }}

    def get_accounts(self, username=None): return [{"username": username}]
    def acquire_token_silent(self, scopes, account): return {"access_token": "access-in-memory"}


class FakeOAuthFactory:
    def __init__(self): self.clients = []
    def __call__(self, config, path):
        client = FakeOAuthClient(path, config.microsoft_tenant_id)
        self.clients.append(client)
        return client


def microsoft_config(tmp_path: Path) -> Config:
    secret = tmp_path / "client-secret.txt"
    secret.write_text("fictitious-test-secret", encoding="utf-8")
    payload = config_payload("microsoft")
    payload["microsoft"] = {
        "clientId": "client-test", "tenantId": "tenant-lakatos",
        "clientSecretFile": "client-secret.txt",
        "redirectUri": "http://127.0.0.1:8020/auth/microsoft/callback",
    }
    write_config(tmp_path, payload)
    return Config.load(tmp_path)


def authenticated_client(tmp_path: Path):
    selected = microsoft_config(tmp_path)
    factory = FakeOAuthFactory()
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=factory)
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    app = create_app(selected, service); app.testing = True
    client = app.test_client()
    login = client.get("/auth/microsoft")
    assert login.status_code == 302
    assert factory.clients[0].requested_scopes == list(MAIL_SCOPES)
    assert "offline_access" not in factory.clients[0].requested_scopes
    callback = client.get("/auth/microsoft/callback?state=state-123&code=fake-code")
    assert callback.status_code == 303
    return selected, service, client


def gmail_config(tmp_path: Path) -> Config:
    secret = tmp_path / "google-secret.txt"
    secret.write_text("fictitious-google-secret", encoding="utf-8")
    payload = config_payload_v11("gmail")
    payload["google"] = {
        "account": "pessoa@gmail.test", "clientId": "google-client",
        "clientSecretFile": "google-secret.txt",
        "redirectUri": "http://127.0.0.1:8020/auth/google/callback",
    }
    write_config(tmp_path, payload)
    return Config.load(tmp_path)


def test_gmail_oauth_is_mandatory_and_bound_to_single_account(tmp_path):
    calls = []
    def requester(method, url, headers, body):
        calls.append((method, url, headers, body))
        if url.endswith("/token"):
            return 200, {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}
        if "userinfo" in url:
            return 200, {"sub": "google-subject", "email": "pessoa@gmail.test", "email_verified": True, "name": "Pessoa"}
        if url.endswith("/profile"):
            return 200, {"emailAddress": "pessoa@gmail.test"}
        if url.endswith("/labels"):
            return 200, {"labels": [{"id": "INBOX", "name": "Entrada", "messagesUnread": 2}]}
        return 404, {}
    selected = gmail_config(tmp_path)
    auth = GoogleAuthService(selected, Store(selected.state_dir), requester=requester)
    service = MailService(selected, auth=auth)
    app = create_app(selected, service); app.testing = True
    client = app.test_client()
    assert client.get("/").headers["location"].endswith("/auth/google")
    login = client.get("/auth/google")
    assert login.status_code == 302
    query = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
        __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(login.headers["location"]).query
    )
    assert set(query["scope"][0].split()) == set(GMAIL_SCOPES)
    callback = client.get(f"/auth/google/callback?state={query['state'][0]}&code=fake")
    assert callback.status_code == 303
    assert client.get("/api/folders").json["folders"][0]["id"] == "INBOX"
    assert all("pessoa@gmail.test" not in str(body) for method, url, headers, body in calls if url.endswith("/token"))


def test_microsoft_login_protects_routes_and_replay(tmp_path):
    selected = microsoft_config(tmp_path)
    factory = FakeOAuthFactory()
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=factory)
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    app = create_app(selected, service); app.testing = True
    client = app.test_client()
    assert client.get("/api/folders").status_code == 401
    assert client.get("/auth/microsoft").status_code == 302
    assert client.get("/auth/microsoft/callback?state=state-123&code=fake").status_code == 303
    assert client.get("/api/folders").status_code == 200
    assert client.get("/auth/microsoft/callback?state=state-123&code=replay").status_code == 401
    assert app.test_client().get("/api/folders").status_code == 401


def test_microsoft_session_csrf_logout_and_csp(tmp_path):
    _selected, _service, client = authenticated_client(tmp_path)
    page = client.get("/")
    assert "pessoa@empresa.test" in page.text
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.post("/api/lists", json={}).status_code == 403
    csrf = client.get_cookie("cmail_csrf").value
    saved = client.post("/api/lists", headers={"X-CSRF-Token": csrf}, json={
        "name": "Equipe", "recipients": [{"address": "a@example.com"}]
    })
    assert saved.status_code == 200
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}, json={}).status_code == 200
    assert client.get("/api/folders").status_code == 401


def test_lists_are_isolated_by_principal(tmp_path):
    selected = config(tmp_path)
    service = MailService(selected, FakeMail())
    alpha = Principal("alpha", "alpha@example.com", frozenset({MANAGE_LISTS, READ_MAIL}))
    beta = Principal("beta", "beta@example.com", frozenset({MANAGE_LISTS, READ_MAIL}))
    service.save_list(alpha, "Equipe", [{"address": "a@example.com"}])
    service.save_list(beta, "Equipe", [{"address": "b@example.com"}])
    assert service.lists(alpha)[0]["recipients"] == 1
    assert service.lists(beta)[0]["recipients"] == 1
    assert service.store.list_recipients(service.lists(alpha)[0]["id"], "beta") == []


def test_frontend_does_not_render_api_values_with_inner_html():
    script = Path("cmail/static/app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "textContent" in script


class FakeTokenAuth:
    def access_token(self, identity_id):
        assert identity_id == "identity-1"
        return "memory-only-token"


def test_graph_provider_uses_only_me_routes_and_normalizes_mail():
    calls = []
    def requester(method, path, token, payload, headers):
        calls.append((method, path, token, payload, headers))
        if "mailFolders?" in path:
            return 200, {"value": [{"id": "folder-1", "displayName": "Entrada", "unreadItemCount": 2}]}
        if "messages?" in path:
            return 200, {"value": [{
                "id": "message-1", "subject": "<img src=x onerror=alert(1)>",
                "from": {"emailAddress": {"name": "<b>Remetente</b>", "address": "a@example.com"}},
                "bodyPreview": "Resumo", "isRead": False,
            }]}
        if method == "PATCH": return 200, {"id": "message-1", "isRead": True}
        if path.endswith("/move"): return 200, {"id": "message-2"}
        if path == "/me/sendMail": return 202, {}
        return 200, {}
    selected = MicrosoftGraphProvider(FakeTokenAuth(), "identity-1", requester=requester)
    assert selected.folders()[0]["unread"] == 2
    message = selected.messages("folder-1")[0]
    assert message["subject"].startswith("<img")
    assert selected.set_read("message-1", True)["isRead"] is True
    assert selected.move("message-1", "folder-2")["moved"] is True
    assert selected.send(["a@example.com"], "Assunto", "Corpo")["accepted"] is True
    assert all(path.startswith("/me/") for _, path, *_ in calls)
    assert all(token == "memory-only-token" for _, _, token, *_ in calls)


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


def test_blueprint_can_be_mounted_under_host_prefix(tmp_path):
    selected = config(tmp_path)
    app = create_app(selected, MailService(selected, FakeMail()), url_prefix="/tools/mail")
    app.testing = True
    client = app.test_client()
    page = client.get("/tools/mail/")
    assert page.status_code == 200
    assert 'data-base="/tools/mail"' in page.text
    assert client.get("/tools/mail/static/style.css").status_code == 200


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


def test_msal_client_explicitly_excludes_offline_access(tmp_path, monkeypatch):
    selected = microsoft_config(tmp_path)
    captured = {}
    class FakePersistence:
        def __init__(self, path): captured["path"] = path
    class FakeCache:
        def __init__(self, persistence): captured["persistence"] = persistence
    class FakeConfidentialClient:
        def __init__(self, client_id, **kwargs): captured.update(client_id=client_id, **kwargs)
    monkeypatch.setitem(sys.modules, "msal", types.SimpleNamespace(ConfidentialClientApplication=FakeConfidentialClient))
    monkeypatch.setitem(sys.modules, "msal_extensions", types.SimpleNamespace(
        FilePersistenceWithDataProtection=FakePersistence, PersistedTokenCache=FakeCache,
    ))
    build_microsoft_client(selected, tmp_path / "cache.bin")
    assert captured["exclude_scopes"] == ["offline_access"]
    assert captured["authority"].endswith("/tenant-lakatos")
