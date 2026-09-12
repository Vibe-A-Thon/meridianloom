"""What the bundle says about standards — FR-M50-01/02/03, AC-61, MV1-T11.

An auditor holding only the bundle must be able to read three things: the
information model the log corresponds to, the retention available against the
obligation they are held to, and — in the same place — what these mappings
are **not**.

That last one is the test that matters. A compliance section without its
disclaimer reads as a conformity claim, and ISO/IEC 24970 is a draft that is
not harmonised under the AI Act, so it confers no presumption of conformity.
Saying so is P27 applied to our own paperwork: the same rule that forbids
rendering a client-side control as enforced.
"""

from __future__ import annotations

from meridian_core.ledger import compliance


class TestTheStandardsAreNamed:
    def test_the_new_instruments_appear(self):
        joined = " | ".join(compliance.STANDARDS)
        assert "24970" in joined
        assert "Article 26" in joined

    def test_the_older_mappings_survive(self):
        # MP6: nothing built is removed to make room. SSDF, 42001 and
        # Article 12 were the buyer's vocabulary before and still are.
        joined = " | ".join(compliance.STANDARDS)
        assert "SSDF" in joined
        assert "42001" in joined
        assert "Article 12" in joined


class TestTheDisclaimer:
    def test_the_section_says_what_it_is_not(self):
        # AC-61's third clause. Without this the section is a list of
        # standards beside a signed record, which reads as conformance to
        # anyone not looking closely — and the people not looking closely
        # are exactly who a compliance section is read by.
        section = compliance.compliance_section()
        disclaimer = section["disclaimer"].lower()
        assert "not a certification" in disclaimer
        assert "presumption of conformity" in disclaimer

    def test_the_draft_standard_is_labelled_a_draft_where_it_is_used(self):
        # Not only in the disclaimer: the mapping row itself carries it, so
        # a reader who quotes one row out of context still gets the caveat.
        rows = [m for m in compliance.MAPPINGS if "24970" in m["framework"]]
        assert rows, "no ISO/IEC 24970 mapping found"
        for row in rows:
            assert "DRAFT AND NOT HARMONISED" in row["requirement"]


class TestTheRetentionMargin:
    def test_it_states_the_obligation_and_the_margin(self):
        # FR-M50-03: a reader sees the margin rather than computing it. The
        # question a deployer is answering is not "how long can this keep
        # records" but "does it clear the floor I am held to".
        retention = compliance.retention_section()
        assert retention["obligationMonths"] == 6
        assert "Article 26" in retention["obligation"]
        assert retention["marginMonths"] == (
            retention["availableMonths"] - retention["obligationMonths"]
        )
        assert retention["marginMonths"] > 0

    def test_the_margin_tracks_the_target_rather_than_being_written_down(self):
        # A hard-coded margin would go stale the moment the target moved,
        # and would go stale silently — the number would still look right.
        one_year = compliance.retention_section(target_years=1)
        assert one_year["availableMonths"] == 12
        assert one_year["marginMonths"] == 6

    def test_a_target_below_the_floor_reports_a_negative_margin(self):
        # It does NOT clamp at zero. A deployment that cannot meet the
        # obligation must say so in the bundle; rounding the shortfall away
        # would be the most consequential silent zero in the product (P26).
        short = compliance.retention_section(target_years=0)
        assert short["marginMonths"] == -6


class TestTheBundleCarriesIt:
    def test_the_section_reaches_the_wire_shape(self):
        section = compliance.compliance_section()
        for key in ("standards", "mappings", "retention", "disclaimer"):
            assert key in section, f"the bundle's compliance section lost {key}"

    def test_every_mapping_names_the_bundle_fields_that_satisfy_it(self):
        # A mapping that names no field is an assertion an auditor cannot
        # check against the bundle in hand, which is the only thing they
        # have.
        for row in compliance.MAPPINGS:
            assert row.get("bundleFields"), f"{row['reference']} names no bundle field"
