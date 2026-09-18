"""Audit follow-ups: TASK-035 network-egress refusal at the tool gate;
TASK-071 exit checks keyed by loop id."""

from __future__ import annotations

import json

import pytest

from meridian_core.runtime import LangGraphLoopRunner, LoopDefinition
from meridian_core.tools import SandboxConfig, ToolDeniedError, ToolSurface
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3


def _graph(*edges):
    nodes = {}
    for a, b in edges:
        nodes.setdefault(a, []).append(b)
        nodes.setdefault(b, [])
    return {k: tuple(v) for k, v in nodes.items()}


# -- TASK-035 -------------------------------------------------------------------


def test_network_binary_refused_and_recorded(tmp_path):
    surface = ToolSurface(SandboxConfig(working_dir=tmp_path / "work"))
    surface.permit("agent-1", {"curl"})
    with pytest.raises(ToolDeniedError, match="AC-29"):
        surface.invoke("agent-1", "curl", ["curl", "https://evil.example"])


def test_network_binary_allowed_when_policy_permits(tmp_path):
    surface = ToolSurface(SandboxConfig(working_dir=tmp_path / "work"))
    surface.permit("agent-1", {"curl"})
    surface.permit_network("agent-1")
    argv = ["curl", "--version"] if False else _curl_version_argv()
    result = surface.invoke("agent-1", "curl", argv)
    assert result.ok is True


def _curl_version_argv():
    import sys
    if sys.platform == "win32":
        return ["cmd", "/c", "echo curl 8.0"]  # no network; argv[0] is the check
    return ["curl", "--version"]


def test_non_network_tools_unaffected(tmp_path):
    surface = ToolSurface(SandboxConfig(working_dir=tmp_path / "work"))
    surface.permit("agent-1", {"echo"})
    result = surface.invoke("agent-1", "echo", _echo_argv("ok"))
    assert result.ok is True


def _echo_argv(text):
    import sys
    if sys.platform == "win32":
        return ["cmd", "/c", f"echo {text}"]
    return ["echo", text]


# -- TASK-071 -------------------------------------------------------------------


def _defn(loop_id: str):
    return LoopDefinition(
        loop_id=loop_id, entry_condition="x", body_graph=_graph(("a", "b")),
        exit_criteria="done", max_iterations=3, token_budget=100,
        wall_clock_budget_s=60, cost_ceiling_usd=1.0, escalation_target="human",
    )


def test_exit_checks_keyed_by_loop_id_not_object_identity(tmp_path):
    conn = sqlite3.connect(tmp_path / "cp.db", check_same_thread=False)
    runner = LangGraphLoopRunner(SqliteSaver(conn))
    first = _defn("L1")
    second = _defn("L1")  # distinct object, same loop id
    runner.with_exit_check(first, lambda state: True)
    # The second definition — a different object — must see the checker.
    assert runner._exit_checks[second.loop_id](None) is True
    conn.close()
