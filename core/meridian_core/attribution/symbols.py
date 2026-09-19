"""tree-sitter line→symbol mapping (FR-M33-02 subset, F0 Workstream C task 14).

Maps (file, line) to the qualified name of the enclosing function/class so a
provenance answer reads "PaymentController.submit", not only line 12.
Parsing is structural and deterministic — zero model calls (FR-M36-07).

Degradation contract (G3): an unregistered language reports
``symbol: None, language: None`` and never raises; a parse error in a
registered language still yields the best enclosing-symbol chain
tree-sitter can recover; a line with no enclosing definition reports
``symbol: None`` with the language set. Only a missing/unreadable file is
an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tree_sitter import Language, Node, Parser

__all__ = ["SymbolsError", "SymbolResult", "symbol_at"]


class SymbolsError(Exception):
    """A clean, user-actionable symbol-resolution failure (never a crash)."""


@dataclass(frozen=True)
class SymbolResult:
    path: str
    line: int  # 1-based, as requested
    language: str | None  # null when the extension is not registered
    symbol: str | None  # qualified enclosing name, null when none/degraded


# Per-language grammar + the node types that open a named scope, with the
# field carrying the declared name. Deliberately data, not .scm query
# files: the queries ship inside the grammar wheels and drift across
# versions, while the def-node shapes below are stable.
def _java_language() -> Language:
    import tree_sitter_java

    return Language(tree_sitter_java.language())


def _python_language() -> Language:
    import tree_sitter_python

    return Language(tree_sitter_python.language())


_LANGUAGES: dict[str, tuple[str, Callable[[], Language], dict[str, str]]] = {
    ".java": (
        "java",
        _java_language,
        {
            "class_declaration": "name",
            "interface_declaration": "name",
            "enum_declaration": "name",
            "method_declaration": "name",
            "constructor_declaration": "name",
        },
    ),
    ".py": (
        "python",
        _python_language,
        {"class_definition": "name", "function_definition": "name"},
    ),
}

_parsers: dict[str, tuple[Parser, dict[str, str]]] = {}


def _parser_for(extension: str) -> tuple[Parser, dict[str, str]] | None:
    entry = _LANGUAGES.get(extension.lower())
    if entry is None:
        return None
    cached = _parsers.get(extension.lower())
    if cached is None:
        _, factory, def_nodes = entry
        cached = (Parser(factory()), def_nodes)
        _parsers[extension.lower()] = cached
    return cached


def _def_name(node: Node, def_nodes: dict[str, str]) -> str | None:
    field = def_nodes.get(node.type)
    if field is None:
        return None
    child = node.child_by_field_name(field)
    if child is None:
        return None
    return child.text.decode("utf-8", errors="replace")


def _enclosing_chain(root: Node, row: int, def_nodes: dict[str, str]) -> list[str]:
    """Qualified name of the innermost definition enclosing ``row`` (0-based).

    tree-sitter tolerates broken syntax, so this always returns the best
    chain recoverable from the concrete tree — never an exception.
    """
    chain: list[str] = []

    def walk(node: Node) -> None:
        if node.start_point[0] > row or node.end_point[0] < row:
            return
        name = _def_name(node, def_nodes)
        if name is not None:
            chain.append(name)
        for child in node.children:
            if child.start_point[0] <= row and child.end_point[0] >= row:
                walk(child)

    walk(root)
    return chain


def symbol_at(path: Path | str, line: int) -> SymbolResult:
    """Resolve the enclosing symbol of ``line`` (1-based) in ``path``."""
    target = Path(path)
    if not target.exists():
        raise SymbolsError(f"file does not exist: {target}")
    language = _LANGUAGES.get(target.suffix.lower())
    if language is None:
        return SymbolResult(path=str(target), line=line, language=None, symbol=None)
    parser, def_nodes = _parser_for(target.suffix.lower())
    source = target.read_bytes()
    tree = parser.parse(source)
    chain = _enclosing_chain(tree.root_node, line - 1, def_nodes)
    return SymbolResult(
        path=str(target),
        line=line,
        language=language[0],
        symbol=".".join(chain) if chain else None,
    )
