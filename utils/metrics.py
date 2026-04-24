"""In-memory metrics for the /metrics endpoint.

Lightweight aggregates — no external deps, resets on restart. Thread-safe via a
single lock. Hook points:
  - record_usage(stage, input, output, cache_read, cache_create)
        called from _log_usage in app.py for every Opus call
  - incr(counter, n=1)
        generic counter (assessments_started, pdf_generated, etc.)
  - incr_managed_tool(tool_name)
        called from managed-agents event loops (redteam + monitor)

Never raises — metrics bugs must not break the pipeline.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

log = logging.getLogger("regula")

_LOCK = threading.Lock()

_counters: dict[str, int] = defaultdict(int)
_by_stage: dict[str, dict[str, int]] = defaultdict(lambda: {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "cache_create_tokens": 0,
})
_managed_tool_calls: dict[str, int] = defaultdict(int)
_started_at = time.time()


def record_usage(
    stage: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_create: int = 0,
) -> None:
    try:
        with _LOCK:
            s = _by_stage[stage]
            s["calls"] += 1
            s["input_tokens"] += int(input_tokens or 0)
            s["output_tokens"] += int(output_tokens or 0)
            s["cache_read_tokens"] += int(cache_read or 0)
            s["cache_create_tokens"] += int(cache_create or 0)
    except Exception:
        log.exception("metrics.record_usage failed — ignored")


def incr(counter: str, n: int = 1) -> None:
    try:
        with _LOCK:
            _counters[counter] += n
    except Exception:
        pass


def incr_managed_tool(tool_name: str | None) -> None:
    if not tool_name:
        return
    try:
        with _LOCK:
            _managed_tool_calls[tool_name] += 1
    except Exception:
        pass


def snapshot() -> dict[str, Any]:
    with _LOCK:
        by_stage = {k: dict(v) for k, v in _by_stage.items()}
        counters = dict(_counters)
        managed = dict(_managed_tool_calls)

    total_in = sum(v["input_tokens"] for v in by_stage.values())
    total_out = sum(v["output_tokens"] for v in by_stage.values())
    total_read = sum(v["cache_read_tokens"] for v in by_stage.values())
    total_create = sum(v["cache_create_tokens"] for v in by_stage.values())
    denom = total_read + total_create
    cache_hit_ratio = round(total_read / denom, 3) if denom else 0.0

    return {
        "uptime_seconds": round(time.time() - _started_at, 1),
        "counters": counters,
        "by_stage": by_stage,
        "managed_tool_calls": managed,
        "totals": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cache_read_tokens": total_read,
            "cache_create_tokens": total_create,
            "cache_hit_ratio": cache_hit_ratio,
        },
    }
