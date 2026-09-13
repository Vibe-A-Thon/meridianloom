"""The evidence gate applies the rule written before the data (MV5 preparation).

`docs/evidence-gate.md` fixed the thresholds on 12 September 2026. The
instrument that scores the study was older than that document and applied a
different, lower bar, and its tests could not tell. Their fixtures invented a
gate decision of `block` and a `subject` column. The Governor writes neither, so
on a real ledger the instrument counted no gate stop and saw no approval, and
every test stayed green.

So these tests are built the other way round. Ledger-derived measures are read
from rows the real Governor writes: `gate.evaluate` and `gate.approve` are driven
through a real sidecar, and the one shape written by hand (a detected revert) is
copied from the server's own entry. The decision rule is tested as a truth table
over the three states, because every branch of §4 is a published outcome and a
branch nobody exercised is a branch nobody checked.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.metrics import evidence_gate as eg
from meridian_core.metrics.evidence_study import (
    STUDY_SCHEMA,
    missing_recorded_fields,
    validate_study,
)
from meridian_core.rejection.detector import REASON_REVERTED
from meridian_core.server import SidecarServer

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREGISTRATION = REPO_ROOT / "docs" / "evidence-gate.md"
TEMPLATE = REPO_ROOT / "docs" / "baselines" / "evidence-gate" / "study-record.template.json"

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles:
  review:
    criteria:
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
"""

ROLES_TEXT = """
version: 1
defaultRole: contributor
roles:
  approver:
    permissions: [approve, delegate]
  contributor:
    permissions: []
delegation:
  maxChainDepth: 2
  maxTtlDays: 30
"""


# -- a real Governor -----------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    for key, value in (
        ("GIT_AUTHOR_NAME", "Fixture"),
        ("GIT_AUTHOR_EMAIL", "fixture@example.com"),
        ("GIT_COMMITTER_NAME", "Fixture"),
        ("GIT_COMMITTER_EMAIL", "fixture@example.com"),
    ):
        env.setdefault(key, value)
    result = subprocess.run(
        [
            "git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main", "-c", "user.name=Ada Lovelace",
            "-c", "user.email=ada@example.com", *args,
        ],
        cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture()
def server(tmp_path: Path) -> SidecarServer:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Ada Lovelace")
    git(repo, "config", "user.email", "ada@example.com")
    (repo / "app.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    policy = repo / ".meridian" / "policy"
    policy.mkdir(parents=True)
    (policy / "governance.yaml").write_text(PACK_TEXT, encoding="utf-8")
    (policy / "roles.yaml").write_text(ROLES_TEXT, encoding="utf-8")
    sidecar = SidecarServer(ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()))
    sidecar.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "handshake",
        "params": {
            "protocolVersion": protocol.PROTOCOL_VERSION, "client": "pytest",
            "workspaceDir": str(repo), "tiers": ["flight-recorder", "governor"],
        },
    })
    sidecar.test_repo = repo  # type: ignore[attr-defined]
    return sidecar


def call(server: SidecarServer, method: str, params: dict) -> dict:
    response = server.handle_message({"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
    assert "result" in response, response
    return response["result"]


def diff(server: SidecarServer, story: str) -> int:
    return server.ledger.append({
        "story_id": story, "phase": "build", "loop_id": "L2-task", "loop_iteration": 1,
        "actor_id": "developer-agent", "actor_version": "1.0.0", "actor_kind": "external",
        "policy_version": "f0", "action_type": "diff", "decision": "proposed",
    }).sequence


def gate_stop(server: SidecarServer, story: str) -> int:
    """A gate stop exactly as the Governor records one."""
    result = call(server, "gate.evaluate", {"storyId": story, "gate": "review", "packet": {}})
    assert result["decision"] == "block", result
    return max(row["seq"] for row in server.ledger.query(action_type="gate", story_id=story))


def approve(server: SidecarServer, story: str | None = None) -> str:
    commit = git(server.test_repo, "rev-parse", "main").strip()  # type: ignore[attr-defined]
    params = {"subject": "main", "commit": commit, "role": "approver"}
    if story:
        params["storyId"] = story
    call(server, "gate.approve", params)
    return commit


def reverted(server: SidecarServer, story: str, commit: str) -> int:
    """The entry trust/detectRejections writes for a revert (server.py)."""
    return server.ledger.append({
        "story_id": story, "phase": "review", "loop_id": "rejection", "loop_iteration": 0,
        "actor_id": "developer-agent", "actor_version": "1.0.0", "actor_kind": "external",
        "policy_version": "f0", "vendor": "meridian", "action_type": "rejection",
        "decision": "rejected", "rework_reason": "other", "rejected_commit": commit,
        "rejecting_commit": "b" * 40,
        "tool_calls": [{"shape": REASON_REVERTED, "paths": ["app.txt"], "linesRejected": 1,
                        "rejectedAt": "2026-09-20T10:00:00Z", "reasonNote": ""}],
    }).sequence


ARM_A = [f"A-{i}" for i in range(6)]
ARM_B = [f"B-{i}" for i in range(7)]
ARM_C = [f"C-{i}" for i in range(7)]


def study(**sections) -> dict:
    """Twenty stories allocated across three arms, registered before data."""
    record = {
        "studyId": "pilot-1",
        "preregistration": {
            "registeredAt": "2026-09-14T09:00:00Z",
            "thresholdsDigest": eg.thresholds_digest(),
            "firstStoryMeasuredAt": "2026-09-15T09:00:00Z",
        },
        "allocation": (
            [{"storyId": s, "arm": "A", "kind": "greenfield"} for s in ARM_A]
            + [{"storyId": s, "arm": "B", "kind": "greenfield"} for s in ARM_B]
            + [{"storyId": s, "arm": "C", "kind": "greenfield"} for s in ARM_C]
        ),
    }
    record.update(sections)
    assert validate_study(record) == [], validate_study(record)
    return record


def worked(server: SidecarServer) -> None:
    """Every story in a Meridian arm left at least one row."""
    for story in ARM_B + ARM_C:
        diff(server, story)


def adjudicate(sequence: int, *, real: bool = True, missed: bool = True, ran_gate: bool = False) -> dict:
    return {
        "gateSequence": sequence, "realDefect": real, "caughtByAgentProcess": not missed,
        "reviewer": "reviewer-1", "reviewerRanGate": ran_gate,
    }


def gate_report(server: SidecarServer, record: dict | None = None, **kwargs) -> dict:
    return eg.compute_evidence_gate(server.ledger, study=record, **kwargs)


# -- §4, the rule --------------------------------------------------------------


def statuses(**overrides: str) -> dict:
    measures = {m: {"id": m, "status": eg.MET, "note": ""} for m in eg.THRESHOLDS}
    for measure_id, status in overrides.items():
        measures[measure_id]["status"] = status
    return measures


class TestTheRuleIsTheOneWrittenInAdvance:
    def test_go_needs_every_threshold_and_o1(self):
        assert eg.decide(20, statuses())["verdict"] == eg.GO

    def test_either_p1_or_p2_is_enough_for_go(self):
        assert eg.decide(20, statuses(P1=eg.NOT_MET))["verdict"] == eg.GO
        assert eg.decide(20, statuses(P2=eg.NOT_MET))["verdict"] == eg.GO

    def test_unmeasured_query_usage_blocks_go_instead_of_being_waved_through(self):
        # The old instrument returned GO here and asked someone to "confirm it
        # out of band". §5: unmeasured is never satisfied.
        decision = eg.decide(20, statuses(P4=eg.UNMEASURED))
        assert decision["verdict"] == eg.INSUFFICIENT
        assert decision["undecidedOutcome"] == eg.GO
        assert decision["unmeasured"] == ["P4"]

    def test_unmeasured_change_failure_rate_is_not_treated_as_not_worse(self):
        decision = eg.decide(20, statuses(P3=eg.UNMEASURED))
        assert decision["verdict"] == eg.INSUFFICIENT
        assert "P3" in decision["unmeasured"]

    def test_stop_when_the_governance_layer_holds_and_o1_does_not(self):
        decision = eg.decide(20, statuses(O1=eg.NOT_MET))
        assert decision["verdict"] == eg.STOP
        assert "success" in decision["reasons"][0]

    def test_stop_can_rest_on_an_o1_nobody_argued(self):
        assert eg.decide(20, statuses(O1=eg.UNMEASURED))["verdict"] == eg.STOP

    def test_pivot_when_nobody_queries_but_the_trust_instruments_are_used(self):
        assert eg.decide(20, statuses(P4=eg.NOT_MET, P5=eg.MET))["verdict"] == eg.PIVOT

    def test_kill_when_retention_fails(self):
        assert eg.decide(20, statuses(P6=eg.NOT_MET))["verdict"] == eg.KILL

    def test_kill_when_stability_fails(self):
        assert eg.decide(20, statuses(P3=eg.NOT_MET))["verdict"] == eg.KILL

    def test_kill_when_the_tax_rises_and_nothing_was_caught(self):
        decision = eg.decide(20, statuses(C2=eg.NOT_MET, P1=eg.NOT_MET, P2=eg.NOT_MET))
        assert decision["verdict"] == eg.KILL

    def test_the_old_instrument_had_no_kill_at_all(self):
        # Retention failed and stability failed; there is no reading of §4
        # under which this is anything but KILL.
        decision = eg.decide(20, statuses(P6=eg.NOT_MET, P3=eg.NOT_MET, P4=eg.NOT_MET, P5=eg.NOT_MET))
        assert decision["verdict"] == eg.KILL

    def test_pivot_is_tried_before_kill_because_section_4_is_ordered(self):
        decision = eg.decide(20, statuses(P4=eg.NOT_MET, P5=eg.MET, P6=eg.NOT_MET))
        assert decision["verdict"] == eg.PIVOT

    def test_an_undecided_earlier_outcome_is_never_skipped_to_reach_a_later_one(self):
        # P6 failed, which is KILL, but PIVOT might apply: P4 is unmeasured.
        decision = eg.decide(20, statuses(P6=eg.NOT_MET, P4=eg.UNMEASURED))
        assert decision["verdict"] == eg.INSUFFICIENT
        assert decision["undecidedOutcome"] == eg.PIVOT

    def test_a_combination_no_outcome_names_is_reported_not_rounded(self):
        decision = eg.decide(20, statuses(P1=eg.NOT_MET, P2=eg.NOT_MET))
        assert decision["verdict"] == eg.UNCLASSIFIED

    def test_fewer_than_twenty_stories_is_no_answer(self):
        decision = eg.decide(19, statuses())
        assert decision["verdict"] == eg.INSUFFICIENT
        assert "19 of 20" in decision["reasons"][0]


# -- the measures, from what the Governor actually writes -----------------------


class TestGateStopsAreTheRowsTheGovernorWrites:
    def test_a_real_gate_stop_is_counted(self, server):
        # The old instrument looked for decision == "block"; the Governor
        # records "rejected". On this ledger it would have counted zero.
        stops = [gate_stop(server, "C-0"), gate_stop(server, "C-1")]
        report = gate_report(server, study(adjudications=[]))
        assert report["context"]["gateStops"] == 2
        assert report["measures"]["P1"]["gateStops"] == 2
        assert sorted(stops) == sorted(
            row["seq"] for row in server.ledger.query(action_type="gate")
        )

    def test_three_independently_confirmed_defects_meet_p1(self, server):
        stops = [gate_stop(server, f"C-{i}") for i in range(4)]
        report = gate_report(server, study(adjudications=[adjudicate(s) for s in stops[:3]]))
        p1 = report["measures"]["P1"]
        assert p1["status"] == eg.MET
        assert p1["confirmed"] == 3

    def test_one_confirmed_block_is_not_p1(self, server):
        # The old instrument returned GO on a single blocked evaluation.
        stop = gate_stop(server, "C-0")
        report = gate_report(server, study(adjudications=[adjudicate(stop)]))
        assert report["measures"]["P1"]["status"] == eg.NOT_MET

    def test_a_reviewer_who_ran_the_gate_does_not_confirm_a_defect(self, server):
        stops = [gate_stop(server, f"C-{i}") for i in range(3)]
        record = study(adjudications=[
            adjudicate(stops[0]), adjudicate(stops[1]), adjudicate(stops[2], ran_gate=True),
        ])
        p1 = gate_report(server, record)["measures"]["P1"]
        assert p1["confirmed"] == 2
        # Not NOT_MET: an independent reviewer could still confirm the third.
        assert p1["status"] == eg.UNMEASURED

    def test_a_defect_the_agent_already_caught_is_not_uniquely_caught(self, server):
        stops = [gate_stop(server, f"C-{i}") for i in range(3)]
        record = study(adjudications=[adjudicate(s, missed=(s != stops[2])) for s in stops])
        assert gate_report(server, record)["measures"]["P1"]["status"] == eg.NOT_MET

    def test_an_adjudication_of_something_that_was_not_a_stop_is_refused(self, server):
        not_a_stop = diff(server, "C-0")
        stops = [gate_stop(server, f"C-{i}") for i in range(2)]
        record = study(adjudications=[adjudicate(s) for s in stops] + [adjudicate(not_a_stop)])
        p1 = gate_report(server, record)["measures"]["P1"]
        assert p1["refusedAdjudications"] == [not_a_stop]
        assert p1["status"] == eg.NOT_MET

    def test_a_stop_outside_arm_c_is_not_counted(self, server):
        gate_stop(server, "B-0")
        report = gate_report(server, study(adjudications=[]))
        assert report["context"]["gateStops"] == 0


class TestFalseBlocks:
    def test_a_share_above_fifteen_percent_fails_c1(self, server):
        stops = [gate_stop(server, f"C-{i}") for i in range(4)]
        record = study(adjudications=[adjudicate(stops[0], real=False)] + [adjudicate(s) for s in stops[1:]])
        c1 = gate_report(server, record)["measures"]["C1"]
        assert c1["status"] == eg.NOT_MET
        assert c1["bounds"] == [0.25, 0.25]

    def test_unsettled_stops_count_against_c1_until_they_are_settled(self, server):
        stops = [gate_stop(server, f"C-{i % 7}") for i in range(4)]
        record = study(adjudications=[adjudicate(s) for s in stops[:3]])
        c1 = gate_report(server, record)["measures"]["C1"]
        assert c1["bounds"] == [0.0, 0.25]
        assert c1["status"] == eg.UNMEASURED

    def test_c1_is_met_when_even_the_upper_bound_is_under_the_ceiling(self, server):
        stops = [gate_stop(server, f"C-{i % 7}") for i in range(10)]
        record = study(adjudications=[adjudicate(s) for s in stops[:9]])
        c1 = gate_report(server, record)["measures"]["C1"]
        assert c1["bounds"] == [0.0, 0.1]
        assert c1["status"] == eg.MET

    def test_no_stops_leaves_the_share_undefined(self, server):
        report = gate_report(server, study(adjudications=[]))
        assert report["measures"]["C1"]["status"] == eg.UNMEASURED


class TestRejectionRateAgainstArmA:
    def test_arm_c_lower_in_every_split_meets_p2(self, server):
        proposed = [diff(server, "C-0") for _ in range(4)]
        reverted(server, "C-0", "c" * 40)
        server.ledger.append({
            "story_id": "C-0", "phase": "review", "loop_id": "rejection", "loop_iteration": 0,
            "actor_id": "developer-agent", "actor_version": "1", "actor_kind": "external",
            "policy_version": "f0", "action_type": "rejection", "decision": "rejected",
            "rejected_sequence": proposed[0],
        })
        record = study(armA={"method": "team tracker", "rejectionRate": {"greenfield": {"rejected": 5, "proposed": 10}}})
        p2 = gate_report(server, record)["measures"]["P2"]
        assert p2["splits"]["greenfield"]["armC"]["rate"] == 0.25
        assert p2["status"] == eg.MET

    def test_a_split_measured_in_only_one_arm_leaves_p2_unmeasured(self, server):
        diff(server, "C-0")
        record = study(armA={"method": "team tracker", "rejectionRate": {
            "greenfield": {"rejected": 5, "proposed": 10},
            "brownfield": {"rejected": 5, "proposed": 10},
        }})
        assert gate_report(server, record)["measures"]["P2"]["status"] == eg.UNMEASURED

    def test_arm_c_no_lower_fails_p2(self, server):
        proposed = diff(server, "C-0")
        server.ledger.append({
            "story_id": "C-0", "phase": "review", "loop_id": "rejection", "loop_iteration": 0,
            "actor_id": "developer-agent", "actor_version": "1", "actor_kind": "external",
            "policy_version": "f0", "action_type": "rejection", "decision": "rejected",
            "rejected_sequence": proposed,
        })
        record = study(armA={"method": "team tracker", "rejectionRate": {"greenfield": {"rejected": 1, "proposed": 2}}})
        assert gate_report(server, record)["measures"]["P2"]["status"] == eg.NOT_MET


class TestChangeFailureRate:
    def test_a_revert_of_a_gated_merge_counts_against_the_baseline(self, server):
        commit = approve(server, "C-0")
        reverted(server, "C-0", commit)
        record = study(baselineChangeFailureRate={"rate": 0.2, "method": "DORA export, Q2"})
        p3 = gate_report(server, record)["measures"]["P3"]
        assert (p3["gatedMerges"], p3["reverted"], p3["value"]) == (1, 1, 1.0)
        assert p3["status"] == eg.NOT_MET

    def test_an_unreverted_gated_merge_holds_against_the_baseline(self, server):
        approve(server, "C-0")
        record = study(baselineChangeFailureRate={"rate": 0.2, "method": "DORA export, Q2"})
        assert gate_report(server, record)["measures"]["P3"]["status"] == eg.MET

    def test_a_reverted_approval_nobody_allocated_leaves_p3_unmeasured(self, server):
        approve(server, "C-0")
        stray = approve(server)  # story id defaults to gate:main, in no arm
        reverted(server, "gate:main", stray)
        record = study(baselineChangeFailureRate={"rate": 0.9, "method": "DORA export, Q2"})
        assert gate_report(server, record)["measures"]["P3"]["status"] == eg.UNMEASURED

    def test_no_baseline_is_no_comparison(self, server):
        approve(server, "C-0")
        p3 = gate_report(server, study())["measures"]["P3"]
        assert p3["status"] == eg.UNMEASURED
        assert "cannot know" in p3["note"]


class TestApprovalHygiene:
    def test_the_approval_subject_is_read_from_what_the_governor_recorded(self, server):
        # The subject lives in the encrypted detail. The old instrument read it
        # from the row, found nothing, and reported that no approval existed.
        approve(server, "C-0")
        seen: list[str] = []

        def hygiene(subject: str) -> list[str]:
            seen.append(subject)
            return []

        record = study(hygieneDetermination={
            "systematicRubberStamping": False, "reviewer": "reviewer-1",
            "basis": "time-on-artifact sampled for every approval",
        })
        report = gate_report(server, record, hygiene=hygiene)
        assert seen == ["main"]
        assert report["measures"]["C3"]["ledgerSignals"]["assessed"] is True
        assert report["measures"]["C3"]["status"] == eg.MET

    def test_a_finding_of_rubber_stamping_fails_c3(self, server):
        record = study(hygieneDetermination={
            "systematicRubberStamping": True, "reviewer": "reviewer-1", "basis": "bulk approvals",
        })
        assert gate_report(server, record)["measures"]["C3"]["status"] == eg.NOT_MET


class TestWhatOnlyPeopleCanSupply:
    def test_without_a_record_nothing_that_needs_people_is_satisfied(self, server):
        report = gate_report(server)
        assert report["recommendation"]["verdict"] == eg.INSUFFICIENT
        assert "no study record" in report["recommendation"]["reasons"][0]
        for measure_id in ("P1", "P2", "P4", "P5", "P6", "C1", "C2", "C3", "O1"):
            assert report["measures"][measure_id]["status"] == eg.UNMEASURED

    def test_one_engineer_week_without_a_query_fails_p4(self, server):
        record = study(provenanceQueries={"method": "weekly survey", "weeks": [
            {"week": 1, "engineers": [{"engineer": "eng-1", "queries": 3}, {"engineer": "eng-2", "queries": 1}]},
            {"week": 2, "engineers": [{"engineer": "eng-1", "queries": 2}, {"engineer": "eng-2", "queries": 0}]},
        ]})
        p4 = gate_report(server, record)["measures"]["P4"]
        assert p4["status"] == eg.NOT_MET
        assert "week 2: eng-2" in p4["note"]

    def test_a_decision_change_naming_an_entry_outside_the_scope_is_not_counted(self, server):
        record = study(trustDecisionChanges={"method": "retro notes", "instances": [
            {"date": "2026-09-20", "changed": "autonomy_tier", "description": "lowered atlas", "ledgerSequence": 999},
        ]})
        p5 = gate_report(server, record)["measures"]["P5"]
        assert p5["status"] == eg.NOT_MET
        assert p5["refused"] == 1

    @pytest.mark.parametrize(("kept", "original", "expected"), [
        (2, 5, eg.MET), (1, 5, eg.NOT_MET), (2, 6, eg.NOT_MET), (3, 6, eg.MET),
    ])
    def test_retention_needs_two_and_two_in_five(self, server, kept, original, expected):
        record = study(retention={"originalTesters": original, "stillUsingAtWeek8": kept, "method": "asked"})
        assert gate_report(server, record)["measures"]["P6"]["status"] == expected

    def test_review_time_twenty_percent_above_arm_a_is_the_ceiling(self, server):
        at = study(reviewTime={"method": "stopwatch", "armA": [10, 10], "armC": [12, 12]})
        over = study(reviewTime={"method": "stopwatch", "armA": [10, 10], "armC": [12.5, 12.5]})
        assert gate_report(server, at)["measures"]["C2"]["status"] == eg.MET
        assert gate_report(server, over)["measures"]["C2"]["status"] == eg.NOT_MET

    def test_ledger_latency_is_shown_beside_c2_and_never_decides_it(self, server):
        gate_stop(server, "C-0")
        approve(server, "C-0")
        c2 = gate_report(server, study())["measures"]["C2"]
        assert c2["status"] == eg.UNMEASURED
        assert c2["ledgerLatencyProxy"]["usedForC2"] is False


class TestAStudyThroughTheRealGovernor:
    def full_study(self, server: SidecarServer, **overrides) -> dict:
        worked(server)
        stops = [gate_stop(server, f"C-{i}") for i in range(3)]
        approve(server, "C-0")
        sections = dict(
            adjudications=[adjudicate(s) for s in stops],
            armA={"method": "team tracker", "rejectionRate": {"greenfield": {"rejected": 5, "proposed": 10}}},
            baselineChangeFailureRate={"rate": 0.2, "method": "DORA export, Q2"},
            reviewTime={"method": "stopwatch", "armA": [30, 40], "armC": [33, 35]},
            hygieneDetermination={"systematicRubberStamping": False, "reviewer": "reviewer-2", "basis": "sampled"},
            provenanceQueries={"method": "weekly survey", "weeks": [
                {"week": 1, "engineers": [{"engineer": "eng-1", "queries": 2}]},
            ]},
            trustDecisionChanges={"method": "retro notes", "instances": [
                {"date": "2026-09-20", "changed": "agent_choice", "description": "moved tests to another agent"},
            ]},
            retention={"originalTesters": 5, "stillUsingAtWeek8": 3, "method": "asked"},
            orchestraCase={"determination": "satisfied", "taskClass": "legacy COBOL migration",
                           "evidence": "rejection rate 60% on that class across both arms"},
        )
        sections.update(overrides)
        return study(**sections)

    def test_a_study_that_meets_every_threshold_reaches_go(self, server):
        report = gate_report(server, self.full_study(server))
        assert {m: v["status"] for m, v in report["measures"].items()} == {
            "P1": eg.MET, "P2": eg.MET, "P3": eg.MET, "P4": eg.MET, "P5": eg.MET,
            "P6": eg.MET, "C1": eg.MET, "C2": eg.MET, "C3": eg.MET, "O1": eg.MET,
        }
        assert report["stories"]["total"] == 20
        assert report["recommendation"]["verdict"] == eg.GO
        assert report["preregistration"]["state"] == "intact"

    def test_the_same_study_without_o1_is_a_stop(self, server):
        record = self.full_study(server, orchestraCase={"determination": "not_satisfied"})
        assert gate_report(server, record)["recommendation"]["verdict"] == eg.STOP

    def test_a_story_in_a_meridian_arm_with_no_rows_does_not_count(self, server):
        record = self.full_study(server)
        record["allocation"].append({"storyId": "C-ghost", "arm": "C", "kind": "greenfield"})
        record["allocation"] = [e for e in record["allocation"] if e["storyId"] != "A-0"]
        report = gate_report(server, record)
        assert report["stories"]["allocatedButAbsentFromLedger"] == ["C-ghost"]
        assert report["stories"]["total"] == 19
        assert report["recommendation"]["verdict"] == eg.INSUFFICIENT


# -- §5, the preregistration ---------------------------------------------------


class TestThePreregistrationHolds:
    def test_the_instrument_applies_the_numbers_the_document_fixed(self):
        text = PREREGISTRATION.read_text(encoding="utf-8")

        def row(measure_id: str) -> str:
            match = re.search(rf"^\| \*\*{measure_id}\*\* \|.*$", text, re.MULTILINE)
            assert match, f"{measure_id} is not in {PREREGISTRATION.name}"
            return match.group(0)

        assert int(re.search(r"At least (\d+) across 20 stories", row("P1")).group(1)) == eg.THRESHOLDS["P1"]["atLeast"]
        assert int(re.search(r"At least (\d+) per engineer per week", row("P4")).group(1)) == eg.THRESHOLDS["P4"]["atLeast"]
        assert int(re.search(r"At least (\d+) recorded instance", row("P5")).group(1)) == eg.THRESHOLDS["P5"]["atLeast"]
        kept, of = re.search(r"At least (\d+) of (\d+)", row("P6")).groups()
        assert (int(kept), int(of)) == (eg.THRESHOLDS["P6"]["atLeast"], eg.THRESHOLDS["P6"]["ofOriginal"])
        assert int(re.search(r"No more than (\d+)% of gate stops", row("C1")).group(1)) / 100 == eg.THRESHOLDS["C1"]["atMostShare"]
        assert 1 + int(re.search(r"No more than (\d+)% above", row("C2")).group(1)) / 100 == eg.THRESHOLDS["C2"]["atMostRatio"]
        assert "Twenty stories" in text and eg.REQUIRED_STORIES == 20

    def test_every_reading_the_instrument_applies_is_written_in_the_document(self):
        text = PREREGISTRATION.read_text(encoding="utf-8")
        for key, reading in eg.READINGS.items():
            assert reading in text, f"reading {key!r} is applied but not written in §6"

    def test_an_intact_registration_is_reported_intact(self, server):
        assert gate_report(server, study())["preregistration"]["state"] == "intact"

    def test_a_threshold_changed_after_registration_is_declared(self, server, monkeypatch):
        stops = [gate_stop(server, f"C-{i}") for i in range(2)]
        record = study(adjudications=[adjudicate(s) for s in stops])
        monkeypatch.setitem(eg.THRESHOLDS["P1"], "atLeast", 2)
        report = gate_report(server, record)
        # The lowered bar is applied — the arithmetic reads the thresholds — and
        # the result says in its first line that it cannot be trusted.
        assert report["measures"]["P1"]["status"] == eg.MET
        assert report["preregistration"]["state"] == "digest_mismatch"
        assert report["recommendation"]["invalidated"] is True
        assert "not intact" in report["recommendation"]["reasons"][0]

    def test_a_reading_changed_after_registration_is_declared_too(self, server, monkeypatch):
        record = study()
        monkeypatch.setitem(eg.READINGS, "P4", "Sustained means most weeks.")
        assert gate_report(server, record)["preregistration"]["state"] == "digest_mismatch"

    def test_registering_after_the_first_story_was_measured_is_declared(self, server):
        record = study()
        record["preregistration"]["registeredAt"] = "2026-09-16T09:00:00Z"
        report = gate_report(server, record)
        assert report["preregistration"]["state"] == "registered_after_data"
        assert report["recommendation"]["invalidated"] is True


# -- the study record ----------------------------------------------------------


class TestTheStudyRecord:
    def test_the_shipped_template_cannot_be_scored_as_a_study(self):
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        assert validate_study(template), "a blank template must never validate as a study"

    def test_an_email_address_where_a_person_is_named_is_refused(self):
        record = study()
        record["adjudications"] = [adjudicate(1)]
        record["adjudications"][0]["reviewer"] = "ada@example.com"
        problems = validate_study(record)
        assert any("pseudonym" in problem for problem in problems)

    def test_a_story_in_two_arms_is_refused(self):
        record = study()
        record["allocation"].append({"storyId": "A-0", "arm": "C", "kind": "greenfield"})
        assert any("more than once" in p for p in validate_study(record))

    def test_o1_satisfied_by_assertion_alone_is_refused(self):
        record = study()
        record["orchestraCase"] = {"determination": "satisfied"}
        assert any("assertion" in p for p in validate_study(record))

    def test_an_invalid_record_decides_nothing(self, server):
        record = study()
        record["retention"] = {"originalTesters": 5, "stillUsingAtWeek8": 6, "method": "asked"}
        report = gate_report(server, record)
        assert report["study"]["valid"] is False
        assert report["recommendation"]["verdict"] == eg.INSUFFICIENT
        assert "does not validate" in report["recommendation"]["reasons"][0]

    def test_fr_m46_14_fields_the_record_lacks_are_published_as_missing(self):
        assert missing_recorded_fields(study()) == sorted([
            "30-day regressions", "accepted-change cost", "agent and model configuration versions",
            "defects caught", "false blocks", "human time", "independent review",
        ])

    def test_the_schema_is_draft_7(self):
        assert STUDY_SCHEMA["$schema"] == "http://json-schema.org/draft-07/schema#"


# -- FR-M46-04, beside the rule ------------------------------------------------


class TestFirstValue:
    def sessions(self, *minutes):
        return [{"participant": f"p-{i}", "minutesToFirstAnswer": m} for i, m in enumerate(minutes)]

    def test_four_of_five_within_fifteen_minutes(self):
        record = study(firstValue={"sessions": self.sessions(5, 9, 14, 15, 40)})
        assert eg.score_first_value(record)["onboarding"]["status"] == eg.MET

    def test_a_session_that_never_reached_an_answer_counts_against(self):
        record = study(firstValue={"sessions": self.sessions(5, 9, 14, None, 40)})
        assert eg.score_first_value(record)["onboarding"]["status"] == eg.NOT_MET

    def test_four_sessions_are_not_five(self):
        record = study(firstValue={"sessions": self.sessions(5, 9, 14, 15)})
        assert eg.score_first_value(record)["onboarding"]["status"] == eg.UNMEASURED

    def test_eight_of_ten_review_tasks(self):
        tasks = [{"participant": f"p-{i}", "identifiedRealBlockingRisk": i < 8} for i in range(10)]
        assert eg.score_first_value(study(firstValue={"reviewTasks": tasks}))["reviewTasks"]["status"] == eg.MET
        tasks[7]["identifiedRealBlockingRisk"] = False
        assert eg.score_first_value(study(firstValue={"reviewTasks": tasks}))["reviewTasks"]["status"] == eg.NOT_MET


# -- the editor screen's path --------------------------------------------------


class TestTheEditorScreenPath:
    def test_a_valid_role_pack_attaches_the_ledger_hygiene_signals(self, server):
        result = call(server, "evidence/gate", {})
        assert result["measures"]["C3"]["ledgerSignals"]["assessed"] is True

    def test_a_fail_closed_role_pack_is_not_reported_as_a_clean_hygiene_check(self, server):
        # assess_hygiene returns no warnings for a fail-closed pack, because it
        # checks nothing. Passed through, that read as "assessed, no signals".
        roles = server.test_repo / ".meridian" / "policy" / "roles.yaml"  # type: ignore[attr-defined]
        roles.write_text("roles: [this is not a role pack\n", encoding="utf-8")
        result = call(server, "evidence/gate", {})
        assert result["measures"]["C3"]["ledgerSignals"]["assessed"] is False
