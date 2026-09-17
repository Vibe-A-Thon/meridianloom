"""Corpus batch 3 — canonical/Merkle malleability, retention/expiry,
observer confidence ceilings, consent/privacy, ingestion exactly-once,
policy bundles, economics binding, origin vocabulary. See harness.py for
coverage limits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meridian_core.governance import policy_bundle
from meridian_core.ingest import (
    DiskExhaustedError,
    EventIngester,
    SourceEvent,
)
from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    canonical_json,
    inclusion_proof,
    verify_inclusion,
)
from meridian_core.ledger.merkle import leaf_hash
from meridian_core.ledger import privacy as ledger_privacy
from meridian_core.metrics import economics as eco
from meridian_core.observers import base as observer_base
from meridian_core.observers import retention as observer_retention

from .harness import (
    Fixture,
    KIND_BLOCKED,
    KIND_DETECTED,
    KIND_REDACTED,
    KIND_RECORDED,
    SURFACE_HOSTED,
    SURFACE_PASSIVE,
)

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": f"ADV3-{seq}",
        "phase": "build",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": "agent",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-17T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


def _ledger(tmp: Path) -> Ledger:
    led = Ledger(tmp / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 4):
        led.append(_entry(seq))
    return led


# -- hosted: canonical malleability --------------------------------------------


def _f_canonical(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "KEY-ORDER":
            # Canonical JSON must hash key order-independently: the same
            # payload in two orders produces the same entry hash input.
            a = canonical_json({"b": 1, "a": 2})
            b = canonical_json({"a": 2, "b": 1})
            assert a == b
        elif case == "DUPLICATE-KEYS":
            # Duplicate keys in a detail string are the caller's problem:
            # json.loads takes the last value deterministically, and the
            # chain records exactly what was persisted.
            led = _ledger(tmp)
            try:
                led.append(
                    _entry(4, input='{"k": 1, "k": 2}', blob_subject="adv")
                )
                row = led.query(action_type="diff", story_id="ADV3-4")[0]
                persisted = led.read_blob(row["input_ref"], row["blob_key_id"])
                assert json.loads(persisted.decode()) == {"k": 2}
                assert led.verify().ok is True
            finally:
                led.close()
        elif case == "CRLF-CONTENT":
            led = _ledger(tmp)
            try:
                led.append(_entry(4, input="line1\r\nline2\rline3", blob_subject="adv"))
                row = led.query(action_type="diff", story_id="ADV3-4")[0]
                assert b"line1\r\nline2\rline3" == led.read_blob(
                    row["input_ref"], row["blob_key_id"]
                )
                assert led.verify().ok is True
            finally:
                led.close()
        elif case == "UNICODE-NORMALIZATION":
            # NFC vs NFD spellings of the same name are DIFFERENT strings:
            # recorded as given, never silently normalised (the record is
            # the evidence; an auditor sees exactly what was written).
            led = _ledger(tmp)
            try:
                nfc = "café"
                nfd = "café"
                assert nfc != nfd
                led.append(_entry(4, actor_id=nfc))
                led.append(_entry(5, actor_id=nfd))
                rows = led.query(action_type="diff", story_id="ADV3-5")
                assert rows[0]["actor_id"] == nfd
                assert led.verify().ok is True
            finally:
                led.close()
        elif case == "EMPTY-BLOB":
            led = _ledger(tmp)
            try:
                led.append(_entry(4, input="", blob_subject="adv"))
                row = led.query(action_type="diff", story_id="ADV3-4")[0]
                assert led.read_blob(row["input_ref"], row["blob_key_id"]) == b""
                assert led.verify().ok is True
            finally:
                led.close()
        else:  # ORIGIN-VOCAB
            led = _ledger(tmp)
            try:
                with pytest.raises(ValueError, match="FR-M40-02"):
                    led.append(_entry(4, origin="bogus-door"))
                assert led.verify().ok is True
            finally:
                led.close()

    return Fixture(
        id=f"CAN-{case}",
        family="canonical_malleability",
        surface=SURFACE_HOSTED,
        kind=KIND_RECORDED if case not in ("ORIGIN-VOCAB",) else KIND_BLOCKED,
        description=f"canonical: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- passive: merkle proof malleability -------------------------------------------


def _f_merkle(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        from meridian_core.ledger.merkle import root as merkle_root

        payloads = [canonical_json({"i": i}) for i in range(8)]
        leaves = [leaf_hash(p) for p in payloads]
        expected_root = merkle_root(leaves)
        proof = inclusion_proof(leaves, 3)
        if case == "FORGED-SIBLING":
            forged = [b"\x00" * 32 if i == 0 else s for i, s in enumerate(proof)]
            assert verify_inclusion(3, leaves[3], len(leaves), forged, expected_root) is False
        elif case == "WRONG-INDEX":
            assert verify_inclusion(4, leaves[3], len(leaves), proof, expected_root) is False
        elif case == "MALLEATED-LEAF":
            assert verify_inclusion(3, leaf_hash(b"forged"), len(leaves), proof, expected_root) is False
        elif case == "TRUNCATED-PROOF":
            assert verify_inclusion(3, leaves[3], len(leaves), proof[:-1], expected_root) is False
        else:  # SANITY
            assert verify_inclusion(3, leaves[3], len(leaves), proof, expected_root) is True

    return Fixture(
        id=f"MERKLE-{case}",
        family="merkle_proof_malleability",
        surface=SURFACE_PASSIVE,
        kind=KIND_DETECTED if case != "SANITY" else KIND_RECORDED,
        description=f"merkle: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- passive: retention / evidence expiry --------------------------------------------


def _f_retention(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "WITHIN-WINDOW":
            record = observer_retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
            expiry = observer_retention.expiry_for(
                record, T0 + timedelta(hours=12)
            )
            assert expiry is None
        elif case == "AFTER-WINDOW":
            record = observer_retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
            expiry = observer_retention.expiry_for(
                record, T0 + timedelta(days=400)
            )
            assert expiry is not None
            assert expiry.vendor == "copilot"
        elif case == "CAPTURED-LATE":
            # A capture landing after the window closed is expired evidence
            # too — the marker names the shut window (FR-M44-13).
            record = observer_retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(days=400)
            )
            expiry = observer_retention.expiry_for(
                record, T0 + timedelta(days=401)
            )
            assert expiry is not None
        elif case == "UNKNOWN-VENDOR":
            record = observer_retention.record_capture(
                "madeup-vendor", "otel", T0, captured_at=T0
            )
            assert record.window_days is None
            assert record.achieved_margin is None  # no fabricated numbers (P25/P26)
            assert observer_retention.expiry_for(record, T0) is None
        else:  # BOUNDARY
            record = observer_retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0
            )
            window = record.window_days
            assert window is not None
            just_before = observer_retention.expiry_for(
                record, T0 + timedelta(days=window, microseconds=-1)
            )
            just_after = observer_retention.expiry_for(
                record, T0 + timedelta(days=window)
            )
            assert just_before is None
            assert just_after is not None

    return Fixture(
        id=f"RET-{case}",
        family="retention_expiry",
        surface=SURFACE_PASSIVE,
        kind=KIND_DETECTED if case in ("AFTER-WINDOW", "CAPTURED-LATE", "BOUNDARY") else KIND_RECORDED,
        description=f"retention: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- passive: observer confidence ceiling -------------------------------------------


def _f_observer_ceiling(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        def scan_direct(workspace: Path, now: datetime):
            return None

        if case == "TRAILER-CLAIMS-DIRECT":
            # The ceiling rule fires at observation time: a scan claiming
            # better confidence than its rung allows is DOWNGRADED to the
            # tier ceiling, never propagated (base.py honesty ceiling).

            def scan_overclaim(workspace: Path, now: datetime):
                return observer_base.Observation(
                    vendor="cursor",
                    session_id="s",
                    confidence="direct",
                    source="test",
                    detail="overclaiming scan",
                    started_at="2026-09-17T00:00:00Z",
                )

            tier = observer_base.EvidenceTier(
                name="git-trailers", confidence="inferred", scan=scan_overclaim
            )
            outcome = observer_base.run_fallback_chain(
                "cursor", [tier], tmp, datetime.now(timezone.utc)
            )
            assert outcome.observation is not None
            assert outcome.observation.confidence == "inferred"
        elif case == "UNKNOWN-TIER":
            tier = observer_base.EvidenceTier(
                name="made-up-tier", confidence="inferred", scan=scan_direct
            )
            with pytest.raises(ValueError, match="unknown fallback-chain tier"):
                observer_base.run_fallback_chain(
                    "cursor", [tier], tmp, datetime.now(timezone.utc)
                )
        else:  # HONEST-CEILING
            tier = observer_base.EvidenceTier(
                name="git-trailers", confidence="inferred", scan=scan_direct
            )
            outcome = observer_base.run_fallback_chain(
                "cursor", [tier], tmp, datetime.now(timezone.utc)
            )
            assert outcome.observation is None  # scan found nothing

    return Fixture(
        id=f"OBS-{case}",
        family="observer_confidence_ceiling",
        surface=SURFACE_PASSIVE,
        kind=KIND_BLOCKED if case != "HONEST-CEILING" else KIND_RECORDED,
        description=f"observer ceiling: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: consent / privacy ----------------------------------------------------------


def _f_privacy(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = _ledger(tmp)
        try:
            controller = ledger_privacy.PrivacyController(led)
            led.append(
                _entry(4, input="private content of bob", blob_subject="bob")
            )
            if case == "NO-CONSENT-WITHHOLDS":
                exported = controller.export_for_recipient("acme-analytics")
                assert "bob" in exported["withheldSubjects"]
                assert "bob" not in exported["payloads"]
            elif case == "CONSENT-ALLOWS":
                controller.record_consent(
                    "bob", "acme-analytics", actor="data-controller"
                )
                exported = controller.export_for_recipient("acme-analytics")
                assert "bob" in exported["consentedSubjects"]
                assert exported["payloads"]["bob"]
            elif case == "FORGED-CONSENT-IGNORED":
                # A consent-shaped entry NOT issued through the privacy
                # vocabulary must not grant consent: the replay honours
                # only entries that claim the privacy pack (a forgery would
                # have to impersonate the controller explicitly — visible
                # in the chain as exactly that).
                led.append(
                    {
                        "story_id": "evil",
                        "phase": "build",
                        "loop_id": "consent",
                        "loop_iteration": 1,
                        "actor_id": "mallory",
                        "actor_version": "0.0.1",
                        "actor_kind": "role",
                        "policy_version": "policy-v1",  # NOT privacy/v1
                        "action_type": "consent_record",
                        "tool_calls": [
                            {
                                "event": "consent",
                                "subjectId": "bob",
                                "recipient": "acme-analytics",
                                "granted": True,
                            }
                        ],
                    }
                )
                assert (
                    controller.is_consented("bob", recipient="acme-analytics")
                    is False
                )
            elif case == "WILDCARD-CONSENT":
                controller.record_consent(
                    "bob", "*", actor="data-controller"
                )
                assert controller.is_consented("bob", recipient="anyone")
            else:  # REVOKE-WINS
                controller.record_consent(
                    "bob", "acme-analytics", actor="data-controller"
                )
                controller.record_consent(
                    "bob",
                    "acme-analytics",
                    granted=False,
                    actor="data-controller",
                )
                assert (
                    controller.is_consented("bob", recipient="acme-analytics")
                    is False
                )
            assert led.verify().ok is True
        finally:
            led.close()

    return Fixture(
        id=f"PRIV-{case}",
        family="privacy_consent",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED
        if case in ("NO-CONSENT-WITHHOLDS", "FORGED-CONSENT-IGNORED", "REVOKE-WINS")
        else KIND_RECORDED,
        description=f"privacy: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: ingestion exactly-once (FR-M41) ------------------------------------------------


def _f_ingest(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = _ledger(tmp)
        try:
            if case == "DUPLICATE-KEY":
                ingester = EventIngester(led, source="adv-dup")
                event = SourceEvent(
                    key="k1", offset=1,
                    body={**_entry(4), "story_id": "ING-1"},
                )
                first = ingester.ingest_batch([event])
                second = ingester.ingest_batch([event])
                assert first.ingested == 1
                assert second.ingested == 0  # exactly-once: replay drops it
            elif case == "EXCLUDED-PATH":
                ingester = EventIngester(
                    led, source="adv-excl", excluded_path_prefixes=("secret/",)
                )
                event = SourceEvent(
                    key="k2", offset=1, path="secret/file.txt",
                    body={**_entry(4), "story_id": "ING-2"},
                )
                result = ingester.ingest_batch([event])
                assert result.ingested == 0
                assert result.drops.get("excluded_path", 0) == 1
            elif case == "UNSUPPORTED-VENDOR":
                ingester = EventIngester(
                    led, source="adv-vendor", supported_vendors=("claude",)
                )
                event = SourceEvent(
                    key="k3", offset=1,
                    body={**_entry(4), "story_id": "ING-3", "vendor": "mallory-vendor"},
                )
                result = ingester.ingest_batch([event])
                assert result.ingested == 0
                assert result.drops.get("unsupported_vendor", 0) == 1
            else:  # DISK-EXHAUSTED
                ingester = EventIngester(
                    led,
                    source="adv-disk",
                    disk_free_bytes=lambda: 0,
                    disk_reserve_bytes=1,
                )
                event = SourceEvent(
                    key="k4", offset=1,
                    body={**_entry(4), "story_id": "ING-4"},
                )
                with pytest.raises(DiskExhaustedError):
                    ingester.ingest_batch([event])
                # Checkpoint untouched: a later healthy ingest still works.
                ingester = EventIngester(led, source="adv-disk")
                assert ingester.ingest_batch([event]).ingested == 1
            assert led.verify().ok is True
        finally:
            led.close()

    return Fixture(
        id=f"ING-{case}",
        family="ingestion_exactly_once",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED if case == "DISK-EXHAUSTED" else KIND_DETECTED,
        description=f"ingestion: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- passive: signed policy bundles ------------------------------------------------------------


def _bundle(tmp: Path, signed_at: str = "2026-09-17T00:00:00Z"):
    ledger = Ledger(tmp / "bundle-ledger", EphemeralSigningKeyProvider())
    try:
        return policy_bundle.sign_bundle(
            ledger,
            bundle_id="ADV-B1",
            pack_text="version: 1\n",
            activation=signed_at,
            expiry="2027-09-17T00:00:00Z",
            precedence=1,
        )
    finally:
        ledger.close()


def _f_bundle(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        bundle = _bundle(tmp)
        if case == "TAMPERED-PACK":
            raw = policy_bundle.bundle_to_dict(bundle)
            raw["packText"] = "version: 99\n"
            evaluation = policy_bundle.evaluate_bundle(
                policy_bundle.bundle_from_dict(raw)
            )
            # Signature no longer matches the recomputed payload:
            # fail-closed invalid, never supplies policy (SEC-35).
            assert evaluation.valid is False
            assert evaluation.status == "invalid"
        elif case == "EXPIRED":
            evaluation = policy_bundle.evaluate_bundle(
                bundle, now="2027-09-18T00:00:00Z"
            )
            assert evaluation.valid is True
            assert evaluation.status == "expired"
        else:  # SANITY
            evaluation = policy_bundle.evaluate_bundle(
                bundle, now="2026-09-17T12:00:00Z"
            )
            assert evaluation.valid is True
            assert evaluation.status == "active"

    return Fixture(
        id=f"BUNDLE-{case}",
        family="policy_bundle_integrity",
        surface=SURFACE_PASSIVE,
        kind=KIND_DETECTED if case != "SANITY" else KIND_RECORDED,
        description=f"policy bundle: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- passive: economics binding -----------------------------------------------------------------


def _f_econ_bind(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        if case == "NO-GATE-STAYS-UNBOUND":
            led = _ledger(tmp)
            try:
                led.append(
                    _entry(4, action_type="tool_call", cost_usd=3.0, run_id="r1")
                )
                lines = eco.lines_from_ledger(led)
                bound = eco.bind_gate_and_commit(led, lines, story_id="ADV3-4")
                assert bound[0].gate_sequence is None
                assert bound[0].merged_commit is None
            finally:
                led.close()
        elif case == "WRONG-COMMIT-IS-ABANDONED":
            attempts = [
                eco.CostLine(
                    story_id="S", attempt_id="a", actor_id="a", phase="p",
                    cost_usd=eco.Decimal("4"), provenance="locally_inferred",
                    gate_sequence=7, merged_commit="dead",
                )
            ]
            change = eco.split_by_outcome("S", attempts, merged_commit="beef")
            assert change.merged.total == eco.Decimal("0")
            assert change.abandoned.total == eco.Decimal("4")
        else:  # EMPTY-AGGREGATE-NO-FABRICATED-CLASSES
            agg = eco.aggregate([])
            assert agg.total == eco.Decimal("0")
            assert agg.by_provenance == {}
            assert agg.by_measurement == {}
            assert agg.by_category == {}

    return Fixture(
        id=f"ECOB-{case}",
        family="economics_binding",
        surface=SURFACE_PASSIVE,
        kind=KIND_RECORDED,
        description=f"economics binding: {case.lower().replace('-', ' ')}",
        fn=fn,
    )


# -- hosted: redaction batch 3 (vendor prefixes) --------------------------------------------------


def _red3(secret: str, marker: str, description: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = _ledger(tmp)
        try:
            led.append(
                _entry(4, input=f"line: {secret}", blob_subject="adv")
            )
            row = led.query(action_type="diff", story_id="ADV3-4")[0]
            persisted = led.read_blob(row["input_ref"], row["blob_key_id"]).decode()
            assert secret not in persisted, f"SECRET LEAKED via {marker}"
            assert "REDACTED" in persisted
            assert led.verify().ok is True
        finally:
            led.close()

    return Fixture(
        id=f"REDACT-{marker}",
        family="secret_redaction",
        surface=SURFACE_HOSTED,
        kind=KIND_REDACTED,
        description=description,
        fn=fn,
    )


RED3_FIXTURES = [
    _red3("xapp-1-A2b3C4d5E6f7G8h9", "XAPP", "Slack app-level token"),
    _red3("shpat_9a8b7c6d5e4f3a2b1c0d", "SHPAT", "Shopify access token"),
    _red3("SG.Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op.Qr9St0Uv1Wx2Yz3a4b5c6d7e8f9g0h1i2", "SENDGRID", "SendGrid API key"),
    _red3("sq0csp-Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op", "SQ0CSP", "Square client secret"),
    _red3("dop_v1_ab1cd2ef3gh4ij5kl6mn7op8qr9st0uv1wx2yz3a4b5c6d7e8f9g0h", "DOP", "DigitalOcean token"),
    _red3("AGE-SECRET-KEY-1ABC9DEF2GHI3JKL4MNO5PQR6STU7VWX8YZ9AB0CDEFGHI1JKLM2NO3PQ4RS", "AGE", "age encryption identity"),
    _red3("sq0atp-Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op", "SQ0ATP", "Square personal access token"),
    _red3("pypi-AgEIcHlwaS5vcmcCJGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6YWJjZGVmZ2hpag", "PYPI", "PyPI API token"),
    _red3("hf_Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3a4b5", "HF", "Hugging Face access token"),
    _red3("ghs_Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3a4b5", "GHS", "GitHub server-to-server token (sanity: covered by gh[pousr]_)"),
]


def fixtures() -> list[Fixture]:
    return [
        _f_canonical(c)
        for c in (
            "KEY-ORDER", "DUPLICATE-KEYS", "CRLF-CONTENT",
            "UNICODE-NORMALIZATION", "EMPTY-BLOB", "ORIGIN-VOCAB",
        )
    ] + [
        _f_merkle(c)
        for c in ("FORGED-SIBLING", "WRONG-INDEX", "MALLEATED-LEAF", "TRUNCATED-PROOF", "SANITY")
    ] + [
        _f_retention(c)
        for c in ("WITHIN-WINDOW", "AFTER-WINDOW", "CAPTURED-LATE", "UNKNOWN-VENDOR", "BOUNDARY")
    ] + [
        _f_observer_ceiling(c)
        for c in ("TRAILER-CLAIMS-DIRECT", "UNKNOWN-TIER", "HONEST-CEILING")
    ] + [
        _f_privacy(c)
        for c in (
            "NO-CONSENT-WITHHOLDS", "CONSENT-ALLOWS", "FORGED-CONSENT-IGNORED",
            "WILDCARD-CONSENT", "REVOKE-WINS",
        )
    ] + [
        _f_ingest(c)
        for c in ("DUPLICATE-KEY", "EXCLUDED-PATH", "UNSUPPORTED-VENDOR", "DISK-EXHAUSTED")
    ] + [
        _f_bundle(c) for c in ("TAMPERED-PACK", "EXPIRED", "SANITY")
    ] + [
        _f_econ_bind(c)
        for c in ("NO-GATE-STAYS-UNBOUND", "WRONG-COMMIT-IS-ABANDONED", "EMPTY-AGGREGATE-NO-FABRICATED-CLASSES")
    ] + RED3_FIXTURES
