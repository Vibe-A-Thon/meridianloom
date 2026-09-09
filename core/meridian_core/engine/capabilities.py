"""Capability protocol and registry seam (FR-M33-02/FR-M33-03).

A *capability* is one deterministic, model-free unit of work the engine can
execute: tree-sitter structural edits, LSP symbol resolution, tool runners,
template scaffolding, graph queries, ledger-history estimation, convention
checks from ``learned/rules/`` — the full FR-M33-02 set lands in slice 2 of
the M33 workstream and registers itself here. Slice 1 defines only the seam:
the ``Capability`` protocol dispatch executes against and the
``CapabilityRegistry`` that maps action class → capability.

The registry consults the action-class catalogue (FR-M33-01) on every
registration and resolution: a capability may only serve a class the
catalogue declares deterministic (or names as an assisted class's
``deterministicFirst``), and the catalogue always has the final word on the
mode. A registration against an unknown class is refused and recorded.

Zero model calls: capabilities are plain Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .catalogue import Catalogue

__all__ = ["Capability", "CapabilityOutcome", "CapabilityRegistry"]


@dataclass(frozen=True)
class CapabilityOutcome:
    """What a capability run produced.

    ``handled`` False means the capability inspected the action and declares
    ``no_deterministic_path`` *for this instance* (e.g. the dependency graph
    is cyclic and ``decompose_packets`` cannot partition it). Dispatch then
    applies the catalogue's escalation condition before anything can reach
    the router (FR-M33-03).
    """

    handled: bool
    result: Any = None
    reason: str = ""


@runtime_checkable
class Capability(Protocol):
    """The seam slice 2 fills with the FR-M33-02 capability set.

    ``name`` matches the ``capability`` / ``deterministicFirst`` value in
    ``policy/action-classes.yaml``. ``run`` executes deterministically and
    without any model call; it must be replay-identical for identical
    inputs (FR-M33-08).
    """

    @property
    def name(self) -> str: ...

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome: ...


@dataclass
class CapabilityRegistry:
    """Maps action class → capability, catalogue-checked.

    ``refusals`` records every registration that was refused, with the
    reason — an unknown class, a class the catalogue does not let this
    capability serve, or a fail-closed catalogue (deny-logging posture,
    SEC-14-style: denials are recorded, never silent).
    """

    catalogue: Catalogue
    _by_class: dict[str, Capability] = field(default_factory=dict)
    refusals: list[str] = field(default_factory=list)

    def register(self, action_class: str, capability: Capability) -> bool:
        """Bind ``capability`` to ``action_class``. Refused (and recorded)
        when the catalogue does not declare the class executable by a
        capability of this name."""
        entry = self.catalogue.lookup(action_class)
        if entry is None:
            self.refusals.append(
                f"{action_class}: unknown action class — registration refused"
            )
            return False
        allowed = (entry.capability, entry.deterministic_first)
        if capability.name not in allowed or (entry.mode == "generative"):
            self.refusals.append(
                f"{action_class}: catalogue mode '{entry.mode}' does not permit "
                f"capability '{capability.name}' — registration refused"
            )
            return False
        self._by_class[action_class] = capability
        return True

    def resolve(self, action_class: str) -> Capability | None:
        """The capability bound to ``action_class``, or None. Consults the
        catalogue first: a fail-closed catalogue refuses everything."""
        if self.catalogue.lookup(action_class) is None:
            return None
        return self._by_class.get(action_class)

    def resolve_first(self, action_class: str) -> Capability | None:
        """The ``deterministicFirst`` capability for an assisted class, or
        None when unregistered — the gap is then declared with whatever the
        deterministic phase could not do itself."""
        entry = self.catalogue.lookup(action_class)
        if entry is None or not entry.deterministic_first:
            return None
        return self._by_class.get(action_class)

    @classmethod
    def from_catalogue(
        cls, catalogue: Catalogue, bindings: Sequence[tuple[str, Capability]] = ()
    ) -> "CapabilityRegistry":
        registry = cls(catalogue=catalogue)
        for action_class, capability in bindings:
            registry.register(action_class, capability)
        return registry
