"""Declarative learned/rules loader (FR-M33-06; SEC-26).

The Trainer (M14) distills recurring model-produced patterns into
declarative rules under every active adapter's ``learned/rules/``
(``.meridian/adapters/<id>/learned/rules/`` and workspace ``learned/rules/``,
D18). The engine loads them here and applies them ahead of any model call
for the matching action class, so distillation directly shrinks model
dependency.

SEC-26 — *learned state is data, never code*: rules are declarative
predicates only, in a tight schema. Anything executable-shaped is REFUSED
and the refusal names the rule id: the rule never loads, never matches,
never runs. Refusals are recorded in ``RuleSet.refusals`` (denials are
recorded, never silent).

Predicate ops are a closed set evaluated in plain Python — no eval, no
templates, no callbacks:

    when:
      - {field: payload.path, op: matches, value: '.*_test\\.py$'}
      - {field: story.kind, op: in, value: [greenfield, migration]}

Zero model calls: predicate evaluation is table lookups over the payload.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

__all__ = ["Predicate", "Rule", "RuleSet", "load_rules", "parse_rule_document"]

#: The closed predicate-op set. Anything else is a schema violation.
OPS = ("equals", "not_equals", "matches", "in", "contains", "exists")

#: Keys a rule entry may carry. Unknown keys are refused (tight schema).
_RULE_KEYS = frozenset({"id", "description", "action_classes", "when", "then"})

#: Keys the ``then`` block may carry: declarative outcomes only.
_THEN_KEYS = frozenset({"convention", "suggestion", "propose"})

#: Executable shapes scanned for in every string value of a rule. A hit
#: means the rule is code smuggled as data and it is refused by id.
_EXECUTABLE_PATTERNS = (
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"__import__"),
    re.compile(r"\bimport\s+[A-Za-z_]"),  # a Python import statement
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bopen\s*\("),
    re.compile(r"`[^`]*`"),  # shell command substitution
    re.compile(r"\$\("),
    re.compile(r"\{\{"),  # template evaluation markers
)


def _executable_hit(value: str) -> str | None:
    for pattern in _EXECUTABLE_PATTERNS:
        match = pattern.search(value)
        if match:
            return f"executable content ({match.group(0)!r})"
    return None


def _scan_strings(value: Any, where: str, hits: list[str]) -> None:
    if isinstance(value, str):
        hit = _executable_hit(value)
        if hit:
            hits.append(f"{where}: {hit}")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _scan_strings(item, f"{where}.{key}", hits)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, item in enumerate(value):
            _scan_strings(item, f"{where}[{index}]", hits)


@dataclass(frozen=True)
class Predicate:
    """One declarative predicate over the action payload."""

    field: str
    op: str
    value: Any = None

    def matches(self, payload: Mapping[str, Any]) -> bool:
        """Evaluate against a payload. Pure data lookup — dotted field
        paths, closed op set, no execution."""
        current: Any = payload
        for part in self.field.split("."):
            if not isinstance(current, Mapping) or part not in current:
                current = None
                break
            current = current[part]
        if self.op == "exists":
            return current is not None
        if self.op == "equals":
            return current == self.value
        if self.op == "not_equals":
            return current != self.value
        if self.op == "in":
            return isinstance(self.value, Sequence) and not isinstance(
                self.value, (str, bytes, bytearray)
            ) and current in self.value
        if self.op == "contains":
            return (
                isinstance(current, Sequence)
                and not isinstance(current, (str, bytes, bytearray))
                and self.value in current
            ) or (isinstance(current, str) and isinstance(self.value, str) and self.value in current)
        if self.op == "matches":
            return (
                isinstance(current, str)
                and isinstance(self.value, str)
                and re.search(self.value, current) is not None
            )
        return False  # unknown op never matches (fail closed)


@dataclass(frozen=True)
class Rule:
    """One declarative learned rule (FR-M33-06)."""

    id: str
    action_classes: tuple[str, ...]
    predicates: tuple[Predicate, ...]
    then: Mapping[str, str]
    source: str
    description: str = ""

    def applies_to(self, action_class: str) -> bool:
        return action_class in self.action_classes

    def matches(self, payload: Mapping[str, Any]) -> bool:
        """True when every predicate holds. Pure evaluation, no code."""
        return all(predicate.matches(payload) for predicate in self.predicates)


@dataclass
class RuleSet:
    """All learned rules from every source path.

    ``refusals`` names every rule that failed schema validation or carried
    executable content (SEC-26) — refused rules are excluded from ``rules``
    so a poisoned rule can never match.
    """

    rules: list[Rule] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    def for_class(self, action_class: str) -> list[Rule]:
        """Every rule that applies to the action class (FR-M33-06: applied
        ahead of any model call for the matching class)."""
        return [rule for rule in self.rules if rule.applies_to(action_class)]

    def matching(self, action_class: str, payload: Mapping[str, Any]) -> list[Rule]:
        """Rules that apply to the class AND match the payload."""
        return [rule for rule in self.for_class(action_class) if rule.matches(payload)]


def _parse_predicate(raw: Any, where: str, errors: list[str]) -> Predicate | None:
    if not isinstance(raw, Mapping):
        errors.append(f"{where}: expected a mapping with field/op/value")
        return None
    unknown = set(raw) - {"field", "op", "value"}
    for key in sorted(unknown):
        errors.append(f"{where}: unknown key '{key}'")
    field_name = raw.get("field")
    if not isinstance(field_name, str) or not field_name.strip():
        errors.append(f"{where}.field: expected a non-empty dotted path")
        return None
    op = raw.get("op")
    if op not in OPS:
        errors.append(f"{where}.op: '{op}' is not a predicate op ({', '.join(OPS)})")
        return None
    value = raw.get("value")
    if op in ("equals", "not_equals", "matches", "in", "contains") and value is None:
        errors.append(f"{where}.value: op '{op}' needs a value")
        return None
    if op == "matches" and isinstance(value, str):
        try:
            re.compile(value)
        except re.error as error:
            errors.append(f"{where}.value: invalid regex: {error}")
            return None
    if op == "in" and not (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    ):
        errors.append(f"{where}.value: op 'in' needs a list value")
        return None
    return Predicate(field=field_name.strip(), op=op, value=value)


def parse_rule_document(text: str, source: str) -> RuleSet:
    """Parse one ``learned/rules/`` document. Refused rules (schema
    violations or executable content) are excluded and named; a
    syntactically broken document refuses all of its rules."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return RuleSet(refusals=[f"{source}: not valid YAML: {error} — document refused"])
    if raw is None:
        return RuleSet()
    if not isinstance(raw, Mapping):
        return RuleSet(refusals=[f"{source}: must be a mapping at the top level — document refused"])
    unknown_top = set(raw) - {"version", "rules"}
    if unknown_top:
        return RuleSet(
            refusals=[
                f"{source}: unknown top-level section '{sorted(unknown_top)[0]}' — document refused"
            ]
        )
    raw_rules = raw.get("rules", [])
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes, bytearray)):
        return RuleSet(refusals=[f"{source}: 'rules' must be a list — document refused"])

    rules: list[Rule] = []
    refusals: list[str] = []
    for index, raw_rule in enumerate(raw_rules):
        where = f"{source}:rules[{index}]"
        if not isinstance(raw_rule, Mapping):
            refusals.append(f"{where}: expected a mapping — rule refused")
            continue
        unknown = set(raw_rule) - _RULE_KEYS
        rule_id = raw_rule.get("id")
        label = rule_id if isinstance(rule_id, str) and rule_id.strip() else where
        if unknown:
            refusals.append(
                f"{label}: unknown keys {sorted(unknown)} — rule refused "
                f"(declarative schema, SEC-26)"
            )
            continue
        if not isinstance(rule_id, str) or not rule_id.strip():
            refusals.append(f"{where}: rule needs a non-empty 'id' — rule refused")
            continue

        # Executable-content scan BEFORE anything else: a rule carrying code
        # is refused with its id named, whatever else is wrong with it.
        hits: list[str] = []
        _scan_strings(raw_rule, label, hits)
        if hits:
            refusals.append(f"{label}: {'; '.join(hits)} — rule refused (SEC-26)")
            continue

        action_classes = raw_rule.get("action_classes")
        if (
            not isinstance(action_classes, Sequence)
            or isinstance(action_classes, (str, bytes, bytearray))
            or not action_classes
            or any(not isinstance(c, str) or not c.strip() for c in action_classes)
        ):
            refusals.append(f"{label}: 'action_classes' must be a non-empty list of strings — rule refused")
            continue
        raw_when = raw_rule.get("when", [])
        if not isinstance(raw_when, Sequence) or isinstance(raw_when, (str, bytes, bytearray)):
            refusals.append(f"{label}: 'when' must be a list of predicates — rule refused")
            continue
        predicates: list[Predicate] = []
        p_errors: list[str] = []
        for p_index, raw_predicate in enumerate(raw_when):
            predicate = _parse_predicate(raw_predicate, f"{label}.when[{p_index}]", p_errors)
            if predicate is not None:
                predicates.append(predicate)
        if p_errors:
            refusals.append(f"{label}: {'; '.join(p_errors)} — rule refused")
            continue
        raw_then = raw_rule.get("then")
        if not isinstance(raw_then, Mapping) or not raw_then:
            refusals.append(f"{label}: 'then' must be a non-empty mapping — rule refused")
            continue
        unknown_then = set(raw_then) - _THEN_KEYS
        if unknown_then:
            refusals.append(
                f"{label}: unknown 'then' keys {sorted(unknown_then)} — rule refused (SEC-26)"
            )
            continue
        if any(not isinstance(v, str) or not v.strip() for v in raw_then.values()):
            refusals.append(f"{label}: 'then' values must be non-empty strings — rule refused")
            continue
        description = raw_rule.get("description", "")
        rules.append(
            Rule(
                id=rule_id.strip(),
                action_classes=tuple(c.strip() for c in action_classes),
                predicates=tuple(predicates),
                then={k: v.strip() for k, v in raw_then.items()},
                source=source,
                description=description.strip() if isinstance(description, str) else "",
            )
        )
    return RuleSet(rules=rules, refusals=refusals)


def load_rules(directories: Sequence[str | Path]) -> RuleSet:
    """Load every ``*.yaml`` / ``*.yml`` rule document under each
    directory (adapter ``learned/rules/`` dirs, workspace ``learned/rules/``).
    Missing directories are not an error. Refusals from every document are
    collected and named."""
    combined = RuleSet()
    for directory in directories:
        root = Path(directory)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".yaml", ".yml"):
                continue
            document = parse_rule_document(
                path.read_text(encoding="utf-8"), str(path)
            )
            combined.rules.extend(document.rules)
            combined.refusals.extend(document.refusals)
    return combined
