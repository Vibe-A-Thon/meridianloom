"""Per-field provenance records for every provenance answer (FR-M41-01,
FR-M41-02; N1 Workstream B T10).

Every provenance answer — ``attrib/blame``, ``attrib/symbol``, and every
classification that rides them — carries, PER FIELD, five facts:

* ``value`` — the field's content (the answer itself);
* ``source`` — where the fact came from (``git blame --porcelain``, the
  symbols engine, the heuristic classifier, ...);
* ``captureMethod`` — how it was captured (porcelain parse, tree-sitter
  walk, burst/timing heuristics, ...);
* ``contractVersion`` — the version of the contract that produced it
  (:data:`ATTRIBUTION_CONTRACT_VERSION`);
* ``capturedAt`` — the capture timestamp, ISO 8601 UTC;
* ``state`` — one of exactly four: ``observed`` (read directly from
  evidence), ``inferred`` (derived by a documented deterministic rule),
  ``unknown`` (no evidence exists), ``redacted`` (withheld by policy).

FR-M41-02's hard rule: **signing an artefact never promotes an
``inferred`` field to ``observed``.** The record is frozen; a signature
may cover the serialised record (see :func:`signed_form`) but the state
field is part of the signed bytes and cannot move without breaking the
signature — promotion is structurally impossible, not merely disciplined.

Zero model calls (FR-M36-07): a frozen dataclass and JSON encoding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .states import ATTRIBUTION_CONTRACT_VERSION, PROVENANCE_STATES

__all__ = ["ProvenanceField", "captured_now", "signed_form"]


def captured_now() -> str:
    """The capture timestamp, ISO 8601 UTC (microseconds, Z-suffixed)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class ProvenanceField:
    """One field of a provenance answer with its full evidence chain."""

    value: Any
    source: str
    capture_method: str
    contract_version: str
    captured_at: str
    state: str

    def __post_init__(self) -> None:
        if self.state not in PROVENANCE_STATES:
            raise ValueError(
                f"provenance state must be one of {PROVENANCE_STATES}, "
                f"got {self.state!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """The wire/JSON shape — camelCase, per the bus schema."""
        return {
            "value": self.value,
            "source": self.source,
            "captureMethod": self.capture_method,
            "contractVersion": self.contract_version,
            "capturedAt": self.captured_at,
            "state": self.state,
        }

    @classmethod
    def observed(
        cls,
        value: Any,
        *,
        source: str,
        capture_method: str,
        captured_at: str,
    ) -> "ProvenanceField":
        """A field read directly from observed evidence."""
        return cls(
            value=value,
            source=source,
            capture_method=capture_method,
            contract_version=ATTRIBUTION_CONTRACT_VERSION,
            captured_at=captured_at,
            state="observed",
        )

    @classmethod
    def inferred(
        cls,
        value: Any,
        *,
        source: str,
        capture_method: str,
        captured_at: str,
    ) -> "ProvenanceField":
        """A field derived by a documented deterministic rule. Signing the
        artefact never moves this to ``observed`` (FR-M41-02)."""
        return cls(
            value=value,
            source=source,
            capture_method=capture_method,
            contract_version=ATTRIBUTION_CONTRACT_VERSION,
            captured_at=captured_at,
            state="inferred",
        )

    @classmethod
    def unknown(
        cls,
        *,
        source: str,
        capture_method: str,
        captured_at: str,
    ) -> "ProvenanceField":
        """A field with no evidence — reported as unknown, never invented."""
        return cls(
            value=None,
            source=source,
            capture_method=capture_method,
            contract_version=ATTRIBUTION_CONTRACT_VERSION,
            captured_at=captured_at,
            state="unknown",
        )


def signed_form(record: dict[str, Any]) -> bytes:
    """The canonical serialisation a signature covers: the state string is
    inside these bytes, so signing cannot promote ``inferred`` to
    ``observed`` — any tamper with the state changes the signature
    (FR-M41-02)."""
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
