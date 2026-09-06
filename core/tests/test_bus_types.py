"""Generated bus types are the sidecar's contract source (FR-M32-09)."""

from __future__ import annotations

import typing

import bus_types

from meridian_core import protocol
from meridian_core.server import SidecarServer


def test_protocol_version_comes_from_generated_types():
    assert protocol.PROTOCOL_VERSION == bus_types.PROTOCOL_VERSION == 1


def test_error_codes_come_from_generated_types():
    assert protocol.PARSE_ERROR == bus_types.PARSE_ERROR == -32700
    assert protocol.ERROR_PROTOCOL_MISMATCH == bus_types.PROTOCOL_MISMATCH == -32002
    assert protocol.ERROR_NOT_IMPLEMENTED == bus_types.NOT_IMPLEMENTED == -32001


def test_method_name_literal_matches_runtime_method_list():
    assert set(typing.get_args(bus_types.MethodName)) == set(bus_types.REQUEST_METHODS)
    assert set(typing.get_args(bus_types.NotificationName)) == set(
        bus_types.NOTIFICATION_METHODS
    )


def test_method_contract_pairs_every_request_method():
    assert set(bus_types.METHOD_CONTRACT) == set(bus_types.REQUEST_METHODS)
    for contract in bus_types.METHOD_CONTRACT.values():
        assert isinstance(contract["params"], type)
        assert isinstance(contract["result"], type)


def test_server_registry_exactly_covers_the_contract():
    # SidecarServer.__init__ asserts registry == REQUEST_METHODS; building it
    # is the drift check.
    server = SidecarServer()
    assert set(server._handlers) == set(bus_types.REQUEST_METHODS)


def test_placeholder_methods_answer_not_implemented():
    server = SidecarServer()
    # Enable every tier first: the point here is the NOT_IMPLEMENTED
    # placeholder contract, not the tier gate (test_tiers.py covers the gate).
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "handshake",
            "params": {
                "protocolVersion": 1,
                "client": "pytest",
                "tiers": ["flight-recorder", "governor", "orchestra"],
            },
        }
    )
    for method in (
        "loop.start",
        "loop.stop",
        "loop.status",
        "gate.evaluate",
        "steer.send",
        "trust.summary",
        "acp/sessionBegin",
        "acp/sessionEnd",
        "acp/permissionDecision",
    ):
        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": method})
        assert response is not None
        assert response["error"]["code"] == bus_types.NOT_IMPLEMENTED, method


def test_ledger_methods_are_implemented_but_need_a_workspace():
    # FR-M10-01: real handlers, answering LEDGER_UNAVAILABLE until the
    # handshake carries workspaceDir (see test_ledger_durability.py).
    server = SidecarServer()
    for method in ("ledger.append", "ledger.query"):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": method}
        )
        assert response["error"]["code"] == bus_types.LEDGER_UNAVAILABLE, method


def test_health_reports_process_state():
    server = SidecarServer()
    response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "health"})
    result = response["result"]
    assert result["status"] == "ok"
    assert result["pid"] > 0
    assert result["activeLoops"] == 0
