"""Listas, journal de envio e auditoria mínima do CMAIL."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.path = state_dir / "cmail.sqlite3"

    def connect(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS mail_lists(
            id INTEGER PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(owner_id,name));
          CREATE TABLE IF NOT EXISTS mail_recipients(
            list_id INTEGER NOT NULL, address TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(list_id,address), FOREIGN KEY(list_id) REFERENCES mail_lists(id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS mail_drafts(
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            payload_json TEXT NOT NULL, confirmation_hash TEXT NOT NULL,
            status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}', owner_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS mail_audit_events(
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, action TEXT NOT NULL,
            status TEXT NOT NULL, detail_json TEXT NOT NULL, owner_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS auth_identities(
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, tenant_id TEXT NOT NULL,
            subject_id TEXT NOT NULL, email TEXT NOT NULL, display_name TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(provider,tenant_id,subject_id));
          CREATE TABLE IF NOT EXISTS mail_connections(
            identity_id TEXT PRIMARY KEY, status TEXT NOT NULL, scopes_json TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
            FOREIGN KEY(identity_id) REFERENCES auth_identities(id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS web_sessions(
            token_hash TEXT PRIMARY KEY, identity_id TEXT NOT NULL, csrf_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT,
            FOREIGN KEY(identity_id) REFERENCES auth_identities(id) ON DELETE CASCADE);
          CREATE INDEX IF NOT EXISTS idx_web_sessions_identity ON web_sessions(identity_id);
        """)
        self._migrate_legacy(db)
        return db

    @staticmethod
    def _migrate_legacy(db: sqlite3.Connection) -> None:
        version = int(db.execute("PRAGMA user_version").fetchone()[0])
        if version >= 2:
            return
        names = {
            str(row[0]) for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if {"recipient_lists", "recipients"} <= names:
            db.execute(
                "INSERT OR IGNORE INTO mail_lists(id,owner_id,name,created_at) SELECT id,'',name,created_at FROM recipient_lists"
            )
            db.execute(
                "INSERT OR IGNORE INTO mail_recipients(list_id,address,name) SELECT list_id,address,name FROM recipients"
            )
        if "drafts" in names:
            db.execute(
                """INSERT OR IGNORE INTO mail_drafts(id,created_at,expires_at,payload_json,confirmation_hash,status,result_json,owner_id)
                   SELECT id,created_at,expires_at,payload_json,confirmation_hash,status,result_json,'' FROM drafts"""
            )
        if "audit_events" in names:
            db.execute(
                """INSERT OR IGNORE INTO mail_audit_events(id,created_at,action,status,detail_json,owner_id)
                   SELECT id,created_at,action,status,detail_json,'' FROM audit_events"""
            )
        db.execute("PRAGMA user_version=2")
        db.commit()

    def status(self, owner_id: str = "") -> dict[str, object]:
        with self.connect() as db:
            lists = db.execute("SELECT COUNT(*) FROM mail_lists WHERE owner_id=?", (owner_id,)).fetchone()[0]
            drafts = db.execute("SELECT COUNT(*) FROM mail_drafts WHERE owner_id=?", (owner_id,)).fetchone()[0]
            last = db.execute(
                "SELECT created_at,action,status FROM mail_audit_events WHERE owner_id=? ORDER BY id DESC LIMIT 1",
                (owner_id,),
            ).fetchone()
        return {"lists": lists, "drafts": drafts, "lastAction": dict(last) if last else None}

    def lists(self, owner_id: str = "") -> list[dict[str, object]]:
        with self.connect() as db:
            rows = db.execute("""SELECT l.id,l.name,l.created_at,COUNT(r.address) AS recipients
                               FROM mail_lists l LEFT JOIN mail_recipients r ON r.list_id=l.id
                               WHERE l.owner_id=? GROUP BY l.id ORDER BY l.name""", (owner_id,)).fetchall()
        return [dict(row) for row in rows]

    def save_list(self, name: str, recipients: list[dict[str, str]], owner_id: str = "") -> dict[str, object]:
        selected = " ".join(str(name or "").split())[:120]
        if not selected:
            raise ValueError("Nome da lista é obrigatório.")
        clean: dict[str, str] = {}
        for item in recipients:
            address = str(item.get("address") or "").strip().casefold()
            if not EMAIL.fullmatch(address):
                raise ValueError("Lista contém endereço inválido.")
            clean[address] = " ".join(str(item.get("name") or "").split())[:120]
        if not clean or len(clean) > 1000:
            raise ValueError("Lista deve conter entre 1 e 1000 destinatários.")
        with self.connect() as db:
            db.execute("INSERT INTO mail_lists(owner_id,name,created_at) VALUES(?,?,?) ON CONFLICT(owner_id,name) DO NOTHING",
                       (owner_id, selected, _now().isoformat()))
            row = db.execute("SELECT id FROM mail_lists WHERE owner_id=? AND name=?", (owner_id, selected)).fetchone()
            db.execute("DELETE FROM mail_recipients WHERE list_id=?", (row[0],))
            db.executemany("INSERT INTO mail_recipients(list_id,address,name) VALUES(?,?,?)",
                           ((row[0], address, label) for address, label in clean.items()))
        return {"id": row[0], "name": selected, "recipients": len(clean)}

    def list_recipients(self, list_id: int, owner_id: str = "") -> list[str]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT r.address FROM mail_recipients r JOIN mail_lists l ON l.id=r.list_id WHERE r.list_id=? AND l.owner_id=? ORDER BY r.address",
                (list_id, owner_id),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def prepare(self, payload: dict[str, object], owner_id: str = "") -> dict[str, object]:
        recipients = [str(item).strip().casefold() for item in payload.get("recipients", []) if str(item).strip()]
        if payload.get("listId"):
            recipients.extend(self.list_recipients(int(payload["listId"]), owner_id))
        recipients = list(dict.fromkeys(recipients))
        if not recipients or len(recipients) > 1000 or any(not EMAIL.fullmatch(item) for item in recipients):
            raise ValueError("Destinatários inválidos ou acima do limite.")
        subject = str(payload.get("subject") or "").strip()[:500]
        body = str(payload.get("body") or "")[:200_000]
        if not subject or not body:
            raise ValueError("Assunto e corpo são obrigatórios.")
        clean = {"recipients": recipients, "subject": subject, "body": body}
        identifier, token = secrets.token_urlsafe(18), secrets.token_urlsafe(32)
        expires = _now() + timedelta(minutes=10)
        with self.connect() as db:
            db.execute("INSERT INTO mail_drafts(id,created_at,expires_at,payload_json,confirmation_hash,status,owner_id) VALUES(?,?,?,?,?,?,?)",
                       (identifier, _now().isoformat(), expires.isoformat(), json.dumps(clean, ensure_ascii=False),
                        hashlib.sha256(token.encode()).hexdigest(), "prepared", owner_id))
            self._audit(db, "send-prepare", "prepared", {"draftId": identifier, "recipientCount": len(recipients)}, owner_id)
        return {"draftId": identifier, "confirmationToken": token, "expiresAt": expires.isoformat(),
                "recipientCount": len(recipients), "subject": subject, "bodyPreview": body[:240]}

    def claim(self, identifier: str, token: str, owner_id: str = "") -> dict[str, object]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mail_drafts WHERE id=? AND owner_id=?", (identifier, owner_id)).fetchone()
            if not row or row["status"] != "prepared":
                raise ValueError("Rascunho ausente, consumido ou incerto.")
            if datetime.fromisoformat(row["expires_at"]) < _now():
                db.execute("UPDATE mail_drafts SET status='expired' WHERE id=? AND owner_id=?", (identifier, owner_id))
                raise ValueError("Confirmação expirada.")
            if not secrets.compare_digest(row["confirmation_hash"], hashlib.sha256(token.encode()).hexdigest()):
                raise ValueError("Confirmação inválida.")
            db.execute("UPDATE mail_drafts SET status='sending' WHERE id=? AND owner_id=?", (identifier, owner_id))
            self._audit(db, "send-execute", "sending", {"draftId": identifier}, owner_id)
            return json.loads(row["payload_json"])

    def finish(self, identifier: str, status: str, result: dict[str, object], owner_id: str = "") -> None:
        with self.connect() as db:
            db.execute("UPDATE mail_drafts SET status=?,result_json=? WHERE id=? AND owner_id=?",
                       (status, json.dumps(result, ensure_ascii=False), identifier, owner_id))
            self._audit(db, "send-execute", status, {"draftId": identifier, **result}, owner_id)

    @staticmethod
    def _audit(db: sqlite3.Connection, action: str, status: str, detail: dict[str, object], owner_id: str = "") -> None:
        db.execute("INSERT INTO mail_audit_events(created_at,action,status,detail_json,owner_id) VALUES(?,?,?,?,?)",
                   (_now().isoformat(), action, status, json.dumps(detail, ensure_ascii=False), owner_id))

    def save_identity(
        self, tenant_id: str, subject_id: str, email: str, display_name: str,
        *, provider: str = "microsoft", scopes: list[str] | None = None,
    ) -> dict[str, str]:
        if provider not in {"microsoft", "google"}:
            raise ValueError("Provedor de identidade inválido.")
        now = _now().isoformat()
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM auth_identities WHERE provider=? AND tenant_id=? AND subject_id=?",
                (provider, tenant_id, subject_id),
            ).fetchone()
            identity_id = str(row[0]) if row else secrets.token_urlsafe(18)
            db.execute(
                """INSERT INTO auth_identities(id,provider,tenant_id,subject_id,email,display_name,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider,tenant_id,subject_id) DO UPDATE SET
                     email=excluded.email,display_name=excluded.display_name,updated_at=excluded.updated_at""",
                (identity_id, provider, tenant_id, subject_id, email, display_name, now, now),
            )
            db.execute(
                """INSERT INTO mail_connections(identity_id,status,scopes_json,updated_at)
                   VALUES(?,?,?,?) ON CONFLICT(identity_id) DO UPDATE SET
                   status=excluded.status,scopes_json=excluded.scopes_json,last_error='',updated_at=excluded.updated_at""",
                (
                    identity_id, "authorized",
                    json.dumps(scopes or ["Mail.ReadWrite", "Mail.Send"]), now,
                ),
            )
        return self.identity(identity_id) or {}

    def identity(self, identity_id: str) -> dict[str, str] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT id,provider,tenant_id,subject_id,email,display_name FROM auth_identities WHERE id=?",
                (identity_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_session(self, identity_id: str, hours: int) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now, expires = _now(), _now() + timedelta(hours=hours)
        with self.connect() as db:
            db.execute(
                "INSERT INTO web_sessions(token_hash,identity_id,csrf_hash,created_at,expires_at) VALUES(?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), identity_id,
                 hashlib.sha256(csrf.encode()).hexdigest(), now.isoformat(), expires.isoformat()),
            )
        return token, csrf

    def session(self, token: str) -> dict[str, str] | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute(
                """SELECT s.token_hash,s.csrf_hash,s.expires_at,i.id,i.provider,i.tenant_id,i.subject_id,i.email,i.display_name
                   FROM web_sessions s JOIN auth_identities i ON i.id=s.identity_id
                   WHERE s.token_hash=? AND s.revoked_at IS NULL""", (digest,),
            ).fetchone()
            if row and datetime.fromisoformat(row["expires_at"]) < _now():
                db.execute("UPDATE web_sessions SET revoked_at=? WHERE token_hash=?", (_now().isoformat(), digest))
                return None
        return dict(row) if row else None

    def csrf_valid(self, session_row: dict[str, str], token: str) -> bool:
        expected = str(session_row.get("csrf_hash") or "")
        return bool(token) and secrets.compare_digest(expected, hashlib.sha256(token.encode()).hexdigest())

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        with self.connect() as db:
            db.execute(
                "UPDATE web_sessions SET revoked_at=? WHERE token_hash=?",
                (_now().isoformat(), hashlib.sha256(token.encode()).hexdigest()),
            )

    def revoke_identity_sessions(self, identity_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE web_sessions SET revoked_at=? WHERE identity_id=? AND revoked_at IS NULL",
                (_now().isoformat(), identity_id),
            )

    def set_connection_status(self, identity_id: str, status: str, error: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE mail_connections SET status=?,last_error=?,updated_at=? WHERE identity_id=?",
                (status, error[:120], _now().isoformat(), identity_id),
            )

    def connection(self, identity_id: str) -> dict[str, object] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT status,scopes_json,last_error,updated_at FROM mail_connections WHERE identity_id=?",
                (identity_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["scopes"] = json.loads(str(result.pop("scopes_json")))
        return result
