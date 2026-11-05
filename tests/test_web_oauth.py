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
