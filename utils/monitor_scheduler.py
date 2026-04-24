"""Background scheduler for the Regulatory Monitor.

Plain asyncio loop (no APScheduler dependency). On each tick, enumerates
subscribed profiles from profile_store and runs run_managed_monitor for those
whose last_check_iso is older than min_interval. Runs are staggered so we
never fire parallel Anthropic sessions from one server process.

Configurable via env:
    MONITOR_INTERVAL_HOURS       how often the tick fires (default 168 = weekly)
    MONITOR_STAGGER_SECONDS      gap between per-user runs (default 30)
    MONITOR_MIN_INTERVAL_HOURS   skip profiles checked more recently (default 24)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from utils import profile_store

log = logging.getLogger("regula")

MonitorRunner = Callable[[dict], Awaitable[dict]]


class MonitorScheduler:
    def __init__(
        self,
        runner: MonitorRunner,
        *,
        interval_seconds: int,
        stagger_seconds: int = 30,
        min_interval_seconds: int = 24 * 3600,
    ) -> None:
        self._runner = runner
        self._interval = max(60, int(interval_seconds))
        self._stagger = max(0, int(stagger_seconds))
        self._min_interval = max(0, int(min_interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_tick_iso: str | None = None
        self._last_runs: int = 0

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "[monitor] scheduler started: interval=%ds stagger=%ds min_interval=%ds",
            self._interval, self._stagger, self._min_interval,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        log.info("[monitor] scheduler stopped")

    def status(self) -> dict:
        return {
            "running": self._task is not None and not self._task.done(),
            "interval_seconds": self._interval,
            "stagger_seconds": self._stagger,
            "min_interval_seconds": self._min_interval,
            "last_tick_iso": self._last_tick_iso,
            "last_tick_runs": self._last_runs,
        }

    async def _loop(self) -> None:
        try:
            # Tick once shortly after startup so we don't wait a whole interval
            # before the first pass. Nothing runs if no due profiles.
            await asyncio.sleep(5)
            while not self._stop.is_set():
                try:
                    await self._tick()
                except Exception:
                    log.exception("[monitor] tick failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                    return
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _tick(self) -> None:
        profiles = profile_store.list_profiles()
        due = [p for p in profiles if self._is_due(p)]
        self._last_tick_iso = _now_iso()
        self._last_runs = 0
        if not due:
            log.info("[monitor] tick — %d profiles, 0 due", len(profiles))
            return
        log.info("[monitor] tick — %d profiles, %d due", len(profiles), len(due))
        for profile in due:
            if self._stop.is_set():
                return
            try:
                await self._runner(profile)
                self._last_runs += 1
            except Exception:
                log.exception("[monitor] run failed for user %s", profile.get("user_id"))
            await asyncio.sleep(self._stagger)

    def _is_due(self, profile: dict) -> bool:
        last = profile.get("last_check_iso")
        if not last:
            return True
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - last_dt >= timedelta(seconds=self._min_interval)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
