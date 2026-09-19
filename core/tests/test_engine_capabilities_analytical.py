"""Analytical capability set (FR-M33-02 slice 2b).

The nine analytical capabilities registered into the slice-1
``CapabilityRegistry`` seam and routed end-to-end by dispatch
(FR-M33-03):

* ``tool_runner``          — configured build/test/lint/scanner commands in
                             the sandbox, exit/stdout/stderr captured,
                             line-oriented failure summaries;
* ``template_scaffold``    — skill-pack template rendering with a declared
                             substitution syntax and path-escape refusal;
* ``migration_classifier`` — Gradle/npm/Python manifest parsing, SPDX
                             license lookup from the pinned policy map,
                             confidence-labelled migration-reversibility;
* ``graph_blast_radius``   — import-graph reachability with dependency
                             paths, from tree-sitter parses;
* ``graph_decompose``      — dependency-first work packets along graph
                             boundaries; cycles are no_deterministic_path;
* ``ledger_cost_estimate`` — median + spread from same-class ledger
                             history; unknown when there is no history;
* ``coverage_mapping``     — acceptance criteria → test evidence mapping,
                             evidenced/partial/uncovered + confidence;
* ``rule_ambiguity``       — fixed ambiguity rules over criterion text,
                             the assisted detect_ambiguity deterministic
                             first phase (FR-M33-04);
* ``convention_rules``     — naming/import/layering checks against
                             tree-sitter output, violations named
                             file:line, the assisted name_tests phase.

Zero model calls throughout (FR-M36-07) — the package scan is asserted
separately (tests/test_no_model_calls.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from meridian_core.engine import analytical_capability_set, load_catalogue
from meridian_core.engine.catalogue import repo_default_paths
from meridian_core.engine.ambiguity import RuleAmbiguityCapability
from meridian_core.engine.capabilities import CapabilityRegistry
from meridian_core.engine.classify import (
    MigrationClassifierCapability,
    parse_license_map,
)
from meridian_core.engine.conventions import ConventionRulesCapability
from meridian_core.engine.cost import LedgerCostEstimateCapability
from meridian_core.engine.coverage import CoverageMappingCapability
from meridian_core.engine.dispatch import WHY_ASSISTED_GAP, Dispatcher
from meridian_core.engine.graph import BlastRadiusCapability, PacketDecomposeCapability
from meridian_core.engine.rules import parse_rule_document
from meridian_core.engine.runners import ToolRunnerCapability
from meridian_core.engine.scaffold import TemplateScaffoldCapability

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "analytical"
GRADLE_DIR = FIXTURES / "gradle"
NPM_DIR = FIXTURES / "npm"
PYTHON_DIR = FIXTURES / "python"
SRC = FIXTURES / "src"
PY_SRC = SRC / "py"
TESTS_DIR = FIXTURES / "tests"
TEMPLATE = FIXTURES / "template" / "skill-pack"
ESCAPING_TEMPLATE = FIXTURES / "template" / "escaping"


def registry_with_analytical() -> CapabilityRegistry:
    catalogue = load_catalogue(repo_default_paths())
    assert not catalogue.fail_closed, catalogue.errors
    bindings = [
        (cls.id, cap)
        for cap in analytical_capability_set()
        for cls in catalogue.classes.values()
        if cls.capability == cap.name or cls.deterministic_first == cap.name
    ]
    registry = CapabilityRegistry.from_catalogue(catalogue, bindings)
    assert registry.refusals == []
    return registry


class TestToolRunner:
    """FR-M33-02 tool runners: configured commands, captured output,
    deterministic failure summaries."""

    def test_configured_command_runs_and_passes(self):
        runner = ToolRunnerCapability()
        config = {
            "cwd": str(PYTHON_DIR),
            "tools": {
                "echo_ok": {
                    "command": [sys.executable, "-c", "print('hello sandbox')"],
                    "timeout_seconds": 30,
                    "failure_patterns": ["^FAILED"],
                }
            },
        }
        outcome = runner.run({"tool": "echo_ok", "config": config})
        assert outcome.handled is True
        result = outcome.result
        assert result["passed"] is True
        assert result["exit_code"] == 0
        assert result["timed_out"] is False
        assert result["stdout_tail"] == ["hello sandbox"]
        assert result["failures"] == []

    def test_pytest_failure_summary_is_line_oriented(self):
        runner = ToolRunnerCapability()
        config = {
            "cwd": str(TESTS_DIR.parent),
            "tools": {
                "unit_tests": {
                    "command": [
                        sys.executable,
                        "-m",
                        "pytest",
                        str(TESTS_DIR / "test_failing.py"),
                        "-q",
                    ],
                    "timeout_seconds": 120,
                    "failure_patterns": ["FAILED", "AssertionError"],
                }
            },
        }
        outcome = runner.run({"tool": "unit_tests", "config": config})
        assert outcome.handled is True
        result = outcome.result
        assert result["passed"] is False
        assert result["exit_code"] != 0
        assert result["failures"], "expected parsed failure lines"
        for failure in result["failures"]:
            assert failure["line"] >= 1
            assert failure["pattern"] in ("FAILED", "AssertionError")
        assert any("test_that_fails" in f["text"] for f in result["failures"])

    def test_timeout_is_reported_not_raised(self):
        runner = ToolRunnerCapability()
        config = {
            "cwd": str(PYTHON_DIR),
            "tools": {
                "slow": {
                    "command": [sys.executable, "-c", "import time; time.sleep(30)"],
                    "timeout_seconds": 1,
                }
            },
        }
        outcome = runner.run({"tool": "slow", "config": config})
        assert outcome.handled is True
        assert outcome.result["timed_out"] is True
        assert outcome.result["passed"] is False
        assert outcome.result["exit_code"] is None

    def test_unconfigured_tool_is_refused_not_guessed(self):
        runner = ToolRunnerCapability()
        outcome = runner.run({"tool": "npm_test", "config": {"cwd": str(PYTHON_DIR), "tools": {}}})
        assert outcome.handled is False
        assert "never" in outcome.reason  # commands never come from the engine

    def test_invalid_failure_pattern_refused(self):
        runner = ToolRunnerCapability()
        config = {
            "cwd": str(PYTHON_DIR),
            "tools": {"x": {"command": [sys.executable, "-c", "pass"],
                            "timeout_seconds": 5, "failure_patterns": ["[unclosed"]}},
        }
        outcome = runner.run({"tool": "x", "config": config})
        assert outcome.handled is False
        assert "invalid failure pattern" in outcome.reason


class TestTemplateScaffold:
    """FR-M33-02 template scaffolding with declared substitution syntax."""

    def test_renders_template_with_declared_syntax(self, tmp_path):
        scaffold = TemplateScaffoldCapability()
        target = tmp_path / "out"
        outcome = scaffold.run(
            {
                "template_dir": str(TEMPLATE),
                "target_dir": str(target),
                "values": {
                    "module_name": "payments",
                    "class_name": "PaymentService",
                    "description": "Processes payments against the ledger.",
                },
            }
        )
        assert outcome.handled is True
        assert outcome.result["rendered"] == 2
        rendered = target / "src" / "payments.py"
        assert rendered.is_file()
        text = rendered.read_text(encoding="utf-8")
        assert "class PaymentService:" in text
        assert "Processes payments against the ledger." in text
        assert "${" not in text
        readme = (target / "README.md").read_text(encoding="utf-8")
        assert readme.startswith("# PaymentService")

    def test_path_escape_is_refused_with_file_named(self, tmp_path):
        scaffold = TemplateScaffoldCapability()
        target = tmp_path / "out"
        outcome = scaffold.run(
            {
                "template_dir": str(ESCAPING_TEMPLATE),
                "target_dir": str(target),
                "values": {"step": ".."},  # renders the file's path outside the target
            }
        )
        assert outcome.handled is False
        assert "escapes" in outcome.reason
        assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*"))


class TestMigrationClassifier:
    """FR-M33-02 dependency/license/migration-reversibility classification."""

    def test_gradle_manifest_parses_with_spdx_licenses(self):
        classifier = MigrationClassifierCapability()
        outcome = classifier.run({"path": str(GRADLE_DIR)})
        assert outcome.handled is True
        manifest = outcome.result["manifests"][0]
        assert manifest["ecosystem"] == "gradle"
        deps = {d["name"]: d for d in manifest["dependencies"]}
        assert deps["com.acme:ledger-core"]["version"] == "1.2.0"
        assert deps["com.acme:ledger-core"]["license"] == "Apache-2.0"
        assert deps["junit:junit"]["license"] == "EPL-2.0"
        assert all(d["license_source"].startswith("policy-map:") for d in deps.values())

    def test_flyway_and_layout_mark_data_migration_high_confidence(self):
        classifier = MigrationClassifierCapability()
        outcome = classifier.run({"path": str(GRADLE_DIR)})
        reversibility = outcome.result["reversibility"]
        assert reversibility["classification"] == "data_migration"
        assert reversibility["confidence"] == "high"
        assert any("flyway" in e for e in reversibility["evidence"])
        assert any("migration" in e for e in reversibility["evidence"])

    def test_npm_manifest(self):
        classifier = MigrationClassifierCapability()
        outcome = classifier.run({"path": str(NPM_DIR / "package.json")})
        assert outcome.handled is True
        deps = {d["name"]: d for d in outcome.result["manifests"][0]["dependencies"]}
        assert deps["react"]["license"] == "MIT"
        assert deps["pg"]["license"] == "MIT"
        # jest is deliberately absent from the pinned map: unknown, never guessed.
        assert deps["jest"]["license"] == "unknown"
        assert deps["jest"]["license_source"] == "unmapped"
        assert outcome.result["reversibility"]["classification"] == "code_only"

    def test_requirements_manifest_and_unknown_license(self):
        classifier = MigrationClassifierCapability()
        outcome = classifier.run({"path": str(PYTHON_DIR / "requirements.txt")})
        deps = {d["name"]: d for d in outcome.result["manifests"][0]["dependencies"]}
        assert deps["flask"]["license"] == "BSD-3-Clause"
        assert deps["requests"]["license"] == "Apache-2.0"
        assert deps["leftpad"]["license"] == "unknown"
        assert outcome.result["reversibility"]["classification"] == "code_only"
        assert outcome.result["reversibility"]["confidence"] == "medium"

    def test_workspace_license_map_override(self, tmp_path):
        override = tmp_path / "licenses.yaml"
        override.write_text(
            "version: 1\nlicenses:\n  leftpad: WTFPL\n", encoding="utf-8"
        )
        classifier = MigrationClassifierCapability()
        outcome = classifier.run(
            {
                "path": str(PYTHON_DIR / "requirements.txt"),
                "license_map_path": str(override),
            }
        )
        deps = {d["name"]: d for d in outcome.result["manifests"][0]["dependencies"]}
        assert deps["leftpad"]["license"] == "WTFPL"

    def test_broken_license_map_fails_closed(self):
        broken = parse_license_map("version: nope\n", "broken.yaml")
        assert broken.fail_closed
        assert broken.lookup("flask") is None

    def test_unsupported_manifest_refused(self, tmp_path):
        stray = tmp_path / "notes.txt"
        stray.write_text("hello\n", encoding="utf-8")
        classifier = MigrationClassifierCapability()
        outcome = classifier.run({"path": str(stray)})
        assert outcome.handled is False


class TestBlastRadius:
    """FR-M33-02 blast radius over the static import graph."""

    def test_python_chain_lists_paths(self):
        blast = BlastRadiusCapability()
        outcome = blast.run({"root": str(PY_SRC), "path": str(PY_SRC / "ledger.py")})
        assert outcome.handled is True
        result = outcome.result
        assert result["directly_affected"] == ["payments.py"]
        affected = {entry["file"]: entry for entry in result["affected"]}
        assert set(affected) == {"payments.py", "report.py"}
        assert affected["payments.py"]["depth"] == 1
        assert affected["payments.py"]["via"] == ["ledger.py", "payments.py"]
        assert affected["report.py"]["depth"] == 2
        assert affected["report.py"]["via"] == ["ledger.py", "payments.py", "report.py"]

    def test_java_chain(self):
        blast = BlastRadiusCapability()
        outcome = blast.run({"root": str(SRC), "path": str(SRC / "java" / "com" / "acme" / "core" / "Ledger.java")})
        assert outcome.handled is True
        affected = {entry["file"] for entry in outcome.result["affected"]}
        assert any(f.endswith("PaymentService.java") for f in affected)
        assert any(f.endswith("Main.java") for f in affected)

    def test_unknown_symbol_refused_not_guessed(self):
        blast = BlastRadiusCapability()
        outcome = blast.run(
            {"root": str(PY_SRC), "path": str(PY_SRC / "ledger.py"), "symbol": "Nonexistent"}
        )
        assert outcome.handled is False
        assert "Nonexistent" in outcome.reason

    def test_known_symbol_accepted(self):
        blast = BlastRadiusCapability()
        outcome = blast.run(
            {"root": str(PY_SRC), "path": str(PY_SRC / "ledger.py"), "symbol": "Ledger"}
        )
        assert outcome.handled is True
        assert outcome.result["symbol"] == "Ledger"

    def test_file_outside_root_refused(self, tmp_path):
        blast = BlastRadiusCapability()
        outcome = blast.run({"root": str(PY_SRC), "path": str(tmp_path / "x.py")})
        assert outcome.handled is False


class TestPacketDecomposition:
    """FR-M33-02 packet decomposition along graph boundaries."""

    def test_dependency_first_packets(self):
        decomposer = PacketDecomposeCapability()
        outcome = decomposer.run(
            {
                "root": str(PY_SRC),
                "files": ["ledger.py", "payments.py", "report.py", "util.py"],
            }
        )
        assert outcome.handled is True
        packets = outcome.result["packets"]
        assert [p["files"] for p in packets] == [
            ["ledger.py", "util.py"],
            ["payments.py"],
            ["report.py"],
        ]
        assert packets[0]["depends_on"] == []
        assert packets[1]["depends_on"] == [0]
        assert packets[2]["depends_on"] == [1]
        # dependency-first ordering: every packet only depends on earlier ones
        for packet in packets:
            assert all(dep < packet["index"] for dep in packet["depends_on"])

    def test_cycle_is_no_deterministic_path(self, tmp_path):
        (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")
        decomposer = PacketDecomposeCapability()
        outcome = decomposer.run({"root": str(tmp_path)})
        assert outcome.handled is False
        assert "cycle" in outcome.reason

    def test_unknown_file_in_scope_refused(self):
        decomposer = PacketDecomposeCapability()
        outcome = decomposer.run({"root": str(PY_SRC), "files": ["nope.py"]})
        assert outcome.handled is False
        assert "nope.py" in outcome.reason


class TestLedgerCostEstimate:
    """FR-M33-02 / FR-M26-01 cost estimation from ledger history."""

    def rows(self):
        return [
            {"seq": 1, "actor_id": "agent-a", "story_id": "S-1", "story_class": "feature",
             "cost_usd": 10.0, "tokens_in": 100, "tokens_out": 50, "ts_utc": "2026-01-05T10:00:00Z"},
            {"seq": 2, "actor_id": "agent-a", "story_id": "S-2", "story_class": "feature",
             "cost_usd": 20.0, "tokens_in": 200, "tokens_out": 50, "ts_utc": "2026-01-06T10:00:00Z"},
            {"seq": 3, "actor_id": "agent-b", "story_id": "S-3", "story_class": "feature",
             "cost_usd": 30.0, "tokens_in": 300, "tokens_out": 50, "ts_utc": "2026-01-07T10:00:00Z"},
            {"seq": 4, "actor_id": "agent-a", "story_id": "S-9", "story_class": "spike",
             "cost_usd": 999.0, "tokens_in": 10, "tokens_out": 10, "ts_utc": "2026-01-08T10:00:00Z"},
        ]

    def test_median_with_spread_from_same_class(self):
        estimator = LedgerCostEstimateCapability()
        outcome = estimator.run({"rows": self.rows(), "story_class": "feature"})
        assert outcome.handled is True
        result = outcome.result
        assert result["status"] == "estimated"
        assert result["estimate_usd"] == 20.0
        assert result["spread_usd"]["min"] == 10.0
        assert result["spread_usd"]["max"] == 30.0
        assert result["spread_usd"]["p25"] == 15.0
        assert result["spread_usd"]["p75"] == 25.0
        assert result["sample_count"] == 3
        # the spike story must not leak into the feature estimate
        assert result["spread_usd"]["max"] < 100

    def test_no_history_is_unknown_never_fabricated(self):
        estimator = LedgerCostEstimateCapability()
        outcome = estimator.run({"rows": self.rows(), "story_class": "greenfield"})
        assert outcome.handled is True
        assert outcome.result["status"] == "unknown"
        assert outcome.result["estimate_usd"] is None
        assert outcome.result["sample_count"] == 0


class TestCoverageMapping:
    """FR-M33-02 coverage-to-criteria mapping."""

    def test_evidenced_partial_uncovered(self):
        mapping = CoverageMappingCapability()
        criteria = [
            {"id": "AC-1", "text": "Payment records appear in the ledger report"},
            {"id": "AC-2", "text": "Refunds appear in the ledger report"},
            {"id": "AC-3", "text": "The audit trail is tamper-evident"},
        ]
        outcome = mapping.run({"criteria": criteria, "test_target": str(TESTS_DIR)})
        assert outcome.handled is True
        by_id = {c["criterion"]: c for c in outcome.result["criteria"]}
        assert by_id["AC-1"]["classification"] == "evidenced"
        assert by_id["AC-1"]["confidence"] == "high"
        assert {e["test"] for e in by_id["AC-1"]["evidence"]} == {
            "test_record_payment",
            "test_refund_appears_in_ledger_report",
        }
        assert by_id["AC-2"]["classification"] == "evidenced"
        assert by_id["AC-3"]["classification"] == "uncovered"
        assert by_id["AC-3"]["evidence"] == []
        # every evidence entry names file:line
        for criterion in by_id.values():
            for evidence in criterion["evidence"]:
                assert Path(evidence["file"]).is_file()
                assert evidence["line"] >= 1

    def test_missing_target_refused(self):
        mapping = CoverageMappingCapability()
        outcome = mapping.run({"criteria": [{"id": "AC-1", "text": "x"}], "test_target": "/nope"})
        assert outcome.handled is False


class TestRuleAmbiguity:
    """FR-M33-02 rule-based ambiguity detection (assisted deterministic
    first phase, FR-M33-04)."""

    def test_vague_quantifier_flagged_with_rule_id(self):
        capability = RuleAmbiguityCapability()
        outcome = capability.run(
            {"criteria": [{"id": "AC-1", "text": "The API shall respond fast under load"}]}
        )
        assert outcome.handled is True
        flags = outcome.result["flags"]
        assert any(f["rule"] == "ambiguity.vague_quantifier" and f["span"] == "fast" for f in flags)
        assert outcome.result["flagged_criteria"] == ["AC-1"]
        assert outcome.result["gap"] == "propose resolution"

    def test_missing_actor_and_condition(self):
        capability = RuleAmbiguityCapability()
        outcome = capability.run(
            {
                "criteria": [
                    {"id": "AC-1", "text": "Shall record payments in the ledger"},
                    {"id": "AC-2", "text": "The report must export within 2 days"},
                    {"id": "AC-3", "text": "When the payment succeeds, the ledger records it"},
                ]
            }
        )
        flags = outcome.result["flags"]
        by_criterion = {}
        for flag in flags:
            by_criterion.setdefault(flag["criterion"], set()).add(flag["rule"])
        assert "ambiguity.missing_actor" in by_criterion["AC-1"]
        assert "ambiguity.missing_condition" in by_criterion["AC-2"]
        assert "AC-3" not in by_criterion

    def test_learned_rules_ride_along(self):
        document = """
version: 1
rules:
  - id: learned.migration-criteria
    action_classes: [detect_ambiguity]
    when:
      - {field: story.kind, op: equals, value: migration}
    then:
      suggestion: migration criteria need rollback wording
"""
        rules = parse_rule_document(document, "learned.yaml")
        assert rules.refusals == []
        capability = RuleAmbiguityCapability()
        outcome = capability.run(
            {
                "story": {"kind": "migration"},
                "criteria": [{"id": "AC-1", "text": "When the migration runs, data moves"}],
                "rules": rules,
            }
        )
        assert outcome.handled is True
        assert outcome.result["learned_rules_matched"] == ["learned.migration-criteria"]
        assert outcome.result["flags"] == []


class TestConventionRules:
    """FR-M33-02 convention checks (assisted name_tests deterministic
    first phase, FR-M33-04)."""

    def test_naming_and_banned_import_violations_named_with_line(self):
        capability = ConventionRulesCapability()
        outcome = capability.run(
            {
                "root": str(PY_SRC / "bad_style.py"),
                "conventions": {
                    "naming": {"function": "snake_case", "class": "PascalCase"},
                    "banned_imports": ["subprocess"],
                },
            }
        )
        assert outcome.handled is True
        violations = outcome.result["violations"]
        by_rule = {}
        for violation in violations:
            by_rule.setdefault(violation["rule"], []).append(violation)
        assert "convention.naming.function" in by_rule
        assert "BadFunction" in by_rule["convention.naming.function"][0]["detail"]
        assert "convention.naming.class" in by_rule
        assert "my_class" in by_rule["convention.naming.class"][0]["detail"]
        assert "convention.banned_import" in by_rule
        for violation in violations:
            assert violation["line"] >= 1
            assert violation["file"].endswith("bad_style.py")

    def test_layering_violation(self, tmp_path):
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "widget.py").write_text("import datastore.core\n", encoding="utf-8")
        capability = ConventionRulesCapability()
        outcome = capability.run(
            {
                "root": str(tmp_path),
                "conventions": {"layering": [{"from": "ui", "to": "datastore"}]},
            }
        )
        assert outcome.handled is True
        layering = [v for v in outcome.result["violations"] if v["rule"] == "convention.layering"]
        assert len(layering) == 1
        assert layering[0]["file"].endswith("widget.py")

    def test_clean_tree_has_no_violations(self):
        capability = ConventionRulesCapability()
        outcome = capability.run(
            {
                "root": str(PY_SRC / "ledger.py"),
                "conventions": {
                    "naming": {"function": "snake_case", "class": "PascalCase"},
                    "banned_imports": ["subprocess"],
                },
            }
        )
        assert outcome.handled is True
        assert outcome.result["violations"] == []

    def test_unknown_case_convention_refused(self):
        capability = ConventionRulesCapability()
        outcome = capability.run(
            {"root": str(PY_SRC), "conventions": {"naming": {"function": "yelling"}}}
        )
        assert outcome.handled is False
        assert "yelling" in outcome.reason


class TestDispatchEndToEnd:
    """FR-M33-03: the analytical capabilities route through dispatch."""

    def test_deterministic_classes_execute(self):
        registry = registry_with_analytical()
        dispatcher = Dispatcher(catalogue=registry.catalogue, registry=registry)
        outcome = dispatcher.dispatch(
            "estimate_cost",
            {
                "rows": [
                    {"story_id": "S-1", "story_class": "feature", "cost_usd": 12.0,
                     "tokens_in": 5, "tokens_out": 5, "ts_utc": "2026-01-01T00:00:00Z"}
                ],
                "story_class": "feature",
            },
        )
        assert outcome.kind == "executed"
        assert outcome.router_eligible is False
        assert outcome.capability == "ledger_cost_estimate"
        assert outcome.result["estimate_usd"] == 12.0

    def test_assisted_detect_ambiguity_runs_deterministic_first(self):
        registry = registry_with_analytical()
        dispatcher = Dispatcher(catalogue=registry.catalogue, registry=registry)
        outcome = dispatcher.dispatch(
            "detect_ambiguity",
            {"criteria": [{"id": "AC-1", "text": "The page shall load fast"}]},
        )
        assert outcome.kind == "assisted"
        assert outcome.router_eligible is True
        assert outcome.why_llm == WHY_ASSISTED_GAP
        assert outcome.capability == "rule_ambiguity"
        assert outcome.gap == "propose resolution"
        flags = outcome.result["flags"]
        assert any(f["rule"] == "ambiguity.vague_quantifier" for f in flags)

    def test_map_coverage_class_executes_via_catalogue(self):
        registry = registry_with_analytical()
        dispatcher = Dispatcher(catalogue=registry.catalogue, registry=registry)
        outcome = dispatcher.dispatch(
            "map_coverage",
            {
                "criteria": [{"id": "AC-1", "text": "Refunds appear in the ledger report"}],
                "test_target": str(TESTS_DIR),
            },
        )
        assert outcome.kind == "executed"
        assert outcome.capability == "coverage_mapping"
        assert outcome.result["criteria"][0]["classification"] == "evidenced"

    def test_cyclic_decompose_escalates_only_via_named_condition(self):
        registry = registry_with_analytical()
        dispatcher = Dispatcher(catalogue=registry.catalogue, registry=registry)

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("import b\n", encoding="utf-8")
            (root / "b.py").write_text("import a\n", encoding="utf-8")
            outcome = dispatcher.dispatch("decompose_packets", {"root": tmp})
        assert outcome.kind == "generative"  # escalateIf named in policy
        assert outcome.router_eligible is True
        assert outcome.escalate_if == "cyclic_or_ambiguous"
