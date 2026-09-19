"""Run initiation over the bus — M40, MV2-T02/T03/T04.

`test_initiation.py` pins the contract in isolation, with injected callables
and no repository on disk. That is the right shape for the ordering proof,
and it is not a proof that anything was wired up: a contract can be perfect
and reachable by nobody.

These drive the real `SidecarServer` against a real git repository and a real
ledger, so the claims are about the product rather than about a dataclass:

  * preflight answers the six questions and *shows* the missing ones
    (FR-M40-03);
  * a launch the role pack does not permit is refused, and the refusal is
    recorded (FR-M40-05, SEC-30);
  * nothing — no branch, no worktree, no entry implying work — exists until
    after a human confirms (FR-M40-09, AC-39);
  * five doors produce five records differing only in `origin` (AC-38).

The negative controls are the assertions about absence: `git branch --list`
and the filesystem, checked after every refusal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from meridian_core import initiation, protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer
from meridian_core.worktree import manager as worktree_mod

from test_attribution import git

ADAPTERS = {"Developer": "acme-java-developer", "QA": "acme-qa"}

#: The five doors AC-38 names. The remaining origins are covered by
#: `test_every_other_door_is_startable`, which derives its list from this one
#: so that adding a door to the vocabulary cannot leave it untested.
FIVE_DOORS = ("ui", "command", "omnibar", "chat", "editor")
GATES = ["DoR", "Design", "DoD", "Security", "Review"]

ROLES_TEXT = """
version: 1
defaultRole: approver
roles:
  approver:
    description: Accountable human approver.
    permissions: [approve, delegate]
  auditor:
    description: Read-only across the ledger.
    permissions: [export-audit]
    readOnly: true
approvals:
  nOfM: {}
soD:
  forbidSelfApproval: true
delegation:
  maxChainDepth: 2
  maxTtlDays: 30
hygiene:
  approveLatencyFloorSeconds: 30
  bulkWindowMinutes: 10
  bulkMinCount: 3
"""


@pytest.fixture()
def initiation_repo(repo: Path) -> Path:
    """The fixture repo with an identity and a role pack.

    The identity is repo-local rather than inherited: `_human_identity`
    resolves through `GitIdentityProvider`, and a machine with no global
    git identity would otherwise fail these tests for a reason that has
    nothing to do with initiation.
    """
    git(repo, "config", "user.name", "Alice A")
    git(repo, "config", "user.email", "alice@example.com")
    policy = repo / ".meridian" / "policy"
    policy.mkdir(parents=True, exist_ok=True)
    (policy / "roles.yaml").write_text(ROLES_TEXT, encoding="utf-8")
    return repo


@pytest.fixture()
def server(initiation_repo: Path, tmp_path_factory) -> SidecarServer:
    ledger_dir = tmp_path_factory.mktemp("ledger")
    instance = SidecarServer(ledger=Ledger(ledger_dir, EphemeralSigningKeyProvider()))
    instance.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(initiation_repo),
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    return instance


def call(server: SidecarServer, method: str, params: dict) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": 99, "method": method, "params": params}
    )


def ok(response: dict) -> dict:
    assert "error" not in response, response.get("error")
    return response["result"]


def err(response: dict) -> dict:
    assert "error" in response, f"expected a refusal, got {response.get('result')}"
    return response["error"]


def branches(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "branch", "--list", "--format=%(refname:short)"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def preflight_for(
    server: SidecarServer,
    repo: Path,
    *,
    origin: str = "ui",
    mode: str = "dry_run",
    **over,
) -> dict:
    params = {
        "origin": origin,
        "intent": "Add an idempotency key to the payment submission endpoint",
        "repo": str(repo),
        "baseBranch": "main",
        "adapters": dict(ADAPTERS),
        "mode": mode,
        "gates": list(GATES),
        "estimateUsd": 3.1,
        "costCeilingUsd": 6.0,
    }
    params.update(over)
    return ok(call(server, "run/preflight", params))["preflight"]


def run_entries(server: SidecarServer, run_id: str) -> list[dict]:
    ledger = server._ensure_ledger()
    return list(ledger.query(story_id=run_id, limit=100))


class TestPreflightAnswersTheSixQuestions:
    """FR-M40-03. Preflight is mandatory, so it has to be *answerable*."""

    def test_a_complete_request_is_confirmable(self, server, initiation_repo):
        report = preflight_for(server, initiation_repo)
        assert report["confirmable"] is True
        assert report["missing"] == []
        assert report["intent"].startswith("Add an idempotency key")
        assert report["adapters"] == ADAPTERS
        assert report["gates"] == GATES
        assert report["estimateUsd"] == 3.1 and report["costCeilingUsd"] == 6.0
        assert report["mode"] == "dry_run"

    def test_a_missing_estimate_is_shown_not_raised(self, server, initiation_repo):
        # An exception here would leave the human with a dialog that will not
        # open and no way to see why. The surface has to be able to render
        # what is unanswered.
        response = call(
            server,
            "run/preflight",
            {
                "origin": "ui",
                "intent": "Something",
                "repo": str(initiation_repo),
                "adapters": dict(ADAPTERS),
                "gates": list(GATES),
            },
        )
        report = ok(response)["preflight"]
        assert report["confirmable"] is False
        assert "estimate" in report["missing"]

    def test_zero_is_an_answer_and_none_is_not(self, server, initiation_repo):
        # P26 at the door: a measured zero is a cost estimate. Treating it as
        # missing would block a legitimately free run; treating None as zero
        # would tell a human a run costs nothing when nobody knows.
        free = preflight_for(server, initiation_repo, estimateUsd=0.0, costCeilingUsd=0.0)
        assert free["missing"] == []
        unknown = preflight_for(server, initiation_repo, estimateUsd=None)
        assert "estimate" in unknown["missing"]

    def test_an_origin_outside_the_vocabulary_is_refused_at_the_door(
        self, server, initiation_repo
    ):
        error = err(
            call(
                server,
                "run/preflight",
                {"origin": "smtp", "intent": "x", "repo": str(initiation_repo)},
            )
        )
        assert error["data"]["code"] == "ORIGIN_UNKNOWN"

    def test_the_promised_paths_are_the_paths_that_get_created(
        self, server, initiation_repo
    ):
        """The worktree promise on screen 10.51 has to be true.

        The dialog tells the reader their working tree is untouched and names
        the path that will be created instead. The contract derives that path
        and the worktree manager creates it — two derivations, and if they
        drift the screen is showing a path that does not exist while the run
        writes somewhere the reader was never told about.
        """
        report = preflight_for(server, initiation_repo)
        manager = worktree_mod.WorktreeManager(initiation_repo)
        expected_path = manager.worktree_path(report["runId"])
        assert Path(initiation_repo / report["worktree"]) == expected_path
        assert report["branch"] == f"{worktree_mod.BRANCH_PREFIX}{report['runId']}"


class TestNothingIsCreatedBeforeConfirmation:
    """FR-M40-03/09, AC-39. The refusals all happen before anything exists."""

    def test_an_unconfirmed_start_is_refused_and_creates_nothing(
        self, server, initiation_repo
    ):
        report = preflight_for(server, initiation_repo)
        error = err(
            call(server, "run/start", {"preflight": report, "confirmed": False})
        )
        assert error["data"]["code"] == "PREFLIGHT_NOT_CONFIRMED"
        assert report["branch"] not in branches(initiation_repo)
        assert not (initiation_repo / report["worktree"]).exists()

    def test_an_incomplete_preflight_cannot_be_confirmed(
        self, server, initiation_repo
    ):
        report = preflight_for(server, initiation_repo, estimateUsd=None)
        assert report["confirmable"] is False
        error = err(
            call(server, "run/start", {"preflight": report, "confirmed": True})
        )
        assert error["data"]["code"] == "PREFLIGHT_INCOMPLETE"
        assert "estimate" in error["data"]["missing"]
        assert report["branch"] not in branches(initiation_repo)

    def test_a_confirmation_for_a_different_target_is_refused(
        self, server, initiation_repo
    ):
        """The human confirmed one branch; the start asked for another.

        Both are derived from the run id, so they cannot legitimately differ.
        Quietly creating the derived one would mean the confirmation covered
        something the human never saw — which is the whole thing preflight
        exists to prevent.
        """
        report = preflight_for(server, initiation_repo)
        report = {**report, "branch": "meridian/somewhere-else"}
        error = err(
            call(server, "run/start", {"preflight": report, "confirmed": True})
        )
        assert error["data"]["code"] == "PREFLIGHT_TAMPERED"
        assert "somewhere-else" not in " ".join(branches(initiation_repo))


class TestLaunchAuthority:
    """FR-M40-05, SEC-30. Role-checked before anything is created."""

    def test_a_read_only_role_may_dry_run(self, server, initiation_repo):
        # A dry run writes nothing, so a read-only role is not exceeding what
        # the policy says it may do.
        report = preflight_for(server, initiation_repo, mode="dry_run")
        result = ok(
            call(
                server,
                "run/start",
                {"preflight": report, "confirmed": True, "role": "auditor"},
            )
        )
        assert result["mode"] == "dry_run"

    def test_a_read_only_role_may_not_go_live(self, server, initiation_repo):
        report = preflight_for(server, initiation_repo, mode="live")
        error = err(
            call(
                server,
                "run/start",
                {"preflight": report, "confirmed": True, "role": "auditor"},
            )
        )
        assert error["data"]["code"] == "MODE_NOT_PERMITTED"
        assert error["data"]["permitted"] == ["dry_run"]
        assert report["branch"] not in branches(initiation_repo)
        assert not (initiation_repo / report["worktree"]).exists()

    def test_the_refusal_is_recorded(self, server, initiation_repo):
        # A refused launch that leaves no trace is indistinguishable from one
        # nobody attempted, and "who was turned away, and why" is exactly the
        # question asked after an incident.
        report = preflight_for(server, initiation_repo, mode="live")
        err(
            call(
                server,
                "run/start",
                {"preflight": report, "confirmed": True, "role": "auditor"},
            )
        )
        entries = run_entries(server, report["runId"])
        assert [e["action_type"] for e in entries] == ["run_start_refused"]
        assert entries[0]["decision"] == "rejected"
        assert entries[0]["origin"] == "ui"
        assert entries[0]["run_id"] == report["runId"]

    def test_an_asserted_identity_never_satisfies_a_verified_requirement(
        self, server, initiation_repo
    ):
        """FR-M42-05, reused rather than re-implemented.

        The fixture identity comes from git config, which is a claim and not
        a verification. A policy that requires verification has to refuse it,
        or the assurance ladder is decorative.
        """
        report = preflight_for(server, initiation_repo)
        error = err(
            call(
                server,
                "run/start",
                {
                    "preflight": report,
                    "confirmed": True,
                    "requiresVerifiedIdentity": True,
                },
            )
        )
        assert error["data"]["code"] == "IDENTITY_ASSURANCE_INSUFFICIENT"
        assert error["data"]["assurance"] == "asserted"
        assert report["branch"] not in branches(initiation_repo)

    def test_a_started_run_records_who_and_at_what_assurance(
        self, server, initiation_repo
    ):
        report = preflight_for(server, initiation_repo)
        result = ok(
            call(server, "run/start", {"preflight": report, "confirmed": True})
        )
        assert result["authorisedBy"] == "alice@example.com"
        # The assurance travels with the identity so a run authorised by a
        # git name is never later read as having been verified.
        assert result["assurance"] == "asserted"
        entries = run_entries(server, report["runId"])
        assert entries[0]["human_actor"] == "Alice A <alice@example.com>"


class TestStartingARun:
    def test_the_record_lands_before_the_worktree_exists(
        self, server, initiation_repo
    ):
        """E1/FR-M10-08, through the real ledger and the real git.

        On a crash between the two, an entry with no worktree is a run that
        plainly did not start; a worktree with no entry is unexplained work
        on a branch nobody can account for.
        """
        report = preflight_for(server, initiation_repo)
        result = ok(
            call(server, "run/start", {"preflight": report, "confirmed": True})
        )
        assert result["sequence"] is not None
        assert report["branch"] in branches(initiation_repo)
        assert (initiation_repo / report["worktree"]).is_dir()
        entries = run_entries(server, report["runId"])
        assert [e["action_type"] for e in entries] == ["run_started"]
        assert entries[0]["seq"] == result["sequence"]

    def test_the_primary_working_tree_is_untouched(self, server, initiation_repo):
        # The claim the dialog makes to the reader, checked against git
        # rather than against the sentence.
        before = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=initiation_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        report = preflight_for(server, initiation_repo)
        ok(call(server, "run/start", {"preflight": report, "confirmed": True}))
        after = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=initiation_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert after == before

    def test_five_doors_differ_only_in_origin(self, server, initiation_repo):
        """AC-38, through the ledger this time.

        The contract-level version of this test lives in `test_initiation.py`
        and compares dataclasses. This one compares the rows that actually
        get written, because the ledger is what a reviewer reads a year
        later — and a field that diverges between doors only in the server's
        entry assembly would pass the contract test and fail here.
        """
        doors = list(FIVE_DOORS)
        rows = []
        for door in doors:
            report = preflight_for(server, initiation_repo, origin=door)
            ok(call(server, "run/start", {"preflight": report, "confirmed": True}))
            rows.append(run_entries(server, report["runId"])[0])

        assert [row["origin"] for row in rows] == doors
        # Everything that is not per-run identity must be identical.
        varies_legitimately = {
            # Per-entry identity and chain linkage, plus the per-run id the
            # entry is *about*. Everything else is the shape of the record,
            # and AC-38 is the claim that the shape does not depend on the
            # door.
            "seq",
            "entry_hash",
            "prev_hash",
            "signature",
            "ts_utc",
            "story_id",
            "run_id",
            "origin",
            "input_digest",
            "input_ref",
        }
        shapes = set()
        for row in rows:
            shapes.add(
                tuple(
                    sorted(
                        (key, repr(value))
                        for key, value in row.items()
                        if key not in varies_legitimately
                    )
                )
            )
        assert len(shapes) == 1, (
            "records from different doors differ in more than `origin`; "
            "AC-38 requires the door to be the only difference"
        )

    def test_every_other_door_is_startable(self, server, initiation_repo):
        """The vocabulary is closed, so a door that exists and cannot be used
        is a real failure mode — and `file`, `connector` and `api` have no UI,
        so they are the ones that would rot unnoticed.

        The list is derived rather than written out: a door added to
        `ORIGINS` and to neither test would otherwise be covered by nothing
        while both tests stayed green.
        """
        rest = [door for door in initiation.ORIGINS if door not in FIVE_DOORS]
        assert set(rest) | set(FIVE_DOORS) == set(initiation.ORIGINS)
        for door in rest:
            report = preflight_for(server, initiation_repo, origin=door)
            result = ok(
                call(server, "run/start", {"preflight": report, "confirmed": True})
            )
            assert result["origin"] == door


class TestCancellationLeavesOneRecord:
    """FR-M40-09, AC-39 — asserted against the filesystem, git and the ledger."""

    def test_cancelling_creates_no_worktree_and_no_branch(
        self, server, initiation_repo
    ):
        report = preflight_for(server, initiation_repo)
        result = ok(call(server, "run/cancel", {"preflight": report}))
        assert result["cancelled"] is True
        assert not (initiation_repo / report["worktree"]).exists()
        assert report["branch"] not in branches(initiation_repo)

    def test_cancelling_leaves_exactly_one_entry_and_it_says_so(
        self, server, initiation_repo
    ):
        report = preflight_for(server, initiation_repo)
        ok(call(server, "run/cancel", {"preflight": report, "reason": "wrong repo"}))
        entries = run_entries(server, report["runId"])
        assert len(entries) == 1
        assert entries[0]["action_type"] == "run_cancelled_at_preflight"
        assert entries[0]["decision"] == "cancelled"
        assert entries[0]["origin"] == "ui"

    def test_a_cancellation_is_recorded_rather_than_erased(
        self, server, initiation_repo
    ):
        # Not "no record": a run that vanished without one is
        # indistinguishable from a run that never reached preflight, and the
        # difference matters when someone asks why work was not done.
        report = preflight_for(server, initiation_repo)
        ok(call(server, "run/cancel", {"preflight": report}))
        assert run_entries(server, report["runId"]) != []

    def test_cancelling_is_not_a_cleanup_path(self, server, initiation_repo):
        """The guarantee is structural, not janitorial.

        If cancellation worked by deleting a worktree that start had
        optimistically created, the promise would depend on the cleanup
        running — and it would not survive a crash between the two. Nothing
        is created before confirmation, so there is nothing to tidy: proven
        by cancelling a run that was never started and finding the tree
        already clean.
        """
        def tree() -> list[str]:
            # Recursive, and skipping .git, whose internals churn on read.
            # The first version of this compared only the top-level names
            # and passed against a planted eager worktree, because the
            # `.meridian` directory already existed for the policy files —
            # a test that cannot see the thing it is about.
            return sorted(
                str(path.relative_to(initiation_repo))
                for path in initiation_repo.rglob("*")
                if ".git" not in path.parts
            )

        before = tree()
        report = preflight_for(server, initiation_repo)
        ok(call(server, "run/cancel", {"preflight": report}))
        assert tree() == before
