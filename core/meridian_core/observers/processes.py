"""Process inspection for external-agent session detection (X-29).

Cross-platform, read-only listing of running processes: the vendor agent
process names (claude, cursor-agent, copilot-agent, codex, devin, gemini)
are matched against process names AND command lines — a helper executable
named ``claude.exe`` is detected exactly like the real one.

Windows: a ``ctypes`` Toolhelp snapshot enumeration — no child process,
~milliseconds even under aggressive endpoint scanning, which is what keeps
X-29's 2-second budget. EnumProcesses and ``tasklist`` are the fallbacks.
POSIX: ``ps -eo pid=,comm=,args=`` (names + full command lines).

Every spawned probe runs with a SEC-27-scrubbed environment (no
MERIDIAN_* variables cross into the child). Pure stdlib; zero model calls.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from .isolation import scrub_env

# X-29: the vendor agents the Crown must notice within 2 seconds.
AGENT_PROCESS_NAMES = ("claude", "cursor-agent", "copilot-agent", "codex", "devin", "gemini")

VENDOR_BY_PROCESS = {
    "claude": "claude-code",
    "cursor-agent": "cursor",
    "copilot-agent": "copilot",
    "codex": "codex",
    "devin": "devin",
    "gemini": "gemini",
}

_PROCESS_TIMEOUT_SECONDS = 15
_PID_BUFFER = 4096
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TH32CS_SNAPPROCESS = 0x00000002

# A process name must appear as a standalone token (name or command line):
# "claude.exe", "/usr/bin/claude", "fake_claude_helper.py" all match;
# "claudette" and "myclaude" do not.
_TOKEN_BOUNDARY = r"(?<![a-z0-9]){}(?![a-z0-9])"
_MATCHERS = [
    (name, re.compile(_TOKEN_BOUNDARY.format(re.escape(name)))) for name in AGENT_PROCESS_NAMES
]


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    command_line: str


def match_vendor(name: str, command_line: str) -> str | None:
    """Map a process name/command line to a vendor id, or None."""
    haystack = f"{name}\n{command_line}".lower()
    for process_name, pattern in _MATCHERS:
        if pattern.search(haystack):
            return VENDOR_BY_PROCESS[process_name]
    return None


def _run_probe(argv: list[str], timeout: float) -> str:
    env, _scrubbed = scrub_env()
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"probe failed: {argv[0]}")
    return result.stdout


def _list_windows_fast() -> list[ProcessInfo]:
    """Toolhelp snapshot enumeration: one kernel call, ~milliseconds.

    No child process is spawned, so endpoint-scanning overhead cannot blow
    the X-29 2-second budget.
    """
    import ctypes

    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        raise RuntimeError(f"CreateToolhelp32Snapshot failed: {ctypes.get_last_error()}")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        processes: list[ProcessInfo] = []
        has_more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while has_more:
            if entry.th32ProcessID != 0:
                processes.append(
                    ProcessInfo(
                        pid=int(entry.th32ProcessID),
                        name=entry.szExeFile,
                        command_line="",
                    )
                )
            has_more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return processes
    finally:
        kernel32.CloseHandle(snapshot)


def _list_windows_api() -> list[ProcessInfo]:
    """EnumProcesses + QueryFullProcessImageFileNameW — second fallback."""
    import ctypes

    from ctypes import wintypes

    psapi = ctypes.windll.psapi
    kernel32 = ctypes.windll.kernel32

    pids = (wintypes.DWORD * _PID_BUFFER)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(
        ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(needed)
    ):
        raise RuntimeError("EnumProcesses failed")
    count = needed.value // ctypes.sizeof(wintypes.DWORD)

    name_buffer = ctypes.create_unicode_buffer(512)
    processes: list[ProcessInfo] = []
    for index in range(count):
        pid = pids[index]
        if pid == 0:
            continue
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            continue  # protected/system process: not an agent we can see
        try:
            length = wintypes.DWORD(ctypes.sizeof(name_buffer))
            ok = kernel32.QueryFullProcessImageFileNameW(
                handle, 0, name_buffer, ctypes.byref(length)
            )
            if not ok or length.value == 0:
                continue
            # Device path, e.g. \Device\HarddiskVolume3\...\claude.exe
            image = name_buffer.value.rsplit("\\", 1)[-1]
            processes.append(
                ProcessInfo(pid=int(pid), name=image, command_line="")
            )
        finally:
            kernel32.CloseHandle(handle)
    return processes


def _list_windows_fallback() -> list[ProcessInfo]:
    """tasklist names-only (no command lines) — last-resort fallback."""
    raw = _run_probe(
        ["tasklist", "/FO", "CSV", "/NH"], _PROCESS_TIMEOUT_SECONDS
    )
    processes = []
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 2:
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        processes.append(ProcessInfo(pid=pid, name=row[0], command_line=""))
    return processes


def _list_windows() -> list[ProcessInfo]:
    for listing in (_list_windows_fast, _list_windows_api):
        try:
            return listing()
        except Exception:  # noqa: BLE001 - next listing strategy
            continue
    # tasklist either works or raises — never a silent empty listing.
    return _list_windows_fallback()


def _list_posix() -> list[ProcessInfo]:
    raw = _run_probe(["ps", "-eo", "pid=,comm=,args="], _PROCESS_TIMEOUT_SECONDS)
    processes = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command_line = parts[2] if len(parts) > 2 else parts[1]
        processes.append(ProcessInfo(pid=pid, name=parts[1], command_line=command_line))
    return processes


def list_processes() -> list[ProcessInfo]:
    """Every running process with (pid, name, command line)."""
    if sys.platform == "win32":
        return _list_windows()
    return _list_posix()


ProcessLister = Callable[[], list[ProcessInfo]]
