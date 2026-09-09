"""Agent-vs-agent comparison on one story (FR-M37-04; F1 Workstream E task 22).

FR-M37-04: shadow mode (FR-M25-07, extended to external agents) — the same
task run by two agents, with yield, rejection reasons, cost and LLM ratio
side by side. The comparison derives from the ledger on demand
(FR-M17-05 — no metrics database) and reuses the same in-process cache +
append invalidation as the other trust metrics.

Side-by-side components, and what the ledger supports:

* **yield** — first-pass yield over the agent's ``diff`` entries on the
  story: 1 - rejected/proposed, where *rejected* is the F0 linked-rejection
  shape (the sequence is carried by a ``rejection`` entry) OR the entry's
  own ``rejected``/``reworked`` decision. No proposed changes by the agent
  on the story is **insufficient evidence, never zero**;
* **rejection reasons** — the E-GR-03 classes of the story's rejections
  attributed to the agent (the rejected change's author, resolved through
  ``rejected_sequence`` and falling back to the rejection entry's own
  actor — the same attribution rule as trust/reasonDistribution);
* **cost** — the ``cost_usd`` / ``tokens_in`` / ``tokens_out`` columns
  summed over everything the agent did in scope on the story. When NO
  in-scope entry by the agent carries any cost or token value the
  component is **insufficient evidence** — the ledger recorded no spend
  for this attempt;
* **LLM ratio** — the share of the story's recorded token throughput
  attributable to the agent: the agent's tokens (in + out) over the
  tokens recorded on every in-scope entry for the story. It answers "how
  LLM-heavy was this agent's approach relative to its competitor" from
  the only LLM-usage evidence the ledger carries. When the story records
  no tokens at all the component is **unknown** — the number is never
  fabricated.

Every component without evidence is labelled (``insufficient_evidence`` /
``unknown``) and carries a null value, so a thin agent is visible in the
comparison, never hidden behind a fabricated zero or a missing key.

Zero model calls (FR-M36-07): arithmetic over ledger rows.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..rejection.taxonomy import load_taxonomy
from .coverage import ATTACH_KEY, envelope_for, scan_scope

__all__ = ["compute_agent_comparison"]

_STATUS_OK = "ok"
_STATUS_INSUFFICIENT = "insufficient_evidence"
_STATUS_UNKNOWN = "unknown"

REJECTED_DECISIONS = ("rejected", "reworked")


def _component(status: str, value: float | None, **extra: Any) -> dict[str, Any]:
    component: dict[str, Any] = {"status": status, "value": value}
    component.update(extra)
    return component


def compute_agent_comparison(
    ledger,
    *,
    story_id: str,
    actor_ids: list[str] | tuple[str, ...] | None = None,
    repo_id: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    classify: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Side-by-side comparison of the agents that ran ``story_id``.

    ``actor_ids`` restricts (and orders) the comparison; absent, every
    actor with an in-scope entry on the story is compared. ``classify``
    maps the story id to greenfield/brownfield (None when the story has no
    commit data — reported as ``unclassified``, never dropped).
    """
    scope = {
        "storyId": story_id,
        "repoId": repo_id,
        "actorIds": list(actor_ids) if actor_ids is not None else None,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }

    # FR-M41-07 (D36): full-history cursor scans; the repo filter below is
    # a declared scope restriction, so the envelope keeps the whole
    # scanned story population (FR-M41-08). The rejection lookup is the
    # auxiliary scan: a capped lookup truncates the comparison too.
    rows, rows_available = scan_scope(
        ledger,
        story_id=story_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )
    scoped_rows = rows
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]

    rejection_rows, rejection_available = scan_scope(
        ledger, action_type="rejection"
    )
    rejection_scanned = rejection_rows
    if repo_id is not None:
        rejection_rows = [
            row for row in rejection_rows if row.get("repo_id") == repo_id
        ]
    if from_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] >= from_sequence
        ]
    if to_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] <= to_sequence
        ]
    story_rejections = [
        row for row in rejection_rows if row.get("story_id") == story_id
    ]
    rejected_sequences = {
        row["rejected_sequence"]
        for row in story_rejections
        if row.get("rejected_sequence") is not None
    }

    default_reason = load_taxonomy().default.id
    actors: list[str] = list(actor_ids) if actor_ids is not None else sorted(
        {row["actor_id"] for row in rows}
    )

    story_tokens = sum(
        (row.get("tokens_in") or 0) + (row.get("tokens_out") or 0)
        for row in rows
    )

    agents: dict[str, dict[str, Any]] = {}
    for actor in actors:
        diffs = [
            row
            for row in rows
            if row["actor_id"] == actor and row["action_type"] == "diff"
        ]
        proposed = len(diffs)
        rejected_count = sum(
            1
            for row in diffs
            if row["seq"] in rejected_sequences
            or row.get("decision") in REJECTED_DECISIONS
        )
        if proposed:
            rate = round(rejected_count / proposed, 6)
            yield_component = _component(
                _STATUS_OK, round(1 - rate, 6), proposed=proposed,
                rejected=rejected_count,
            )
        else:
            yield_component = _component(
                _STATUS_INSUFFICIENT,
                None,
                proposed=0,
                rejected=0,
                note="no proposed changes by this agent on the story",
            )

        # Rejection reasons attributed to this agent on the story — the
        # rejected change's author, falling back to the entry's own actor.
        by_class: dict[str, int] = {}
        total_reasons = 0
        for row in story_rejections:
            reason = row.get("rework_reason") or default_reason
            attributed = row["actor_id"]
            rejected_sequence = row.get("rejected_sequence")
            if rejected_sequence is not None:
                source = ledger.get_entry(rejected_sequence)
                if source is not None and source.get("actor_id"):
                    attributed = source["actor_id"]
            if attributed != actor:
                continue
            by_class[reason] = by_class.get(reason, 0) + 1
            total_reasons += 1
        if total_reasons:
            reasons_component = _component(
                _STATUS_OK,
                None,  # a distribution, not a scalar — the value is byClass
                total=total_reasons,
                byClass=dict(sorted(by_class.items())),
            )
        else:
            reasons_component = _component(
                _STATUS_INSUFFICIENT,
                None,
                total=0,
                byClass={},
                note="no rejections attributed to this agent on the story",
            )

        actor_rows = [row for row in rows if row["actor_id"] == actor]
        total_usd = sum(row.get("cost_usd") or 0.0 for row in actor_rows)
        tokens_in = sum(row.get("tokens_in") or 0 for row in actor_rows)
        tokens_out = sum(row.get("tokens_out") or 0 for row in actor_rows)
        spend_rows = sum(
            1
            for row in actor_rows
            if row.get("cost_usd") is not None
            or row.get("tokens_in") is not None
            or row.get("tokens_out") is not None
        )
        if spend_rows:
            cost_component = _component(
                _STATUS_OK,
                round(total_usd, 6),
                totalUsd=round(total_usd, 6),
                tokensIn=tokens_in,
                tokensOut=tokens_out,
                entries=spend_rows,
            )
        else:
            cost_component = _component(
                _STATUS_INSUFFICIENT,
                None,
                totalUsd=None,
                tokensIn=0,
                tokensOut=0,
                entries=0,
                note="no in-scope entry by this agent carries cost or token data",
            )

        agent_tokens = tokens_in + tokens_out
        if story_tokens:
            llm_component = _component(
                _STATUS_OK,
                round(agent_tokens / story_tokens, 6),
                tokens=agent_tokens,
                storyTokens=story_tokens,
            )
        else:
            llm_component = _component(
                _STATUS_UNKNOWN,
                None,
                tokens=agent_tokens,
                storyTokens=0,
                note="the story records no token usage",
            )

        agents[actor] = {
            "yield": yield_component,
            "rejectionReasons": reasons_component,
            "cost": cost_component,
            "llmRatio": llm_component,
        }

    if classify is None:
        story_classification = "unclassified"
    else:
        story_classification = classify(story_id) or "unclassified"

    return {
        "scope": scope,
        "storyId": story_id,
        "storyClassification": story_classification,
        "agents": agents,
        # Multi-figure result: the envelope carries no single value.
        ATTACH_KEY: envelope_for(
            None,
            scoped_rows,
            rows_available,
            aux_scans=((rejection_scanned, rejection_available),),
        ).to_dict(),
    }
