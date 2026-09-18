"""FR-M26-04 (audit TASK-310): the three cost levers — prompt caching,
context compaction, tool-result summarisation — with savings recorded to
the ledger and reconcilable per story.
"""

from __future__ import annotations

import json

import pytest

from meridian_core.levers import (
    CostLeverSet,
    LeverConfig,
    LeverReport,
    LeverSavings,
    config_from_pack,
)
from meridian_core.router import Router
from tests.test_router_m8 import CATALOGUE, detail, dispatcher, ledger  # noqa: F401
from meridian_core.engine.capabilities import CapabilityRegistry
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.catalogue import parse_catalogue
from meridian_core.engine.structural import StructuralParseCapability
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger


def make_router(tmp_path, levers):
    cat = parse_catalogue(CATALOGUE, "test")
    registry = CapabilityRegistry(cat)
    registry.register("parse", StructuralParseCapability())
    return Router(Dispatcher(catalogue=cat, registry=registry),
                  Ledger(tmp_path / "l", EphemeralSigningKeyProvider()),
                  levers=levers)


LONG_TOOL_RESULT = "tool result: " + "x" * 20_000
PROMPT_WITH_RESULT = "system: rules\n" + LONG_TOOL_RESULT + "\nquestion: proceed?"


def test_cache_hit_records_savings_on_second_identical_call(tmp_path) -> None:
    router = make_router(tmp_path, CostLeverSet())
    for _ in range(2):
        decision = router.request_model_call(
            action_class="suggest_change", agent_id="a", story_id="S1",
            phase="build", payload={"prompt": "prefix " * 2000 + "suffix"},
        )
        assert decision.permitted is True
    rows = router._ledger.query(action_type="model_call", story_id="S1")
    first = json.loads(
        router._ledger.read_blob(rows[0]["input_ref"], rows[0]["blob_key_id"]).decode()
    )
    second = json.loads(
        router._ledger.read_blob(rows[1]["input_ref"], rows[1]["blob_key_id"]).decode()
    )
    assert first["levers"]["cachedTokens"] == 0
    assert second["levers"]["cachedTokens"] > 0
    report = router._lever_report.for_story("S1")
    assert report["cachedTokens"] == second["levers"]["cachedTokens"]
    router._ledger.close()


def test_compaction_drops_oldest_tool_results_with_marker(tmp_path) -> None:
    levers = CostLeverSet(LeverConfig(context_budget_bytes=2_000))
    router = make_router(tmp_path, levers)
    router.request_model_call(
        action_class="suggest_change", agent_id="a", story_id="S2",
        phase="build",
        payload={"prompt": "tool result: " + "a" * 5_000 + "\n"
                 + "tool result: " + "b" * 5_000 + "\n" + "q"},
    )
    row = router._ledger.query(action_type="model_call", story_id="S2")[0]
    recorded = json.loads(
        router._ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode()
    )
    assert recorded["levers"]["compactedBytes"] > 0
    router._ledger.close()


def test_summarisation_caps_oversized_tool_result(tmp_path) -> None:
    router = make_router(tmp_path, CostLeverSet())
    router.request_model_call(
        action_class="suggest_change", agent_id="a", story_id="S3",
        phase="build", payload={"prompt": PROMPT_WITH_RESULT},
    )
    row = router._ledger.query(action_type="model_call", story_id="S3")[0]
    recorded = json.loads(
        router._ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode()
    )
    assert recorded["levers"]["summarisedBytes"] > 0
    router._ledger.close()


def test_disabled_levers_are_pass_through(tmp_path) -> None:
    router = make_router(
        tmp_path,
        CostLeverSet(LeverConfig(
            prompt_caching=False, context_compaction=False,
            tool_result_summarisation=False,
        )),
    )
    router.request_model_call(
        action_class="suggest_change", agent_id="a", story_id="S4",
        phase="build", payload={"prompt": PROMPT_WITH_RESULT},
    )
    router.request_model_call(
        action_class="suggest_change", agent_id="a", story_id="S4",
        phase="build", payload={"prompt": PROMPT_WITH_RESULT},
    )
    rows = router._ledger.query(action_type="model_call", story_id="S4")
    for row in rows:
        recorded = json.loads(
            router._ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode()
        )
        # Disabled levers are a pass-through: savings are all zero, and
        # the shaped prompt is untouched (no cache, compaction, marker).
        assert recorded["levers"] == {
            "cachedTokens": 0, "compactedBytes": 0, "summarisedBytes": 0,
        }
    router._ledger.close()


def test_config_from_pack_defaults_and_overrides() -> None:
    default = config_from_pack(None)
    assert default.prompt_caching and default.context_compaction
    overridden = config_from_pack({
        "promptCaching": False,
        "cacheTtlSeconds": 60,
        "resultCapBytes": 1000,
    })
    assert overridden.prompt_caching is False
    assert overridden.cache_ttl_s == 60
    assert overridden.context_compaction is True


def test_lever_report_aggregates_per_story() -> None:
    report = LeverReport()
    report.record("S1", LeverSavings(cached_tokens=10))
    report.record("S1", LeverSavings(cached_tokens=5, compacted_bytes=100))
    report.record("S2", LeverSavings(summarised_bytes=50))
    assert report.for_story("S1") == {
        "cachedTokens": 15, "compactedBytes": 100, "summarisedBytes": 0,
    }
    assert report.aggregate() == {
        "cachedTokens": 15, "compactedBytes": 100, "summarisedBytes": 50,
    }
