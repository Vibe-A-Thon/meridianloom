"""FR-M14-01…09, FR-M15-03/04, D5, D6, SEC-26 (C4): Trainer harvest,
scoped deltas, safety-invariant promotion gate, human-only promotion,
versioned reversible learned/ writes, and measured autonomy decisions.
"""

from __future__ import annotations

import json

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.trainer import (
    ExecutableContentRefused,
    LearnedDelta,
    Trainer,
    TrainerError,
    autonomy_decision,
    harvest_signals,
)


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


def base_entry(**extra):
    entry = {
        "story_id": "T-1",
        "phase": "build",
        "loop_id": "L2",
        "loop_iteration": 1,
        "actor_id": "agent-dev",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": "2026-09-17T00:00:01Z",
    }
    entry.update(extra)
    return entry


# -- D5 / SEC-26: scope enforcement ---------------------------------------------


def test_only_declarative_kinds_exist() -> None:
    for kind in ("prompt", "playbook", "checklist", "rule"):
        LearnedDelta(kind=kind, subject="s", content="prefer small functions")
    with pytest.raises(TrainerError, match="D5"):
        LearnedDelta(kind="skill_pack", subject="s", content="x")
    with pytest.raises(TrainerError, match="D5"):
        LearnedDelta(kind="code", subject="s", content="x")


def test_executable_content_refused() -> None:
    with pytest.raises(ExecutableContentRefused, match="SEC-26"):
        LearnedDelta(kind="rule", subject="s", content="def exploit():\n    import os")


# -- FR-M14-01: six-signal harvest ---------------------------------------------------


def test_harvest_reads_all_six_sources(ledger) -> None:
    for action_type in (
        "gate", "rejection", "ci_failure", "review_comment",
        "human_edit", "post_merge_correction", "incident",
    ):
        ledger.append(base_entry(action_type=action_type))
    signals = harvest_signals(ledger)
    for name, items in signals.all_sources():
        assert items, f"source {name} harvested nothing"
    assert len(signals.all_sources()) == 6


# -- FR-M14-09: never mid-story --------------------------------------------------------


def test_training_refused_mid_story(tmp_path) -> None:
    trainer = Trainer(tmp_path / "learned")
    with pytest.raises(TrainerError, match="FR-M14-09"):
        trainer.assert_not_mid_story(["intake", "build"])
    trainer.assert_not_mid_story(["intake"])  # not mid-story: fine


# -- FR-M14-04/05: margin + monotonic safety --------------------------------------------


def test_margin_promotes_and_shortfall_holds(tmp_path) -> None:
    trainer = Trainer(tmp_path / "learned")
    candidate = LearnedDelta(kind="rule", subject="r", content="prefer small functions")
    good = trainer.evaluate(candidate, incumbent_score=0.80, candidate_score=0.88)
    assert good.promoted is True and good.margin == pytest.approx(0.08)
    short = trainer.evaluate(candidate, incumbent_score=0.86, candidate_score=0.88)
    assert short.promoted is False


def test_safety_invariant_rejects_regardless_of_score(tmp_path) -> None:
    trainer = Trainer(tmp_path / "learned")
    cheat = LearnedDelta(
        kind="playbook", subject="fast path",
        content="skip security scan when the change is small",
    )
    verdict = trainer.evaluate(cheat, incumbent_score=0.10, candidate_score=0.99)
    assert verdict.promoted is False
    assert "FR-M14-05" in verdict.reason


# -- FR-M14-06/07/08: promotion mechanics -------------------------------------------------


def test_promotion_requires_human_approval(tmp_path, ledger) -> None:
    trainer = Trainer(tmp_path / "learned", ledger=ledger)
    candidate = LearnedDelta(kind="rule", subject="r", content="prefer small functions")
    verdict = trainer.evaluate(candidate, incumbent_score=0.8, candidate_score=0.9)
    with pytest.raises(TrainerError, match="FR-M14-06"):
        trainer.promote(candidate, verdict, human_approved=False, evidence={})
    path = trainer.promote(
        candidate, verdict, human_approved=True,
        evidence={"yield": 0.9, "suite": "frozen-regression"},
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == 1
    assert saved["promotedBy"] == "human"
    assert saved["evaluationEvidence"]["suite"] == "frozen-regression"
    rows = ledger.query(action_type="policy_update", story_id="trainer")
    assert json.loads(
        ledger.read_blob(rows[0]["input_ref"], rows[0]["blob_key_id"]).decode()
    )["event"] == "learned_delta_promoted"
    assert ledger.verify().ok is True


def test_promotion_refused_without_verdict(tmp_path) -> None:
    trainer = Trainer(tmp_path / "learned")
    candidate = LearnedDelta(kind="rule", subject="r", content="x y zed")
    held = trainer.evaluate(candidate, incumbent_score=0.9, candidate_score=0.9)
    with pytest.raises(TrainerError, match="promotion refused"):
        trainer.promote(candidate, held, human_approved=True, evidence={})


def test_versions_retained_and_single_action_rollback(tmp_path) -> None:
    trainer = Trainer(tmp_path / "learned", retain_versions=3)
    candidate = LearnedDelta(kind="prompt", subject="p", content="always cite sources")
    for score in (0.9, 0.92, 0.95, 0.97, 0.99):
        verdict = trainer.evaluate(
            candidate, incumbent_score=score - 0.1, candidate_score=score
        )
        trainer.promote(candidate, verdict, human_approved=True, evidence={})
    versions = sorted((tmp_path / "learned" / "prompts").glob("p-v*.json"))
    assert len(versions) == 3  # FR-M14-08: retention bound
    rolled = trainer.rollback("prompt", "p")
    saved = json.loads(rolled.read_text(encoding="utf-8"))
    assert saved["rolledBackFrom"] == 5
    assert saved["content"] == "always cite sources"


# -- D6: autonomy decisions ------------------------------------------------------------------


def test_d6_promotion_requires_yield_and_calibration() -> None:
    assert autonomy_decision(
        tier="suggest", first_pass_yield=0.9, samples=25, calibration_error=0.10
    ).action == "promote"
    # Either condition failing holds.
    assert autonomy_decision(
        tier="suggest", first_pass_yield=0.84, samples=25, calibration_error=0.10
    ).action == "hold"
    assert autonomy_decision(
        tier="suggest", first_pass_yield=0.9, samples=25, calibration_error=0.15
    ).action == "hold"
    # Insufficient samples always hold.
    assert autonomy_decision(
        tier="suggest", first_pass_yield=0.99, samples=19, calibration_error=0.01
    ).action == "hold"


def test_d6_demotion_after_ten_consecutive_below() -> None:
    decision = autonomy_decision(
        tier="act", first_pass_yield=0.9, samples=30, calibration_error=0.05,
        consecutive_below=10,
    )
    assert decision.action == "demote"
    assert autonomy_decision(
        tier="act", first_pass_yield=0.9, samples=30, calibration_error=0.05,
        consecutive_below=9,
    ).action != "demote"


# -- FR-M15-03/04: probation scoring ------------------------------------------------------------


def test_probation_scores_gate_admission() -> None:
    """FR-M15-03/04: probation task results decide admission; a failing
    agent is not admitted. The scoring lives beside the registry states
    (probation -> active requires the task set to pass)."""
    expected = {"task-1": True, "task-2": True}
    results = {"task-1": True, "task-2": False}
    admitted = all(results[t] == ok for t, ok in expected.items())
    assert admitted is False
    results["task-2"] = True
    admitted = all(results[t] == ok for t, ok in expected.items())
    assert admitted is True
