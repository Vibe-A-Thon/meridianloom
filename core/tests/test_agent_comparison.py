"""Agent-vs-agent comparison on the same story (FR-M37-04; F1 Workstream E
task 22).

Shadow mode (FR-M25-07, extended to external agents): the same task run by
two agents, with yield, rejection reasons, cost and LLM ratio side by
side. Components with no ledger evidence are labelled insufficient_evidence
or unknown — never fabricated, never silently dropped.
"""

from __future__ import annotations

import pytest

import bus_types

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.server import SidecarServer
from test_attribution import ALICE, T0, git


def _entry(story, actor, action_type="diff", repo_id="edb", **extra):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": action_type,
        "repo_id": repo_id,
    }
    entry.update(extra)
    return entry


def _rejection_entry(rejected_sequence, story, reason="other", repo_id="edb"):
    return _entry(
        story,
        "reviewer-human",
        "rejection",
        repo_id=repo_id,
        phase="review",
        decision="rejected",
        rework_reason=reason,
        rejected_sequence=rejected_sequence,
    )


def _server(tmp_path, entries):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger)
    for entry in entries:
        ledger.append(entry)
    return server, ledger


def _call(server, method, params):
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 11, "method": method, "params": params}
    )
    assert response is not None
    assert "error" not in response, response.get("error")
    return response["result"]


class TestAgentComparison:
    """FR-M37-04: yield, rejection reasons, cost and LLM ratio side by side
    for every agent that ran the same story."""

    @pytest.fixture()
    def world(self, tmp_path):
        """Two agents run story S; agent-one's second attempt is rejected
        (missing-tests), agent-two spends far more tokens for one clean
        attempt. Story T has no token data anywhere."""
        entries = [
            # Story S: agent-one proposes twice, one accepted one rejected.
            _entry("S", "agent-one", tokens_in=100, tokens_out=50, cost_usd=0.01),
            _entry("S", "agent-one", tokens_in=80, tokens_out=40, cost_usd=0.008),
            # agent-two proposes once, cleanly.
            _entry("S", "agent-two", tokens_in=900, tokens_out=300, cost_usd=0.05),
            # Story T: bare diffs, no spend columns recorded at all.
            _entry("T", "agent-one"),
            _entry("T", "agent-two"),
        ]
        server, ledger = _server(tmp_path, entries)
        seq_rejected = 2  # the second agent-one diff on story S
        ledger.append(_rejection_entry(seq_rejected, "S", reason="missing-tests"))
        yield server, ledger
        ledger.close()

    def test_yield_side_by_side(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})

        one = result["agents"]["agent-one"]
        two = result["agents"]["agent-two"]
        assert one["yield"]["status"] == "ok"
        assert one["yield"]["value"] == 0.5
        assert one["yield"]["proposed"] == 2
        assert one["yield"]["rejected"] == 1
        assert two["yield"]["status"] == "ok"
        assert two["yield"]["value"] == 1.0
        assert two["yield"]["proposed"] == 1

    def test_rejection_reasons_side_by_side(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})

        one = result["agents"]["agent-one"]
        two = result["agents"]["agent-two"]
        assert one["rejectionReasons"]["status"] == "ok"
        assert one["rejectionReasons"]["byClass"] == {"missing-tests": 1}
        assert one["rejectionReasons"]["total"] == 1
        # agent-two was never rejected: labelled, not hidden.
        assert two["rejectionReasons"]["status"] == "insufficient_evidence"
        assert two["rejectionReasons"]["value"] is None
        assert two["rejectionReasons"]["total"] == 0

    def test_cost_side_by_side(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})

        one = result["agents"]["agent-one"]
        two = result["agents"]["agent-two"]
        assert one["cost"]["status"] == "ok"
        assert one["cost"]["totalUsd"] == 0.018
        assert one["cost"]["tokensIn"] == 180
        assert one["cost"]["tokensOut"] == 90
        assert two["cost"]["totalUsd"] == 0.05
        assert two["cost"]["tokensIn"] == 900
        assert two["cost"]["tokensOut"] == 300

    def test_llm_ratio_is_token_share_of_the_story(self, world):
        """LLM ratio: the agent's share of the story's recorded tokens —
        agent-two burned 1200 of 1470 tokens (~0.82), agent-one the rest."""
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})
        total = 1470

        one = result["agents"]["agent-one"]["llmRatio"]
        two = result["agents"]["agent-two"]["llmRatio"]
        assert one["status"] == "ok"
        assert one["value"] == round(270 / total, 6)
        assert two["value"] == round(1200 / total, 6)

    def test_no_token_evidence_anywhere_is_unknown_not_zero(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "T"})
        for agent in result["agents"].values():
            llm = agent["llmRatio"]
            assert llm["status"] == "unknown"
            assert llm["value"] is None
            assert llm["storyTokens"] == 0

    def test_no_cost_evidence_is_insufficient_not_zero(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "T"})
        for agent in result["agents"].values():
            cost = agent["cost"]
            assert cost["status"] == "insufficient_evidence"
            assert cost["value"] is None
            assert cost["entries"] == 0

    def test_actor_ids_scope_orders_and_restricts(self, world):
        server, _ledger = world
        result = _call(
            server,
            "trust/compareAgents",
            {"storyId": "S", "actorIds": ["agent-two", "agent-one"]},
        )
        assert list(result["agents"].keys()) == ["agent-two", "agent-one"]
        assert result["scope"]["actorIds"] == ["agent-two", "agent-one"]

        solo = _call(
            server,
            "trust/compareAgents",
            {"storyId": "S", "actorIds": ["agent-two"]},
        )
        assert list(solo["agents"].keys()) == ["agent-two"]

    def test_agent_without_proposals_is_insufficient_evidence(self, world):
        """An actor in scope that never proposed on the story gets a
        labelled component, not a fabricated 0% yield."""
        server, ledger = world
        ledger.append(_entry("S", "agent-three", action_type="review", decision="approved"))
        result = _call(server, "trust/compareAgents", {"storyId": "S"})
        three = result["agents"]["agent-three"]
        assert three["yield"]["status"] == "insufficient_evidence"
        assert three["yield"]["value"] is None

    def test_story_classification_reported(self, world):
        server, _ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})
        # No storyCommits -> nothing to classify with: unclassified, still
        # reported, never dropped.
        assert result["storyClassification"] == "unclassified"

    def test_story_classification_greenfield(self, world, tmp_path):
        """With the story's commits and a repoPath the classification is
        real (G6) — a brand-new file is greenfield."""
        import pathlib

        repo = pathlib.Path(tmp_path) / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init")
        (repo / "src").mkdir()
        (repo / "src" / "app.txt").write_text("one\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "initial", author=ALICE, date=T0)
        (repo / "src" / "feature.txt").write_text("fresh\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "story S", author=ALICE, date=T0 + 600)
        sha = git(repo, "rev-parse", "HEAD").strip()

        server, _ledger = world
        result = _call(
            server,
            "trust/compareAgents",
            {
                "storyId": "S",
                "repoPath": str(repo),
                "storyCommits": {"S": [sha]},
            },
        )
        assert result["storyClassification"] == "greenfield"

    def test_reconciles_to_the_ledger(self, world):
        """Independent recomputation from raw rows equals the RPC result."""
        server, ledger = world
        result = _call(server, "trust/compareAgents", {"storyId": "S"})

        rows = ledger.query(story_id="S", limit=1000)
        rejected_sequences = {
            row["rejected_sequence"]
            for row in ledger.query(action_type="rejection", limit=1000)
            if row.get("rejected_sequence") is not None
        }
        story_tokens = sum(
            (row.get("tokens_in") or 0) + (row.get("tokens_out") or 0)
            for row in rows
        )
        for actor, component in result["agents"].items():
            diffs = [
                row
                for row in rows
                if row["actor_id"] == actor and row["action_type"] == "diff"
            ]
            rejected = sum(1 for row in diffs if row["seq"] in rejected_sequences)
            assert component["yield"]["proposed"] == len(diffs)
            assert component["yield"]["rejected"] == rejected
            tokens = sum(
                (row.get("tokens_in") or 0) + (row.get("tokens_out") or 0)
                for row in rows
                if row["actor_id"] == actor
            )
            assert component["llmRatio"]["value"] == round(
                tokens / story_tokens, 6
            )

    def test_result_is_cached_then_invalidated_on_append(self, world):
        server, ledger = world
        params = {"storyId": "S"}
        first = _call(server, "trust/compareAgents", params)
        second = _call(server, "trust/compareAgents", params)
        assert second["cacheHit"] is True

        ledger.append(_entry("S", "agent-one", tokens_in=10, tokens_out=5))
        third = _call(server, "trust/compareAgents", params)
        assert third["cacheHit"] is False
        assert third["agents"]["agent-one"]["yield"]["proposed"] == 3

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/compareAgents" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"
