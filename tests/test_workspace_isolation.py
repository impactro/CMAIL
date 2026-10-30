"""Focused workspace isolation regression tests."""
import re
import pytest
from fastapi.testclient import TestClient
from cmail.auth import AuthenticationError, MicrosoftAuthService
from cmail.api import CmailApi
from cmail.service import MANAGE_LISTS, READ_MAIL, MailService, Principal
from cmail.store import Store
from cmail.web import create_app, create_component_app
from helpers import (FakeMail, FakeOAuthClient, FakeOAuthFactory, config, microsoft_config, microsoft_state)


def test_embedded_mode_isolates_mailboxes_and_local_state_by_workspace(tmp_path):
    selected = microsoft_config(tmp_path)

    class WorkspaceOAuthClient(FakeOAuthClient):
        def __init__(self, path, tenant, sequence):
            super().__init__(path, tenant)
            self.sequence = sequence

        def acquire_token_by_auth_code_flow(self, flow, auth_response):
            result = super().acquire_token_by_auth_code_flow(flow, auth_response)
            result["id_token_claims"]["oid"] = f"person-{self.sequence}"
            result["id_token_claims"]["preferred_username"] = (
                f"pessoa{self.sequence}@empresa.test"
            )
            return result

    class WorkspaceOAuthFactory:
        def __init__(self):
            self.sequence = 0

        def __call__(self, config, path):
            self.sequence += 1
            return WorkspaceOAuthClient(
                path,
                config.microsoft_tenant_id,
                self.sequence,
            )

    def resolver(request):
        workspace = str(request.headers.get("X-Test-Workspace") or "")
        if workspace not in {"workspace-a", "workspace-b"}:
            raise AuthenticationError("Workspace não autenticado pelo host.")
        return {
            "identifier": workspace,
            "email": f"{workspace}@host.test",
            "capabilities": ["mail.read", "mail.manage", "mail.send", "lists.manage"],
        }

    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(
        selected,
        store,
        client_factory=WorkspaceOAuthFactory(),
    )
    service = MailService(
        selected,
        auth=auth,
        graph_factory=lambda _auth, _identity: FakeMail(),
    )
    app = create_app(selected, service, principal_resolver=resolver)
    client_a = TestClient(
        app,
        follow_redirects=False,
        headers={"X-Test-Workspace": "workspace-a"},
    )
    client_b = TestClient(
        app,
        follow_redirects=False,
        headers={"X-Test-Workspace": "workspace-b"},
    )

    first_page = client_a.get("/")
    assert first_page.status_code == 200
    assert 'target="_top"' in first_page.text
    assert client_a.get("/api/folders").status_code == 401
    assert client_a.get("/health").json()["singleAccount"] is False
    assert client_a.get("/setup").status_code == 404

    login_a = client_a.get("/auth/microsoft")
    assert login_a.status_code == 302
    assert client_a.get(f"/auth/callback?state={microsoft_state(login_a)}&code=a").status_code == 303
    assert client_a.get("/api/folders").status_code == 200
    assert client_b.get("/api/folders").status_code == 401

    login_b = client_b.get("/auth/microsoft")
    assert login_b.status_code == 302
    assert client_b.get(f"/auth/callback?state={microsoft_state(login_b)}&code=b").status_code == 303
    assert client_b.get("/api/folders").status_code == 200

    identity_a = store.bound_identity("microsoft", "workspace-a")
    identity_b = store.bound_identity("microsoft", "workspace-b")
    assert identity_a and identity_b and identity_a["id"] != identity_b["id"]

    page_a = client_a.get("/")
    csrf_a = re.search(r'data-csrf="([^"]+)"', page_a.text).group(1)
    saved = client_a.post(
        "/api/lists",
        headers={"X-CSRF-Token": csrf_a},
        json={"name": "Equipe A", "recipients": [{"address": "a@example.com"}]},
    )
    assert saved.status_code == 200
    assert len(store.lists("workspace-a")) == 1
    assert store.lists("workspace-b") == []
    api = CmailApi(service)
    assert api.connection_status("workspace-a")["state"] == "connected"
    disconnected = api.disconnect_owner("workspace-a")
    assert disconnected["state"] == "disabled"
    assert disconnected["authorized"] is False
    assert client_a.get("/api/folders").status_code == 401


def test_owner_connection_status_and_webmail_preference_are_independent(tmp_path):
    selected = microsoft_config(tmp_path)
    store = Store(selected.state_dir)
    auth = MicrosoftAuthService(selected, store, client_factory=FakeOAuthFactory())
    service = MailService(selected, auth=auth, graph_factory=lambda _auth, _identity: FakeMail())
    api = CmailApi(service)

    initial = api.connection_status("workspace-a")
    assert initial == {
        "provider": "outlook", "state": "disconnected", "authorized": False,
        "requiresReconnect": False, "email": "", "webmailEnabled": True,
        "canAuthorize": True,
    }
    disabled = api.set_webmail_enabled("workspace-a", False)
    assert disabled["webmailEnabled"] is False
    assert disabled["state"] == "disconnected"
    assert Store(selected.state_dir).webmail_enabled("workspace-a") is False


def test_embedded_disabled_webmail_blocks_ui_but_not_python_api(tmp_path):
    selected = config(tmp_path)
    service = MailService(selected, FakeMail())
    service.set_webmail_enabled("workspace-a", False)

    def resolver(_request):
        return {
            "identifier": "workspace-a", "email": "a@example.com",
            "capabilities": ["mail.read"],
        }

    client = TestClient(
        create_app(selected, service, principal_resolver=resolver),
        follow_redirects=False,
    )
    page = client.get("/")
    assert page.status_code == 200
    assert "Webmail desabilitado" in page.text
    assert client.get("/api/folders").status_code == 403
    principal = CmailApi(service).principal_for_owner("workspace-a", frozenset({"mail.read"}))
    assert CmailApi(service).folders(principal)[0]["id"] == "INBOX"


def test_embedded_oauth_success_path_is_relative_and_validated(tmp_path):
    selected = microsoft_config(tmp_path)
    factory = FakeOAuthFactory()
    service = MailService(
        selected,
        auth=MicrosoftAuthService(selected, Store(selected.state_dir), client_factory=factory),
        graph_factory=lambda _auth, _identity: FakeMail(),
    )

    def resolver(_request):
        return {"identifier": "workspace-a", "email": "a@example.com", "capabilities": ["mail.read"]}

    client = TestClient(
        create_app(
            selected, service, principal_resolver=resolver,
            oauth_success_path="/?embedded=cmail",
        ),
        follow_redirects=False,
    )
    login = client.get("/auth/microsoft")
    callback = client.get(f"/auth/callback?state={microsoft_state(login)}&code=fake")
    assert callback.status_code == 303
    assert callback.headers["location"] == "/?embedded=cmail"

    config_file = tmp_path / "cmail.json"
    with pytest.raises(ValueError, match="caminho relativo"):
        create_component_app(
            tmp_path,
            {
                "configFile": config_file,
                "principalResolvers": {"cmail": resolver},
                "oauthSuccessPath": "https://evil.example.test/return",
            },
        )


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
