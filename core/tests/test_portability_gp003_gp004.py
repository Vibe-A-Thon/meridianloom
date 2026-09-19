"""GP-003/GP-004 adversarial regressions: the audit's reproductions must
fail before any write, leaving the destination and its siblings
unchanged."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from meridian_core.adapters import AdapterRegistry
from meridian_core.adapters.roster import materialize_roster
from meridian_core.portability import (
    AGENT_CARD,
    ImportRefusedError,
    export_package,
    import_package,
    package_signature,
    signer_fingerprint,
    verify_package_trust,
)

ALLOW = frozenset({"repo_read", "build", "test", "apply_patch"})


def make_package(tmp_path, key) -> Path:
    roster = Path(materialize_roster(tmp_path / "roster")[0]).parent
    result = export_package(roster / "developer", tmp_path / "out", signing_key=key)
    return result.package


def trusted(tmp_path, key) -> set[str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    _, pub_hex = package_signature(make_package(tmp_path, key))
    return {signer_fingerprint(pub_hex)}


def registry() -> AdapterRegistry:
    return AdapterRegistry(tool_allowlist=ALLOW)


def test_substituted_member_fails_before_write(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    package = make_package(tmp_path, key)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(package) as src:
        entries = {n: src.read(n) for n in src.namelist()}
    entries["agent.py"] = entries["agent.py"] + b"\n# EVIL\n"
    with zipfile.ZipFile(tampered, "w") as out:
        for name, data in entries.items():
            out.writestr(name, data)
    before = sorted(p.name for p in (tmp_path / "imported").rglob("*")) if (tmp_path / "imported").exists() else []
    with pytest.raises(ImportRefusedError, match="signed manifest"):
        import_package(
            tampered, tmp_path / "imported",
            trusted_key=key.public_key(), available_tools=ALLOW,
            registry=registry(), confirm=True,
        )
    after = sorted(p.name for p in (tmp_path / "imported").rglob("*")) if (tmp_path / "imported").exists() else []
    assert before == after  # nothing written


def test_added_member_fails_before_write(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    package = make_package(tmp_path, key)
    hostile = tmp_path / "added.zip"
    with zipfile.ZipFile(package) as src:
        entries = [(n, src.read(n)) for n in src.namelist()]
    entries.append(("evil.txt", b"added member"))
    with zipfile.ZipFile(hostile, "w") as out:
        for name, data in entries:
            out.writestr(name, data)
    with pytest.raises(ImportRefusedError, match="added or removed"):
        import_package(
            hostile, tmp_path / "imported",
            trusted_key=key.public_key(), available_tools=ALLOW,
            registry=registry(), confirm=True,
        )
    assert not (tmp_path / "imported" / "developer").exists()


def test_removed_manifest_entry_fails_before_write(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    package = make_package(tmp_path, key)
    hostile = tmp_path / "removed.zip"
    with zipfile.ZipFile(package) as src:
        entries = [(n, src.read(n)) for n in src.namelist() if n != "agent.py"]
    with zipfile.ZipFile(hostile, "w") as out:
        for name, data in entries:
            out.writestr(name, data)
    with pytest.raises(ImportRefusedError, match="added or removed"):
        import_package(
            hostile, tmp_path / "imported",
            trusted_key=key.public_key(), available_tools=ALLOW,
            registry=registry(), confirm=True,
        )


def test_traversal_archive_fails_and_sibling_unchanged(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    package = make_package(tmp_path, key)
    hostile = tmp_path / "hostile.zip"
    sibling_proof = tmp_path / "imported" / "developer-extra" / "audit-proof.txt"
    with zipfile.ZipFile(package) as src:
        entries = [(n, src.read(n)) for n in src.namelist()]
    entries.append(("../developer-extra/audit-proof.txt", b"pwned"))
    with zipfile.ZipFile(hostile, "w") as out:
        for name, data in entries:
            out.writestr(name, data)
    with pytest.raises(ImportRefusedError):
        import_package(
            hostile, tmp_path / "imported",
            trusted_key=key.public_key(), available_tools=ALLOW,
            registry=registry(), confirm=True,
        )
    assert not sibling_proof.exists()


def test_trust_path_authenticates_members(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    package = make_package(tmp_path, key)
    fps = trusted(tmp_path, key)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    verify_package_trust(package, trusted_fingerprints=fps)  # clean passes

    tampered = tmp_path / "tampered2.zip"
    with zipfile.ZipFile(package) as src:
        entries = {n: src.read(n) for n in src.namelist()}
    entries["skills/SKILL.md"] = b"substituted skill"
    with zipfile.ZipFile(tampered, "w") as out:
        for name, data in entries.items():
            out.writestr(name, data)
    with pytest.raises(ImportRefusedError, match="tampered"):
        verify_package_trust(tampered, trusted_fingerprints=fps)
