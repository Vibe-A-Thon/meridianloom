"""Repo convention checks capability (FR-M33-02; FR-M33-04/-06).

The deterministic-first phase of the assisted ``name_tests`` class:
checks repo conventions — naming (snake_case / camelCase / PascalCase
per definition kind), import restrictions (banned import patterns) and
layering (package A may not import package B) — against tree-sitter
parse output. Every violation is named with ``file:line``, the rule id
and the offending name/import. The conventions themselves arrive on the
payload (policy/workspace config or distilled ``learned/rules``
conventions), never hard-coded.

The gap this leaves for the assisted phase is the proposal of candidate
names *within* the conventions — this capability's violations bound that
space.

Zero model calls: tree-sitter plus case/pattern checks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from tree_sitter import Node

from ..attribution.symbols import _LANGUAGES, _parser_for
from .capabilities import CapabilityOutcome

__all__ = ["ConventionRulesCapability"]

_CAPABILITY_NAME = "convention_rules"

#: Naming conventions this checker understands (fixed vocabulary).
_CASES = ("snake_case", "camelCase", "PascalCase")

_CASE_PATTERNS = {
    "snake_case": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}

#: Definition kinds addressable by naming conventions, per language.
_KIND_MAP = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "java": {
        "method_declaration": "method",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
    },
}


def _check_case(name: str, convention: str) -> bool:
    pattern = _CASE_PATTERNS.get(convention)
    return pattern.match(name) is not None if pattern else True


class ConventionRulesCapability:
    """The ``convention_rules`` capability — the ``deterministicFirst``
    phase of the assisted ``name_tests`` class.

    Payload: ``{root, conventions}`` where ``root`` is a file or
    directory to check and ``conventions`` is
    ``{"naming": {kind: case}, "banned_imports": [regex...],
    "layering": [{"from": prefix, "to": prefix}]}``.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        root_raw = action.get("root")
        conventions = action.get("conventions")
        if not isinstance(root_raw, str) or not root_raw:
            return CapabilityOutcome(handled=False, reason="missing 'root'")
        if not isinstance(conventions, Mapping):
            return CapabilityOutcome(handled=False, reason="missing 'conventions' mapping")
        root = Path(root_raw)
        if not root.exists():
            return CapabilityOutcome(handled=False, reason=f"root does not exist: {root}")

        parsed_conventions = self._parse_conventions(conventions)
        if isinstance(parsed_conventions, CapabilityOutcome):
            return parsed_conventions
        naming, banned, layering = parsed_conventions

        sources = (
            [root]
            if root.is_file()
            else sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _LANGUAGES)
        )
        violations: list[dict[str, Any]] = []
        for path in sources:
            violations.extend(self._check_file(path, root, naming, banned, layering))
        violations.sort(key=lambda v: (v["file"], v["line"], v["rule"]))

        return CapabilityOutcome(
            handled=True,
            result={
                "files_checked": len(sources),
                "violations": violations,
                "violation_count": len(violations),
                "gap": "candidate names within conventions",
            },
            reason=f"{len(violations)} convention violation(s) across {len(sources)} file(s) "
            f"(FR-M33-02)",
        )

    @staticmethod
    def _parse_conventions(conventions: Mapping[str, Any]) -> "tuple[dict, list[re.Pattern[str]], list[tuple[str, str]]] | CapabilityOutcome":
        raw_naming = conventions.get("naming", {})
        if not isinstance(raw_naming, Mapping):
            return CapabilityOutcome(handled=False, reason="'naming' must be a mapping of kind → case")
        naming: dict[str, str] = {}
        for kind, case in raw_naming.items():
            if case not in _CASES:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"naming convention '{case}' for '{kind}' is unknown — must be one of {_CASES}",
                )
            naming[str(kind)] = str(case)

        raw_banned = conventions.get("banned_imports", [])
        if not isinstance(raw_banned, list) or any(not isinstance(p, str) for p in raw_banned):
            return CapabilityOutcome(
                handled=False, reason="'banned_imports' must be a list of regex strings"
            )
        banned: list[re.Pattern[str]] = []
        for pattern in raw_banned:
            try:
                banned.append(re.compile(pattern))
            except re.error as error:
                return CapabilityOutcome(
                    handled=False, reason=f"invalid banned_imports pattern {pattern!r}: {error}"
                )

        raw_layering = conventions.get("layering", [])
        if not isinstance(raw_layering, list):
            return CapabilityOutcome(handled=False, reason="'layering' must be a list of {from, to}")
        layering: list[tuple[str, str]] = []
        for entry in raw_layering:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("from"), str) or not isinstance(entry.get("to"), str):
                return CapabilityOutcome(
                    handled=False, reason="each layering entry needs string 'from' and 'to' prefixes"
                )
            layering.append((entry["from"], entry["to"]))
        return naming, banned, layering

    def _check_file(
        self,
        path: Path,
        root: Path,
        naming: Mapping[str, str],
        banned: "list[re.Pattern[str]]",
        layering: "list[tuple[str, str]]",
    ) -> list[dict[str, Any]]:
        parser, def_nodes = _parser_for(path.suffix.lower())
        tree = parser.parse(path.read_bytes())
        language = _LANGUAGES[path.suffix.lower()][0]
        kind_map = _KIND_MAP[language]
        violations: list[dict[str, Any]] = []
        # Layering addresses modules by their dotted path relative to the
        # checked root (ui/widget.py → "ui.widget").
        if root.is_dir():
            module = ".".join(path.relative_to(root).with_suffix("").parts)
        else:
            module = path.stem

        imports: list[tuple[str, int]] = []

        def walk(node: Node) -> None:
            field_name = def_nodes.get(node.type)
            if field_name is not None and node.type in kind_map:
                kind = kind_map[node.type]
                name_node = node.child_by_field_name(field_name)
                if name_node is not None:
                    name = name_node.text.decode("utf-8", errors="replace")
                    convention = naming.get(kind)
                    # Leading-underscore (private/dunder) names are exempt:
                    # __init__, _ helpers are convention-neutral.
                    if convention and not name.startswith("_") and not _check_case(name, convention):
                        violations.append(
                            {
                                "rule": f"convention.naming.{kind}",
                                "file": str(path),
                                "line": node.start_point[0] + 1,
                                "detail": f"{kind} '{name}' violates {convention}",
                            }
                        )
            if node.type == "import_statement" or node.type == "import_from_statement":
                text = node.text.decode("utf-8", errors="replace")
                for pattern in banned:
                    if pattern.search(text):
                        violations.append(
                            {
                                "rule": "convention.banned_import",
                                "file": str(path),
                                "line": node.start_point[0] + 1,
                                "detail": f"import matches banned pattern {pattern.pattern!r}: "
                                f"{text.strip()[:80]}",
                            }
                        )
                        break
                imported = self._imported_name(node)
                if imported is not None:
                    imports.append((imported, node.start_point[0] + 1))
            for child in node.children:
                walk(child)

        walk(tree.root_node)

        if language == "python":
            for imported, line in imports:
                for source_prefix, target_prefix in layering:
                    if module.startswith(source_prefix) and imported.startswith(target_prefix):
                        violations.append(
                            {
                                "rule": "convention.layering",
                                "file": str(path),
                                "line": line,
                                "detail": f"module layer '{source_prefix}' may not import "
                                f"'{target_prefix}' ({imported})",
                            }
                        )
        return violations

    @staticmethod
    def _imported_name(node: Node) -> "str | None":
        if node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module is not None:
                return module.text.decode("utf-8", errors="replace")
            return None
        target = next(
            (c for c in node.children if c.type in ("dotted_name", "aliased_import")),
            None,
        )
        if target is None:
            return None
        if target.type == "aliased_import":
            target = target.child_by_field_name("name") or target
        if target is not None and target.type == "dotted_name":
            return target.text.decode("utf-8", errors="replace")
        return None
