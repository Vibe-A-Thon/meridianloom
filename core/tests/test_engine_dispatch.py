"""Deterministic-first dispatch (FR-M33-03) and the FR-M8-15 boundary.

Every agent action is dispatched to the engine before the router. The
outcome kinds:

* executed   — deterministic capability did the work; NOT router-eligible;
               a model call for the class is structurally impossible.
* assisted   — engine ran its deterministic-first phase, declared the
               bounded gap; router-eligible with why_llm=assisted_gap.
* generative — engine cannot help; router-eligible with
               why_llm=generative_by_policy (or no_deterministic_path when
               a named escalation condition fired).
* refused    — unknown class, fail-closed catalogue, or a deterministic
               class with no named escalation condition; NOT router-eligible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.engine.capabilities import CapabilityOutcome, CapabilityRegistry
from meridian_core.engine.catalogue import load_catalogue, parse_catalogue, repo_default_paths
from meridian_core.engine.dispatch import (
    WHY_ASSISTED_GAP,
    WHY_GENERATIVE_BY_POLICY,
    WHY_NO_DETERMINISTIC_PATH,
    Dispatcher,
)
from meridian_core.engine.rules import RuleSet, parse_rule_document

REPO_ROOT = Path(__file__).resolve().parents[2]

CATALOGUE = """
version: 1
actionClasses:
  parse:
    mode: deterministic
    capability: structural_parse
    engine: tree-sitter
    schema: ParsedFile
    rationale: pure function of file bytes
  decompose_packets:
    mode: deterministic
    capability: graph_decompose
    engine: graph
    escalateIf: cyclic_or_ambiguous
    schema: WorkPackets
    rationale: topological partition; only cycles escalate
  detect_ambiguity:
    mode: assisted
    deterministicFirst: rule_ambiguity
    gap: propose resolution
    schema: AmbiguityProposal
    engine: rules
    rationale: rules detect, model proposes
  implement:
    mode: generative
    validate: [syntax, types, tests, conventions, scope]
    schema: Patch
    engine: none
    rationale: novel code, validated before effect
"""


class FakeCapability:
    """A stand-in FR-M33-02 capability."""

    def __init__(self, name, handled=True, result=None, reason=""):
        self._name = name
        self._handled = handled
        self._result = result
        self._reason = reason

    @property
    def name(self):
        return self._name

    def run(self, action):
        return CapabilityOutcome(
            handled=self._handled, result=self._result, reason=self._reason
        )


@pytest.fixture()
def catalogue():
    return parse_catalogue(CATALOGUE, "test")


@pytest.fixture()
def dispatcher(catalogue):
    registry = CapabilityRegistry(catalogue)
    registry.register("parse", FakeCapability("structural_parse", result={"tree": "ok"}))
    registry.register(
        "decompose_packets", FakeCapability("graph_decompose", result={"packets": []})
    )
    registry.register(
        "detect_ambiguity",
        FakeCapability("rule_ambiguity", result={"candidates": ["a", "b"]}),
    )
    return Dispatcher(catalogue=catalogue, registry=registry)


class TestDeterministic:
    def test_capability_executes_and_router_is_unreachable(self, dispatcher):
        outcome = dispatcher.dispatch("parse", {"path": "src/app.py"})
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert outcome.why_llm is None
        assert outcome.result == {"tree": "ok"}

    def test_no_deterministic_path_without_escalate_is_refused(self, catalogue):
        """FR-M8-15: a model call for a class with a deterministic path is
        structurally impossible — the dispatch layer refuses."""
        registry = CapabilityRegistry(catalogue)
        registry.register(
            "parse", FakeCapability("structural_parse", handled=False, reason="unsupported grammar")
        )
        dispatcher = Dispatcher(catalogue=catalogue, registry=registry)
        outcome = dispatcher.dispatch("parse", {})
        assert outcome.kind == "refused"
        assert outcome.router_eligible is False
        assert outcome.why_llm is None
        assert "FR-M8-15" in outcome.reason

    def test_unregistered_capability_without_escalate_is_refused(self, dispatcher):
        """Deterministic class whose capability is not built yet: still not
        router-eligible unless policy named an escalation condition."""
        outcome = dispatcher.dispatch("parse", {})
        assert outcome.kind in ("executed", "refused")  # registered in fixture
        registry = CapabilityRegistry(dispatcher.catalogue)
        bare = Dispatcher(catalogue=dispatcher.catalogue, registry=registry)
        result = bare.dispatch("parse", {})
        assert result.kind == "refused"
        assert result.router_eligible is False

    def test_named_escalation_condition_reaches_router(self, catalogue):
        registry = CapabilityRegistry(catalogue)
        registry.register(
            "decompose_packets",
            FakeCapability("graph_decompose", handled=False, reason="dependency cycle detected"),
        )
        dispatcher = Dispatcher(catalogue=catalogue, registry=registry)
        outcome = dispatcher.dispatch("decompose_packets", {})
        assert outcome.kind == "generative"
        assert outcome.router_eligible is True
        assert outcome.why_llm == WHY_NO_DETERMINISTIC_PATH
        assert outcome.escalate_if == "cyclic_or_ambiguous"

    def test_handled_escalating_class_executes(self, dispatcher):
        outcome = dispatcher.dispatch("decompose_packets", {})
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False


class TestAssisted:
    def test_engine_does_work_and_declares_bounded_gap(self, dispatcher):
        """FR-M33-03/-04 seam: the decision and its shape exist now; full
        assisted mode lands in slice 3."""
        outcome = dispatcher.dispatch("detect_ambiguity", {"story": "M33"})
        assert outcome.kind == "assisted"
        assert outcome.router_eligible is True
        assert outcome.why_llm == WHY_ASSISTED_GAP
        assert outcome.gap == "propose resolution"
        assert outcome.schema == "AmbiguityProposal"
        assert outcome.result == {"candidates": ["a", "b"]}

    def test_assisted_without_registered_first_still_declares_gap(self, catalogue):
        dispatcher = Dispatcher(
            catalogue=catalogue, registry=CapabilityRegistry(catalogue)
        )
        outcome = dispatcher.dispatch("detect_ambiguity", {})
        assert outcome.kind == "assisted"
        assert outcome.router_eligible is True
        assert outcome.gap == "propose resolution"
        assert outcome.result is None
        assert "not registered" in outcome.reason


class TestGenerative:
    def test_generative_class_is_router_eligible_by_policy(self, dispatcher):
        outcome = dispatcher.dispatch("implement", {"packet": "p1"})
        assert outcome.kind == "generative"
        assert outcome.router_eligible is True
        assert outcome.why_llm == WHY_GENERATIVE_BY_POLICY
        assert outcome.validate == ("syntax", "types", "tests", "conventions", "scope")
        assert outcome.schema == "Patch"


class TestRefusal:
    def test_unknown_class_refused(self, dispatcher):
        outcome = dispatcher.dispatch("conjure", {})
        assert outcome.kind == "refused"
        assert outcome.router_eligible is False
        assert "unknown action class" in outcome.reason

    def test_fail_closed_catalogue_refuses_everything(self):
        broken = parse_catalogue("{unclosed", "test")
        dispatcher = Dispatcher(catalogue=broken, registry=CapabilityRegistry(broken))
        outcome = dispatcher.dispatch("implement", {})
        assert outcome.kind == "refused"
        assert outcome.router_eligible is False
        assert "fail-closed" in outcome.reason


class TestRegistrySeam:
    def test_registration_against_unknown_class_refused_and_recorded(self, catalogue):
        registry = CapabilityRegistry(catalogue)
        assert registry.register("nope", FakeCapability("x")) is False
        assert any("unknown action class" in r for r in registry.refusals)

    def test_registration_against_generative_class_refused(self, catalogue):
        registry = CapabilityRegistry(catalogue)
        assert registry.register("implement", FakeCapability("structural_parse")) is False
        assert any("does not permit" in r for r in registry.refusals)

    def test_resolve_consults_catalogue(self, catalogue):
        registry = CapabilityRegistry(catalogue)
        capability = FakeCapability("structural_parse")
        registry.register("parse", capability)
        assert registry.resolve("parse") is capability
        assert registry.resolve("unknown") is None

    def test_from_catalogue_binds_all(self, catalogue):
        capability = FakeCapability("structural_parse")
        registry = CapabilityRegistry.from_catalogue(
            catalogue, [("parse", capability)]
        )
        assert registry.resolve("parse") is capability
        assert registry.refusals == []


class TestLearnedRulesAheadOfRouter:
    """FR-M33-06: distilled rules are consulted ahead of any decision that
    can reach the router, and the matched ids ride on the outcome."""

    RULES = """
version: 1
rules:
  - id: name-tests-by-convention
    description: learned naming convention for tests
    action_classes: [implement, name_tests, parse]
    when:
      - {field: payload.path, op: matches, value: '.*_test\\.py$'}
    then:
      convention: test names read <method>_when_<condition>
"""

    def test_generative_outcome_carries_matched_rules(self, dispatcher):
        rule_set = RuleSet(rules=parse_rule_document(self.RULES, "test").rules)
        dispatcher.rules = rule_set
        hit = dispatcher.dispatch("implement", {"payload": {"path": "foo_test.py"}})
        assert hit.router_eligible is True
        assert hit.rules_matched == ("name-tests-by-convention",)
        miss = dispatcher.dispatch("implement", {"payload": {"path": "foo.py"}})
        assert miss.rules_matched == ()

    def test_refused_outcome_also_records_rules_consulted(self, catalogue):
        rule_set = RuleSet(rules=parse_rule_document(self.RULES, "test").rules)
        registry = CapabilityRegistry(catalogue)
        dispatcher = Dispatcher(catalogue=catalogue, registry=registry, rules=rule_set)
        outcome = dispatcher.dispatch("parse", {"payload": {"path": "foo_test.py"}})
        assert outcome.kind == "refused"  # no capability registered
        assert outcome.rules_matched == ("name-tests-by-convention",)


class TestWithRepositoryCatalogue:
    """End-to-end against the real D16 artefact (FR-M33-01 + FR-M33-03)."""

    def test_repo_catalogue_dispatches_without_capabilities_registered(self):
        catalogue = load_catalogue(repo_default_paths())
        dispatcher = Dispatcher(catalogue=catalogue, registry=CapabilityRegistry(catalogue))
        # Deterministic classes refuse rather than fall through to a model.
        for class_id in ("parse", "resolve_symbol", "run_tests", "scaffold"):
            outcome = dispatcher.dispatch(class_id, {})
            assert outcome.kind == "refused", class_id
            assert outcome.router_eligible is False, class_id
        # Generative classes are router-eligible with why_llm (FR-M8-16).
        outcome = dispatcher.dispatch("implement", {})
        assert outcome.kind == "generative"
        assert outcome.why_llm == WHY_GENERATIVE_BY_POLICY
        # Assisted classes declare their gap.
        outcome = dispatcher.dispatch("draft_adr", {})
        assert outcome.kind == "assisted"
        assert outcome.gap == "prose sections"
