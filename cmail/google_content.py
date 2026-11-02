"""Bounded, owner-bound Google content operations. No arbitrary endpoint proxy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from .google_auth import GoogleAuthService, CONTENT_SCOPES, ConsentRequired
from .principal import Principal

MAX_BYTES = 1024 * 1024
MAX_INPUT = 64 * 1024
TTL = 600


class ReadOperation(str, Enum):
    DRIVE_LIST = "drive.list"
    DRIVE_GET = "drive.get"
    DRIVE_TEXT = "drive.text"
    DOCS_GET = "docs.get"
    SHEETS_GET = "sheets.get"
    SHEETS_METADATA = "sheets.metadata"
    SLIDES_GET = "slides.get"


class WriteOperation(str, Enum):
    DRIVE_UPDATE = "drive.update"
    DRIVE_FOLDER = "drive.create_folder"
    DOCS_BATCH = "docs.batch_update"
    SHEETS_UPDATE = "sheets.update"
    SHEETS_FORMAT = "sheets.format"
    SLIDES_BATCH = "slides.batch_update"


@dataclass(frozen=True)
class GoogleRead:
    operation: ReadOperation
    identifier: str = ""
    query: str = ""
    page_token: str = ""
    page_size: int = 100
    max_pages: int = 1
    range: str = "A1:Z100"
    export: bool = False


@dataclass(frozen=True)
class GoogleWrite:
    operation: WriteOperation
    identifier: str = ""
    changes: dict = field(default_factory=dict)


class ContentError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, url, headers, body):
    """Fixed hosts selected internally, no redirect, retry or unbounded read."""
    opener = urllib.request.build_opener(_NoRedirect)
    selected = urllib.request.Request(url, data=body, method=method, headers=headers)
    start = time.monotonic()
    try:
        with opener.open(selected, timeout=20) as response:
            chunks, size = [], 0
            while True:
                if time.monotonic() - start > 20:
                    raise ContentError("google-time-limit")
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ContentError("google-response-limit")
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            value = (raw.decode("utf-8") if headers.get("Accept") == "text/plain"
                     else json.loads(raw) if raw else {})
            return response.status, value
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, {}  # Never expose provider error bodies.
    except Exception:
        raise ContentError("google-transport-error") from None


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Conteúdo JSON inválido.") from None


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        raise ValueError("ID Google inválido.")
    return value


def _text(value, maximum):
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise ValueError("Texto Google inválido.")
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Limite Google inválido.")
    return value


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Campos Google inválidos.")


def _cap(operation, write=False):
    return "google." + operation.value.split(".")[0] + (".write" if write else ".read")


class GoogleContent:
    def __init__(self, auth: GoogleAuthService, store, *, requester=None, clock=time.time):
        self.auth, self.store = auth, store
        self.requester = requester or request
        self.clock = clock

    def _owner(self, principal: Principal, capability):
        principal.require(capability)
        identity = self.store.identity(principal.identity_id)
        if (not identity or identity.get("provider") != "google" or
                (identity.get("owner_id") or identity["id"]) != principal.storage_owner):
            raise PermissionError("Proprietário Google incompatível.")
        connection = self.store.connection(principal.identity_id)
        if not connection or connection["status"] != "authorized":
            raise PermissionError("Conexão Google não autorizada.")

    def _authorize(self, principal, capability):
        self._owner(principal, capability)  # Must precede token access, refresh and HTTP.
        self.auth.require_scopes(principal.identity_id, capability)

    def begin_consent(self, principal, capability):
        if capability not in CONTENT_SCOPES:
            raise ValueError("Capacidade Google inválida.")
        if principal.identity_id:
            self._owner(principal, capability)
        else:
            principal.require(capability)
            if not principal.owner_id or len(principal.owner_id) > 256:
                raise PermissionError("Proprietário Google obrigatório.")
        return self.auth.begin_content(principal.identity_id, principal.storage_owner, capability)

    def _call(self, principal, capability, method, path, *, params=None, body=None, text=False):
        self._authorize(principal, capability)
        try:
            token = self.auth.access_token(principal.identity_id)
            self.auth.require_scopes(principal.identity_id, capability)  # Refresh may narrow grant.
            headers = {"Authorization": "Bearer " + token,
                       "Accept": "text/plain" if text else "application/json"}
            raw = _json(body) if body is not None else None
            if raw is not None:
                if len(raw) > MAX_INPUT:
                    raise ContentError("google-input-limit")
                headers["Content-Type"] = "application/json"
            url = path + ("?" + urllib.parse.urlencode(params) if params else "")
            status, value = self.requester(method, url, headers, raw)
            if status < 200 or status >= 300:
                raise ContentError("google-request-failed")
            if len(_json(value)) > MAX_BYTES:
                raise ContentError("google-response-limit")
            if text and not isinstance(value, str):
                raise ContentError("google-response-invalid")
            if not text and not isinstance(value, dict):
                raise ContentError("google-response-invalid")
            return value
        except ConsentRequired:
            raise
        except Exception:
            raise ContentError("google-request-failed-or-response-limit") from None

    def read(self, principal: Principal, query: GoogleRead):
        if not isinstance(query, GoogleRead) or not isinstance(query.operation, ReadOperation):
            raise ValueError("Operação de leitura Google inválida.")
        op = query.operation
        cap = _cap(op)
        self._authorize(principal, cap)
        if op == ReadOperation.DRIVE_LIST:
            _integer(query.page_size, 1, 100)
            _integer(query.max_pages, 1, 10)
            if not isinstance(query.query, str) or len(query.query) > 2048:
                raise ValueError("Consulta Google inválida.")
            if not isinstance(query.page_token, str) or len(query.page_token) > 2048:
                raise ValueError("Página Google inválida.")
            files, seen, token = [], set(), query.page_token
            start = time.monotonic()
            incomplete = False
            for _ in range(query.max_pages):
                if time.monotonic() - start > 60:
                    raise ContentError("google-time-limit")
                params = {"q": query.query, "pageSize": query.page_size,
                          "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,description,parents,modifiedTime,size)"}
                if token:
                    params["pageToken"] = token
                result = self._call(principal, cap, "GET", "https://www.googleapis.com/drive/v3/files", params=params)
                batch = result.get("files", [])
                if not isinstance(batch, list) or len(batch) > query.page_size:
                    raise ContentError("google-page-invalid")
                files.extend(batch)
                incomplete = incomplete or bool(result.get("incompleteSearch"))
                token = result.get("nextPageToken", "")
                if not isinstance(token, str) or len(token) > 2048:
                    raise ContentError("google-page-invalid")
                if len(_json(files)) > MAX_BYTES:
                    raise ContentError("google-response-limit")
                if not token:
                    break  # Empty or partial pages are NOT terminal when a token exists.
                if token in seen:
                    raise ContentError("google-page-cycle")
                seen.add(token)
            return {"files": files, "nextPageToken": token,
                    "incompleteSearch": incomplete, "complete": not token and not incomplete}
        identifier = _id(query.identifier)
        if op == ReadOperation.DRIVE_GET:
            return self._call(principal, cap, "GET", f"https://www.googleapis.com/drive/v3/files/{identifier}",
                              params={"fields": "id,name,mimeType,description,parents,modifiedTime,size"})
        if op == ReadOperation.DRIVE_TEXT:
            if type(query.export) is not bool:
                raise ValueError("Modo de exportação Google inválido.")
            # Download only text/plain; export only Docs to plain text. No URL following.
            metadata = self.read(principal, GoogleRead(ReadOperation.DRIVE_GET, identifier))
            if query.export:
                if metadata.get("mimeType") != "application/vnd.google-apps.document":
                    raise ValueError("Somente Docs pode ser exportado para texto.")
                path, params = f"{identifier}/export", {"mimeType": "text/plain"}
            else:
                if metadata.get("mimeType") != "text/plain":
                    raise ValueError("Somente text/plain pode ser baixado.")
                path, params = identifier, {"alt": "media"}
            return {"text": self._call(principal, cap, "GET", "https://www.googleapis.com/drive/v3/files/" + path,
                                       params=params, text=True)}
        if op == ReadOperation.DOCS_GET:
            path = f"https://docs.googleapis.com/v1/documents/{identifier}"
        elif op == ReadOperation.SHEETS_GET:
            area = urllib.parse.quote(_text(query.range, 256), safe="")
            path = f"https://sheets.googleapis.com/v4/spreadsheets/{identifier}/values/{area}"
        elif op == ReadOperation.SHEETS_METADATA:
            return self._call(principal, cap, "GET",
                f"https://sheets.googleapis.com/v4/spreadsheets/{identifier}",
                params={"fields": "spreadsheetId,spreadsheetUrl,sheets(properties,charts(chartId,spec,position))"})
        else:
            path = f"https://slides.googleapis.com/v1/presentations/{identifier}"
        return self._call(principal, cap, "GET", path)

    @staticmethod
    def _write_spec(change: GoogleWrite):
        if not isinstance(change, GoogleWrite) or not isinstance(change.operation, WriteOperation):
            raise ValueError("Operação de escrita Google inválida.")
        op, data = change.operation, change.changes
        if len(_json(data)) > MAX_INPUT:
            raise ValueError("google-input-limit")
        identifier = _id(change.identifier) if op != WriteOperation.DRIVE_FOLDER else ""
        if op == WriteOperation.DRIVE_UPDATE:
            _keys(data, (), ("name", "description"))
            if not data:
                raise ValueError("Alteração vazia.")
            for key, value in data.items():
                _text(value, 255 if key == "name" else 4096)
            return "PATCH", f"https://www.googleapis.com/drive/v3/files/{identifier}", data, {"fields": "id,name,mimeType,description"}
        if op == WriteOperation.DRIVE_FOLDER:
            _keys(data, ("name",), ("parent",))
            body = {"name": _text(data["name"], 255), "mimeType": "application/vnd.google-apps.folder"}
            if "parent" in data:
                body["parents"] = [_id(data["parent"])]
            return "POST", "https://www.googleapis.com/drive/v3/files", body, {"fields": "id,name,mimeType,parents"}
        if op == WriteOperation.SHEETS_UPDATE:
            _keys(data, ("range", "values"))
            area = urllib.parse.quote(_text(data["range"], 256), safe="")
            rows = data["values"]
            if (not isinstance(rows, list) or not 1 <= len(rows) <= 100 or
                any(not isinstance(row, list) or not 1 <= len(row) <= 26 or
                    any(type(cell) not in (str, int, float, bool) for cell in row) for row in rows)):
                raise ValueError("Valores Google inválidos.")
            return "PUT", f"https://sheets.googleapis.com/v4/spreadsheets/{identifier}/values/{area}", {"values": rows}, {"valueInputOption": "RAW"}
        if op == WriteOperation.SHEETS_FORMAT:
            keys = ("sheetId", "startRowIndex", "endRowIndex", "startColumnIndex", "endColumnIndex", "format")
            _keys(data, keys)
            grid = {key: _integer(data[key], 0, 1_000_000) for key in keys[:-1]}
            if not (1 <= grid["endRowIndex"] - grid["startRowIndex"] <= 100
                    and 1 <= grid["endColumnIndex"] - grid["startColumnIndex"] <= 26):
                raise ValueError("Formatação exige intervalo limitado a 100 linhas por 26 colunas.")
            style = data["format"]
            _keys(style, (), ("bold", "italic", "fontSize", "horizontalAlignment", "numberFormat"))
            if not style:
                raise ValueError("Formatação vazia.")
            cell_format, fields, text_format = {}, [], {}
            for key in ("bold", "italic"):
                if key in style:
                    if type(style[key]) is not bool:
                        raise ValueError("Formatação booleana inválida.")
                    text_format[key] = style[key]
            if "fontSize" in style:
                text_format["fontSize"] = _integer(style["fontSize"], 6, 72)
            if text_format:
                cell_format["textFormat"] = text_format
                fields.extend("userEnteredFormat.textFormat." + key for key in text_format)
            if "horizontalAlignment" in style:
                if style["horizontalAlignment"] not in ("LEFT", "CENTER", "RIGHT"):
                    raise ValueError("Alinhamento inválido.")
                cell_format["horizontalAlignment"] = style["horizontalAlignment"]
                fields.append("userEnteredFormat.horizontalAlignment")
            if "numberFormat" in style:
                number = style["numberFormat"]
                _keys(number, ("type",), ("pattern",))
                if number["type"] not in ("NUMBER", "CURRENCY", "PERCENT", "DATE", "TIME", "DATE_TIME", "SCIENTIFIC", "TEXT"):
                    raise ValueError("Formato numérico inválido.")
                if "pattern" in number:
                    _text(number["pattern"], 80)
                cell_format["numberFormat"] = number
                fields.append("userEnteredFormat.numberFormat")
            body = {"requests": [{"repeatCell": {"range": grid,
                    "cell": {"userEnteredFormat": cell_format}, "fields": ",".join(fields)}}]}
            return "POST", f"https://sheets.googleapis.com/v4/spreadsheets/{identifier}:batchUpdate", body, None
        # Small explicit batch allowlist: insertText only, no links, deletes or sharing.
        _keys(data, ("requests",))
        requests = data["requests"]
        if not isinstance(requests, list) or not 1 <= len(requests) <= 20:
            raise ValueError("Lote Google inválido.")
        for item in requests:
            _keys(item, ("insertText",))
            insert = item["insertText"]
            if op == WriteOperation.DOCS_BATCH:
                _keys(insert, ("text", "location"))
                _keys(insert["location"], ("index",))
                _integer(insert["location"]["index"], 1, 1000000)
            else:
                _keys(insert, ("text", "objectId", "insertionIndex"))
                _id(insert["objectId"])
                _integer(insert["insertionIndex"], 0, 1000000)
            _text(insert["text"], 10000)
        if op == WriteOperation.DOCS_BATCH:
            path = f"https://docs.googleapis.com/v1/documents/{identifier}:batchUpdate"
        else:
            path = f"https://slides.googleapis.com/v1/presentations/{identifier}:batchUpdate"
        return "POST", path, data, None

    def prepare(self, principal: Principal, change: GoogleWrite):
        if not isinstance(change, GoogleWrite) or not isinstance(change.operation, WriteOperation):
            raise ValueError("Operação de escrita Google inválida.")
        # Freeze caller-owned nested dictionaries BEFORE validating or authorizing.
        # The persisted snapshot must be exactly the payload validated here.
        change = GoogleWrite(change.operation, change.identifier, json.loads(_json(change.changes)))
        self._write_spec(change)
        cap = _cap(change.operation, True)
        self._authorize(principal, cap)  # Local checks only: no refresh, no HTTP.
        snapshot = json.loads(_json({"operation": change.operation.value,
                                    "identifier": change.identifier, "changes": change.changes}))
        identifier, token = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        expires = self.clock() + TTL
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM google_content_previews WHERE expires_at < ?", (self.clock(),))
            count = db.execute("SELECT count(*) FROM google_content_previews WHERE owner_id=?",
                               (principal.storage_owner,)).fetchone()[0]
            if count >= 128:
                raise ContentError("google-preview-limit")
            db.execute("INSERT INTO google_content_previews VALUES(?,?,?,?,?,?,?,?)",
                       (identifier, principal.storage_owner, principal.identity_id,
                        expires, hashlib.sha256(token.encode()).hexdigest(),
                        _json(snapshot).decode(), "prepared", ""))
        return {"previewId": identifier, "confirmationToken": token, "expiresAt": expires,
                "preview": snapshot, "status": "prepared"}

    def execute(self, principal: Principal, preview_id: str, confirmation_token: str, *, confirmed: bool = False):
        if confirmed is not True:
            raise PermissionError("Confirmação específica obrigatória.")
        _text(preview_id, 128)
        _text(confirmation_token, 128)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM google_content_previews WHERE id=? AND owner_id=? AND identity_id=?",
                             (preview_id, principal.storage_owner, principal.identity_id)).fetchone()
            if (not row or row["status"] != "prepared" or row["expires_at"] <= self.clock() or
                not secrets.compare_digest(row["confirmation_hash"], hashlib.sha256(confirmation_token.encode()).hexdigest())):
                raise PermissionError("Prévia ausente, expirada ou consumida.")
            snapshot = json.loads(row["payload_json"])
            change = GoogleWrite(WriteOperation(snapshot["operation"]), snapshot["identifier"], snapshot["changes"])
            cap = _cap(change.operation, True)
            self._authorize(principal, cap)
            db.execute("UPDATE google_content_previews SET status='claimed' WHERE id=?", (preview_id,))
        # Claim is durable before token refresh and the first HTTP attempt. Crash also consumes it.
        method, path, body, params = self._write_spec(change)
        try:
            result = self._call(principal, cap, method, path, params=params, body=body)
            status = "completed"
        except Exception:
            result, status = {"error": "google-write-uncertain", "retryAllowed": False}, "uncertain"
        with self.store.connect() as db:
            db.execute("UPDATE google_content_previews SET status=?,error=? WHERE id=?",
                       (status, "google-write-uncertain" if status == "uncertain" else "", preview_id))
        return {"previewId": preview_id, "status": status, "result": result, "retryAllowed": False}
