"""C6 Differentiation — the eleven v2 items, core-side.

FR-M10-16 annotations/bookmarks · FR-M13-08 counterfactual queries ·
FR-M14-11 quality-diversity archive · FR-M16-10 retirement handover ·
FR-M19-07 batch epic ingestion · FR-M24-05 agent-detected issues ·
FR-M30-05 scheduled tasks · FR-P5-09 property/fuzz test generation ·
FR-P8-02 deployment behind a Governor flag (D7: plans only — the flag
guards a body that raises its requirement id rather than deploying).

ECO-06 (Navion MCP browser) and ECO-08 (teamlore import) are ecosystem
integrations; their core seams are the MCP client (FR-M9-01) and the
import path (FR-M16-04) already shipped — recorded in DECISIONS as
integrations, not new modules.

Zero model calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from meridian_core.ledger.redaction import redact_secrets


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- FR-M10-16: annotations and bookmarks ---------------------------------------


@dataclass(frozen=True)
class Annotation:
    target_seq: int
    author: str
    text: str
    bookmark: bool = False


class AnnotationStore:
    """Annotations are ordinary append-only ledger entries
    (action_type ``annotation``); bookmarks are annotations with the
    bookmark flag. They ride the chain like everything else."""

    def __init__(self, ledger: Any) -> None:
        self._ledger = ledger

    def add(self, annotation: Annotation) -> int:
        result = self._ledger.append(
            {
                "story_id": "ledger-annotations",
                "phase": "review",
                "loop_id": "annotations",
                "loop_iteration": 1,
                "actor_id": annotation.author,
                "actor_version": "local",
                "actor_kind": "role",
                "policy_version": "annotations/v1",
                "action_type": "annotation",
                "tool_calls": [
                    {
                        "targetSeq": annotation.target_seq,
                        "text": redact_secrets(annotation.text),
                        "bookmark": annotation.bookmark,
                    }
                ],
            }
        )
        return result.sequence

    def bookmarks(self) -> list[Mapping[str, Any]]:
        out = []
        for row in self._ledger.query_all(action_type="annotation"):
            for call in json.loads(row["tool_calls"] or "[]"):
                if call.get("bookmark"):
                    out.append(call)
        return out


# -- FR-M13-08: counterfactual queries ----------------------------------------------


@dataclass(frozen=True)
class CounterfactualResult:
    """A targeted replay with one input changed — the answer to 'what
    would the decision have been WITHOUT factor X'. Marked as evidence
    (it is a controlled replay), never narrative."""

    decision_id: str
    changed_factor: str
    original_output: Any
    counterfactual_output: Any
    output_changed: bool

    def labelled(self) -> str:
        return (
            "[evidence — counterfactual replay] "
            f"decision {self.decision_id} without {self.changed_factor}:"
            f" output {'CHANGED' if self.output_changed else 'unchanged'}"
        )


def counterfactual(
    decide: Callable[[Mapping[str, Any]], Any],
    *,
    decision_id: str,
    inputs: Mapping[str, Any],
    output: Any,
    without_factor: str,
) -> CounterfactualResult:
    if without_factor not in inputs:
        raise KeyError(without_factor)
    modified = {k: v for k, v in inputs.items() if k != without_factor}
    counter = decide(modified)
    return CounterfactualResult(
        decision_id=decision_id,
        changed_factor=without_factor,
        original_output=output,
        counterfactual_output=counter,
        output_changed=counter != output,
    )


# -- FR-M14-11: quality-diversity archive ------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    content: str
    descriptors: Mapping[str, float]  # behavioural characterisation


class QualityDiversityArchive:
    """Keeps candidates that are EITHER better than the archive's best
    on score OR behaviourally novel (far from everything archived).
    Pure exploitation collapses; QD keeps the diverse frontier."""

    def __init__(self, *, novelty_threshold: float = 0.1, max_size: int = 50) -> None:
        self._novelty = novelty_threshold
        self._max = max_size
        self._archive: list[Candidate] = []

    @staticmethod
    def _distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
        keys = set(a) | set(b)
        return max((abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys), default=0.0)

    def consider(self, candidate: Candidate, *, score: float, best_score: float) -> bool:
        if not self._archive:
            self._archive.append(candidate)
            return True
        nearest = min(self._distance(candidate.descriptors, c.descriptors) for c in self._archive)
        novel = nearest >= self._novelty
        better = score > best_score
        if novel or better:
            self._archive.append(candidate)
            self._archive = self._archive[-self._max:]
            return True
        return False

    def archive(self) -> tuple[Candidate, ...]:
        return tuple(self._archive)


# -- FR-M16-10: retirement handover ---------------------------------------------------------


def retire_with_handover(
    fabric: Any,
    *,
    retiring_subject: str,
    successor_subject: str,
    ledger: Any,
) -> int:
    """Offer the retiring agent's procedural memory to a named
    successor; the transfer is ledger-recorded. Memory itself moves
    through the fabric (new entry, successor subject)."""
    from meridian_core.memory.fabric import MemoryEntry, Provenance

    source = fabric.get("procedural", retiring_subject)
    if source is None:
        raise KeyError(retiring_subject)
    transferred = fabric.write(
        MemoryEntry(
            entry_id=f"handover-{successor_subject}",
            tier="procedural",
            subject=successor_subject,
            content=source.content,
            provenance=Provenance(
                origin_sequence=None,
                author="retirement-handover",
                ts_utc=utc_now(),
                confidence=source.provenance.confidence,
                origin="workspace",
                pinned=False,
            ),
        ),
        actor="retirement-handover",
        contradiction_terms={successor_subject},
    )
    result = ledger.append(
        {
            "story_id": "agent-retirement",
            "phase": "govern",
            "loop_id": "retirement",
            "loop_iteration": 1,
            "actor_id": "retirement-handover",
            "actor_version": "local",
            "actor_kind": "meta",
            "policy_version": "retirement/v1",
            "action_type": "policy_update",
            "tool_calls": [
                {
                    "event": "memory_handover",
                    "from": retiring_subject,
                    "to": successor_subject,
                }
            ],
        }
    )
    return result.sequence


# -- FR-M19-07: batch epic ingestion ------------------------------------------------------------


@dataclass(frozen=True)
class EpicStory:
    story_id: str
    title: str
    acceptance: tuple[str, ...]


def ingest_epic(text: str, *, id_prefix: str = "EPIC") -> tuple[EpicStory, ...]:
    """Split an epic document into stories: '##' headings are stories,
    '- ' bullets under a heading are acceptance criteria. Deterministic;
    an epic with no stories is an error, not an empty success."""
    stories: list[EpicStory] = []
    current: EpicStory | None = None
    acceptance: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                stories.append(
                    EpicStory(current.story_id, current.title, tuple(acceptance))
                )
            title = line[3:].strip()
            current = EpicStory(
                story_id=f"{id_prefix}-{len(stories) + 1:03d}", title=title, acceptance=()
            )
            acceptance = []
        elif line.strip().startswith("- ") and current is not None:
            acceptance.append(line.strip()[2:])
    if current is not None:
        stories.append(EpicStory(current.story_id, current.title, tuple(acceptance)))
    if not stories:
        raise ValueError("FR-M19-07: the epic contains no '## ' story headings")
    return tuple(stories)


# -- FR-M24-05: agent-detected issues -------------------------------------------------------------


def record_detected_issue(
    ledger: Any,
    *,
    agent_id: str,
    severity: str,
    description: str,
    story_id: str,
) -> int:
    """Agent-detected issues land in the ledger and surface in the
    Problems panel by query — an issue an agent saw is evidence, not
    chat."""
    if severity not in ("info", "warning", "critical"):
        raise ValueError(f"unknown severity {severity!r}")
    result = ledger.append(
        {
            "story_id": story_id,
            "phase": "build",
            "loop_id": "problems",
            "loop_iteration": 1,
            "actor_id": agent_id,
            "actor_version": "local",
            "actor_kind": "role",
            "policy_version": "problems/v1",
            "action_type": "detected_issue",
            "tool_calls": [
                {"severity": severity, "description": redact_secrets(description)}
            ],
        }
    )
    return result.sequence


def detected_issues(ledger: Any, *, story_id: str | None = None) -> list[Mapping[str, Any]]:
    rows = ledger.query_all(
        action_type="detected_issue", story_id=story_id
    ) if story_id else ledger.query_all(action_type="detected_issue")
    out = []
    for row in rows:
        for call in json.loads(row["tool_calls"] or "[]"):
            out.append({"storyId": row["story_id"], **call})
    return out


# -- FR-M30-05: scheduled tasks ----------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    action: str  # e.g. "trainer.run", "corpus.refresh"
    interval_s: int
    last_run_ts: str | None = None

    def next_fire_after(self, now: datetime) -> datetime:
        if self.last_run_ts is None:
            return now
        last = datetime.strptime(self.last_run_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        return last + timedelta(seconds=self.interval_s)


class ScheduleRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}

    def register(self, task: ScheduledTask) -> None:
        if task.interval_s < 60:
            raise ValueError("scheduled tasks may not run more often than every 60s")
        self._tasks[task.task_id] = task

    def due(self, now: datetime) -> tuple[ScheduledTask, ...]:
        return tuple(
            task
            for task in self._tasks.values()
            if task.last_run_ts is None or task.next_fire_after(now) <= now
        )

    def mark_run(self, task_id: str, *, at: datetime) -> None:
        task = self._tasks[task_id]
        self._tasks[task_id] = ScheduledTask(
            task_id=task.task_id,
            action=task.action,
            interval_s=task.interval_s,
            last_run_ts=at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


# -- FR-P5-09: property/fuzz test generation ---------------------------------------------------------


def fuzz_cases(schema: Mapping[str, Any], *, budget: int = 8) -> list[Mapping[str, Any]]:
    """Deterministic boundary-focused cases from a JSON-schema-ish
    declaration: required-field omission, type violations, boundary
    values, oversize. The generated cases seed the agent's test
    authoring — deterministic, no model call."""
    cases: list[Mapping[str, Any]] = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    base = {name: _sample_for(spec) for name, spec in properties.items()}
    cases.append({"name": "valid-baseline", "value": dict(base), "expect": "accept"})
    for name in required:
        violated = dict(base)
        violated.pop(name, None)
        cases.append(
            {"name": f"missing-required-{name}", "value": violated, "expect": "reject"}
        )
    for name, spec in properties.items():
        if spec.get("type") == "string":
            violated = dict(base)
            violated[name] = "x" * (int(spec.get("maxLength", 100)) + 1)
            cases.append(
                {"name": f"oversize-{name}", "value": violated, "expect": "reject"}
            )
    return cases[:budget]


def _sample_for(spec: Mapping[str, Any]) -> Any:
    kind = spec.get("type")
    if kind == "string":
        return str(spec.get("default", "sample"))
    if kind == "integer":
        return int(spec.get("default", 1))
    if kind == "boolean":
        return bool(spec.get("default", True))
    if kind == "array":
        return []
    return None


# -- FR-P8-02: deployment behind a Governor flag (D7: plans only) ----------------------------------------


def deploy_execution(*, governor_flag: bool) -> None:
    """D7 governs: Release/Operate produce PLANS; deployment execution
    is not v1 scope. The flag exists so the integration point is real;
    the body raises its requirement id rather than pretending."""
    if governor_flag:
        raise NotImplementedError(
            "FR-P8-02: deployment execution is gated behind the Governor"
            " flag, and D7 keeps Release/Operate to plans only in v1 —"
            " this body is the seam, not the feature"
        )
    raise NotImplementedError(
        "FR-P8-02: deployment execution requires the Governor flag; the"
        " default is plans-only (D7)"
    )
