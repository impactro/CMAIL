"""Focused web oauth regression tests."""
import pytest
import json
import sys
import types
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cmail.auth import MicrosoftAuthService, build_microsoft_client
from cmail.gmail import GMAIL_SCOPES, GoogleAuthService
from cmail.service import MailService
from cmail.store import Store
from cmail.web import create_app, create_component_app
from helpers import (FakeMail, FakeOAuthFactory, authenticated_client, config_payload_v11, gmail_config, microsoft_config, microsoft_state)


def test_embedded_microsoft_registers_callback_and_keeps_oauth_out_of_iframe(tmp_path):
    secret = tmp_path / "module" / "client-secret.txt"
    secret.parent.mkdir()
    secret.write_text("fictitious-test-secret", encoding="utf-8")
    payload = config_payload_v11("microsoft")
    payload["server"]["cookieSecure"] = True
    payload["microsoft"] = {
        "account": "",
        "clientId": "client-test",
        "tenantId": "tenant-lakatos",
        "clientSecretFile": "client-secret.txt",
        "redirectUri": "https://lia.example.test/auth/callback",
    }
    config_file = tmp_path / "module" / "cmail.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    registered = []

    def resolver(_request):
        return {
            "identifier": "workspace-a",
            "email": "pessoa@empresa.test",
            "capabilities": ["mail.read"],
        }

    app = create_component_app(
        tmp_path,
        {
            "configFile": config_file,
            "principalResolvers": {"cmail": resolver},
            "registerOAuthCallback": lambda **value: registered.append(value),
        },
    )
    assert registered == [{
        "component_id": "cmail",
        "state_prefix": "cmail.",
        "callback_path": "/cm/cmail/auth/callback",
    }]
    response = TestClient(
        app,
        base_url="https://lia.example.test",
        follow_redirects=False,
    ).get("/")
    assert response.status_code == 200
    assert 'target="_top"' in response.text
    assert "/auth/microsoft" in response.text

    host = FastAPI()
    host.mount("/cm/cmail", app, name="cm-cmail")
    mounted = TestClient(
        host,
        base_url="https://lia.example.test",
        follow_redirects=False,
    ).get("/cm/cmail/")
    assert mounted.status_code == 200
    assert 'href="/cm/cmail/auth/microsoft" target="_top"' in mounted.text


def test_store_binds_first_verified_oauth_identity_until_reconfigured(tmp_path):
    store = Store(tmp_path / "instance-a" / "state")
    first = store.save_identity(
        "tenant", "subject-1", "primeira@empresa.test", "Primeira",
        enforce_single_account=True,
    )
    rejected = store.save_identity(
        "tenant", "subject-2", "segunda@empresa.test", "Segunda",
        enforce_single_account=True,
    )
    assert first["email"] == "primeira@empresa.test"
    assert rejected == {}

    store.reset_oauth_identities()
    second = store.save_identity(
        "tenant", "subject-2", "segunda@empresa.test", "Segunda",
        enforce_single_account=True,
    )
    assert second["email"] == "segunda@empresa.test"

    other_instance = Store(tmp_path / "instance-b" / "state")
    independent = other_instance.save_identity(
        "tenant", "subject-1", "primeira@empresa.test", "Primeira",
        enforce_single_account=True,
    )
    assert independent["email"] == "primeira@empresa.test"
    assert store.bound_identity("microsoft")["email"] == "segunda@empresa.test"
    assert other_instance.bound_identity("microsoft")["email"] == "primeira@empresa.test"


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
    app = create_app(selected, service)
    client = TestClient(app, follow_redirects=False)
    assert client.get("/").headers["location"].endswith("/auth/google")
    login = client.get("/auth/google")
    assert login.status_code == 302
    query = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
        __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(login.headers["location"]).query
    )
    assert set(query["scope"][0].split()) == set(GMAIL_SCOPES)
    callback = client.get(f"/auth/google/callback?state={query['state'][0]}&code=fake")
    assert callback.status_code == 303
    assert client.get("/api/folders").json()["folders"][0]["id"] == "INBOX"
    assert all("pessoa@gmail.test" not in str(body) for method, url, headers, body in calls if url.endswith("/token"))


def test_microsoft_login_protects_routes_and_replay(tmp_path):
    selected = microsoft_config(tmp_path)
    factory = FakeOAuthFactory()
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=factory)
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    app = create_app(selected, service)
    client = TestClient(app, follow_redirects=False)
    assert client.get("/api/folders").status_code == 401
    login = client.get("/auth/microsoft")
    assert login.status_code == 302
    state = microsoft_state(login)
    assert state.startswith("cmail.")
    assert client.get(f"/auth/callback?state={state}&code=fake").status_code == 303
    assert client.get("/api/folders").status_code == 200
    assert client.get(f"/auth/callback?state={state}&code=replay").status_code == 401
    assert TestClient(app, follow_redirects=False).get("/api/folders").status_code == 401


def test_microsoft_account_mismatch_renders_recovery_page_and_preserves_api_json(tmp_path):
    selected = microsoft_config(tmp_path, account="outra@empresa.test")
    factory = FakeOAuthFactory()
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=factory)
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    app = create_app(selected, service)
    client = TestClient(app, follow_redirects=False)

    login = client.get("/auth/microsoft")
    assert login.status_code == 302
    callback = client.get(f"/auth/callback?state={microsoft_state(login)}&code=fake")
    assert callback.status_code == 401
    assert callback.headers["content-type"].startswith("text/html")
    assert "Conta diferente da configurada" in callback.text
    assert "Reconfigurar conta" in callback.text
    assert 'href="/setup"' in callback.text
    assert client.cookies.get("cmail_oauth_browser") is None

    api_error = TestClient(app, follow_redirects=False).get("/api/folders")
    assert api_error.status_code == 401
    assert api_error.headers["content-type"].startswith("application/json")
    assert api_error.json()["ok"] is False


def test_microsoft_session_csrf_logout_and_csp(tmp_path):
    _selected, _service, client = authenticated_client(tmp_path)
    page = client.get("/")
    assert "pessoa@empresa.test" in page.text
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.post("/api/lists", json={}).status_code == 403
    csrf = client.cookies.get("cmail_csrf")
    saved = client.post("/api/lists", headers={"X-CSRF-Token": csrf}, json={
        "name": "Equipe", "recipients": [{"address": "a@example.com"}]
    })
    assert saved.status_code == 200
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}, json={}).status_code == 200
    assert client.get("/api/folders").status_code == 401


@pytest.mark.parametrize("offline_access", [False, True])
def test_msal_client_only_requests_offline_access_after_explicit_opt_in(tmp_path, monkeypatch, offline_access):
    from dataclasses import replace
    selected = microsoft_config(tmp_path)
    selected = replace(selected, microsoft_offline_access=offline_access)
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
    assert captured["exclude_scopes"] == ([] if offline_access else ["offline_access"])
    assert captured["authority"].endswith("/tenant-lakatos")
