"""External contract drift is visible, never silent — FR-M44-06/07, NFR-40,
MVP-R6.1, MV1-T09.

Meridian derives evidence from contracts it does not control: another
vendor's telemetry shape, a protocol's wire version, a commit-message
convention. When one of those moves, the choices are to notice or to keep
mapping the old shape onto the new data and call the result evidence.

`shared/schema/external-contracts.json` pins what the code was built against.
These tests hold the code and the pin together, so a version can only change
as a reviewed event.

**What this cannot do**, stated here as well as in the manifest because a
check whose limits live only in a comment gets trusted past them: it cannot
detect a rename upstream that nobody has noticed. That needs the upstream
schema, which needs a network call, and a gate that fails when a third party
is unreachable teaches people to ignore the gate. What it does is make drift
a decision rather than an accident.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

MANIFEST = (
    Path(__file__).resolve().parents[2] / "shared" / "schema" / "external-contracts.json"
)

OBSERVER_MODULES = ["claude", "copilot", "cursor", "codex", "devin"]


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class TestTheManifestItself:
    def test_it_exists_and_is_versioned(self, manifest):
        assert manifest["vocabularyVersion"]
        assert manifest["contracts"], "no external contract is pinned"
        assert manifest["observers"], "no observer version is pinned"

    def test_every_contract_states_its_risk(self, manifest):
        # A pin with no stated risk is a version number. The risk is the
        # part that tells a reader what happens when it moves — and for two
        # of these the honest answer is "a rename we would not detect".
        for contract in manifest["contracts"]:
            assert contract["risk"].strip(), f"{contract['id']} states no risk"
            assert contract["status"] in {"stable", "unstable"}

    def test_the_unstable_contract_is_labelled_unstable(self, manifest):
        # OTel GenAI conventions are at Development status with documented
        # rename risk. Labelling them stable would be the overclaim; this is
        # the one row where the label carries real weight.
        otel = next(c for c in manifest["contracts"] if c["id"] == "otel-genai-semconv")
        assert otel["status"] == "unstable"


class TestObserverVersionsMatchTheirPins:
    @pytest.mark.parametrize("name", OBSERVER_MODULES)
    def test_the_code_agrees_with_the_manifest(self, name, manifest):
        """Drift in either direction fails.

        A pin bumped without the mapping being re-read is the same defect as
        a mapping changed without the pin moving: in both cases the recorded
        contract version stops describing the code that produced the
        evidence, and every entry derived from it carries a version that is
        not true.
        """
        module = importlib.import_module(f"meridian_core.observers.{name}")
        pinned = next((o for o in manifest["observers"] if o["id"] == name), None)
        assert pinned is not None, (
            f"observer {name!r} declares versions but is not pinned in "
            f"external-contracts.json — an unpinned contract is an unreviewed one"
        )
        assert module.VENDOR_RELEASE == pinned["vendorRelease"], (
            f"{name}: code says vendor_release={module.VENDOR_RELEASE!r}, manifest "
            f"pins {pinned['vendorRelease']!r}. Re-read the mapping, then move the pin."
        )
        assert module.ADAPTER_VERSION == pinned["adapterVersion"]

    def test_no_observer_is_missing_from_the_manifest(self, manifest):
        # The failure this catches is a sixth observer added without a pin.
        # It would work, produce evidence, and record a contract version
        # nobody reviewed.
        pinned = {o["id"] for o in manifest["observers"]}
        assert set(OBSERVER_MODULES) <= pinned

    def test_every_pinned_observer_still_exists(self, manifest):
        # And the reverse: a pin left behind by a deleted observer is a
        # claim about a contract nothing consumes.
        for entry in manifest["observers"]:
            importlib.import_module(f"meridian_core.observers.{entry['id']}")


class TestDegradationIsVisible:
    def test_an_unparseable_format_downgrades_rather_than_going_silent(self, tmp_path):
        """NFR-40 / G3: a contract Meridian cannot parse produces a visible
        warning and the next tier, never a gap in the cloth."""
        from datetime import datetime, timezone

        from meridian_core.observers import base

        def broken(_ws, _now):
            raise base.TelemetryFormatError("field renamed upstream")

        fallback = base.Observation(
            vendor="claude",
            session_id="s",
            confidence=base.CONFIDENCE_INFERRED,
            source=base.CHAIN_FILESYSTEM,
            detail="",
            started_at=None,
            workspace=str(tmp_path),
            agent_id=None,
        )
        tiers = [
            base.EvidenceTier(base.CHAIN_OTEL, base.CONFIDENCE_DIRECT, broken, True),
            base.EvidenceTier(
                base.CHAIN_FILESYSTEM,
                base.CONFIDENCE_INFERRED,
                lambda _ws, _now: fallback,
            ),
        ]
        outcome = base.run_fallback_chain(
            "claude", tiers, Path(tmp_path), datetime.now(timezone.utc)
        )
        # It degraded rather than failing, AND it said so.
        assert outcome.observation is not None
        assert outcome.observation.confidence == base.CONFIDENCE_INFERRED
        assert outcome.warnings, (
            "the chain degraded silently; NFR-32 and NFR-40 both require the "
            "downgrade to be visible within one session"
        )
        assert "renamed" in " ".join(outcome.warnings).lower()
