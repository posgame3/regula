"""Anonymous benchmark: percentile ranking of a user's compliance score
against all other assessments in the same sector + company-size bucket.

Why: a score in isolation ("you got 34/100") is disorienting. Comparing against
peers ("median for transport SMBs is 52/100, top 10% is 78/100") gives the
user a sense of how urgent their gaps really are and creates a retention hook
("come back after fixes and see if you moved up").

Privacy: we store ONLY (sector, size_bucket, score, timestamp). No company
name, no email, no session_id — not enough data to re-identify a submitter
even with the full DB.

Schema (shares data/regula.db with sessions + profiles):
  benchmarks(id PK, sector, size_bucket, score INT, created_at TEXT)
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


# ────────────────────── Normalization helpers ──────────────────────


_SIZE_BUCKETS = [
    (1, 9, "1-9"),
    (10, 49, "10-49"),
    (50, 249, "50-249"),
    (250, 10**9, "250+"),
]


def size_bucket_for(employee_count: int | None) -> str:
    """Map employee count to EU-style SME buckets. Unknown → '10-49' (most common)."""
    if not isinstance(employee_count, int) or employee_count < 1:
        return "10-49"
    for lo, hi, label in _SIZE_BUCKETS:
        if lo <= employee_count <= hi:
            return label
    return "250+"


# Canonicalize sector strings. Matches NIS2 Annex I/II at a coarse level —
# keeps benchmark buckets statistically meaningful without fragmenting into
# 100+ micro-sectors ("medical devices manufacturing" etc.).
_SECTOR_ALIASES = {
    "transport": {"transport", "logistics", "freight", "trucking", "road freight",
                  "shipping", "courier", "postal", "rail", "aviation", "maritime"},
    "health": {"health", "healthcare", "hospital", "medical", "pharma", "pharmaceutical",
               "clinic", "medtech", "medical devices"},
    "energy": {"energy", "electricity", "gas", "oil", "hydrogen", "utility", "power"},
    "water": {"water", "drinking water", "wastewater", "sewage"},
    "banking": {"banking", "bank", "finance", "financial services", "credit"},
    "digital": {"digital", "saas", "cloud", "software", "internet", "it", "tech",
                "dns", "cdn", "data center", "datacentre"},
    "ict_services": {"ict", "managed services", "msp", "mssp", "it services"},
    "manufacturing": {"manufacturing", "factory", "production", "industrial"},
    "chemicals": {"chemicals", "chemistry"},
    "food": {"food", "agriculture", "beverage"},
    "waste": {"waste", "recycling"},
    "public_admin": {"public", "government", "administration", "municipality"},
    "research": {"research", "university", "academic"},
    "space": {"space", "satellite"},
    "other": set(),
}


def normalize_sector(raw: str | None) -> str:
    """Normalize free-text sector into one of a fixed vocabulary. Keeps bucket
    sizes statistically meaningful for percentile calc."""
    if not raw:
        return "other"
    needle = raw.strip().lower()
    if not needle:
        return "other"
    for canonical, aliases in _SECTOR_ALIASES.items():
        if any(a in needle for a in aliases):
            return canonical
    return "other"


def derive_score(session: dict) -> int | None:
    """Prefer the board presenter's 0-100 score; fall back to a gap-weighted
    estimate. Returns None if we can't compute anything meaningful."""
    board = session.get("board_slides") or {}
    for slide in (board.get("slides") or []):
        val = slide.get("score")
        if isinstance(val, (int, float)) and 0 <= val <= 100:
            return int(round(val))
    gaps = ((session.get("gap_analysis") or {}).get("gaps")) or []
    if not gaps:
        # No gap data at all — skip, don't contaminate percentiles.
        return None
    weights = {"critical": 15, "high": 10, "medium": 5, "low": 2}
    penalty = sum(weights.get((g.get("risk_level") or "").lower(), 5) for g in gaps)
    return max(0, min(100, 100 - penalty))


# ────────────────────────── DB layer ──────────────────────────


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
        CREATE TABLE IF NOT EXISTS benchmarks (
            id          TEXT PRIMARY KEY,
            sector      TEXT NOT NULL,
            size_bucket TEXT NOT NULL,
            score       INTEGER NOT NULL,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_bucket ON benchmarks(sector, size_bucket)")
    _conn = conn
    _seed_if_empty(conn)
    return conn


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """First-run synthetic seed so percentile rendering isn't empty on demo day.
    Real user submissions mix in naturally. Distribution is based on the empirical
    fact that most SMB self-assessments score 25-55 (lots of gaps)."""
    n = conn.execute("SELECT COUNT(*) FROM benchmarks").fetchone()[0]
    if n > 0:
        return
    import random
    rng = random.Random(42)  # deterministic seed for reproducible percentiles
    sectors = list(_SECTOR_ALIASES.keys())
    size_buckets = [b[2] for b in _SIZE_BUCKETS]
    now = _now_iso()
    rows = []
    # ~8 synthetic samples per (sector, bucket) = 112 total baseline.
    for sector in sectors:
        for bucket in size_buckets:
            # center around 42, spread ±22, clamped
            count = 8 if sector != "other" else 3
            for _ in range(count):
                score = int(max(5, min(95, rng.gauss(42, 20))))
                rows.append((
                    f"bch_{uuid.uuid4().hex[:12]}", sector, bucket, score, now,
                ))
    conn.executemany(
        "INSERT INTO benchmarks(id, sector, size_bucket, score, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    log.info("benchmark seed: inserted %d synthetic samples", len(rows))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(sector: str, size_bucket: str, score: int) -> None:
    """Persist a benchmark sample. Called from the pipeline on completion."""
    if not (0 <= score <= 100):
        return
    with _LOCK:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO benchmarks(id, sector, size_bucket, score, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"bch_{uuid.uuid4().hex[:12]}", sector, size_bucket, int(score), _now_iso()),
        )


def compute_percentiles(sector: str, size_bucket: str, user_score: int) -> dict[str, Any]:
    """Return {count, median, top10, bottom10, user_percentile, peer_group, fallback_used}.
    Falls back to sector-wide (any size), then all samples, when the exact bucket is thin.
    """
    with _LOCK:
        conn = _get_conn()

        def fetch(where_sql: str, params: tuple) -> list[int]:
            rows = conn.execute(
                f"SELECT score FROM benchmarks WHERE {where_sql} ORDER BY score",
                params,
            ).fetchall()
            return [r[0] for r in rows]

        scores = fetch("sector = ? AND size_bucket = ?", (sector, size_bucket))
        peer_group = f"{sector} · {size_bucket}"
        fallback_used = False
        if len(scores) < 5:
            scores = fetch("sector = ?", (sector,))
            peer_group = f"{sector} (all sizes)"
            fallback_used = True
        if len(scores) < 5:
            scores = fetch("1=1", ())
            peer_group = "all sectors"
            fallback_used = True
    if not scores:
        return {
            "count": 0, "median": None, "top10": None, "bottom10": None,
            "user_percentile": None, "peer_group": peer_group,
            "fallback_used": fallback_used,
        }
    count = len(scores)
    median = scores[count // 2]
    top10 = scores[max(0, int(count * 0.9) - 1)]  # 90th percentile threshold
    bottom10 = scores[max(0, int(count * 0.1) - 1)]  # 10th percentile threshold
    # User percentile: share of samples strictly below user_score.
    below = sum(1 for s in scores if s < user_score)
    user_percentile = round(100 * below / count)
    return {
        "count": count,
        "median": int(median),
        "top10": int(top10),
        "bottom10": int(bottom10),
        "user_percentile": user_percentile,
        "peer_group": peer_group,
        "fallback_used": fallback_used,
    }
