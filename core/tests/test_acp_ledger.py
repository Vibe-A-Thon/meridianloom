"""Hosted-session ledger recording (FR-M34-04, SEC-28; F1 Workstream A task 4).

The extension host's ACP client reports session facts over the bus; the
sidecar appends durable ledger entries:

- acp/sessionBegin  -> action_type ``session_begin`` (actorKind external,
  vendor ``acp``, direct observation confidence) before the agent's turn;
- acp/sessionEnd    -> action_type ``session_end``, attributed to the same
  actor as the session's begin entry;
- acp/permissionDecision -> action_type ``permission_decision`` with the
  decision (approved/rejected) and the reason citation — the governance
  trail that SEC-28 re-request checks query by actorId.

The methods are governor-tier: with the default tier set they are refused
with the structured TIER_DISABLED error (G5), and enabling the governor via
the handshake unlocks them.
"""

from __future__ import annotations

import pytest

from meridian_core import protocol
from meridian_core.ledger import core as ledger_core
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.ledger.core import Ledger
from meridian_core.server import SidecarServer


@pytest.fixture()
def server(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
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


class TestTierGate:
    def test_governor_disabled_refuses_session_recording(self, server):
        response = call(
            server,
            1,
            "acp/sessionBegin",
            {"agentId": "gemini", "sessionId": "s", "cwd": "/work"},
        )
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert response["error"]["data"]["tier"] == "governor"

    def test_governor_enabled_records(self, server):
        enable_governor(server)
        recorded = begin(server)
        assert recorded == {"recorded": True}


class TestSessionRecording:
    def test_session_begin_appends_a_session_begin_entry(self, server):
        enable_governor(server)
        begin(server, session_id="sess-9", startedAt="2026-10-01T10:00:00Z")
        entries = result(server, "ledger.query", {"actorId": "gemini"})["entries"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["actionType"] == "session_begin"
        assert entry["actorKind"] == "external"
        assert entry["actorVersion"] == "0.30.0"
        assert entry["vendor"] == "acp"
        assert entry["observationConfidence"] == "direct"
        assert entry["externalSessionId"] == "sess-9"
        assert entry["timestamp"] == "2026-10-01T10:00:00Z"

    def test_session_end_appends_and_resolves_the_actor_from_begin(self, server):
        enable_governor(server)
        begin(server, session_id="sess-2", agent_id="claude-acp")
        ended = result(
            server,
            "acp/sessionEnd",
            {"sessionId": "sess-2", "stopReason": "end_turn"},
        )
        assert ended == {"recorded": True}
        entries = result(server, "ledger.query", {"actorId": "claude-acp"})["entries"]
        assert [e["actionType"] for e in entries] == ["session_begin", "session_end"]
        assert entries[1]["externalSessionId"] == "sess-2"

    def test_session_end_without_begin_records_with_unknown_actor(self, server):
        enable_governor(server)
        ended = result(
            server,
            "acp/sessionEnd",
            {"sessionId": "never-began", "stopReason": "cancelled"},
        )
        assert ended == {"recorded": True}
        entries = result(server, "ledger.query", {"actorId": "unknown"})["entries"]
        assert entries[0]["actionType"] == "session_end"


class TestPermissionDecisionRecording:
    def test_selected_records_an_approved_decision(self, server):
        enable_governor(server)
        begin(server, session_id="sess-3")
        recorded = result(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "sess-3",
                "adapterId": "gemini",
                "toolCallId": "tc-1",
                "toolKind": "execute",
                "optionId": "allow-once",
                "outcome": "selected",
            },
        )
        assert recorded == {"recorded": True}
        entries = result(
            server, "ledger.query", {"actorId": "gemini", "actionType": "permission_decision"}
        )["entries"]
        assert len(entries) == 1
        assert entries[0]["decision"] == "approved"

    def test_denied_by_policy_records_a_rejected_decision_with_reason(self, server):
        enable_governor(server)
        result(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "sess-4",
                "adapterId": "gemini",
                "toolCallId": "tc-2",
                "toolKind": "execute",
                "outcome": "denied_by_policy",
                "reason": "execute is not in the probation allow-list for gemini",
                "policyVersion": "acp-permissions/v1",
            },
        )
        entries = result(
            server, "ledger.query", {"actorId": "gemini", "actionType": "permission_decision"}
        )["entries"]
        assert entries[0]["decision"] == "rejected"
        assert "probation allow-list" in entries[0]["reworkReason"]
        assert entries[0]["policyVersion"] == "acp-permissions/v1"

    def test_cancelled_records_without_a_decision(self, server):
        enable_governor(server)
        result(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "sess-5",
                "adapterId": "gemini",
                "toolCallId": "tc-3",
                "toolKind": "edit",
                "outcome": "cancelled",
            },
        )
        entries = result(
            server, "ledger.query", {"actorId": "gemini", "actionType": "permission_decision"}
        )["entries"]
        assert entries[0]["decision"] is None

    def test_rejections_are_queryable_by_actor_for_sec28_citation(self, server):
        enable_governor(server)
        for call_id, kind in (("tc-a", "execute"), ("tc-b", "execute"), ("tc-c", "read")):
            result(
                server,
                "acp/permissionDecision",
                {
                    "sessionId": "sess-6",
                    "adapterId": "gemini",
                    "toolCallId": call_id,
                    "toolKind": kind,
                    "outcome": "denied_by_policy",
                    "reason": f"{kind} not allowed",
                },
            )
        rejected = result(
            server,
            "ledger.query",
            {
                "actorId": "gemini",
                "actionType": "permission_decision",
                "fromSequence": 1,
                "toSequence": 10_000,
            },
        )["entries"]
        assert len(rejected) == 3
        assert all(e["decision"] == "rejected" for e in rejected)
        assert [e["reworkReason"] for e in rejected] == [
            "execute not allowed",
            "execute not allowed",
            "read not allowed",
        ]
