"""Bypass detection (FR-M42-09), the ledger entry + same-session downgrade
(FR-M42-10), and AC-48 — N2 Workstream C tasks T09/T10.

Each named circumvention has its own detector test over its own evidence
source; the detection entry is its own action_type, durable before the
detector returns; and the downgrade (envelope gapClass = the
circumvention id, plus the weakened observer-health/trust surfaces) is
visible from the SAME ledger in the SAME session — Meridian weakens its
own claim rather than remaining silent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core.governance import approval_class, bypass
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider

#: A ruleset-bypass identity (the FR-M42-09 circumvention shape): the actor
#: IS the repository ruleset's bypass actor, but the entry claims a human.
BYPASS_IDENTITY = "repo-ruleset-bypass-actor"


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _append(
    ledger: Ledger,
    *,
    action_type: str,
    decision: str | None = None,
    detail: dict | None = None,
    actor_id: str = "governor",
    actor_kind: str = "meta",
    vendor: str = "meridian",
    confidence: str = "direct",
    story_id: str = "story-1",
) -> int:
    entry: dict = {
        "story_id": story_id,
        "phase": "review",
        "loop_id": "governance",
        "loop_iteration": 1,
        "actor_id": actor_id,
        "actor_version": "0",
        "actor_kind": actor_kind,
        "policy_version": "governance/test",
        "action_type": action_type,
        "vendor": vendor,
        "observation_confidence": confidence,
        "input": json.dumps(detail or {}, ensure_ascii=False),
    }
    if decision is not None:
        entry["decision"] = decision
    return ledger.append(entry).sequence


def _detection_rows(ledger: Ledger) -> list[dict]:
    return ledger.query(action_type=bypass.DETECTION_ACTION, limit=1000)


# -- detector 1: ruleset bypass actor claiming a human class (FR-M42-09) -------


def test_ruleset_bypass_actor_detected(ledger: Ledger) -> None:
    """An approval whose approvedBy.class claims human_individual while the
    acting identity carries ruleset/bypass markers is detected, and the
    detection names the entry and the identity."""
    seq = _append(
        ledger,
        action_type="approval",
        decision="approved",
        actor_id=BYPASS_IDENTITY,
        detail={
            "approvedBy": approval_class.stamp("human_individual", "asserted"),
            "decision": "approve",
        },
    )
    detections = bypass.detect_ruleset_bypass_actor(ledger)
    assert len(detections) == 1
    detection = detections[0]
    assert detection.circumvention == bypass.RULESET_BYPASS_ACTOR
    assert detection.evidence["entrySequence"] == seq
    assert detection.evidence["claimedClass"] == "human_individual"
    assert detection.evidence["classifiedAs"] == "ruleset_actor"
    assert BYPASS_IDENTITY in detection.detail


def test_ruleset_bypass_actor_clean_human_not_flagged(ledger: Ledger) -> None:
    """A genuinely human approval (no markers) is not a detection — the
    cross-check must not cry wolf on real humans."""
    _append(
        ledger,
        action_type="approval",
        decision="approved",
        actor_id="ada@example.com",
        detail={
            "approvedBy": approval_class.stamp("human_individual", "verified"),
            "decision": "approve",
        },
    )
    assert bypass.detect_ruleset_bypass_actor(ledger) == []


def test_ruleset_bypass_actor_permission_decision_scanned(ledger: Ledger) -> None:
    """Permission decisions are decision entries too — detector 1 scans
    both approval and permission_decision populations."""
    _append(
        ledger,
        action_type="permission_decision",
        decision="approved",
        actor_id="branch-ruleset-bypass",
        detail={
            "approvedBy": approval_class.stamp("human_individual"),
            "toolKind": "edit",
        },
        story_id="acp:s1",
    )
    detections = bypass.detect_ruleset_bypass_actor(ledger)
    assert [d.circumvention for d in detections] == [bypass.RULESET_BYPASS_ACTOR]


# -- detector 2: client-edited tool allow-list (FR-M42-09) ---------------------


def test_client_allowlist_tamper_detected(ledger: Ledger) -> None:
    """The digest recorded at load differs from the reloaded file's digest
    and matches no policy-version entry: a client-side edit, detected."""
    bypass.record_policy_digest(ledger, path="policy/acp-permissions.yaml", sha256="a" * 64)
    detections = bypass.detect_allowlist_tamper(
        ledger, path="policy/acp-permissions.yaml", current_sha256="b" * 64
    )
    assert len(detections) == 1
    assert detections[0].circumvention == bypass.CLIENT_ALLOWLIST_TAMPER
    assert detections[0].evidence["recordedSha256"] == "a" * 64
    assert detections[0].evidence["currentSha256"] == "b" * 64


def test_client_allowlist_version_bump_not_tamper(ledger: Ledger) -> None:
    """A changed digest that IS recorded as a policy-version entry is a
    legitimate version bump, not a tamper signal."""
    bypass.record_policy_digest(ledger, path="policy/acp-permissions.yaml", sha256="a" * 64)
    bypass.record_policy_digest(ledger, path="policy/acp-permissions.yaml", sha256="b" * 64)
    assert (
        bypass.detect_allowlist_tamper(
            ledger, path="policy/acp-permissions.yaml", current_sha256="b" * 64
        )
        == []
    )


def test_client_allowlist_no_baseline_not_tamper(ledger: Ledger) -> None:
    """No recorded digest means the tracker never ran — unknown is a state,
    never fabricated into a detection (P26)."""
    assert (
        bypass.detect_allowlist_tamper(
            ledger, path="policy/acp-permissions.yaml", current_sha256="b" * 64
        )
        == []
    )


# -- detector 3: content exclusion not applying in agent mode (FR-M42-09) ------


def test_content_exclusion_gap_detected(ledger: Ledger) -> None:
    """An agent-attributed file-access entry touching an excluded path is
    detected; a human entry touching the same path is not (the exclusion
    failing in AGENT mode is the circumvention)."""
    _append(
        ledger,
        action_type="tool_call",
        actor_id="agent-cursor",
        actor_kind="external",
        vendor="cursor",
        confidence="telemetry",
        detail={"path": "secrets/credentials.env", "tool": "read"},
        story_id="acp:s1",
    )
    _append(
        ledger,
        action_type="tool_call",
        actor_id="ada@example.com",
        actor_kind="external",
        confidence="direct",
        detail={"path": "secrets/credentials.env", "tool": "read"},
        story_id="acp:s1",
    )
    detections = bypass.detect_content_exclusion_gap(
        ledger, excluded_paths=["secrets/"]
    )
    assert len(detections) == 1
    assert detections[0].circumvention == bypass.CONTENT_EXCLUSION_NOT_APPLIED
    assert detections[0].evidence["path"] == "secrets/credentials.env"
    assert detections[0].evidence["matchedExclusion"] == "secrets/"


def test_content_exclusion_agent_outside_excluded_paths_clean(ledger: Ledger) -> None:
    _append(
        ledger,
        action_type="tool_call",
        actor_id="agent-cursor",
        actor_kind="external",
        vendor="cursor",
        confidence="telemetry",
        detail={"path": "src/app.py", "tool": "read"},
        story_id="acp:s1",
    )
    assert bypass.detect_content_exclusion_gap(ledger, excluded_paths=["secrets/"]) == []


# -- detector 4: removed or disabled provenance hook (FR-M42-09) ----------------


def test_provenance_hook_removed_detected(ledger: Ledger) -> None:
    """An installed baseline followed by a not-installed current status is
    a removal; while the hook is present there is no detection."""
    bypass.record_hook_state(ledger, installed=True, hook_path=".git/hooks/commit-msg")
    status_present = {"installed": True, "detail": "Meridian commit-msg hook installed"}
    assert bypass.detect_provenance_hook_removed(ledger, status=status_present) == []
    status_gone = {"installed": False, "detail": "commit-msg hook not installed"}
    detections = bypass.detect_provenance_hook_removed(ledger, status=status_gone)
    assert len(detections) == 1
    assert detections[0].circumvention == bypass.PROVENANCE_HOOK_REMOVED
    assert detections[0].evidence["installedAtSequence"] >= 1
    assert "not installed" in detections[0].detail


def test_provenance_hook_never_installed_not_detection(ledger: Ledger) -> None:
    """The hook is opt-in: never-installed is the honest default, never a
    removal — only an install baseline establishes the claim."""
    status = {"installed": False, "detail": "commit-msg hook not installed"}
    assert bypass.detect_provenance_hook_removed(ledger, status=status) == []


# -- detector 5: telemetry disabled after being enabled (FR-M42-09) --------------


def test_telemetry_downgrade_detected(ledger: Ledger) -> None:
    """enabled -> disabled for the same observer is the downgrade event;
    disabled-without-enable and enable-alone are not."""
    bypass.record_telemetry_state(ledger, observer="claude", enabled=False)
    detections = bypass.detect_telemetry_downgrade(ledger)
    assert detections == []  # disabled after never-enabled: no downgrade
    bypass.record_telemetry_state(ledger, observer="claude", enabled=True)
    bypass.record_telemetry_state(ledger, observer="claude", enabled=False)
    bypass.record_telemetry_state(ledger, observer="codex", enabled=True)
    detections = bypass.detect_telemetry_downgrade(ledger)
    assert len(detections) == 1
    assert detections[0].circumvention == bypass.TELEMETRY_DOWNGRADE
    assert detections[0].evidence["observer"] == "claude"


# -- FR-M42-10: entry + same-session downgrade -----------------------------------


def _assert_downgrade_visible(ledger: Ledger, circumvention: str) -> None:
    """The downgrade half of FR-M42-10, checked on the same in-session
    ledger: the envelope gap rides under the circumvention id and the
    weakened surface is named."""
    gaps = bypass.bypass_gaps(ledger)
    matching = [gap for gap in gaps if gap.gapClass == circumvention]
    assert matching, f"no envelope gap for {circumvention}"
    assert matching[0].count >= 1
    assert matching[0].detail
    surfaces = bypass.downgraded_surfaces(ledger)
    assert any(
        circumvention in circumventions for circumventions in surfaces.values()
    ), f"no weakened surface for {circumvention}"
    health = bypass.observer_health_downgrades(ledger)
    assert any(record["status"] == "downgraded" for record in health)


@pytest.mark.parametrize(
    "circumvention",
    list(bypass.CIRCUMVENTIONS),
    ids=list(bypass.CIRCUMVENTIONS),
)
def test_each_detection_records_entry_and_downgrades_same_session(
    ledger: Ledger, circumvention: str
) -> None:
    """FR-M42-10 per circumvention: the detection produces its own durable
    ledger entry AND downgrades the affected coverage claim within one
    session — the entry and the weakened claim both read from the same
    in-process ledger, no restart, no second call."""
    if circumvention == bypass.RULESET_BYPASS_ACTOR:
        _append(
            ledger,
            action_type="approval",
            decision="approved",
            actor_id=BYPASS_IDENTITY,
            detail={"approvedBy": approval_class.stamp("human_individual", "asserted")},
        )
        detection = bypass.detect_ruleset_bypass_actor(ledger)[0]
    elif circumvention == bypass.CLIENT_ALLOWLIST_TAMPER:
        bypass.record_policy_digest(ledger, path="policy/acp-permissions.yaml", sha256="a" * 64)
        detection = bypass.detect_allowlist_tamper(
            ledger, path="policy/acp-permissions.yaml", current_sha256="b" * 64
        )[0]
    elif circumvention == bypass.CONTENT_EXCLUSION_NOT_APPLIED:
        _append(
            ledger,
            action_type="tool_call",
            actor_id="agent-cursor",
            actor_kind="external",
            vendor="cursor",
            confidence="telemetry",
            detail={"path": "secrets/key.pem"},
            story_id="acp:s1",
        )
        detection = bypass.detect_content_exclusion_gap(
            ledger, excluded_paths=["secrets/"]
        )[0]
    elif circumvention == bypass.PROVENANCE_HOOK_REMOVED:
        bypass.record_hook_state(ledger, installed=True)
        detection = bypass.detect_provenance_hook_removed(
            ledger, status={"installed": False, "detail": "commit-msg hook not installed"}
        )[0]
    else:  # telemetry downgrade
        bypass.record_telemetry_state(ledger, observer="claude", enabled=True)
        bypass.record_telemetry_state(ledger, observer="claude", enabled=False)
        detection = bypass.detect_telemetry_downgrade(ledger)[0]

    before = ledger.last_sequence
    sequence = bypass.record_detection(ledger, detection)
    assert sequence is not None and sequence > before  # durable before return
    rows = _detection_rows(ledger)
    assert len(rows) == 1
    assert rows[0]["decision"] == "detected"
    detail = json.loads(ledger.read_blob(rows[0]["input_ref"], rows[0]["blob_key_id"]))
    assert detail["circumvention"] == circumvention
    assert detail["fingerprint"] == detection.fingerprint
    assert detail["detectorVersion"] == bypass.DETECTOR_VERSION
    _assert_downgrade_visible(ledger, circumvention)


def test_detection_is_idempotent_across_rescans(ledger: Ledger) -> None:
    """Re-running the same scan never duplicates the entry (stable
    fingerprint): the claim stays weakened, the ledger stays honest."""
    _append(
        ledger,
        action_type="approval",
        decision="approved",
        actor_id=BYPASS_IDENTITY,
        detail={"approvedBy": approval_class.stamp("human_individual")},
    )
    first = bypass.run_detections(ledger, bypass.BypassEvidence())
    assert len(first) == 1
    second = bypass.run_detections(ledger, bypass.BypassEvidence())
    assert len(second) == 1
    assert second[0].sequence == first[0].sequence  # same open entry, no dup
    assert len(_detection_rows(ledger)) == 1
    _assert_downgrade_visible(ledger, bypass.RULESET_BYPASS_ACTOR)


# -- AC-48: the acceptance scenario ------------------------------------------------


def test_ac48_ruleset_bypass_actor_and_removed_hook_self_reported(ledger: Ledger) -> None:
    """AC-48: a ruleset bypass actor is enabled AND the provenance hook is
    removed. Both are detected, both produce ledger entries, and Meridian
    downgrades its own coverage claim within one session."""
    _append(
        ledger,
        action_type="approval",
        decision="approved",
        actor_id=BYPASS_IDENTITY,
        detail={"approvedBy": approval_class.stamp("human_individual", "asserted")},
    )
    bypass.record_hook_state(ledger, installed=True, hook_path=".git/hooks/commit-msg")

    evidence = bypass.BypassEvidence(
        hook_status={"installed": False, "detail": "commit-msg hook not installed"}
    )
    detections = bypass.run_detections(ledger, evidence)
    found = {detection.circumvention: detection for detection in detections}
    assert set(found) == {
        bypass.RULESET_BYPASS_ACTOR,
        bypass.PROVENANCE_HOOK_REMOVED,
    }

    rows = _detection_rows(ledger)
    assert len(rows) == 2  # both produced their own durable entry
    assert all(row["decision"] == "detected" for row in rows)

    # The downgrade, same session: envelope gaps under both circumvention
    # ids and both weakened surfaces named.
    gaps = {gap.gapClass: gap for gap in bypass.bypass_gaps(ledger)}
    assert bypass.RULESET_BYPASS_ACTOR in gaps
    assert bypass.PROVENANCE_HOOK_REMOVED in gaps
    surfaces = bypass.downgraded_surfaces(ledger)
    assert surfaces["trust/approval-integrity"] == [bypass.RULESET_BYPASS_ACTOR]
    assert surfaces["provenance-trail"] == [bypass.PROVENANCE_HOOK_REMOVED]
