"""One contract, many doors — M40, MV2, FR-M40-01/02/03/05/09, SEC-30, AC-38.

The invariant under test is not "a run can start". It is that **every** way
of starting one converges on the same object, so preflight, authority and
origin are guaranteed once rather than per door. Four doors with four private
routes would each work, and "how did this run start?" would have four answers.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from meridian_core import initiation


NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


def a_request(**over):
    kwargs = dict(
        origin="ui",
        intent="Add an idempotency key to the payment submission endpoint",
        repo="payments-service",
        base_branch="main",
        adapters={"Developer": "acme-java-developer"},
        mode="dry_run",
        gates=("DoR", "Design", "DoD", "Security", "Review"),
        estimate_usd=3.10,
        cost_ceiling_usd=6.00,
        now=NOW,
    )
    kwargs.update(over)
    return initiation.build_run_request(**kwargs)


class TestTheOriginVocabulary:
    def test_the_contract_and_the_ledger_agree(self):
        """The vocabulary is not a new decision.

        The ledger has carried this CHECK constraint since schema v2 — M40's
        storage half was built before its contract half. If these two ever
        diverge, a run would pass the contract and fail at the database, or
        worse, pass both while meaning different things.
        """
        from meridian_core.ledger import schema

        statement = next(
            s for s in schema._V2_STATEMENTS if "origin" in s and "CHECK" in s
        )
        for origin in initiation.ORIGINS:
            assert f"'{origin}'" in statement, (
                f"origin {origin!r} is in the contract's vocabulary but not in "
                f"the ledger's CHECK constraint"
            )

    @pytest.mark.parametrize("origin", initiation.ORIGINS)
    def test_every_door_builds_a_request(self, origin):
        assert a_request(origin=origin).origin == origin

    def test_an_unknown_door_is_refused_by_name(self):
        with pytest.raises(initiation.InitiationError) as caught:
            a_request(origin="telepathy")
        assert caught.value.code == "ORIGIN_UNKNOWN"
        # The message names the closed set rather than saying "invalid".
        assert "omnibar" in str(caught.value)


class TestAC38:
    def test_five_doors_differ_only_in_origin(self):
        """AC-38, stated as the test rather than as prose.

        Five origins, one otherwise-identical request each. Every recorded
        field must match except `origin` — and `run_id`/`created_at`, which
        are per-run by construction and pinned here so the comparison is
        about the door and nothing else.
        """
        doors = ["ui", "command", "omnibar", "chat", "editor"]
        records = [
            initiation.first_entry_fields(
                initiation.authorise(
                    a_request(origin=door, run_id="run_fixed"),
                    identity_email="vikram@example.com",
                    identity_assurance="asserted",
                    permitted_modes=("dry_run", "live"),
                )
            )
            for door in doors
        ]
        assert [r.pop("origin") for r in records] == doors
        first = records[0]
        for other in records[1:]:
            assert other == first, (
                "two doors produced ledger records differing in something "
                "other than origin; AC-38 requires the door to be the only "
                "difference"
            )

    def test_the_branch_and_worktree_are_derived_not_supplied(self):
        # Two doors passing different branches for the same run id is the
        # divergence the single contract exists to prevent, so neither is
        # an input.
        request = a_request(run_id="run_abc")
        assert request.branch == "meridian/run_abc"
        assert request.worktree == ".meridian/worktrees/run_abc"


class TestPreflightIsMandatoryAndComplete:
    def test_a_complete_request_is_confirmable(self):
        report = initiation.preflight(a_request())
        assert report.confirmable
        assert report.missing == ()

    @pytest.mark.parametrize(
        "field,over",
        [
            ("adapters", {"adapters": {}}),
            ("estimate", {"estimate_usd": None}),
            ("estimate", {"cost_ceiling_usd": None}),
            ("gates", {"gates": ()}),
        ],
    )
    def test_each_missing_answer_is_named_and_blocks_confirmation(self, field, over):
        """FR-M40-03's six questions, one at a time.

        A preflight missing a field is worse than no preflight: it asks for
        a confirmation the human cannot actually give, and an incomplete one
        that still says "Start" is a consent dialog with a hole in it.
        """
        report = initiation.preflight(a_request(**over))
        assert field in report.missing
        assert not report.confirmable

    def test_a_zero_estimate_is_an_answer_not_a_gap(self):
        # P26 in miniature. `None` is unknown; 0.0 is a measured zero, and
        # conflating them would report a free run as an unpriced one.
        report = initiation.preflight(a_request(estimate_usd=0.0, cost_ceiling_usd=0.0))
        assert "estimate" not in report.missing

    def test_the_wire_shape_carries_every_field_the_dialog_renders(self):
        wire = initiation.preflight(a_request()).as_wire()
        for key in (
            "intent",
            "adapters",
            "repo",
            "baseBranch",
            "branch",
            "worktree",
            "estimateUsd",
            "costCeilingUsd",
            "gates",
            "mode",
            "confirmable",
        ):
            assert key in wire, f"the preflight dialog cannot render without {key}"


class TestLaunchAuthority:
    def test_an_authorised_run_records_who_and_at_what_assurance(self):
        authorised = initiation.authorise(
            a_request(),
            identity_email="vikram@example.com",
            identity_assurance="asserted",
            permitted_modes=("dry_run",),
        )
        assert authorised.authorised_by == "vikram@example.com"
        # The assurance travels with the identity, so a run authorised by a
        # git name is never later read as verified.
        assert authorised.authorised_assurance == "asserted"

    def test_an_unauthenticated_session_cannot_start_a_run(self):
        # SEC-30, including through the command palette — the door most
        # likely to be argued as an exception.
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.authorise(
                a_request(origin="command"),
                identity_email="",
                identity_assurance="unknown",
                permitted_modes=("dry_run", "live"),
            )
        assert caught.value.code == "IDENTITY_UNAVAILABLE"

    def test_an_under_privileged_identity_is_refused_and_the_refusal_says_why(self):
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.authorise(
                a_request(mode="live"),
                identity_email="intern@example.com",
                identity_assurance="asserted",
                permitted_modes=("dry_run",),
            )
        assert caught.value.code == "MODE_NOT_PERMITTED"
        assert caught.value.detail["permitted"] == ["dry_run"]
        assert "dry_run" in str(caught.value)

    def test_an_asserted_identity_never_satisfies_a_verified_requirement(self):
        # FR-M42-05 reused rather than re-implemented: the same rule that
        # governs approval governs launch.
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.authorise(
                a_request(),
                identity_email="vikram@example.com",
                identity_assurance="asserted",
                permitted_modes=("dry_run",),
                requires_verified=True,
            )
        assert caught.value.code == "IDENTITY_ASSURANCE_INSUFFICIENT"

    def test_authorisation_does_not_mutate_the_original_request(self):
        # The request is frozen because a mutable one could be edited
        # between preflight and start, making the human's confirmation a
        # confirmation of something else.
        request = a_request()
        initiation.authorise(
            request,
            identity_email="vikram@example.com",
            identity_assurance="asserted",
            permitted_modes=("dry_run",),
        )
        assert request.authorised_by is None


class TestCancellationLeavesOneRecord:
    def test_the_record_names_what_was_not_created(self):
        """FR-M40-09.

        Not "no record": a cancellation is a fact, and a run that vanished
        without one would be indistinguishable from a run that never reached
        preflight. What it must not leave is a worktree, a branch, or any
        entry implying work began.
        """
        record = initiation.cancellation_record(a_request(), reason="changed my mind")
        assert record["actionType"] == "run_cancelled_at_preflight"
        assert record["decision"] == "cancelled"
        assert record["detail"]["reason"] == "changed my mind"
        note = record["detail"]["note"].lower()
        assert "no worktree" in note and "no branch" in note

    def test_it_carries_the_origin_so_a_cancelled_run_is_still_traceable(self):
        record = initiation.cancellation_record(a_request(origin="chat"))
        assert record["origin"] == "chat"


class TestNothingIsCreatedBeforeConfirmation:
    """FR-M40-09's guarantee is structural, not a cleanup path.

    "A cancelled run leaves no worktree and no branch" can be achieved two
    ways: create nothing until the human says yes, or create optimistically
    and tidy up on cancel. Only the first is a guarantee — the second
    depends on the cleanup running, and cleanup does not run when the
    process is killed, the disk is full, or the cancel path has the bug.
    """

    def _authorised(self, **over):
        return initiation.authorise(
            a_request(**over),
            identity_email="vikram@example.com",
            identity_assurance="asserted",
            permitted_modes=("dry_run", "live"),
        )

    def test_an_unconfirmed_run_creates_nothing(self):
        created: list[tuple] = []
        recorded: list[dict] = []
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.start_run(
                self._authorised(),
                confirmed=False,
                record_entry=lambda entry: recorded.append(entry),
                create_worktree=lambda *args: created.append(args),
            )
        assert caught.value.code == "PREFLIGHT_NOT_CONFIRMED"
        assert created == [], "a worktree was created for an unconfirmed run"
        assert recorded == [], "a run entry was written for an unconfirmed run"

    def test_an_unauthorised_run_creates_nothing(self):
        created: list[tuple] = []
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.start_run(
                a_request(),  # never passed through authorise()
                confirmed=True,
                record_entry=lambda entry: entry,
                create_worktree=lambda *args: created.append(args),
            )
        assert caught.value.code == "NOT_AUTHORISED"
        assert created == []

    def test_an_incomplete_preflight_cannot_be_confirmed_past(self):
        # Confirming a dialog that could not have shown the cost is not
        # consent to the cost.
        created: list[tuple] = []
        with pytest.raises(initiation.InitiationError) as caught:
            initiation.start_run(
                self._authorised(estimate_usd=None),
                confirmed=True,
                record_entry=lambda entry: entry,
                create_worktree=lambda *args: created.append(args),
            )
        assert caught.value.code == "PREFLIGHT_INCOMPLETE"
        assert "estimate" in caught.value.detail["missing"]
        assert created == []

    def test_a_confirmed_run_records_before_it_creates(self):
        """E1 / FR-M10-08: nothing acts without being recorded first.

        The order matters on a crash: a worktree with no ledger entry is
        unexplained work, while an entry with no worktree is a run that
        plainly did not start.
        """
        order: list[str] = []
        result = initiation.start_run(
            self._authorised(),
            confirmed=True,
            record_entry=lambda entry: (order.append("record"), {"sequence": 1})[1],
            create_worktree=lambda *args: (order.append("create"), ".meridian/wt")[1],
        )
        assert order == ["record", "create"]
        assert result["runId"].startswith("run_")
        assert result["origin"] == "ui"
        assert result["authorisedBy"] == "vikram@example.com"
        assert result["assurance"] == "asserted"

    def test_the_first_entry_carries_run_id_and_origin(self):
        # FR-M40-02: the columns the ledger has had since schema v2, filled.
        captured: dict = {}
        initiation.start_run(
            self._authorised(origin="chat"),
            confirmed=True,
            record_entry=lambda entry: (captured.update(entry), {"sequence": 1})[1],
            create_worktree=lambda *args: "wt",
        )
        assert captured["origin"] == "chat"
        assert captured["runId"].startswith("run_")
        assert captured["humanActor"] == "vikram@example.com"
