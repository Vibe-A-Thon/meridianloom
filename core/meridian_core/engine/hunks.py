"""Hunk-only large-file editing with generated-file exclusion (FR-M28-05,
FR-M28-07; FR-M33-02).

FR-M28-05: an edit to a large file is hunk-scoped. The file streams line by
line source → temp file; the only lines held in memory at once are the
current hunk's match block (its context plus the lines it removes) — never
the whole file. Hunks match in payload order, scanning forward, first exact
match wins (deterministic, replay-identical).

FR-M28-07: generated files are refused with the path named, before any byte
of the edit is attempted. The exclusion list below is the conservative
default (lockfiles, generated protobuf / graphql outputs, minified bundles);
a payload may EXTEND it via ``generated_patterns`` but never shrink it —
removing an exclusion is a reviewed policy change, not a runtime option.
Binary files (NUL in the first chunk) are refused too.

Atomicity: the edit writes a temp file in the same directory and
``os.replace``s it into place only when EVERY hunk matched. A mismatch is a
refusal naming the hunk — the original file is byte-for-byte untouched.

Zero model calls: streaming text processing only.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .capabilities import CapabilityOutcome

__all__ = ["HunkEditCapability", "GENERATED_PATTERNS"]

_CAPABILITY_NAME = "hunk_edit"

#: FR-M28-07 default exclusion list — lockfiles, generated protobuf /
#: graphql outputs, minified bundles. Matched against the basename and the
#: posix path. Conservative on purpose: an entry here is a reviewed
#: artefact; extend only with the same care as a policy change.
GENERATED_PATTERNS: tuple[str, ...] = (
    # lockfiles / dependency snapshots
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    # generated protobuf outputs
    "*.pb.go",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.pb.cc",
    "*.pb.h",
    # generated graphql outputs
    "*.graphqls.go",
    "*.graphql.ts",
    "*.graphql.js",
    # minified / bundled artefacts
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.bundle.css",
)

_BINARY_PROBE_BYTES = 8192


class HunkMismatch(Exception):
    """A hunk matched nowhere; names the payload index and the block."""

    def __init__(self, index: int, block: tuple[str, ...]):
        self.index = index
        self.block = block
        super().__init__(
            f"hunks[{index}] ({block[0].rstrip()!r}…, {len(block)} line(s)) matched nowhere"
        )


@dataclass(frozen=True)
class _Hunk:
    """One edit: ``old_block`` (context + lines to remove, contiguous) must
    appear in the file in payload order; it is replaced by ``new_block``
    (context + lines to add). Context lines pass through unchanged."""

    old_block: tuple[str, ...]
    new_block: tuple[str, ...]


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(_BINARY_PROBE_BYTES)
    except OSError:
        return False


def _generated_match(path: Path, patterns: tuple[str, ...]) -> str | None:
    basename = path.name
    posix = path.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatchcase(basename, pattern) or fnmatch.fnmatchcase(posix, pattern):
            return pattern
    return None


def _apply_streaming(
    source, target, hunks: list[_Hunk]
) -> tuple[list[dict[str, Any]], int]:
    """Stream source → target applying hunks in order. Only the current
    hunk's match block is buffered; everything else passes through as read.
    Returns ``(report, window_lines)`` — ``window_lines`` is the peak number
    of file lines held in memory at once, the FR-M28-05 hunk-scoping
    evidence. Raises ``HunkMismatch`` when a hunk matches nowhere; the
    caller then discards the unfinished temp file."""
    report: list[dict[str, Any]] = []
    pending = deque(hunks)
    buffer: deque[str] = deque()  # lookahead, at most one match block deep
    buffer_line = 0  # 0-based line number of buffer[0] in the source file
    window_lines = 0  # peak buffer depth

    def fill(want: int) -> None:
        while len(buffer) < want:
            line = source.readline()
            if line == "":
                break
            buffer.append(line)
        nonlocal window_lines
        window_lines = max(window_lines, len(buffer))

    while pending:
        hunk = pending[0]
        fill(len(hunk.old_block))
        if tuple(buffer) == hunk.old_block:
            for line in hunk.new_block:
                target.write(line)
            report.append(
                {"hunk_index": hunks.index(hunk), "matched_line": buffer_line + 1}
            )
            buffer_line += len(hunk.old_block)
            buffer.clear()
            pending.popleft()
        else:
            if len(buffer) < len(hunk.old_block):
                raise HunkMismatch(hunks.index(hunk), hunk.old_block)
            target.write(buffer.popleft())
            buffer_line += 1

    while True:
        if buffer:
            target.write(buffer.popleft())
            continue
        line = source.readline()
        if line == "":
            break
        target.write(line)
    return report, window_lines


class HunkEditCapability:
    """The ``hunk_edit`` capability, owned by the ``hunk_edit`` action class
    (FR-M33-01).

    Payload: ``{path, hunks: [{context: [...], old: [...], new: [...]}],
    generated_patterns?: [...]}``. The edit is atomic: every hunk matches or
    nothing is written.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        path = action.get("path")
        if not isinstance(path, str) or not path:
            return CapabilityOutcome(handled=False, reason="missing 'path'")
        raw_hunks = action.get("hunks")
        if (
            not isinstance(raw_hunks, list)
            or not raw_hunks
            or any(not isinstance(h, Mapping) for h in raw_hunks)
        ):
            return CapabilityOutcome(handled=False, reason="'hunks' must be a non-empty list")
        extra = action.get("generated_patterns", [])
        if not isinstance(extra, list) or any(not isinstance(p, str) for p in extra):
            return CapabilityOutcome(
                handled=False, reason="'generated_patterns' must be a list of strings"
            )
        patterns = GENERATED_PATTERNS + tuple(extra)

        target = Path(path)
        if not target.is_file():
            return CapabilityOutcome(handled=False, reason=f"not a file: {target}")
        hit = _generated_match(target, patterns)
        if hit is not None:
            return CapabilityOutcome(
                handled=False,
                reason=f"edit refused (FR-M28-07): {target} matches generated-file pattern "
                f"{hit!r} — generated files are never edited",
            )
        if _is_binary(target):
            return CapabilityOutcome(
                handled=False,
                reason=f"edit refused (FR-M28-07): {target} is a binary file — binary files "
                f"are never edited",
            )

        hunks: list[_Hunk] = []
        for index, raw in enumerate(raw_hunks):
            parts: dict[str, tuple[str, ...]] = {}
            for key in ("context", "old", "new"):
                value = raw.get(key)
                if not isinstance(value, list) or any(not isinstance(line, str) for line in value):
                    return CapabilityOutcome(
                        handled=False,
                        reason=f"hunks[{index}]: '{key}' must be a list of strings",
                    )
                parts[key] = tuple(value)
            if not parts["old"] and not parts["new"]:
                return CapabilityOutcome(
                    handled=False, reason=f"hunks[{index}]: 'old' and 'new' are both empty"
                )
            hunks.append(
                _Hunk(old_block=parts["context"] + parts["old"], new_block=parts["context"] + parts["new"])
            )

        temp_name: str | None = None
        try:
            with target.open("r", encoding="utf-8", newline="") as source:
                fd, temp_name = tempfile.mkstemp(
                    prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
                )
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
                    try:
                        report, window_lines = _apply_streaming(source, out, hunks)
                    except HunkMismatch as mismatch:
                        return CapabilityOutcome(
                            handled=False,
                            reason=f"edit refused: {target}: {mismatch} — no hunk of the "
                            f"edit was applied (file untouched)",
                        )
            os.replace(temp_name, target)
            temp_name = None
        except OSError as error:
            return CapabilityOutcome(handled=False, reason=f"cannot edit {target}: {error}")
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

        return CapabilityOutcome(
            handled=True,
            result={"path": str(target), "hunks_applied": report, "window_lines": window_lines},
            reason=f"hunk-scoped edit applied ({len(report)} hunk(s), peak window "
            f"{window_lines} lines — FR-M28-05)",
        )
