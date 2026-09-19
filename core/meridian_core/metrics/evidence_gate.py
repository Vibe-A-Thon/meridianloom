"""The evidence gate, applying the rule that was written before the data.

`docs/evidence-gate.md` is a preregistration: ten measures, their thresholds
and a decision rule, fixed on 12 September 2026 with no study data in
existence. This module is the instrument the study is scored with. Its one job
is to apply **that** rule, not a nearby rule and not a kinder one.

Until MV5 was prepared, it did not. The first version was written against the
earlier F2 sketch in `gaps_implementation.md`, and when the thresholds were
fixed the instrument was never brought into line. Against the preregistration
it:

* returned GO on a single unconfirmed gate block, where P1 needs three defects,
  each confirmed by a reviewer who did not run the gate;
* returned GO with change failure rate and provenance-query usage unmeasured
  ("treated as not worse", "confirm it out of band"), where §5 says an
  unmeasured threshold is recorded as unmeasured and never as satisfied;
* had no KILL path, and no P5, P6, C1, C2 or O1 at all;
* and, read against what the product actually writes, counted **nothing**. It
  looked for gate rows whose decision was `block`, but the Governor records a
  gate stop as `rejected`. It looked for an approval's subject on the row, but
  the subject lives in the encrypted detail. Its tests passed because their
  fixtures used the shapes the instrument expected rather than the shapes the
  product writes.

A study scored by an instrument with a lower bar than the one written in
advance is exactly the negotiation with oneself the preregistration exists to
prevent.

**Three states, three-valued logic.** Every measure is `met`, `not_met` or
`unmeasured`. The decision rule is walked in the order §4 writes it. A rule
whose outcome depends on an unmeasured threshold is *undecided*, and an
undecided rule stops the walk: a later outcome is never reached by skipping an
earlier one that might have applied. Where partial evidence already settles a
threshold (three confirmed defects are three, however many stops are still
unadjudicated), the measure is decided from the bound and the note says so.

**Readings.** Where the preregistration's words admit more than one reading,
the one that makes GO harder is applied, because §1 puts the burden of evidence
on the tier. Each reading is stated in `docs/evidence-gate.md` §6 and is part
of the digest, so changing one after the data exists is visible.

Zero model calls (FR-M36-07): arithmetic over ledger rows and a JSON record.
"""

from __future__ import annotations

import hashlib
import json
from statistics import median
from typing import Any, Callable

from ..rejection.detector import REASON_REVERTED
from .coverage import ATTACH_KEY, envelope_for, scan_scope
from .evidence_study import missing_recorded_fields, registered_after_data, validate_study
from .statistics import proportion_statistics

#: The preregistration this instrument applies.
PREREGISTRATION_DOCUMENT = "docs/evidence-gate.md"

#: §2: twenty stories. Fewer is not a smaller answer; it is no answer.
REQUIRED_STORIES = 20

MET = "met"
NOT_MET = "not_met"
UNMEASURED = "unmeasured"

GO = "go"
STOP = "stop"
PIVOT = "pivot"
KILL = "kill"
INSUFFICIENT = "insufficient_evidence"
#: A combination of results §4 names no outcome for. Reported, never rounded
#: to the nearest outcome.
UNCLASSIFIED = "unclassified"

#: §3, as the instrument applies it. Read by the measures below, never copied
#: into them, so the digest and the arithmetic cannot disagree.
THRESHOLDS: dict[str, dict[str, Any]] = {
    "P1": {
        "measure": "Defects uniquely caught",
        "atLeast": 3,
        "confirmedBy": "a reviewer who did not run the gate",
    },
    "P2": {
        "measure": "Rejection rate, arm C against arm A, split greenfield/brownfield",
        "rule": "lower in arm C",
    },
    "P3": {
        "measure": "Change failure rate for gated merges against the team's baseline",
        "rule": "no worse",
    },
    "P4": {
        "measure": "Provenance queries actually run",
        "atLeast": 1,
        "per": "engineer per week, sustained",
    },
    "P5": {"measure": "The Trust Observatory changes a decision", "atLeast": 1},
    "P6": {
        "measure": "First-value retention at week 8",
        "atLeast": 2,
        "ofOriginal": 5,
    },
    "C1": {
        "measure": "False blocks, reviewer-adjudicated",
        "atMostShare": 0.15,
        "of": "gate stops",
    },
    "C2": {
        "measure": "Median human review time per gated PR",
        "atMostRatio": 1.2,
        "against": "arm A",
    },
    "C3": {
        "measure": "Approval hygiene",
        "rule": "no evidence of systematic rubber-stamping",
    },
    "O1": {
        "measure": "A task class where the team's existing agents underperform",
        "rule": "named, with evidence, before any agent is built",
    },
}

#: The readings applied where §3 and §4 admit more than one. Each string
#: appears verbatim in `docs/evidence-gate.md` §6; a test holds them together.
READINGS: dict[str, str] = {
    "ambiguity": "Where a threshold admits more than one reading, the reading that makes GO harder is applied.",
    "P1": "A stop without an independent adjudication, or with independent adjudications that disagree, could still prove to be a defect, so P1 is not met only when the confirmed defects plus those stops cannot reach three.",
    "P2": "Every split present in arm C's allocation or in arm A's figures must be measured in both arms, and arm C must be lower in each.",
    "P3": "A reverted approval that cannot be attributed to an arm leaves P3 unmeasured, because it may be a gated merge that failed.",
    "P4": "Sustained means every engineer listed in every recorded week ran at least one provenance query.",
    "P6": "At least two testers retained, and at least two in five of the original testers.",
    "C1": "Gate stops that are unadjudicated or disputed are counted as false blocks for the upper bound; with no gate stops at all the share is undefined and C1 is unmeasured.",
    "C2": "Both arms are timed by the same human method; ledger timings are context and never the measure.",
    "C3": "A reviewer's recorded determination decides C3, with the ledger's hygiene signals attached as its evidence.",
    "O1": "Unmeasured is not satisfied, so STOP can rest on an O1 nobody argued.",
    "order": "Outcomes are tried in the written order GO, STOP, PIVOT, KILL, and an undecided outcome stops the walk.",
    "gap": "A combination of results that no outcome names is reported as unclassified.",
}

#: The measures each outcome's condition reads, for naming what blocks it.
_RULE_READS: dict[str, tuple[str, ...]] = {
    GO: ("P1", "P2", "P3", "P4", "P6", "C1", "C2", "C3", "O1"),
    STOP: ("P1", "P2", "P3", "P4", "P6", "C1", "C2", "C3", "O1"),
    PIVOT: ("P4", "P5"),
    KILL: ("P6", "P3", "C2", "P1", "P2"),
}


def thresholds_digest() -> str:
    """The digest a study registers before its first story (§5)."""
    canonical = json.dumps(
        {
            "requiredStories": REQUIRED_STORIES,
            "thresholds": THRESHOLDS,
            "readings": READINGS,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preregistration() -> dict[str, Any]:
    """What a study team registers: the digest, and what it is a digest of."""
    return {
        "document": PREREGISTRATION_DOCUMENT,
        "thresholdsDigest": thresholds_digest(),
        "requiredStories": REQUIRED_STORIES,
        "thresholds": THRESHOLDS,
        "readings": READINGS,
    }


# -- helpers -------------------------------------------------------------------


def _measure(
    measure_id: str,
    status: str,
    *,
    source: str,
    note: str,
    value: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": measure_id,
        "status": status,
        "value": value,
        "threshold": THRESHOLDS[measure_id],
        "source": source,
        "note": note,
        **extra,
    }


def _no_record(measure_id: str, what: str) -> dict[str, Any]:
    return _measure(
        measure_id,
        UNMEASURED,
        source="study record",
        note=f"no study record supplies {what}. Unmeasured is not satisfied.",
    )


def _detail(ledger: Any, row: dict[str, Any]) -> dict[str, Any]:
    """The encrypted detail the Governor recorded with a row."""
    ref, key_id = row.get("input_ref"), row.get("blob_key_id")
    reader = getattr(ledger, "read_blob", None)
    if not ref or not key_id or reader is None:
        return {}
    try:
        parsed = json.loads(reader(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_calls(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("tool_calls")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [call for call in raw if isinstance(call, dict)] if isinstance(raw, list) else []


def _truncated(measure_id: str, source: str) -> dict[str, Any]:
    return _measure(
        measure_id,
        UNMEASURED,
        source=source,
        note=(
            "the ledger scope was larger than could be read, so a count from it "
            "would be a floor presented as a total."
        ),
    )


# -- the measures ----------------------------------------------------------------


def _p1_and_c1(
    stops: list[dict[str, Any]],
    record: dict[str, Any] | None,
    complete: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = "ledger gate stops + study adjudications"
    if record is None or "adjudications" not in record:
        return (
            _no_record("P1", "reviewer adjudications of the gate stops"),
            _no_record("C1", "reviewer adjudications of the gate stops"),
        )
    if not complete:
        return _truncated("P1", source), _truncated("C1", source)

    stop_sequences = {int(row["seq"]) for row in stops}
    adjudications = record["adjudications"]
    refused = sorted(
        {a["gateSequence"] for a in adjudications if a["gateSequence"] not in stop_sequences}
    )
    valid = [a for a in adjudications if a["gateSequence"] in stop_sequences]
    by_stop: dict[int, list[dict[str, Any]]] = {}
    for adjudication in valid:
        by_stop.setdefault(adjudication["gateSequence"], []).append(adjudication)

    # P1 — confirmed only by reviewers who did not run the gate, and only when
    # every such reviewer of that stop agrees it was a defect the agent missed.
    confirmed: set[int] = set()
    possible: set[int] = set()
    for sequence in stop_sequences:
        independent = [a for a in by_stop.get(sequence, []) if not a["reviewerRanGate"]]
        verdicts = {a["realDefect"] and not a["caughtByAgentProcess"] for a in independent}
        if verdicts == {True}:
            confirmed.add(sequence)
        elif not independent or verdicts == {True, False}:
            possible.add(sequence)
    floor = int(THRESHOLDS["P1"]["atLeast"])
    p1_extra = {
        "gateStops": len(stop_sequences),
        "confirmed": len(confirmed),
        "undecidedStops": len(possible),
        "refusedAdjudications": refused,
    }
    refused_note = (
        f" {len(refused)} adjudication(s) named a sequence that is not a gate stop "
        "in this scope and were not counted." if refused else ""
    )
    if len(confirmed) >= floor:
        p1 = _measure(
            "P1", MET, source=source, value=len(confirmed),
            note=f"{len(confirmed)} defects confirmed by reviewers who did not run the gate." + refused_note,
            **p1_extra,
        )
    elif len(confirmed) + len(possible) < floor:
        p1 = _measure(
            "P1", NOT_MET, source=source, value=len(confirmed),
            note=(
                f"{len(confirmed)} confirmed, and even if all {len(possible)} undecided "
                f"stop(s) proved to be defects the total could not reach {floor}."
            ) + refused_note,
            **p1_extra,
        )
    else:
        p1 = _measure(
            "P1", UNMEASURED, source=source, value=len(confirmed),
            note=(
                f"{len(confirmed)} confirmed and {len(possible)} stop(s) without a settled "
                f"independent adjudication; they decide whether {floor} is reached."
            ) + refused_note,
            **p1_extra,
        )

    # C1 — any reviewer may adjudicate; the share is bounded when some are open.
    ceiling = float(THRESHOLDS["C1"]["atMostShare"])
    total = len(stop_sequences)
    if total == 0:
        return p1, _measure(
            "C1", UNMEASURED, source=source,
            note="no gate stopped a change in arm C, so a false-block share is undefined.",
            gateStops=0,
        )
    false_blocks = sum(
        1 for s in stop_sequences
        if by_stop.get(s) and {a["realDefect"] for a in by_stop[s]} == {False}
    )
    real_blocks = sum(
        1 for s in stop_sequences
        if by_stop.get(s) and {a["realDefect"] for a in by_stop[s]} == {True}
    )
    unsettled = total - false_blocks - real_blocks
    low = round(false_blocks / total, 6)
    high = round((false_blocks + unsettled) / total, 6)
    c1_extra = {
        "gateStops": total,
        "falseBlocks": false_blocks,
        "unsettled": unsettled,
        "bounds": [low, high],
        "statistics": proportion_statistics(false_blocks, total - unsettled, missing=unsettled, available=total),
    }
    if high <= ceiling:
        c1 = _measure("C1", MET, source=source, value=low,
                      note=f"at most {high:.0%} of {total} gate stops were false blocks.", **c1_extra)
    elif low > ceiling:
        c1 = _measure("C1", NOT_MET, source=source, value=low,
                      note=f"at least {low:.0%} of {total} gate stops were false blocks.", **c1_extra)
    else:
        c1 = _measure("C1", UNMEASURED, source=source, value=low,
                      note=(
                          f"between {low:.0%} and {high:.0%} of {total} gate stops were false "
                          f"blocks; the {unsettled} unsettled stop(s) decide which side of "
                          f"{ceiling:.0%} it falls."
                      ), **c1_extra)
    return p1, c1


def _p2(
    rows: list[dict[str, Any]],
    record: dict[str, Any] | None,
    arm_c_kinds: dict[str, str],
    complete: bool,
) -> dict[str, Any]:
    source = "ledger (arm C) + study record (arm A)"
    if record is None or "armA" not in record:
        return _no_record("P2", "arm A's rejection rate")
    if not complete:
        return _truncated("P2", source)

    arm_a = record["armA"]["rejectionRate"]
    rejected_sequences = {
        row.get("rejected_sequence") for row in rows
        if row.get("action_type") == "rejection" and row.get("rejected_sequence") is not None
    }
    splits = sorted(set(arm_c_kinds.values()) | set(arm_a))
    if not splits:
        return _measure("P2", UNMEASURED, source=source,
                        note="neither arm recorded a greenfield or brownfield story.")

    results: dict[str, Any] = {}
    reduced: list[bool | None] = []
    for split in splits:
        stories = {story for story, kind in arm_c_kinds.items() if kind == split}
        proposed = [
            row for row in rows
            if row.get("action_type") == "diff" and str(row.get("story_id")) in stories
        ]
        rejected = [
            row for row in proposed
            if row.get("seq") in rejected_sequences
            or row.get("decision") in ("rejected", "reworked")
        ]
        baseline = arm_a.get(split)
        c_rate = len(rejected) / len(proposed) if proposed else None
        a_rate = baseline["rejected"] / baseline["proposed"] if baseline and baseline["proposed"] else None
        comparable = c_rate is not None and a_rate is not None
        results[split] = {
            "armC": {
                "rejected": len(rejected),
                "proposed": len(proposed),
                "rate": round(c_rate, 6) if c_rate is not None else None,
                "statistics": proportion_statistics(len(rejected), len(proposed)),
            },
            "armA": {
                "rejected": baseline["rejected"] if baseline else None,
                "proposed": baseline["proposed"] if baseline else None,
                "rate": round(a_rate, 6) if a_rate is not None else None,
                "statistics": proportion_statistics(baseline["rejected"], baseline["proposed"])
                if baseline else None,
            },
            "comparable": comparable,
            "reduced": (c_rate < a_rate) if comparable else None,
        }
        reduced.append(results[split]["reduced"])

    if any(value is False for value in reduced):
        worse = [split for split, r in results.items() if r["reduced"] is False]
        return _measure("P2", NOT_MET, source=source, splits=results,
                        note=f"arm C did not reject less than arm A in: {', '.join(worse)}.")
    if all(value is True for value in reduced):
        return _measure("P2", MET, source=source, splits=results,
                        note=f"arm C rejected less than arm A in every split: {', '.join(splits)}.")
    missing = [split for split, r in results.items() if not r["comparable"]]
    return _measure("P2", UNMEASURED, source=source, splits=results,
                    note=f"not measured in both arms: {', '.join(missing)}.")


def _p3(
    ledger: Any,
    rows: list[dict[str, Any]],
    record: dict[str, Any] | None,
    arm_of: dict[str, str],
    supplied_baseline: float | None,
    complete: bool,
) -> dict[str, Any]:
    source = "ledger approvals and reverts + team baseline"
    if record and record.get("baselineChangeFailureRate"):
        baseline: float | None = float(record["baselineChangeFailureRate"]["rate"])
    else:
        baseline = supplied_baseline
    if not complete:
        return _truncated("P3", source)

    reverted_commits = {
        row.get("rejected_commit") for row in rows
        if row.get("action_type") == "rejection"
        and row.get("rejected_commit")
        and any(call.get("shape") == REASON_REVERTED for call in _tool_calls(row))
    }
    gated: list[str] = []
    unattributed_failed = 0
    unattributed = 0
    for row in rows:
        if row.get("action_type") != "approval" or row.get("decision") != "approved":
            continue
        commit = _detail(ledger, row).get("commit")
        if not commit:
            continue
        story = str(row.get("story_id"))
        if record is None or arm_of.get(story) == "C":
            gated.append(commit)
        elif story not in arm_of:
            unattributed += 1
            unattributed_failed += int(commit in reverted_commits)
    failed = sum(1 for commit in gated if commit in reverted_commits)
    extra = {
        "gatedMerges": len(gated),
        "reverted": failed,
        "unattributedApprovals": unattributed,
        "baseline": baseline,
        "statistics": proportion_statistics(failed, len(gated)),
    }
    if unattributed_failed:
        return _measure("P3", UNMEASURED, source=source, **extra,
                        note=(
                            f"{unattributed_failed} reverted approval(s) are not allocated to "
                            "any arm and may be gated merges that failed. Allocate their "
                            "stories to decide P3."
                        ))
    if not gated:
        return _measure("P3", UNMEASURED, source=source, **extra,
                        note="no approved merge in arm C, so there is no failure rate to compare.")
    observed = round(failed / len(gated), 6)
    if baseline is None:
        return _measure("P3", UNMEASURED, source=source, value=observed, **extra,
                        note=(
                            f"gated change failure rate is {observed:.1%}, but no team baseline "
                            "was supplied. The ledger cannot know this team's rate before Meridian."
                        ))
    status = MET if observed <= baseline else NOT_MET
    return _measure("P3", status, source=source, value=observed, **extra,
                    note=f"gated {observed:.1%} against the team's {baseline:.1%}.")


def _p4(record: dict[str, Any] | None) -> dict[str, Any]:
    source = "study record"
    if record is None or "provenanceQueries" not in record:
        return _measure(
            "P4", UNMEASURED, source=source,
            note=(
                "Meridian does not count what people read, by design: counting reads "
                "is a product decision with a privacy cost. The study team records "
                "queries run. Unmeasured is not satisfied."
            ),
        )
    weeks = record["provenanceQueries"]["weeks"]
    floor = int(THRESHOLDS["P4"]["atLeast"])
    entries = [(w["week"], e["engineer"], e["queries"]) for w in weeks for e in w["engineers"]]
    if not entries:
        return _measure("P4", UNMEASURED, source=source,
                        note="the record lists no engineer in any week.")
    short = [f"week {week}: {who}" for week, who, queries in entries if queries < floor]
    extra = {"weeks": len(weeks), "engineerWeeks": len(entries)}
    if short:
        return _measure("P4", NOT_MET, source=source, value=len(short), **extra,
                        note=f"below {floor} provenance query in {len(short)} engineer-week(s): "
                        + ", ".join(short[:10]))
    return _measure("P4", MET, source=source, value=0, **extra,
                    note=f"every engineer ran at least {floor} query in each of {len(weeks)} week(s).")


def _p5(record: dict[str, Any] | None, sequences: set[int]) -> dict[str, Any]:
    source = "study record"
    if record is None or "trustDecisionChanges" not in record:
        return _no_record("P5", "decisions changed after viewing the Trust Observatory")
    instances = record["trustDecisionChanges"]["instances"]
    refused = [i for i in instances if "ledgerSequence" in i and i["ledgerSequence"] not in sequences]
    counted = [i for i in instances if i not in refused]
    floor = int(THRESHOLDS["P5"]["atLeast"])
    note = f"{len(counted)} recorded decision change(s)."
    if refused:
        note += f" {len(refused)} named a ledger entry outside this scope and were not counted."
    return _measure("P5", MET if len(counted) >= floor else NOT_MET, source=source,
                    value=len(counted), note=note, refused=len(refused))


def _p6(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None or "retention" not in record:
        return _no_record("P6", "week-8 retention, which only asking the testers can answer")
    retention = record["retention"]
    kept, original = retention["stillUsingAtWeek8"], retention["originalTesters"]
    floor, of = int(THRESHOLDS["P6"]["atLeast"]), int(THRESHOLDS["P6"]["ofOriginal"])
    met = kept >= floor and kept * of >= floor * original
    note = f"{kept} of {original} original testers still using it at week 8."
    if original != of:
        note += f" The threshold names {of} testers; {original} were recorded."
    return _measure("P6", MET if met else NOT_MET, source="study record", value=kept, note=note)


def _c2(
    record: dict[str, Any] | None,
    latency_proxy: dict[str, Any],
) -> dict[str, Any]:
    if record is None or "reviewTime" not in record:
        return _measure(
            "C2", UNMEASURED, source="study record",
            note="no study record supplies human review times for both arms.",
            ledgerLatencyProxy=latency_proxy,
        )
    times = record["reviewTime"]
    if not times["armA"] or not times["armC"]:
        return _measure("C2", UNMEASURED, source="study record", ledgerLatencyProxy=latency_proxy,
                        note="review times are needed for both arms.")
    a, c = median(times["armA"]), median(times["armC"])
    if a == 0:
        return _measure("C2", UNMEASURED, source="study record", ledgerLatencyProxy=latency_proxy,
                        note="arm A's median review time is zero, so a ratio is undefined.")
    ratio = round(c / a, 6)
    ceiling = float(THRESHOLDS["C2"]["atMostRatio"])
    return _measure(
        "C2", MET if ratio <= ceiling else NOT_MET, source="study record", value=ratio,
        note=f"median {c:g} minutes in arm C against {a:g} in arm A ({ratio - 1:+.0%}).",
        medianMinutes={"armA": a, "armC": c},
        ledgerLatencyProxy=latency_proxy,
    )


def _c3(record: dict[str, Any] | None, signals: dict[str, Any]) -> dict[str, Any]:
    source = "study determination + ledger hygiene signals"
    if record is None or "hygieneDetermination" not in record:
        return _measure("C3", UNMEASURED, source=source, ledgerSignals=signals,
                        note="no reviewer's determination on rubber-stamping is recorded.")
    determination = record["hygieneDetermination"]
    systematic = determination["systematicRubberStamping"]
    note = (
        "a reviewer found systematic rubber-stamping." if systematic
        else "a reviewer found no systematic rubber-stamping."
    )
    if not signals.get("assessed"):
        note += " The ledger's hygiene signals were not available to attach."
    return _measure("C3", NOT_MET if systematic else MET, source=source,
                    note=note, basis=determination["basis"], ledgerSignals=signals)


def _o1(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None or "orchestraCase" not in record:
        return _no_record("O1", "a named task class where the team's agents underperform")
    case = record["orchestraCase"]
    if case["determination"] == "satisfied":
        return _measure("O1", MET, source="study record", value=case.get("taskClass"),
                        note=f"named: {case.get('taskClass')}.", evidence=case.get("evidence"))
    return _measure("O1", NOT_MET, source="study record",
                    note="no task class was found where a Meridian agent would plausibly do better.")


def score_first_value(record: dict[str, Any] | None) -> dict[str, Any]:
    """FR-M46-04 (MVP-R5.3). Not part of §4's rule; published beside it."""
    section = (record or {}).get("firstValue") or {}

    sessions = section.get("sessions")
    if not sessions:
        onboarding = {"status": UNMEASURED, "note": "no onboarding session is recorded."}
    elif len(sessions) != 5:
        onboarding = {
            "status": UNMEASURED,
            "note": f"the requirement names five sessions; {len(sessions)} are recorded.",
        }
    else:
        within = sum(
            1 for s in sessions
            if s["minutesToFirstAnswer"] is not None and s["minutesToFirstAnswer"] <= 15
        )
        onboarding = {
            "status": MET if within >= 4 else NOT_MET,
            "value": within,
            "note": f"{within} of 5 reached a first provenance answer within 15 minutes.",
        }

    tasks = section.get("reviewTasks")
    if not tasks:
        review = {"status": UNMEASURED, "note": "no review task is recorded."}
    elif len(tasks) != 10:
        review = {
            "status": UNMEASURED,
            "note": f"the requirement names ten review tasks; {len(tasks)} are recorded.",
        }
    else:
        right = sum(1 for t in tasks if t["identifiedRealBlockingRisk"])
        review = {
            "status": MET if right >= 8 else NOT_MET,
            "value": right,
            "note": f"{right} of 10 identified the real blocking risk.",
        }
    return {"requirement": "FR-M46-04", "onboarding": onboarding, "reviewTasks": review}


# -- the rule --------------------------------------------------------------------


def _all(*values: bool | None) -> bool | None:
    if any(value is False for value in values):
        return False
    if any(value is None for value in values):
        return None
    return True


def _any(*values: bool | None) -> bool | None:
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


def decide(
    story_count: int,
    measures: dict[str, dict[str, Any]],
    *,
    study_problem: str | None = None,
) -> dict[str, Any]:
    """§4, walked in order over three-valued logic."""
    if study_problem:
        return {"verdict": INSUFFICIENT, "reasons": [study_problem]}
    if story_count < REQUIRED_STORIES:
        return {
            "verdict": INSUFFICIENT,
            "reasons": [
                f"{story_count} of {REQUIRED_STORIES} stories. The gate is defined over "
                "twenty; fewer is not a smaller answer, it is no answer."
            ],
        }

    def status(measure_id: str) -> str:
        return measures[measure_id]["status"]

    def met(measure_id: str) -> bool | None:
        return None if status(measure_id) == UNMEASURED else status(measure_id) == MET

    def failed(measure_id: str) -> bool | None:
        return None if status(measure_id) == UNMEASURED else status(measure_id) == NOT_MET

    governance = _all(
        met("P3"), met("P4"), met("P6"), _any(met("P1"), met("P2")),
        met("C1"), met("C2"), met("C3"),
    )
    o1_met = status("O1") == MET
    rules: list[tuple[str, bool | None]] = [
        (GO, _all(governance, o1_met)),
        (STOP, _all(governance, not o1_met)),
        (PIVOT, _all(failed("P4"), met("P5"))),
        (KILL, _any(failed("P6"), failed("P3"), _all(failed("C2"), failed("P1"), failed("P2")))),
    ]

    for outcome, holds in rules:
        if holds is False:
            continue
        if holds is None:
            blocked = [m for m in _RULE_READS[outcome] if status(m) == UNMEASURED]
            return {
                "verdict": INSUFFICIENT,
                "undecidedOutcome": outcome,
                "unmeasured": blocked,
                "reasons": [
                    f"§4 tries its outcomes in order, and {outcome.upper()} can be neither "
                    f"ruled in nor ruled out: {', '.join(blocked)} unmeasured. A later "
                    "outcome is never reached by skipping one that might apply."
                ],
            }
        return {"verdict": outcome, "reasons": _reasons(outcome, measures)}

    return {
        "verdict": UNCLASSIFIED,
        "reasons": [
            "no outcome in §4 names this combination of results. It is reported as it "
            "is, not assigned to the nearest outcome; §5 forbids amending the rule now "
            "that the data exists, so the published result says so."
        ],
    }


def _reasons(outcome: str, measures: dict[str, dict[str, Any]]) -> list[str]:
    def said(measure_id: str) -> str:
        m = measures[measure_id]
        return f"{measure_id} {m['status'].replace('_', ' ')}: {m['note']}"

    if outcome == GO:
        return [said(m) for m in ("P1", "P2", "P3", "P4", "P6", "C1", "C2", "C3", "O1")]
    if outcome == STOP:
        return [
            "the governance thresholds hold, and O1 is "
            f"{measures['O1']['status'].replace('_', ' ')}. Ship the Flight Recorder and "
            "Governor as the product. This is a success (R29).",
            said("O1"),
        ]
    if outcome == PIVOT:
        return [
            "nobody queries provenance, but the trust instruments change decisions. "
            "Drop the gating, keep the measurement.",
            said("P4"),
            said("P5"),
        ]
    return [
        "the layer costs more than it returns.",
        *(said(m) for m in ("P6", "P3", "C2", "P1", "P2") if measures[m]["status"] == NOT_MET),
    ]


# -- the report ------------------------------------------------------------------


def compute_evidence_gate(
    ledger: Any,
    *,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    study: dict[str, Any] | None = None,
    baseline_change_failure_rate: float | None = None,
    hygiene: Callable[[str], list[str]] | None = None,
) -> dict[str, Any]:
    """The preregistered gate over a ledger scope and a study record.

    ``study`` is the record `evidence_study` defines. Without one, every
    measure that needs people reads unmeasured, and the verdict is
    insufficient_evidence. ``baseline_change_failure_rate`` is the one human
    figure the editor screen can supply on its own. ``hygiene`` maps an
    approval's subject to FR-M20-06 warnings, attached to C3 as evidence.
    """
    rows, rows_available = scan_scope(
        ledger, from_sequence=from_sequence, to_sequence=to_sequence
    )
    complete = len(rows) >= rows_available
    sequences = {int(row["seq"]) for row in rows if row.get("seq") is not None}

    study_problems = validate_study(study) if study is not None else []
    record = study if study is not None and not study_problems else None

    excluded = {e["storyId"] for e in (record or {}).get("exclusions", [])}
    allocation = [e for e in (record or {}).get("allocation", []) if e["storyId"] not in excluded]
    arm_of = {e["storyId"]: e["arm"] for e in allocation}
    arm_c_kinds = {e["storyId"]: e["kind"] for e in allocation if e["arm"] == "C"}
    ledger_stories = {str(row.get("story_id")) for row in rows if row.get("story_id")}

    # A story allocated to the Governor's arm with no rows in scope went through
    # nothing. Arm B runs with the Governor off, in its own workspace, so its
    # rows are in a different ledger: its slice is exported and attached
    # separately, and this ledger cannot say whether those stories were worked.
    missing_from_ledger = sorted(
        e["storyId"] for e in allocation if e["arm"] == "C" and e["storyId"] not in ledger_stories
    )
    if record is not None:
        story_count = len(allocation) - len(missing_from_ledger)
    else:
        story_count = len(ledger_stories)

    gates = [row for row in rows if row.get("action_type") == "gate"]
    stops = [
        row for row in gates
        if row.get("decision") == "rejected"
        and (record is None or arm_of.get(str(row.get("story_id"))) == "C")
    ]

    # Context: ledger facts shown beside the measures, never deciding them.
    approvals = [
        row for row in rows
        if row.get("action_type") == "approval" and row.get("decision") == "approved"
    ]
    subjects = sorted(
        {str(_detail(ledger, row).get("subject")) for row in approvals if _detail(ledger, row).get("subject")}
    )
    if hygiene is None:
        signals: dict[str, Any] = {"assessed": False, "approvals": len(approvals)}
    else:
        warnings = [warning for subject in subjects for warning in hygiene(subject)]
        signals = {
            "assessed": True,
            "approvals": len(approvals),
            "subjects": subjects,
            "warnings": warnings[:50],
        }
    from .dora import _parse_ts  # the canonical ISO parse, shared

    opened: dict[str, Any] = {}
    for row in gates:
        stamp = _parse_ts(row.get("ts_utc"))
        opened.setdefault(str(row.get("story_id")), stamp)
    waits = [
        (stamp - opened[story]).total_seconds()
        for row in approvals
        if (story := str(row.get("story_id"))) in opened
        and (stamp := _parse_ts(row.get("ts_utc"))) is not None
        and opened[story] is not None
        and stamp > opened[story]
    ]
    latency_proxy = {
        "what": "seconds from a gate evaluation to an approval on the same story",
        "samples": len(waits),
        "medianSeconds": round(median(waits), 3) if waits else None,
        "usedForC2": False,
    }

    p1, c1 = _p1_and_c1(stops, record, complete)
    measures = {
        "P1": p1,
        "P2": _p2(rows, record, arm_c_kinds, complete),
        "P3": _p3(ledger, rows, record, arm_of, baseline_change_failure_rate, complete),
        "P4": _p4(record),
        "P5": _p5(record, sequences),
        "P6": _p6(record),
        "C1": c1,
        "C2": _c2(record, latency_proxy),
        "C3": _c3(record, signals),
        "O1": _o1(record),
    }

    # §5: a threshold changed after data invalidates the preregistration, and
    # the published result must say so. The verdict is still computed.
    current = thresholds_digest()
    if record is None:
        state, invalidated = "not_registered", False
    elif record["preregistration"]["thresholdsDigest"] != current:
        state, invalidated = "digest_mismatch", True
    elif registered_after_data(record):
        state, invalidated = "registered_after_data", True
    else:
        state, invalidated = "intact", False

    if study is None:
        study_problem = (
            "no study record. Nine of the ten measures need people to supply them; "
            "run `python -m meridian_core.cli evidence-gate --study <record>`."
        )
    elif study_problems:
        study_problem = f"the study record does not validate: {study_problems[0]}"
    else:
        study_problem = None

    recommendation = decide(story_count, measures, study_problem=study_problem)
    if invalidated:
        recommendation["reasons"].insert(
            0,
            {
                "digest_mismatch": (
                    "The preregistration is not intact: the thresholds this instrument "
                    "applies are not the ones this study registered. If they were amended "
                    "before the first story, register again; if after, §5 says this result "
                    "must be published as invalidated."
                ),
                "registered_after_data": (
                    "The preregistration is not intact: it was registered after the first "
                    "story was measured. §5 says this result must be published as invalidated."
                ),
            }[state],
        )
    recommendation["invalidated"] = invalidated

    return {
        "preregistration": {
            "document": PREREGISTRATION_DOCUMENT,
            "thresholdsDigest": current,
            "registeredDigest": (record or {}).get("preregistration", {}).get("thresholdsDigest"),
            "state": state,
            "invalidated": invalidated,
        },
        "scope": {
            "fromSequence": from_sequence,
            "toSequence": to_sequence,
            "baselineChangeFailureRate": baseline_change_failure_rate,
        },
        "study": {
            "supplied": study is not None,
            "valid": study is not None and not study_problems,
            "problems": study_problems,
            "studyId": (record or {}).get("studyId"),
            "missingRecordedFields": missing_recorded_fields(record),
            "exclusions": (record or {}).get("exclusions", []),
        },
        "stories": {
            "total": story_count,
            "required": REQUIRED_STORIES,
            "byArm": {arm: sum(1 for a in arm_of.values() if a == arm) for arm in ("A", "B", "C")},
            "allocatedButAbsentFromLedger": missing_from_ledger,
            "inLedger": len(ledger_stories),
            "ids": sorted(arm_of or ledger_stories)[:200],
        },
        "measures": measures,
        "context": {
            "gateEvaluations": len(gates),
            "gateStops": len(stops),
            "hygieneSignals": signals,
            "reviewLatencyProxy": latency_proxy,
        },
        "firstValue": score_first_value(record),
        "recommendation": recommendation,
        ATTACH_KEY: envelope_for(None, rows, rows_available).to_dict(),
    }
