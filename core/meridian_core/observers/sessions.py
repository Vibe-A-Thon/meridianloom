"""External session detection and monitoring (X-29, FR-M35-03).

An external agent session becomes visible in the session list (the data
behind the Crown) within 2 seconds: the monitor polls running processes
(vendor agent names) and the observer framework's observations, maps them
to session records with vendor tag + observation confidence, and keeps the
result in a cache that RPC handlers read WITHOUT waiting on observer IO
(NFR-29).

The monitor thread is the only place observer IO happens; ``snapshot()``
is a lock-protected read of the last completed tick.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import fsprobe
from .manager import ObserverManager
from .processes import ProcessInfo, list_processes, match_vendor

# X-29: detection (and disappearance) within 2 seconds; poll at 0.5 s.
POLL_INTERVAL_SECONDS = 0.5

# A session whose process vanishes is still shown this long (covers the
# poll gap so the UI does not flicker between ticks).
_GRACE_SECONDS = 0.0

_PROCESS_CONFIDENCE = "telemetry"
_PROCESS_SOURCE = "process"


def detect_process_sessions(
    processes: list[ProcessInfo],
    now: datetime,
) -> list[dict[str, Any]]:
    """Process listing -> session records with vendor tags (X-29)."""
    sessions: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for info in processes:
        vendor = match_vendor(info.name, info.command_line)
        if vendor is None:
            continue
        key = (vendor, info.pid)
        if key in seen:
            continue
        seen.add(key)
        sessions.append(
            {
                "sessionId": f"proc:{info.pid}",
                "vendor": vendor,
                "confidence": _PROCESS_CONFIDENCE,
                "source": _PROCESS_SOURCE,
                "detail": f"process {info.name} (pid {info.pid}) is running",
                "pid": info.pid,
                "startedAt": None,
                "lastActivityAt": now.isoformat(),
                "agentId": None,
            }
        )
    return sessions


def observation_to_session(observation, now: datetime) -> dict[str, Any]:
    return {
        "sessionId": observation.session_id,
        "vendor": observation.vendor,
        "confidence": observation.confidence,
        "source": observation.source,
        "detail": observation.detail,
        "pid": None,
        "startedAt": observation.started_at,
        "lastActivityAt": now.isoformat(),
        "agentId": observation.agent_id,
    }


def merge_sessions(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union session records, deduplicated by (vendor, sessionId)."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        for record in group:
            key = (record["vendor"], record["sessionId"])
            existing = merged.get(key)
            if existing is None or _confidence_rank(record) < _confidence_rank(existing):
                merged[key] = record
    return [merged[key] for key in sorted(merged, key=lambda k: (k[0], k[1]))]


def _confidence_rank(record: dict[str, Any]) -> int:
    try:
        return ("direct", "telemetry", "inferred").index(record["confidence"])
    except ValueError:
        return len(("direct", "telemetry", "inferred"))


class SessionMonitor:
    """Polls processes + observers; serves cached session records (X-29).

    All observation work (git, gh probes, fs walks, OTLP parsing) happens
    on the single monitor thread. RPC handlers call :meth:`snapshot`,
    which never touches observer IO (NFR-29).
    """

    def __init__(
        self,
        manager: ObserverManager,
        workspace: Path | str,
        interval_seconds: float = POLL_INTERVAL_SECONDS,
        processes_factory: Callable[[], list[ProcessInfo]] = list_processes,
        write_probe: Callable[..., fsprobe.WriteBurst | None] = fsprobe.recent_writes,
    ) -> None:
        self._manager = manager
        self._workspace = Path(workspace)
        self._interval = interval_seconds
        self._list_processes = processes_factory
        self._write_probe = write_probe
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {
            "sessions": [],
            "warnings": [],
            "generatedAt": None,
        }
        self._thread: threading.Thread | None = None
        self._ticks = 0

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="meridian-session-monitor",
            daemon=True,  # never outlives the sidecar process
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def ticks(self) -> int:
        return self._ticks

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the monitor must never die silently
                with self._lock:
                    self._cache = {
                        **self._cache,
                        "warnings": [
                            *self._cache["warnings"],
                            "session monitor tick failed (G3: observation degrades, never silently)",
                        ],
                    }
            self._stop.wait(self._interval)

    # -- one detection pass (synchronous; directly testable) ---------------------

    def tick(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        process_sessions = detect_process_sessions(self._list_processes(), now)
        observations = self._manager.observe(self._workspace, now)
        observation_sessions = [
            observation_to_session(observation, now) for observation in observations
        ]
        sessions = merge_sessions(process_sessions, observation_sessions)
        warnings = self._manager.warnings()
        with self._lock:
            self._ticks += 1
            self._cache = {
                "sessions": sessions,
                "warnings": list(warnings),
                "generatedAt": now.isoformat(),
            }
        return sessions

    # -- RPC-facing read: never waits on observer IO ------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sessions": list(self._cache["sessions"]),
                "warnings": list(self._cache["warnings"]),
                "generatedAt": self._cache["generatedAt"],
            }
