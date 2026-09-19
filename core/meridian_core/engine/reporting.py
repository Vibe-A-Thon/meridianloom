"""Per-class engine reporting (FR-M33-07) over ledger dispatch records.

The engine records one dispatch record per action it handles (assisted /
generative / executed / refused). Records land in the open ledger as
``action_type="engine_dispatch"`` rows — the summary (action class,
mode, status, attempts, validation errors, why_llm) rides in the
``tool_calls`` JSON column, latency in ``latency_ms``, model cost in
``cost_usd``, tokens in ``tokens_in``/``tokens_out`` — so the FR-M33-07
numbers are *derived from the ledger on demand*, never stored in a
metrics database (FR-M17-05, same convention as
``core/meridian_core/metrics/``).

:class:`EngineReporter` computes per action class:

* **deterministic hit rate** — executed / actions (the class needed no
  model at all);
* **assisted rate** — completed through the assisted gap / actions;
* **generative rate** — completed through the generative path / actions;
* **latency and cost** — total and average model-call latency and cost
  per class;
* **cost saved versus the generative path** — for classes with a policy
  baseline (``cost_baselines``: the dollars a generative-only run of the
  class would have cost), saved = Σ(baseline − actual model cost) over
  executed/completed records. No baseline in policy means **unknown** —
  reported with no value, never an invented number (the same honesty
  convention as the DORA export).

Results cache in-process (``meridian_core.metrics.trust.TrustMetricsCache``)
and the cache key carries the ledger tip sequence: a record appended
after a compute can never serve a stale number, and the sidecar clears
the cache from its ``ledger.append`` handler exactly like the other
metrics caches.

Zero model calls: SQL aggregation and JSON parsing only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..metrics.trust import TrustMetricsCache

__all__ = ["DispatchRecord", "EngineReporter", "LedgerRecorder"]

#: The ledger action_type under which engine dispatch records land.
ENGINE_DISPATCH_ACTION = "engine_dispatch"


@dataclass(frozen=True)
class DispatchRecord:
    """One engine-mode outcome, as recorded for FR-M33-07 reporting."""

    action_class: str
    mode: str  # dispatch kind: executed|assisted|generative|refused
    status: str  # ModeResult status: executed|completed|refused|rework_refused|ceiling_breach
    attempts: int  # model calls made
    latency_ms: int
    cost_usd: float
    tokens_in: int
    tokens_out: int
    validation_errors: tuple[str, ...] = ()
    why_llm: str | None = None
    rules_matched: tuple[str, ...] = ()


class LedgerRecorder:
    """Appends one ``engine_dispatch`` ledger row per dispatch record.

    The normative columns carry the accounting natively; the class-level
    summary rides in ``tool_calls`` as a single-element JSON array (the
    column's documented shape).
    """

    def __init__(self, ledger: Any, *, policy_version: str = "catalogue") -> None:
        self._ledger = ledger
        self._policy_version = policy_version

    def record(
        self,
        record: DispatchRecord,
        *,
        story_id: str = "engine",
        phase: str = "engine",
        actor_id: str = "meridian-engine",
    ) -> Any:
        summary = [
            {
                "action_class": record.action_class,
                "mode": record.mode,
                "status": record.status,
                "attempts": record.attempts,
                "why_llm": record.why_llm,
                "rules_matched": list(record.rules_matched),
                "validation_errors": list(record.validation_errors),
            }
        ]
        return self._ledger.append(
            {
                "story_id": story_id,
                "phase": phase,
                "loop_id": "engine-dispatch",
                "loop_iteration": 0,
                "actor_id": actor_id,
                "actor_version": "0",
                "actor_kind": "meta",
                "policy_version": self._policy_version,
                "action_type": ENGINE_DISPATCH_ACTION,
                "tool_calls": json.dumps(summary, sort_keys=True),
                "latency_ms": record.latency_ms,
                "cost_usd": record.cost_usd,
                "tokens_in": record.tokens_in,
                "tokens_out": record.tokens_out,
            }
        )


class EngineReporter:
    """FR-M33-07 per-class metrics, derived from ledger dispatch records
    on demand and cached in-process (invalidated on ``ledger.append`` —
    the cache key carries the tip sequence, so a missed clear still
    cannot serve stale numbers)."""

    def __init__(
        self,
        ledger: Any,
        *,
        cost_baselines: Mapping[str, float] | None = None,
        cache: TrustMetricsCache | None = None,
    ) -> None:
        self._ledger = ledger
        #: Policy-supplied dollars-per-action baselines for the generative
        #: path, by action class; absent class → cost saved is unknown.
        self._cost_baselines = dict(cost_baselines or {})
        self._cache = cache or TrustMetricsCache()

    def invalidate(self) -> None:
        """Dropped on every ledger append (the sidecar's append handler),
        exactly like the other metrics caches."""
        self._cache.invalidate()

    def per_class(
        self,
        *,
        story_id: str | None = None,
        phase: str | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Per-class hit/assisted/generative rates, latency, cost and cost
        saved over the in-scope dispatch records."""
        scope = {
            "storyId": story_id,
            "phase": phase,
            "fromSequence": from_sequence,
            "toSequence": to_sequence,
        }
        key = f"engine-per-class:{json.dumps(scope, sort_keys=True)}@{self._ledger.last_sequence}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        rows = self._ledger.query_all(
            action_type=ENGINE_DISPATCH_ACTION,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
        )
        if story_id is not None:
            rows = [row for row in rows if row.get("story_id") == story_id]
        if phase is not None:
            rows = [row for row in rows if row.get("phase") == phase]

        classes: dict[str, dict[str, Any]] = {}
        for row in rows:
            summaries = json.loads(row.get("tool_calls") or "[]")
            if not summaries:
                continue
            summary = summaries[0]
            bucket = classes.setdefault(
                summary["action_class"],
                {
                    "actions": 0,
                    "executed": 0,
                    "assisted": 0,
                    "generative": 0,
                    "refused": 0,
                    "rework_refused": 0,
                    "ceiling_breach": 0,
                    "model_calls": 0,
                    "latency_ms": 0,
                    "cost_usd": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                },
            )
            bucket["actions"] += 1
            status = summary.get("status", "")
            mode = summary.get("mode", "")
            # assisted/generative are paths (the dispatch mode a completed
            # action took); executed/refused/rework_refused/ceiling_breach
            # are statuses.
            if mode in ("assisted", "generative"):
                bucket[mode] += 1
            if status in ("executed", "refused", "rework_refused", "ceiling_breach"):
                bucket[status] += 1
            bucket["model_calls"] += int(summary.get("attempts") or 0)
            bucket["latency_ms"] += int(row.get("latency_ms") or 0)
            bucket["cost_usd"] += float(row.get("cost_usd") or 0.0)
            bucket["tokens_in"] += int(row.get("tokens_in") or 0)
            bucket["tokens_out"] += int(row.get("tokens_out") or 0)

        report: dict[str, Any] = {}
        for class_id in sorted(classes):
            bucket = classes[class_id]
            actions = bucket["actions"]
            rates = {
                "deterministicHitRate": round(bucket["executed"] / actions, 6),
                "assistedRate": round(bucket["assisted"] / actions, 6),
                "generativeRate": round(bucket["generative"] / actions, 6),
            }
            baseline = self._cost_baselines.get(class_id)
            if baseline is None:
                cost_saved: Any = None
                saved_note = (
                    "no generative-path cost baseline in policy for this "
                    "class — cost saved is unknown, not invented"
                )
            else:
                saved = 0.0
                for row in rows:
                    summaries = json.loads(row.get("tool_calls") or "[]")
                    if not summaries or summaries[0].get("action_class") != class_id:
                        continue
                    if summaries[0].get("status") in ("executed", "completed"):
                        saved += baseline - float(row.get("cost_usd") or 0.0)
                cost_saved = round(saved, 6)
                saved_note = "policy baseline minus actual model cost, summed over executed/completed records"
            report[class_id] = {
                "actions": actions,
                "counts": {
                    key: bucket[key]
                    for key in (
                        "executed",
                        "assisted",
                        "generative",
                        "refused",
                        "rework_refused",
                        "ceiling_breach",
                    )
                },
                "rates": rates,
                "modelCalls": bucket["model_calls"],
                "latencyMs": {
                    "total": bucket["latency_ms"],
                    "avg": round(bucket["latency_ms"] / actions, 3),
                },
                "costUsd": {
                    "total": round(bucket["cost_usd"], 6),
                    "avg": round(bucket["cost_usd"] / actions, 6),
                },
                "tokens": {"in": bucket["tokens_in"], "out": bucket["tokens_out"]},
                "costSavedUsd": cost_saved,
                "notes": {"costSaved": saved_note},
            }

        result = {"scope": scope, "ledgerTip": self._ledger.last_sequence, "classes": report}
        self._cache.put(key, result)
        return result
