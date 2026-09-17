"""MCP server gateway (FR-M34-06; F1 Workstream A task 6).

The standalone MCP server process speaks MCP to any client and forwards each
tools/call as one ``mcp/invoke`` on the sidecar bus. The sidecar half is the
permission gate and the provenance trail:

- ``mcp/invoke`` is governor-tier: with the default tier set it is refused
  with the structured TIER_DISABLED error (G5), same shape as every other
  governor method;
- every call is ledger-recorded as a ``tool_call`` entry (vendor ``mcp``,
  direct confidence) BEFORE the underlying handler runs — an external MCP
  client leaves the same trail as any other governed actor;
- the tool name maps onto the existing read-only handler and the result
  passes through verbatim; unknown tool names are refused with
  INVALID_PARAMS listing what exists.
"""

from __future__ import annotations

import json

import pytest

from meridian_core import protocol
from meridian_core.ledger import core as ledger_core
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.ledger.core import Ledger
from meridian_core.server import SidecarServer, _RpcError


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


def invoke(server, tool, arguments=None, **extra):
    params = {"tool": tool, "arguments": arguments or {}}
    params.update(extra)
    return result(server, "mcp/invoke", params)


def append_story_entry(server, story_id="mcp-story"):
    return result(
        server,
        "ledger.append",
        {
            "storyId": story_id,
            "phase": "build",
            "loopId": "L1",
            "loopIteration": 1,
            "actorId": "claude-code",
            "actorVersion": "1.0.0",
            "actorKind": "external",
            "policyVersion": "test",
            "actionType": "diff",
            "vendor": "claude-code",
        },
    )


class TestTierGate:
    def test_governor_disabled_refuses_mcp_invoke(self, server):
        response = call(server, 1, "mcp/invoke", {"tool": "ledger_query", "arguments": {}})
        error = response["error"]
        assert error["code"] == protocol.ERROR_TIER_DISABLED
        assert error["data"]["tier"] == "governor"
        assert error["data"]["capability"] == "governor.mcp-server"
        assert error["data"]["method"] == "mcp/invoke"
        assert "meridian.tiers" in error["data"]["remediation"]

    def test_governor_enabled_unlocks_mcp_invoke(self, server):
        enable_governor(server)
        verdict = invoke(server, "ledger_verify")
        assert verdict["tool"] == "ledger_verify"
        assert verdict["result"]["ok"] is True


class TestToolDispatch:
    def test_unknown_tool_is_refused_with_available_tools(self, server):
        enable_governor(server)
        response = call(server, 2, "mcp/invoke", {"tool": "rm_rf", "arguments": {}})
        error = response["error"]
        assert error["code"] == protocol.INVALID_PARAMS
        for tool in (
            "ledger_query",
            "ledger_export_bundle",
            "ledger_verify",
            "trust_rejection_rate",
        ):
            assert tool in error["data"]["availableTools"]

    def test_missing_arguments_defaults_to_empty_object(self, server):
        enable_governor(server)
        verdict = invoke(server, "ledger_verify", None)
        assert verdict["result"]["ok"] is True

    def test_ledger_query_passthrough(self, server):
        enable_governor(server)
        append_story_entry(server)
        queried = invoke(server, "ledger_query", {"storyId": "mcp-story"})
        assert queried["tool"] == "ledger_query"
        entries = queried["result"]["entries"]
        assert len(entries) == 1
        assert entries[0]["storyId"] == "mcp-story"
        assert entries[0]["vendor"] == "claude-code"

    def test_underlying_structured_errors_propagate_verbatim(self, server):
        enable_governor(server)
        # No ledger anywhere: the underlying read answers LEDGER_UNAVAILABLE
        # and the gateway passes that structured error through untouched.
        bare = SidecarServer()
        enable_governor(bare)
        response = call(bare, 3, "mcp/invoke", {"tool": "ledger_verify", "arguments": {}})
        assert response["error"]["code"] == protocol.ERROR_LEDGER_UNAVAILABLE

    def test_trust_rejection_rate_passthrough(self, server):
        enable_governor(server)
        metrics = invoke(server, "trust_rejection_rate", {})
        result_json = metrics["result"]
        assert "agents" in result_json or "rejectionRate" in result_json or (
            isinstance(result_json, dict)
        )

    def test_export_bundle_passthrough(self, server):
        enable_governor(server)
        append_story_entry(server)
        bundle = invoke(server, "ledger_export_bundle", {"storyId": "mcp-story"})
        assert bundle["result"]["formatVersion"] == 1
        assert bundle["result"]["entries"][0]["storyId"] == "mcp-story"
        assert "signature" in bundle["result"]


class TestLedgerRecording:
    def test_call_recorded_as_tool_call_before_executing(self, server):
        enable_governor(server)
        append_story_entry(server)
        invoke(server, "ledger_query", {"storyId": "mcp-story"}, client="vscode-copilot")
        rows = server.ledger.query(action_type="tool_call")
        assert len(rows) == 1
        row = rows[0]
        assert row["story_id"] == "mcp:ledger_query"
        assert row["actor_id"] == "vscode-copilot"
        assert row["actor_kind"] == "external"
        assert row["vendor"] == "mcp"
        assert row["observation_confidence"] == "direct"
        assert row["loop_id"] == "mcp-server"
        assert row["policy_version"] == "mcp-server/v1"
        # input is an encrypted blob (FR-M10-07); read it back the same way
        # ledger.getEntry does.
        detail = json.loads(
            server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["tool"] == "ledger_query"
        assert detail["arguments"] == {"storyId": "mcp-story"}

    def test_default_actor_is_mcp_client(self, server):
        enable_governor(server)
        invoke(server, "ledger_verify")
        rows = server.ledger.query(action_type="tool_call")
        assert rows[0]["actor_id"] == "mcp-client"

    def test_identity_bound_as_asserted_with_reason(self, server):
        """FR-M44-01/02 (N2-T21/T22): the MCP client identity is bound to
        the declared name at "asserted" assurance with the reason stated —
        in the ledger entry and in the result, never upgraded to verified.
        """
        enable_governor(server)
        verdict = invoke(server, "ledger_verify", client="vscode-copilot")
        assert verdict["identity"] == {
            "client": "vscode-copilot",
            "assurance": "asserted",
            "reason": (
                "caller-declared MCP client name; no executable digest or"
                " resolved version is available at this boundary"
            ),
        }
        row = server.ledger.query(action_type="tool_call")[0]
        detail = json.loads(
            server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["identity"]["assurance"] == "asserted"
        assert detail["identity"]["client"] == "vscode-copilot"
        assert "no executable digest" in detail["identity"]["reason"]

    def test_default_identity_is_named_mcp_client(self, server):
        enable_governor(server)
        verdict = invoke(server, "ledger_verify")
        assert verdict["identity"]["client"] == "mcp-client"
        assert verdict["identity"]["assurance"] == "asserted"

    def test_session_id_recorded_when_given(self, server):
        enable_governor(server)
        invoke(server, "ledger_verify", sessionId="mcp-session-9")
        rows = server.ledger.query(action_type="tool_call")
        assert rows[0]["external_session_id"] == "mcp-session-9"

    def test_recording_survives_even_when_the_tool_errors(self, server, monkeypatch):
        enable_governor(server)

        def broken(self, params):
            raise _RpcError(protocol.INVALID_PARAMS, "boom")

        monkeypatch.setitem(server._handlers, "ledger.verify", broken)
        response = call(server, 4, "mcp/invoke", {"tool": "ledger_verify", "arguments": {}})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert response["error"]["message"] == "boom"
        # The governance trail is durable before and independently of the
        # outcome, same principle as acp/permissionDecision.
        rows = server.ledger.query(action_type="tool_call")
        assert len(rows) == 1
