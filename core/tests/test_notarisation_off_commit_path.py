"""Notarisation is not on the commit path — `NFR-47` (M52, MV3-T06).

`NFR-47` says digesting a third-party provenance record adds no measurable
delay to a commit. Notarisation was built to run only when somebody asks for
it (`interop/notarise`), so the requirement holds by construction — and "by
construction" is exactly the kind of statement this repository has learned to
distrust until something checks it. The provenance hook is one import away
from putting a network of git subprocess calls in front of every commit.

So this is a guard, in the style of the spawn and initiation guards: an AST
walk of every module the commit-msg hook can import, transitively, asserting
that neither the notarisation module nor the server that loads it is among
them. A timing assertion would be weaker: it measures one machine on one day
and passes on a slow path that happens to be fast today. Unreachable is not a
number that drifts.

The guard comes with its own negative control, and with a check that the walk
is not vacuously empty — a closure of nothing would pass on a guard that had
stopped reading imports at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import meridian_core

PACKAGE = Path(meridian_core.__file__).parent

#: The script git runs on every commit (FR-M36-03).
COMMIT_PATH_ENTRY = "meridian_core.hooks"

#: Modules whose presence on the commit path would put notarisation there.
#: The server is listed because it imports `interop` at module level: reaching
#: the server reaches notarisation, however indirectly.
MUST_NOT_REACH = {"meridian_core.interop", "meridian_core.server"}


def _module_file(root: Path, dotted: str) -> Path | None:
    """The source file for `dotted` under `root`, package or module."""
    relative = Path(*dotted.split("."))
    for candidate in (root / relative.with_suffix(".py"), root / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(root: Path, dotted: str, source: Path) -> set[str]:
    """Every in-package module this file imports, anywhere in the file.

    Anywhere, not only at module level: a lazy import inside a function still
    runs on the commit path the moment that function does, and a guard that
    only read the top of the file would miss exactly the import most likely to
    be added later "just for this one case".
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    is_package = source.name == "__init__.py"
    package_parts = dotted.split(".") if is_package else dotted.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "meridian_core":
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module.split(".")[0] != "meridian_core":
                continue
            found.add(module)
            # `from meridian_core import trailers` imports a submodule by name.
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                if _module_file(root, candidate) is not None:
                    found.add(candidate)
    return found


def commit_path_closure(root: Path, entry: str) -> set[str]:
    """Every in-package module reachable from `entry`, including the parent
    packages whose `__init__` runs when a submodule is imported."""
    seen: set[str] = set()
    pending = [entry]
    while pending:
        dotted = pending.pop()
        parts = dotted.split(".")
        for depth in range(1, len(parts) + 1):
            name = ".".join(parts[:depth])
            if name in seen:
                continue
            source = _module_file(root, name)
            if source is None:
                continue
            seen.add(name)
            pending.extend(_imports(root, name, source) - seen)
    return seen


def test_the_commit_hook_never_reaches_notarisation():
    reached = commit_path_closure(PACKAGE.parent, COMMIT_PATH_ENTRY) & MUST_NOT_REACH
    assert not reached, (
        f"the commit-msg hook can import {sorted(reached)}. NFR-47: digesting a "
        "third-party provenance record must add no delay to a commit, and the "
        "only way to guarantee that is for notarisation to be unreachable from "
        "the hook. Notarise on request (interop/notarise), never on commit."
    )


def test_the_walk_actually_reads_the_hook_s_imports():
    # A closure of nothing would satisfy the guard above for the wrong reason.
    reached = commit_path_closure(PACKAGE.parent, COMMIT_PATH_ENTRY)
    assert COMMIT_PATH_ENTRY in reached
    assert "meridian_core.trailers" in reached
    assert "meridian_core.gitcmd" in reached


def test_the_guard_detects_notarisation_put_on_the_commit_path(tmp_path):
    """A guard that cannot fail proves nothing — so make it fail once.

    Planted in a tmp tree rather than in the package, because other guards
    walk the package concurrently under `-n auto` and a probe that appears and
    vanishes there makes an unrelated test flaky.
    """
    fake = tmp_path / "meridian_core"
    fake.mkdir()
    (fake / "__init__.py").write_text("", encoding="utf-8")
    (fake / "helpers.py").write_text(
        "def notarise_on_commit():\n"
        "    from meridian_core import interop\n"
        "    return interop\n",
        encoding="utf-8",
    )
    (fake / "hooks.py").write_text(
        "from meridian_core import helpers\n", encoding="utf-8"
    )
    (fake / "interop.py").write_text("", encoding="utf-8")
    reached = commit_path_closure(tmp_path, COMMIT_PATH_ENTRY)
    assert "meridian_core.interop" in reached, (
        "the guard did not follow a lazy import two modules deep; it would not "
        "have noticed a real one either"
    )
