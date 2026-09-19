"""Learned/rules loader (FR-M33-06; SEC-26).

The engine loads distilled declarative rules from every active adapter's
``learned/rules/`` (``.meridian/adapters/<id>/learned/``) and the
workspace's ``learned/rules/``, applies them ahead of any model call for
the matching action class, and REFUSES executable content: the schema is
declarative-only (closed predicate-op set, closed ``then`` keys, unknown
keys rejected) and every string value is scanned for executable shapes.
A refusal names the rule id; a refused rule never loads, never matches.
"""

from __future__ import annotations

import pytest

from meridian_core.engine.rules import load_rules, parse_rule_document

VALID = """
version: 1
rules:
  - id: name-tests-by-convention
    description: recurring pattern distilled from reviewer feedback
    action_classes: [name_tests, implement]
    when:
      - {field: payload.path, op: matches, value: '.*_test\\.py$'}
      - {field: story.kind, op: in, value: [greenfield, migration]}
      - {field: payload.lang, op: equals, value: python}
      - {field: packet.tags, op: contains, value: unit}
      - {field: payload.option, op: exists}
      - {field: payload.legacy, op: not_equals, value: true}
    then:
      convention: test names read <method>_when_<condition>
      suggestion: prefer arrange-act-assert ordering
"""


class TestParseAndMatch:
    def test_valid_document_loads(self):
        rule_set = parse_rule_document(VALID, "test")
        assert rule_set.refusals == []
        assert len(rule_set.rules) == 1
        rule = rule_set.rules[0]
        assert rule.id == "name-tests-by-convention"
        assert rule.applies_to("name_tests")
        assert not rule.applies_to("clarify")

    def test_predicates_match_payload(self):
        rule = parse_rule_document(VALID, "test").rules[0]
        payload = {
            "payload": {
                "path": "src/app_test.py",
                "lang": "python",
                "option": 1,
                "legacy": False,
            },
            "story": {"kind": "greenfield"},
            "packet": {"tags": ["unit", "fast"]},
        }
        assert rule.matches(payload)
        payload["story"]["kind"] = "maintenance"
        assert not rule.matches(payload)


def _op_cases():
    yield {"a": {"b": 1}}, "equals", "1", True
    yield {"a": {"b": 1}}, "equals", "2", False
    yield {"a": {"b": 1}}, "not_equals", "2", True
    yield {"a": {"b": "hello world"}}, "contains", "world", True
    yield {"a": {"b": ["x", "y"]}}, "contains", "x", True
    yield {"a": {"b": 1}}, "in", "[1, 2]", True
    yield {"a": {"b": 1}}, "exists", "", True


class TestOps:
    @pytest.mark.parametrize(
        "payload,op,value,expected", list(_op_cases()), ids=lambda x: str(x)
    )
    def test_op(self, payload, op, value, expected):
        rule = parse_rule_document(
            f"version: 1\nrules:\n"
            f"  - id: r\n    action_classes: [c]\n"
            f"    when:\n      - {{field: a.b, op: {op}, value: {value}}}\n"
            f"    then:\n      convention: x\n",
            "test",
        ).rules[0]
        assert rule.matches(payload) is expected


class TestExecutableContentRefused:
    """SEC-26: learned state is data, never code."""

    @pytest.mark.parametrize(
        "poison",
        [
            "{field: payload.x, op: equals, value: 'eval(open(\"/etc/passwd\").read())'}",
            "{field: payload.x, op: equals, value: 'exec(payload.code)'}",
            "{field: payload.x, op: equals, value: 'compile(src, \"<s>\", \"exec\")'}",
            "{field: payload.x, op: equals, value: '__import__(\"os\")'}",
            "{field: payload.x, op: equals, value: 'import os'}",
            "{field: payload.x, op: equals, value: 'subprocess.run([\"sh\", \"-c\", cmd])'}",
            "{field: payload.x, op: equals, value: 'os.system(cmd)'}",
            "{field: payload.x, op: equals, value: 'run `rm -rf` now'}",
            "{field: payload.x, op: equals, value: 'call $(evil)'}",
            "{field: payload.x, op: equals, value: '{{ payload.secret }}'}",
        ],
    )
    def test_executable_shaped_value_refused_with_rule_id(self, poison):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: poisoned-rule\n    action_classes: [implement]\n"
            "    when:\n"
            f"      - {poison}\n"
            "    then:\n      convention: x\n",
            "learned/rules/poison.yaml",
        )
        assert rule_set.rules == []
        assert len(rule_set.refusals) == 1
        assert "poisoned-rule" in rule_set.refusals[0]
        assert "SEC-26" in rule_set.refusals[0]

    def test_executable_content_in_then_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: sneaky\n    action_classes: [implement]\n"
            "    when: []\n"
            "    then:\n      suggestion: 'try eval(trick) here'\n",
            "test",
        )
        assert rule_set.rules == []
        assert "sneaky" in rule_set.refusals[0]

    def test_unknown_rule_key_refused_with_rule_id(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: overloaded\n    action_classes: [implement]\n"
            "    when: []\n"
            "    code: 'print(1)'\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert "overloaded" in rule_set.refusals[0]

    def test_unknown_then_key_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: bad-then\n    action_classes: [implement]\n"
            "    when: []\n"
            "    then:\n      run: 'anything at all'\n",
            "test",
        )
        assert rule_set.rules == []
        assert "bad-then" in rule_set.refusals[0]

    def test_valid_rule_next_to_poisoned_rule_still_loads(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: poisoned\n    action_classes: [implement]\n"
            "    when:\n      - {field: a, op: equals, value: 'eval(x)'}\n"
            "    then:\n      convention: x\n"
            "  - id: clean\n    action_classes: [implement]\n"
            "    when:\n      - {field: a, op: equals, value: fine}\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert [rule.id for rule in rule_set.rules] == ["clean"]
        assert any("poisoned" in refusal for refusal in rule_set.refusals)


class TestSchemaRefusals:
    def test_unknown_op_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: bad-op\n    action_classes: [c]\n"
            "    when:\n      - {field: a, op: exec, value: x}\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert "bad-op" in rule_set.refusals[0]

    def test_op_needing_value_without_value_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: no-value\n    action_classes: [c]\n"
            "    when:\n      - {field: a, op: equals}\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert "no-value" in rule_set.refusals[0]

    def test_invalid_regex_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: bad-regex\n    action_classes: [c]\n"
            "    when:\n      - {field: a, op: matches, value: '[unclosed'}\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert "bad-regex" in rule_set.refusals[0]

    def test_in_op_needs_list_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: bad-in\n    action_classes: [c]\n"
            "    when:\n      - {field: a, op: in, value: notalist}\n"
            "    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert "bad-in" in rule_set.refusals[0]

    def test_missing_id_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - action_classes: [c]\n    when: []\n    then:\n      convention: x\n",
            "test",
        )
        assert rule_set.rules == []
        assert rule_set.refusals

    def test_non_mapping_document_refused(self):
        rule_set = parse_rule_document("- just\n- a list\n", "test")
        assert rule_set.rules == []
        assert rule_set.refusals

    def test_broken_yaml_refused(self):
        rule_set = parse_rule_document("{unclosed", "learned/rules/broken.yaml")
        assert rule_set.rules == []
        assert "broken.yaml" in rule_set.refusals[0]

    def test_unknown_top_level_section_refused(self):
        rule_set = parse_rule_document("version: 1\nfunctions: []\n", "test")
        assert rule_set.rules == []
        assert rule_set.refusals

    def test_empty_then_refused(self):
        rule_set = parse_rule_document(
            "version: 1\nrules:\n"
            "  - id: no-then\n    action_classes: [c]\n    when: []\n    then: {}\n",
            "test",
        )
        assert rule_set.rules == []
        assert "no-then" in rule_set.refusals[0]

    def test_empty_document_is_no_rules_no_refusals(self):
        rule_set = parse_rule_document("", "test")
        assert rule_set.rules == []
        assert rule_set.refusals == []


class TestLoadFromDirectories:
    def test_merges_adapter_and_workspace_dirs(self, tmp_path):
        adapter_dir = tmp_path / ".meridian" / "adapters" / "dev" / "learned" / "rules"
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter-rule.yaml").write_text(
            "version: 1\nrules:\n"
            "  - id: adapter-rule\n    action_classes: [implement]\n"
            "    when: []\n    then:\n      convention: x\n",
            encoding="utf-8",
        )
        workspace_dir = tmp_path / "learned" / "rules"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "workspace-rule.yml").write_text(
            "version: 1\nrules:\n"
            "  - id: workspace-rule\n    action_classes: [name_tests]\n"
            "    when: []\n    then:\n      convention: y\n",
            encoding="utf-8",
        )
        rule_set = load_rules([adapter_dir, workspace_dir])
        assert sorted(rule.id for rule in rule_set.rules) == [
            "adapter-rule",
            "workspace-rule",
        ]
        assert rule_set.refusals == []

    def test_missing_directories_skipped(self, tmp_path):
        rule_set = load_rules([tmp_path / "does-not-exist" / "rules"])
        assert rule_set.rules == []
        assert rule_set.refusals == []

    def test_refusals_collected_across_documents(self, tmp_path):
        rules_dir = tmp_path / "learned" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "a.yaml").write_text(
            "version: 1\nrules:\n"
            "  - id: ok\n    action_classes: [c]\n    when: []\n    then:\n      convention: x\n",
            encoding="utf-8",
        )
        (rules_dir / "b.yaml").write_text(
            "version: 1\nrules:\n"
            "  - id: poison\n    action_classes: [c]\n"
            "    when:\n      - {field: a, op: equals, value: 'eval(pwn)'}\n"
            "    then:\n      convention: x\n",
            encoding="utf-8",
        )
        rule_set = load_rules([rules_dir])
        assert [rule.id for rule in rule_set.rules] == ["ok"]
        assert any("poison" in refusal for refusal in rule_set.refusals)

    def test_non_yaml_files_ignored(self, tmp_path):
        rules_dir = tmp_path / "learned" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "notes.md").write_text("eval(evil)", encoding="utf-8")
        (rules_dir / "README.txt").write_text("not a rule", encoding="utf-8")
        rule_set = load_rules([rules_dir])
        assert rule_set.rules == []
        assert rule_set.refusals == []

    def test_for_class_filters(self, tmp_path):
        rules_dir = tmp_path / "learned" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "r.yaml").write_text(
            "version: 1\nrules:\n"
            "  - id: for-implement\n    action_classes: [implement]\n"
            "    when: []\n    then:\n      convention: x\n"
            "  - id: for-clarify\n    action_classes: [clarify]\n"
            "    when: []\n    then:\n      convention: y\n",
            encoding="utf-8",
        )
        rule_set = load_rules([rules_dir])
        assert [rule.id for rule in rule_set.for_class("implement")] == ["for-implement"]
