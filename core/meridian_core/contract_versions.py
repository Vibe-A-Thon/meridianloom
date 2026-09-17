"""FR-M44-06/07, NFR-40 (N2 Workstream E task 24): the external contract
version is recorded on every derived ledger entry.

Meridian derives evidence from contracts it does not control — observer
fallback chains, other tools' git-note conventions, wire protocols. When
one of those moves, the ledger entry must say which version of the
contract produced it, so a later reader can weigh the evidence and a
rename degrades coverage *visibly* instead of silently mapping old shapes
onto new data.

``shared/schema/external-contracts.json`` is the pin manifest; the code↔pin
lock is held by ``core/tests/test_contract_drift.py``. This module resolves
a source (observer vendor, interop tool) to the pinned version, and — the
part that makes NFR-40 real — returns ``None`` for anything unpinned so the
caller must record the degradation explicitly. ``None`` is never silently
turned into a version.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import meridian_core

MANIFEST_RELATIVE = Path("shared") / "schema" / "external-contracts.json"

UNPINNED = "unpinned"


class UnpinnedContractError(ValueError):
    """A derived entry was about to be written with no contract version
    and the caller did not explicitly accept the degradation (NFR-40)."""


def manifest_path() -> Path:
    return Path(meridian_core.__file__).resolve().parents[2] / MANIFEST_RELATIVE


@lru_cache(maxsize=4)
def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path is not None else manifest_path()
    return json.loads(source.read_text(encoding="utf-8"))


def observer_adapter_version(vendor: str, manifest: dict[str, Any] | None = None) -> str | None:
    """The pinned adapter version for an observer vendor, or None when the
    vendor is not pinned (never invented)."""
    manifest = manifest if manifest is not None else load_manifest()
    for observer in manifest.get("observers", []):
        if observer.get("id") == vendor and observer.get("adapterVersion"):
            return f"observer-adapter/{observer['adapterVersion']}"
    return None


def contract_version(contract_id: str, manifest: dict[str, Any] | None = None) -> str | None:
    """The pinned version of a named external contract, or None."""
    manifest = manifest if manifest is not None else load_manifest()
    for contract in manifest.get("contracts", []):
        if contract.get("id") == contract_id and contract.get("pinnedVersion"):
            return f"contract/{contract_id}/{contract['pinnedVersion']}"
    return None


def resolve_source_version(source_id: str, manifest: dict[str, Any] | None = None) -> str | None:
    """Resolve any derived-evidence source to its pinned version.

    Observer vendors resolve through the observers section; anything else
    may resolve through the contracts section. Unrecognised sources return
    None — the caller records :data:`UNPINNED` and surfaces the gap.
    """
    manifest = manifest if manifest is not None else load_manifest()
    return observer_adapter_version(source_id, manifest) or contract_version(
        source_id, manifest
    )


def stamp_external_contract(
    detail: dict[str, Any], source_id: str, manifest: dict[str, Any] | None = None
) -> tuple[dict[str, Any], str]:
    """Return ``(detail, version)`` with the contract version recorded.

    The version string lands in the entry detail under the stable key
    ``externalContractVersion`` — it rides the encrypted blob, the chain
    hash and every exported bundle. An unpinned source is recorded as
    ``"unpinned"`` (visible degradation, NFR-40), never as a fabricated
    version and never omitted.
    """
    version = resolve_source_version(source_id, manifest)
    stamped = dict(detail)
    stamped["externalContractVersion"] = version if version is not None else UNPINNED
    return stamped, stamped["externalContractVersion"]
