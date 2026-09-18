"""The M8 router: model calls go through here, never around.

See the package docstring for the requirement mapping. The single
structural rule (FR-M8-15): there is no code path from a non-eligible
engine outcome to a permitted model call except the explicit
policy-permission (human override) path, which is itself recorded with
its own why_llm value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from meridian_core.engine.dispatch import (
    WHY_ASSISTED_GAP,
    WHY_GENERATIVE_BY_POLICY,
    WHY_NO_DETERMINISTIC_PATH,
    Dispatcher,
)

WHY_HUMAN_OVERRIDE = "human_override"

#: FR-M8-16 closed vocabulary. Anything else is a defect, not an extension.
WHY_LLM_VOCABULARY = (
    WHY_NO_DETERMINISTIC_PATH,
    WHY_ASSISTED_GAP,
    WHY_GENERATIVE_BY_POLICY,
    WHY_HUMAN_OVERRIDE,
)


class RouterError(ValueError):
    """A router input violated a closed vocabulary or a structural rule."""


@dataclass(frozen=True)
class RouteDecision:
    """One router decision. ``permitted`` False means no model call may
    proceed; ``refusal_reason`` names why (readable, ledger-recorded).
    ``recorded_sequence`` is the ledger sequence of the evidence entry —
    every decision leaves one."""

    permitted: bool
    action_class: str
    why_llm: str | None
    refusal_reason: str | None = None
    human_override: bool = False
    recorded_sequence: int | None = None


@dataclass(frozen=True)
class DependencyRatio:
    """FR-M8-17: LLM dependency ratio over a scope.

    ``model_calls / (model_calls + engine_executions)``; ``None`` when the
    denominator is zero — insufficient evidence is reported, never
    fabricated as 0 or 1. ``ceiling``/``breached`` attach the policy check
    when a ceiling was supplied.
    """

    scope: Mapping[str, str]
    model_calls: int
    engine_executions: int
    ratio: float | None
    ceiling: float | None = None
    breached: bool | None = None
    escalation_sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": dict(self.scope),
            "modelCalls": self.model_calls,
            "engineExecutions": self.engine_executions,
            "ratio": self.ratio,
            "ceiling": self.ceiling,
            "breached": self.breached,
            "escalationSequence": self.escalation_sequence,
        }


class Router:
    """The model-call boundary behind the engine.

    ``dispatcher`` is the M33 engine boundary (catalogue + capabilities +
    rules). ``ledger`` records refusals (FR-M8-15) and permitted calls with
    their why_llm (FR-M8-16); both entry kinds ride the hash chain, so the
    ratio in FR-M8-17 is computed from evidence, not self-report.
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        ledger: Any = None,
        *,
        ceilings: Mapping[str, float] | None = None,
        levers: Any = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._ledger = ledger
        #: FR-M26-04 cost levers (prompt caching, compaction,
        #: summarisation). None = pass-through (levers off).
        self._levers = levers
        self._lever_report = None
        if levers is not None:
            from meridian_core.levers import LeverReport

            self._lever_report = LeverReport()
        #: FR-M8-17 policy ceilings, e.g. {"default": 0.35} or
        #: {"story:EDB-1": 0.2}. The most specific key wins; "default" is
        #: the fallback.
        self._ceilings = dict(ceilings or {})

    # -- the decision ---------------------------------------------------------

    def request_model_call(
        self,
        *,
        action_class: str,
        agent_id: str,
        story_id: str,
        phase: str,
        payload: Mapping[str, Any] | None = None,
        human_override: bool = False,
        loop_id: str = "router",
        loop_iteration: int = 1,
    ) -> RouteDecision:
        """FR-M8-15/16: decide one model call. Refusals and permits are both
        ledger-recorded before the decision returns."""
        outcome = self._dispatcher.dispatch(action_class, payload)

        if not outcome.router_eligible and not human_override:
            reason = (
                f"FR-M8-15: action class '{action_class}' has a deterministic"
                f" path (engine outcome kind={outcome.kind}); a model call is"
                " refused unless policy explicitly permits it"
            )
            sequence = self._record(
                action_type="rejection",
                decision="rejected",
                action_class=action_class,
                agent_id=agent_id,
                story_id=story_id,
                phase=phase,
                loop_id=loop_id,
                loop_iteration=loop_iteration,
                detail={"refusal": "model_call", "reason": reason,
                        "engineOutcome": outcome.kind},
            )
            return RouteDecision(
                permitted=False,
                action_class=action_class,
                why_llm=None,
                refusal_reason=reason,
                recorded_sequence=sequence,
            )

        if outcome.router_eligible:
            why = outcome.why_llm
            if why not in WHY_LLM_VOCABULARY or why == WHY_HUMAN_OVERRIDE:
                # The engine never assigns human_override; an eligible
                # outcome without a valid engine why is a defect — fail
                # closed rather than permit an unlabelled call.
                reason = (
                    f"router: eligible outcome for '{action_class}' carried"
                    f" invalid why_llm {why!r}; refusing (fail-closed)"
                )
                sequence = self._record(
                    action_type="rejection",
                    decision="rejected",
                    action_class=action_class,
                    agent_id=agent_id,
                    story_id=story_id,
                    phase=phase,
                    loop_id=loop_id,
                    loop_iteration=loop_iteration,
                    detail={"refusal": "model_call", "reason": reason},
                )
                return RouteDecision(
                    permitted=False,
                    action_class=action_class,
                    why_llm=None,
                    refusal_reason=reason,
                    recorded_sequence=sequence,
                )
        else:
            # human_override on a non-eligible class: the explicit policy
            # permission FR-M8-15 allows. The override itself is recorded.
            why = WHY_HUMAN_OVERRIDE

        detail: dict[str, Any] = {
            "whyLlm": why,
            "humanOverride": human_override,
            "engineOutcome": outcome.kind,
        }
        if self._levers is not None:
            from meridian_core.levers import savings_to_ledger_detail

            # FR-M26-04: shape the call before it is considered dispatched,
            # and record what the levers saved. No prompt in the payload
            # is a pass-through — the levers never invent content.
            prompt = (payload or {}).get("prompt")
            savings = None
            if isinstance(prompt, str):
                _, savings = self._levers.apply(
                    prompt=prompt, story_id=story_id, why_llm=why
                )
                self._lever_report.record(story_id, savings)
            detail["levers"] = (
                savings.to_dict() if savings is not None else {}
            )
        sequence = self._record(
            action_type="model_call",
            decision="proposed",
            action_class=action_class,
            agent_id=agent_id,
            story_id=story_id,
            phase=phase,
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            detail=detail,
        )
        return RouteDecision(
            permitted=True,
            action_class=action_class,
            why_llm=why,
            human_override=human_override,
            recorded_sequence=sequence,
        )

    # -- FR-M8-17: dependency ratio ---------------------------------------------

    def record_engine_execution(
        self,
        *,
        action_class: str,
        agent_id: str,
        story_id: str,
        phase: str,
        loop_id: str = "engine",
        loop_iteration: int = 1,
    ) -> int | None:
        """Record a deterministic engine execution. The FR-M8-17 ratio's
        denominator is evidence: every deterministic execution that stood
        in place of a model call is written here by the caller that ran it
        (the loop runtime in M4; tests today)."""
        return self._record(
            action_type="engine_executed",
            decision="approved",
            action_class=action_class,
            agent_id=agent_id,
            story_id=story_id,
            phase=phase,
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            detail={"engine": "deterministic"},
        )

    def dependency_ratio(
        self,
        *,
        agent_id: str | None = None,
        phase: str | None = None,
        story_id: str | None = None,
        action_class: str | None = None,
        ceiling: float | None = None,
    ) -> DependencyRatio:
        """LLM dependency ratio over the given scope (FR-M8-17).

        Counts evidence entries: ``model_call`` vs ``engine_executed``,
        filtered by whichever scope dimensions are given. A scope with no
        denominator reports ``ratio: None`` — insufficient evidence.
        A ceiling (explicit or from policy) that is breached is recorded
        as an escalation entry ONCE per call that observes the breach.
        """
        if self._ledger is None:
            raise RouterError("router has no ledger; ratio needs evidence")
        scope = {
            k: v
            for k, v in (
                ("agent", agent_id),
                ("phase", phase),
                ("story", story_id),
                ("class", action_class),
            )
            if v is not None
        }
        model_calls, engine_runs = self._count(scope)
        total = model_calls + engine_runs
        ratio = (model_calls / total) if total else None
        effective_ceiling = ceiling if ceiling is not None else self._ceiling_for(
            scope
        )
        breached = None
        escalation = None
        if effective_ceiling is not None and ratio is not None:
            breached = ratio > effective_ceiling
            if breached:
                escalation = self._record(
                    action_type="policy_update",
                    decision="proposed",
                    action_class=action_class or "*",
                    agent_id=agent_id or "router",
                    story_id=story_id or "router",
                    phase=phase or "govern",
                    loop_id="router",
                    loop_iteration=1,
                    detail={
                        "event": "llm_ratio_ceiling_breached",
                        "scope": scope,
                        "ratio": ratio,
                        "ceiling": effective_ceiling,
                    },
                )
        return DependencyRatio(
            scope=scope,
            model_calls=model_calls,
            engine_executions=engine_runs,
            ratio=ratio,
            ceiling=effective_ceiling,
            breached=breached,
            escalation_sequence=escalation,
        )

    def _ceiling_for(self, scope: Mapping[str, str]) -> float | None:
        keys = [f"{k}:{v}" for k, v in scope.items()]
        keys.append("default")
        for key in keys:
            if key in self._ceilings:
                return self._ceilings[key]
        return None

    def _count(self, scope: Mapping[str, str]) -> tuple[int, int]:
        model_calls = 0
        engine_runs = 0
        for action_type in ("model_call", "engine_executed"):
            for row in self._ledger.query(action_type=action_type, limit=100000):
                if not self._scope_matches(row, scope):
                    continue
                if action_type == "model_call":
                    model_calls += 1
                else:
                    engine_runs += 1
        return model_calls, engine_runs

    def _scope_matches(self, row: Mapping[str, Any], scope: Mapping[str, str]) -> bool:
        dimension_column = {
            "agent": "actor_id",
            "phase": "phase",
            "story": "story_id",
        }
        for dimension, value in scope.items():
            column = dimension_column.get(dimension)
            if column is not None:
                if row.get(column) != value:
                    return False
            elif dimension == "class":
                # action_class rides in the encrypted detail blob; the
                # scope filter reads it back the same way an auditor would.
                if self._detail(row).get("actionClass") != value:
                    return False
        return True

    def _detail(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        if not row.get("input_ref"):
            return {}
        try:
            raw = self._ledger.read_blob(row["input_ref"], row["blob_key_id"])
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001 - unreadable detail scopes out
            return {}

    # -- ledger writing -----------------------------------------------------------

    def _record(
        self,
        *,
        action_type: str,
        decision: str,
        action_class: str,
        agent_id: str,
        story_id: str,
        phase: str,
        loop_id: str,
        loop_iteration: int,
        detail: Mapping[str, Any],
    ) -> int | None:
        if self._ledger is None:
            return None
        result = self._ledger.append(
            {
                "story_id": story_id,
                "phase": phase,
                "loop_id": loop_id,
                "loop_iteration": loop_iteration,
                "actor_id": agent_id,
                "actor_version": "router/v1",
                "actor_kind": "meta",
                "policy_version": "router/v1",
                "action_type": action_type,
                "decision": decision,
                "input": json.dumps(
                    {"actionClass": action_class, **detail}, ensure_ascii=False
                ),
            }
        )
        return result.sequence
