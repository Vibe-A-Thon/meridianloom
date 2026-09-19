"""C6 differentiation items (core-side): annotations/bookmarks,
counterfactual queries, quality-diversity archive, retirement handover,
batch epic ingestion, detected issues, scheduled tasks, fuzz case
generation, and the D7-honest deployment seam.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from meridian_core.differentiation import (
    Annotation,
    AnnotationStore,
    Candidate,
    QualityDiversityArchive,
    ScheduledTask,
    ScheduleRegistry,
    counterfactual,
    deploy_execution,
    detected_issues,
    fuzz_cases,
    ingest_epic,
    record_detected_issue,
    retire_with_handover,
)
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.memory.fabric import MemoryFabric


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


# -- FR-M10-16 -----------------------------------------------------------------


def test_annotations_and_bookmarks_ride_the_chain(ledger) -> None:
    store = AnnotationStore(ledger)
    store.add(Annotation(target_seq=7, author="auditor", text="check this"))
    store.add(Annotation(target_seq=9, author="lead", text="revisit at release", bookmark=True))
    bookmarks = store.bookmarks()
    assert len(bookmarks) == 1
    assert bookmarks[0]["targetSeq"] == 9
    assert ledger.verify().ok is True


# -- FR-M13-08 --------------------------------------------------------------------


def test_counterfactual_replay_answers_what_if() -> None:
    def decide(inputs):
        return "approve" if inputs.get("tests_green") and inputs.get("scan_clean") else "block"

    result = counterfactual(
        decide,
        decision_id="d1",
        inputs={"tests_green": True, "scan_clean": True},
        output="approve",
        without_factor="scan_clean",
    )
    # Without the scan-clean factor the same decision function blocks:
    # the factor was load-bearing.
    assert result.output_changed is True
    assert result.counterfactual_output == "block"
    assert "evidence" in result.labelled()


# -- FR-M14-11 -----------------------------------------------------------------------


def test_quality_diversity_archive_keeps_novel_or_better() -> None:
    archive = QualityDiversityArchive(novelty_threshold=0.2)
    first = Candidate("c1", "v1", {"brevity": 0.1, "formality": 0.1})
    assert archive.consider(first, score=0.5, best_score=0.5) is True
    # Near-duplicate, not better: refused.
    dup = Candidate("c2", "v2", {"brevity": 0.15, "formality": 0.12})
    assert archive.consider(dup, score=0.51, best_score=0.9) is False
    # Novel corner: kept despite lower score.
    novel = Candidate("c3", "v3", {"brevity": 0.9, "formality": 0.1})
    assert archive.consider(novel, score=0.4, best_score=0.9) is True
    # Better than best: kept despite proximity.
    better = Candidate("c4", "v4", {"brevity": 0.12, "formality": 0.11})
    assert archive.consider(better, score=0.95, best_score=0.9) is True


# -- FR-M16-10 --------------------------------------------------------------------------


def test_retirement_handover_transfers_memory_recorded(ledger, tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    fabric = MemoryFabric(ws)
    from meridian_core.memory.fabric import MemoryEntry, Provenance

    fabric.write(
        MemoryEntry(
            entry_id="p1", tier="procedural", subject="legacy-agent-playbook",
            content="always characterise before changing legacy code",
            provenance=Provenance(
                origin_sequence=None, author="legacy-agent", ts_utc="2026-09-17T00:00:00Z",
                confidence=0.95, origin="workspace",
            ),
        ),
        actor="legacy-agent",
    )
    sequence = retire_with_handover(
        fabric, retiring_subject="legacy-agent-playbook",
        successor_subject="successor-agent-playbook", ledger=ledger,
    )
    assert sequence is not None
    assert "characterise" in fabric.get(
        "procedural", "successor-agent-playbook"
    ).content
    rows = ledger.query(action_type="policy_update", story_id="agent-retirement")
    assert json.loads(rows[0]["tool_calls"])[0]["event"] == "memory_handover"


# -- FR-M19-07 -----------------------------------------------------------------------------


def test_batch_epic_ingestion_splits_stories() -> None:
    epic = (
        "# Payments epic\n"
        "## Idempotency keys\n"
        "- replays return the original response\n"
        "- concurrent dedup holds\n"
        "## Refund parity\n"
        "- refunds mirror the charge exactly\n"
    )
    stories = ingest_epic(epic, id_prefix="EDB")
    assert [s.story_id for s in stories] == ["EDB-001", "EDB-002"]
    assert len(stories[0].acceptance) == 2
    with pytest.raises(ValueError, match="FR-M19-07"):
        ingest_epic("no headings here")


# -- FR-M24-05 --------------------------------------------------------------------------------


def test_detected_issues_surface_by_query(ledger) -> None:
    record_detected_issue(
        ledger, agent_id="qa", severity="critical",
        description="flaky payment test", story_id="S1",
    )
    record_detected_issue(
        ledger, agent_id="sec", severity="warning",
        description="unused dependency", story_id="S2",
    )
    issues = detected_issues(ledger)
    assert len(issues) == 2
    s1 = detected_issues(ledger, story_id="S1")
    assert s1[0]["severity"] == "critical"
    with pytest.raises(ValueError, match="severity"):
        record_detected_issue(
            ledger, agent_id="x", severity="urgent",
            description="bad enum", story_id="S3",
        )


# -- FR-M30-05 -----------------------------------------------------------------------------------


def test_scheduled_tasks_due_and_marked() -> None:
    registry = ScheduleRegistry()
    registry.register(ScheduledTask("t1", "trainer.run", interval_s=3600))
    now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    due = registry.due(now)
    assert [t.task_id for t in due] == ["t1"]
    registry.mark_run("t1", at=now)
    assert registry.due(now) == ()
    assert registry.due(now + timedelta(seconds=3601))[0].task_id == "t1"
    with pytest.raises(ValueError, match="60s"):
        registry.register(ScheduledTask("t2", "x", interval_s=30))


# -- FR-P5-09 -------------------------------------------------------------------------------------


def test_fuzz_cases_cover_boundaries() -> None:
    schema = {
        "required": ["amount"],
        "properties": {
            "amount": {"type": "integer", "default": 10},
            "note": {"type": "string", "maxLength": 50},
        },
    }
    cases = fuzz_cases(schema, budget=10)
    names = {c["name"] for c in cases}
    assert "valid-baseline" in names
    assert "missing-required-amount" in names
    assert "oversize-note" in names


# -- FR-P8-02 (D7) -----------------------------------------------------------------------------------


def test_deployment_execution_is_a_d7_seam() -> None:
    with pytest.raises(NotImplementedError, match="FR-P8-02"):
        deploy_execution(governor_flag=True)
    with pytest.raises(NotImplementedError, match="D7"):
        deploy_execution(governor_flag=False)
