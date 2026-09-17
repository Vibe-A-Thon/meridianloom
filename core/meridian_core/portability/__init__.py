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
PACKAGE_SUFFIX = ".meridian-agent.zip"

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
    card_bytes = json.dumps(card, indent=2, sort_keys=True).encode("utf-8")
    signature = signing_key.sign(card_bytes)
    public_key = signing_key.public_key().public_bytes_raw()

    destination.mkdir(parents=True, exist_ok=True)
    package = destination / f"{manifest.adapter_id}-{manifest.version}{PACKAGE_SUFFIX}"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as bundle:
        for rel, data in members:
            bundle.writestr(rel, data)
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


def inspect_package(package: Path) -> Mapping[str, Any]:
    """FR-M16-04: what the package contains — for the import diff."""
    with zipfile.ZipFile(package) as bundle:
        card = json.loads(bundle.read(AGENT_CARD).decode("utf-8"))
        names = sorted(n for n in bundle.namelist() if n not in (AGENT_CARD, SIGNATURE_FILE))
    return {"card": card["agentCard"], "files": names, "excluded": card.get("excluded", [])}


def verify_package(package: Path, *, trusted_key: Ed25519PublicKey) -> Mapping[str, Any]:
    """FR-M16-04: signature verification — the FIRST thing import does.
    An unverifiable package never reaches the filesystem."""
    with zipfile.ZipFile(package) as bundle:
        card_bytes = bundle.read(AGENT_CARD)
        sig_raw = json.loads(bundle.read(SIGNATURE_FILE).decode("utf-8"))
    trusted_key.verify(bytes.fromhex(sig_raw["signature"]), card_bytes)
    return json.loads(card_bytes.decode("utf-8"))


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
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as bundle:
        for name in bundle.namelist():
            if name in (AGENT_CARD, SIGNATURE_FILE):
                continue
            member = bundle.getinfo(name)
            # Zip-slip guard: members must land inside the target.
            dest = (target / name).resolve()
            if not str(dest).startswith(str(target.resolve())):
                raise ImportRefusedError(f"unsafe path in package: {name}")
            if name.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(bundle.read(name))
    adapter = registry.plug(target)
    return adapter


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
