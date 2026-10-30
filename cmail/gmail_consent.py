"""Explicit desktop consent using Google OAuth, loopback callback and PKCE."""
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .auth import AuthenticationError
from .google_auth import GOOGLE_AUTH, GOOGLE_TOKEN, GMAIL_API, GMAIL_SCOPES
from .gmail_file import _read_json, _request, _field, _duration, TOKEN_URIS
from .store import EMAIL


class GmailFileConsent:
    def __init__(self, client_file, token_file, account, redirect_uri, *, requester=None, transport="api"):
        if transport not in {"api", "smtp"}:
            raise AuthenticationError("Transporte Gmail inválido.")
        self.transport = transport
        self.scopes = ("https://mail.google.com/",) if transport == "smtp" else GMAIL_SCOPES
        self.account = str(account).strip().casefold()
        self.token_file = Path(token_file)
        parsed = urllib.parse.urlsplit(redirect_uri)
        if (not self.account.isascii() or not EMAIL.fullmatch(self.account) or parsed.scheme != "http"
                or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.path != "/auth/callback" or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise AuthenticationError("Configuração do consentimento Gmail inválida.")
        if self.token_file.exists() or not self.token_file.parent.is_dir():
            raise AuthenticationError("Escolha um arquivo novo em pasta privada existente.")
        value = _read_json(Path(client_file)).get("installed")
        if (not isinstance(value, dict) or not isinstance(value.get("token_uri", GOOGLE_TOKEN), str)
                or value.get("token_uri", GOOGLE_TOKEN) not in TOKEN_URIS):
            raise AuthenticationError("Use credenciais Google de aplicativo Desktop.")
        self.client_id = _field(value, "client_id")
        self._secret = _field(value, "client_secret")
        self._requester = requester or _request
        self.redirect_uri = redirect_uri
        self._state = secrets.token_urlsafe(32)
        self._verifier = secrets.token_urlsafe(64)
        self._started = time.monotonic()
        self._used = False

    def authorization_url(self):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode()).digest()).decode().rstrip("=")
        return GOOGLE_AUTH + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "redirect_uri": self.redirect_uri,
            "response_type": "code", "scope": " ".join(self.scopes),
            "access_type": "offline", "prompt": "consent", "state": self._state,
            "login_hint": self.account, "code_challenge": challenge,
            "code_challenge_method": "S256",
        })

    def complete(self, callback_url):
        parsed = urllib.parse.urlsplit(callback_url)
        expected = urllib.parse.urlsplit(self.redirect_uri)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if (self._used or time.monotonic() - self._started > 600
                or (parsed.scheme, parsed.netloc, parsed.path) !=
                   (expected.scheme, expected.netloc, expected.path)
                or parsed.fragment or query.get("state") != [self._state]
                or len(query.get("code", [])) != 1 or not query["code"][0]
                or "error" in query):
            raise AuthenticationError("Retorno OAuth inválido ou expirado.")
        self._used = True  # Never replay an uncertain exchange.
        try:
            body = urllib.parse.urlencode({"client_id": self.client_id,
                "client_secret": self._secret, "code": query["code"][0],
                "redirect_uri": self.redirect_uri, "code_verifier": self._verifier,
                "grant_type": "authorization_code"}).encode("ascii")
            status, value = self._requester("POST", GOOGLE_TOKEN, {
                "Content-Type": "application/x-www-form-urlencoded"}, body)
            if status != 200 or not isinstance(value, dict):
                raise ValueError()
            token, refresh = _field(value, "access_token"), _field(value, "refresh_token")
            expiry = datetime.fromtimestamp(time.time() + _duration(value.get("expires_in", 3600)), timezone.utc)
            if self.transport == "smtp":
                from .gmail_smtp import GmailSmtpAuth
                GmailSmtpAuth.validate_account(self.account, token)
            else:
                status, profile = self._requester("GET", GMAIL_API + "/profile", {
                    "Authorization": "Bearer " + token, "Accept": "application/json"}, None)
                if (status != 200 or not isinstance(profile, dict)
                        or not secrets.compare_digest(str(profile.get("emailAddress", "")).casefold(), self.account)):
                    raise ValueError()
            credentials = {"type": "authorized_user", "token": token,
                "refresh_token": refresh, "client_id": self.client_id,
                "client_secret": self._secret, "token_uri": GOOGLE_TOKEN,
                "expiry": expiry.isoformat(), "scopes": list(self.scopes)}
            descriptor = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(credentials, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                self.token_file.unlink(missing_ok=True)
                raise
            return {"account": self.account, "authorized": True, "created": True}
        except Exception:
            raise AuthenticationError("Não foi possível concluir o consentimento Gmail.") from None


def authorize(client_file, token_file, account, *, timeout=300, transport="api"):
    if not 1 <= timeout <= 600:
        raise ValueError("Timeout de autenticação inválido.")
    result = {}
    flow = None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Callback contains authorization code/state: never log it.

        def do_GET(self):
            if urllib.parse.urlsplit(self.path).path != "/auth/callback":
                self.send_error(404)
                return
            try:
                result["value"] = flow.complete(flow.redirect_uri + "?" + urllib.parse.urlsplit(self.path).query)
                status = 200
            except Exception:
                result["error"] = True
                status = 400
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Autenticação processada. Consulte o terminal.".encode())

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        flow = GmailFileConsent(client_file, token_file, account,
            f"http://127.0.0.1:{server.server_port}/auth/callback", transport=transport)
        print(json.dumps({"authorizationUrl": flow.authorization_url(),
                          "expiresInSeconds": timeout}, ensure_ascii=False), flush=True)
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if "value" not in result:
        raise AuthenticationError("Consentimento Gmail não concluído.")
    return result["value"]
