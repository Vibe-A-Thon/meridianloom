"""FR-M42-09/10 + AC-48 (FUT-024; N2 Workstream C tasks T09/T10):
governance-bypass detection.

Meridian reports controls as in force; FR-M42-09 names five circumventions
that MUST be detected when they occur, each from its own evidence source,
deterministically, naming what it saw:

1. ``ruleset_bypass_actor`` — an approval/permission-decision entry whose
   recorded ``approvedBy.class`` claims a HUMAN class while the acting
   identity itself carries ruleset/bypass markers (cross-check of the
   stamped class against the identity, reusing the D40 classifier).
   Evidence source: ledger ``approval`` / ``permission_decision`` rows.
2. ``client_allowlist_tamper`` — the ACP tool allow-list's digest recorded
   at load (a ``policy_version`` row); on reload a digest that differs from
   the recorded one AND is not itself recorded as a policy-version entry is
   a client-side edit, not a version bump. Evidence source: the recorded
   digests vs the current file digest.
3. ``content_exclusion_not_applied`` — a policy exclusion list vs observed
   AGENT file-access entries (``tool_call`` rows attributed ``agent``)
   touching an excluded path: the exclusion did not apply in agent mode.
   Evidence source: ledger ``tool_call`` rows vs the exclusion list.
4. ``provenance_hook_removed`` — the commit-msg hook's installed state is
   ledger-tracked (``hook_lifecycle`` rows); an install record followed by
   a current status that is not installed is a removal/disable. Evidence
   source: the lifecycle rows vs ``hooks.status`` facts.
5. ``telemetry_downgrade`` — observer telemetry state transitions
   (``telemetry_state`` rows): ``enabled`` followed by ``disabled`` for the
   same observer is a downgrade event. Evidence source: the transition rows.

FR-M42-10 / AC-48: every detection produces its own durable ledger entry
(action_type ``bypass_detection``, committed before the detector returns —
FR-M10-08) and downgrades the affected coverage claim WITHIN ONE SESSION:
:func:`bypass_gaps` exposes open detections as envelope ``gaps`` (gapClass
= the circumvention id) and :func:`downgraded_surfaces` names the
observer-health/trust surfaces whose claims are weakened. Meridian weakens
its own claim rather than remaining silent. A detection stays open until
explicitly resolved elsewhere (v1 ships no resolution path: a detected
bypass keeps the claim weakened — the conservative reading).

Detectors are idempotent per evidence: each detection carries a stable
fingerprint and :func:`record_detection` refuses to duplicate an open entry
with the same fingerprint, so re-running a scan is safe across sessions.

Zero model calls (FR-M36-07): every detector is a deterministic scan over
ledger rows and supplied evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..ledger.core import Ledger, utc_now
from ..metrics.coverage import DataGap
from . import approval_class

__all__ = [
    "ALLOWLIST_TAMPER",
    "CONTENT_EXCLUSION_NOT_APPLIED",
    "DETECTION_ACTION",
    "DETECTOR_VERSION",
    "PROVENANCE_HOOK_REMOVED",
    "RULESET_BYPASS_ACTOR",
    "TELEMETRY_DOWNGRADE",
    "BypassDetection",
    "BypassEvidence",
    "bypass_gaps",
    "detect_allowlist_tamper",
    "detect_content_exclusion_gap",
    "detect_provenance_hook_removed",
    "detect_ruleset_bypass_actor",
    "detect_telemetry_downgrade",
    "downgraded_surfaces",
    "observer_health_downgrades",
    "open_detections",
    "record_detection",
    "record_hook_state",
    "record_policy_digest",
    "record_telemetry_state",
    "run_detections",
    "sha256_file",
]

#: The closed circumvention vocabulary (FR-M42-09). Stable ids — they are
#: the gapClass values on coverage envelopes and the keys of every surface
#: mapping below.
RULESET_BYPASS_ACTOR = "ruleset_bypass_actor"
CLIENT_ALLOWLIST_TAMPER = "client_allowlist_tamper"
CONTENT_EXCLUSION_NOT_APPLIED = "content_exclusion_not_applied"
PROVENANCE_HOOK_REMOVED = "provenance_hook_removed"
TELEMETRY_DOWNGRADE = "telemetry_downgrade"

#: The closed set, in canonical order.
CIRCUMVENTIONS: tuple[str, ...] = (
    RULESET_BYPASS_ACTOR,
    CLIENT_ALLOWLIST_TAMPER,
    CONTENT_EXCLUSION_NOT_APPLIED,
    PROVENANCE_HOOK_REMOVED,
    TELEMETRY_DOWNGRADE,
)

#: Ledger action_type of a detection entry (FR-M42-10 — its own type).
DETECTION_ACTION = "bypass_detection"

#: Detector version: bump when a detector's rule changes; recorded on every
#: entry so an old detection is interpretable without this module.
DETECTOR_VERSION = "bypass/v1"

#: Action types of the human/policy decision entries detector 1 scans.
_DECISION_ACTION_TYPES = ("approval", "permission_decision")

#: Action types the evidence recorders write.
_POLICY_DIGEST_ACTION = "policy_version"
_HOOK_LIFECYCLE_ACTION = "hook_lifecycle"
_TELEMETRY_STATE_ACTION = "telemetry_state"

#: FR-M42-10: which claim surface each circumvention downgrades. These are
#: the observer-health/trust (and provenance) claims Meridian weakens.
SURFACE_BY_CIRCUMVENTION: dict[str, str] = {
    RULESET_BYPASS_ACTOR: "trust/approval-integrity",
    CLIENT_ALLOWLIST_TAMPER: "trust/permission-policy-integrity",
    CONTENT_EXCLUSION_NOT_APPLIED: "observer-health/evidence",
    PROVENANCE_HOOK_REMOVED: "provenance-trail",
    TELEMETRY_DOWNGRADE: "observer-health/telemetry",
}


@dataclass(frozen=True)
class BypassDetection:
    """One detected circumvention: what it is, what was seen, and the
    stable fingerprint that dedupes its ledger entry."""

    circumvention: str  # a member of CIRCUMVENTIONS
    detail: str  # plain words naming what was seen
    fingerprint: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    sequence: int | None = None  # the detection entry, set once recorded

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "circumvention": self.circumvention,
            "detail": self.detail,
            "fingerprint": self.fingerprint,
            "evidence": dict(self.evidence),
            "detectorVersion": DETECTOR_VERSION,
        }
        if self.sequence is not None:
            payload["sequence"] = self.sequence
        return payload


@dataclass(frozen=True)
class BypassEvidence:
    """The out-of-ledger evidence the detectors need, supplied by the
    caller (the sidecar scan or the tests). A detector with no evidence
    for its source is skipped — absence of evidence is never a detection."""

    allowlist_path: str | None = None  # the tracked allow-list file
    allowlist_sha256: str | None = None  # its CURRENT digest (at reload)
    excluded_paths: tuple[str, ...] = ()  # the policy exclusion list
    hook_status: Mapping[str, Any] | None = None  # hooks.status() facts


# -- ledger detail access ------------------------------------------------------


def _read_detail(ledger: Ledger, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def _append_governance_row(
    ledger: Ledger,
    *,
    action_type: str,
    decision: str,
    detail: Mapping[str, Any],
    story_id: str,
) -> int:
    result = ledger.append(
        {
            "story_id": story_id,
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/bypass/v1",
            "action_type": action_type,
            "decision": decision,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(detail, ensure_ascii=False),
        }
    )
    return result.sequence


# -- evidence recorders (the load-time/transition side of the detectors) -------


def record_policy_digest(
    ledger: Ledger, *, path: str, sha256: str, recorded_by: str = "sidecar"
) -> int:
    """Record the allow-list digest at load — the baseline detector 2
    compares the next reload against. A legitimate policy version bump
    records its new digest here; an unrecorded change is the tamper."""
    return _append_governance_row(
        ledger,
        action_type=_POLICY_DIGEST_ACTION,
        decision="recorded",
        detail={
            "method": "policy.digest.record",
            "path": str(path),
            "sha256": sha256,
            "recordedAt": utc_now(),
            "recordedBy": recorded_by,
        },
        story_id=f"policy:{path}",
    )


def record_hook_state(
    ledger: Ledger, *, installed: bool, hook_path: str | None = None
) -> int:
    """Ledger-track the commit-msg hook's installed state (detector 4's
    baseline). The install RPC (or the host) records ``installed``; the
    removal path records ``removed``."""
    detail: dict[str, Any] = {
        "method": "hook.lifecycle",
        "installed": bool(installed),
        "recordedAt": utc_now(),
    }
    if hook_path:
        detail["hookPath"] = hook_path
    return _append_governance_row(
        ledger,
        action_type=_HOOK_LIFECYCLE_ACTION,
        decision="installed" if installed else "removed",
        detail=detail,
        story_id="hooks:commit-msg",
    )


def record_telemetry_state(
    ledger: Ledger, *, observer: str, enabled: bool, source: str = "sidecar"
) -> int:
    """Record an observer's telemetry state transition (detector 5's
    evidence). ``enabled`` -> ``disabled`` for the same observer is the
    downgrade detector 5 names."""
    return _append_governance_row(
        ledger,
        action_type=_TELEMETRY_STATE_ACTION,
        decision="enabled" if enabled else "disabled",
        detail={
            "method": "telemetry.state",
            "observer": observer,
            "enabled": bool(enabled),
            "source": source,
            "recordedAt": utc_now(),
        },
        story_id=f"telemetry:{observer}",
    )


def sha256_file(path: str) -> str:
    """The hex SHA-256 of a file — the digest the allow-list tracker records
    and re-checks. Raises OSError when the file cannot be read (the caller
    surfaces that; a missing baseline never fabricates a detection)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- the five detectors (FR-M42-09) --------------------------------------------


def detect_ruleset_bypass_actor(
    ledger: Ledger, *, limit: int = 10_000
) -> list[BypassDetection]:
    """Detector 1: a decision entry claiming a human ``approvedBy`` class
    whose acting identity classifies as a ruleset/bypass actor."""
    rows: list[dict[str, Any]] = []
    for action_type in _DECISION_ACTION_TYPES:
        rows.extend(ledger.query(action_type=action_type, limit=limit))
    rows.sort(key=lambda row: row["seq"])
    detections: list[BypassDetection] = []
    for row in rows:
        detail = _read_detail(ledger, row)
        approved_by = detail.get("approvedBy")
        claimed = approved_by.get("class") if isinstance(approved_by, Mapping) else None
        if not approval_class.is_human_class(claimed):
            continue
        identity = " ".join(
            str(part)
            for part in (
                detail.get("name"),
                detail.get("email"),
                row.get("human_actor"),
                row.get("actor_id"),
            )
            if part
        )
        if not identity:
            continue
        classified = approval_class.classify(name=identity)
        if classified != "ruleset_actor":
            continue
        detections.append(
            BypassDetection(
                circumvention=RULESET_BYPASS_ACTOR,
                detail=(
                    f"entry {row['seq']} ({row['action_type']}) records "
                    f"approvedBy.class '{claimed}' but its acting identity "
                    f"'{identity}' classifies as ruleset_actor (ruleset/bypass "
                    "markers) — a ruleset bypass actor claimed a human class"
                ),
                fingerprint=f"{RULESET_BYPASS_ACTOR}:{row['seq']}",
                evidence={
                    "entrySequence": row["seq"],
                    "actionType": row["action_type"],
                    "claimedClass": claimed,
                    "identity": identity,
                    "classifiedAs": classified,
                },
            )
        )
    return detections


def detect_allowlist_tamper(
    ledger: Ledger, *, path: str, current_sha256: str, limit: int = 10_000
) -> list[BypassDetection]:
    """Detector 2: the allow-list digest changed since the recorded
    baseline and the new digest appears in NO policy-version entry — a
    client-side edit, not a version bump. No recorded baseline means the
    tracker never ran: nothing to compare, no detection (P26: unknown is
    a state, never fabricated into a claim)."""
    records = [
        row
        for row in ledger.query(action_type=_POLICY_DIGEST_ACTION, limit=limit)
        if _read_detail(ledger, row).get("path") == str(path)
    ]
    if not records:
        return []
    baseline_detail = _read_detail(ledger, records[-1])
    baseline = str(baseline_detail.get("sha256") or "")
    baseline_seq = int(records[-1]["seq"])
    if not baseline or current_sha256 == baseline:
        return []
    recorded_digests = {
        str(_read_detail(ledger, row).get("sha256") or "") for row in records
    }
    if current_sha256 in recorded_digests:
        return []  # a legitimate version bump recorded the new digest
    return [
        BypassDetection(
            circumvention=CLIENT_ALLOWLIST_TAMPER,
            detail=(
                f"the allow-list at '{path}' now digests to {current_sha256}, "
                f"which matches no recorded policy-version entry (baseline "
                f"{baseline} recorded at entry {baseline_seq}) — the file was "
                "edited outside the policy-version path"
            ),
            fingerprint=f"{CLIENT_ALLOWLIST_TAMPER}:{path}:{baseline_seq}",
            evidence={
                "path": str(path),
                "recordedSha256": baseline,
                "recordedAtSequence": baseline_seq,
                "currentSha256": current_sha256,
            },
        )
    ]


def _path_is_excluded(path: str, excluded_paths: Sequence[str]) -> str | None:
    """The exclusion entry a path falls under (normalized prefix match), or
    None. An exclusion of ``secrets/`` covers ``secrets`` and everything
    beneath it; an exact file entry covers just that file."""
    normalized = path.replace("\\", "/").strip("/")
    for raw in excluded_paths:
        entry = str(raw).replace("\\", "/").strip("/")
        if not entry:
            continue
        if normalized == entry or normalized.startswith(entry + "/"):
            return str(raw)
    return None


def detect_content_exclusion_gap(
    ledger: Ledger, *, excluded_paths: Sequence[str], limit: int = 10_000
) -> list[BypassDetection]:
    """Detector 3: an AGENT-attributed file-access entry touching an
    excluded path — the content exclusion did not apply in agent mode."""
    if not excluded_paths:
        return []
    from ..metrics.coverage import ledger_row_attribution_state

    detections: list[BypassDetection] = []
    for row in ledger.query(action_type="tool_call", limit=limit):
        if ledger_row_attribution_state(row) != "agent":
            continue
        detail = _read_detail(ledger, row)
        path = detail.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        matched = _path_is_excluded(path.strip(), excluded_paths)
        if matched is None:
            continue
        detections.append(
            BypassDetection(
                circumvention=CONTENT_EXCLUSION_NOT_APPLIED,
                detail=(
                    f"agent file-access entry {row['seq']} touched excluded "
                    f"path '{path}' (matched exclusion '{matched}') — the "
                    "content exclusion did not apply in agent mode"
                ),
                fingerprint=f"{CONTENT_EXCLUSION_NOT_APPLIED}:{row['seq']}",
                evidence={
                    "entrySequence": row["seq"],
                    "path": path,
                    "matchedExclusion": matched,
                },
            )
        )
    return detections


def detect_provenance_hook_removed(
    ledger: Ledger, *, status: Mapping[str, Any], limit: int = 10_000
) -> list[BypassDetection]:
    """Detector 4: an installed-state baseline exists and the hook's
    current status is not installed — the provenance hook was removed or
    disabled. Only an explicit install record establishes the baseline
    (the hook is opt-in; never-installed is not a removal)."""
    if status.get("installed"):
        return []
    rows = ledger.query(action_type=_HOOK_LIFECYCLE_ACTION, limit=limit)
    installs = [
        row for row in rows if row.get("decision") == "installed"
    ]
    if not installs:
        return []
    baseline = installs[-1]
    detail = _read_detail(ledger, baseline)
    return [
        BypassDetection(
            circumvention=PROVENANCE_HOOK_REMOVED,
            detail=(
                f"the commit-msg provenance hook was recorded installed at "
                f"entry {baseline['seq']}"
                + (f" ({detail.get('hookPath')})" if detail.get("hookPath") else "")
                + f" but its current status is 'not installed' "
                f"({status.get('detail', 'no detail')}) — the hook was "
                "removed or disabled"
            ),
            fingerprint=f"{PROVENANCE_HOOK_REMOVED}:{baseline['seq']}",
            evidence={
                "installedAtSequence": baseline["seq"],
                "hookPath": detail.get("hookPath"),
                "currentStatus": dict(status),
            },
        )
    ]


def detect_telemetry_downgrade(
    ledger: Ledger, *, limit: int = 10_000
) -> list[BypassDetection]:
    """Detector 5: per observer, an ``enabled`` telemetry state followed by
    a ``disabled`` state — telemetry disabled after having been enabled.
    Each disabled row that closes an enabled interval is one event."""
    rows = ledger.query(action_type=_TELEMETRY_STATE_ACTION, limit=limit)
    detections: list[BypassDetection] = []
    enabled_observers: set[str] = set()
    for row in rows:  # query returns ascending seq — a state machine walk
        detail = _read_detail(ledger, row)
        observer = str(detail.get("observer") or "")
        if not observer:
            continue
        if row.get("decision") == "enabled" or detail.get("enabled") is True:
            enabled_observers.add(observer)
        elif (
            row.get("decision") == "disabled" or detail.get("enabled") is False
        ) and observer in enabled_observers:
            enabled_observers.discard(observer)
            detections.append(
                BypassDetection(
                    circumvention=TELEMETRY_DOWNGRADE,
                    detail=(
                        f"observer '{observer}' telemetry transitioned "
                        f"enabled -> disabled at entry {row['seq']} — "
                        "telemetry was disabled after having been enabled"
                    ),
                    fingerprint=f"{TELEMETRY_DOWNGRADE}:{observer}:{row['seq']}",
                    evidence={
                        "observer": observer,
                        "transitionAtSequence": row["seq"],
                    },
                )
            )
    return detections


# -- recording (FR-M42-10: durable before return, idempotent per fingerprint) ---


def _open_fingerprints(ledger: Ledger, *, limit: int = 10_000) -> set[str]:
    fingerprints: set[str] = set()
    for row in ledger.query(action_type=DETECTION_ACTION, limit=limit):
        detail = _read_detail(ledger, row)
        fingerprint = detail.get("fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            fingerprints.add(fingerprint)
    return fingerprints


def record_detection(ledger: Ledger, detection: BypassDetection) -> int | None:
    """Append the detection's own ledger entry (FR-M42-10), durable before
    return (FR-M10-08). An open entry with the same fingerprint already
    exists: this scan already reported it — no duplicate row, None is
    returned and the existing claim stays weakened."""
    if detection.fingerprint in _open_fingerprints(ledger):
        return None
    return _append_governance_row(
        ledger,
        action_type=DETECTION_ACTION,
        decision="detected",
        detail=detection.to_dict(),
        story_id=f"bypass:{detection.circumvention}",
    )


def run_detections(ledger: Ledger, evidence: BypassEvidence) -> list[BypassDetection]:
    """Run every detector whose evidence source is present, record one
    ledger entry per NEW detection, and return all detections found this
    scan (each carries its entry sequence once recorded)."""
    found: list[BypassDetection] = []
    found.extend(detect_ruleset_bypass_actor(ledger))
    if evidence.allowlist_path is not None and evidence.allowlist_sha256 is not None:
        found.extend(
            detect_allowlist_tamper(
                ledger,
                path=evidence.allowlist_path,
                current_sha256=evidence.allowlist_sha256,
            )
        )
    if evidence.excluded_paths:
        found.extend(
            detect_content_exclusion_gap(ledger, excluded_paths=evidence.excluded_paths)
        )
    if evidence.hook_status is not None:
        found.extend(detect_provenance_hook_removed(ledger, status=evidence.hook_status))
    found.extend(detect_telemetry_downgrade(ledger))
    recorded: list[BypassDetection] = []
    for detection in found:
        sequence = record_detection(ledger, detection)
        recorded.append(
            BypassDetection(
                circumvention=detection.circumvention,
                detail=detection.detail,
                fingerprint=detection.fingerprint,
                evidence=detection.evidence,
                sequence=sequence
                if sequence is not None
                else _existing_sequence(ledger, detection.fingerprint),
            )
        )
    return recorded


def _existing_sequence(ledger: Ledger, fingerprint: str) -> int | None:
    for row in reversed(ledger.query(action_type=DETECTION_ACTION, limit=10_000)):
        detail = _read_detail(ledger, row)
        if detail.get("fingerprint") == fingerprint:
            return int(row["seq"])
    return None


# -- the downgrade wiring (FR-M42-10 / AC-48) -----------------------------------


def open_detections(ledger: Ledger, *, limit: int = 10_000) -> list[BypassDetection]:
    """Every detection currently open (v1: every recorded detection — no
    resolution path ships). The claim stays weakened until one does."""
    detections: list[BypassDetection] = []
    for row in ledger.query(action_type=DETECTION_ACTION, limit=limit):
        detail = _read_detail(ledger, row)
        circumvention = detail.get("circumvention")
        if not isinstance(circumvention, str) or circumvention not in CIRCUMVENTIONS:
            continue
        detections.append(
            BypassDetection(
                circumvention=circumvention,
                detail=str(detail.get("detail") or ""),
                fingerprint=str(detail.get("fingerprint") or f"seq:{row['seq']}"),
                evidence=detail.get("evidence")
                if isinstance(detail.get("evidence"), Mapping)
                else {},
                sequence=int(row["seq"]),
            )
        )
    return detections


def bypass_gaps(ledger: Ledger) -> tuple[DataGap, ...]:
    """FR-M42-10: open detections as coverage-envelope gaps — the gapClass
    IS the circumvention id, aggregated per class with the newest detection
    named. A metric that consults this weakens its own claim in the same
    operation that produces its figure (NFR-34): the envelope it reports
    says WHICH control was circumvented, never silently 'complete'."""
    per_class: dict[str, list[BypassDetection]] = {}
    for detection in open_detections(ledger):
        per_class.setdefault(detection.circumvention, []).append(detection)
    gaps = []
    for circumvention in CIRCUMVENTIONS:
        detections = per_class.get(circumvention)
        if not detections:
            continue
        newest = detections[-1]
        gaps.append(
            DataGap(
                gapClass=circumvention,
                count=len(detections),
                detail=(
                    f"newest detection at entry {newest.sequence}: {newest.detail}"
                ),
            )
        )
    return tuple(gaps)


def downgraded_surfaces(ledger: Ledger) -> dict[str, list[str]]:
    """FR-M42-10: the observer-health/trust/provenance claim surfaces
    weakened right now, each mapped to the open circumvention ids that
    weaken it. A surface that reads this map MUST present itself as
    downgraded rather than in force (Meridian weakens its own claim)."""
    surfaces: dict[str, list[str]] = {}
    for detection in open_detections(ledger):
        surface = SURFACE_BY_CIRCUMVENTION[detection.circumvention]
        surfaces.setdefault(surface, [])
        if detection.circumvention not in surfaces[surface]:
            surfaces[surface].append(detection.circumvention)
    return {surface: sorted(ids) for surface, ids in sorted(surfaces.items())}


def observer_health_downgrades(ledger: Ledger) -> list[dict[str, Any]]:
    """The downgrade records shaped for the observer-health surface
    (doctor/observe-health consume the same list-of-dicts shape): one
    entry per weakened surface, status ``downgraded``, naming the
    circumvention and the detection entry."""
    records = []
    for surface, circumventions in downgraded_surfaces(ledger).items():
        records.append(
            {
                "check": surface,
                "status": "downgraded",
                "detail": (
                    "coverage claim weakened by open bypass detection(s): "
                    + ", ".join(circumventions)
                    + " (FR-M42-10)"
                ),
            }
        )
    return records
