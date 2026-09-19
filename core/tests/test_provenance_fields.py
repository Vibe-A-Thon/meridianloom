"""Per-field provenance on every provenance answer (FR-M41-01, FR-M41-02;
N1 Workstream B T10).

Every field of a provenance answer (attrib/blame, attrib/symbol) carries
its source, its capture method, the contract version it was derived
from, its capture timestamp, and one of exactly four states:
``observed`` / ``inferred`` / ``unknown`` / ``redacted``.

FR-M41-02's structural rule: signing an artefact never promotes an
``inferred`` field to ``observed`` — the state string is inside the
signed bytes, so promotion breaks the signature rather than passing
silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.attribution import wire as attribution_wire
from meridian_core.attribution.provenance import (
    ProvenanceField,
    captured_now,
    signed_form,
)
from meridian_core.attribution.states import (
    ATTRIBUTION_CONTRACT_VERSION,
    PROVENANCE_STATES,
)
from meridian_core.server import SidecarServer

from test_symbols import JAVA_SOURCE, line_of


class TestProvenanceField:
    def test_four_states_exactly(self):
        assert PROVENANCE_STATES == ("observed", "inferred", "unknown", "redacted")

    def test_record_carries_the_five_facts(self):
        record = ProvenanceField.observed(
            "value-x",
            source="git",
            capture_method="git blame --porcelain -M -C",
            captured_at="2026-09-08T12:00:00.000000Z",
        ).to_dict()
        assert record == {
            "value": "value-x",
            "source": "git",
            "captureMethod": "git blame --porcelain -M -C",
            "contractVersion": ATTRIBUTION_CONTRACT_VERSION,
            "capturedAt": "2026-09-08T12:00:00.000000Z",
            "state": "observed",
        }

    def test_unknown_field_has_no_invented_value(self):
        record = ProvenanceField.unknown(
            source="symbols engine",
            capture_method="language registry lookup",
            captured_at=captured_now(),
        ).to_dict()
        assert record["state"] == "unknown"
        assert record["value"] is None

    def test_invalid_state_rejected(self):
        with pytest.raises(ValueError):
            ProvenanceField(
                value="x",
                source="s",
                capture_method="m",
                contract_version=ATTRIBUTION_CONTRACT_VERSION,
                captured_at=captured_now(),
                state="plausible",
            )

    def test_record_is_immutable(self):
        record = ProvenanceField.inferred(
            0.5,
            source="heuristics",
            capture_method="burst/timing rules",
            captured_at=captured_now(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            object.__setattr__  # attribute assignment raises
            record.state = "observed"  # type: ignore[misc]


class TestSigningNeverPromotes:
    def test_signed_bytes_include_the_state(self):
        inferred = ProvenanceField.inferred(
            "claude",
            source="git trailers",
            capture_method="Co-Authored-By parse",
            captured_at="2026-09-08T12:00:00.000000Z",
        ).to_dict()
        signed = signed_form(inferred)
        assert isinstance(signed, bytes) and signed

        # A tampered record promoting inferred -> observed no longer
        # verifies against the original signature: promotion is
        # structurally impossible, not merely disciplined (FR-M41-02).
        promoted = dict(inferred)
        promoted["state"] = "observed"
        assert signed_form(promoted) != signed

    def test_inferred_survives_the_round_trip(self):
        inferred = ProvenanceField.inferred(
            0.75,
            source="heuristics",
            capture_method="burst/timing rules",
            captured_at=captured_now(),
        )
        signed = signed_form(inferred.to_dict())
        # Signing covers the record; the state is still inferred.
        assert inferred.state == "inferred"
        assert b"inferred" in signed


class TestWireProvenanceBuilders:
    def test_blame_provenance_is_all_observed(self):
        provenance = attribution_wire.blame_provenance("/repo", "HEAD")
        assert set(provenance) == {"repoPath", "ref", "lines"}
        for record in provenance.values():
            assert record["state"] == "observed"
            assert record["contractVersion"] == ATTRIBUTION_CONTRACT_VERSION
            assert record["capturedAt"].endswith("Z")
            assert record["source"]
            assert record["captureMethod"]

    def test_symbol_provenance_marks_null_fields_unknown(self):
        provenance = attribution_wire.symbol_provenance("notes.txt", 1, None, None)
        assert provenance["path"]["state"] == "observed"
        assert provenance["line"]["state"] == "observed"
        assert provenance["language"]["state"] == "unknown"
        assert provenance["language"]["value"] is None
        assert provenance["symbol"]["state"] == "unknown"

    def test_symbol_provenance_observed_when_resolved(self):
        provenance = attribution_wire.symbol_provenance(
            "Service.py", 3, "python", "Service.handle"
        )
        assert provenance["language"]["state"] == "observed"
        assert provenance["language"]["value"] == "python"
        assert provenance["symbol"]["state"] == "observed"
        assert provenance["symbol"]["value"] == "Service.handle"


class TestProvenanceRpc:
    def _server(self, repo: Path) -> SidecarServer:
        server = SidecarServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "workspaceDir": str(repo),
                },
            }
        )
        assert "result" in response
        return server

    def test_blame_answer_carries_per_field_provenance(self, repo):
        server = self._server(repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "attrib/blame",
                "params": {"repoPath": str(repo), "paths": ["README.md"]},
            }
        )
        assert "result" in response, response
        provenance = response["result"]["provenance"]
        for field in ("repoPath", "ref", "lines"):
            record = provenance[field]
            assert record["state"] == "observed"
            assert record["source"]
            assert record["captureMethod"]
            assert record["contractVersion"] == ATTRIBUTION_CONTRACT_VERSION
            assert record["capturedAt"].endswith("Z")

    def test_symbol_answer_marks_unregistered_language_unknown(self, repo):
        server = self._server(repo)
        (repo / "notes.txt").write_text("x\n", encoding="utf-8")
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "attrib/symbol",
                "params": {"repoPath": str(repo), "path": "notes.txt", "line": 1},
            }
        )
        assert "result" in response, response
        result = response["result"]
        assert result["language"] is None
        provenance = result["provenance"]
        assert provenance["language"]["state"] == "unknown"
        assert provenance["symbol"]["state"] == "unknown"
        assert provenance["path"]["state"] == "observed"

    def test_symbol_answer_observed_when_resolved(self, repo):
        java_file = repo / "PaymentController.java"
        java_file.write_text(JAVA_SOURCE, encoding="utf-8")
        server = self._server(repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "attrib/symbol",
                "params": {
                    "repoPath": str(repo),
                    "path": java_file.name,
                    "line": line_of(JAVA_SOURCE, "Receipt receipt = charge"),
                },
            }
        )
        assert "result" in response, response
        result = response["result"]
        assert result["symbol"] == "PaymentController.submit"
        provenance = result["provenance"]
        assert provenance["symbol"]["state"] == "observed"
        assert provenance["symbol"]["value"] == "PaymentController.submit"
        assert provenance["symbol"]["captureMethod"]
