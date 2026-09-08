"""Steer & clarify over hosted ACP sessions (FR-M25-01/02/03/04/06;
F1 Workstream D tasks 17-18).

The governor.steer capability is the durable half of the M25 steering
surface. The extension host owns the wire (injecting a second
session/prompt into the running ACP session); the sidecar owns the
record, and every steer/* RPC is ledger-recorded BEFORE it returns
(FR-M10-08):

- steer.send    -> action_type ``steer`` (who steered — the resolved human
  identity, FR-M20-01 — what, when, into which session);
- steer/question -> ``clarifying_question`` — durable BEFORE the human can
  answer (options + the agent's recommendation, FR-M25-02);
- steer/answer  -> ``clarifying_answer`` linked to the question entry; the
  recorded answer is what resumes the loop;
- steer/escalate -> ``escalation`` for confidence below the per-class
  threshold (FR-M25-03);
- steer/accept  -> ``partial_acceptance`` — per file/hunk accepted or
  reworked in one action (FR-M25-04), queryable via steer/acceptanceStatus;
- steer/plan    -> ``plan_output`` — dry-run planner output (FR-M25-06);
- steer/status  -> the honest capability payload: hosted true only when a
  hosted session_begin exists; observe-only sessions report hosted false
  and every mutating steer RPC refuses with the structured NOT_HOSTED
  error (task 18 — an honest refusal, never a silent failure or a dead
  control).

G5: governor disabled -> TIER_DISABLED, recorder untouched.
"""

from __future__ import annotations

import pytest

from meridian_core import protocol
from meridian_core.governance.identity import HumanIdentity, StaticIdentityProvider
from meridian_core.identity import IdentityUnavailableError
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

HUMAN = HumanIdentity(name="Grace Hopper", email="grace@example.com")


@pytest.fixture()
def server(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(
        ledger=ledger, identity_provider=StaticIdentityProvider(HUMAN)
    )
    yield instance
    ledger.close()


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    assert response is not None and response["id"] == request_id
    return response


def result(server, method, params=None):
    response = call(server, 7, method, params or {})
    assert "error" not in response, response.get("error")
    return response["result"]


def error(server, method, params=None):
    response = call(server, 9, method, params or {})
    assert "error" in response, response
    return response["error"]


def enable_governor(server: SidecarServer) -> None:
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "method": "tiers/set",
            "params": {"tiers": ["flight-recorder", "governor"]},
        }
    )


def begin(server, session_id="sess-1", agent_id="gemini", **extra):
    params = {
        "agentId": agent_id,
        "agentVersion": "0.30.0",
        "sessionId": session_id,
        "cwd": "/work",
    }
    params.update(extra)
    return result(server, "acp/sessionBegin", params)


STEER_METHODS = [
    "steer.send",
    "steer/question",
    "steer/answer",
    "steer/escalate",
    "steer/accept",
    "steer/acceptanceStatus",
    "steer/status",
    "steer/plan",
]


class TestTierGate:
    @pytest.mark.parametrize("method", STEER_METHODS)
    def test_governor_disabled_refuses(self, server, method):
        response = call(server, 1, method, {"sessionId": "s"})
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert response["error"]["data"]["tier"] == "governor"


class TestSteerSend:
    def test_records_who_what_when_before_returning(self, server):
        enable_governor(server)
        begin(server, session_id="sess-steer")
        ack = result(
            server,
            "steer.send",
            {"sessionId": "sess-steer", "message": "Use the existing parser."},
        )
        assert ack == {"accepted": True, "sequence": ack["sequence"]}
        entries = result(
            server,
            "ledger.query",
            {"storyId": "acp:sess-steer", "actionType": "steer"},
        )["entries"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["humanActor"] == "Grace Hopper <grace@example.com>"
        assert entry["actorId"] == "gemini"  # attributed to the hosted agent's story
        assert entry["externalSessionId"] == "sess-steer"
        assert entry["vendor"] == "acp"
        assert entry["observationConfidence"] == "direct"

    def test_observe_only_session_refuses_with_structured_not_hosted(self, server):
        enable_governor(server)
        failure = error(
            server,
            "steer.send",
            {"sessionId": "obs-9", "message": "stop"},
        )
        assert failure["code"] == protocol.ERROR_NOT_HOSTED
        assert "observed" in failure["message"]
        assert "not hosted" in failure["message"]
        assert failure["data"]["hosted"] is False
        assert failure["data"]["sessionId"] == "obs-9"
        # Nothing was recorded for a session Meridian does not host.
        status = result(server, "steer/status", {"sessionId": "obs-9"})
        assert status["hosted"] is False
        entries = result(
            server, "ledger.query", {"storyId": "acp:obs-9"}
        )["entries"]
        assert entries == []

    def test_session_that_ended_is_still_honest_history(self, server):
        enable_governor(server)
        begin(server, session_id="sess-ended")
        result(server, "acp/sessionEnd", {"sessionId": "sess-ended"})
        # The hosted begin is on record: steer records against it. Liveness
        # is the extension registry's question, not the ledger's.
        ack = result(
            server, "steer.send", {"sessionId": "sess-ended", "message": "x"}
        )
        assert ack["accepted"] is True


class TestClarifyingQuestion:
    def test_question_is_durable_before_any_answer(self, server):
        enable_governor(server)
        begin(server, session_id="sess-q")
        asked = result(
            server,
            "steer/question",
            {
                "sessionId": "sess-q",
                "question": "Which parser should I extend?",
                "options": [
                    {"optionId": "a", "name": "The JSON parser"},
                    {"optionId": "b", "name": "The YAML parser", "recommended": True},
                ],
                "toolCallId": "tc-1",
            },
        )
        assert asked["accepted"] is True
        entries = result(
            server,
            "ledger.query",
            {"storyId": "acp:sess-q", "actionType": "clarifying_question"},
        )["entries"]
        assert len(entries) == 1
        assert entries[0]["actorId"] == "gemini"

    def test_answer_links_to_the_question_and_resumes(self, server):
        enable_governor(server)
        begin(server, session_id="sess-q2")
        asked = result(
            server,
            "steer/question",
            {"sessionId": "sess-q2", "question": "Extend which parser?"},
        )
        answered = result(
            server,
            "steer/answer",
            {
                "sessionId": "sess-q2",
                "questionSequence": asked["sequence"],
                "selectedOptionId": "a",
            },
        )
        assert answered["accepted"] is True
        assert answered["resumed"] is True
        entries = result(
            server,
            "ledger.query",
            {"storyId": "acp:sess-q2", "actionType": "clarifying_answer"},
        )["entries"]
        assert len(entries) == 1
        assert entries[0]["humanActor"] == "Grace Hopper <grace@example.com>"

    def test_cancelled_answer_is_recorded_honestly(self, server):
        enable_governor(server)
        begin(server, session_id="sess-q3")
        asked = result(
            server,
            "steer/question",
            {"sessionId": "sess-q3", "question": "Proceed?"},
        )
        answered = result(
            server,
            "steer/answer",
            {
                "sessionId": "sess-q3",
                "questionSequence": asked["sequence"],
                "cancelled": True,
            },
        )
        assert answered["resumed"] is True
        detail = result(server, "ledger.getEntry", {"sequence": answered["sequence"]})
        assert detail["inputAvailable"] is True
        assert '"cancelled": true' in detail["input"]

    def test_answer_to_unknown_question_is_a_refusal(self, server):
        enable_governor(server)
        begin(server, session_id="sess-q4")
        failure = error(
            server,
            "steer/answer",
            {"sessionId": "sess-q4", "questionSequence": 999},
        )
        assert failure["code"] == protocol.INVALID_PARAMS
        assert "no recorded clarifying question" in failure["message"]

    def test_question_on_observed_session_refuses_not_hosted(self, server):
        enable_governor(server)
        failure = error(
            server,
            "steer/question",
            {"sessionId": "obs-q", "question": "which?"},
        )
        assert failure["code"] == protocol.ERROR_NOT_HOSTED


class TestUncertaintyEscalation:
    def test_low_confidence_records_an_escalation(self, server):
        enable_governor(server)
        begin(server, session_id="sess-esc")
        raised = result(
            server,
            "steer/escalate",
            {
                "sessionId": "sess-esc",
                "actionClass": "edit",
                "confidence": 0.42,
                "threshold": 0.8,
                "toolCallId": "tc-low",
            },
        )
        assert raised == {
            "accepted": True,
            "sequence": raised["sequence"],
            "escalated": True,
        }
        detail = result(server, "ledger.getEntry", {"sequence": raised["sequence"]})
        assert detail["inputAvailable"] is True
        assert '"confidence": 0.42' in detail["input"]
        assert '"threshold": 0.8' in detail["input"]
        assert '"actionClass": "edit"' in detail["input"]

    def test_escalation_on_observed_session_refuses_not_hosted(self, server):
        enable_governor(server)
        failure = error(
            server,
            "steer/escalate",
            {
                "sessionId": "obs-e",
                "actionClass": "edit",
                "confidence": 0.1,
                "threshold": 0.8,
            },
        )
        assert failure["code"] == protocol.ERROR_NOT_HOSTED


class TestPartialAcceptance:
    def test_accept_records_both_halves_and_status_is_queryable(self, server):
        enable_governor(server)
        begin(server, session_id="sess-acc")
        ack = result(
            server,
            "steer/accept",
            {
                "sessionId": "sess-acc",
                "accepted": [
                    {"file": "src/parser.ts", "hunks": [{"index": 0, "digest": "d0"}]}
                ],
                "rejected": [
                    {"file": "src/parser.ts", "hunks": [{"index": 1}]},
                    {"file": "src/cli.ts", "hunks": [{"index": 0}]},
                ],
            },
        )
        assert ack["accepted"] is True
        status = result(
            server, "steer/acceptanceStatus", {"sessionId": "sess-acc"}
        )
        assert status["hosted"] is True
        by_file = {f["file"]: f for f in status["files"]}
        assert set(by_file) == {"src/parser.ts", "src/cli.ts"}
        parser = {h["index"]: h["state"] for h in by_file["src/parser.ts"]["hunks"]}
        assert parser == {0: "accepted", 1: "rejected"}
        assert by_file["src/cli.ts"]["hunks"] == [{"index": 0, "state": "rejected"}]
        assert by_file["src/parser.ts"]["decidedBy"] == (
            "Grace Hopper <grace@example.com>"
        )

    def test_later_accept_replaces_state_for_the_named_files(self, server):
        enable_governor(server)
        begin(server, session_id="sess-acc2")
        result(
            server,
            "steer/accept",
            {
                "sessionId": "sess-acc2",
                "accepted": [],
                "rejected": [{"file": "a.ts", "hunks": [{"index": 0}]}],
            },
        )
        result(
            server,
            "steer/accept",
            {
                "sessionId": "sess-acc2",
                "accepted": [{"file": "a.ts", "hunks": [{"index": 0}]}],
                "rejected": [],
            },
        )
        status = result(
            server, "steer/acceptanceStatus", {"sessionId": "sess-acc2"}
        )
        assert status["files"][0]["hunks"] == [{"index": 0, "state": "accepted"}]

    def test_status_of_observed_session_is_empty_and_unhosted(self, server):
        enable_governor(server)
        status = result(
            server, "steer/acceptanceStatus", {"sessionId": "obs-a"}
        )
        assert status == {"sessionId": "obs-a", "hosted": False, "files": []}


class TestSteerStatus:
    def test_hosted_session_reports_mode_and_lifecycle(self, server):
        enable_governor(server)
        begin(server, session_id="sess-st", mode="dry-run")
        status = result(server, "steer/status", {"sessionId": "sess-st"})
        assert status["hosted"] is True
        assert status["mode"] == "dry-run"
        assert status["adapterId"] == "gemini"
        assert status["beginSequence"] >= 1
        assert "beganAt" in status
        assert "endedAt" not in status
        result(server, "acp/sessionEnd", {"sessionId": "sess-st"})
        status = result(server, "steer/status", {"sessionId": "sess-st"})
        assert status["hosted"] is True
        assert "endedAt" in status
        assert "endSequence" in status

    def test_normal_mode_is_default(self, server):
        enable_governor(server)
        begin(server, session_id="sess-nm")
        status = result(server, "steer/status", {"sessionId": "sess-nm"})
        assert status["mode"] == "normal"


class TestDryRunPlan:
    def test_plan_output_is_recorded(self, server):
        enable_governor(server)
        begin(server, session_id="sess-plan", mode="dry-run")
        ack = result(
            server,
            "steer/plan",
            {
                "sessionId": "sess-plan",
                "entries": [
                    {"content": "Extend the parser", "status": "pending"},
                    {"content": "Wire the CLI", "status": "pending"},
                ],
                "costEstimate": {"currency": "USD", "maxTokens": 12000},
            },
        )
        assert ack["accepted"] is True
        detail = result(server, "ledger.getEntry", {"sequence": ack["sequence"]})
        assert detail["inputAvailable"] is True
        assert "Wire the CLI" in detail["input"]
        assert "12000" in detail["input"]

    def test_plan_on_observed_session_refuses_not_hosted(self, server):
        enable_governor(server)
        failure = error(
            server, "steer/plan", {"sessionId": "obs-p", "entries": []}
        )
        assert failure["code"] == protocol.ERROR_NOT_HOSTED


class TestIdentity:
    def test_anonymous_steering_is_impossible(self, server):
        """FR-M20-01: who steered is never a free-text param — without a
        resolvable identity the RPC refuses instead of recording an
        anonymous steering act."""

        class NoIdentity:
            def resolve(self):
                raise IdentityUnavailableError("no identity")

        ledger = server._ledger  # noqa: SLF001
        bare = SidecarServer(ledger=ledger, identity_provider=NoIdentity())
        enable_governor(bare)
        begin(bare, session_id="sess-id")
        failure = error(
            bare, "steer.send", {"sessionId": "sess-id", "message": "x"}
        )
        assert failure["code"] == protocol.INVALID_PARAMS
        assert "identity" in failure["message"]
