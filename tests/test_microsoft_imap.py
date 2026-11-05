import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cmail.config import Config, ConfigError
from cmail.microsoft_imap import MicrosoftImapAuth, MicrosoftImapProvider, SCOPES
from cmail.auth import AuthenticationError
from cmail.service import MailService
from cmail.principal import READ_MAIL

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"


def config(tmp_path):
    value = json.loads((Path(__file__).parents[1]/"cmail/defaults/cmail.config.json").read_text())
    value.update(mode="microsoft-imap")
    value["state"]["directory"] = str(tmp_path/"security/cmail/accounts/outlook-smtp")
    value["microsoft"].update(clientId=CLIENT, tenantId=TENANT, account="a@example.test")
    value["imap"].update(account="a@example.test", username="a@example.test",
                         imapHost="outlook.office365.com", smtpHost="smtp.office365.com")
    return value


@pytest.mark.parametrize("field,value", [("imapHost", "attacker.test"), ("smtpPort", 25),
                                         ("username", "b@example.test"), ("passwordFile", "secret.txt")])
def test_oauth_destination_and_mailbox_cannot_be_substituted(tmp_path, field, value):
    payload = config(tmp_path)
    payload["imap"][field] = value
    with pytest.raises(ConfigError):
        Config.from_mapping(payload, path=tmp_path/"config.json")


def test_silent_auth_selects_only_exact_mailbox_and_tenant(tmp_path):
    cfg = Config.from_mapping(config(tmp_path), path=tmp_path/"config.json")
    app = Mock()
    identity = {"username": cfg.account, "realm": TENANT}
    app.get_accounts.return_value = [identity]
    app.acquire_token_silent_with_error.return_value = {"access_token": "synthetic-token"}
    auth = MicrosoftImapAuth(cfg, client_factory=lambda: app)
    auth.path.parent.mkdir(parents=True)
    auth.path.write_bytes(b"synthetic encrypted cache")
    assert auth.access_token() == "synthetic-token"
    app.acquire_token_silent_with_error.assert_called_once_with(SCOPES, account=identity)
    app.get_accounts.return_value = [{"username": cfg.account, "realm": CLIENT}]
    with pytest.raises(AuthenticationError):
        auth.access_token()
    assert app.acquire_token_silent_with_error.call_count == 1


def test_status_authenticates_both_protocols_without_sending(tmp_path):
    cfg = Config.from_mapping(config(tmp_path), path=tmp_path/"config.json")
    imap, smtp = Mock(), Mock()
    imap.authenticate.return_value = ("OK", [])
    smtp.ehlo.return_value = (250, b"ok")
    smtp.auth.return_value = (235, b"ok")
    smtp.noop.return_value = (250, b"ok")
    auth = SimpleNamespace(access_token=lambda: "synthetic-token")
    provider = MicrosoftImapProvider(cfg, auth=auth, imap_ssl_factory=lambda *a, **kw: imap,
                                     smtp_factory=lambda *a, **kw: smtp)
    assert provider.status()["smtpAuthenticated"]
    assert imap.authenticate.call_args[0][0] == "XOAUTH2"
    imap.login.assert_not_called()
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()
    smtp.starttls.assert_called_once()
    service = MailService(cfg, mail_provider=provider)
    p = service.principal_for_owner("trusted-host-owner", frozenset({READ_MAIL}))
    assert p.email == cfg.account
    assert service.provider_for(p) is provider


def test_import_mismatched_origin_never_creates_cache(tmp_path):
    cfg = Config.from_mapping(config(tmp_path), path=tmp_path/"config.json")
    source = tmp_path/"old.json"
    source.write_text(json.dumps({"version": "omail-msal-cache-v1", "client_id": CLIENT,
        "tenant_id": TENANT, "address": "wrong@example.test", "scopes": SCOPES}))
    auth = MicrosoftImapAuth(cfg)
    with pytest.raises(ValueError):
        auth.import_omail(source)
    assert not auth.path.exists()


def test_device_login_wrong_identity_is_removed_without_acceptance(tmp_path, monkeypatch):
    cfg = Config.from_mapping(config(tmp_path), path=tmp_path/"config.json")
    app = Mock()
    app.acquire_token_by_device_flow.return_value = {"access_token": "synthetic",
        "id_token_claims": {"preferred_username": "other@example.test", "tid": TENANT}}
    other = {"username": "other@example.test"}
    app.get_accounts.return_value = [other]
    auth = MicrosoftImapAuth(cfg, client_factory=lambda: app)
    persistence = Mock()
    persistence.load.return_value = '{}'
    monkeypatch.setattr(auth, '_persistence', lambda **kw: persistence)
    with pytest.raises(AuthenticationError):
        auth.finish_login()
    app.remove_account.assert_called_once_with(other)


def test_device_start_only_returns_public_code_not_device_secret(tmp_path, monkeypatch):
    cfg = Config.from_mapping(config(tmp_path), path=tmp_path/"config.json")
    app = Mock()
    app.initiate_device_flow.return_value = {'device_code': 'private-device-secret',
                                            'user_code': 'PUBLIC', 'expires_in': 900}
    auth = MicrosoftImapAuth(cfg, client_factory=lambda: app)
    persistence = Mock()
    monkeypatch.setattr(auth, '_persistence', lambda **kw: persistence)
    result = auth.start_login()
    assert result['userCode'] == 'PUBLIC'
    assert 'private-device-secret' not in json.dumps(result)
    assert 'private-device-secret' in persistence.save.call_args.args[0]
