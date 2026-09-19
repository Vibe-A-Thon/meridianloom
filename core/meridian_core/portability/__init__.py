"""M16 portability — FR-M16-01…06, 09 (C3).

Export produces THE ADAPTER FOLDER as a portable signed package (v2.1:
the package is the folder, including all of ``learned/``): manifest,
skills, instructions, learned state, tests — plus a signed agent card.
Export excludes, by default and irreversibly, credentials, episodic
memory, ledger blobs and anything tagged untrusted or containing
detected secrets; a pre-export scan ENFORCES this and blocks the export
on detection (FR-M16-03 — the block is the feature, not a warning).

Import verifies the signature, presents a full diff of what will be
introduced, refuses when a required skill or tool is unavailable in the
importing workspace (FR-M16-06), and admits the agent to PROBATION — a
trained agent from another team is not trusted on arrival
(FR-M16-05). Skill-pack upgrade runs the bound agents' own ``tests/``
through the sandbox before the new version becomes active
(FR-M16-09).

Zero model calls.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from meridian_core.adapters import (
    AdapterFolder,
    AdapterRegistry,
    folder_digest,
    parse_manifest,
)
from meridian_core.ledger.redaction import redact_secrets
from meridian_core.tools.surface import SandboxConfig, run_in_sandbox

AGENT_CARD = "agent-card.json"
SIGNATURE_FILE = "signature.json"
CONTENT_MANIFEST = "content-manifest.json"
PACKAGE_SUFFIX = ".meridian-agent.zip"

#: Archive preflight budgets (GP-004): refused before any write.
MAX_MEMBERS = 500
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024

#: FR-M16-03: excluded from export, always.
EXCLUDED_DIRS = ("learned/episodic", ".git")
EXCLUDED_NAMES = ("credentials.json", ".env", "ledger.db")


class ExportBlockedError(ValueError):
    """FR-M16-03: the pre-export scan found secrets/untrusted content.
    The export does not proceed — there is no override flag."""


class ImportRefusedError(ValueError):
    """FR-M16-04/06: signature invalid, or required skills/tools missing."""


@dataclass(frozen=True)
class ExportResult:
    package: Path
    agent_card: Mapping[str, Any]
    scanned_files: int
    excluded: tuple[str, ...]


def _scan_file(path: Path, root: Path) -> str | None:
    """Returns a refusal reason, or None when clean."""
    rel = path.relative_to(root).as_posix()
    if rel in EXCLUDED_NAMES or any(rel.startswith(d + "/") for d in EXCLUDED_DIRS):
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None
    redacted = redact_secrets(text)
    if redacted != text:
        return f"FR-M16-03: detected secret material in {rel}"
    if "untrusted: true" in text or '"untrusted": true' in text:
        return f"FR-M16-03: untrusted-tagged content in {rel} cannot export"
    return None


def export_package(
    adapter_root: Path,
    destination: Path,
    *,
    signing_key: Ed25519PrivateKey,
    exclude_episodic: bool = True,
) -> ExportResult:
    """FR-M16-01/02/03: package the adapter folder; sign the agent card;
    block on secrets/untrusted content. The exclusion of excluded paths
    is recorded on the card — the exported artifact cannot smuggle them
    back in."""
    manifest = parse_manifest(
        (adapter_root / "adapter.yaml").read_text(encoding="utf-8"), str(adapter_root)
    )
    excluded: list[str] = []
    scanned = 0
    members: list[tuple[str, bytes]] = []
    for path in sorted(adapter_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(adapter_root).as_posix()
        if rel in EXCLUDED_NAMES or any(
            rel.startswith(d + "/") for d in EXCLUDED_DIRS
        ):
            excluded.append(rel)
            continue
        scanned += 1
        reason = _scan_file(path, adapter_root)
        if reason is not None:
            raise ExportBlockedError(reason)
        members.append((rel, path.read_bytes()))

    card = {
        "agentCard": {
            "id": manifest.adapter_id,
            "version": manifest.version,
            "role": manifest.role,
            "capabilities": sorted(manifest.action_classes),
            "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "contentDigest": folder_digest(adapter_root),
        },
        "excluded": excluded,
        "format": "meridian-agent/1",
    }
    # GP-003: the signature must authenticate the CONTENTS, not only the
    # card. A content manifest covers every member's path, byte length
    # and digest, and the card commits to the manifest's digest — a
    # substituted agent.py, an added member, or a removed digest fails
    # verification before anything reaches the filesystem.
    content_manifest = {
        "version": 1,
        "members": [
            {
                "path": rel,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for rel, data in members
        ],
    }
    manifest_bytes = json.dumps(
        content_manifest, indent=2, sort_keys=True
    ).encode("utf-8")
    card_signed = {
        "agentCard": card["agentCard"],
        "excluded": card["excluded"],
        "format": card["format"],
        "contentManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    card_bytes = json.dumps(card_signed, indent=2, sort_keys=True).encode("utf-8")
    signature = signing_key.sign(card_bytes)
    public_key = signing_key.public_key().public_bytes_raw()

    destination.mkdir(parents=True, exist_ok=True)
    package = destination / f"{manifest.adapter_id}-{manifest.version}{PACKAGE_SUFFIX}"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as bundle:
        for rel, data in members:
            bundle.writestr(rel, data)
        bundle.writestr(CONTENT_MANIFEST, manifest_bytes)
        bundle.writestr(AGENT_CARD, card_bytes)
        bundle.writestr(
            SIGNATURE_FILE,
            json.dumps(
                {"signature": signature.hex(), "publicKey": public_key.hex()},
                indent=2,
            ),
        )
    return ExportResult(
        package=package,
        agent_card=card["agentCard"],
        scanned_files=scanned,
        excluded=tuple(excluded),
    )


def signer_fingerprint(public_key_hex: str) -> str:
    import hashlib

    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


def trust_signer(ledger: Any, *, fingerprint: str, human_approved: bool) -> None:
    """TASK-330: record an explicit, human-approved trust decision for an
    external signer fingerprint. The record is an ordinary ledger entry —
    auditable, hash-chained, reversible only by a later distrust entry."""
    if not human_approved:
        raise ImportRefusedError(
            "signer trust requires explicit human approval; it is never"
            " self-granted"
        )
    ledger.append(
        {
            "story_id": "portability-trust",
            "phase": "govern",
            "loop_id": "portability",
            "loop_iteration": 1,
            "actor_id": "operator",
            "actor_version": "local",
            "actor_kind": "meta",
            "policy_version": "portability/v1",
            "action_type": "policy_update",
            "tool_calls": [
                {"event": "signer_trusted", "fingerprint": fingerprint}
            ],
        }
    )


def trusted_signers(ledger: Any) -> set[str]:
    """The trusted fingerprint set: latest event per fingerprint wins, so
    a distrust entry (event=signer_distrusted) revokes."""
    state: dict[str, bool] = {}
    for row in ledger.query(action_type="policy_update", limit=100_000):
        raw = row.get("tool_calls")
        if not raw:
            continue
        try:
            calls = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for call in calls:
            event = call.get("event")
            if event == "signer_trusted":
                state[call["fingerprint"]] = True
            elif event == "signer_distrusted":
                state[call["fingerprint"]] = False
    return {fp for fp, trusted in state.items() if trusted}


def inspect_package(package: Path) -> Mapping[str, Any]:
    """FR-M16-04: what the package contains — for the import diff."""
    with zipfile.ZipFile(package) as bundle:
        card = json.loads(bundle.read(AGENT_CARD).decode("utf-8"))
        names = sorted(n for n in bundle.namelist() if n not in (AGENT_CARD, SIGNATURE_FILE))
    return {"card": card["agentCard"], "files": names, "excluded": card.get("excluded", [])}


def package_signature(package: Path) -> tuple[bytes, str]:
    """The signed card bytes and the signer public key (hex)."""
    with zipfile.ZipFile(package) as bundle:
        card_bytes = bundle.read(AGENT_CARD)
        sig_raw = json.loads(bundle.read(SIGNATURE_FILE).decode("utf-8"))
    return card_bytes, str(sig_raw["publicKey"])


def verify_package(package: Path, *, trusted_key: Ed25519PublicKey) -> Mapping[str, Any]:
    """FR-M16-04: signature verification — the FIRST thing import does.
    An unverifiable package never reaches the filesystem."""
    card_bytes, _ = package_signature(package)
    trusted_key.verify(
        bytes.fromhex(
            json.loads(
                zipfile.ZipFile(package).read(SIGNATURE_FILE).decode("utf-8")
            )["signature"]
        ),
        card_bytes,
    )
    return json.loads(card_bytes.decode("utf-8"))


def _authenticate_members(package: Path, card: Mapping[str, Any]) -> None:
    """GP-003/004 preflight, shared by the trust path and direct imports:
    budgets, canonical containment, and authentication of EVERY member
    against the signed content manifest. Raises before any write."""
    with zipfile.ZipFile(package) as bundle:
        names = bundle.namelist()
        if len(names) > MAX_MEMBERS:
            raise ImportRefusedError(
                f"archive has {len(names)} members; the budget is {MAX_MEMBERS}"
            )
        total = 0
        records: dict[str, tuple[int, str]] = {}
        for info in bundle.infolist():
            if info.file_size > MAX_MEMBER_BYTES:
                raise ImportRefusedError(
                    f"member {info.filename!r} exceeds the"
                    f" {MAX_MEMBER_BYTES}-byte budget"
                )
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ImportRefusedError("archive exceeds the total size budget")
            if info.filename.startswith("/") or "\\" in info.filename:
                raise ImportRefusedError(
                    f"absolute or UNC member path: {info.filename!r}"
                )
            anchor = Path("anchor-root").resolve()
            resolved = (anchor / info.filename).resolve()
            try:
                resolved.relative_to(anchor)
            except ValueError:
                raise ImportRefusedError(
                    f"traversing member path: {info.filename!r}"
                )
            records[info.filename] = (
                info.file_size,
                hashlib.sha256(bundle.read(info.filename)).hexdigest(),
            )
        if CONTENT_MANIFEST not in records:
            raise ImportRefusedError("package has no content manifest")
        declared = json.loads(bundle.read(CONTENT_MANIFEST).decode("utf-8"))
        expected = {
            str(m["path"]): (int(m["bytes"]), str(m["sha256"]))
            for m in declared.get("members", [])
        }
        actual_members = {
            k: v
            for k, v in records.items()
            if k not in (CONTENT_MANIFEST, AGENT_CARD, SIGNATURE_FILE)
        }
        if set(expected) != set(actual_members):
            raise ImportRefusedError(
                "package members do not match the signed content manifest"
                f" (added or removed:"
                f" {sorted(set(actual_members) ^ set(expected))})"
            )
        for name, observed in actual_members.items():
            if expected[name] != observed:
                raise ImportRefusedError(
                    f"member {name!r} does not match the signed manifest —"
                    " the package contents were tampered with"
                )
        if card.get("contentManifestSha256") != hashlib.sha256(
            bundle.read(CONTENT_MANIFEST)
        ).hexdigest():
            raise ImportRefusedError("card does not commit to the content manifest")


def verify_package_trust(
    package: Path, *, trusted_fingerprints: set[str]
) -> Mapping[str, Any]:
    """TASK-330 + GP-003/004: verify the package against its own embedded
    key, require an explicitly trusted signer fingerprint, authenticate
    EVERY member against the signed content manifest, and preflight the
    whole archive (paths, budgets) BEFORE any byte reaches the filesystem.
    Nothing is written until everything verifies."""
    card_bytes, public_key_hex = package_signature(package)
    if signer_fingerprint(public_key_hex) not in trusted_fingerprints:
        raise ImportRefusedError(
            "package signed by an untrusted fingerprint; record trust with"
            " an explicit human approval first (portability/trust)"
        )
    card = verify_package(
        package,
        trusted_key=Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)),
    )
    _authenticate_members(package, card)
    return card


def diff_against_workspace(
    package: Path, destination_root: Path
) -> Mapping[str, Any]:
    """FR-M16-04: the full diff of what import will introduce."""
    incoming = inspect_package(package)
    existing: dict[str, str] = {}
    target = destination_root / incoming["card"]["id"]
    if target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.is_file():
                existing[path.relative_to(target).as_posix()] = str(
                    hash(path.read_bytes())
                )
    proposed = set(incoming["files"])
    present = set(existing)
    return {
        "adapterId": incoming["card"]["id"],
        "added": sorted(proposed - present),
        "overwritten": sorted(proposed & present),
        "unchangedOnDisk": sorted(present - proposed),
    }


def import_package(
    package: Path,
    destination_root: Path,
    *,
    trusted_key: Ed25519PublicKey,
    available_tools: frozenset[str],
    registry: AdapterRegistry,
    confirm: bool,
) -> AdapterFolder:
    """FR-M16-04/05/06: verify, (caller shows the diff and sets
    ``confirm=True``), refuse on missing tools, extract, admit to
    PROBATION."""
    card = verify_package(package, trusted_key=trusted_key)
    _authenticate_members(package, card)
    if not confirm:
        raise ImportRefusedError(
            "FR-M16-04: import requires explicit confirmation after the"
            " diff is presented"
        )
    with zipfile.ZipFile(package) as bundle:
        manifest_raw = yaml.safe_load(bundle.read("adapter.yaml").decode("utf-8"))
        declared = set(manifest_raw.get("permittedTools") or ())
    missing = declared - set(available_tools)
    if missing:
        raise ImportRefusedError(
            f"FR-M16-06: importing workspace lacks required tools:"
            f" {sorted(missing)}"
        )
    target = destination_root / card["agentCard"]["id"]
    # GP-004: stage outside the active adapter directory and publish only
    # after validation admits the adapter — a failed or adversarial import
    # leaves the destination AND its siblings unchanged.
    import shutil
    import tempfile

    destination_root.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix="meridian-import-", dir=str(destination_root))
    )
    try:
        with zipfile.ZipFile(package) as bundle:
            for name in bundle.namelist():
                if name in (AGENT_CARD, SIGNATURE_FILE, CONTENT_MANIFEST):
                    continue
                dest = (staged / name).resolve()
                try:
                    dest.relative_to(staged.resolve())
                except ValueError:
                    raise ImportRefusedError(f"unsafe path in package: {name}")
                if name.endswith("/"):
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(bundle.read(name))
        adapter = registry.plug(staged)
        if not adapter.valid:
            raise ImportRefusedError(
                f"staged adapter failed validation: {list(adapter.errors)}"
            )
        if target.exists():
            backup = target.with_name(target.name + ".preimport-backup")
            shutil.move(str(target), str(backup))
            try:
                shutil.move(str(staged), str(target))
            except Exception:
                shutil.move(str(backup), str(target))
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(staged), str(target))
        return registry.plug(target)
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def run_upgrade_regression(
    adapter_root: Path,
    *,
    sandbox: SandboxConfig,
    tool_name: str = "python",
) -> Mapping[str, Any]:
    """FR-M16-09: a skill-pack upgrade runs the bound agent's own
    ``tests/`` in the sandbox BEFORE the new version becomes active.
    The result is the admission ticket; a failing run keeps the old
    version."""
    tests = adapter_root / "tests"
    if not tests.is_dir() or not any(tests.rglob("test_*.py")):
        return {"ran": False, "reason": "no tests/ in the adapter folder"}
    result = run_in_sandbox(
        [tool_name, "-m", "pytest", str(tests), "-q"],
        sandbox,
    )
    return {
        "ran": True,
        "ok": result.ok,
        "output_tail": result.output[-400:],
        "truncated": result.truncated,
    }
