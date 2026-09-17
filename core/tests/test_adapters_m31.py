"""FR-M31-02…04, 06…10, 12, 15 (F3 step 7): adapter discovery, validation,
hot plug / unplug / re-plug, probation admission, plain-Python bridge
sandboxing + permission routing, portability, dependency resolution —
proven against the materialized §6.10 roster. Zero model calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from meridian_core.adapters import (
    AdapterRegistry,
    PlainPythonBridge,
    folder_digest,
    parse_manifest,
)
from meridian_core.adapters.roster import ROSTER, materialize_roster
from meridian_core.tools import SandboxConfig, ToolDeniedError, ToolSurface

ALLOWLIST = frozenset(
    {"repo_read", "build", "test", "apply_patch", "static_analysis", "scan"}
)


@pytest.fixture()
def roster_dir(tmp_path) -> Path:
    return Path(materialize_roster(tmp_path / "adapters")[0]).parent


def test_manifest_digest_matches_folder(roster_dir) -> None:
    manifest = parse_manifest(
        (roster_dir / "developer" / "adapter.yaml").read_text(encoding="utf-8"),
        "developer",
    )
    assert manifest.digest == folder_digest(roster_dir / "developer")


def test_roster_is_the_must_v1_core() -> None:
    ids = {spec["id"] for spec in ROSTER}
    assert {
        "chief-orchestrator", "phase-orchestrator", "analyst", "architect",
        "tech-lead", "scrum-master", "developer", "front-end-engineer",
        "qa-engineer", "qa-lead", "security", "reviewer", "xai", "governance",
    } <= ids


# -- FR-M31-02/03: discovery + validation ---------------------------------------


def test_discovery_loads_full_roster_into_probation(roster_dir) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    assert len(registry.adapters) == len(ROSTER)
    # FR-M31-07: every admitted adapter enters at probation.
    assert all(
        registry.states[a] == "probation" for a in registry.adapters
    )


def test_precedence_first_root_wins(roster_dir, tmp_path) -> None:
    override = tmp_path / "override"
    (override / "developer").mkdir(parents=True)
    manifest = (roster_dir / "developer" / "adapter.yaml").read_text(
        encoding="utf-8"
    ).replace('version: "1.0.0"', 'version: "9.9.9"')
    (override / "developer" / "adapter.yaml").write_text(manifest, encoding="utf-8")
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([override, roster_dir])
    assert registry.adapters["developer"].root == override / "developer"


def test_invalid_adapter_listed_with_errors_never_loaded(roster_dir, tmp_path) -> None:
    bad_root = tmp_path / "badroot"
    (bad_root / "rogue").mkdir(parents=True)
    (bad_root / "rogue" / "adapter.yaml").write_text(
        "id: rogue\nversion: '1'\nrole: rogue\npermittedTools: [exfiltrate]\n",
        encoding="utf-8",
    )
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir, bad_root])
    rogue = registry.adapters["rogue"]
    assert rogue.valid is False
    assert any("allow-list" in e for e in rogue.errors)
    assert registry.states["rogue"] == "retired"  # never admitted


def test_digest_tamper_detected(roster_dir) -> None:
    agent_py = roster_dir / "developer" / "agent.py"
    agent_py.write_text(agent_py.read_text() + "\n# tampered\n", encoding="utf-8")
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    dev = registry.adapters["developer"]
    assert dev.valid is False
    assert any("digest mismatch" in e for e in dev.errors)


def test_missing_manifest_is_an_error_not_a_crash(roster_dir, tmp_path) -> None:
    ghost_root = tmp_path / "ghostroot"
    (ghost_root / "ghost").mkdir(parents=True)
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir, ghost_root])
    assert registry.adapters["ghost"].valid is False


# -- FR-M31-04: unplug / re-plug ----------------------------------------------------


def test_unplug_retires_and_checkpoint_escalates(roster_dir) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    registry.unplug(
        "developer", inflight={"story": "EDB-1", "progress": ["built api"]}
    )
    assert registry.states["developer"] == "retired"
    assert registry.checkpoints["developer"]["story"] == "EDB-1"
    assert registry.escalations[-1]["checkpointed"] is True
    # In-flight work is not lost.
    assert registry.checkpoints["developer"]["progress"] == ["built api"]


def test_every_adapter_survives_unplug_and_replug(roster_dir, tmp_path) -> None:
    """The M31 definition of done: every prebuilt adapter — the whole
    roster — survives unplug and re-plug."""
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    for spec in ROSTER:
        registry.unplug(spec["id"], inflight={"marker": spec["id"]})
        assert registry.states[spec["id"]] == "retired"
        restored = registry.replug(spec["id"], roster_dir / spec["id"])
        assert restored.valid is True
        assert registry.states[spec["id"]] == "probation"


# -- FR-M31-12: portability -----------------------------------------------------------


def test_learned_state_exports_and_imports(roster_dir, tmp_path) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    learned = roster_dir / "developer" / "learned"
    (learned / "rule.json").write_text(
        json.dumps({"id": "r1", "rule": "prefer small functions"}), encoding="utf-8"
    )
    archive = registry.export_state("developer", tmp_path / "developer-state")
    assert archive.exists()
    # A fresh registry on a fresh roster consumes the archive: learned/
    # is the complete record of acquired state.
    fresh_dir = tmp_path / "fresh"
    materialize_roster(fresh_dir)
    fresh = AdapterRegistry(tool_allowlist=ALLOWLIST)
    fresh.load([fresh_dir])
    fresh.import_state("developer", archive)
    imported = (fresh_dir / "developer" / "learned" / "rule.json")
    assert json.loads(imported.read_text(encoding="utf-8"))["id"] == "r1"


# -- FR-M31-15: dependency resolution ------------------------------------------------------


def test_dependency_graph_validates_at_discovery(roster_dir, tmp_path) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    assert registry.resolve_dependencies() == {}
    # Break the graph: a lone adapter declaring an absent dependency.
    lone = tmp_path / "lone"
    (lone / "lonely").mkdir(parents=True)
    (lone / "lonely" / "adapter.yaml").write_text(
        "id: lonely\nversion: '1'\nrole: helper\n"
        "permittedTools: [repo_read]\ndependencies: [developer]\n",
        encoding="utf-8",
    )
    broken = AdapterRegistry(tool_allowlist=ALLOWLIST)
    broken.load([lone])
    assert broken.resolve_dependencies() == {"lonely": ["developer"]}


# -- FR-M31-06: plain-Python bridge, sandboxed + permission-routed ----------------------------


def test_bridge_runs_in_sandbox_and_routes_tools(roster_dir, tmp_path) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    manifest = parse_manifest(
        (roster_dir / "developer" / "adapter.yaml").read_text(encoding="utf-8"),
        "developer",
    )
    surface = ToolSurface(
        SandboxConfig(working_dir=tmp_path / "work"), ledger=None
    )
    surface.permit("developer", {"build"})
    from dataclasses import replace

    bridge = PlainPythonBridge(
        replace(manifest, bridge="plain_python"),
        roster_dir / "developer" / "agent.py",
        surface,
    )
    args = tmp_path / "args.json"
    args.write_text(json.dumps({"task": "demo"}), encoding="utf-8")
    output = bridge.invoke(
        "developer", args_file=args, sandbox=SandboxConfig(working_dir=tmp_path)
    )
    assert json.loads(output)["adapter"] == "developer"

    # The bridge's only tool path is permission-checked (FR-M9-03):
    # an unpermitted tool raises instead of executing.
    with pytest.raises(ToolDeniedError):
        bridge.guarded_tool("developer", "test", ["echo", "hi"])
    result = bridge.guarded_tool("developer", "build", _echo_argv("ok"))
    assert result.ok is True


def test_stand_in_agent_bodies_run(roster_dir) -> None:
    """The shipped agent.py bodies really execute: subprocess, JSON in
    and out, no model calls."""
    args = roster_dir / "qa-engineer" / "tests" / "args.json"
    args.write_text(json.dumps({"check": "smoke"}), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(roster_dir / "qa-engineer" / "agent.py"), str(args)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["adapter"] == "qa-engineer"


def _echo_argv(text: str) -> list[str]:
    if sys.platform == "win32":
        return ["cmd", "/c", f"echo {text}"]
    return ["echo", text]
