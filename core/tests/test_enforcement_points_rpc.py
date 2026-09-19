"""governance/enforcementPoints — FR-M42-11/12, SEC-32, MV1-T01.

The declaration already existed and already reached the audit bundle. What
did not exist was any way for an interface to ask for it, so two screens
carried hand-written prose notices about their own boundaries. Prose does not
compose and cannot be enforced by a type; this RPC is what a rendering
invariant can be built on.

The test that matters here is `test_v1_never_claims_scm_enforcement`: the
method must report where a control ACTUALLY binds, not where it is meant to.
"""

from __future__ import annotations

import pytest

from meridian_core.governance import enforcement_points


class TestTheRegistry:
    def test_every_declared_point_is_in_the_closed_vocabulary(self):
        # FR-M42-11's vocabulary is closed. A point outside it means a
        # surface would have to invent a rendering for it, which is how an
        # unqualified "enforced" gets shown.
        for name, declaration in enforcement_points.CONTROLS.items():
            assert enforcement_points.is_known_point(
                declaration.enforcement_point
            ), f"{name} declares {declaration.enforcement_point!r}, which is not in the vocabulary"

    def test_every_control_says_what_could_bypass_it(self):
        # FR-M42-12: a reviewer holding only the bundle must be able to say
        # what could have bypassed each decision and who could have done it.
        # An empty note makes that impossible while still looking complete.
        for name, declaration in enforcement_points.CONTROLS.items():
            assert declaration.boundary_note.strip(), f"{name} has no boundary note"


class TestTheEffectiveDeclaration:
    def test_v1_never_claims_scm_enforcement(self):
        """The point of the method, and the reason D37 is honest rather than
        aspirational: with no SCM binding configured — which is every v1
        install — nothing may report `scm`."""
        section = enforcement_points.enforcement_section(scm_binding_configured=False)
        assert section["scmBindingConfigured"] is False
        claiming_scm = [
            name
            for name, record in section["controls"].items()
            if record["enforcementPoint"] == "scm"
        ]
        assert claiming_scm == [], (
            f"{claiming_scm} report SCM enforcement with no SCM binding configured. "
            "SEC-32: a control may not be presented as enforced at a boundary "
            "where it is not."
        )

    def test_the_downgrade_states_itself(self):
        # A silent downgrade would be worse than no downgrade: the reader
        # would see `sidecar` and never learn that `scm` was intended and
        # refused. P26 — the unknown is reported, not absorbed.
        scm_controls = [
            name
            for name, d in enforcement_points.CONTROLS.items()
            if d.enforcement_point == "scm"
        ]
        if not scm_controls:
            pytest.skip("no scm-point control declared; nothing to downgrade")
        for name in scm_controls:
            effective = enforcement_points.effective_declaration(
                name, scm_binding_configured=False
            )
            assert effective.enforcement_point == "sidecar"
            assert "EFFECTIVE POINT" in effective.boundary_note

    def test_configuring_the_binding_restores_the_claim(self):
        # The downgrade is conditional, not a permanent lie in the other
        # direction. A customer who configures the SCM check gets the
        # stronger, true declaration.
        scm_controls = [
            name
            for name, d in enforcement_points.CONTROLS.items()
            if d.enforcement_point == "scm"
        ]
        if not scm_controls:
            pytest.skip("no scm-point control declared")
        for name in scm_controls:
            effective = enforcement_points.effective_declaration(
                name, scm_binding_configured=True
            )
            assert effective.enforcement_point == "scm"

    def test_an_unknown_control_raises_rather_than_returning_nothing(self):
        # A control nobody declared is a programming error. Returning an
        # empty declaration would let a surface render a control with no
        # boundary at all, which is the failure this module exists to stop.
        with pytest.raises(KeyError):
            enforcement_points.effective_declaration("not-a-control")


class TestTheRpcContract:
    """The shape the interface consumes. `enforcement_section` is the one
    source; the RPC must not build a second, divergent copy (J7)."""

    def test_the_section_carries_the_vocabulary_and_its_version(self):
        section = enforcement_points.enforcement_section()
        assert section["vocabularyVersion"] == enforcement_points.VOCABULARY_VERSION
        assert section["vocabulary"] == list(enforcement_points.VOCABULARY)

    def test_every_record_carries_the_four_fields_a_surface_needs(self):
        section = enforcement_points.enforcement_section()
        assert section["controls"], "the registry is empty"
        for name, record in section["controls"].items():
            assert record["control"] == name
            assert record["enforcementPoint"] in enforcement_points.VOCABULARY
            assert isinstance(record["enforced"], bool)
            assert record["boundaryNote"]
            assert record["vocabularyVersion"]

    def test_the_bundle_and_the_surface_read_the_same_source(self):
        """J7: two copies of one claim is the defect.

        The audit bundle's enforcement section and the RPC result must be
        the same declaration, so a reviewer holding the bundle and a user
        looking at the screen cannot be told different things about the
        same control. Compares the produced value rather than the import,
        because an alias proves only that a name exists — this fails if
        either side ever starts computing its own copy.
        """
        from meridian_core.ledger import bundle as ledger_bundle

        assert (
            ledger_bundle._enforcement_section()
            == enforcement_points.enforcement_section()
        )
