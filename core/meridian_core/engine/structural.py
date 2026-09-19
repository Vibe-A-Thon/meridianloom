"""Structural parse/edit capability (FR-M33-02; FR-M28-02).

Extends the F0 attribution tree-sitter usage (``attribution/symbols.py``):
the same grammar table and parser cache drive *edits*, not only line→symbol
mapping. A structural edit inserts, replaces or deletes a named node region
(byte-range splice) and then re-parses the result — an edit that leaves an
``ERROR`` or missing node anywhere in the tree is REFUSED with the failure
named; the original source is never modified (this capability is pure: it
returns the edited text, it does not write files).

Degradation contract: a language with no registered grammar reports
``no_deterministic_path`` naming the extension, never a fabricated tree. A
target that matches no node is refused naming the target. Zero model calls:
this is tree-sitter only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tree_sitter import Node

from ..attribution.symbols import _LANGUAGES, _parser_for
from .capabilities import CapabilityOutcome

__all__ = ["StructuralParseCapability"]

_CAPABILITY_NAME = "structural_parse"

#: Edit operations a structural edit payload may request.
_EDIT_KINDS = ("replace", "delete", "insert")


@dataclass(frozen=True)
class _Target:
    """Where the edit lands. Either a named-node selector or a 1-based line
    anchor (insert only)."""

    node_type: str | None
    name: str | None
    line: int | None


def _summarize(root: Node, def_nodes: Mapping[str, str]) -> list[dict[str, Any]]:
    """Deterministic, JSON-safe definition inventory of the parse tree."""

    found: list[dict[str, Any]] = []

    def walk(node: Node) -> None:
        field = def_nodes.get(node.type)
        if field is not None:
            name_node = node.child_by_field_name(field)
            found.append(
                {
                    "type": node.type,
                    "name": (
                        name_node.text.decode("utf-8", errors="replace")
                        if name_node is not None
                        else None
                    ),
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                }
            )
        for child in node.children:
            walk(child)

    walk(root)
    return found


def _find_node(root: Node, target: _Target, def_nodes: Mapping[str, str]) -> Node | None:
    """The first node in document order matching the selector. With a name,
    the selector matches on the grammar's declared-name field for that node
    type; without one, the first node of the type wins (deterministic)."""
    if target.node_type is None:
        return None
    want_name = target.name

    def walk(node: Node) -> Node | None:
        if node.type == target.node_type:
            if want_name is None:
                return node
            field = def_nodes.get(node.type)
            name_node = node.child_by_field_name(field) if field else None
            if name_node is not None and name_node.text.decode("utf-8", errors="replace") == want_name:
                return node
        for child in node.children:
            hit = walk(child)
            if hit is not None:
                return hit
        return None

    return walk(root)


def _first_error(root: Node) -> Node | None:
    """The first ERROR/missing node in document order, if the tree is broken."""

    def walk(node: Node) -> Node | None:
        if node.type == "ERROR" or node.is_missing:
            return node
        for child in node.children:
            hit = walk(child)
            if hit is not None:
                return hit
        return None

    return walk(root)


class StructuralParseCapability:
    """The ``structural_parse`` capability: parse summaries and validated
    structural edits, owned by the ``parse`` action class (FR-M33-01).

    Payload (op ``parse``): ``{op, path}`` → definition inventory.
    Payload (op ``edit``): ``{op, path, target, edit:{kind, text?}}`` where
    target is ``{node_type, name?}`` (replace/delete/insert at node end) or
    ``{line}`` (insert after the line). Returns the edited source in
    ``result["text"]``; the caller decides whether to write it.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        op = action.get("op")
        if op not in ("parse", "edit"):
            return CapabilityOutcome(handled=False, reason=f"missing or unknown 'op': {op!r}")
        path = action.get("path")
        if not isinstance(path, str) or not path:
            return CapabilityOutcome(handled=False, reason="missing 'path'")

        target_path = Path(path)
        try:
            source = target_path.read_bytes()
        except OSError as error:
            return CapabilityOutcome(handled=False, reason=f"cannot read {target_path}: {error}")

        entry = _LANGUAGES.get(target_path.suffix.lower())
        if entry is None:
            return CapabilityOutcome(
                handled=False,
                reason=f"no grammar registered for '{target_path.suffix}' — "
                f"structural parse unavailable for {target_path}",
            )
        language_name = entry[0]
        parser, def_nodes = _parser_for(target_path.suffix.lower())
        tree = parser.parse(source)

        if op == "parse":
            return CapabilityOutcome(
                handled=True,
                result={
                    "path": str(target_path),
                    "language": language_name,
                    "root": tree.root_node.type,
                    "has_error": tree.root_node.has_error,
                    "definitions": _summarize(tree.root_node, def_nodes),
                },
                reason="parsed (FR-M33-02)",
            )

        outcome = self._edit(action, source, tree.root_node, def_nodes)
        if isinstance(outcome, CapabilityOutcome):
            return outcome
        edited, node_desc = outcome
        return CapabilityOutcome(
            handled=True,
            result={
                "path": str(target_path),
                "language": language_name,
                "target": node_desc,
                "text": edited.decode("utf-8", errors="replace"),
            },
            reason=f"structural edit applied to {node_desc} and re-parse clean (FR-M28-02)",
        )

    def _edit(
        self, action, source: bytes, root: Node, def_nodes: Mapping[str, str]
    ) -> "tuple[bytes, str] | CapabilityOutcome":
        target = self._target(action.get("target"))
        if isinstance(target, CapabilityOutcome):
            return target
        edit = action.get("edit")
        if not isinstance(edit, Mapping):
            return CapabilityOutcome(handled=False, reason="missing 'edit' mapping")
        kind = edit.get("kind")
        if kind not in _EDIT_KINDS:
            return CapabilityOutcome(handled=False, reason=f"edit kind must be one of {_EDIT_KINDS}")
        text = edit.get("text", "")
        if kind in ("replace", "insert") and not isinstance(text, str):
            return CapabilityOutcome(handled=False, reason="edit 'text' must be a string")

        if target.line is not None:
            if kind != "insert":
                return CapabilityOutcome(
                    handled=False, reason="a line target only supports insert"
                )
            lines = source.decode("utf-8", errors="replace").splitlines(keepends=True)
            if not 0 <= target.line <= len(lines):
                return CapabilityOutcome(
                    handled=False,
                    reason=f"line {target.line} out of range (file has {len(lines)} lines)",
                )
            # Insert after the named 1-based line; line 0 inserts at the top.
            offset = sum(len(line.encode("utf-8")) for line in lines[: target.line])
            edited = source[:offset] + text.encode("utf-8") + source[offset:]
            node_desc = f"line {target.line}"
        else:
            node = _find_node(root, target, def_nodes)
            if node is None:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"no node matching target {target.node_type!r}"
                    + (f" named {target.name!r}" if target.name else "")
                    + f" in {action.get('path')}",
                )
            if kind == "replace":
                edited = source[: node.start_byte] + text.encode("utf-8") + source[node.end_byte :]
            elif kind == "delete":
                edited = source[: node.start_byte] + source[node.end_byte :]
            else:  # insert at node end
                edited = source[: node.end_byte] + text.encode("utf-8") + source[node.end_byte :]
            node_desc = f"{node.type} '{target.name or ''}' lines {node.start_point[0] + 1}-{node.end_point[0] + 1}"

        # Syntax-aware validation: the edited source must re-parse clean.
        reparsed = _parser_for(Path(str(action.get("path"))).suffix.lower())[0].parse(edited)
        error = _first_error(reparsed.root_node)
        if error is not None:
            return CapabilityOutcome(
                handled=False,
                reason=f"edit refused: re-parse of {action.get('path')} fails — "
                f"{error.type} node at line {error.start_point[0] + 1}; "
                f"target {node_desc} left unmodified",
            )
        return edited, node_desc

    @staticmethod
    def _target(raw: Any) -> "_Target | CapabilityOutcome":
        if not isinstance(raw, Mapping):
            return CapabilityOutcome(handled=False, reason="missing 'target' mapping")
        node_type = raw.get("node_type")
        name = raw.get("name")
        line = raw.get("line")
        if line is not None:
            if not isinstance(line, int) or isinstance(line, bool) or line < 0:
                return CapabilityOutcome(handled=False, reason="target 'line' must be a non-negative integer")
            return _Target(node_type=None, name=None, line=line)
        if not isinstance(node_type, str) or not node_type:
            return CapabilityOutcome(
                handled=False, reason="target needs 'node_type'/'name' or a 'line'"
            )
        if name is not None and not isinstance(name, str):
            return CapabilityOutcome(handled=False, reason="target 'name' must be a string")
        return _Target(node_type=node_type, name=name, line=None)
