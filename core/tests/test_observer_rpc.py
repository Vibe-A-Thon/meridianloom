"""observe/* RPC surface and doctor wiring tests (FR-M35-08, X-29, FR-M30-01).

The sidecar exposes the observer manager over the bus: observe/sessions
serves the X-29 session list from the monitor cache (never blocking on
observer IO), observe/health reports per-observer status, and doctor's
observer check is wired to the real manager instead of the not-built stub.
"""

from __future__ import annotations

import time

from meridian_core import doctor
from meridian_core.server import SidecarServer


def call(server: SidecarServer, method: str, params=None, request_id: int = 1):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    )


class TestObserveSessionsRpc:
    def setup_method(self):
        self.server = SidecarServer()

    def test_sessions_before_handshake_are_empty_not_an_error(self):
        response = call(self.server, "observe/sessions")
        result = response["result"]
        assert result["sessions"] == []
        assert result["warnings"]

    def test_sessions_follow_the_generated_contract_shape(self):
        response = call(self.server, "observe/sessions")
        session_keys = {
            "sessionId",
            "vendor",
            "confidence",
            "source",
            "detail",
            "pid",
            "startedAt",
            "lastActivityAt",
            "agentId",
        }
        assert set(response["result"]) == {"sessions", "warnings"}
        for session in response["result"]["sessions"]:
            assert set(session) <= session_keys
            assert session["confidence"] in ("direct", "telemetry", "inferred")

    def test_handshake_starts_the_session_monitor(self, tmp_path):
        response = call(
            self.server,
            "handshake",
            {
                "protocolVersion": 1,
                "client": "pytest",
                "workspaceDir": str(tmp_path),
            },
        )
        assert "result" in response
        health = call(self.server, "observe/health")["result"]
        assert health["monitorRunning"] is True
        assert {o["name"] for o in health["observers"]} == {"claude-code", "copilot"}
        self.server._handle_shutdown({"reason": "test teardown"})

    def test_sessions_after_handicap_come_from_the_monitor(self, tmp_path):
        call(
            self.server,
            "handshake",
            {
                "protocolVersion": 1,
                "client": "pytest",
                "workspaceDir": str(tmp_path),
            },
        )
        deadline = time.monotonic() + 5
        running = False
        while time.monotonic() < deadline:
            if self.server._session_monitor and self.server._session_monitor.ticks > 0:
                running = True
                break
            time.sleep(0.05)
        assert running, "session monitor did not tick after handshake"
        response = call(self.server, "observe/sessions")
        assert "generatedAt" not in response["result"]  # wire shape stays minimal
        self.server._handle_shutdown({"reason": "test teardown"})


class TestObserveHealthRpc:
    def setup_method(self):
        self.server = SidecarServer()

    def test_health_reports_both_observers_versioned(self):
        result = call(self.server, "observe/health")["result"]
        assert result["monitorRunning"] is False
        by_name = {o["name"]: o for o in result["observers"]}
        assert set(by_name) == {"claude-code", "copilot"}
        for record in by_name.values():
            assert record["status"] in ("ok", "degraded")
            assert record["vendorRelease"]
            assert record["adapterVersion"]
            assert isinstance(record["warnings"], list)

    def test_health_result_matches_the_contract(self):
        response = call(self.server, "observe/health")
        assert set(response["result"]) == {"observers", "monitorRunning"}
        for observer in response["result"]["observers"]:
            assert set(observer) <= {
                "name",
                "vendor",
                "status",
                "detail",
                "vendorRelease",
                "adapterVersion",
                "warnings",
            }


class TestDoctorObserverWiring:
    def test_doctor_uses_the_real_manager_not_the_stub(self, tmp_path):
        server = SidecarServer()
        call(
            server,
            "handshake",
            {
                "protocolVersion": 1,
                "client": "pytest",
                "workspaceDir": str(tmp_path),
            },
        )
        response = call(server, "doctor/run", {"checks": ["observers"]})
        check = response["result"]["checks"][0]
        assert check["id"] == "observers"
        # The stub used to warn "not built yet"; the real manager answers
        # with the actual observer states.
        assert "not built yet" not in check["detail"]
        assert "claude-code" in check["detail"]
        assert check["status"] in ("pass", "warn")
        server._handle_shutdown({"reason": "test teardown"})

    def test_doctor_observer_check_reflects_degradation(self):
        server = SidecarServer()
        server._observers.warn("claude-code", "simulated format drift (NFR-32)")
        response = call(server, "doctor/run", {"checks": ["observers"]})
        check = response["result"]["checks"][0]
        assert check["status"] == "warn"
        assert "claude-code" in check["detail"]
        assert "inferred" in check["remediation"]

    def test_observers_check_is_still_honest_without_the_framework(self):
        # The registry contract keeps the warn-not-crash path when no
        # observer_health probe is wired (defensive; server always wires).
        context = doctor.DoctorContext(started_at=0.0)
        result = doctor.run_doctor({"checks": ["observers"]}, context)
        assert result["checks"][0]["status"] == "warn"
