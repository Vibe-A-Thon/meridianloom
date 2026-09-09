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

Slice 2b adds the analytical half: tool runners (``tool_runner``),
template scaffolding (``template_scaffold``), dependency/license/
migration classification (``migration_classifier``), import-graph blast
radius and packet decomposition (``graph_blast_radius`` /
``graph_decompose``), ledger-history cost estimation
(``ledger_cost_estimate``), coverage-to-criteria mapping
(``coverage_mapping``), rule-based ambiguity detection
(``rule_ambiguity``) and convention checks (``convention_rules``) — see
``analytical_capability_set``.
"""

from .ambiguity import RuleAmbiguityCapability
from .capabilities import Capability, CapabilityOutcome, CapabilityRegistry
from .catalogue import ActionClass, Catalogue, load_catalogue, parse_catalogue
from .conventions import ConventionRulesCapability
from .cost import LedgerCostEstimateCapability
from .coverage import CoverageMappingCapability
from .diffing import DiffPatchCapability
from .dispatch import DispatchOutcome, Dispatcher
from .graph import BlastRadiusCapability, PacketDecomposeCapability
from .hunks import HunkEditCapability
from .lsp_bridge import SymbolResolutionCapability
from .runners import ToolRunnerCapability
from .rules import Rule, RuleSet, load_rules, parse_rule_document
from .scaffold import TemplateScaffoldCapability
from .structural import StructuralParseCapability
from .classify import MigrationClassifierCapability

__all__ = [
    "ActionClass",
    "BlastRadiusCapability",
    "Capability",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "Catalogue",
    "ConventionRulesCapability",
    "CoverageMappingCapability",
    "DiffPatchCapability",
    "DispatchOutcome",
    "Dispatcher",
    "HunkEditCapability",
    "LedgerCostEstimateCapability",
    "MigrationClassifierCapability",
    "PacketDecomposeCapability",
    "Rule",
    "RuleAmbiguityCapability",
    "RuleSet",
    "StructuralParseCapability",
    "SymbolResolutionCapability",
    "TemplateScaffoldCapability",
    "ToolRunnerCapability",
    "analytical_capability_set",
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


def analytical_capability_set() -> list[Capability]:
    """The slice-2b analytical capabilities of FR-M33-02, ready to register
    against the catalogue's deterministic classes (run_tests →
    ``tool_runner``, scaffold → ``template_scaffold``, classify_migration →
    ``migration_classifier``, blast_radius → ``graph_blast_radius``,
    decompose_packets → ``graph_decompose``, estimate_cost →
    ``ledger_cost_estimate``, map_coverage → ``coverage_mapping``) and the
    assisted classes' deterministic-first phases (detect_ambiguity →
    ``rule_ambiguity``, name_tests → ``convention_rules``)."""
    return [
        ToolRunnerCapability(),
        TemplateScaffoldCapability(),
        MigrationClassifierCapability(),
        BlastRadiusCapability(),
        PacketDecomposeCapability(),
        LedgerCostEstimateCapability(),
        CoverageMappingCapability(),
        RuleAmbiguityCapability(),
        ConventionRulesCapability(),
    ]
