"""Focused component contracts regression tests."""
import json
import re
from fastapi.testclient import TestClient
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from cmail.cm import describe
from cmail.api import CmailApi, create_component_api
from cmail.service import MailService, Principal
from cmail.web import create_component_app
from helpers import (FakeMail, PROJECT_ROOT, config, config_payload)


def test_component_app_uses_host_config_file_without_parsing_agent_env(tmp_path):
    config_file = tmp_path / "module" / "cmail.json"
    config_file.parent.mkdir()
    config_file.write_text(json.dumps(config_payload()), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "AI_TYPE=codex\nCMAIL_CONFIG_FILE=module/cmail.json\n",
        encoding="utf-8",
    )
    app = create_component_app(tmp_path, {"configFile": config_file})
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["framework"] == "fastapi"


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
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    entry_points = project["entry-points"]
    assert entry_points["crania_agent.components"] == {"cmail": "cmail.cm:describe"}
    assert entry_points["crania_agent.component_apis"] == {"cmail": "cmail.api:create_component_api"}
    assert callable(describe)
    assert callable(__import__("cmail.api", fromlist=["create_api"]).create_api)


def test_component_api_uses_host_config_and_system_sender(tmp_path):
    config_file = tmp_path / "module" / "cmail.json"
    config_file.parent.mkdir()
    config_file.write_text(json.dumps(config_payload()), encoding="utf-8")
    api = create_component_api(tmp_path, {"configFile": config_file})
    result = api.system_send("workspace-a", "a@example.com", "Assunto", "Corpo")
    assert result["demo"] is True
    assert api.principal_for_owner("workspace-a").storage_owner == "workspace-a"


def test_api_owns_audit_history_and_calendar_availability(tmp_path):
    selected = config(tmp_path)
    service = MailService(selected, FakeMail())
    api = CmailApi(service)
    principal = Principal(
        "local", "local@example.com",
        frozenset({"mail.read", "mail.manage", "mail.send"}), "workspace-a",
    )
    availability = api.availability(
        principal, ["a@example.com"], "2026-09-12T08:00:00",
        "2026-09-12T09:00:00", "E. South America Standard Time", 30,
    )
    assert availability["count"] == 1
    service.store.record_action("fixture", "completed", {"safe": True}, "workspace-a")
    history = api.history(principal)
    assert history[0]["action"] == "fixture"
    assert history[0]["detail"] == {"safe": True}
