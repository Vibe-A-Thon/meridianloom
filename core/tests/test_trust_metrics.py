"""Rejection rate derived from the ledger (F0 Workstream F task 30;
FR-M17-05, FR-M37-01, FR-M37-06, G6).

The reconciliation test (AC-34 partial, "reconciles to the ledger")
recomputes the expected rate independently from raw ledger rows and
asserts it equals the RPC result exactly. The >=10-sessions human half of
AC-34 is out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import bus_types

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.server import SidecarServer
from test_attribution import ALICE, BOB, T0, git

DAY = 86_400
YEAR = 365 * DAY


def _repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path


def _commit(repo: Path, date: int, message: str = "work", author=BOB) -> str:
    git(repo, "add", ".")
    git(repo, "commit", "-m", message, author=author, date=date)
    return git(repo, "rev-parse", "HEAD").strip()


def _story_a(repo: Path) -> str:
    """Greenfield: one brand-new file."""
    (repo / "src" / "feature.txt").write_text("fresh\ncode\n", encoding="utf-8")
    return _commit(repo, T0 + 600, message="story A")


def _story_b(repo: Path) -> str:
    """Brownfield: a one-line edit to a year-old file."""
    (repo / "src" / "app.txt").write_text("one\ntwo-old\nthree\n", encoding="utf-8")
    return _commit(repo, T0 + YEAR, message="story B")


def _diff_entry(story: str, actor: str, repo_id: str = "edb", **extra):
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
        "repo_id": repo_id,
    }
    entry.update(extra)
    return entry


def _rejection_entry(rejected_sequence, story: str, repo_id: str = "edb"):
    return {
        "story_id": story,
        "phase": "review",
        "loop_id": "rejection",
        "loop_iteration": 0,
        "actor_id": "unknown",
        "actor_version": "0",
        "actor_kind": "external",
        "policy_version": "f0",
        "action_type": "rejection",
        "decision": "rejected",
        "rework_reason": "other",
        "rejected_sequence": rejected_sequence,
        "rejected_commit": "a" * 40,
        "rejecting_commit": "b" * 40,
        "repo_id": repo_id,
    }


@pytest.fixture()
def world(tmp_path):
    """Fixture repository (two classifiable stories) + seeded ledger."""
    repo = _repo(tmp_path / "repo")
    sha_a = _story_a(repo)
    sha_b = _story_b(repo)
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger)
    # Proposed changes: 3 on story A, 2 on story B, 1 on unclassified C.
    ledger.append(_diff_entry("A", "agent-one"))
    seq_a2 = ledger.append(_diff_entry("A", "agent-two")).sequence
    ledger.append(_diff_entry("A", "agent-one"))
    ledger.append(_diff_entry("B", "agent-one"))
    seq_b5 = ledger.append(_diff_entry("B", "agent-three")).sequence
    ledger.append(_diff_entry("C", "agent-two"))
    # Rejections: one per story, plus one untracked (null sequence) that
    # names no proposed entry and cannot enter any numerator.
    ledger.append(_rejection_entry(seq_a2, "A"))
    ledger.append(_rejection_entry(seq_b5, "B"))
    ledger.append(_rejection_entry(None, "untracked"))
    yield server, ledger, repo, {"A": sha_a, "B": sha_b}
    ledger.close()


def _call(server, method, params):
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 11, "method": method, "params": params}
    )
    assert response is not None
    assert "error" not in response, response.get("error")
    return response["result"]


def _independent_recomputation(ledger, repo_id, classifications):
    """The reconciliation oracle: same definitions, written down twice."""
    rows = [
        row
        for row in ledger.query(action_type="diff", limit=1000)
        if row.get("repo_id") == repo_id
    ]
    rejected_sequences = {
        row["rejected_sequence"]
        for row in ledger.query(action_type="rejection", limit=1000)
        if row.get("repo_id") == repo_id
        and row.get("rejected_sequence") is not None
    }
    overall = {"proposed": 0, "rejected": 0}
    split = {
        "greenfield": {"proposed": 0, "rejected": 0},
        "brownfield": {"proposed": 0, "rejected": 0},
        "unclassified": {"proposed": 0, "rejected": 0},
    }
    by_agent = {}
    for row in rows:
        hit = row["seq"] in rejected_sequences
        overall["proposed"] += 1
        overall["rejected"] += hit
        agent = by_agent.setdefault(row["actor_id"], {"proposed": 0, "rejected": 0})
        agent["proposed"] += 1
        agent["rejected"] += hit
        kind = classifications.get(row["story_id"], "unclassified")
        split[kind]["proposed"] += 1
        split[kind]["rejected"] += hit
    return overall, split, by_agent


class TestRejectionRate:
    def test_rate_split_by_greenfield_brownfield(self, world):
        server, _ledger, repo, shas = world
        result = _call(
            server,
            "trust/rejectionRate",
            {
                "repoPath": str(repo),
                "repoId": "edb",
                "storyCommits": {"A": [shas["A"]], "B": [shas["B"]]},
            },
        )

        assert result["cacheHit"] is False
        assert result["proposed"] == 6
        assert result["rejected"] == 2
        assert result["rate"] == pytest.approx(round(2 / 6, 6))
        # G6: the split is always reported.
        assert result["split"]["greenfield"] == {
            "proposed": 3,
            "rejected": 1,
            "rate": round(1 / 3, 6),
        }
        assert result["split"]["brownfield"] == {
            "proposed": 2,
            "rejected": 1,
            "rate": 0.5,
        }
        assert result["split"]["unclassified"] == {
            "proposed": 1,
            "rejected": 0,
            "rate": 0.0,
        }
        # Per agent.
        assert result["byAgent"]["agent-one"] == {
            "proposed": 3,
            "rejected": 0,
            "rate": 0.0,
        }
        assert result["byAgent"]["agent-two"] == {
            "proposed": 2,
            "rejected": 1,
            "rate": 0.5,
        }
        assert result["byAgent"]["agent-three"] == {
            "proposed": 1,
            "rejected": 1,
            "rate": 1.0,
        }

    def test_reconciles_to_the_ledger(self, world):
        """AC-34 partial: the RPC result equals an independent recomputation
        from the raw ledger rows."""
        server, ledger, repo, shas = world
        result = _call(
            server,
            "trust/rejectionRate",
            {
                "repoPath": str(repo),
                "repoId": "edb",
                "storyCommits": {"A": [shas["A"]], "B": [shas["B"]]},
            },
        )
        overall, split, by_agent = _independent_recomputation(
            ledger, "edb", {"A": "greenfield", "B": "brownfield"}
        )

        assert result["proposed"] == overall["proposed"]
        assert result["rejected"] == overall["rejected"]
        for kind, bucket in split.items():
            assert result["split"][kind]["proposed"] == bucket["proposed"]
            assert result["split"][kind]["rejected"] == bucket["rejected"]
        for agent, bucket in by_agent.items():
            assert result["byAgent"][agent]["proposed"] == bucket["proposed"]
            assert result["byAgent"][agent]["rejected"] == bucket["rejected"]

    def test_result_is_cached_then_invalidated_on_append(self, world):
        server, ledger, repo, shas = world
        params = {
            "repoPath": str(repo),
            "repoId": "edb",
            "storyCommits": {"A": [shas["A"]], "B": [shas["B"]]},
        }
        first = _call(server, "trust/rejectionRate", params)
        second = _call(server, "trust/rejectionRate", params)
        assert second["cacheHit"] is True
        assert second["proposed"] == first["proposed"]

        ledger.append(_diff_entry("A", "agent-one"))
        third = _call(server, "trust/rejectionRate", params)
        assert third["cacheHit"] is False
        assert third["proposed"] == first["proposed"] + 1

    def test_actor_scope(self, world):
        server, _ledger, repo, shas = world
        result = _call(
            server,
            "trust/rejectionRate",
            {
                "repoPath": str(repo),
                "repoId": "edb",
                "actorId": "agent-one",
                "storyCommits": {"A": [shas["A"]], "B": [shas["B"]]},
            },
        )
        assert result["scope"]["actorId"] == "agent-one"
        assert result["proposed"] == 3
        assert result["byAgent"] == {
            "agent-one": {"proposed": 3, "rejected": 0, "rate": 0.0}
        }

    def test_repo_scope_filters_entries(self, world):
        server, ledger, repo, shas = world
        ledger.append(_diff_entry("A", "agent-one", repo_id="other-repo"))
        result = _call(
            server,
            "trust/rejectionRate",
            {
                "repoPath": str(repo),
                "repoId": "edb",
                "storyCommits": {"A": [shas["A"]], "B": [shas["B"]]},
            },
        )
        assert result["proposed"] == 6

    def test_no_story_commits_reports_unclassified(self, world):
        server, _ledger, _repo, _shas = world
        result = _call(server, "trust/rejectionRate", {"repoId": "edb"})
        assert result["split"]["unclassified"]["proposed"] == 6
        assert result["split"]["greenfield"]["proposed"] == 0

    def test_empty_ledger_reports_zeroes(self, tmp_path):
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        server = SidecarServer(ledger=ledger)
        try:
            result = _call(server, "trust/rejectionRate", {})
        finally:
            ledger.close()
        assert result["proposed"] == 0
        assert result["rejected"] == 0
        assert result["rate"] == 0.0
        for bucket in result["split"].values():
            assert bucket == {"proposed": 0, "rejected": 0, "rate": 0.0}

    def test_story_with_missing_commits_degrades_to_unclassified(self, world):
        server, _ledger, repo, shas = world
        result = _call(
            server,
            "trust/rejectionRate",
            {
                "repoPath": str(repo),
                "repoId": "edb",
                # Story A's commits were rewritten away: it degrades to
                # unclassified rather than failing the metric.
                "storyCommits": {"A": ["deadbeef" * 5], "B": [shas["B"]]},
            },
        )
        assert result["split"]["unclassified"]["proposed"] == 4  # A's 3 + C's 1
        assert result["split"]["brownfield"]["proposed"] == 2

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/rejectionRate" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"


def _entry(story, actor, action_type, phase, repo_id="edb", **extra):
    entry = {
        "story_id": story,
        "phase": phase,
        "loop_id": "L1",
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


class TestScopedRejectionRate:
    """FR-M37-01 (F1 Workstream E task 19): the rejection rate extended with
    per-action-class, per-story, and per-phase scopes.

    Additive wire shape: the F0 keys (scope/proposed/rejected/rate/split/
    byAgent) keep their F0 meaning; byActionClass/byPhase/byStory generalise
    "rejected" to entries carrying decision rejected|reworked themselves —
    the review-time and rework shapes FR-M37-01 names alongside reverts.
    """

    @pytest.fixture()
    def world(self, tmp_path):
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        server = SidecarServer(ledger=ledger)
        # Proposed changes (diffs): 3 on story A, 1 on story B.
        ledger.append(_entry("A", "agent-one", "diff", "build"))
        ledger.append(_entry("A", "agent-one", "diff", "review", decision="rejected"))
        seq_b = ledger.append(_entry("B", "agent-two", "diff", "build")).sequence
        # A rejection entry naming seq_b (the linked-rejection shape).
        ledger.append(_rejection_entry(seq_b, "B"))
        # Non-diff entries in scope: a reworked test run, an approved review.
        ledger.append(_entry("A", "agent-one", "test_run", "verify", decision="reworked"))
        ledger.append(_entry("A", "agent-one", "review", "review", decision="approved"))
        yield server, ledger
        ledger.close()

    def test_by_action_class_phase_story(self, world):
        server, _ledger = world
        result = _call(server, "trust/rejectionRate", {"repoId": "edb"})

        # F0 keys unchanged: diffs only, linked-rejection shape.
        assert result["proposed"] == 3
        assert result["rejected"] == 1
        # New scopes generalise over every in-scope entry.
        assert result["byActionClass"]["diff"] == {
            "proposed": 3,
            "rejected": 2,
            "rate": round(2 / 3, 6),
        }
        assert result["byActionClass"]["test_run"] == {
            "proposed": 1,
            "rejected": 1,
            "rate": 1.0,
        }
        assert result["byActionClass"]["review"] == {
            "proposed": 1,
            "rejected": 0,
            "rate": 0.0,
        }
        assert result["byPhase"]["build"] == {
            "proposed": 2,
            "rejected": 1,
            "rate": 0.5,
        }
        assert result["byPhase"]["review"] == {
            "proposed": 2,
            "rejected": 1,
            "rate": 0.5,
        }
        assert result["byPhase"]["verify"] == {
            "proposed": 1,
            "rejected": 1,
            "rate": 1.0,
        }
        assert result["byStory"]["A"] == {
            "proposed": 4,
            "rejected": 2,
            "rate": 0.5,
        }
        assert result["byStory"]["B"] == {
            "proposed": 1,
            "rejected": 1,
            "rate": 1.0,
        }

    def test_decision_rejected_counts_on_the_diff_itself(self, world):
        """FR-M37-01: "rejected in review" — the decision-rejected diff is
        visible on the generalised scopes even without a rejection entry."""
        server, _ledger = world
        result = _call(server, "trust/rejectionRate", {"repoId": "edb"})
        assert result["byStory"]["A"]["rejected"] == 2

    def test_phase_filter_scopes_every_view(self, world):
        server, _ledger = world
        result = _call(server, "trust/rejectionRate", {"repoId": "edb", "phase": "build"})
        assert result["scope"]["phase"] == "build"
        assert result["proposed"] == 2
        assert result["rejected"] == 1
        assert list(result["byPhase"].keys()) == ["build"]
        assert result["byStory"] == {
            "A": {"proposed": 1, "rejected": 0, "rate": 0.0},
            "B": {"proposed": 1, "rejected": 1, "rate": 1.0},
        }

    def test_action_type_filter(self, world):
        server, _ledger = world
        result = _call(
            server, "trust/rejectionRate", {"repoId": "edb", "actionType": "test_run"}
        )
        assert result["scope"]["actionType"] == "test_run"
        # The F0 aggregate stays diff-based ("proposed" means diffs); the
        # actionType filter scopes the generalised views.
        assert result["proposed"] == 3
        assert result["byActionClass"] == {
            "test_run": {"proposed": 1, "rejected": 1, "rate": 1.0}
        }

    def test_f0_result_keys_unchanged(self, world):
        """Additive guarantee: the F0 wire shape is a subset of the new one."""
        server, _ledger = world
        result = _call(server, "trust/rejectionRate", {"repoId": "edb"})
        for key in ("scope", "proposed", "rejected", "rate", "split", "byAgent", "cacheHit"):
            assert key in result
