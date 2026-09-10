"""F2 — the evidence gate, computed rather than argued.

``gaps_implementation.md`` §F2 defines a decision phase, not a build phase:
twenty real stories from the team's own backlog, through F0 + F1, using the
team's own agents, and then a written decision — GO to F3, STOP and ship the
recorder, PIVOT to analytics, or KILL — with the raw ledger slice attached.

Every measure it names was already computable from shipped surfaces, but they
were computable in seven different places. A team finishing twenty stories had
to assemble the verdict by hand from seven panels, which is precisely the kind
of manual assembly this project has repeatedly got wrong: each part true, the
whole unverified.

This module computes the gate in one call, and its central discipline is what
it refuses to do. **Two of the seven measures are not recorded anywhere**, and
this returns them as ``unavailable`` with the reason, never as zero:

* *provenance queries actually run* — nothing counts reads. Meridian records
  what agents did, not what humans looked at, and adding usage counting is a
  product decision with a privacy cost, not an oversight to paper over here.
* *first-value retention at week 8* — requires knowing who is still using it,
  which the product deliberately does not phone home to learn.

A verdict computed over five of seven measures is a partial verdict, and it
says so. `insufficient_evidence` is a real outcome of this gate, not a
failure of it — reporting GO on a five-story sample would be the single most
expensive lie this codebase could tell, because F3 is the Orchestra build.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Callable

from .coverage import ATTACH_KEY, envelope_for, scan_scope

#: §F2 requires twenty. Fewer is not a smaller answer, it is no answer.
REQUIRED_STORIES = 20

#: Measure states. `unavailable` means the evidence does not exist; `ok` means
#: it does. There is deliberately no state that means "assume zero".
OK = "ok"
UNAVAILABLE = "unavailable"
INSUFFICIENT = "insufficient_evidence"

GO = "go"
STOP = "stop"
PIVOT = "pivot"
KILL = "kill"


def _measure(
    status: str,
    *,
    value: Any = None,
    note: str,
    **extra: Any,
) -> dict[str, Any]:
    return {"status": status, "value": value, "note": note, **extra}


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 6) if whole else None


def compute_evidence_gate(
    ledger: Any,
    *,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    baseline_change_failure_rate: float | None = None,
    hygiene: Callable[[str], list[str]] | None = None,
) -> dict[str, Any]:
    """The F2 gate over the ledger's own record.

    ``baseline_change_failure_rate`` is the team's pre-Meridian figure, which
    the ledger cannot know — it is the team's own number, supplied by whoever
    runs the gate. Absent, the comparison reads unavailable rather than
    inventing a baseline to beat.

    ``hygiene`` maps a subject to FR-M20-06 warnings (``roles.assess_hygiene``
    bound to the workspace's role pack). Absent, approval hygiene reads
    unavailable rather than reporting a clean bill from no check.
    """
    rows, rows_available = scan_scope(
        ledger, from_sequence=from_sequence, to_sequence=to_sequence
    )

    stories = sorted({str(row.get("story_id")) for row in rows if row.get("story_id")})
    diffs = [row for row in rows if row.get("action_type") == "diff"]
    gates = [row for row in rows if row.get("action_type") == "gate"]
    approvals = [row for row in rows if row.get("action_type") == "approval"]
    rejections = [row for row in rows if row.get("action_type") == "rejection"]

    # Which stories were gated at all. The whole gate turns on comparing work
    # that passed through the governance layer with work that did not.
    gated_stories = {str(row.get("story_id")) for row in gates if row.get("story_id")}
    ungated_stories = {s for s in stories if s not in gated_stories}

    measures: dict[str, dict[str, Any]] = {}

    # --- 1. rejection rate, gated vs ungated ------------------------------
    def _rejection_rate(story_ids: set[str]) -> tuple[float | None, int, int]:
        scoped = [d for d in diffs if str(d.get("story_id")) in story_ids]
        rejected = {
            row.get("rejected_sequence")
            for row in rejections
            if str(row.get("story_id")) in story_ids
        }
        hit = [d for d in scoped if d.get("seq") in rejected]
        return _rate(len(hit), len(scoped)), len(hit), len(scoped)

    after, after_hit, after_n = _rejection_rate(gated_stories)
    before, before_hit, before_n = _rejection_rate(ungated_stories)
    if after is None or before is None:
        measures["rejectionRate"] = _measure(
            UNAVAILABLE,
            note=(
                "the comparison needs proposed changes on both sides — "
                f"{after_n} gated and {before_n} ungated in this scope. "
                "Without both, there is nothing to compare gating against."
            ),
            gated={"rate": after, "rejected": after_hit, "proposed": after_n},
            ungated={"rate": before, "rejected": before_hit, "proposed": before_n},
        )
    else:
        measures["rejectionRate"] = _measure(
            OK,
            value=round(after - before, 6),
            note=(
                f"gated {after:.1%} against ungated {before:.1%}. "
                "A negative delta means gating reduced rejection."
            ),
            gated={"rate": after, "rejected": after_hit, "proposed": after_n},
            ungated={"rate": before, "rejected": before_hit, "proposed": before_n},
        )

    # --- 2. defects the gates caught that the agent's process missed -------
    blocked = [row for row in gates if str(row.get("decision")) in {"block", "blocked"}]
    if not gates:
        measures["gateCatches"] = _measure(
            UNAVAILABLE,
            note="no gate was evaluated in this scope, so nothing was caught or missed.",
            gatesRun=0,
        )
    else:
        measures["gateCatches"] = _measure(
            OK,
            value=len(blocked),
            note=(
                f"{len(blocked)} of {len(gates)} gate evaluations blocked a change "
                "the agent's own process had already proposed."
            ),
            gatesRun=len(gates),
            blocked=len(blocked),
            blockRate=_rate(len(blocked), len(gates)),
        )

    # --- 3. change failure rate against the team's own baseline -----------
    merged = [row for row in diffs if str(row.get("decision")) == "approved"]
    reverted = {
        row.get("rejected_sequence")
        for row in rejections
        if "revert" in str(row.get("tool_calls") or "").lower()
    }
    gated_merged = [m for m in merged if str(m.get("story_id")) in gated_stories]
    failed = [m for m in gated_merged if m.get("seq") in reverted]
    observed = _rate(len(failed), len(gated_merged))
    if observed is None:
        measures["changeFailureRate"] = _measure(
            UNAVAILABLE,
            note="no gated change was merged in this scope, so no failure rate exists.",
        )
    elif baseline_change_failure_rate is None:
        measures["changeFailureRate"] = _measure(
            UNAVAILABLE,
            value=observed,
            note=(
                f"gated change failure rate is {observed:.1%}, but no team baseline "
                "was supplied. The ledger cannot know what this team's rate was "
                "before Meridian; supply it to make the comparison."
            ),
            observed=observed,
            merged=len(gated_merged),
        )
    else:
        measures["changeFailureRate"] = _measure(
            OK,
            value=round(observed - baseline_change_failure_rate, 6),
            note=(
                f"gated {observed:.1%} against a supplied baseline of "
                f"{baseline_change_failure_rate:.1%}."
            ),
            observed=observed,
            baseline=baseline_change_failure_rate,
            merged=len(gated_merged),
        )

    # --- 4. approval hygiene (FR-M20-06) -----------------------------------
    subjects = sorted(
        {str(row.get("subject")) for row in approvals if row.get("subject")}
    )
    if hygiene is None:
        measures["approvalHygiene"] = _measure(
            UNAVAILABLE,
            note=(
                "no role pack was available to assess against, so rubber-stamping "
                "signals were not measured. This is not a clean bill of health."
            ),
            approvals=len(approvals),
        )
    elif not subjects:
        measures["approvalHygiene"] = _measure(
            UNAVAILABLE,
            note="no approval was recorded in this scope.",
            approvals=0,
        )
    else:
        warnings = [w for subject in subjects for w in hygiene(subject)]
        measures["approvalHygiene"] = _measure(
            OK,
            value=len(warnings),
            note=(
                f"{len(warnings)} rubber-stamping signal(s) across {len(subjects)} "
                "approved subject(s). Zero is the healthy figure."
            ),
            approvals=len(approvals),
            subjects=len(subjects),
            warnings=warnings[:50],
        )

    # --- 5. the time the layer costs --------------------------------------
    # From gate-open to approval on the same subject: the tax, in seconds.
    from .dora import _parse_ts  # local: shares the canonical ISO parse

    opened: dict[str, Any] = {}
    for row in gates:
        subject = str(row.get("subject") or row.get("story_id") or "")
        stamp = _parse_ts(row.get("ts_utc"))
        if subject and stamp and subject not in opened:
            opened[subject] = stamp
    costs: list[float] = []
    for row in approvals:
        subject = str(row.get("subject") or row.get("story_id") or "")
        stamp = _parse_ts(row.get("ts_utc"))
        start = opened.get(subject)
        if stamp and start and stamp > start:
            costs.append((stamp - start).total_seconds())
    if not costs:
        measures["timeCostPerGatedChange"] = _measure(
            UNAVAILABLE,
            note=(
                "no subject has both a gate evaluation and a later approval, so "
                "the tax the layer imposes cannot be measured."
            ),
        )
    else:
        measures["timeCostPerGatedChange"] = _measure(
            OK,
            value=round(median(costs), 3),
            note=(
                f"median {median(costs) / 60:.1f} minutes from gate evaluation to "
                f"approval across {len(costs)} subject(s)."
            ),
            samples=len(costs),
            unit="seconds",
        )

    # --- 6 and 7. the two nobody records ----------------------------------
    measures["provenanceQueriesRun"] = _measure(
        UNAVAILABLE,
        note=(
            "Meridian records what agents did, not what humans looked at. "
            "Nothing counts provenance reads, so whether anyone actually uses "
            "the thing the product is for cannot be answered from the ledger. "
            "Counting reads is a product decision with a privacy cost, not an "
            "omission to be papered over with a zero."
        ),
    )
    measures["firstValueRetention"] = _measure(
        UNAVAILABLE,
        note=(
            "week-8 retention needs to know who is still using it, and the "
            "product deliberately does not phone home to learn that. Ask the "
            "five testers directly and record the answer alongside this report."
        ),
    )

    # --- the verdict --------------------------------------------------------
    verdict, reasons = _decide(len(stories), measures)

    return {
        "scope": {
            "fromSequence": from_sequence,
            "toSequence": to_sequence,
            "baselineChangeFailureRate": baseline_change_failure_rate,
        },
        "stories": {
            "total": len(stories),
            "required": REQUIRED_STORIES,
            "gated": len(gated_stories),
            "ungated": len(ungated_stories),
            "ids": stories[:200],
        },
        "measures": measures,
        "recommendation": {"verdict": verdict, "reasons": reasons},
        ATTACH_KEY: envelope_for(None, rows, rows_available).to_dict(),
    }


def _decide(story_count: int, measures: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """§F2's go / stop / pivot / kill, applied to what was measured.

    The thresholds are the ones written in the plan, not invented here. Where
    the evidence does not reach them, the answer is `insufficient_evidence` —
    which is a real outcome of this gate, and a far cheaper one than a GO that
    starts the Orchestra build on a five-story sample.
    """
    reasons: list[str] = []

    if story_count < REQUIRED_STORIES:
        return INSUFFICIENT, [
            f"{story_count} of {REQUIRED_STORIES} stories. The gate is defined over "
            "twenty real stories; fewer is not a smaller answer, it is no answer."
        ]

    unavailable = [name for name, m in measures.items() if m["status"] != OK]
    if len(unavailable) > 2:
        # Two are structurally unrecordable (queries, retention). More than
        # that means the run itself did not produce the evidence.
        return INSUFFICIENT, [
            "more measures are unavailable than the two the product cannot "
            f"record: {', '.join(unavailable)}. The run did not exercise the "
            "governance layer enough to decide anything."
        ]

    rejection = measures["rejectionRate"]
    catches = measures["gateCatches"]
    gating_helped = (
        rejection["status"] == OK and (rejection["value"] or 0) < 0
    ) or (catches["status"] == OK and (catches["value"] or 0) > 0)

    failure = measures["changeFailureRate"]
    stability_ok = failure["status"] != OK or (failure["value"] or 0) <= 0

    if gating_helped and stability_ok:
        if rejection["status"] == OK and (rejection["value"] or 0) < 0:
            reasons.append(
                f"gating moved rejection rate by {rejection['value']:+.1%}."
            )
        if catches["status"] == OK and (catches["value"] or 0) > 0:
            reasons.append(
                f"gates blocked {catches['value']} change(s) the agents proposed."
            )
        reasons.append(
            "change failure rate is no worse than the baseline supplied."
            if failure["status"] == OK
            else "change failure rate could not be compared; treated as not worse."
        )
        reasons.append(
            "Provenance-query usage is NOT evidenced — §F2 requires it for GO, so "
            "confirm it out of band before starting F3."
        )
        return GO, reasons

    if not gating_helped:
        reasons.append(
            "gating neither reduced rejection rate nor caught changes the agents' "
            "own process missed — on this evidence the governance layer is ceremony."
        )
        return PIVOT if catches["status"] == OK else STOP, reasons + [
            "Ship the Flight Recorder as the product (§F2 STOP is a success, R29), "
            "or narrow to the analytics if those are what the team actually used."
        ]

    reasons.append(
        "gating helped, but change failure rate is worse than the supplied baseline: "
        "the layer is trading stability for scrutiny."
    )
    return STOP, reasons
