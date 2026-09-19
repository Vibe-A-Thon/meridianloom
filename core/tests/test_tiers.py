"""Tier enforcement tests (FR-M36-05, principle G5).

G5: a tier that is disabled must leave no scar. With only flight-recorder
enabled (the default), governor and orchestra RPCs are refused with a
structured, actionable TIER_DISABLED error while every flight-recorder RPC
works; enabling a tier is a configuration change only — a handshake param or
a tiers/set notification — never a reinstall.
"""

from __future__ import annotations

import bus_types
from meridian_core import protocol, tiers
from meridian_core.server import SidecarServer


def call(server: SidecarServer, method: str, params: dict | None = None, request_id: int = 1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return server.handle_message(message)


def handshake(server: SidecarServer, enabled: list[str] | None = None):
    params = {"protocolVersion": 1, "client": "pytest"}
    if enabled is not None:
        params["tiers"] = enabled
    return call(server, "handshake", params)


class TestNormalise:
    def test_default_is_flight_recorder_only(self):
        assert tiers.normalise_enabled_tiers(None) == {"flight-recorder"}
        assert tiers.normalise_enabled_tiers([]) == {"flight-recorder"}

    def test_base_tier_cannot_be_removed(self):
        # G5 is about removing upper tiers; the base is always present so
        # lifecycle methods answer no matter what the setting says.
        assert tiers.normalise_enabled_tiers(["governor"]) == {
            "flight-recorder",
            "governor",
        }

    def test_unknown_tiers_are_dropped(self):
        assert tiers.normalise_enabled_tiers(["orchestra", "bogus"]) == {
            "flight-recorder",
            "orchestra",
        }

    def test_registry_covers_every_request_method_exactly_once(self):
        claims = [
            method
            for capability in bus_types.CAPABILITIES
            for method in capability["rpcMethods"]
        ]
        assert len(claims) == len(set(claims)), "a capability double-claims a method"
        assert set(claims) == set(bus_types.REQUEST_METHODS)

    def test_every_capability_is_owned_by_exactly_one_tier(self):
        for capability in bus_types.CAPABILITIES:
            assert capability["tier"] in bus_types.TIERS
        ids = [capability["id"] for capability in bus_types.CAPABILITIES]
        assert len(ids) == len(set(ids))


class TestTierGate:
    def setup_method(self):
        # No handshake: the sidecar default must already be safe.
        self.server = SidecarServer()

    def test_flight_recorder_methods_work_by_default(self):
        assert "result" in call(self.server, "ping")
        assert "result" in call(self.server, "health")
        assert "result" in call(self.server, "doctor/run")
        # The ledger is implemented (FR-M10-01) but needs workspaceDir:
        # a structured LEDGER_UNAVAILABLE, NOT a tier refusal.
        assert call(self.server, "ledger.append")["error"]["code"] == (
            protocol.ERROR_LEDGER_UNAVAILABLE
        )

    def test_governor_and_orchestra_methods_are_refused_by_default(self):
        for method in ("gate.evaluate", "steer.send", "trust.summary", "loop.start"):
            response = call(self.server, method)
            assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED, method

    def test_refusal_is_structured_and_actionable(self):
        response = call(self.server, "loop.start")
        error = response["error"]
        assert "orchestra" in error["message"]
        data = error["data"]
        assert data["method"] == "loop.start"
        assert data["capability"] == "orchestra.loops"
        assert data["tier"] == "orchestra"
        assert data["enabledTiers"] == ["flight-recorder"]
        # The remediation names the setting and the no-reinstall promise.
        assert "meridian.tiers" in data["remediation"]
        assert "no reinstall" in data["remediation"]

    def test_unknown_method_still_reports_method_not_found(self):
        response = call(self.server, "nope")
        assert response["error"]["code"] == protocol.METHOD_NOT_FOUND


class TestEnablingTiers:
    def test_handshake_enables_upper_tiers(self):
        server = SidecarServer()
        handshake(server, ["flight-recorder", "orchestra"])
        # Orchestra method now passes the tier gate. loop.* is implemented
        # (it used to be a NOT_IMPLEMENTED placeholder), and with no
        # workspace configured it answers LEDGER_UNAVAILABLE — a refusal
        # from the handler, not from the gate.
        response = call(server, "loop.start")
        assert response["error"]["code"] == protocol.ERROR_LEDGER_UNAVAILABLE
        # Governor stays refused — enabling is per-tier.
        response = call(server, "gate.evaluate")
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert server.enabled_tiers == {"flight-recorder", "orchestra"}

    def test_handshake_without_tiers_keeps_the_default(self):
        server = SidecarServer()
        handshake(server)
        assert server.enabled_tiers == {"flight-recorder"}

    def test_tiers_set_notification_flips_tiers_without_reconnect(self):
        server = SidecarServer()
        handshake(server)
        assert call(server, "steer.send")["error"]["code"] == protocol.ERROR_TIER_DISABLED
        # FR-M36-05: a config change is the whole cost of enabling a tier.
        assert (
            server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "method": "tiers/set",
                    "params": {"tiers": ["flight-recorder", "governor"]},
                }
            )
            is None  # notification: no response
        )
        # steer.send is implemented since F1 Workstream D task 17 (it now
        # passes the tier gate and fails on params — a real handler, not the
        # NOT_IMPLEMENTED placeholder; core/tests/test_steer.py covers it).
        assert call(server, "steer.send")["error"]["code"] == protocol.INVALID_PARAMS
        assert call(server, "trust.summary")["error"]["code"] == protocol.ERROR_NOT_IMPLEMENTED
        assert call(server, "loop.start")["error"]["code"] == protocol.ERROR_TIER_DISABLED

    def test_tiers_set_cannot_drop_the_base_tier(self):
        server = SidecarServer()
        handshake(server, ["flight-recorder", "governor", "orchestra"])
        server.handle_message(
            {"jsonrpc": "2.0", "method": "tiers/set", "params": {"tiers": []}}
        )
        assert server.enabled_tiers == {"flight-recorder"}
        assert "result" in call(server, "ping")
