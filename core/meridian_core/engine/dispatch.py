"""Deterministic-first dispatch (FR-M33-03; FR-M8-15/-16 seam).

Every agent action is dispatched to the engine BEFORE the router. For each
action the engine returns exactly one decision:

* ``executed``    — a deterministic capability (FR-M33-02) did the whole
                    action. The outcome is not router-eligible; a model call
                    for this class is structurally impossible to reach from
                    here (FR-M8-15 is enforced AT this boundary — the router
                    workstream adds its own refusal as defence in depth).
* ``assisted``    — the class is assisted by policy: the engine runs its
                    ``deterministicFirst`` capability (the substantive
                    work), then declares the bounded gap and gap schema the
                    model may fill (full assisted mode, FR-M33-04, lands in
                    slice 3 — the dispatch decision and its shape are fixed
                    here).
* ``generative``  — the class is generative by policy: the engine cannot
                    help; the router may be invoked, and every output must
                    pass the class's ``validate`` list before it takes
                    effect (FR-M33-05).
* ``refused``     — unknown class, fail-closed catalogue, or a deterministic
                    class whose capability reported ``no_deterministic_path``
                    without a named ``escalateIf`` condition. Router-eligible
                    is False; nothing downstream may turn this into a model
                    call (FR-M8-15).

Learned rules (FR-M33-06) are consulted ahead of EVERY decision whose class
could reach the router — the matched rule ids ride on the outcome so the
validators and the ledger see that distillation was applied first.

Router-eligible outcomes carry ``why_llm`` from the FR-M8-16 vocabulary
(``no_deterministic_path`` · ``assisted_gap`` · ``generative_by_policy``;
``human_override`` is assigned by the router, never here). Zero model calls:
this module only consults the catalogue, the capability registry and the
rule set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .capabilities import CapabilityRegistry
from .catalogue import Catalogue
from .rules import RuleSet

__all__ = ["DispatchOutcome", "Dispatcher"]

#: FR-M8-16 why_llm vocabulary (human_override is router-assigned only).
WHY_NO_DETERMINISTIC_PATH = "no_deterministic_path"
WHY_ASSISTED_GAP = "assisted_gap"
WHY_GENERATIVE_BY_POLICY = "generative_by_policy"

OUTCOME_KINDS = ("executed", "assisted", "generative", "refused")


@dataclass(frozen=True)
class DispatchOutcome:
    """The engine's decision for one action. ``router_eligible`` is the
    single gate the router boundary checks — there is no code path from a
    non-eligible outcome to a model call."""

    kind: str  # one of OUTCOME_KINDS
    action_class: str
    router_eligible: bool
    why_llm: str | None = None
    capability: str | None = None
    gap: str | None = None
    schema: str | None = None
    validate: tuple[str, ...] = ()
    escalate_if: str | None = None
    rules_matched: tuple[str, ...] = ()
    result: Any = None
    reason: str = ""


@dataclass
class Dispatcher:
    """The engine's dispatch boundary. Constructed with the catalogue, the
    capability registry and (optionally) the loaded learned rules."""

    catalogue: Catalogue
    registry: CapabilityRegistry
    rules: RuleSet = field(default_factory=RuleSet)

    def dispatch(
        self, action_class: str, payload: Mapping[str, Any] | None = None
    ) -> DispatchOutcome:
        """Decide — and where possible execute — one agent action. Never
        raises on policy content; refuses instead (fail-closed)."""
        payload = payload or {}
        entry = self.catalogue.lookup(action_class)
        if entry is None:
            reason = (
                "unknown action class"
                if not self.catalogue.fail_closed
                else f"catalogue fail-closed: {'; '.join(self.catalogue.errors)}"
            )
            return DispatchOutcome(
                kind="refused",
                action_class=action_class,
                router_eligible=False,
                reason=reason,
            )

        # FR-M33-06: learned rules are consulted ahead of any decision that
        # could reach the router, and the matched ids ride on the outcome.
        matched = self.rules.matching(action_class, payload)
        rules_matched = tuple(rule.id for rule in matched)

        if entry.mode == "deterministic":
            return self._dispatch_deterministic(entry, payload, rules_matched)
        if entry.mode == "assisted":
            return self._dispatch_assisted(entry, payload, rules_matched)
        return DispatchOutcome(
            kind="generative",
            action_class=entry.id,
            router_eligible=True,
            why_llm=WHY_GENERATIVE_BY_POLICY,
            schema=entry.schema,
            validate=entry.validate,
            rules_matched=rules_matched,
            reason="generative by policy; engine output validation is router-side (FR-M33-05)",
        )

    def _dispatch_deterministic(self, entry, payload, rules_matched) -> DispatchOutcome:
        capability = self.registry.resolve(entry.id)
        if capability is None:
            reason = f"capability '{entry.capability}' not registered (FR-M33-02 pending)"
            if entry.escalate_if:
                return DispatchOutcome(
                    kind="generative",
                    action_class=entry.id,
                    router_eligible=True,
                    why_llm=WHY_NO_DETERMINISTIC_PATH,
                    capability=entry.capability,
                    escalate_if=entry.escalate_if,
                    schema=entry.schema,
                    rules_matched=rules_matched,
                    reason=f"{reason}; escalation condition '{entry.escalate_if}' named in policy",
                )
            return DispatchOutcome(
                kind="refused",
                action_class=entry.id,
                router_eligible=False,
                capability=entry.capability,
                rules_matched=rules_matched,
                reason=f"{reason}; class has no named escalation condition — a model call is "
                f"structurally impossible (FR-M8-15)",
            )
        outcome = capability.run(payload)
        if outcome.handled:
            return DispatchOutcome(
                kind="executed",
                action_class=entry.id,
                router_eligible=False,
                capability=capability.name,
                schema=entry.schema,
                rules_matched=rules_matched,
                result=outcome.result,
                reason=outcome.reason or "executed deterministically (FR-M33-03)",
            )
        # no_deterministic_path for this instance: escalate only if policy
        # named the condition; otherwise refuse (FR-M8-15).
        if entry.escalate_if:
            return DispatchOutcome(
                kind="generative",
                action_class=entry.id,
                router_eligible=True,
                why_llm=WHY_NO_DETERMINISTIC_PATH,
                capability=capability.name,
                escalate_if=entry.escalate_if,
                schema=entry.schema,
                rules_matched=rules_matched,
                reason=f"capability reports no_deterministic_path: {outcome.reason}; "
                f"escalation condition '{entry.escalate_if}' named in policy",
            )
        return DispatchOutcome(
            kind="refused",
            action_class=entry.id,
            router_eligible=False,
            capability=capability.name,
            rules_matched=rules_matched,
            reason=f"capability reports no_deterministic_path: {outcome.reason}; class has "
            f"no named escalation condition — a model call is structurally impossible (FR-M8-15)",
        )

    def _dispatch_assisted(self, entry, payload, rules_matched) -> DispatchOutcome:
        # The engine does the substantive work now (FR-M33-04); the bounded
        # gap + schema are declared for the router. Full assisted validation
        # of the return lands in slice 3.
        first = self.registry.resolve_first(entry.id)
        result = None
        note = "deterministic-first phase not registered"
        if first is not None:
            outcome = first.run(payload)
            if outcome.handled:
                result = outcome.result
                note = "deterministic-first phase executed"
            else:
                note = f"deterministic-first phase reports no_deterministic_path: {outcome.reason}"
        return DispatchOutcome(
            kind="assisted",
            action_class=entry.id,
            router_eligible=True,
            why_llm=WHY_ASSISTED_GAP,
            capability=entry.deterministic_first,
            gap=entry.gap,
            schema=entry.schema,
            rules_matched=rules_matched,
            result=result,
            reason=f"{note}; bounded gap '{entry.gap}' declared (FR-M33-04)",
        )
