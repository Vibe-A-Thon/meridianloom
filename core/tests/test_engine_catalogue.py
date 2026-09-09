"""Action-class catalogue (FR-M33-01; §7.10; D16).

The catalogue is the policy artefact classifying every agent action as
deterministic, assisted or generative. Parsing is fail-closed like the
other policy packs, and an unknown class is always refused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.engine.catalogue import (
    load_catalogue,
    parse_catalogue,
    repo_default_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID = """
version: 1
actionClasses:
  parse:
    mode: deterministic
    capability: structural_parse
    engine: tree-sitter
    schema: ParsedFile
    rationale: syntax trees are pure functions of file bytes
  detect_ambiguity:
    mode: assisted
    deterministicFirst: rule_ambiguity
    gap: propose resolution
    schema: AmbiguityProposal
    engine: rules
    rationale: detection is rules; only the proposal is a gap
  implement:
    mode: generative
    validate: [syntax, types, tests, conventions, scope]
    schema: Patch
    engine: none
    rationale: novel implementation, validated before effect
ceilings:
  llm_dependency_ratio_max: 0.35
"""


@pytest.fixture(scope="module")
def repo_pack():
    return load_catalogue(repo_default_paths())


class TestRepositoryCatalogue:
    """The real policy/action-classes.yaml must parse clean and cover §7.10."""

    def test_repo_pack_parses_clean(self, repo_pack):
        assert not repo_pack.fail_closed, repo_pack.errors
        assert repo_pack.version >= 1

    @pytest.mark.parametrize(
        "class_id",
        [
            "parse",
            "resolve_symbol",
            "run_tests",
            "scaffold",
            "classify_migration",
            "blast_radius",
            "decompose_packets",
            "estimate_cost",
            "detect_ambiguity",
            "draft_adr",
            "name_tests",
            "implement",
            "design_novel",
            "clarify",
            "rationale",
        ],
    )
    def test_covers_section_7_10_class(self, repo_pack, class_id):
        assert repo_pack.lookup(class_id) is not None, f"§7.10 class '{class_id}' missing"

    def test_deterministic_classes_name_capabilities(self, repo_pack):
        for entry in repo_pack.classes.values():
            if entry.mode == "deterministic":
                assert entry.capability, f"{entry.id}: deterministic without capability"

    def test_assisted_classes_declare_bounded_gap_and_schema(self, repo_pack):
        for entry in repo_pack.classes.values():
            if entry.mode == "assisted":
                assert entry.gap and entry.schema, f"{entry.id}: assisted without gap/schema"

    def test_generative_classes_declare_validators(self, repo_pack):
        for entry in repo_pack.classes.values():
            if entry.mode == "generative":
                assert entry.validate, f"{entry.id}: generative without validators"
                assert entry.schema, f"{entry.id}: generative without output schema"

    def test_decompose_packets_is_the_only_escalating_deterministic_class(self, repo_pack):
        escalating = [
            entry.id
            for entry in repo_pack.classes.values()
            if entry.mode == "deterministic" and entry.escalate_if
        ]
        assert escalating == ["decompose_packets"]

    def test_llm_dependency_ceiling_matches_section_7_10(self, repo_pack):
        assert repo_pack.ceilings["llm_dependency_ratio_max"] == 0.35

    def test_every_class_carries_a_rationale(self, repo_pack):
        for entry in repo_pack.classes.values():
            assert entry.rationale.strip(), f"{entry.id}: no rationale (FR-M33-01)"


class TestParse:
    def test_valid_pack(self):
        catalogue = parse_catalogue(VALID, "test")
        assert not catalogue.fail_closed
        assert catalogue.lookup("parse").mode == "deterministic"
        assert catalogue.lookup("detect_ambiguity").router_eligible
        assert not catalogue.lookup("parse").router_eligible

    def test_not_yaml_fails_closed(self):
        assert parse_catalogue("{unclosed", "test").fail_closed

    def test_non_mapping_fails_closed(self):
        assert parse_catalogue("- just\n- a\n- list\n", "test").fail_closed

    def test_bad_version_fails_closed(self):
        assert parse_catalogue("version: zero\nactionClasses: {}\n", "test").fail_closed

    def test_unknown_top_level_section_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nsurprises: {}\nactionClasses: {}\n", "test"
        )
        assert catalogue.fail_closed

    def test_unknown_class_key_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses:\n"
            "  parse:\n"
            "    mode: deterministic\n"
            "    capability: structural_parse\n"
            "    engine: tree-sitter\n"
            "    rationale: ok\n"
            "    bonus: true\n",
            "test",
        )
        assert catalogue.fail_closed

    def test_deterministic_without_capability_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses:\n"
            "  parse:\n"
            "    mode: deterministic\n"
            "    engine: tree-sitter\n"
            "    rationale: no capability named\n",
            "test",
        )
        assert catalogue.fail_closed

    def test_generative_with_capability_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses:\n"
            "  implement:\n"
            "    mode: generative\n"
            "    capability: structural_parse\n"
            "    validate: [syntax]\n"
            "    schema: Patch\n"
            "    engine: none\n"
            "    rationale: claims a capability it must not have\n",
            "test",
        )
        assert catalogue.fail_closed

    @pytest.mark.parametrize(
        "body",
        [
            # generative without validators
            "    mode: generative\n    schema: Patch\n    engine: none\n    rationale: r\n",
            # generative with empty validators
            "    mode: generative\n    validate: []\n    schema: Patch\n"
            "    engine: none\n    rationale: r\n",
            # generative without schema
            "    mode: generative\n    validate: [syntax]\n    engine: none\n    rationale: r\n",
        ],
    )
    def test_generative_shape_violations_fail_closed(self, body):
        catalogue = parse_catalogue(
            f"version: 1\nactionClasses:\n  implement:\n{body}", "test"
        )
        assert catalogue.fail_closed

    @pytest.mark.parametrize(
        "body",
        [
            # assisted without deterministicFirst
            "    mode: assisted\n    gap: g\n    schema: S\n    engine: rules\n"
            "    rationale: r\n",
            # assisted without gap
            "    mode: assisted\n    deterministicFirst: c\n    schema: S\n"
            "    engine: rules\n    rationale: r\n",
            # assisted without schema
            "    mode: assisted\n    deterministicFirst: c\n    gap: g\n"
            "    engine: rules\n    rationale: r\n",
        ],
    )
    def test_assisted_shape_violations_fail_closed(self, body):
        catalogue = parse_catalogue(
            f"version: 1\nactionClasses:\n  detect_ambiguity:\n{body}", "test"
        )
        assert catalogue.fail_closed

    def test_unknown_mode_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses:\n"
            "  wish:\n"
            "    mode: magic\n"
            "    engine: none\n"
            "    rationale: r\n",
            "test",
        )
        assert catalogue.fail_closed

    def test_bad_ceiling_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses: {}\nceilings:\n  llm_dependency_ratio_max: 1.5\n",
            "test",
        )
        assert catalogue.fail_closed

    def test_missing_rationale_fails_closed(self):
        catalogue = parse_catalogue(
            "version: 1\nactionClasses:\n"
            "  parse:\n"
            "    mode: deterministic\n"
            "    capability: structural_parse\n"
            "    engine: tree-sitter\n",
            "test",
        )
        assert catalogue.fail_closed

    def test_fail_closed_pack_refuses_every_lookup(self):
        catalogue = parse_catalogue("{unclosed", "test")
        assert catalogue.lookup("parse") is None

    def test_unknown_class_is_refused(self):
        catalogue = parse_catalogue(VALID, "test")
        assert catalogue.lookup("not_a_class") is None


class TestLoad:
    def test_first_readable_file_wins(self, tmp_path):
        override = tmp_path / "action-classes.yaml"
        override.write_text(
            "version: 1\nactionClasses: {}\nceilings: {}\n", encoding="utf-8"
        )
        catalogue = load_catalogue([override, REPO_ROOT / "policy" / "action-classes.yaml"])
        assert catalogue.source == str(override)
        assert catalogue.classes == {}

    def test_falls_back_to_repo_default(self, tmp_path):
        catalogue = load_catalogue([tmp_path / "missing.yaml", REPO_ROOT / "policy" / "action-classes.yaml"])
        assert not catalogue.fail_closed
        assert "parse" in catalogue.classes

    def test_no_file_found_fails_closed(self, tmp_path):
        catalogue = load_catalogue([tmp_path / "missing.yaml"])
        assert catalogue.fail_closed
        assert any("no catalogue file" in e for e in catalogue.errors)

    def test_repo_default_paths_include_workspace_override(self, tmp_path):
        paths = repo_default_paths(tmp_path)
        assert paths[0] == tmp_path / ".meridian" / "policy" / "action-classes.yaml"
        assert paths[1] == REPO_ROOT / "policy" / "action-classes.yaml"
