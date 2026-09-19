"""FR-M16-01…06, 09 (C3): portable adapter packages — signed export with
a blocking pre-export secret scan, signature-verified import with diff
and explicit confirmation, missing-tool refusal, probation admission,
and sandboxed upgrade regression before a new version activates.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from meridian_core.adapters import AdapterRegistry
from meridian_core.adapters.roster import materialize_roster
from meridian_core.portability import (
    ExportBlockedError,
    ImportRefusedError,
    diff_against_workspace,
    export_package,
    import_package,
    inspect_package,
    run_upgrade_regression,
    verify_package,
)
from meridian_core.tools.surface import SandboxConfig

ALLOWLIST = frozenset({"repo_read", "build", "test", "apply_patch", "static_analysis", "scan"})


@pytest.fixture()
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture()
def roster_dir(tmp_path) -> Path:
    return Path(materialize_roster(tmp_path / "adapters")[0]).parent


def test_export_produces_signed_package_with_card(roster_dir, key, tmp_path) -> None:
    result = export_package(
        roster_dir / "developer", tmp_path / "out", signing_key=key
    )
    assert result.package.exists()
    assert result.agent_card["id"] == "developer"
    assert result.agent_card["version"] == "1.0.0"
    card = verify_package(result.package, trusted_key=key.public_key())
    assert card["agentCard"]["role"] == "developer"


def test_export_blocks_on_detected_secret(roster_dir, key, tmp_path) -> None:
    poisoned = roster_dir / "developer"
    (poisoned / "learned" / "leak.txt").write_text(
        "api_key = z9y8x7w6v5u4t3s2r1q0", encoding="utf-8"
    )
    with pytest.raises(ExportBlockedError, match="FR-M16-03"):
        export_package(poisoned, tmp_path / "out", signing_key=key)
    # The blocked export leaves no package behind.
    assert not list((tmp_path / "out").glob("*.zip"))


def test_export_blocks_on_untrusted_tagged_content(roster_dir, key, tmp_path) -> None:
    poisoned = roster_dir / "qa-engineer"
    (poisoned / "learned" / "story-claim.json").write_text(
        '{"untrusted": true, "claim": "from a story"}', encoding="utf-8"
    )
    with pytest.raises(ExportBlockedError, match="untrusted"):
        export_package(poisoned, tmp_path / "out", signing_key=key)


def test_export_records_exclusions_on_card(roster_dir, key, tmp_path) -> None:
    (roster_dir / "reviewer" / ".env").write_text("TOKEN=x", encoding="utf-8")
    result = export_package(roster_dir / "reviewer", tmp_path / "out", signing_key=key)
    assert ".env" in result.excluded
    with zipfile.ZipFile(result.package) as bundle:
        assert ".env" not in bundle.namelist()


def test_import_requires_valid_signature(roster_dir, key, tmp_path) -> None:
    result = export_package(roster_dir / "developer", tmp_path / "out", signing_key=key)
    stranger = Ed25519PrivateKey.generate()
    with pytest.raises(Exception):  # InvalidSignature
        verify_package(result.package, trusted_key=stranger.public_key())


def test_import_refused_without_confirmation(roster_dir, key, tmp_path) -> None:
    result = export_package(roster_dir / "developer", tmp_path / "out", signing_key=key)
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    with pytest.raises(ImportRefusedError, match="confirmation"):
        import_package(
            result.package, tmp_path / "imported",
            trusted_key=key.public_key(),
            available_tools=ALLOWLIST,
            registry=registry,
            confirm=False,
        )


def test_import_refused_when_tools_missing(roster_dir, key, tmp_path) -> None:
    result = export_package(roster_dir / "developer", tmp_path / "out", signing_key=key)
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    with pytest.raises(ImportRefusedError, match="FR-M16-06"):
        import_package(
            result.package, tmp_path / "imported",
            trusted_key=key.public_key(),
            available_tools=frozenset({"repo_read"}),
            registry=registry,
            confirm=True,
        )


def test_import_full_round_trip_into_probation(roster_dir, key, tmp_path) -> None:
    """FR-M16-04/05: verify → diff → confirm → extract → probation."""
    result = export_package(roster_dir / "developer", tmp_path / "out", signing_key=key)
    diff = diff_against_workspace(result.package, tmp_path / "imported")
    assert diff["adapterId"] == "developer"
    assert "adapter.yaml" in diff["added"]
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    adapter = import_package(
        result.package, tmp_path / "imported",
        trusted_key=key.public_key(),
        available_tools=ALLOWLIST,
        registry=registry,
        confirm=True,
    )
    assert adapter.valid is True
    assert adapter.manifest.adapter_id == "developer"
    assert registry.states["developer"] == "probation"  # not trusted on arrival
    assert (tmp_path / "imported" / "developer" / "agent.py").exists()


def test_diff_shows_overwrites_on_reimport(roster_dir, key, tmp_path) -> None:
    result = export_package(roster_dir / "developer", tmp_path / "out", signing_key=key)
    registry = AdapterRegistry(tool_allowlist=ALLOWLIST)
    import_package(
        result.package, tmp_path / "imported",
        trusted_key=key.public_key(), available_tools=ALLOWLIST,
        registry=registry, confirm=True,
    )
    diff = diff_against_workspace(result.package, tmp_path / "imported")
    assert set(diff["overwritten"]) == set(diff["added"]) or diff["overwritten"]


def test_upgrade_regression_runs_adapter_tests(roster_dir, tmp_path) -> None:
    """FR-M16-09: the upgrade admission ticket is the agent's own tests
    running in the sandbox."""
    sandbox = SandboxConfig(working_dir=tmp_path / "work", timeout_s=120)
    result = run_upgrade_regression(roster_dir / "developer", sandbox=sandbox)
    assert result["ran"] is True
    assert result["ok"] is True
    broken = roster_dir / "developer"
    (broken / "tests" / "test_smoke.py").write_text(
        "def test_fail():\n    assert False\n", encoding="utf-8"
    )
    failed = run_upgrade_regression(broken, sandbox=sandbox)
    assert failed["ok"] is False
