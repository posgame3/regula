"""SQLite-backed persistence for assessment sessions.

Why: in-memory sessions are lost on server restart — mid-assessment users see
the chat close, and /report/{session_id} returns 404 for any PDF downloaded
after a redeploy. SQLite survives restarts and is good enough for a single-box
deployment (the app's target scale).

Design:
  - One table `sessions(session_id, created_at, updated_at, data JSON)`.
  - Whole session dict stored as JSON — we don't query fields individually.
  - Write-through on every stage change (small, fast); the WebSocket path
    still reads from an in-memory cache for latency.
  - SQLite connection is process-local with `check_same_thread=False`
    + a single write lock, so concurrent FastAPI requests don't corrupt state.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(BASE_DIR, "data", "regula.db")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL,
            stage       TEXT NOT NULL,
            data        TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)")
    _conn = conn
    return conn


def _sanitize_for_json(session: dict) -> dict:
    """Drop unserialisable keys before JSON-encoding.
    `messages` blocks can contain SDK objects captured during the pipeline;
    we only need to restore business state (findings/results) after a restart.
    """
    return {k: v for k, v in session.items() if k != "messages"}


def save(session: dict) -> None:
    """Write-through on every meaningful transition. Idempotent."""
    sid = session.get("session_id")
    if not sid:
        return
    now = time.time()
    data = json.dumps(_sanitize_for_json(session), ensure_ascii=False, default=str)
    stage = session.get("stage") or ""
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO sessions(session_id, created_at, updated_at, stage, data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                stage      = excluded.stage,
                data       = excluded.data
            """,
            (sid, now, now, stage, data),
        )


def load(session_id: str) -> dict | None:
    """Return the persisted session dict or None. Messages are NOT restored —
    the WebSocket conversation is dead once the server restarted; but the
    analysis/PDF data is intact.
    """
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    try:
        session = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    session.setdefault("messages", [])  # frontend never reads these post-restart
    return session


def list_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Small helper for ops/debug — not exposed via the public API."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT session_id, stage, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {"session_id": r[0], "stage": r[1], "updated_at": r[2]}
        for r in rows
    ]
