"""Unified diff production and deterministic patch application (FR-M33-02).

Two pure functions over text, exposed as one capability:

* ``diff`` — produce a unified diff with ``difflib``. Output is
  replay-identical for identical inputs: fixed ``a/`` ``b/`` labels from the
  payload, no timestamps.
* ``apply`` — apply a unified diff to text. Hunks apply in order against the
  original line numbering, each located by exact context match starting at
  its header position plus the running offset from hunks already applied,
  then an expanding ±1, ±2, … deterministic scan. A hunk that matches
  nowhere is a REJECTION: it lands in ``result["rejected"]`` named by its
  ``@@ -a,b +c,d @@`` header and the reason — hunks are never silently
  dropped, and applied hunks are listed too, so the caller can see exactly
  what took effect (FR-M25-04's engine-side half).

Zero model calls: text in, text out.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .capabilities import CapabilityOutcome

__all__ = ["DiffPatchCapability", "parse_patch", "apply_patch", "unified_diff"]

_CAPABILITY_NAME = "diff_patch"

#: One hunk header: @@ -old_start[,old_count] +new_start[,new_count] @@
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\s*$")


@dataclass(frozen=True)
class Hunk:
    """One parsed hunk. ``old_block`` is what must match the target text
    (context + removal lines, contiguous); ``new_block`` is what replaces
    it (context + addition lines)."""

    old_start: int  # 1-based, as in the header
    old_count: int
    new_start: int
    new_count: int
    old_block: tuple[str, ...]
    new_block: tuple[str, ...]

    @property
    def header(self) -> str:
        return (
            f"@@ -{self.old_start},{self.old_count} "
            f"+{self.new_start},{self.new_count} @@"
        )


def unified_diff(
    old_text: str,
    new_text: str,
    from_label: str = "a",
    to_label: str = "b",
    context: int = 3,
) -> str:
    """A unified diff string, deterministic for identical inputs."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{from_label}", tofile=f"b/{to_label}", n=context
    )
    return "".join(diff)


def parse_patch(patch_text: str) -> list[Hunk]:
    """Parse the hunks of a unified diff. Raises ``ValueError`` naming the
    offending line on malformed input — never a silent partial parse."""
    lines = patch_text.splitlines(keepends=True)
    # Skip the --- / +++ file headers when present.
    start = 0
    if lines and (lines[0].startswith("---") or lines[0].startswith("diff ")):
        start = 1
        if len(lines) > 1 and lines[1].startswith("+++"):
            start = 2

    hunks: list[Hunk] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if line.strip() == "" or line.startswith("\\"):
            index += 1
            continue
        match = _HUNK_RE.match(line.rstrip("\n"))
        if match is None:
            raise ValueError(f"malformed patch at line {index + 1}: {line.rstrip()!r}")
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        old_block: list[str] = []
        new_block: list[str] = []
        body = 0
        index += 1
        while index < len(lines) and body < old_count + new_count:
            body_line = lines[index]
            if body_line.startswith("---") and index + 1 < len(lines):
                break  # next file's header without a blank separator
            tag = body_line[:1]
            payload = body_line[1:]
            if tag == " ":
                old_block.append(payload)
                new_block.append(payload)
                body += 2
            elif tag == "-":
                old_block.append(payload)
                body += 1
            elif tag == "+":
                new_block.append(payload)
                body += 1
            elif body_line.startswith("\\"):
                pass  # "\ No newline at end of file" — informational
            else:
                raise ValueError(
                    f"malformed hunk {line.rstrip()!r} at patch line {index + 1}: "
                    f"expected ' ', '-', '+' or '\\', got {body_line.rstrip()!r}"
                )
            index += 1
        if body != old_count + new_count:
            raise ValueError(
                f"hunk {line.rstrip()!r} declares {old_count + new_count} body lines, found {body}"
            )
        hunks.append(
            Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                old_block=tuple(old_block),
                new_block=tuple(new_block),
            )
        )
    return hunks


def _matches(text_lines: list[str], block: tuple[str, ...], position: int) -> bool:
    if position < 0 or position + len(block) > len(text_lines):
        return False
    return tuple(text_lines[position : position + len(block)]) == block


def _locate(text_lines: list[str], block: tuple[str, ...], expected: int) -> int | None:
    """First matching position in deterministic order: expected, then an
    expanding alternating scan (+1, -1, +2, -2, …) within bounds."""
    if _matches(text_lines, block, expected):
        return expected
    for offset in range(1, len(text_lines) + 1):
        for candidate in (expected + offset, expected - offset):
            if _matches(text_lines, block, candidate):
                return candidate
    return None


def apply_patch(
    old_text: str, patch_text: str
) -> tuple[str, list[str], list[dict[str, str]]]:
    """Apply ``patch_text`` to ``old_text``.

    Returns ``(new_text, applied_headers, rejected)`` where ``rejected``
    names every hunk that failed and why. Applied hunks shift the line
    numbering for later hunks via the running offset; a rejection does not.
    """
    hunks = parse_patch(patch_text)
    text_lines = old_text.splitlines(keepends=True)
    offset = 0
    applied: list[str] = []
    rejected: list[dict[str, str]] = []
    for hunk in hunks:
        expected = hunk.old_start - 1 + offset
        position = _locate(text_lines, hunk.old_block, expected)
        if position is None:
            rejected.append(
                {
                    "hunk": hunk.header,
                    "reason": f"context mismatch: hunk does not match at expected line "
                    f"{hunk.old_start + offset} (searched the whole file)",
                }
            )
            continue
        text_lines[position : position + len(hunk.old_block)] = list(hunk.new_block)
        offset += len(hunk.new_block) - len(hunk.old_block)
        applied.append(hunk.header)
    return "".join(text_lines), applied, rejected


class DiffPatchCapability:
    """The ``diff_patch`` capability, owned by the ``apply_patch`` action
    class (FR-M33-01).

    Payload (op ``diff``): ``{op, old_text, new_text, from_label?, to_label?,
    context?}`` → ``{diff}``.
    Payload (op ``apply``): ``{op, old_text, patch}`` → ``{text, applied,
    rejected}``.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        op = action.get("op")
        if op == "diff":
            return self._diff(action)
        if op == "apply":
            return self._apply(action)
        return CapabilityOutcome(handled=False, reason=f"missing or unknown 'op': {op!r}")

    def _diff(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        old_text = action.get("old_text")
        new_text = action.get("new_text")
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            return CapabilityOutcome(handled=False, reason="'old_text' and 'new_text' must be strings")
        context = action.get("context", 3)
        if not isinstance(context, int) or isinstance(context, bool) or context < 0:
            return CapabilityOutcome(handled=False, reason="'context' must be a non-negative integer")
        from_label = action.get("from_label", "a")
        to_label = action.get("to_label", "b")
        if not isinstance(from_label, str) or not isinstance(to_label, str):
            return CapabilityOutcome(handled=False, reason="labels must be strings")
        return CapabilityOutcome(
            handled=True,
            result={
                "diff": unified_diff(
                    old_text, new_text, from_label=from_label, to_label=to_label, context=context
                )
            },
            reason="unified diff produced (FR-M33-02)",
        )

    def _apply(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        old_text = action.get("old_text")
        patch = action.get("patch")
        if not isinstance(old_text, str) or not isinstance(patch, str):
            return CapabilityOutcome(handled=False, reason="'old_text' and 'patch' must be strings")
        try:
            text, applied, rejected = apply_patch(old_text, patch)
        except ValueError as error:
            return CapabilityOutcome(handled=False, reason=f"invalid patch: {error}")
        result: dict[str, Any] = {"text": text, "applied": applied, "rejected": rejected}
        if rejected:
            result["complete"] = False
            return CapabilityOutcome(
                handled=True,
                result=result,
                reason=f"{len(rejected)} hunk(s) rejected, named in result — none silently dropped",
            )
        result["complete"] = True
        return CapabilityOutcome(handled=True, result=result, reason="patch applied in full")
