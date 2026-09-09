"""Assisted and generative modes (FR-M33-04/FR-M33-05), replay-identical
deterministic paths (FR-M33-08, NFR-27) and model-call ceilings
(FR-M33-09).

The model is always an injected ``ModelClient`` — every client in this
file is a fake; there are no real model calls anywhere (FR-M36-07).
"""

from __future__ import annotations

import json

import pytest

from meridian_core.engine.assist import (
    EngineModes,
    ModelCallBudget,
    ModelResponse,
)
from meridian_core.engine.capabilities import CapabilityOutcome, CapabilityRegistry
from meridian_core.engine.catalogue import load_catalogue, parse_catalogue, repo_default_paths
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.rules import RuleSet, parse_rule_document

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
    validate: [syntax, conventions]
    schema: Patch
    engine: none
    rationale: novel code, validated before effect
ceilings:
  llm_dependency_ratio_max: 0.35
  model_calls:
    global: 3
    per_class: {implement: 2}
"""

SCHEMAS = {
    "AmbiguityProposal": {
        "type": "object",
        "required": ["candidate", "resolution"],
        "additionalProperties": False,
        "properties": {
            "candidate": {"type": "string"},
            "resolution": {"type": "string"},
        },
    },
    "Patch": {
        "type": "object",
        "required": ["files"],
        "additionalProperties": False,
        "properties": {
            "files": {"type": "array", "items": {"type": "string"}},
        },
    },
}

GOOD_PROPOSAL = {"candidate": "a", "resolution": "rename to b"}
GOOD_PATCH = {"files": ["src/app.py"]}


class FakeCapability:
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


class FakeModelClient:
    """Records every GapRequest; plays back queued outputs as responses."""

    def __init__(self, outputs=()):
        self.requests = []
        self._outputs = list(outputs)

    def complete(self, request):
        self.requests.append(request)
        if self._outputs:
            output = self._outputs.pop(0)
        else:
            output = GOOD_PROPOSAL
        if isinstance(output, Exception):
            raise output
        return ModelResponse(
            output=output,
            latency_ms=12,
            cost_usd=0.5,
            tokens_in=10,
            tokens_out=20,
            model_id="fake-model",
        )


@pytest.fixture()
def catalogue():
    return parse_catalogue(CATALOGUE, "test")


@pytest.fixture()
def modes(catalogue):
    registry = CapabilityRegistry(catalogue)
    registry.register("parse", FakeCapability("structural_parse", result={"tree": "ok"}))
    registry.register(
        "detect_ambiguity",
        FakeCapability("rule_ambiguity", result={"candidates": ["a", "b"]}),
    )
    dispatcher = Dispatcher(catalogue=catalogue, registry=registry)
    return EngineModes(
        dispatcher=dispatcher,
        client=FakeModelClient(),
        schemas=SCHEMAS,
        validators={
            "syntax": lambda output: [] if output.get("files") else ["no files listed"],
            "conventions": lambda output: [],
        },
    )


class TestAssistedMode:
    """FR-M33-04: the engine does its part, hands the model a bounded,
    schema-typed gap, and validates the return before it takes effect."""

    def test_engine_part_attached_and_gap_is_schema_typed(self, modes):
        client = FakeModelClient(outputs=[GOOD_PROPOSAL])
        modes.client = client
        result = modes.run("detect_ambiguity", {"story": "M33"})

        assert result.status == "completed"
        assert result.value == GOOD_PROPOSAL  # validated output takes effect
        assert len(client.requests) == 1
        request = client.requests[0]
        # The bounded, schema-typed gap payload:
        assert request.action_class == "detect_ambiguity"
        assert request.gap == "propose resolution"  # the bounded gap, not the task
        assert request.schema == "AmbiguityProposal"
        assert request.schema_doc == SCHEMAS["AmbiguityProposal"]
        assert request.partial == {"candidates": ["a", "b"]}  # engine's partial result
        assert request.context == {"story": "M33"}
        assert request.attempt == 0
        assert request.prior_errors == ()

    def test_invalid_return_is_rework_with_errors_fed_back(self, modes):
        bad = {"candidate": "a"}  # missing required 'resolution'
        client = FakeModelClient(outputs=[bad, GOOD_PROPOSAL])
        modes.client = client
        result = modes.run("detect_ambiguity", {})

        assert result.status == "completed"
        assert result.value == GOOD_PROPOSAL
        assert len(client.requests) == 2
        retry = client.requests[1]
        assert retry.attempt == 1
        assert retry.prior_errors  # validation errors named and fed back
        assert any("resolution" in error for error in retry.prior_errors)
        assert any("AmbiguityProposal" in error for error in retry.prior_errors)

    def test_rework_loop_is_bounded_then_refused_with_cause(self, modes):
        bad = {"candidate": "a"}
        client = FakeModelClient(outputs=[bad, bad, bad, GOOD_PROPOSAL])
        modes.client = client
        result = modes.run("detect_ambiguity", {})

        # Bounded: first attempt + DEFAULT_REWORK_LIMIT retries, then refuse
        # with cause — never a silent accept, never an unbounded loop.
        assert result.status == "rework_refused"
        assert result.attempts == 1 + modes.rework_limit
        assert len(client.requests) == result.attempts
        assert result.value is None  # the invalid output never takes effect
        assert result.validation_errors
        assert any("resolution" in error for error in result.validation_errors)
        assert "refused with cause" in result.reason

    def test_deterministic_checks_also_gate_the_return(self, catalogue):
        registry = CapabilityRegistry(catalogue)
        registry.register(
            "detect_ambiguity",
            FakeCapability("rule_ambiguity", result={"candidates": ["a"]}),
        )
        modes = EngineModes(
            dispatcher=Dispatcher(catalogue=catalogue, registry=registry),
            client=FakeModelClient(outputs=[GOOD_PROPOSAL]),
            schemas=SCHEMAS,
            checks={
                "detect_ambiguity": [
                    lambda output: []
                    if output["resolution"].startswith("rename")
                    else ["resolution must start with 'rename'"]
                ]
            },
        )
        result = modes.run("detect_ambiguity", {})
        assert result.status == "completed"

        modes.checks = {
            "detect_ambiguity": [lambda output: ["deterministic check failed"]]
        }
        modes.client = FakeModelClient(outputs=[GOOD_PROPOSAL, GOOD_PROPOSAL])
        result = modes.run("detect_ambiguity", {})
        assert result.status == "rework_refused"
        assert any("deterministic check failed" in e for e in result.validation_errors)

    def test_unregistered_schema_is_fail_closed(self, modes):
        modes.schemas = {}
        result = modes.run("detect_ambiguity", {})
        assert result.status == "rework_refused"
        assert result.value is None
        assert any("not registered" in e for e in result.validation_errors)


class TestGenerativeMode:
    """FR-M33-05: every model output is validated deterministically before
    it takes effect; failure is rework, then refusal with cause."""

    def test_valid_output_passes_validators_and_takes_effect(self, modes):
        seen = []
        modes.validators = {
            "syntax": lambda output: seen.append(output) or [],
            "conventions": lambda output: [],
        }
        modes.client = FakeModelClient(outputs=[GOOD_PATCH])
        result = modes.run("implement", {"packet": "p1"})

        assert result.status == "completed"
        assert result.value == GOOD_PATCH
        assert seen == [GOOD_PATCH]  # validators ran before the value took effect

    def test_failing_validators_is_bounded_rework_then_refusal(self, modes):
        modes.validators = {
            "syntax": lambda output: ["syntax error at line 1"],
            "conventions": lambda output: [],
        }
        modes.client = FakeModelClient(outputs=[GOOD_PATCH] * 10)
        result = modes.run("implement", {})

        assert result.status == "rework_refused"
        assert result.attempts == 1 + modes.rework_limit
        assert result.value is None
        assert any("syntax error at line 1" in e for e in result.validation_errors)
        assert "validator 'syntax'" in result.validation_errors[0]

    def test_unknown_validator_name_is_fail_closed(self, modes):
        modes.validators = {"syntax": lambda output: []}  # 'conventions' missing
        modes.client = FakeModelClient(outputs=[GOOD_PATCH])
        result = modes.run("implement", {})
        assert result.status == "rework_refused"
        assert result.value is None
        assert any("validator 'conventions' not registered" in e for e in result.validation_errors)

    def test_bare_callable_is_wrapped_as_a_client(self, modes):
        calls = []

        def plain(request):
            calls.append(request)
            return GOOD_PATCH

        modes.client = plain
        result = modes.run("implement", {})
        assert result.status == "completed"
        assert result.value == GOOD_PATCH
        assert len(calls) == 1

    def test_deterministic_class_never_reaches_the_model(self, modes):
        modes.client = FakeModelClient()
        result = modes.run("parse", {"path": "src/app.py"})
        assert result.status == "executed"
        assert result.value == {"tree": "ok"}
        assert modes.client.requests == []

    def test_refused_dispatch_does_not_reach_the_model(self, modes):
        modes.client = FakeModelClient()
        result = modes.run("conjure", {})
        assert result.status == "refused"
        assert modes.client.requests == []


class TestReplayIdentical:
    """FR-M33-08 / NFR-27: same inputs -> byte-identical results on the
    engine's deterministic path; stories replay without cassettes."""

    RULES = """
version: 1
rules:
  - id: name-tests-by-convention
    description: learned naming convention for tests
    action_classes: [implement, detect_ambiguity, parse]
    when:
      - {field: payload.path, op: matches, value: '.*_test\\.py$'}
    then:
      convention: test names read <method>_when_<condition>
"""

    def _build(self):
        catalogue = parse_catalogue(CATALOGUE, "test")
        registry = CapabilityRegistry(catalogue)
        registry.register("parse", FakeCapability("structural_parse", result={"tree": "ok"}))
        registry.register(
            "detect_ambiguity",
            FakeCapability("rule_ambiguity", result={"candidates": ["a", "b"]}),
        )
        rules = RuleSet(rules=parse_rule_document(self.RULES, "test").rules)
        return Dispatcher(catalogue=catalogue, registry=registry, rules=rules)

    @staticmethod
    def _canonical(outcome) -> str:
        return json.dumps(
            {
                "kind": outcome.kind,
                "action_class": outcome.action_class,
                "router_eligible": outcome.router_eligible,
                "why_llm": outcome.why_llm,
                "capability": outcome.capability,
                "gap": outcome.gap,
                "schema": outcome.schema,
                "validate": outcome.validate,
                "escalate_if": outcome.escalate_if,
                "rules_matched": outcome.rules_matched,
                "result": outcome.result,
                "reason": outcome.reason,
            },
            sort_keys=True,
            ensure_ascii=True,
        )

    @pytest.mark.parametrize("class_id", ["parse", "detect_ambiguity", "implement"])
    def test_dispatch_is_byte_identical_across_fresh_instances(self, class_id):
        payload = {"payload": {"path": "foo_test.py"}, "story": "M33"}
        first = self._canonical(self._build().dispatch(class_id, payload))
        second = self._canonical(self._build().dispatch(class_id, payload))
        assert first == second
        assert isinstance(first, str)

    def test_outcome_does_not_depend_on_prior_runs(self):
        """Replay from the middle of a story: outcomes of later actions do
        not depend on how many actions were dispatched before them."""
        one = self._build()
        one.dispatch("parse", {})
        single = self._canonical(one.dispatch("implement", {"x": 1}))

        many = self._build()
        for _ in range(7):
            many.dispatch("parse", {})
        batched = self._canonical(many.dispatch("implement", {"x": 1}))
        assert single == batched


class TestModelCallCeilings:
    """FR-M33-09: per-class and global model-call budgets from policy; a
    breach stops further model calls and records the breach."""

    def test_budget_comes_from_policy(self, catalogue):
        budget = ModelCallBudget.from_catalogue(catalogue)
        assert budget.global_limit == 3
        assert budget.per_class == {"implement": 2}

    def test_per_class_ceiling_stops_calls_and_records_breach(self, modes):
        modes.budget = ModelCallBudget(per_class={"implement": 1})
        modes.client = FakeModelClient(outputs=[GOOD_PATCH, GOOD_PATCH])

        first = modes.run("implement", {})
        assert first.status == "completed"
        second = modes.run("implement", {})
        assert second.status == "ceiling_breach"
        assert second.value is None
        assert first.attempts == 1
        assert len(modes.client.requests) == 1  # the breach made no model call
        assert any("per-class limit 1" in b for b in modes.budget.breaches)
        assert "per-class limit 1" in second.reason

    def test_global_ceiling_spans_classes(self, modes):
        modes.budget = ModelCallBudget(global_limit=2)
        modes.client = FakeModelClient(
            outputs=[GOOD_PROPOSAL, GOOD_PATCH, GOOD_PATCH]
        )
        assert modes.run("detect_ambiguity", {}).status == "completed"
        assert modes.run("implement", {}).status == "completed"
        third = modes.run("implement", {})
        assert third.status == "ceiling_breach"
        assert "global limit 2" in third.reason
        assert any("global limit 2" in b for b in modes.budget.breaches)

    def test_ceiling_breach_mid_rework_stops_the_loop(self, modes):
        bad = {"candidate": "a"}
        modes.budget = ModelCallBudget(per_class={"detect_ambiguity": 1})
        modes.client = FakeModelClient(outputs=[bad, GOOD_PROPOSAL])
        result = modes.run("detect_ambiguity", {})
        # First attempt consumed the class budget; the retry is denied at
        # the ceiling — the loop stops instead of burning calls.
        assert result.status == "ceiling_breach"
        assert result.attempts == 1
        assert result.validation_errors  # the rework cause is still named
        assert len(modes.client.requests) == 1

    def test_repo_catalogue_carries_model_call_ceilings(self):
        catalogue = load_catalogue(repo_default_paths())
        assert not catalogue.errors
        budget = ModelCallBudget.from_catalogue(catalogue)
        assert budget.global_limit == 40
        assert budget.per_class["implement"] == 8

    def test_no_ceiling_means_unlimited(self, modes):
        modes.budget = ModelCallBudget()
        modes.client = FakeModelClient(outputs=[GOOD_PATCH] * 20)
        for _ in range(5):
            assert modes.run("implement", {}).status == "completed"
        assert modes.budget.breaches == []
