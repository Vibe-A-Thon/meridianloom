"""SDLC Phase Set provider — D8, banned pattern 24.

No hard-coded phase count, name or colour anywhere: every consumer of
the phase model reads it through :class:`PhaseSet`, which loads the set
from policy — the workspace override ``.meridian/policy/phases.yaml``
first, then the repository ``policy/phases.yaml``. The shipped default
is the nine phases of Requirements_Final.md §6 exactly (Intake and
Analysis … Operate and Maintain).

A missing or malformed pack is fail-closed: the provider reports its
errors and yields NO phases — a screen that would otherwise render
hard-coded placeholders instead renders the failure (banned pattern 24
is about the temptation to fall back to constants; there is no
fallback here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import yaml


@dataclass(frozen=True)
class Phase:
    """One SDLC phase from policy."""

    key: str  # stable id, e.g. "intake"
    name: str
    order: int


@dataclass
class PhaseSet:
    """The provider result. ``errors`` non-empty means fail-closed:
    consumers must not invent phases."""

    source: str
    phases: tuple[Phase, ...] = ()
    errors: list[str] = field(default_factory=list)

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    @property
    def ordered(self) -> tuple[Phase, ...]:
        return tuple(sorted(self.phases, key=lambda p: (p.order, p.key)))

    def keys(self) -> tuple[str, ...]:
        return tuple(p.key for p in self.ordered)


def load_phase_set(paths: Sequence[Path]) -> PhaseSet:
    """First readable pack wins (workspace override, then repository —
    the same convention as the other policy packs)."""
    for path in paths:
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            return PhaseSet(source=str(path), errors=[f"phases pack is not YAML: {exc}"])
        if not isinstance(raw, dict) or not isinstance(raw.get("phases"), list):
            return PhaseSet(
                source=str(path),
                errors=["phases pack must map 'phases' to a list"],
            )
        phases: list[Phase] = []
        errors: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(raw["phases"]):
            if not isinstance(item, dict) or not item.get("key") or not item.get("name"):
                errors.append(f"phase at index {index} needs key and name")
                continue
            key = str(item["key"])
            if key in seen:
                errors.append(f"duplicate phase key {key!r}")
                continue
            seen.add(key)
            phases.append(
                Phase(key=key, name=str(item["name"]), order=int(item.get("order", index)))
            )
        if errors:
            return PhaseSet(source=str(path), errors=errors)
        return PhaseSet(source=str(path), phases=tuple(phases))
    return PhaseSet(
        source="(no phases pack found)",
        errors=["no readable phases pack on any configured path"],
    )


def default_phase_rows() -> list[dict[str, Any]]:
    """The §6 default, as data — used by the SHIPPED policy/phases.yaml
    and by tests. The runtime never consults this; policy does."""
    names = (
        ("intake", "Intake and Analysis"),
        ("design", "Architecture and Design"),
        ("plan", "Planning and Decomposition"),
        ("build", "Implementation"),
        ("verify", "Verification"),
        ("security", "Security and Compliance"),
        ("review", "Review and Integration"),
        ("release", "Release"),
        ("operate", "Operate and Maintain"),
    )
    return [
        {"key": key, "name": name, "order": index}
        for index, (key, name) in enumerate(names)
    ]
