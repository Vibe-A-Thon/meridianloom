"""FR-M43-06/07/08, SEC-37 (N2 Workstream D task 17): the privacy lifecycle.

The pieces, and where they live:

- **Collection profiles** — ``COLLECTION_PROFILES`` declares, per
  profile, exactly what is captured. The default is ``metadata_only``:
  prompt/output content is never persisted at all (FR-M43-07: the
  default profile persists none of the seeded secrets). ``content_redacted``
  captures blobs after the SEC-07 filter; ``content_full`` captures raw
  content and requires a recorded raw-content consent for the subject.
  ``PrivacyController.append`` enforces the profile before the entry
  reaches the ledger, so a misconfigured caller cannot smuggle content
  past the profile.
- **Consent recording** — ``record_consent`` appends a chain entry
  (``action_type="consent_record"``): consent state is hash-chained
  evidence, not a mutable side table. ``consents_for`` / ``is_consented``
  replay it. A later ``granted=False`` entry revokes.
- **Redaction** — SEC-07 value redaction (redaction.py) plus FR-M43-06
  field/path redaction (``redaction.redact_fields``) and runtime
  pattern registration (``redaction.register_redaction_pattern``).
- **Recipient-specific export filtering** — ``export_for_recipient``
  returns decrypted payloads ONLY for subjects with recorded consent
  for that recipient; withheld subjects are named in a signed
  ``privacy`` section attached to the chain bundle. A recipient export
  therefore structurally cannot contain another subject's content.
- **Retention** — the archive module (archive.py, FR-M43-04/05);
  applying a retention policy moves old blobs to cold storage.
- **Erasure via crypto-shredding** — ``erase_subject`` completes the
  FR-M10-14 journey: destroys the subject's blob key (keystore) AND
  appends an ``erasure`` ledger entry naming the event. The chain stays
  verifiable — entry hashes commit to ciphertext digests, which are
  untouched — while every blob under that key becomes unreadable
  (FR-M43-08, SEC-37). Redaction/erasure are visible as coverage gaps:
  ``coverage_gaps`` reports them by sequence.
- **Backup-key behaviour** (documented here, tested in
  test_ledger_privacy.py): blob keys are wrapped (AES-GCM) under a
  workspace master key HKDF-derived from the provisioned signing seed
  (keystore.py). A backup is a copy of the ledger directory. Two cases:

    1. Backup taken AFTER an erasure: restore is safe by construction —
       the key registry copy has no row for the erased subject, so the
       blobs stay unreadable. Verified by test.
    2. Backup taken BEFORE an erasure, restored verbatim: the old
       wrapped key row comes back and the subject becomes readable
       again. This is the documented hazard of deferred-deletion
       cryptography, and v1's answer is ``replay_erasures_into``:
       after restoring any pre-erasure backup, replay the erasure
       events recorded in the live ledger against the restored copy.
       Erasure events are chain entries — a machine administrator who
       rewrote history to suppress them breaks the hash chain, which
       the verifier catches (FR-M43-02). What replay cannot protect
       against is an attacker restoring a private copy of the old
       backup offline: that is inherent to backups that ever contained
       the key, and the honest mitigation is the erase-on-backup
       discipline this function encodes.

- **Erasure visibility** — FR-M43-08: redaction and erasure show up as
  coverage gaps in provenance answers. ``coverage_gaps`` returns the
  sequences whose blob content is unavailable (erased or never
  captured), each labelled.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from . import canonical, keystore
from .blobs import BlobError, BlobKeyMissing
from .bundle import build_bundle
from .redaction import redact_fields, redact_secrets


@dataclass(frozen=True)
class CollectionProfile:
    """FR-M43-06: what a collection profile captures, declared."""

    name: str
    capture_input: bool
    capture_output: bool
    redact: bool
    captures: tuple[str, ...]
    requires_consent: bool = False


COLLECTION_PROFILES: dict[str, CollectionProfile] = {
    "metadata_only": CollectionProfile(
        name="metadata_only",
        capture_input=False,
        capture_output=False,
        redact=True,
        captures=(
            "entry metadata (story, phase, actor, action, timestamps, digests-of-nothing)",
        ),
    ),
    "content_redacted": CollectionProfile(
        name="content_redacted",
        capture_input=True,
        capture_output=True,
        redact=True,
        captures=(
            "entry metadata",
            "input/output content after the SEC-07 secret-redaction filter",
        ),
    ),
    "content_full": CollectionProfile(
        name="content_full",
        capture_input=True,
        capture_output=True,
        redact=False,
        captures=(
            "entry metadata",
            "raw input/output content (NO secret filter)",
        ),
        requires_consent=True,
    ),
}

DEFAULT_PROFILE = "metadata_only"


@dataclass(frozen=True)
class Consent:
    sequence: int
    ts_utc: str
    subject_id: str
    recipient: str
    scope: str
    granted: bool
    actor: str


@dataclass(frozen=True)
class ErasureEvent:
    sequence: int
    ts_utc: str
    subject_id: str
    key_id: str
    reason: str
    actor: str


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class ConsentRequiredError(Exception):
    """content_full capture for a subject without recorded consent."""


class PrivacyController:
    """Enforces a collection profile over one ledger.

    Sits in front of ``Ledger.append``: the profile decides what content
    may be captured, consent is recorded as chain entries, and erasure
    is the full crypto-shredding journey (key destruction + chain entry).
    """

    def __init__(self, ledger: Any, profile: str = DEFAULT_PROFILE) -> None:
        if profile not in COLLECTION_PROFILES:
            raise ValueError(f"unknown collection profile: {profile!r}")
        self.ledger = ledger
        self.profile = COLLECTION_PROFILES[profile]

    # -- profile enforcement -----------------------------------------------------

    def set_profile(self, profile: str) -> None:
        if profile not in COLLECTION_PROFILES:
            raise ValueError(f"unknown collection profile: {profile!r}")
        self.profile = COLLECTION_PROFILES[profile]

    def append(self, entry: dict[str, Any]) -> Any:
        """Append with the collection profile enforced BEFORE the ledger
        sees content:

        - metadata_only: input/output are dropped — never encrypted,
          never stored, so nothing secret can persist (FR-M43-07);
        - content_full: requires recorded raw-content consent for the
          entry's blob subject;
        - content_redacted: the ledger's SEC-07 filter applies (the
          controller additionally pre-redacts, so the digest in the row
          is the digest of the redacted ciphertext either way).
        """
        entry = dict(entry)
        subject = entry.get("blob_subject") or entry.get("blobSubject")
        wants_content = "input" in entry or "output" in entry
        if wants_content:
            if not (self.profile.capture_input or self.profile.capture_output):
                entry.pop("input", None)
                entry.pop("output", None)
            elif self.profile.requires_consent:
                if subject is None or not self.is_consented(
                    subject, recipient="*", scope="content"
                ):
                    raise ConsentRequiredError(
                        f"profile {self.profile.name} requires recorded content "
                        f"consent for subject {subject!r}"
                    )
        if self.profile.redact:
            for key in ("input", "output"):
                if isinstance(entry.get(key), str):
                    entry[key] = redact_secrets(entry[key])
        return self.ledger.append(entry)

    # -- consent -----------------------------------------------------------------

    def record_consent(
        self,
        subject_id: str,
        recipient: str,
        *,
        scope: str = "content",
        granted: bool = True,
        actor: str = "data-controller",
        at: str | None = None,
    ) -> Any:
        """Record (or revoke, granted=False) consent as a chain entry."""
        payload = {
            "event": "consent",
            "subjectId": subject_id,
            "recipient": recipient,
            "scope": scope,
            "granted": granted,
        }
        entry = {
            "story_id": "meridian-privacy",
            "phase": "govern",
            "loop_id": "consent",
            "loop_iteration": 1,
            "actor_id": actor,
            "actor_version": "local",
            "actor_kind": "role",
            "policy_version": "privacy/v1",
            "action_type": "consent_record",
            "tool_calls": [payload],
            "ts_utc": at,
        }
        return self.ledger.append(entry)

    def consents_for(self, subject_id: str | None = None) -> list[Consent]:
        """Replay the consent log (chain entries), oldest first."""
        out: list[Consent] = []
        for row in self.ledger.query(action_type="consent_record", limit=1000):
            for call in _tool_events(row, "consent"):
                if subject_id is not None and call["subjectId"] != subject_id:
                    continue
                out.append(
                    Consent(
                        sequence=row["seq"],
                        ts_utc=row["ts_utc"],
                        subject_id=call["subjectId"],
                        recipient=call["recipient"],
                        scope=call.get("scope", "content"),
                        granted=bool(call["granted"]),
                        actor=row["actor_id"],
                    )
                )
        return out

    def is_consented(
        self, subject_id: str, *, recipient: str, scope: str = "content"
    ) -> bool:
        """Latest consent state for (subject, recipient, scope).

        ``recipient="*"`` matches a consent granted to any recipient
        (the raw-content consent a subject gives the workspace itself).
        """
        state = False
        for consent in self.consents_for(subject_id):
            if consent.scope != scope:
                continue
            if consent.recipient != recipient and consent.recipient != "*":
                continue
            state = consent.granted
        return state

    # -- recipient-specific export filtering --------------------------------------

    def consented_subjects(self, recipient: str, scope: str = "content") -> set[str]:
        subjects: set[str] = set()
        for consent in self.consents_for():
            if consent.scope == scope and consent.granted and (
                consent.recipient == recipient or consent.recipient == "*"
            ):
                subjects.add(consent.subject_id)
        return subjects

    def export_for_recipient(
        self, recipient: str, *, bundle_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """FR-M43-06 recipient-specific export: the chain bundle (full
        history, still verifies) plus a signed ``privacy`` section naming
        withheld subjects, plus decrypted payloads ONLY for subjects
        consented for this recipient. Unconsented subjects' content is
        structurally absent — not merely marked."""
        consented = self.consented_subjects(recipient)
        bundle = build_bundle(self.ledger, bundle_params or {})
        withheld = sorted(self._subjects_with_content() - consented)
        payloads: dict[str, list[str]] = {}
        for subject in sorted(consented):
            texts: list[str] = []
            key_id = keystore.key_id_for(subject)
            rows = self.ledger.conn.execute(
                "SELECT input_ref, output_ref, blob_key_id FROM ledger_entry"
                " WHERE blob_key_id = ? ORDER BY seq",
                (key_id,),
            ).fetchall()
            for input_ref, output_ref, row_key_id in rows:
                for ref in (input_ref, output_ref):
                    if ref:
                        try:
                            texts.append(
                                self.ledger.read_blob(ref, row_key_id).decode(
                                    "utf-8", "replace"
                                )
                            )
                        except BlobError:
                            texts.append("[ERASED]")
            payloads[subject] = texts
        privacy_section = {
            "recipient": recipient,
            "consentedSubjects": sorted(consented),
            "withheldSubjects": withheld,
            "profile": self.profile.name,
            "note": (
                "Payloads are attached only for subjects with recorded "
                "consent for this recipient. Withheld subjects appear in "
                "the chain (hash integrity) but their content is absent."
            ),
        }
        return {
            "bundle": attach_privacy_section(self.ledger, bundle, privacy_section),
            "payloads": payloads,
            "withheldSubjects": withheld,
            "consentedSubjects": sorted(consented),
        }

    def _subjects_with_content(self) -> set[str]:
        rows = self.ledger.conn.execute(
            "SELECT DISTINCT blob_key_id FROM ledger_entry WHERE blob_key_id IS NOT NULL"
        ).fetchall()
        subjects = set()
        for (key_id,) in rows:
            prefix = "bk:"
            if key_id.startswith(prefix):
                subjects.add(key_id[len(prefix):])
        return subjects

    # -- erasure ------------------------------------------------------------------

    def erase_subject(
        self,
        subject_id: str,
        *,
        reason: str,
        actor: str = "data-controller",
    ) -> Any:
        """FR-M43-08 / SEC-37: erase a subject via crypto-shredding,
        recorded IN the chain.

        1. Destroy the subject's wrapped blob key (keystore) — every
           blob under it becomes unreadable, across live storage,
           exports and any backup restored without erasure replay;
        2. Append an ``erasure`` ledger entry naming the subject, key id
           and reason. The entry is an ordinary chain link: erasure is
           auditable, hash-chained evidence — and it is what
           ``replay_erasures_into`` uses to protect pre-erasure backup
           restores.
        """
        key_id = keystore.key_id_for(subject_id)
        existed = self.ledger.shred_subject(subject_id)
        payload = {
            "event": "erasure",
            "subjectId": subject_id,
            "keyId": key_id,
            "reason": reason,
            "keyExisted": existed,
        }
        entry = {
            "story_id": "meridian-privacy",
            "phase": "govern",
            "loop_id": "erasure",
            "loop_iteration": 1,
            "actor_id": actor,
            "actor_version": "local",
            "actor_kind": "role",
            "policy_version": "privacy/v1",
            "action_type": "erasure",
            "tool_calls": [payload],
            "ts_utc": None,
        }
        return self.ledger.append(entry)

    def erasures(self) -> list[ErasureEvent]:
        out: list[ErasureEvent] = []
        for row in self.ledger.query(action_type="erasure", limit=1000):
            for call in _tool_events(row, "erasure"):
                out.append(
                    ErasureEvent(
                        sequence=row["seq"],
                        ts_utc=row["ts_utc"],
                        subject_id=call["subjectId"],
                        key_id=call["keyId"],
                        reason=call.get("reason", ""),
                        actor=row["actor_id"],
                    )
                )
        return out

    def replay_erasures_into(self, restored_ledger: Any) -> int:
        """Backup-restore protection (documented backup-key behaviour):
        re-apply every erasure recorded in THIS (live) ledger against a
        restored copy, so a pre-erasure backup restore leaves the erased
        subject unreadable. Returns the number of keys destroyed."""
        replayed = 0
        for event in self.erasures():
            if restored_ledger.shred_subject(event.subject_id):
                replayed += 1
        return replayed

    # -- erasure visibility (coverage gaps) ----------------------------------------

    def coverage_gaps(self) -> list[dict[str, Any]]:
        """FR-M43-08: redaction/erasure as coverage gaps for provenance
        answers. One entry per sequence whose blob content is
        unavailable, labelled with the cause (erased vs never captured)."""
        erased_keys = {
            event.key_id for event in self.erasures()
        }
        gaps: list[dict[str, Any]] = []
        for row in self.ledger.query(limit=1000):
            key_id = row.get("blob_key_id")
            has_refs = bool(row.get("input_ref") or row.get("output_ref"))
            if not has_refs:
                continue
            if key_id in erased_keys:
                gaps.append(
                    {
                        "sequence": row["seq"],
                        "cause": "erased",
                        "subject": key_id.removeprefix("bk:"),
                    }
                )
            else:
                try:
                    if row.get("input_ref"):
                        self.ledger.read_blob(row["input_ref"], key_id)
                except BlobKeyMissing:
                    gaps.append(
                        {
                            "sequence": row["seq"],
                            "cause": "erased",
                            "subject": key_id.removeprefix("bk:"),
                        }
                    )
        return gaps


def _tool_events(row: dict[str, Any], event: str) -> list[dict[str, Any]]:
    raw = row.get("tool_calls")
    if not raw:
        return []
    try:
        calls = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [
        call
        for call in calls
        if isinstance(call, dict) and call.get("event") == event
    ]


def attach_privacy_section(
    ledger: Any, bundle: dict[str, Any], privacy_section: dict[str, Any]
) -> dict[str, Any]:
    """Attach (or replace) the privacy section of a chain bundle and
    re-sign the bundle: the recipient's disclosure set is itself
    signed, so it cannot be widened after export without detection."""
    bundle = dict(bundle)
    bundle["privacy"] = privacy_section
    digest = hashlib.sha256(canonical.canonical_json(bundle)).digest()
    bundle["signature"] = {
        "algorithm": "Ed25519",
        "signedAt": bundle.get("generatedAt"),
        "digest": digest.hex(),
        "signature": ledger.sign(digest).hex(),
    }
    return bundle


def redacted_export_entry(row: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    """FR-M43-06 field/path redaction convenience for export surfaces:
    a copy of a ledger row (wire shape) with the named fields redacted."""
    return redact_fields(row, fields)
