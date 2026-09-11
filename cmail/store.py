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
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS recipient_lists(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS recipients(
            list_id INTEGER NOT NULL, address TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(list_id,address), FOREIGN KEY(list_id) REFERENCES recipient_lists(id));
          CREATE TABLE IF NOT EXISTS drafts(
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            payload_json TEXT NOT NULL, confirmation_hash TEXT NOT NULL,
            status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}');
          CREATE TABLE IF NOT EXISTS audit_events(
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, action TEXT NOT NULL,
            status TEXT NOT NULL, detail_json TEXT NOT NULL);
        """)
        return db

    def status(self) -> dict[str, object]:
        with self.connect() as db:
            lists = db.execute("SELECT COUNT(*) FROM recipient_lists").fetchone()[0]
            drafts = db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            last = db.execute("SELECT created_at,action,status FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        return {"lists": lists, "drafts": drafts, "lastAction": dict(last) if last else None}

    def lists(self) -> list[dict[str, object]]:
        with self.connect() as db:
            rows = db.execute("""SELECT l.id,l.name,l.created_at,COUNT(r.address) AS recipients
                               FROM recipient_lists l LEFT JOIN recipients r ON r.list_id=l.id
                               GROUP BY l.id ORDER BY l.name""").fetchall()
        return [dict(row) for row in rows]

    def save_list(self, name: str, recipients: list[dict[str, str]]) -> dict[str, object]:
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
            db.execute("INSERT INTO recipient_lists(name,created_at) VALUES(?,?) ON CONFLICT(name) DO NOTHING",
                       (selected, _now().isoformat()))
            row = db.execute("SELECT id FROM recipient_lists WHERE name=?", (selected,)).fetchone()
            db.execute("DELETE FROM recipients WHERE list_id=?", (row[0],))
            db.executemany("INSERT INTO recipients(list_id,address,name) VALUES(?,?,?)",
                           ((row[0], address, label) for address, label in clean.items()))
        return {"id": row[0], "name": selected, "recipients": len(clean)}

    def list_recipients(self, list_id: int) -> list[str]:
        with self.connect() as db:
            rows = db.execute("SELECT address FROM recipients WHERE list_id=? ORDER BY address", (list_id,)).fetchall()
        return [str(row[0]) for row in rows]

    def prepare(self, payload: dict[str, object]) -> dict[str, object]:
        recipients = [str(item).strip().casefold() for item in payload.get("recipients", []) if str(item).strip()]
        if payload.get("listId"):
            recipients.extend(self.list_recipients(int(payload["listId"])))
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
            db.execute("INSERT INTO drafts(id,created_at,expires_at,payload_json,confirmation_hash,status) VALUES(?,?,?,?,?,?)",
                       (identifier, _now().isoformat(), expires.isoformat(), json.dumps(clean, ensure_ascii=False),
                        hashlib.sha256(token.encode()).hexdigest(), "prepared"))
            self._audit(db, "send-prepare", "prepared", {"draftId": identifier, "recipientCount": len(recipients)})
        return {"draftId": identifier, "confirmationToken": token, "expiresAt": expires.isoformat(),
                "recipientCount": len(recipients), "subject": subject, "bodyPreview": body[:240]}

    def claim(self, identifier: str, token: str) -> dict[str, object]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM drafts WHERE id=?", (identifier,)).fetchone()
            if not row or row["status"] != "prepared":
                raise ValueError("Rascunho ausente, consumido ou incerto.")
            if datetime.fromisoformat(row["expires_at"]) < _now():
                db.execute("UPDATE drafts SET status='expired' WHERE id=?", (identifier,))
                raise ValueError("Confirmação expirada.")
            if not secrets.compare_digest(row["confirmation_hash"], hashlib.sha256(token.encode()).hexdigest()):
                raise ValueError("Confirmação inválida.")
            db.execute("UPDATE drafts SET status='sending' WHERE id=?", (identifier,))
            self._audit(db, "send-execute", "sending", {"draftId": identifier})
            return json.loads(row["payload_json"])

    def finish(self, identifier: str, status: str, result: dict[str, object]) -> None:
        with self.connect() as db:
            db.execute("UPDATE drafts SET status=?,result_json=? WHERE id=?",
                       (status, json.dumps(result, ensure_ascii=False), identifier))
            self._audit(db, "send-execute", status, {"draftId": identifier, **result})

    @staticmethod
    def _audit(db: sqlite3.Connection, action: str, status: str, detail: dict[str, object]) -> None:
        db.execute("INSERT INTO audit_events(created_at,action,status,detail_json) VALUES(?,?,?,?)",
                   (_now().isoformat(), action, status, json.dumps(detail, ensure_ascii=False)))
