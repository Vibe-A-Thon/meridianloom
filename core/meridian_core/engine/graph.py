"""Static import-graph capabilities (FR-M33-02; FR-M13-09).

Builds a file-level import graph from tree-sitter parses, reusing the
F0 grammar table and parser cache (``attribution/symbols.py``): Python
``import`` / ``from … import`` statements and Java ``package`` /
``import`` declarations become edges between files. On this graph:

* ``graph_blast_radius`` answers blast-radius for a changed file (or a
  changed symbol in that file): the directly and transitively affected
  nodes, each with the dependency path from the change listed. Graph
  reachability is exact and replay-identical — gates and ablations
  consume it, so a fabricated answer is worse than none.
* ``graph_decompose`` partitions a story's file set into work packets
  along graph boundaries: each packet's files depend only on earlier
  packets, so every packet is independently testable, ordered
  dependency-first. A cycle is ``no_deterministic_path`` — the
  ``decompose_packets`` class names its escalation condition in policy
  (``escalateIf: cyclic_or_ambiguous``).

Zero model calls: tree-sitter plus graph traversal only.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from tree_sitter import Node

from ..attribution.symbols import _LANGUAGES, _parser_for
from .capabilities import CapabilityOutcome

__all__ = ["BlastRadiusCapability", "ImportGraph", "PacketDecomposeCapability", "build_import_graph"]

_BLAST_NAME = "graph_blast_radius"
_DECOMPOSE_NAME = "graph_decompose"

_SOURCE_SUFFIXES = frozenset(_LANGUAGES)


@dataclass
class FileNode:
    """One file in the import graph: its symbols and raw import names."""

    path: str  # relative to the graph root, forward slashes
    language: str
    symbols: list[dict[str, Any]] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # raw imported module/type names


@dataclass
class ImportGraph:
    """Nodes (relative paths) and depends-on edges between them."""

    root: str
    nodes: dict[str, FileNode] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)  # importer → imported

    def importers_of(self, path: str) -> set[str]:
        """Reverse edges: who imports ``path``."""
        return {src for src, targets in self.edges.items() if path in targets}


def _definitions(root: Node, def_nodes: Mapping[str, str]) -> list[dict[str, Any]]:
    """Definition inventory, same shape as the structural capability."""

    def walk(node: Node, found: list[dict[str, Any]]) -> None:
        field_name = def_nodes.get(node.type)
        if field_name is not None:
            name_node = node.child_by_field_name(field_name)
            found.append(
                {
                    "kind": node.type,
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
            walk(child, found)

    found: list[dict[str, Any]] = []
    walk(root, found)
    return found


def _python_imports(root: Node) -> list[str]:
    """Raw imported module names from import statements (relative imports
    yield nothing — they cannot be resolved without package context)."""
    names: list[str] = []

    def walk(node: Node) -> None:
        if node.type == "import_statement":
            for child in node.children:
                target = child
                if target.type == "aliased_import":
                    target = target.child_by_field_name("name") or target
                if target is not None and target.type == "dotted_name":
                    names.append(target.text.decode("utf-8", errors="replace"))
        elif node.type == "import_from_statement":
            if node.child_by_field_name("relative_import") is not None:
                return  # unresolved without package context
            module = node.child_by_field_name("module_name")
            if module is not None:
                names.append(module.text.decode("utf-8", errors="replace"))
        for child in node.children:
            walk(child)

    walk(root)
    return names


def _java_package(root: Node) -> str | None:
    for child in root.children:
        if child.type == "package_declaration":
            for part in child.children:
                if part.type in ("scoped_identifier", "identifier"):
                    return part.text.decode("utf-8", errors="replace")
    return None


def _java_imports(root: Node) -> "tuple[list[str], list[str]]":
    """(imported type names, wildcard package prefixes)."""
    types: list[str] = []
    packages: list[str] = []
    for child in root.children:
        if child.type != "import_declaration":
            continue
        body = next(
            (c for c in child.children if c.type in ("scoped_identifier", "identifier")),
            None,
        )
        if body is None:
            continue
        text = body.text.decode("utf-8", errors="replace")
        if any(c.type == "asterisk" for c in child.children):
            packages.append(text)
        else:
            types.append(text)
    return types, packages


def _python_module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def build_import_graph(root: str | Path) -> ImportGraph:
    """Parse every registered-language source under ``root`` and resolve
    imports to files. Unresolvable imports are dropped (no fabricated
    edges); a file that imports nothing still appears as a node."""
    root_path = Path(root)
    graph = ImportGraph(root=str(root_path))
    py_modules: dict[str, str] = {}
    java_types: dict[str, str] = {}  # "pkg.Type" → file
    java_packages: dict[str, set[str]] = {}

    sources = sorted(
        p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in _SOURCE_SUFFIXES
    )
    for path in sources:
        relative = path.relative_to(root_path)
        rel = str(relative).replace("\\", "/")
        entry = _LANGUAGES[path.suffix.lower()]
        parser, def_nodes = _parser_for(path.suffix.lower())
        tree = parser.parse(path.read_bytes())
        node = FileNode(path=rel, language=entry[0], symbols=_definitions(tree.root_node, def_nodes))
        if path.suffix.lower() == ".py":
            node.imports = _python_imports(tree.root_node)
            py_modules[_python_module_name(relative)] = rel
        else:
            package = _java_package(tree.root_node) or ""
            node.imports, wildcards = _java_imports(tree.root_node)
            for symbol in node.symbols:
                if symbol["name"] and package:
                    java_types[f"{package}.{symbol['name']}"] = rel
            if package:
                java_packages.setdefault(package, set()).add(rel)
            for wildcard in wildcards:
                node.imports.append(f"{wildcard}.*")
        graph.nodes[rel] = node

    def resolve_python(name: str) -> "str | None":
        if name in py_modules:
            return py_modules[name]
        parts = name.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in py_modules:
                return py_modules[candidate]
            parts.pop()
        return None

    def resolve_java(name: str) -> "str | None":
        if name in java_types:
            return java_types[name]
        if name.endswith(".*"):
            members = java_packages.get(name[:-2])
            return None  # wildcard: resolved per-member below
        # Unique package-prefix match: import of a nested/member type.
        matches = {path for full, path in java_types.items() if full.rsplit(".", 1)[0] == name}
        if len(matches) == 1:
            return matches.pop()
        return None

    for rel, node in graph.nodes.items():
        targets: set[str] = set()
        for imported in node.imports:
            if node.language == "python":
                resolved = resolve_python(imported)
            else:
                resolved = resolve_java(imported)
                if resolved is None and imported.endswith(".*"):
                    members = java_packages.get(imported[:-2], set())
                    targets.update(m for m in members if m != rel)
                    continue
            if resolved is not None and resolved != rel:
                targets.add(resolved)
        if targets:
            graph.edges[rel] = targets
    return graph


def _relative_to(graph_root: Path, path: Path) -> "str | None":
    try:
        return str(path.resolve().relative_to(graph_root.resolve())).replace("\\", "/")
    except ValueError:
        return None


class BlastRadiusCapability:
    """The ``graph_blast_radius`` capability, owned by the ``blast_radius``
    action class. Payload: ``{root, path, symbol?}``."""

    @property
    def name(self) -> str:
        return _BLAST_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        root_raw = action.get("root")
        path_raw = action.get("path")
        if not isinstance(root_raw, str) or not root_raw:
            return CapabilityOutcome(handled=False, reason="missing 'root'")
        if not isinstance(path_raw, str) or not path_raw:
            return CapabilityOutcome(handled=False, reason="missing 'path'")
        root = Path(root_raw)
        if not root.is_dir():
            return CapabilityOutcome(handled=False, reason=f"graph root does not exist: {root}")
        rel = _relative_to(root, Path(path_raw))
        if rel is None:
            return CapabilityOutcome(
                handled=False, reason=f"path {path_raw} is not inside graph root {root}"
            )

        graph = build_import_graph(root)
        node = graph.nodes.get(rel)
        if node is None:
            return CapabilityOutcome(
                handled=False,
                reason=f"no parseable source at {rel} under {root} — blast radius unavailable "
                f"for unregistered languages",
            )
        symbol = action.get("symbol")
        if symbol is not None:
            if not isinstance(symbol, str) or not symbol.strip():
                return CapabilityOutcome(handled=False, reason="'symbol' must be a non-empty string")
            if symbol not in {s["name"] for s in node.symbols}:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"symbol '{symbol}' is not defined in {rel} — blast radius refused "
                    f"rather than guessed",
                )

        # BFS over reverse edges; the via-chain is the shortest dependency
        # path from the changed node (deterministic: sorted frontier).
        affected: dict[str, tuple[int, list[str]]] = {}
        queue: deque[tuple[str, list[str]]] = deque([(rel, [rel])])
        while queue:
            current, chain = queue.popleft()
            for importer in sorted(graph.importers_of(current)):
                if importer in affected or importer == rel:
                    continue
                affected[importer] = (len(chain), chain + [importer])
                queue.append((importer, chain + [importer]))

        entries = [
            {"file": file, "depth": depth, "via": chain}
            for file, (depth, chain) in sorted(affected.items())
        ]
        return CapabilityOutcome(
            handled=True,
            result={
                "node": rel,
                "symbol": symbol,
                "directly_affected": sorted(graph.importers_of(rel)),
                "affected": entries,
            },
            reason=f"blast radius over import graph: {len(entries)} affected file(s) (FR-M33-02)",
        )


class PacketDecomposeCapability:
    """The ``graph_decompose`` capability, owned by the ``decompose_packets``
    action class. Payload: ``{root, files?}`` — ``files`` (relative paths)
    scopes the decomposition to a story's touch set; omitted means the
    whole tree."""

    @property
    def name(self) -> str:
        return _DECOMPOSE_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        root_raw = action.get("root")
        if not isinstance(root_raw, str) or not root_raw:
            return CapabilityOutcome(handled=False, reason="missing 'root'")
        root = Path(root_raw)
        if not root.is_dir():
            return CapabilityOutcome(handled=False, reason=f"graph root does not exist: {root}")
        graph = build_import_graph(root)

        scope_raw = action.get("files")
        if scope_raw is None:
            scope = set(graph.nodes)
        else:
            if (
                not isinstance(scope_raw, list)
                or any(not isinstance(item, str) or not item for item in scope_raw)
            ):
                return CapabilityOutcome(handled=False, reason="'files' must be a list of relative paths")
            scope = {str(Path(item)).replace("\\", "/") for item in scope_raw}
            unknown = sorted(scope - set(graph.nodes))
            if unknown:
                return CapabilityOutcome(
                    handled=False,
                    reason=f"file(s) not in the parsed graph: {', '.join(unknown)}",
                )
        if not scope:
            return CapabilityOutcome(handled=False, reason="empty file set — nothing to decompose")

        # Kahn layering over the induced subgraph: each round's zero-
        # in-degree set is one packet; a round that empties nothing but
        # leaves nodes means a cycle inside the scope.
        remaining = set(scope)
        packets: list[list[str]] = []
        while remaining:
            ready = sorted(
                file
                for file in remaining
                if not (graph.edges.get(file, set()) & remaining)
            )
            if not ready:
                cycle = ", ".join(sorted(remaining))
                return CapabilityOutcome(
                    handled=False,
                    reason=f"dependency cycle or mutual ambiguity inside the file set: {cycle} — "
                    f"no_deterministic_path (escalate only via the policy-named condition)",
                )
            packets.append(ready)
            remaining.difference_update(ready)

        packet_of = {file: index for index, files in enumerate(packets) for file in files}
        result_packets: list[dict[str, Any]] = []
        for index, files in enumerate(packets):
            depends_on = sorted(
                {
                    packet_of[target]
                    for file in files
                    for target in graph.edges.get(file, set())
                    if target in packet_of and packet_of[target] < index
                }
            )
            result_packets.append({"index": index, "files": files, "depends_on": depends_on})

        return CapabilityOutcome(
            handled=True,
            result={"packets": result_packets, "packet_count": len(result_packets)},
            reason=f"decomposed into {len(result_packets)} dependency-first packet(s) (FR-M33-02)",
        )
