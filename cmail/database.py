"""SQLite lifecycle and schema, initialized once per database file identity."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._identity = None
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=15000")
            with self._lock:
                stat = self.path.stat()
                identity = (stat.st_dev, stat.st_ino)
                if self._identity != identity:
                    self._initialize(db)
                    self._identity = identity
            return db
        except BaseException:
            db.close()
            raise

    def _initialize(self, db):
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
            owner_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(provider,tenant_id,subject_id));
          CREATE TABLE IF NOT EXISTS mail_connections(
            identity_id TEXT PRIMARY KEY, status TEXT NOT NULL, scopes_json TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
            FOREIGN KEY(identity_id) REFERENCES auth_identities(id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS web_sessions(
            token_hash TEXT PRIMARY KEY, identity_id TEXT NOT NULL, csrf_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT,
            FOREIGN KEY(identity_id) REFERENCES auth_identities(id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS owner_preferences(
            owner_id TEXT PRIMARY KEY,
            webmail_enabled INTEGER NOT NULL DEFAULT 1 CHECK(webmail_enabled IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_web_sessions_identity ON web_sessions(identity_id);
          CREATE INDEX IF NOT EXISTS idx_mail_audit_owner_id ON mail_audit_events(owner_id,id DESC);
        """)
        self._migrate_legacy(db)

    @staticmethod
    def _migrate_legacy(db: sqlite3.Connection) -> None:
        version = int(db.execute("PRAGMA user_version").fetchone()[0])
        names = {
            str(row[0]) for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if version < 2 and {"recipient_lists", "recipients"} <= names:
            db.execute(
                "INSERT OR IGNORE INTO mail_lists(id,owner_id,name,created_at) SELECT id,'',name,created_at FROM recipient_lists"
            )
            db.execute(
                "INSERT OR IGNORE INTO mail_recipients(list_id,address,name) SELECT list_id,address,name FROM recipients"
            )
        if version < 2 and "drafts" in names:
            db.execute(
                """INSERT OR IGNORE INTO mail_drafts(id,created_at,expires_at,payload_json,confirmation_hash,status,result_json,owner_id)
                   SELECT id,created_at,expires_at,payload_json,confirmation_hash,status,result_json,'' FROM drafts"""
            )
        if version < 2 and "audit_events" in names:
            db.execute(
                """INSERT OR IGNORE INTO mail_audit_events(id,created_at,action,status,detail_json,owner_id)
                   SELECT id,created_at,action,status,detail_json,'' FROM audit_events"""
            )
        columns = {
            str(row[1]) for row in db.execute("PRAGMA table_info(auth_identities)")
        }
        if "owner_id" not in columns:
            db.execute(
                "ALTER TABLE auth_identities ADD COLUMN owner_id TEXT NOT NULL DEFAULT ''"
            )
        db.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_identity_provider_owner
               ON auth_identities(provider,owner_id) WHERE owner_id <> ''"""
        )
        db.execute("PRAGMA user_version=4")
        db.commit()
