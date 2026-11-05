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

