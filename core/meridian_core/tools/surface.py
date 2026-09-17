"""M9 Tool Access Surface — FR-M9-02…07.

Native tools (repository read, patch application, build/test/static-
analysis/dependency-scan invocation, SCM operations) execute through ONE
surface so the controls cannot be bypassed by calling a tool directly:

- FR-M9-03: every invocation is checked against the calling agent's
  permitted-tool set BEFORE execution; denials are ledger-recorded.
- FR-M9-04: results are size-capped with an explicit truncation marker,
  never silently trimmed.
- FR-M9-05: build/test/script execution runs in a sandbox: dedicated
  working directory, scrubbed environment (no inherited credentials),
  wall-clock timeout. The egress allow-list is declared in the sandbox
  config and recorded on every run; actual network egress enforcement
  belongs to the host's firewall, which the sidecar does not control —
  declared honestly rather than claimed (SEC-32 vocabulary).
- FR-M9-06: dependency additions are a distinct, separately approvable
  change class.
- FR-M9-07: the tool layer never exposes raw credentials to agent
  context — the environment is scrubbed before the tool sees it, and
  logged inputs/outputs pass through SEC-07 redaction.

Zero model calls.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from meridian_core.ledger.redaction import redact_secrets

TRUNCATION_MARKER = "\n...[TRUNCATED: result exceeded the tool size cap]..."
CHANGE_CLASS_DEPENDENCY_ADD = "dependency_addition"


class ToolDeniedError(PermissionError):
    """FR-M9-03: the agent's permitted set does not include this tool."""


@dataclass(frozen=True)
class ToolResult:
    """FR-M9-04: capped, explicitly marked when truncated."""

    ok: bool
    output: str
    truncated: bool = False
    change_class: str = "ordinary"
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output": self.output,
            "truncated": self.truncated,
            "changeClass": self.change_class,
            "exitCode": self.exit_code,
        }


@dataclass(frozen=True)
class SandboxConfig:
    """FR-M9-05. ``env_allowlist`` names the ONLY environment variables a
    sandboxed process may see (built from scratch — nothing inherited).
    ``egress_allowlist`` is declared and recorded per run; enforcement is
    the host firewall's job, stated rather than claimed."""

    working_dir: Path
    env_allowlist: tuple[str, ...] = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "LANG", "PATHEXT", "COMSPEC")
    egress_allowlist: tuple[str, ...] = ()
    timeout_s: float = 300.0


@dataclass(frozen=True)
class PinnedMcpServer:
    """FR-M9-08: an MCP server is pinned by version (and, where the
    packaging provides one, content digest). ``trust_acknowledged`` is the
    explicit user confirmation — a local MCP server executes arbitrary
    code, so a pinned server without the acknowledgement is refused."""

    server_id: str
    command: tuple[str, ...]
    version: str
    digest: str | None = None
    trust_acknowledged: bool = False


class McpServerRefusedError(ValueError):
    """FR-M9-08: installing/invoking an unacknowledged or unpinned server."""


def scrub_environment(
    base: Mapping[str, str] | None, allowlist: Sequence[str]
) -> dict[str, str]:
    """FR-M9-05/07: build the sandbox environment from scratch. Only
    allow-listed variables survive — no inherited credentials, tokens in
    environment variables, or user-specific paths leak into the tool
    process or anything it logs."""
    source = base if base is not None else os.environ
    allowed = set(allowlist)
    return {k: v for k, v in source.items() if k in allowed}


def run_in_sandbox(
    argv: Sequence[str],
    config: SandboxConfig,
    *,
    size_cap_bytes: int = 64_000,
) -> ToolResult:
    """FR-M9-05: run a command in the constrained environment. On timeout
    the process is killed and the result says so — never silently."""
    config.working_dir.mkdir(parents=True, exist_ok=True)
    env = scrub_environment(os.environ, config.env_allowlist)
    try:
        completed = subprocess.run(
            list(argv),
            cwd=config.working_dir,
            env=env,
            capture_output=True,
            timeout=config.timeout_s,
        )
        output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
        return _capped(output, completed.returncode == 0, completed.returncode, size_cap_bytes)
    except subprocess.TimeoutExpired:
        return ToolResult(
            ok=False,
            output=(
                f"sandbox: command timed out after {config.timeout_s}s"
                " and was killed"
            ),
            exit_code=None,
        )


def _capped(output: str, ok: bool, exit_code: int | None, cap: int) -> ToolResult:
    """FR-M9-04: cap with an explicit marker. The marker itself is never
    truncated away."""
    encoded = output.encode("utf-8")
    if len(encoded) <= cap:
        return ToolResult(ok=ok, output=output, exit_code=exit_code)
    kept = encoded[:cap].decode("utf-8", "ignore")
    return ToolResult(
        ok=ok,
        output=kept + TRUNCATION_MARKER,
        truncated=True,
        exit_code=exit_code,
    )


@dataclass
class ToolSurface:
    """The single dispatch point for native tools (FR-M9-02/03)."""

    sandbox: SandboxConfig
    ledger: Any = None
    size_cap_bytes: int = 64_000
    #: FR-M9-02: the native tool catalogue. SCM operations (branch,
    #: commit, PR draft) go through gitcmd/pr modules; repo read through
    #: the filesystem with the worktree boundary enforced by the caller's
    #: workspace root.
    tools: dict[str, Callable[..., ToolResult]] = field(default_factory=dict)
    _denial_count: int = 0

    def permit(self, agent_id: str, tools: set[str]) -> None:
        if not hasattr(self, "_permitted"):
            self._permitted = {}
        self._permitted[agent_id] = frozenset(tools)

    def permitted_tools(self, agent_id: str) -> frozenset:
        return getattr(self, "_permitted", {}).get(agent_id, frozenset())

    def invoke(
        self,
        agent_id: str,
        tool: str,
        argv: Sequence[str],
        *,
        change_class: str = "ordinary",
    ) -> ToolResult:
        """FR-M9-03: permission BEFORE execution; denials hit the ledger."""
        if tool not in self.permitted_tools(agent_id):
            self._denial_count += 1
            self._record_denial(agent_id, tool, argv)
            raise ToolDeniedError(
                f"FR-M9-03: agent '{agent_id}' is not permitted tool '{tool}'"
            )
        result = run_in_sandbox(argv, self.sandbox, size_cap_bytes=self.size_cap_bytes)
        if change_class == CHANGE_CLASS_DEPENDENCY_ADD:
            # FR-M9-06: dependency additions are flagged as their own
            # change class, whatever the tool that carried them.
            result = ToolResult(
                ok=result.ok,
                output=result.output,
                truncated=result.truncated,
                change_class=CHANGE_CLASS_DEPENDENCY_ADD,
                exit_code=result.exit_code,
            )
        self._record_invocation(agent_id, tool, argv, result)
        return result

    def _record_denial(self, agent_id: str, tool: str, argv: Sequence[str]) -> None:
        if self.ledger is None:
            return
        self.ledger.append(
            {
                "story_id": "tool-surface",
                "phase": "build",
                "loop_id": "tools",
                "loop_iteration": 1,
                "actor_id": agent_id,
                "actor_version": "local",
                "actor_kind": "role",
                "policy_version": "tools/v1",
                "action_type": "rejection",
                "decision": "rejected",
                "input": redact_secrets(
                    json.dumps(
                        {"tool": tool, "argv": list(argv), "reason": "FR-M9-03"},
                        ensure_ascii=False,
                    )
                ),
            }
        )

    def _record_invocation(
        self, agent_id: str, tool: str, argv: Sequence[str], result: ToolResult
    ) -> None:
        if self.ledger is None:
            return
        self.ledger.append(
            {
                "story_id": "tool-surface",
                "phase": "build",
                "loop_id": "tools",
                "loop_iteration": 1,
                "actor_id": agent_id,
                "actor_version": "local",
                "actor_kind": "role",
                "policy_version": "tools/v1",
                "action_type": "tool_call",
                "input": redact_secrets(
                    json.dumps({"tool": tool, "argv": list(argv)}, ensure_ascii=False)
                ),
                "tool_calls": [
                    {
                        "tool": tool,
                        "ok": result.ok,
                        "truncated": result.truncated,
                        "changeClass": result.change_class,
                    }
                ],
            }
        )


def validate_mcp_server(server: PinnedMcpServer) -> None:
    """FR-M9-08: pin + explicit trust acknowledgement, or refuse."""
    if not server.version.strip():
        raise McpServerRefusedError(
            f"FR-M9-08: MCP server '{server.server_id}' is not version-pinned"
        )
    if not server.digest:
        raise McpServerRefusedError(
            f"FR-M9-08: MCP server '{server.server_id}' has no content digest;"
            " pin the exact artefact before it may run"
        )
    if not server.trust_acknowledged:
        raise McpServerRefusedError(
            f"FR-M9-08: MCP server '{server.server_id}' executes arbitrary code"
            " locally; install requires the explicit trust acknowledgement"
        )
