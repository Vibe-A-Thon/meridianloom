"""Tool runner capability (FR-M33-02; FR-M28-03 seam).

Builds, tests, linters and scanners execute as configured commands in the
sandbox directory — the command line, the working directory and the timeout
ALWAYS come from policy/workspace config carried on the action payload,
never from this module. The capability captures exit code / stdout /
stderr and parses failure summaries with line-oriented regexes, likewise
from config (``failure_patterns``): each matching line is one failure
record with its line number, the line and the pattern that fired. No
pattern ever "interprets" output semantically; the pass/fail signal is
the exit code, ground truth that must not be paraphrased (SEC-14 records
denials at the same boundary).

Zero model calls: subprocess execution plus regex over captured lines.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from ..childenv import child_environment
from .capabilities import CapabilityOutcome

__all__ = ["ToolRunnerCapability"]

_CAPABILITY_NAME = "tool_runner"

#: Captured output is tailed to keep capability payloads bounded and
#: replay-identical; the full stream stays in the sandbox logs.
_TAIL_LINES = 50

#: Failure records per run are capped; the summary names the cap when hit.
_MAX_FAILURES = 100


def _tail(text: str) -> list[str]:
    lines = text.splitlines()
    return lines[-_TAIL_LINES:]


def _tool_environment() -> dict[str, str]:
    """Environment for sandboxed tool commands.

    The general child process rule removes Meridian secrets. Tool runs also
    must not inherit pytest's own control variables when the capability is
    tested from inside pytest: nested pytest invocations then treat themselves
    as part of the parent run and can change reporting behavior.
    """
    return {
        key: value
        for key, value in child_environment().items()
        if not key.startswith("PYTEST_")
    }


class ToolRunnerCapability:
    """The ``tool_runner`` capability, owned by the ``run_tests`` action
    class (FR-M33-01).

    Payload: ``{tool, config}`` where ``config`` is
    ``{"cwd": <sandbox dir>, "tools": {name: {"command": [...], \
    "timeout_seconds": n, "failure_patterns": [regex, ...]?}}}``.
    A tool with no configured command is refused with the tool named —
    commands are never hard-coded here.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        tool = action.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            return CapabilityOutcome(handled=False, reason="missing 'tool'")
        config = action.get("config")
        if not isinstance(config, Mapping):
            return CapabilityOutcome(handled=False, reason="missing 'config' mapping")
        tools = config.get("tools")
        entry = tools.get(tool) if isinstance(tools, Mapping) else None
        if not isinstance(entry, Mapping):
            return CapabilityOutcome(
                handled=False,
                reason=f"tool '{tool}' has no configured entry — commands come from "
                f"policy/workspace config, never the engine",
            )
        command = entry.get("command")
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(part, str) or not part for part in command)
        ):
            return CapabilityOutcome(
                handled=False, reason=f"tool '{tool}': configured command must be a non-empty list of strings"
            )
        timeout = entry.get("timeout_seconds", 60)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            return CapabilityOutcome(
                handled=False, reason=f"tool '{tool}': timeout_seconds must be a positive number"
            )
        cwd = config.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return CapabilityOutcome(handled=False, reason="config 'cwd' (sandbox directory) is required")
        sandbox = Path(cwd)
        if not sandbox.is_dir():
            return CapabilityOutcome(handled=False, reason=f"sandbox directory does not exist: {sandbox}")

        patterns = self._patterns(entry, tool)
        if isinstance(patterns, CapabilityOutcome):
            return patterns

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(sandbox),
                # A sandboxed tool that inherits the ledger signing key is not
                # sandboxed. It used to inherit the sidecar's whole
                # environment (SEC-27; see meridian_core.childenv).
                env=_tool_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            timed_out = False
            exit_code: int | None = completed.returncode
            stdout, stderr = completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as error:
            timed_out = True
            exit_code = None
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
        except OSError as error:
            return CapabilityOutcome(
                handled=False, reason=f"tool '{tool}' could not start: {error}"
            )
        duration_ms = int((time.monotonic() - started) * 1000)

        failures, capped = self._failures(stdout, stderr, patterns)
        return CapabilityOutcome(
            handled=True,
            result={
                "tool": tool,
                "command": command,
                "cwd": str(sandbox),
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "passed": exit_code == 0 and not timed_out,
                "stdout_tail": _tail(stdout),
                "stderr_tail": _tail(stderr),
                "failures": failures,
                "failures_capped": capped,
            },
            reason=f"tool '{tool}' executed in sandbox (exit {exit_code}) (FR-M33-02)",
        )

    @staticmethod
    def _patterns(entry: Mapping[str, Any], tool: str) -> "list[re.Pattern[str]] | CapabilityOutcome":
        raw = entry.get("failure_patterns", [])
        if not isinstance(raw, list) or any(not isinstance(p, str) for p in raw):
            return CapabilityOutcome(
                handled=False, reason=f"tool '{tool}': failure_patterns must be a list of regex strings"
            )
        compiled: list[re.Pattern[str]] = []
        for pattern in raw:
            try:
                compiled.append(re.compile(pattern))
            except re.error as error:
                return CapabilityOutcome(
                    handled=False, reason=f"tool '{tool}': invalid failure pattern {pattern!r}: {error}"
                )
        return compiled

    @staticmethod
    def _failures(
        stdout: str, stderr: str, patterns: "list[re.Pattern[str]]"
    ) -> "tuple[list[dict[str, Any]], bool]":
        """Line-oriented deterministic parse: every line of stdout and
        stderr is tested against every configured pattern; a hit is one
        failure record."""
        failures: list[dict[str, Any]] = []
        capped = False
        if not patterns:
            return failures, capped
        for stream_name, text in (("stdout", stdout), ("stderr", stderr)):
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pattern in patterns:
                    if pattern.search(line):
                        if len(failures) >= _MAX_FAILURES:
                            capped = True
                            return failures, capped
                        failures.append(
                            {
                                "stream": stream_name,
                                "line": lineno,
                                "text": line,
                                "pattern": pattern.pattern,
                            }
                        )
                        break
        return failures, capped
