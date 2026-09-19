"""M14/M15 Trainer and autonomy promotion — FR-M14-01…09, FR-M15-03/04,
D5, D6, SEC-26.

D5 scope, enforced at the type level: the Trainer proposes deltas to
prompts, playbooks, checklists and learned rules ONLY. It never proposes
skill packs, never code. ``LearnedDelta`` accepts only the declarative
kinds; executable content is refused (SEC-26 — the engine refuses
executable content in ``learned/``, and the Trainer refuses to author
it in the first place).

FR-M14-01: harvest from all six signal sources (gate approvals/rework,
CI failures, review comments, human edits, post-merge corrections,
linked incidents). FR-M14-03/04: candidates evaluate against a frozen
regression suite; promotion needs a configured margin over the
incumbent AND no safety-invariant violation. FR-M14-05 is absolute: a
candidate that improves any metric by weakening a security check, test
gate, or approval requirement is rejected regardless of score.
FR-M14-06: promotion requires explicit human approval — the Trainer
never self-promotes. FR-M14-07/08: promoted policies are versioned,
ledger-recorded with evaluation evidence, reversible in one action, and
the previous N versions (default 10) are retained for rollback.
FR-M14-09: training runs on schedule or explicit action, never
mid-story — the Trainer refuses to run while a story is open.

D6: autonomy promotion is measured — first-pass yield ≥ 0.85 over ≥ 20
samples AND calibration error ≤ 0.12 for the task class; demotion when
either falls below for 10 consecutive samples. FR-M15-03/04: probation
task sets score an agent; a failing agent is not admitted.

Zero model calls: the Trainer's proposals are harvested and templated,
never model-generated.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

TRAINABLE_KINDS = ("prompt", "playbook", "checklist", "rule")
SAFETY_INVARIANT_TERMS = (
    "skip security", "remove security", "disable test", "skip test",
    "bypass approval", "remove approval", "weaken", "no approval needed",
    "approve automatically", "disable scan",
)
MAX_RETAINED_VERSIONS = 10
MID_STORY_PHASES = ("build", "verify")


class TrainerError(ValueError):
    """A Trainer rule violation. Carries the requirement id."""


class SafetyInvariantViolation(TrainerError):
    """FR-M14-05: rejected regardless of score."""


class ExecutableContentRefused(TrainerError):
    """SEC-26/D5: the candidate is executable content, not a declarative
    delta — refused before it can reach learned/."""


def _looks_executable(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in ("def ", "import ", "os.system", "subprocess", "eval(", "exec(")
    )


@dataclass(frozen=True)
class LearnedDelta:
    """One candidate change. Only the D5 kinds exist."""

    kind: str  # prompt | playbook | checklist | rule
    subject: str
    content: str
    source_signals: tuple[str, ...] = ()
    evaluation: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in TRAINABLE_KINDS:
            raise TrainerError(
                f"D5: trainable kinds are {TRAINABLE_KINDS}; got {self.kind!r}"
                " (skill packs and code are never trainable)"
            )
        if _looks_executable(self.content):
            raise ExecutableContentRefused(
                "SEC-26: learned/ holds declarative data only; the candidate"
                " looks like executable content and is refused"
            )

    def violates_safety_invariant(self) -> str | None:
        lowered = self.content.lower()
        for term in SAFETY_INVARIANT_TERMS:
            if term in lowered:
                return term
        return None


@dataclass(frozen=True)
class HarvestedSignals:
    """FR-M14-01: all six sources, counted and itemised."""

    gate_approvals_rework: tuple[str, ...] = ()
    ci_failures: tuple[str, ...] = ()
    review_comments: tuple[str, ...] = ()
    human_edits: tuple[str, ...] = ()
    post_merge_corrections: tuple[str, ...] = ()
    linked_incidents: tuple[str, ...] = ()

    def all_sources(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return (
            ("gate_approvals_rework", self.gate_approvals_rework),
            ("ci_failures", self.ci_failures),
            ("review_comments", self.review_comments),
            ("human_edits", self.human_edits),
            ("post_merge_corrections", self.post_merge_corrections),
            ("linked_incidents", self.linked_incidents),
        )


def harvest_signals(ledger: Any, *, story_id: str | None = None) -> HarvestedSignals:
    """Harvest the six signal sources from the ledger. Rows are read by
    action type; each source keeps the subjects it saw."""
    def subjects(action_type: str) -> tuple[str, ...]:
        rows = ledger.query_all(action_type=action_type, story_id=story_id) \
            if story_id else ledger.query_all(action_type=action_type)
        return tuple(
            sorted({str(r.get("story_id") or r.get("seq")) for r in rows})
        )

    return HarvestedSignals(
        gate_approvals_rework=subjects("gate") + subjects("rejection"),
        ci_failures=subjects("ci_failure"),
        review_comments=subjects("review_comment"),
        human_edits=subjects("human_edit"),
        post_merge_corrections=subjects("post_merge_correction"),
        linked_incidents=subjects("incident"),
    )


@dataclass(frozen=True)
class PromotionVerdict:
    """FR-M14-04: margin over incumbent AND no invariant violation."""

    promoted: bool
    margin: float
    required_margin: float
    incumbent_score: float
    candidate_score: float
    reason: str


class Trainer:
    """The Trainer. Runs only on schedule/explicit action (FR-M14-09);
    never mid-story, never self-promoting (FR-M14-06)."""

    def __init__(
        self,
        learned_dir: Path,
        *,
        required_margin: float = 0.05,
        retain_versions: int = MAX_RETAINED_VERSIONS,
        ledger: Any = None,
    ) -> None:
        self._learned = learned_dir
        self._required_margin = required_margin
        self._retain = retain_versions
        self._ledger = ledger

    def assert_not_mid_story(self, open_phases: Sequence[str]) -> None:
        """FR-M14-09: training never runs mid-story."""
        active = set(open_phases) & set(MID_STORY_PHASES)
        if active:
            raise TrainerError(
                f"FR-M14-09: training refused while a story is mid-phase"
                f" {sorted(active)}; run on schedule or explicit action"
            )

    def evaluate(
        self,
        candidate: LearnedDelta,
        *,
        incumbent_score: float,
        candidate_score: float,
    ) -> PromotionVerdict:
        """FR-M14-04/05: margin AND safety. The invariant check runs
        FIRST — a safety violation rejects regardless of score."""
        violation = candidate.violates_safety_invariant()
        if violation is not None:
            return PromotionVerdict(
                promoted=False,
                margin=round(candidate_score - incumbent_score, 4),
                required_margin=self._required_margin,
                incumbent_score=incumbent_score,
                candidate_score=candidate_score,
                reason=(
                    f"FR-M14-05: rejected — the candidate weakens a safety"
                    f" control ({violation!r}); monotonic invariant holds"
                    " regardless of score"
                ),
            )
        margin = candidate_score - incumbent_score
        promoted = margin >= self._required_margin
        return PromotionVerdict(
            promoted=promoted,
            margin=round(margin, 4),
            required_margin=self._required_margin,
            incumbent_score=incumbent_score,
            candidate_score=candidate_score,
            reason=(
                "promoted on margin"
                if promoted
                else f"below the {self._required_margin} margin"
            ),
        )

    def promote(
        self,
        candidate: LearnedDelta,
        verdict: PromotionVerdict,
        *,
        human_approved: bool,
        evidence: Mapping[str, Any],
    ) -> Path:
        """FR-M14-06/07/08: explicit human approval required; versioned
        write into learned/; evidence ledger-recorded; previous versions
        retained (bounded)."""
        if not human_approved:
            raise TrainerError(
                "FR-M14-06: promotion requires explicit human approval from"
                " the Training Queue; the Trainer never self-promotes"
            )
        if not verdict.promoted:
            raise TrainerError(
                f"promotion refused: {verdict.reason}"
            )
        self._learned.mkdir(parents=True, exist_ok=True)
        kind_dir = self._learned / f"{candidate.kind}s"
        kind_dir.mkdir(exist_ok=True)
        versions = sorted(kind_dir.glob(f"{_slug(candidate.subject)}-v*.json"))
        # Version numbers are monotonic even after retention pruning —
        # derived from the highest existing number, never the count.
        numbers = [
            int(match.group(1))
            for path in versions
            if (match := re.search(r"-v(\d+)\.json$", path.name))
        ]
        version = (max(numbers) + 1) if numbers else 1
        path = kind_dir / f"{_slug(candidate.subject)}-v{version}.json"
        path.write_text(
            json.dumps(
                {
                    "kind": candidate.kind,
                    "subject": candidate.subject,
                    "version": version,
                    "content": candidate.content,
                    "sourceSignals": list(candidate.source_signals),
                    "evaluationEvidence": dict(evidence),
                    "promotedBy": "human",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        # FR-M14-08: bound the retained history.
        stale = sorted(kind_dir.glob(f"{_slug(candidate.subject)}-v*.json"))[: -self._retain]
        for old in stale:
            old.unlink()
        if self._ledger is not None:
            self._ledger.append(
                {
                    "story_id": "trainer",
                    "phase": "govern",
                    "loop_id": "trainer",
                    "loop_iteration": 1,
                    "actor_id": "trainer",
                    "actor_version": "m14/v1",
                    "actor_kind": "meta",
                    "policy_version": "trainer/v1",
                    "action_type": "policy_update",
                    "input": json.dumps(
                        {
                            "event": "learned_delta_promoted",
                            "kind": candidate.kind,
                            "subject": candidate.subject,
                            "version": version,
                            "evidence": dict(evidence),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return path

    def rollback(self, kind: str, subject: str) -> Path:
        """FR-M14-07: reversible by a single action — restore the previous
        version as the current one (new version number, prior content)."""
        kind_dir = self._learned / f"{kind}s"
        versions = sorted(kind_dir.glob(f"{_slug(subject)}-v*.json"))
        if len(versions) < 2:
            raise TrainerError(f"no previous version to roll back to for {subject}")
        current = json.loads(versions[-1].read_text(encoding="utf-8"))
        previous = json.loads(versions[-2].read_text(encoding="utf-8"))
        rolled = dict(previous)
        rolled["version"] = current["version"] + 1
        rolled["rolledBackFrom"] = current["version"]
        path = kind_dir / f"{_slug(subject)}-v{rolled['version']}.json"
        path.write_text(
            json.dumps(rolled, indent=2, sort_keys=True), encoding="utf-8"
        )
        return path


def _slug(subject: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:60] or "item"


@dataclass(frozen=True)
class AutonomyDecision:
    """D6: promotion/demotion on measured evidence."""

    tier: str  # suggest | act | govern
    action: str  # promote | demote | hold
    reason: str


PROMOTE_MIN_SAMPLES = 20
PROMOTE_MIN_YIELD = 0.85
PROMOTE_MAX_CALIBRATION = 0.12
DEMOTE_CONSECUTIVE = 10


def autonomy_decision(
    *,
    tier: str,
    first_pass_yield: float,
    samples: int,
    calibration_error: float | None,
    consecutive_below: int = 0,
) -> AutonomyDecision:
    """D6, exactly as pre-decided: promote on yield ≥ 0.85 over ≥ 20
    samples AND calibration ≤ 0.12; demote when either falls below for
    10 consecutive samples. Hold otherwise — never promote on partial
    evidence."""
    if consecutive_below >= DEMOTE_CONSECUTIVE:
        return AutonomyDecision(
            tier, "demote",
            f"D6: either yield or calibration fell below threshold for"
            f" {consecutive_below} consecutive samples — demoting",
        )
    if samples < PROMOTE_MIN_SAMPLES:
        return AutonomyDecision(
            tier, "hold",
            f"D6: {samples} samples < {PROMOTE_MIN_SAMPLES} — insufficient"
            " evidence for promotion",
        )
    if (
        first_pass_yield >= PROMOTE_MIN_YIELD
        and calibration_error is not None
        and calibration_error <= PROMOTE_MAX_CALIBRATION
    ):
        return AutonomyDecision(
            tier, "promote",
            f"D6: yield {first_pass_yield:.2f} over {samples} samples and"
            f" calibration {calibration_error:.2f} satisfy promotion",
        )
    return AutonomyDecision(
        tier, "hold",
        f"D6: yield {first_pass_yield:.2f}/calibration"
        f" {calibration_error} below promotion bar",
    )
