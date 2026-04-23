"""SQLite-backed store for monitored user profiles + queued alerts.

Previously JSON file-backed; switched to SQLite for concurrency safety and
consistency with utils/session_store (same DB file, same lock semantics).

Schema:
  profiles(user_id PK, email, sector, language, company_name, open_gaps JSON,
           created_at, last_check_iso)
  alerts(id PK, user_id FK, created_at, payload JSON)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(BASE_DIR, "data", "regula.db")
_LOCK = threading.Lock()
_conn: sqlite3.Connection | None = None


_LEGACY_JSON_PATH = os.path.join(BASE_DIR, "data", "profiles.json")


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id         TEXT PRIMARY KEY,
            email           TEXT,
            sector          TEXT,
            language        TEXT,
            company_name    TEXT,
            open_gaps       TEXT,
            created_at      TEXT NOT NULL,
            last_check_iso  TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            payload    TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, created_at DESC)")
    _conn = conn
    _migrate_legacy_json(conn)
    return conn


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    """One-shot migration from the old JSON store. Idempotent — skips if DB
    already has profiles or legacy file is missing."""
    existing = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    if existing > 0 or not os.path.exists(_LEGACY_JSON_PATH):
        return
    try:
        with open(_LEGACY_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return
    profiles = (data.get("profiles") or {}).values()
    migrated = 0
    for p in profiles:
        uid = p.get("user_id")
        if not uid:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO profiles(user_id, email, sector, language,
                company_name, open_gaps, created_at, last_check_iso)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid, p.get("email"), p.get("sector"), p.get("language"),
                p.get("company_name"),
                json.dumps(p.get("open_gaps") or [], ensure_ascii=False),
                p.get("created_at") or _now_iso(),
                p.get("last_check_iso"),
            ),
        )
        for a in (p.get("alerts") or []):
            aid = a.get("id") or f"alt_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT OR IGNORE INTO alerts(id, user_id, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (aid, uid, a.get("created_at") or _now_iso(),
                 json.dumps(a, ensure_ascii=False)),
            )
        migrated += 1
    if migrated:
        log.info("migrated %d profile(s) from legacy profiles.json", migrated)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_profile(row: sqlite3.Row, alerts: list[dict] | None = None) -> dict:
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "sector": row["sector"],
        "language": row["language"],
        "company_name": row["company_name"],
        "open_gaps": json.loads(row["open_gaps"]) if row["open_gaps"] else [],
        "created_at": row["created_at"],
        "last_check_iso": row["last_check_iso"],
        "alerts": alerts if alerts is not None else [],
    }


def upsert_profile(
    *,
    email: str,
    sector: str | None,
    language: str,
    open_gaps: list[dict[str, Any]],
    company_name: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Create or update a profile keyed by user_id (auto-generated if missing)."""
    with _LOCK:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        if not user_id:
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
        existing = conn.execute(
            "SELECT created_at FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else _now_iso()
        conn.execute(
            """
            INSERT INTO profiles(user_id, email, sector, language, company_name,
                                 open_gaps, created_at, last_check_iso)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                email        = excluded.email,
                sector       = excluded.sector,
                language     = excluded.language,
                company_name = excluded.company_name,
                open_gaps    = excluded.open_gaps
            """,
            (
                user_id, email, sector, language, company_name,
                json.dumps(open_gaps, ensure_ascii=False), created_at,
            ),
        )
        return _fetch_profile(conn, user_id)


def _fetch_profile(conn: sqlite3.Connection, user_id: str) -> dict | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        return None
    alert_rows = conn.execute(
        "SELECT payload FROM alerts WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    alerts = [json.loads(r["payload"]) for r in alert_rows]
    return _row_to_profile(row, alerts)


def get_profile(user_id: str) -> dict | None:
    with _LOCK:
        return _fetch_profile(_get_conn(), user_id)


def list_profiles() -> list[dict]:
    with _LOCK:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT user_id FROM profiles").fetchall()
        return [_fetch_profile(conn, r["user_id"]) for r in rows]


def append_alert(user_id: str, alert: dict) -> dict | None:
    with _LOCK:
        conn = _get_conn()
        exists = conn.execute(
            "SELECT 1 FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not exists:
            return None
        alert = dict(alert)
        alert.setdefault("id", f"alt_{uuid.uuid4().hex[:12]}")
        alert.setdefault("created_at", _now_iso())
        conn.execute(
            "INSERT INTO alerts(id, user_id, created_at, payload) VALUES (?, ?, ?, ?)",
            (alert["id"], user_id, alert["created_at"],
             json.dumps(alert, ensure_ascii=False)),
        )
        return alert


def mark_checked(user_id: str) -> None:
    with _LOCK:
        conn = _get_conn()
        conn.execute(
            "UPDATE profiles SET last_check_iso = ? WHERE user_id = ?",
            (_now_iso(), user_id),
        )


def list_alerts(user_id: str) -> list[dict]:
    with _LOCK:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT payload FROM alerts WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]
