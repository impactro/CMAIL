"""Microsoft IMAP/SMTP XOAUTH2: conta fixa, MSAL público e cache DPAPI.

Não usa Graph, senha, navegador automático ou fallback de transporte.
"""
from __future__ import annotations

import argparse
import json
import smtplib
import ssl
import threading
import time
from pathlib import Path
from uuid import UUID

from .auth import AuthenticationError
from .config import Config
from .mail import ImapSmtpProvider

SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All",
          "https://outlook.office.com/SMTP.Send"]


class MicrosoftImapAuth:
    def __init__(self, config, *, client_factory=None):
        if config.mode != "microsoft-imap":
            raise ValueError("Selecione explicitamente microsoft-imap.")
        UUID(config.microsoft_tenant_id)
        UUID(config.microsoft_client_id)
        self.config = config
        self.path = config.state_dir / "oauth/microsoft-imap.dpapi"
        self.lock = threading.Lock()
        self.client_factory = client_factory or self._client

    def _persistence(self, *, flow=False):
        from msal_extensions import FilePersistenceWithDataProtection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return FilePersistenceWithDataProtection(str(self.path) + (".flow" if flow else ""))

    def start_login(self):
        """Consentimento explícito do operador; segredo device_code só em DPAPI."""
        flow = self.client_factory().initiate_device_flow(scopes=SCOPES)
        if not flow.get("device_code") or not flow.get("user_code"):
            raise AuthenticationError("Microsoft não iniciou a autenticação por dispositivo.")
        self._persistence(flow=True).save(json.dumps(flow))
        return {"verificationUri": "https://microsoft.com/devicelogin",
                "userCode": flow["user_code"], "expiresIn": flow.get("expires_in"),
                "account": self.config.account}

    def finish_login(self):
        flow = json.loads(self._persistence(flow=True).load())
        # Cada execução é limitada; o mesmo fluxo pode ser retomado até expirar.
        deadline = time.monotonic() + 45
        app = self.client_factory()
        result = app.acquire_token_by_device_flow(flow,
            exit_condition=lambda _: time.monotonic() >= deadline)
        if not result or not result.get("access_token"):
            raise AuthenticationError("Autenticação pendente ou recusada pela Microsoft.")
        claims = result.get("id_token_claims", {})
        username = str(claims.get("preferred_username") or claims.get("upn") or "")
        if (username.casefold() != self.config.account.casefold()
                or str(claims.get("tid", "")).casefold() != self.config.microsoft_tenant_id.casefold()):
            for account in app.get_accounts():
                if str(account.get("username", "")).casefold() == username.casefold():
                    app.remove_account(account)
            raise AuthenticationError("Login concluído com outra identidade; conta recusada.")
        Path(str(self.path) + ".flow").unlink(missing_ok=True)
        return {"authenticated": True, "account": self.config.account}

    def _client(self):
        from msal import PublicClientApplication
        from msal_extensions import PersistedTokenCache
        return PublicClientApplication(
            self.config.microsoft_client_id,
            authority="https://login.microsoftonline.com/" + self.config.microsoft_tenant_id,
            token_cache=PersistedTokenCache(self._persistence()))

    def access_token(self):
        try:
            with self.lock:
                if not self.path.is_file():
                    raise ValueError("cache ausente")
                app = self.client_factory()
                accounts = [a for a in app.get_accounts()
                            if str(a.get("username", "")).casefold() == self.config.account.casefold()
                            and str(a.get("realm", "")).casefold() == self.config.microsoft_tenant_id.casefold()]
                if len(accounts) != 1:
                    raise ValueError("identidade divergente")
                result = app.acquire_token_silent_with_error(SCOPES, account=accounts[0])
                if not result or not result.get("access_token"):
                    raise ValueError("renovação recusada")
                return result["access_token"]
        except Exception:
            raise AuthenticationError("Microsoft IMAP/SMTP exige autorização válida da conta configurada; detalhe sensível omitido.") from None

    def import_omail(self, source):
        """Migração explícita, uma vez, sem alterar a origem ou criar login."""
        import msal
        if self.path.exists():
            raise ValueError("Cache de destino já existe; não sobrescrever autorização.")
        source = Path(source).resolve()
        if source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Cache de origem excede o limite.")
        value = json.loads(source.read_text("utf-8-sig"))
        if (value.get("version") != "omail-msal-cache-v1"
                or str(value.get("client_id", "")).casefold() != self.config.microsoft_client_id.casefold()
                or str(value.get("tenant_id", "")).casefold() != self.config.microsoft_tenant_id.casefold()
                or str(value.get("address", "")).casefold() != self.config.account.casefold()
                or not set(SCOPES).issubset(set(value.get("scopes", [])))):
            raise ValueError("Origem OMAIL diverge da conta, aplicativo, tenant ou escopos configurados.")
        cache = msal.SerializableTokenCache()
        cache.deserialize(value["cache"])
        accounts = list(cache.find(msal.TokenCache.CredentialType.ACCOUNT))
        if (len(accounts) != 1
                or str(accounts[0].get("username", "")).casefold() != self.config.account.casefold()
                or str(accounts[0].get("realm", "")).casefold() != self.config.microsoft_tenant_id.casefold()
                or accounts[0].get("environment") != "login.microsoftonline.com"):
            raise ValueError("Cache OMAIL não confirma uma única identidade do tenant esperado.")
        self._persistence().save(cache.serialize())
        return {"imported": True, "encrypted": True, "sourceUnchanged": True}


class MicrosoftImapProvider(ImapSmtpProvider):
    def __init__(self, config, *, auth=None, **kwargs):
        super().__init__(config, **kwargs)
        self.auth = auth or MicrosoftImapAuth(config)

    def _imap_login(self, client):
        token = self.auth.access_token()
        called = False
        def response(challenge):
            nonlocal called
            if called:
                return b""
            called = True
            return f"user={self.config.account}\x01auth=Bearer {token}\x01\x01".encode("utf-8")
        try:
            code, _ = client.authenticate("XOAUTH2", response)
            if code != "OK":
                raise ValueError("auth recusado")
        except Exception:
            raise AuthenticationError("Microsoft recusou autenticação IMAP/XOAUTH2.") from None

    def _smtp_login(self, client):
        token = self.auth.access_token()
        try:
            if client.ehlo()[0] != 250:
                raise ValueError("ehlo recusado")
            code, _ = client.auth("XOAUTH2", lambda challenge=None:
                f"user={self.config.account}\x01auth=Bearer {token}\x01\x01" if challenge is None else "")
            if code != 235:
                raise ValueError("auth recusado")
        except Exception:
            raise AuthenticationError("Microsoft recusou autenticação SMTP/XOAUTH2; conferir política SMTP AUTH da caixa.") from None

    def status(self):
        # Apenas login IMAP e AUTH/NOOP SMTP; nunca MAIL/RCPT/DATA.
        super().status()
        client = self.smtp_factory(self.config.smtp_host, self.config.smtp_port, timeout=30)
        try:
            client.starttls(context=ssl.create_default_context())
            self._smtp_login(client)
            if client.noop()[0] != 250:
                raise AuthenticationError("Microsoft SMTP recusou NOOP.")
        finally:
            try:
                client.quit()
            except Exception:
                pass
        return {"provider": "microsoft-imap", "connected": True,
                "account": self.config.account, "transport": "imap-smtp-xoauth2",
                "imapAuthenticated": True, "smtpAuthenticated": True, "externalEffects": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--agent-root", required=True, type=Path)
    parser.add_argument("action", choices=["import-omail", "status", "auth-start", "auth-finish"])
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    try:
        config = Config.from_file(args.config, root=args.agent_root)
        auth = MicrosoftImapAuth(config)
        if args.action == "import-omail":
            if not args.source:
                raise ValueError("Informe --source.")
            result = auth.import_omail(args.source)
        elif args.action == "auth-start":
            result = auth.start_login()
        elif args.action == "auth-finish":
            result = auth.finish_login()
        else:
            result = MicrosoftImapProvider(config, auth=auth).status()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "errorType": type(error).__name__,
                          "error": "Operação Microsoft IMAP não concluída; origem e cache preservados."}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
