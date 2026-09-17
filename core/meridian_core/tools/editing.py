"""Hunk-based editing and binary/generated exclusion — FR-M28-05/07.

FR-M28-05: files above the configurable size are edited by targeted
hunk, never regenerated whole. ``apply_hunk`` replaces exactly one
anchored occurrence; whole-file writes through this module are refused
for oversized files.

FR-M28-07: binary and generated files (lockfiles, build outputs,
minified assets) are excluded from agent editing by default, with an
allow-list override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LARGE_FILE_BYTES = 100_000

#: FR-M28-07: excluded by default. The allow-list names paths (relative)
#: that may be edited despite matching.
DEFAULT_EXCLUDED_SUFFIXES = (
    ".lock", ".lockb", ".min.js", ".min.css", ".map", ".jar", ".war",
    ".class", ".pyc", ".pyo", ".dll", ".exe", ".so", ".dylib", ".zip",
    ".tar", ".gz", ".tgz", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".wasm",
)
DEFAULT_EXCLUDED_NAMES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "go.sum", "gemfile.lock",
    "gradlew", "gradlew.bat",
)


class EditRefusedError(ValueError):
    """An edit violated FR-M28-05 or FR-M28-07. Carries the requirement."""


@dataclass(frozen=True)
class ExclusionSet:
    """FR-M28-07: default exclusions plus an explicit allow-list."""

    workspace: Path
    allowlist: frozenset[str] = frozenset()
    max_edit_bytes: int = DEFAULT_LARGE_FILE_BYTES

    def is_excluded(self, path: Path) -> bool:
        rel = str(path.relative_to(self.workspace)) if path.is_absolute() else str(path)
        if rel in self.allowlist:
            return False
        name = path.name
        if name in DEFAULT_EXCLUDED_NAMES:
            return True
        return any(name.endswith(suffix) for suffix in DEFAULT_EXCLUDED_SUFFIXES)

    def assert_editable(self, path: Path) -> None:
        if self.is_excluded(path):
            raise EditRefusedError(
                f"FR-M28-07: {path.name} is a binary/generated file excluded"
                " from agent editing by default; add an explicit allow-list"
                " entry to override"
            )


@dataclass(frozen=True)
class Hunk:
    """One targeted edit: replace ``old`` with ``new`` at exactly one
    occurrence (the first). ``occurrence`` selects a later match when the
    anchor is genuinely repeated."""

    path: str
    old: str
    new: str
    occurrence: int = 1


def apply_hunk(workspace: Path, hunk: Hunk, exclusions: ExclusionSet) -> int:
    """FR-M28-05: apply one anchored hunk. Returns the line number of the
    replacement. Refuses whole-file semantics: the anchor must occur at
    least once, and the file must be editable and within the size cap for
    direct rewriting (the hunk replaces a bounded span, never regenerates
    the file)."""
    target = workspace / hunk.path
    exclusions.assert_editable(target)
    if not target.exists():
        raise EditRefusedError(f"FR-M28-05: {hunk.path} does not exist")
    # FR-M28-05: the hunk span is bounded BEFORE any anchor work — an
    # oversized span is refused regardless of whether the anchor matches.
    if len(hunk.old) > exclusions.max_edit_bytes:
        raise EditRefusedError(
            f"FR-M28-05: hunk span {len(hunk.old)} bytes exceeds the"
            f" {exclusions.max_edit_bytes}-byte targeted-edit cap on"
            f" {hunk.path}; split the edit"
        )
    text = target.read_text(encoding="utf-8", errors="strict")
    count = text.count(hunk.old)
    if count == 0:
        raise EditRefusedError(
            f"FR-M28-05: anchor not found in {hunk.path}; refusing to guess"
        )
    if hunk.occurrence > count:
        raise EditRefusedError(
            f"FR-M28-05: anchor occurrence {hunk.occurrence} exceeds the"
            f" {count} occurrences in {hunk.path}"
        )
    before, _, rest = text.partition(hunk.old)
    for _ in range(hunk.occurrence - 1):
        more, _, rest2 = rest.partition(hunk.old)
        before += hunk.old + more
        rest = rest2
    line_number = before.count("\n") + 1
    updated = before + hunk.new + rest
    target.write_text(updated, encoding="utf-8")
    return line_number
