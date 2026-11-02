"""Host-owned config validation never parses the host env or initializes mail."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import cmail.__main__ as cli
from cmail.cm import describe
from cmail.config import Config, ConfigError
from helpers import PROJECT_ROOT, config_payload, write_config


def _host(tmp_path, reference="config/cmail.json"):
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "cmail.json").write_text(json.dumps(config_payload()), encoding="utf-8")
    manifest = {"schemaVersion": "2.0", "composition": "test-host", "components": [
        {"id": "cmail", "enabled": True, "operations": ["check-config"]},
    ]}
    (folder / "components.config.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "AI_TYPE=codex\nCA_STORAGE_MODE=sqlite\n"
        + (f"CMAIL_CONFIG_FILE={reference}\n" if reference is not None else ""),
        encoding="utf-8",
    )
    return folder / "cmail.json"


def _forbid_service(monkeypatch):
    service = Mock(side_effect=AssertionError("Validation cannot create mail state"))
    monkeypatch.setattr(cli, "MailService", service)
    return service


def test_host_validation_uses_explicit_pointer_without_parsing_shared_env(tmp_path, monkeypatch, capsys):
    path = _host(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CMAIL_CONFIG_FILE", "config/cmail.json")
    monkeypatch.setattr(Config, "load", Mock(side_effect=AssertionError("No standalone env lookup")))
    service = _forbid_service(monkeypatch)

    assert cli.main(["check-config", "--from-host"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    service.assert_not_called()
    assert not (path.parent / ".state").exists()


def test_host_validation_missing_pointer_does_not_fall_back_to_standalone(tmp_path, monkeypatch):
    write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CMAIL_CONFIG_FILE", raising=False)
    service = _forbid_service(monkeypatch)
    with pytest.raises(ConfigError, match="CMAIL_CONFIG_FILE"):
        cli.main(["check-config", "--from-host"])
    service.assert_not_called()
    assert not (tmp_path / ".state").exists()


@pytest.mark.parametrize("reference", ["missing.json", "invalid.json"])
def test_host_validation_invalid_pointer_never_falls_back(tmp_path, monkeypatch, reference):
    write_config(tmp_path)
    (tmp_path / "invalid.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CMAIL_CONFIG_FILE", reference)
    _forbid_service(monkeypatch)
    with pytest.raises((ConfigError, OSError)):
        cli.main(["check-config", "--from-host"])
    assert not (tmp_path / ".state").exists()


def test_standalone_validation_keeps_its_own_env_and_creates_no_state(tmp_path, monkeypatch, capsys):
    write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    # Ambient host hints must not override standalone's sole canonical .env.
    monkeypatch.setenv("CMAIL_CONFIG_FILE", "does-not-exist.json")
    _forbid_service(monkeypatch)
    assert cli.main(["check-config"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert not (tmp_path / ".state").exists()


@pytest.mark.parametrize("reference", ["config/cmail.json", None, "missing.json", "invalid.json"])
def test_component_manager_validates_the_same_host_contract(tmp_path, monkeypatch, reference):
    components = pytest.importorskip("ca.components")
    config_file = _host(tmp_path, reference=reference)
    (tmp_path / "invalid.json").write_text("{}", encoding="utf-8")
    entry = SimpleNamespace(name="cmail", value="cmail.cm:describe", load=lambda: describe)
    monkeypatch.setattr(components, "_entry_points_for_group", lambda: [entry])
    # Exercise the current checkout in a real child without installing it.
    environment = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT), CMAIL_CONFIG_FILE="")
    if reference == "config/cmail.json":
        completed = components.invoke_component(tmp_path, "cmail", "check-config", [], environ=environment)
        assert completed.returncode == 0
        assert json.loads(completed.stdout)["ok"] is True
    else:
        with pytest.raises(components.ComponentManagerError) as failure:
            components.invoke_component(tmp_path, "cmail", "check-config", [], environ=environment)
        assert failure.value.code == "CM_EXECUTION_FAILED"
    assert not (config_file.parent / ".state").exists()


def test_host_option_is_not_exposed_on_send_commands():
    assert describe()["operations"]["check-config"]["argv"] == ["check-config", "--from-host"]
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["send-prepare", "--from-host", "--input-json", "mail.json"])


def test_microsoft_send_still_requires_the_authenticated_api(tmp_path, monkeypatch):
    selected = SimpleNamespace(mode="microsoft")
    service = Mock(config=selected)
    monkeypatch.setattr(Config, "load", lambda: selected)
    monkeypatch.setattr(cli, "MailService", lambda _config: service)
    with pytest.raises(ValueError, match="Principal autenticado"):
        cli.main(["send-prepare", "--input-json", str(tmp_path / "mail.json")])
    service.prepare.assert_not_called()
