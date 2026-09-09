"""The Deterministic Engine (M33) — Python-first dispatch, zero model calls.

Slice 1 of the M33 workstream (Phase F3 Orchestra): the engine skeleton —
the action-class catalogue loader (FR-M33-01, policy/action-classes.yaml),
the capability protocol/registry seam (slice 2 fills it with the FR-M33-02
capability set), deterministic-first dispatch (FR-M33-03, enforcing the
FR-M8-15 boundary) and the declarative learned/rules loader (FR-M33-06,
SEC-26).
"""

from .capabilities import Capability, CapabilityOutcome, CapabilityRegistry
from .catalogue import ActionClass, Catalogue, load_catalogue, parse_catalogue
from .dispatch import DispatchOutcome, Dispatcher
from .rules import Rule, RuleSet, load_rules, parse_rule_document

__all__ = [
    "ActionClass",
    "Capability",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "Catalogue",
    "DispatchOutcome",
    "Dispatcher",
    "Rule",
    "RuleSet",
    "load_catalogue",
    "load_rules",
    "parse_catalogue",
    "parse_rule_document",
]
