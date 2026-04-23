"""JSON file-backed store for monitored user profiles + queued alerts.

One file per project run: data/profiles.json.
Not thread-safe under heavy concurrency — intended for hackathon demo scale.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
STORE_PATH = BASE_DIR / "data" / "profiles.json"
_LOCK = threading.Lock()


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"profiles": {}}
    try:
        return json.loads(STORE_PATH.read_text() or "{}") or {"profiles": {}}
    except json.JSONDecodeError:
        return {"profiles": {}}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(STORE_PATH)


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
        data = _load()
        if not user_id:
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
        profile = data["profiles"].get(user_id, {})
        profile.update({
            "user_id": user_id,
            "email": email,
            "sector": sector,
            "language": language,
            "open_gaps": open_gaps,
            "company_name": company_name,
            "created_at": profile.get("created_at") or _now_iso(),
            "last_check_iso": profile.get("last_check_iso"),
            "alerts": profile.get("alerts", []),
        })
        data["profiles"][user_id] = profile
        _save(data)
        return profile


def get_profile(user_id: str) -> dict | None:
    with _LOCK:
        return _load()["profiles"].get(user_id)


def list_profiles() -> list[dict]:
    with _LOCK:
        return list(_load()["profiles"].values())


def append_alert(user_id: str, alert: dict) -> dict | None:
    with _LOCK:
        data = _load()
        profile = data["profiles"].get(user_id)
        if not profile:
            return None
        alert = dict(alert)
        alert.setdefault("id", f"alt_{uuid.uuid4().hex[:12]}")
        alert.setdefault("created_at", _now_iso())
        profile.setdefault("alerts", []).append(alert)
        data["profiles"][user_id] = profile
        _save(data)
        return alert


def mark_checked(user_id: str) -> None:
    with _LOCK:
        data = _load()
        profile = data["profiles"].get(user_id)
        if not profile:
            return
        profile["last_check_iso"] = _now_iso()
        data["profiles"][user_id] = profile
        _save(data)


def list_alerts(user_id: str) -> list[dict]:
    with _LOCK:
        profile = _load()["profiles"].get(user_id)
        return list(profile.get("alerts", [])) if profile else []


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
