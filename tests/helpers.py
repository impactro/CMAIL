"""Synthetic configuration and fake providers shared by focused test suites."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient
from cmail.auth import MAIL_SCOPES, MicrosoftAuthService
from cmail.config import Config
from cmail.service import MailService
from cmail.store import Store
from cmail.web import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeMail:
    def __init__(self): self.sent = []
    def status(self): return {"connected": True}
    def folders(self): return [{"id": "INBOX", "name": "Entrada"}]
    def messages(self, folder, limit=50): return []
    def message(self, folder, identifier): return {}
    def send(self, recipients, subject, body):
        self.sent.append((recipients, subject, body))
        return {"accepted": True, "recipientCount": len(recipients)}
    def availability(self, schedules, start, end, time_zone, interval):
        return {"schedules": schedules, "count": len(schedules), "timeZone": time_zone,
                "intervalMinutes": interval, "start": start, "end": end}


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


class FakeOAuthClient:
    def __init__(self, path: Path, tenant: str = "tenant-lakatos"):
        self.path = path
        self.tenant = tenant
        self.requested_scopes = []

    def initiate_auth_code_flow(self, scopes, redirect_uri, state=None):
        self.requested_scopes = list(scopes)
        selected_state = str(state or "state-123")
        return {
            "state": selected_state,
            "auth_uri": f"https://login.microsoft.test/authorize?state={selected_state}",
            "redirect_uri": redirect_uri,
        }

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"protected-fake-cache")
        return {"access_token": "access-never-persisted", "id_token_claims": {
            "tid": self.tenant, "oid": "person-1", "preferred_username": "pessoa@empresa.test", "name": "Pessoa"
        }}

    def get_accounts(self, username=None): return [{"username": username}]
    def acquire_token_silent_with_error(self, scopes, account): return {"access_token": "access-in-memory"}


class FakeOAuthFactory:
    def __init__(self): self.clients = []
    def __call__(self, config, path):
        client = FakeOAuthClient(path, config.microsoft_tenant_id)
        self.clients.append(client)
        return client


def microsoft_state(response) -> str:
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def microsoft_config(tmp_path: Path, account: str = "") -> Config:
    secret = tmp_path / "client-secret.txt"
    secret.write_text("fictitious-test-secret", encoding="utf-8")
    payload = config_payload_v11("microsoft")
    payload["microsoft"] = {
        "account": account, "clientId": "client-test", "tenantId": "tenant-lakatos",
        "clientSecretFile": "client-secret.txt",
        "redirectUri": "http://localhost:8020/auth/callback",
    }
    write_config(tmp_path, payload)
    return Config.load(tmp_path)


def authenticated_client(tmp_path: Path):
    selected = microsoft_config(tmp_path)
    factory = FakeOAuthFactory()
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=factory)
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    app = create_app(selected, service)
    client = TestClient(app, follow_redirects=False)
    login = client.get("/auth/microsoft")
    assert login.status_code == 302
    assert factory.clients[0].requested_scopes == list(MAIL_SCOPES)
    assert "offline_access" not in factory.clients[0].requested_scopes
    callback = client.get(f"/auth/callback?state={microsoft_state(login)}&code=fake-code")
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


class FakeTokenAuth:
    def access_token(self, identity_id):
        assert identity_id == "identity-1"
        return "memory-only-token"
