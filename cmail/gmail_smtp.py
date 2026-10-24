"""Explicit Gmail SMTP/XOAUTH2 sending. No REST dependency or silent fallback."""
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import smtplib
import ssl

from .auth import AuthenticationError
from .gmail_file import GmailFileAuth
from .store import EMAIL
from .inline_images import add_body


class GmailSmtpAuth(GmailFileAuth):
    def __init__(self, config, *, requester=None):
        if config.gmail_file_transport != "smtp":
            raise ValueError("O transporte SMTP deve ser selecionado explicitamente.")
        super().__init__(config, requester=requester)

    def connection(self, token):
        return self.authenticated_connection(self.config.gmail_file_account, token)

    @staticmethod
    @contextmanager
    def authenticated_connection(account, token):
        # Pin the destination: never deliver OAuth credentials to a configurable host.
        client = None
        try:
            client = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
            if client.ehlo()[0] != 250:
                raise AuthenticationError("O Gmail SMTP recusou a conexão.")
            client.starttls(context=ssl.create_default_context())
            if client.ehlo()[0] != 250:
                raise AuthenticationError("O Gmail SMTP recusou a conexão TLS.")
            # SMTP verifies that the OAuth token may access this exact mailbox.
            code, _ = client.auth("XOAUTH2", lambda challenge=None:
                f"user={account}\x01auth=Bearer {token}\x01\x01" if challenge is None else "")
            if code != 235:
                raise AuthenticationError("O Gmail SMTP não confirmou a conta configurada.")
        except Exception:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            raise AuthenticationError("O Gmail SMTP não confirmou a conta configurada ou o TLS.") from None
        try:
            yield client
        finally:
            # DATA's receipt, not a subsequent QUIT, determines send acceptance.
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass

    def _profile(self, token):
        # Called by the shared refresh/cache path. AUTH+NOOP is read-only, not send.
        self.validate_account(self.config.gmail_file_account, token)

    @staticmethod
    def validate_account(account, token):
        try:
            with GmailSmtpAuth.authenticated_connection(account, token) as client:
                if client.noop()[0] != 250:
                    raise AuthenticationError("O Gmail SMTP recusou a validação da conta.")
        except Exception:
            raise AuthenticationError("O Gmail SMTP recusou a validação da conta.") from None

    def status(self, *, refresh=False):
        result = super().status(refresh=refresh)
        return {**result, "provider": "gmail-file-smtp", "transport": "smtp",
                "capabilities": ["send"], "identityValidation": "smtp-xoauth2"}


class GmailSmtpProvider:
    def __init__(self, auth):
        self.auth = auth

    def status(self):
        return {**self.auth.status(), "externalEffects": True}

    def send(self, recipients, subject, body, *, body_html="", inline_images=None):
        if (not recipients or any(not isinstance(x, str) or not x.isascii()
                or not EMAIL.fullmatch(x) for x in recipients)):
            raise ValueError("Destinatários inválidos.")
        message = EmailMessage()
        account = self.auth.config.gmail_file_account
        message["From"] = account
        message["To"] = recipients[0] if len(recipients) == 1 else "undisclosed-recipients:;"
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message["Message-ID"] = make_msgid(domain=account.split("@", 1)[1])
        add_body(message, body, body_html, inline_images)
        token = self.auth.access_token()
        try:
            with self.auth.connection(token) as client:
                refused = client.send_message(message, from_addr=account, to_addrs=recipients)
                if refused:
                    raise ValueError("Recusa parcial de destinatários; resultado incerto, sem repetição.")
        except Exception:
            # Never include SMTP challenge, bearer, raw provider body or recipient map.
            raise ValueError("Envio SMTP não confirmado; resultado incerto, sem repetição.") from None
        return {"accepted": True, "id": str(message["Message-ID"]),
                "recipientCount": len(recipients), "provider": "gmail-file-smtp",
                "delivery": "submitted"}

    def folders(self):
        raise NotImplementedError("O transporte Gmail SMTP oferece somente envio.")

    def messages(self, folder, limit=50):
        raise NotImplementedError("O transporte Gmail SMTP oferece somente envio.")

    def message(self, folder, identifier):
        raise NotImplementedError("O transporte Gmail SMTP oferece somente envio.")
