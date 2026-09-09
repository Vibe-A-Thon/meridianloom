"""Enforcement-point declaration (FR-M42-11/12, SEC-32, P27; FUT-025;
N2-T05).

Every control declares its enforcement point from the closed FR-M42-11
vocabulary, and the declaration is honest (P27: a control is only as
strong as the boundary it binds at; SEC-32: never present a control as
enforced where it is not):

* the vocabulary is closed and versioned — every registered control's
  point is a member of it;
* the registry covers the shipped controls (merge gate, SCM merge check,
  permission policy, halt, policy refusal, spend ceiling, provenance
  hook, steer checkpoint);
* per D37 the FR-M42-03 SCM binding is REFUSED until a pilot customer
  exists, so in v1 (``scm_binding_configured=False`` — the only v1
  configuration) NO control effectively claims ``scm``: the declared
  ``scm_merge_check`` downgrades to ``sidecar`` and says so;
* advisory controls (``enforced=False``) are never rendered enforced,
  and every decision's ledger detail plus the audit bundle records the
  effective enforcement point (FR-M42-12).
"""

from __future__ import annotations

import json
from pathlib import Path

from meridian_core.governance import enforcement_points
from meridian_core.ledger import bundle as ledger_bundle
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider

# Controls the workstream is accountable for (FR-M42-11 "every control
# Meridian displays" — the v1 registry must cover each one).
REQUIRED_CONTROLS = (
    "merge_gate",
    "scm_merge_check",
    "permission_policy",
    "halt_all",
    "policy_refusal",
    "spend_ceiling",
    "provenance_hook",
    "steer_checkpoint",
)


def effective_points(scm_binding_configured: bool = False) -> dict[str, str]:
    return {
        name: enforcement_points.effective_declaration(
            name, scm_binding_configured=scm_binding_configured
        ).enforcement_point
        for name in enforcement_points.CONTROLS
    }


class TestVocabulary:
    def test_vocabulary_is_the_closed_fr_m42_11_set(self):
        assert enforcement_points.VOCABULARY == (
            "editor",
            "extension_host",
            "sidecar",
            "scm",
            "ci",
            "advisory_only",
        )

    def test_vocabulary_is_versioned(self):
        assert enforcement_points.VOCABULARY_VERSION
        record = enforcement_points.audit_record(
            enforcement_points.CONTROLS["merge_gate"]
        )
        assert record["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION

    def test_every_registered_control_uses_a_vocabulary_point(self):
        for name, declaration in enforcement_points.CONTROLS.items():
            assert enforcement_points.is_known_point(declaration.enforcement_point), (
                name
            )

    def test_registry_covers_every_displayed_control(self):
        for control in REQUIRED_CONTROLS:
            assert control in enforcement_points.CONTROLS

    def test_every_declaration_carries_enforced_flag_and_bypass_note(self):
        # FR-M42-12: a reviewer must be able to state what could have
        # bypassed each control — the note is mandatory and non-empty.
        for name, declaration in enforcement_points.CONTROLS.items():
            assert isinstance(declaration.enforced, bool), name
            assert declaration.boundary_note.strip(), name


class TestHonestDowngrade:
    def test_no_control_effectively_claims_scm_in_v1(self):
        # D37/SEC-32: the SCM binding is refused until a pilot customer
        # exists; v1 never configures it, so nothing effectively claims
        # the scm point.
        points = effective_points(scm_binding_configured=False)
        assert "scm" not in points.values()

    def test_scm_merge_check_downgrades_to_sidecar_with_a_stated_reason(self):
        declaration = enforcement_points.effective_declaration("scm_merge_check")
        assert declaration.enforcement_point == "sidecar"
        assert "D37" in declaration.boundary_note
        assert "Never render as enforced at the SCM" in declaration.boundary_note

    def test_configured_binding_keeps_the_scm_point(self):
        # The future path (T04, customer-gated): once a pilot customer's
        # platform team configures the binding, the declared scm point
        # holds and no downgrade note is added.
        declaration = enforcement_points.effective_declaration(
            "scm_merge_check", scm_binding_configured=True
        )
        assert declaration.enforcement_point == "scm"
        assert declaration is enforcement_points.CONTROLS["scm_merge_check"]

    def test_non_scm_controls_are_not_downgraded(self):
        for name, declaration in enforcement_points.CONTROLS.items():
            if declaration.enforcement_point != "scm":
                assert (
                    enforcement_points.effective_declaration(name)
                    is declaration
                )

    def test_unknown_control_is_an_error_never_a_silent_default(self):
        try:
            enforcement_points.effective_declaration("not_a_control")
        except KeyError:
            pass
        else:  # pragma: no cover - assertion path
            raise AssertionError("unknown control must raise KeyError (P26)")


class TestAdvisoryHonesty:
    def test_advisory_controls_are_never_enforced(self):
        # SEC-32: a client-side/advisory control is never rendered as
        # enforced — enforced=False and an advisory point.
        for name, declaration in enforcement_points.CONTROLS.items():
            if not declaration.enforced:
                assert declaration.enforcement_point == "advisory_only", name
                record = enforcement_points.audit_record(
                    enforcement_points.effective_declaration(name)
                )
                assert record["enforced"] is False

    def test_provenance_hook_is_advisory_and_says_why(self):
        declaration = enforcement_points.effective_declaration("provenance_hook")
        assert declaration.enforced is False
        assert "--no-verify" in declaration.boundary_note


class TestAuditRecords:
    def test_audit_record_shape(self):
        record = enforcement_points.audit_record(
            enforcement_points.effective_declaration("merge_gate")
        )
        assert record["control"] == "merge_gate"
        assert record["enforcementPoint"] == "sidecar"
        assert record["enforced"] is True
        assert record["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION
        assert "IN MERIDIAN" in record["boundaryNote"]

    def test_enforcement_section_lists_every_control_effective(self):
        section = enforcement_points.enforcement_section()
        assert section["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION
        assert section["scmBindingConfigured"] is False
        assert set(section["controls"]) == set(enforcement_points.CONTROLS)
        for record in section["controls"].values():
            assert record["enforcementPoint"] != "scm"

    def test_bundle_carries_the_enforcement_section(self, tmp_path: Path):
        # FR-M42-12/FR-M12-11: the audit bundle records the effective
        # enforcement point per control, inside the signed core.
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        ledger.append(
            {
                "story_id": "gate:main",
                "phase": "review",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_version": "0",
                "actor_kind": "meta",
                "policy_version": "governance/v2",
                "action_type": "gate",
                "decision": "halted",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "input": json.dumps({"method": "gate.halt", "scope": "merge"}),
            }
        )
        exported = ledger_bundle.build_bundle(ledger, {})
        section = exported["enforcement"]
        assert section["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION
        assert set(section["controls"]) == set(enforcement_points.CONTROLS)
        assert all(
            record["enforcementPoint"] != "scm"
            for record in section["controls"].values()
        )


# -- per-decision records via the RPC layer -------------------------------------

from test_merge_gate import call, make_server, repo  # noqa: E402,F401


def _detail(server: "object", sequence: int) -> dict:
    row = server.ledger.get_entry(sequence)
    return json.loads(
        server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
    )


class TestDecisionRecords:
    def test_gate_approve_records_the_effective_enforcement_point(
        self, tmp_path, repo
    ):
        server = make_server(tmp_path, repo)
        response = call(
            server,
            "gate.approve",
            {"subject": "main", "commit": "a" * 40, "role": "approver"},
        )
        detail = _detail(server, response["result"]["sequence"])
        record = detail["enforcementPoint"]
        assert record["control"] == "merge_gate"
        # D37: the merge gate binds in Meridian — the recorded point is
        # sidecar, never scm, in v1.
        assert record["enforcementPoint"] == "sidecar"
        assert record["enforced"] is True
        assert record["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION
        assert "IN MERIDIAN" in record["boundaryNote"]

    def test_gate_halt_records_the_effective_enforcement_point(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        response = call(
            server, "gate.halt", {"reason": "incident", "scope": "merge"}
        )
        detail = _detail(server, response["result"]["sequence"])
        record = detail["enforcementPoint"]
        assert record["control"] == "halt_all"
        assert record["enforcementPoint"] == "sidecar"
        assert record["enforced"] is True
