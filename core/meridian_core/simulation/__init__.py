"""M32 Simulation Core — FR-M32-01…07, AC-16, AC-28's backend half.

A zero-model-call backend implementing the complete message-bus
contract: it serves the SAME request methods the production sidecar
registers (both sides read ``shared/schema/methods.json`` — FR-M32-09's
divergence check is a test comparing this contract against the
sidecar's registry). Scripted story scenarios cover every screen's data
needs (FR-M32-04); responses are canned data, and any ledger writes go
through the real Ledger with ``replay_of`` tagging so simulated work is
never confused with live work (FR-M32-02). Time control — pause, step,
play at N×, jump to sequence — drives the GUI's time-travel and motion
against controllable state (FR-M32-06).

ZERO MODEL CALLS (FR-M32-05): this module imports no model client, and
a test fails the build if one ever appears under ``simulation/``.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from meridian_core.ledger import Ledger
from meridian_core.replay import Cassette, replay_cassette

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "shared" / "schema" / "methods.json"
)

#: FR-M32-04: scripted story scenarios, one per screen's data needs.
SCENARIO_NAMES = (
    "clean-story",
    "rework-and-unravel",
    "loop-bound-hit",
    "blocked-gate",
    "clarifying-question",
    "mid-loop-steer",
    "multi-story-portfolio",
    "tamper-detected-ledger",
    "budget-breach",
    "adapter-plug-unplug",
)


def load_contract(schema_path: Path = SCHEMA_PATH) -> frozenset[str]:
    """The request-method contract both backends implement (FR-M32-01)."""
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    methods = raw.get("x-methods") or raw.get("methods") or {}
    return frozenset(methods.keys())


@dataclass(frozen=True)
class ScenarioStep:
    """One scripted step: a bus request, its canned response, and the
    ledger entries the step writes (replay_of-tagged)."""

    sequence: int
    method: str
    params: Mapping[str, Any]
    response: Mapping[str, Any]
    ledger_payloads: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[ScenarioStep, ...]

    def sequences(self) -> tuple[int, ...]:
        return tuple(s.sequence for s in self.steps)


class SimulationClock:
    """FR-M32-06 time control: pause, step, play at N×, jump to sequence.
    The clock is a pure gate over the scenario cursor — deterministic,
    inspectable, and independent of wall time."""

    def __init__(self, sequences: tuple[int, ...]) -> None:
        self._sequences = sequences
        self._cursor = 0
        self._paused = True
        self._rate = 1

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def position(self) -> int:
        return self._sequences[self._cursor] if self._sequences else 0

    def pause(self) -> int:
        self._paused = True
        return self.position

    def step(self) -> int:
        """Advance exactly one sequence (works from paused or playing)."""
        self._cursor = min(self._cursor + 1, len(self._sequences) - 1)
        return self.position

    def play(self, rate: float = 1.0) -> int:
        if rate <= 0:
            raise ValueError("play rate must be positive")
        self._rate = rate
        self._paused = False
        return self.position

    def jump(self, sequence: int) -> int:
        if sequence not in self._sequences:
            raise ValueError(
                f"sequence {sequence} is not in the scenario"
                f" {self._sequences}"
            )
        self._cursor = self._sequences.index(sequence)
        return self.position

    def advance(self) -> bool:
        """One tick of playback: moves when playing; N× consumes N ticks
        of wall time per step, which the driver honours by calling tick
        at wall cadence. Returns False when the scenario is exhausted."""
        if self._paused or self._cursor >= len(self._sequences) - 1:
            return False
        self._cursor += 1
        return True


class SimulationCore:
    """The scripted backend. Serves contract methods with canned
    scenario data; ledger writes are real entries, replay_of-tagged."""

    def __init__(
        self,
        *,
        contract: frozenset[str] | None = None,
        ledger: Ledger | None = None,
        scenario: Scenario | None = None,
    ) -> None:
        self._contract = contract or load_contract()
        self._ledger = ledger
        self._scenario = scenario
        self.clock = (
            SimulationClock(scenario.sequences()) if scenario else SimulationClock(())
        )
        self._served: list[str] = []

    @property
    def backend(self) -> str:
        return "simulation-core"

    def serve(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """One bus request. Unknown methods get the contracted error
        shape — the same shape the production sidecar returns, so a
        webview handles both identically (FR-M32-01)."""
        if method not in self._contract:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"method not found: {method}",
                },
            }
        step = self._find_step(method, params)
        if step is not None:
            self._write_ledger(step)
            self._served.append(method)
            return dict(step.response)
        self._served.append(method)
        return {"ok": True, "backend": self.backend, "method": method}

    def _find_step(self, method: str, params: Mapping[str, Any]) -> ScenarioStep | None:
        if self._scenario is None:
            return None
        for step in self._scenario.steps:
            if step.method != method:
                continue
            if all(params.get(k) == v for k, v in step.params.items()):
                return step
        return None

    def _write_ledger(self, step: ScenarioStep) -> None:
        """FR-M32-02: real ledger entries through the real Ledger,
        tagged so simulated work is never confused with live work."""
        if self._ledger is None:
            return
        scenario_id = self._scenario.name if self._scenario else "scenario"
        for payload in step.ledger_payloads:
            entry = {
                "story_id": payload.get("story_id", scenario_id),
                "phase": payload.get("phase", "build"),
                "loop_id": payload.get("loop_id", "simulation"),
                "loop_iteration": int(payload.get("loop_iteration", 1)),
                "actor_id": payload.get("actor_id", "simulation-core"),
                "actor_version": "m32/v1",
                "actor_kind": "meta",
                "policy_version": "simulation/v1",
                "action_type": payload.get("action_type", "note"),
                "replay_of": f"scenario:{scenario_id}:{step.sequence}",
            }
            if payload.get("input") is not None:
                entry["input"] = payload["input"]
            self._ledger.append(entry)

    # -- FR-M32-07: golden-corpus runner --------------------------------------

    def run_golden(self, folder: Path, destination: Path) -> Mapping[str, Any]:
        """Replay one golden corpus entry (D10 layout: story + cassette +
        expected root) and report. AC-16: no model calls — guaranteed
        structurally (this whole module imports none)."""
        cassette = Cassette.load(folder / "cassette.json")
        expected_root = (folder / "expected_root.txt").read_text(encoding="utf-8").strip()
        ledger = replay_cassette(cassette, destination)
        try:
            root = ledger._frontier.root().hex()
            ok = root == expected_root
            return {
                "storyId": cassette.story_id,
                "ok": ok,
                "ledgerRoot": root,
                "expectedRoot": expected_root,
                "entries": len(cassette.rows),
            }
        finally:
            ledger.close()


def assert_no_model_client_imports(package_dir: Path) -> None:
    """FR-M32-05: fail if any module under simulation/ (or replay/)
    imports a model client. The Simulation Core makes zero model calls;
    this is the structural proof, run in the test suite."""
    banned = ("openai", "anthropic", "litellm", "langchain_openai", "google.generativeai")
    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == b or name.startswith(b + ".") for b in banned):
                    raise AssertionError(
                        f"FR-M32-05: {path} imports model client {name!r}"
                    )
