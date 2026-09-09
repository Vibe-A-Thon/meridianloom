"""The Deterministic Engine (M33) — Python-first dispatch, zero model calls.

Slice 1 of the M33 workstream (Phase F3 Orchestra): the engine skeleton —
the action-class catalogue loader (FR-M33-01, policy/action-classes.yaml),
the capability protocol/registry seam (slice 2 fills it with the FR-M33-02
capability set), deterministic-first dispatch (FR-M33-03, enforcing the
FR-M8-15 boundary) and the declarative learned/rules loader (FR-M33-06,
SEC-26).

Slice 2a adds the structural half of the FR-M33-02 capability set:
tree-sitter structural edits (``structural_parse``), the LSP symbol
bridge (``symbol_resolution``), unified diff/patch (``diff_patch``) and
hunk-only large-file editing with generated-file exclusion
(``hunk_edit``) — see ``structural_capability_set``.
"""

from .capabilities import Capability, CapabilityOutcome, CapabilityRegistry
from .catalogue import ActionClass, Catalogue, load_catalogue, parse_catalogue
from .diffing import DiffPatchCapability
from .dispatch import DispatchOutcome, Dispatcher
from .hunks import HunkEditCapability
from .lsp_bridge import SymbolResolutionCapability
from .rules import Rule, RuleSet, load_rules, parse_rule_document
from .structural import StructuralParseCapability

__all__ = [
    "ActionClass",
    "Capability",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "Catalogue",
    "DiffPatchCapability",
    "DispatchOutcome",
    "Dispatcher",
    "HunkEditCapability",
    "Rule",
    "RuleSet",
    "StructuralParseCapability",
    "SymbolResolutionCapability",
    "load_catalogue",
    "load_rules",
    "parse_catalogue",
    "parse_rule_document",
    "structural_capability_set",
]


def structural_capability_set() -> list[Capability]:
    """The slice-2a structural capabilities of FR-M33-02, ready to register
    against the catalogue's deterministic classes: ``parse`` →
    ``structural_parse``, ``resolve_symbol`` → ``symbol_resolution``,
    ``apply_patch`` → ``diff_patch``, ``hunk_edit`` → ``hunk_edit``."""
    return [
        StructuralParseCapability(),
        SymbolResolutionCapability(),
        DiffPatchCapability(),
        HunkEditCapability(),
    ]
