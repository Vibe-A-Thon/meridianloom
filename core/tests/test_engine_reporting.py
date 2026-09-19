"""Per-class engine reporting (FR-M33-07): deterministic hit rate,
assisted and generative rates, latency and cost saved per action class —
derived from ledger dispatch records on demand, cached in-process and
invalidated on ledger append (FR-M17-05: no metrics database).

The model client is a fake; there are no real model calls (FR-M36-07).
"""

from __future__ import annotations

import pytest

from meridian_core.engine.assist import EngineModes, ModelCallBudget, ModelResponse
from meridian_core.engine.capabilities import CapabilityOutcome, CapabilityRegistry
from meridian_core.engine.catalogue import parse_catalogue
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.reporting import EngineReporter, LedgerRecorder
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger

CATALOGUE = """
version: 1
actionClasses:
  parse:
    mode: deterministic
    capability: structural_parse
    engine: tree-sitter
    schema: ParsedFile
    rationale: pure function of file bytes
  detect_ambiguity:
    mode: assisted
    deterministicFirst: rule_ambiguity
    gap: propose resolution
    schema: AmbiguityProposal
    engine: rules
    rationale: rules detect, model proposes
  implement:
    mode: generative
    validate: [syntax]
    schema: Patch
    engine: none
    rationale: novel code, validated before effect
"""

SCHEMAS = {
    "AmbiguityProposal": {
        "type": "object",
        "required": ["resolution"],
        "properties": {"resolution": {"type": "string"}},
    },
    "Patch": {
        "type": "object",
        "required": ["files"],
        "properties": {"files": {"type": "array", "items": {"type": "string"}}},
    },
}

GOOD_PROPOSAL = {"resolution": "rename to b"}
GOOD_PATCH = {"files": ["src/app.py"]}
BAD_PATCH = {"files": "not-a-list"}


class FakeCapability:
    def __init__(self, name, result=None):
        self._name = name
        self._result = result

    @property
    def name(self):
        return self._name

    def run(self, action):
        return CapabilityOutcome(handled=True, result=self._result)


class FakeModelClient:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def complete(self, request):
        output = self._outputs.pop(0)
        return ModelResponse(
            output=output, latency_ms=12, cost_usd=0.5, tokens_in=10, tokens_out=20
        )


@pytest.fixture()
def world(tmp_path):
    catalogue = parse_catalogue(CATALOGUE, "test")
    registry = CapabilityRegistry(catalogue)
    registry.register("parse", FakeCapability("structural_parse", result={"tree": "ok"}))
    registry.register(
        "detect_ambiguity",
        FakeCapability("rule_ambiguity", result={"candidates": ["a"]}),
    )
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    modes = EngineModes(
        dispatcher=Dispatcher(catalogue=catalogue, registry=registry),
        client=FakeModelClient([]),
        schemas=SCHEMAS,
        validators={"syntax": lambda output: [] if output.get("files") else ["empty"]},
        recorder=LedgerRecorder(ledger, policy_version="catalogue-v1"),
    )
    reporter = EngineReporter(
        ledger,
        cost_baselines={"parse": 1.0, "detect_ambiguity": 2.0, "implement": 3.0},
    )
    return modes, reporter, ledger


class TestPerClassReporting:
    def test_rates_latency_and_cost_per_class(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})  # deterministic hit
        modes.client = FakeModelClient([GOOD_PROPOSAL])
        modes.run("detect_ambiguity", {})  # assisted, completed on attempt 1
        modes.run("parse", {})  # second deterministic hit
        modes.client = FakeModelClient([BAD_PATCH, GOOD_PATCH, BAD_PATCH])
        modes.run("implement", {})  # generative, completed after one rework

        report = reporter.per_class()
        classes = report["classes"]

        assert classes["parse"]["actions"] == 2
        assert classes["parse"]["rates"]["deterministicHitRate"] == 1.0
        assert classes["parse"]["rates"]["assistedRate"] == 0.0
        assert classes["parse"]["modelCalls"] == 0
        assert classes["parse"]["latencyMs"]["total"] == 0
        assert classes["parse"]["costUsd"]["total"] == 0.0

        assert classes["detect_ambiguity"]["actions"] == 1
        assert classes["detect_ambiguity"]["rates"]["assistedRate"] == 1.0
        assert classes["detect_ambiguity"]["rates"]["deterministicHitRate"] == 0.0
        assert classes["detect_ambiguity"]["modelCalls"] == 1
        assert classes["detect_ambiguity"]["latencyMs"]["total"] >= 0
        assert classes["detect_ambiguity"]["costUsd"]["total"] == 0.5

        assert classes["implement"]["actions"] == 1
        assert classes["implement"]["rates"]["generativeRate"] == 1.0
        assert classes["implement"]["modelCalls"] == 2  # one failed, one reworked
        assert classes["implement"]["costUsd"]["total"] == 1.0

    def test_cost_saved_versus_generative_path(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})  # executed: the full baseline is saved
        modes.client = FakeModelClient([GOOD_PROPOSAL])
        modes.run("detect_ambiguity", {})  # baseline 2.0 minus actual 0.5

        classes = reporter.per_class()["classes"]
        assert classes["parse"]["costSavedUsd"] == 1.0
        assert classes["detect_ambiguity"]["costSavedUsd"] == 1.5

    def test_cost_saved_unknown_without_policy_baseline(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})
        honest = EngineReporter(ledger)  # no baselines at all
        classes = honest.per_class()["classes"]
        assert classes["parse"]["costSavedUsd"] is None
        assert "unknown" in classes["parse"]["notes"]["costSaved"]

    def test_rework_and_ceiling_breach_are_reported(self, world):
        modes, reporter, ledger = world
        modes.client = FakeModelClient([BAD_PATCH, BAD_PATCH, BAD_PATCH])
        modes.run("implement", {})  # rework exhausted
        modes.budget = ModelCallBudget(per_class={"implement": 0})
        modes.client = FakeModelClient([GOOD_PATCH])
        modes.run("implement", {})  # denied before any call

        counts = reporter.per_class()["classes"]["implement"]["counts"]
        assert counts["rework_refused"] == 1
        assert counts["ceiling_breach"] == 1
        assert reporter.per_class()["classes"]["implement"]["modelCalls"] == 3

    def test_scopes_by_story_and_phase(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {}, story_id="s1", phase="build")
        modes.run("parse", {}, story_id="s2", phase="review")

        scoped = reporter.per_class(story_id="s1")["classes"]
        assert scoped["parse"]["actions"] == 1
        scoped = reporter.per_class(phase="review")["classes"]
        assert scoped["parse"]["actions"] == 1
        assert reporter.per_class(story_id="nope")["classes"] == {}


class TestCacheInvalidation:
    def test_results_are_cached_and_tip_keyed(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})
        first = reporter.per_class()
        assert first["classes"]["parse"]["actions"] == 1

        # Same tip: served from the cache (identical object).
        assert reporter.per_class() is first

        # A ledger append moves the tip: the next compute sees the new
        # record even though nobody called invalidate() — the cache key
        # carries the ledger tip sequence (FR-M17-05 convention).
        modes.run("parse", {})
        second = reporter.per_class()
        assert second is not first
        assert second["ledgerTip"] == ledger.last_sequence
        assert second["classes"]["parse"]["actions"] == 2

    def test_invalidate_clears_the_cache(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})
        reporter.per_class()
        reporter.invalidate()
        modes.run("parse", {})
        fresh = reporter.per_class()
        assert fresh["classes"]["parse"]["actions"] == 2

    def test_records_are_ledger_rows(self, world):
        modes, reporter, ledger = world
        modes.run("parse", {})
        rows = ledger.query(action_type="engine_dispatch", limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["latency_ms"] == 0
        assert row["cost_usd"] == 0.0
        assert row["actor_id"] == "meridian-engine"
        import json

        summary = json.loads(row["tool_calls"])[0]
        assert summary["action_class"] == "parse"
        assert summary["status"] == "executed"
        assert summary["mode"] == "executed"
