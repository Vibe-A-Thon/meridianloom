"""Coverage-to-criteria mapping capability (FR-M33-02; FR-M33-06).

Maps acceptance criteria to the tests/lines that evidence them, purely
deterministically: test files are parsed with tree-sitter (test
functions in ``test_*.py`` / ``*Test.java``, plus their decorators and
annotations), criterion text is tokenised, and a criterion is matched
against tests by token overlap. Per criterion the classification is:

* ``evidenced``  — most criterion tokens are covered by matching tests;
* ``partial``    — some coverage, well short of full;
* ``uncovered``  — essentially no token evidence.

Each classification is confidence-labelled from the coverage fraction.
The thresholds are fixed constants here — the engine's contract is that
the same inputs always produce the same map (FR-M33-08).

Zero model calls: tree-sitter plus token arithmetic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from tree_sitter import Node

from ..attribution.symbols import _LANGUAGES, _parser_for
from .capabilities import CapabilityOutcome

__all__ = ["CoverageMappingCapability"]

_CAPABILITY_NAME = "coverage_mapping"

#: Fixed deterministic thresholds (fraction of criterion tokens covered).
_EVIDENCED_MIN = 0.75
_PARTIAL_MIN = 0.25

#: Words that carry no matching signal (criterion boilerplate).
_STOPWORDS = frozenset(
    {
        "shall", "must", "should", "will", "would", "could", "may", "the",
        "and", "for", "with", "from", "that", "this", "when", "then",
        "than", "have", "has", "been", "into", "onto", "able", "user",
        "system", "story", "criterion", "acceptance",
    }
)

#: Test files: pytest naming, or JUnit class naming.
_TEST_FILE_RE = re.compile(r"(^test_.*\.py$|.*_test\.py$|.*Test\.java$)", re.IGNORECASE)

#: Java annotation names that mark a test (matched on the last segment).
_JAVA_TEST_ANNOTATIONS = frozenset({"Test", "ParameterizedTest", "RepeatedTest"})

_TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")


def _criterion_tokens(text: str) -> list[str]:
    """Significant lowercase tokens of a criterion (len >= 4, not a
    stopword, singularised crudely by dropping a trailing 's')."""
    tokens = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if len(token) < 4 or token in _STOPWORDS:
            continue
        tokens.append(token[:-1] if token.endswith("s") and len(token) > 4 else token)
    return tokens


def _name_tokens(name: str) -> set[str]:
    """Tokens of a test name: snake_case / camelCase split, singularised."""
    parts = re.split(r"[_\s]+|(?<=[a-z0-9])(?=[A-Z])", name)
    tokens: set[str] = set()
    for part in parts:
        for match in _TOKEN_RE.finditer(part.lower()):
            token = match.group(0)
            if len(token) < 3:
                continue
            tokens.add(token[:-1] if token.endswith("s") and len(token) > 4 else token)
    return tokens


def _decorator_names(node: Node) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type != "decorator":
            continue
        target = next((c for c in child.children if c.type == "identifier"), None)
        if target is not None:
            names.append(target.text.decode("utf-8", errors="replace"))
    return names


def _java_annotations(node: Node) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type != "modifiers":
            continue
        for annotation in child.children:
            if annotation.type != "annotation":
                continue
            name_node = next(
                (c for c in annotation.children if c.type in ("identifier", "scoped_identifier")),
                None,
            )
            if name_node is not None:
                names.append(name_node.text.decode("utf-8", errors="replace").split(".")[-1])
    return names


def collect_tests(paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    """Parse test files and return one record per test: name, file, line
    and the token set derived from its name (and pytest markers /
    JUnit annotations)."""
    tests: list[dict[str, Any]] = []
    for raw_path in sorted(str(p) for p in paths):
        path = Path(raw_path)
        if not path.is_file() or not _TEST_FILE_RE.match(path.name):
            continue
        entry = _LANGUAGES.get(path.suffix.lower())
        if entry is None:
            continue
        parser, def_nodes = _parser_for(path.suffix.lower())
        tree = parser.parse(path.read_bytes())

        def walk(node: Node) -> None:
            field_name = def_nodes.get(node.type)
            if field_name is not None and node.type in (
                "function_definition",
                "method_declaration",
            ):
                name_node = node.child_by_field_name(field_name)
                if name_node is None:
                    return
                name = name_node.text.decode("utf-8", errors="replace")
                tokens = _name_tokens(name)
                line = node.start_point[0] + 1
                if node.type == "function_definition":
                    tokens.update(_decorator_names(node.parent or node))
                else:
                    for annotation in _java_annotations(node):
                        tokens.add(annotation)
                        if annotation in _JAVA_TEST_ANNOTATIONS:
                            tokens.update(_name_tokens(name))
                tests.append(
                    {"name": name, "file": str(path), "line": line, "tokens": tokens}
                )
            for child in node.children:
                walk(child)

        walk(tree.root_node)
    return tests


def _test_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p
        for p in target.rglob("*")
        if p.is_file() and _TEST_FILE_RE.match(p.name) and p.suffix.lower() in _LANGUAGES
    )


class CoverageMappingCapability:
    """The ``coverage_mapping`` capability, owned by the ``map_coverage``
    action class (FR-M33-01).

    Payload: ``{criteria, test_target}`` — ``criteria`` is a list of
    ``{id, text}`` mappings; ``test_target`` is a test file or a
    directory scanned for test files.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        criteria = action.get("criteria")
        if (
            not isinstance(criteria, list)
            or not criteria
            or any(not isinstance(c, Mapping) or not isinstance(c.get("text"), str) for c in criteria)
        ):
            return CapabilityOutcome(
                handled=False, reason="'criteria' must be a non-empty list of {id, text} mappings"
            )
        target_raw = action.get("test_target")
        if not isinstance(target_raw, str) or not target_raw:
            return CapabilityOutcome(handled=False, reason="missing 'test_target'")
        target = Path(target_raw)
        if not target.exists():
            return CapabilityOutcome(handled=False, reason=f"test target does not exist: {target}")

        tests = collect_tests(_test_files(target))

        mapped: list[dict[str, Any]] = []
        for criterion in criteria:
            criterion_id = str(criterion.get("id"))
            text = str(criterion["text"])
            tokens = _criterion_tokens(text)
            if not tokens:
                mapped.append(
                    {
                        "criterion": criterion_id,
                        "classification": "uncovered",
                        "confidence": "low",
                        "covered_tokens": [],
                        "missing_tokens": [],
                        "evidence": [],
                        "note": "criterion text yields no significant tokens",
                    }
                )
                continue
            evidence: list[dict[str, Any]] = []
            covered: set[str] = set()
            token_set = set(tokens)
            for test in tests:
                overlap = token_set & test["tokens"]
                if overlap:
                    covered.update(overlap)
                    evidence.append(
                        {
                            "test": test["name"],
                            "file": test["file"],
                            "line": test["line"],
                            "tokens": sorted(overlap),
                        }
                    )
            fraction = len(covered) / len(token_set)
            missing = sorted(token_set - covered)
            if fraction >= _EVIDENCED_MIN:
                classification = "evidenced"
                confidence = "high" if fraction >= 1.0 else "medium"
            elif fraction >= _PARTIAL_MIN:
                classification = "partial"
                confidence = "medium"
            else:
                classification = "uncovered"
                confidence = "high"
            mapped.append(
                {
                    "criterion": criterion_id,
                    "classification": classification,
                    "confidence": confidence,
                    "coverage": round(fraction, 4),
                    "covered_tokens": sorted(covered),
                    "missing_tokens": missing,
                    "evidence": evidence,
                }
            )

        return CapabilityOutcome(
            handled=True,
            result={"criteria": mapped, "tests_found": len(tests)},
            reason=f"mapped {len(mapped)} criteria against {len(tests)} test(s) (FR-M33-02)",
        )
