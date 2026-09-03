"""Session detection tests (X-29, FR-M35-03; F0 Workstream D task 20).

An external agent session must be visible in the session list within 2
seconds of the process starting and disappear within 2 seconds of exit.
Detection is by REAL process listing: the test spawns a harmless
long-running python helper whose name matches a vendor agent process name
and asserts detection through the actual platform process table.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meridian_core.observers.manager import ObserverManager
from meridian_core.observers.processes import (
    ProcessInfo,
    list_processes,
    match_vendor,
)
from meridian_core.observers.sessions import (
    POLL_INTERVAL_SECONDS,
    SessionMonitor,
    detect_process_sessions,
    merge_sessions,
)

X29_BUDGET_SECONDS = 2.0

HELPER_SOURCE = """\
import time
print("fake claude agent helper: idle", flush=True)
time.sleep(120)
"""


def make_claude_exe(tmp_path: Path) -> Path:
    """A real process IMAGE named claude (python.exe copied).

    The detection test must be found by the real platform process listing;
    on Windows the fast listing sees image names, so the helper copies the
    interpreter next to its DLLs under the matching name.
    """
    import shutil

    image_dir = tmp_path / "agent-image"
    image_dir.mkdir(exist_ok=True)
    claude_exe = image_dir / ("claude.exe" if sys.platform == "win32" else "claude")
    shutil.copy(sys.executable, claude_exe)
    if sys.platform == "win32":
        for dll in Path(sys.executable).parent.glob("python*.dll"):
            shutil.copy(dll, image_dir / dll.name)
    return claude_exe


@pytest.fixture()
def claude_helper(tmp_path):
    """A real long-running process whose image name is 'claude'."""
    helper = tmp_path / "claude_probe_helper.py"
    helper.write_text(HELPER_SOURCE, encoding="utf-8")
    claude_exe = make_claude_exe(tmp_path)
    proc = subprocess.Popen(
        [str(claude_exe), str(helper)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=10)


def wait_for(condition, timeout: float, interval: float = 0.05) -> float:
    """Poll condition(); return elapsed seconds when it first holds."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition():
            return time.monotonic() - start
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class TestVendorMatching:
    @pytest.mark.parametrize(
        "name,command_line,expected",
        [
            ("claude.exe", "", "claude-code"),
            ("claude", "/usr/local/bin/claude --project x", "claude-code"),
            ("python.exe", r"python C:\ws\claude_probe_helper.py", "claude-code"),
            ("cursor-agent.exe", "", "cursor"),
            ("copilot-agent", "/opt/copilot/agent", "copilot"),
            ("codex", "", "codex"),
            ("devin", "", "devin"),
            ("gemini", "", "gemini"),
            ("node.exe", "node server.js", None),
            ("claudette.exe", "", None),
            ("myclaude-cli", "", None),
            ("python.exe", "python my_script.py", None),
        ],
    )
    def test_match_vendor(self, name, command_line, expected):
        assert match_vendor(name, command_line) == expected


class TestProcessSessionRecords:
    def test_process_listing_maps_to_vendor_tagged_sessions(self):
        processes = [
            ProcessInfo(pid=101, name="claude.exe", command_line="claude"),
            ProcessInfo(pid=202, name="node.exe", command_line="node app.js"),
            ProcessInfo(pid=303, name="copilot-agent", command_line=""),
        ]
        now = datetime.now(timezone.utc)
        sessions = detect_process_sessions(processes, now)
        assert [(s["vendor"], s["pid"]) for s in sessions] == [
            ("claude-code", 101),
            ("copilot", 303),
        ]
        assert all(s["confidence"] == "telemetry" for s in sessions)
        assert all(s["source"] == "process" for s in sessions)
        assert all(s["sessionId"] == f"proc:{s['pid']}" for s in sessions)

    def test_real_process_listing_finds_the_helper(self, claude_helper):
        # Sanity: the platform listing itself sees the helper.
        processes = list_processes()
        vendors = {
            match_vendor(p.name, p.command_line) for p in processes
        }
        assert "claude-code" in vendors
        assert any(p.pid == claude_helper.pid for p in processes)


class TestX29DetectionBudget:
    """The acceptance test: visible within 2s of start, gone within 2s of exit."""

    def test_session_visible_within_two_seconds(self, tmp_path, claude_helper):
        monitor = SessionMonitor(
            ObserverManager(), tmp_path, processes_factory=list_processes
        )
        monitor.start()
        try:
            elapsed = wait_for(
                lambda: any(
                    s["vendor"] == "claude-code"
                    for s in monitor.snapshot()["sessions"]
                ),
                timeout=X29_BUDGET_SECONDS + 2,
            )
            print(f"\nX-29 detection latency: {elapsed * 1000:.0f} ms")
            assert elapsed < X29_BUDGET_SECONDS

            session = next(
                s
                for s in monitor.snapshot()["sessions"]
                if s["vendor"] == "claude-code"
            )
            assert session["pid"] == claude_helper.pid
            assert session["confidence"] == "telemetry"
        finally:
            monitor.stop()

    def test_session_disappears_within_two_seconds_of_exit(self, tmp_path):
        helper = tmp_path / "claude_probe_helper.py"
        helper.write_text(HELPER_SOURCE, encoding="utf-8")
        claude_exe = make_claude_exe(tmp_path)
        proc = subprocess.Popen(
            [str(claude_exe), str(helper)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        monitor = SessionMonitor(
            ObserverManager(), tmp_path, processes_factory=list_processes
        )
        monitor.start()
        try:
            wait_for(
                lambda: any(
                    s["vendor"] == "claude-code"
                    for s in monitor.snapshot()["sessions"]
                ),
                timeout=X29_BUDGET_SECONDS + 2,
            )
            proc.terminate()
            proc.wait(timeout=10)
            elapsed = wait_for(
                lambda: not any(
                    s["vendor"] == "claude-code"
                    for s in monitor.snapshot()["sessions"]
                ),
                timeout=X29_BUDGET_SECONDS + 2,
            )
            print(f"\nX-29 disappearance latency: {elapsed * 1000:.0f} ms")
            assert elapsed < X29_BUDGET_SECONDS
        finally:
            monitor.stop()
            if proc.poll() is None:
                proc.kill()


class TestSessionMerging:
    def test_observations_merge_with_process_sessions(self, tmp_path):
        from meridian_core.observers.base import Observation

        now = datetime.now(timezone.utc)
        processes = [ProcessInfo(pid=42, name="claude.exe", command_line="")]
        process_sessions = detect_process_sessions(processes, now)
        observation = Observation(
            vendor="claude-code",
            session_id="otel:session-1",
            confidence="direct",
            source="otel",
            detail="OTel export",
            started_at=now.isoformat(),
        )
        from meridian_core.observers.sessions import observation_to_session

        merged = merge_sessions(
            process_sessions, [observation_to_session(observation, now)]
        )
        vendors = [s["vendor"] for s in merged]
        assert vendors.count("claude-code") == 2  # distinct sessions, one vendor
        assert any(s["confidence"] == "direct" for s in merged)

    def test_same_identity_keeps_best_confidence(self):
        now = datetime.now(timezone.utc)
        weak = {
            "sessionId": "proc:7",
            "vendor": "codex",
            "confidence": "inferred",
            "source": "filesystem",
            "detail": "writes",
            "pid": 7,
            "startedAt": None,
            "lastActivityAt": now.isoformat(),
            "agentId": None,
        }
        strong = {**weak, "confidence": "telemetry", "source": "process"}
        (merged,) = merge_sessions([weak], [strong])
        assert merged["confidence"] == "telemetry"


class TestMonitorLifecycle:
    def test_tick_is_synchronous_and_updates_cache(self, tmp_path):
        monitor = SessionMonitor(
            ObserverManager(),
            tmp_path,
            processes_factory=lambda: [
                ProcessInfo(pid=5, name="gemini", command_line="")
            ],
        )
        sessions = monitor.tick()
        assert [s["vendor"] for s in sessions] == ["gemini"]
        assert monitor.snapshot()["sessions"] == sessions
        assert monitor.snapshot()["generatedAt"] is not None

    def test_monitor_thread_starts_and_stops(self, tmp_path):
        monitor = SessionMonitor(ObserverManager(), tmp_path)
        monitor.start()
        try:
            assert monitor.running
        finally:
            monitor.stop()
        assert not monitor.running

    def test_poll_interval_meets_x29_budget(self):
        assert POLL_INTERVAL_SECONDS * 2 <= X29_BUDGET_SECONDS
