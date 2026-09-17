"""D8 PhaseSet provider + FR-M5 registry deltas (F3 remaining): policy-
loaded phases with no hard-coded constants anywhere, workspace override,
fail-closed malformed packs; agent states with only-active-takes-work,
immutable versions with ledger recording, retirement keeping history,
provenance on every agent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core.adapters import (
    AdapterRegistry,
    AgentRegistryM5,
    parse_manifest,
)
from meridian_core.adapters.roster import materialize_roster
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.phases import default_phase_rows, load_phase_set

ALLOWLIST = frozenset({"repo_read", "build", "test", "apply_patch"})


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


# -- D8: PhaseSet provider ----------------------------------------------------


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_default_nine_phases_load_from_policy() -> None:
    pack = repo_root() / "policy" / "phases.yaml"
    phase_set = load_phase_set([pack])
    assert phase_set.fail_closed is False
    assert phase_set.keys() == (
        "intake", "design", "plan", "build", "verify",
        "security", "review", "release", "operate",
    )
    names = [p.name for p in phase_set.ordered]
    assert names[0] == "Intake and Analysis"
    assert names[-1] == "Operate and Maintain"


def test_default_rows_match_requirements_section_6() -> None:
    """The shipped pack and the §6 document agree (the pack is generated
    from these rows; this test pins the document, not a copy of it)."""
    rows = default_phase_rows()
    assert [r["key"] for r in rows] == [
        "intake", "design", "plan", "build", "verify",
        "security", "review", "release", "operate",
    ]


def test_workspace_override_wins(tmp_path) -> None:
    override = tmp_path / ".meridian" / "policy" / "phases.yaml"
    override.parent.mkdir(parents=True)
    override.write_text(
        "version: 1\nphases:\n"
        "  - key: only\n    name: Solo Phase\n    order: 0\n",
        encoding="utf-8",
    )
    phase_set = load_phase_set([override, repo_root() / "policy" / "phases.yaml"])
    assert phase_set.keys() == ("only",)
    assert phase_set.source == str(override)


def test_malformed_pack_fails_closed_no_fallback(tmp_path) -> None:
    bad = tmp_path / "phases.yaml"
    bad.write_text("phases: notalist\n", encoding="utf-8")
    phase_set = load_phase_set([bad])
    assert phase_set.fail_closed is True
    assert phase_set.phases == ()  # no invented fallback (banned pattern 24)
    missing = load_phase_set([tmp_path / "absent.yaml"])
    assert missing.fail_closed is True


def test_duplicate_keys_fail_closed(tmp_path) -> None:
    bad = tmp_path / "phases.yaml"
    bad.write_text(
        "phases:\n  - key: a\n    name: A\n  - key: a\n    name: A2\n",
        encoding="utf-8",
    )
    assert load_phase_set([bad]).fail_closed is True


# -- FR-M5: registry deltas ------------------------------------------------------


@pytest.fixture()
def roster_dir(tmp_path) -> Path:
    return Path(materialize_roster(tmp_path / "adapters")[0]).parent


def test_only_active_agents_take_live_work(roster_dir) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir])
    # Freshly discovered = probation: no live work, accurate substate.
    assert m5.can_take_work("developer") is False
    assert "probation" in m5.learning_substate("developer")
    m5.promote("developer")
    assert m5.can_take_work("developer") is True
    m5.pause("developer")
    assert m5.can_take_work("developer") is False
    assert "paused" in m5.learning_substate("developer")


def test_promotion_requires_probation(roster_dir) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir])
    m5.promote("developer")
    with pytest.raises(Exception, match="FR-M5-05"):
        m5.promote("developer")


def test_versions_immutable_old_kept_on_upgrade(roster_dir, tmp_path) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir])
    # Admit through the M5 view so versions are tracked from the start.
    m5.admit(registry.plug(roster_dir / "developer"))
    # Upgrade: bump the developer manifest version and re-admit.
    manifest_path = roster_dir / "developer" / "adapter.yaml"
    upgraded = manifest_path.read_text(encoding="utf-8").replace(
        'version: "1.0.0"', 'version: "1.1.0"'
    )
    manifest_path.write_text(upgraded, encoding="utf-8")
    m5.admit(registry.plug(roster_dir / "developer"))
    assert m5.versions("developer") == ("1.0.0", "1.1.0")


def test_admission_records_exact_version_in_ledger(roster_dir, ledger) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir], ledger=ledger)
    folder = registry.plug(roster_dir / "reviewer")
    m5.admit(folder)
    rows = ledger.query(action_type="policy_update", story_id="agent-registry")
    reviewer_rows = [
        r for r in rows if r["actor_id"] == "reviewer"
    ]
    assert reviewer_rows[0]["actor_version"] == "1.0.0"
    assert ledger.verify().ok is True


def test_retire_keeps_manifest_and_history(roster_dir) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir])
    m5.retire("developer")
    assert m5.can_take_work("developer") is False
    # FR-M5-06: manifest and adapters entry survive retirement.
    assert (roster_dir / "developer" / "adapter.yaml").exists()
    assert "developer" in registry.adapters
    assert "retired" in m5.learning_substate("developer")


def test_provenance_distinguishes_prebuilt_custom_bridged(roster_dir, tmp_path) -> None:
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    registry.load([roster_dir])
    # A bridged adapter (external agent wrapped) and a custom one.
    custom_root = tmp_path / "custom"
    (custom_root / "inhouse-dev").mkdir(parents=True)
    (custom_root / "inhouse-dev" / "adapter.yaml").write_text(
        "id: inhouse-dev\nversion: '1'\nrole: developer\n"
        "permittedTools: [repo_read]\n",
        encoding="utf-8",
    )
    bridged_root = tmp_path / "bridged"
    (bridged_root / "wrapped").mkdir(parents=True)
    (bridged_root / "wrapped" / "adapter.yaml").write_text(
        "id: wrapped\nversion: '1'\nrole: developer\n"
        "permittedTools: [repo_read]\nbridge: plain_python\n",
        encoding="utf-8",
    )
    registry.load([custom_root, bridged_root])
    m5 = AgentRegistryM5(registry, prebuilt_roots=[roster_dir])
    assert m5.provenance("developer") == "prebuilt"
    assert m5.provenance("inhouse-dev") == "custom"
    assert m5.provenance("wrapped") == "bridged"
