"""Ranking suppression over incomparable coverage (FR-M41-15; N1
Workstream C task 15).

compareAgents ranks agents by first-pass yield — but only when the
cohorts are comparable. When an agent's attributed share falls below the
configured floor, or the agents' proposed-change sequence ranges do not
overlap, the ranking is SUPPRESSED with the reason named. A ranking over
incomparable coverage would crown an agent on a thinner evidentiary
base; it reads suppressed instead.
"""

from __future__ import annotations

from pathlib import Path

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics.compare import compute_agent_comparison


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _diff_entry(story: str, actor: str):
    return {
        "story_id": story,
        "phase": "build",
        "loop_id": "L",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }


class TestRanking:
    def test_comparable_cohorts_rank_by_yield(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            # Interleaved proposals: overlapping sequence ranges, the
            # comparable-cohort shape.
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        ranking = result["ranking"]
        assert ranking["status"] == "ok"
        assert ranking["by"] == "yield"
        assert ranking["ranked"] == ["agent-a", "agent-b"]  # tie -> name order
        assert ranking["reason"] is None

    def test_ranking_orders_by_yield_value(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            ledger.append(
                {
                    **_diff_entry("s1", "agent-a"),
                    "decision": "rejected",
                }
            )
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        # agent-b yield 1.0 outranks agent-a yield 0.5.
        assert result["ranking"]["ranked"] == ["agent-b", "agent-a"]

    def test_agents_without_yield_are_unranked_and_named(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            result = compute_agent_comparison(
                ledger, story_id="s1", actor_ids=["agent-a", "ghost"]
            )
        finally:
            ledger.close()
        ranking = result["ranking"]
        assert ranking["status"] == "ok"
        assert ranking["ranked"] == ["agent-a"]
        assert "ghost" in ranking["unranked"]

    def test_no_proposed_changes_anywhere_reads_insufficient_evidence(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(
                {
                    **_diff_entry("s1", "reviewer"),
                    "action_type": "review",
                    "phase": "review",
                }
            )
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        ranking = result["ranking"]
        assert ranking["status"] == "insufficient_evidence"
        assert ranking["ranked"] == []
        assert "insufficient_evidence" in ranking["reason"]

    def test_non_overlapping_sequence_ranges_suppress_with_reason(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            # agent-a proposed early in the story, agent-b only after a
            # long gap of other work: the proposed-change ranges do not
            # overlap, so the yields are not like-for-like.
            for seq in range(3):
                ledger.append(_diff_entry("s1", "agent-a"))
            for seq in range(20):
                ledger.append(_diff_entry("s1", "other-human"))
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        ranking = result["ranking"]
        assert ranking["status"] == "suppressed"
        assert ranking["ranked"] == []
        assert "coverage_not_comparable" in ranking["reason"]
        assert "do not overlap" in ranking["reason"]
        # The suppression names the evidence it rests on.
        assert "agent-a" in ranking["reason"]
        assert "agent-b" in ranking["reason"]

    def test_overlapping_ranges_rank(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            # Non-diff work between the proposals interleaves the agents'
            # ranges — the yields stay like-for-like.
            ledger.append(
                {
                    **_diff_entry("s1", "reviewer"),
                    "action_type": "review",
                    "phase": "review",
                }
            )
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        assert result["ranking"]["status"] == "ok"
        assert set(result["ranking"]["ranked"]) == {"agent-a", "agent-b"}

    def test_attributed_share_below_floor_suppresses_with_reason(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            # A row with no positive authorship evidence drags the
            # attributed share of agent-b's proposed population below a
            # 0.75 floor (1 of 2 attributable).
            ledger.append(
                {
                    **_diff_entry("s1", "agent-b"),
                    "actor_kind": "external",
                }
            )
            ledger.append(
                {**_diff_entry("s1", "agent-b"), "actor_kind": "external"}
            )
            result = compute_agent_comparison(
                ledger, story_id="s1", attribution_floor=0.75
            )
        finally:
            ledger.close()
        ranking = result["ranking"]
        assert ranking["status"] == "suppressed"
        assert ranking["ranked"] == []
        assert "coverage_not_comparable" in ranking["reason"]
        assert "below the configured floor" in ranking["reason"]
        assert "agent-b" in ranking["reason"]

    def test_same_population_below_floor_still_suppresses(self, tmp_path: Path):
        # Both agents attributable-share deficient: the first named agent
        # under the floor is the named reason.
        ledger = _ledger(tmp_path)
        try:
            ledger.append(
                {**_diff_entry("s1", "agent-a"), "actor_kind": "external"}
            )
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(
                ledger, story_id="s1", attribution_floor=0.9
            )
        finally:
            ledger.close()
        assert result["ranking"]["status"] == "suppressed"
        assert "floor" in result["ranking"]["reason"]
