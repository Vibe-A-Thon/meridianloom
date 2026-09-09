"""Greenfield/brownfield split on the trust score and the DORA export
(AMD-M37, G6; N1 Workstream B T12).

FR-M37-06's split already applied to the rejection rate (and the
reason distribution, J-curve and comparison); AMD-M37 notes the trust
score and the DORA export as the two surfaces that did NOT carry it.
Both now report greenfield / brownfield / unclassified buckets like
every other trust metric — stories the classifier declines land in
``unclassified``, reported, never dropped.
"""

from __future__ import annotations

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import dora as dora_mod
from meridian_core.metrics import score as score_mod

from test_trust_metrics import _repo, _story_a, _story_b


def _diff_entry(story: str, actor: str, **extra):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }
    entry.update(extra)
    return entry


@pytest.fixture()
def world(tmp_path):
    """Two classifiable stories (A greenfield, B brownfield) plus an
    unclassified story C, proposed changes on each."""
    repo = _repo(tmp_path / "repo")
    sha_a = _story_a(repo)
    sha_b = _story_b(repo)
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    ledger.append(_diff_entry("A", "agent-one"))
    ledger.append(_diff_entry("B", "agent-one", decision="approved"))
    ledger.append(_diff_entry("C", "agent-one"))
    yield ledger, repo, {"A": [sha_a], "B": [sha_b]}
    ledger.close()


def _classify_with_repo(repo, story_commits):
    """The same storyCommits-driven classifier the RPC layer builds
    (trust/classify semantics: story A's single new-file commit is
    greenfield, story B's edit to a year-old file is brownfield)."""
    from meridian_core.metrics.greenfield import classify as greenfield_classify

    def classify_fn(story_id: str) -> str | None:
        commits = story_commits.get(story_id)
        if not commits:
            return None
        return greenfield_classify(repo, commits=list(commits)).classification

    return classify_fn


class TestTrustScoreSplit:
    def test_split_buckets_carry_full_score_shape(self, world):
        ledger, _repo_path, _story_commits = world
        result = score_mod.compute_trust_score(
            ledger, actor_id="agent-one"
        )
        # Without a classifier everything is unclassified — the split
        # still rides the result, honest about the population.
        assert set(result["split"]) == {
            "greenfield",
            "brownfield",
            "unclassified",
        }
        unclassified = result["split"]["unclassified"]
        assert unclassified["sampleSize"] == 3
        assert unclassified["score"] == result["score"]
        assert result["split"]["greenfield"]["sampleSize"] == 0
        assert result["split"]["greenfield"]["status"] == "insufficient_evidence"

    def test_split_with_classifier(self, world):
        ledger, repo, story_commits = world
        result = score_mod.compute_trust_score(
            ledger,
            actor_id="agent-one",
            classify=_classify_with_repo(repo, story_commits),
        )
        split = result["split"]
        assert split["greenfield"]["sampleSize"] == 1
        assert split["brownfield"]["sampleSize"] == 1
        assert split["unclassified"]["sampleSize"] == 1
        # Each bucket is a real decomposition: components exposed.
        for kind in ("greenfield", "brownfield", "unclassified"):
            assert "components" in split[kind]
            assert "coverage" in split[kind]
            assert "firstPassYield" in split[kind]["components"]


class TestDoraSplit:
    def test_split_buckets_carry_full_four_keys(self, world):
        ledger, _repo_path, _story_commits = world
        result = dora_mod.compute_dora_metrics(ledger)
        assert set(result["split"]) == {
            "greenfield",
            "brownfield",
            "unclassified",
        }
        # No classifier: everything lands in unclassified; the bucket is
        # a full four-keys computation over that population.
        bucket = result["split"]["unclassified"]
        assert bucket["sampleSize"] == 3
        assert set(bucket["metrics"]) == {
            "deploymentFrequency",
            "leadTimeForChanges",
            "changeFailureRate",
            "timeToRestore",
        }
        assert bucket["status"] == result["status"]
        assert result["split"]["greenfield"]["sampleSize"] == 0

    def test_split_with_classifier(self, world):
        ledger, repo, story_commits = world
        result = dora_mod.compute_dora_metrics(
            ledger, classify=_classify_with_repo(repo, story_commits)
        )
        split = result["split"]
        assert split["greenfield"]["sampleSize"] == 1
        assert split["brownfield"]["sampleSize"] == 1
        assert split["unclassified"]["sampleSize"] == 1
        # Story B's diff is approved -> its brownfield bucket evidences
        # the deployment proxy; the greenfield bucket (no approvals)
        # honestly reads unknown, never invented.
        assert split["brownfield"]["metrics"]["deploymentFrequency"]["status"] == "ok"
        assert split["greenfield"]["metrics"]["deploymentFrequency"]["status"] == "unknown"
        assert split["greenfield"]["metrics"]["deploymentFrequency"]["value"] is None
