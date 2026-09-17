"""FR-M8-15/16/17 (F3 step 2): the Model Router behind the engine.

- refusal of model calls for action classes with a deterministic path,
  ledger-recorded (FR-M8-15);
- why_llm from the closed vocabulary on every permitted call, recorded
  (FR-M8-16);
- LLM dependency ratio per agent/phase/story/class with a policy ceiling
  that escalates when breached (FR-M8-17).
"""

from __future__ import annotations

import json

import pytest

from meridian_core.engine.catalogue import parse_catalogue
from meridian_core.engine.capabilities import CapabilityRegistry
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.structural import StructuralParseCapability
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.router import (
    WHY_LLM_VOCABULARY,
    Router,
    RouterError,
)

CATALOGUE = """
version: 1
actionClasses:
  parse:
    mode: deterministic
    capability: structural_parse
    engine: tree-sitter
    schema: ParsedFile
    rationale: structural parse is a pure function of bytes
  suggest_change:
    mode: assisted
    deterministicFirst: structural_parse
    engine: deterministic-first
    gap: candidate_text
    schema: ChangeProposal
    validate: [schema]
    rationale: engine prepares; model fills a bounded gap
  author_story:
    mode: generative
    engine: none
    schema: StoryDraft
    validate: [schema]
    rationale: authoring is generative by policy
"""


@pytest.fixture()
def dispatcher() -> Dispatcher:
    catalogue = parse_catalogue(CATALOGUE, "test")
    assert not catalogue.errors, catalogue.errors
    registry = CapabilityRegistry(catalogue)
    registry.register("parse", StructuralParseCapability())
    return Dispatcher(catalogue=catalogue, registry=registry)


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


def detail(led: Ledger, row: dict) -> dict:
    return json.loads(
        led.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
    )


# -- FR-M8-15: refusal ----------------------------------------------------------


def test_deterministic_class_model_call_refused_and_recorded(
    dispatcher, ledger
) -> None:
    router = Router(dispatcher, ledger)
    decision = router.request_model_call(
        action_class="parse",
        agent_id="agent-1",
        story_id="S1",
        phase="build",
    )
    assert decision.permitted is False
    assert "FR-M8-15" in decision.refusal_reason
    assert decision.why_llm is None
    # The refusal names the engine outcome it is protecting.
    assert "engine outcome kind=" in decision.refusal_reason
    # The refusal is ledger evidence and the chain verifies.
    rows = ledger.query(action_type="rejection", story_id="S1")
    assert len(rows) == 1
    assert rows[0]["decision"] == "rejected"
    assert detail(ledger, rows[0])["refusal"] == "model_call"
    assert ledger.verify().ok is True


def test_unknown_class_refused(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    decision = router.request_model_call(
        action_class="made_up", agent_id="a", story_id="S1", phase="build"
    )
    assert decision.permitted is False
    assert decision.recorded_sequence is not None


# -- FR-M8-16: why_llm on every permitted call ------------------------------------


def test_assisted_class_permitted_with_engine_why(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    decision = router.request_model_call(
        action_class="suggest_change",
        agent_id="agent-1",
        story_id="S1",
        phase="build",
    )
    assert decision.permitted is True
    assert decision.why_llm == "assisted_gap"
    rows = ledger.query(action_type="model_call", story_id="S1")
    assert detail(ledger, rows[0])["whyLlm"] == "assisted_gap"
    assert ledger.verify().ok is True


def test_generative_class_permitted_by_policy(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    decision = router.request_model_call(
        action_class="author_story",
        agent_id="agent-1",
        story_id="S1",
        phase="intake",
    )
    assert decision.permitted is True
    assert decision.why_llm == "generative_by_policy"


def test_human_override_is_router_assigned_and_recorded(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    decision = router.request_model_call(
        action_class="parse",  # deterministic class
        agent_id="agent-1",
        story_id="S1",
        phase="build",
        human_override=True,
    )
    assert decision.permitted is True
    assert decision.why_llm == "human_override"
    rows = ledger.query(action_type="model_call", story_id="S1")
    assert detail(ledger, rows[0])["humanOverride"] is True


def test_why_llm_vocabulary_is_closed(dispatcher, ledger) -> None:
    assert WHY_LLM_VOCABULARY == (
        "no_deterministic_path",
        "assisted_gap",
        "generative_by_policy",
        "human_override",
    )
    # The engine never assigns human_override on its own outcomes.
    outcome = dispatcher.dispatch("suggest_change", {})
    if outcome.router_eligible:
        assert outcome.why_llm != "human_override"


# -- FR-M8-17: dependency ratio ------------------------------------------------------


def _mix(router: Router) -> None:
    """2 model calls + 6 deterministic executions on story S1."""
    for _ in range(2):
        router.request_model_call(
            action_class="suggest_change",
            agent_id="agent-1",
            story_id="S1",
            phase="build",
        )
    for _ in range(6):
        router.record_engine_execution(
            action_class="parse",
            agent_id="agent-1",
            story_id="S1",
            phase="build",
        )


def test_ratio_per_story(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    _mix(router)
    ratio = router.dependency_ratio(story_id="S1")
    assert ratio.model_calls == 2
    assert ratio.engine_executions == 6
    assert ratio.ratio == pytest.approx(0.25)


def test_ratio_empty_scope_is_none_not_fabricated(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    ratio = router.dependency_ratio(story_id="NOPE")
    assert ratio.ratio is None
    assert ratio.model_calls == 0 and ratio.engine_executions == 0


def test_ratio_per_agent_and_phase_scope(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger)
    _mix(router)
    router.record_engine_execution(
        action_class="parse", agent_id="agent-2", story_id="S2", phase="verify"
    )
    scoped = router.dependency_ratio(agent_id="agent-2", phase="verify")
    assert scoped.ratio == 0.0  # one execution, zero calls
    by_class = router.dependency_ratio(action_class="parse")
    assert by_class.engine_executions == 7  # 6 + 1
    assert by_class.model_calls == 0


def test_ceiling_breach_escalates_once_and_records(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger, ceilings={"story:S1": 0.20})
    _mix(router)  # ratio 0.25 > 0.20
    ratio = router.dependency_ratio(story_id="S1")
    assert ratio.ceiling == 0.20
    assert ratio.breached is True
    assert ratio.escalation_sequence is not None
    rows = ledger.query(action_type="policy_update", story_id="S1")
    assert detail(ledger, rows[0])["event"] == "llm_ratio_ceiling_breached"
    assert ledger.verify().ok is True


def test_ceiling_unbreached_records_nothing(dispatcher, ledger) -> None:
    router = Router(dispatcher, ledger, ceilings={"default": 0.35})
    _mix(router)  # 0.25 <= 0.35
    ratio = router.dependency_ratio(story_id="S1")
    assert ratio.breached is False
    assert ratio.escalation_sequence is None
    assert ledger.query(action_type="policy_update") == []


def test_ac26_reference_shape_ratio_at_most_035(dispatcher, ledger) -> None:
    """AC-26's shape: a healthy run keeps the ratio under a 0.35 ceiling —
    1 model call per 5+ deterministic executions."""
    router = Router(dispatcher, ledger, ceilings={"default": 0.35})
    router.request_model_call(
        action_class="suggest_change",
        agent_id="agent-1",
        story_id="REF",
        phase="build",
    )
    for _ in range(5):
        router.record_engine_execution(
            action_class="parse", agent_id="agent-1", story_id="REF", phase="build"
        )
    ratio = router.dependency_ratio(story_id="REF", ceiling=0.35)
    assert ratio.ratio == pytest.approx(1 / 6)
    assert ratio.breached is False


def test_router_without_ledger_refuses_ratio(dispatcher) -> None:
    router = Router(dispatcher)
    with pytest.raises(RouterError):
        router.dependency_ratio(story_id="S1")


def test_every_decision_entry_carries_bound_fields(dispatcher, ledger) -> None:
    """FR-M4-02 shape: every recorded entry declares the eight bound fields."""
    router = Router(dispatcher, ledger)
    router.request_model_call(
        action_class="suggest_change", agent_id="a", story_id="S1", phase="build"
    )
    router.request_model_call(
        action_class="parse", agent_id="a", story_id="S1", phase="build"
    )
    for action_type in ("model_call", "rejection"):
        for row in ledger.query(action_type=action_type):
            for field in (
                "story_id", "phase", "loop_id", "loop_iteration",
                "actor_id", "actor_version", "actor_kind",
                "policy_version", "action_type",
            ):
                assert row[field] is not None and row[field] != "", (
                    action_type, field, row
                )
    assert ledger.verify().ok is True
