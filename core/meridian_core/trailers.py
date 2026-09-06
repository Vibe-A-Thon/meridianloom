"""Git trailer parsing and trailer-block-aware editing (FR-M36-03).

Single ownership of trailer mechanics for the whole sidecar: the commit-msg
hook (F0 Workstream E task 23), the agent-identity trailer parsing (task 24)
and the Claude observer's trailer evidence tier all consume this module so
trailer semantics never diverge.

A *trailer* is one ``Key: value`` line; the *trailer block* is the last
paragraph of a message in which every non-comment line is a trailer, matching
``git interpret-trailers`` semantics. Comments (``#`` lines, as produced by
``git commit --verbose`` or ``#时请…`` commentChar aside) are transparent to
block detection and are always left untouched.
"""

from __future__ import annotations

import re

#: One trailer line: a token of alphanumerics and dashes, colon, space, value.
TRAILER_LINE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*):[ \t](.*)$")

MERIDIAN_LEDGER_KEY = "Meridian-Ledger"
CO_AUTHORED_BY_KEY = "Co-Authored-By"


def is_comment(line: str, comment_char: str = "#") -> bool:
    return line.lstrip().startswith(comment_char)


def parse_trailer_line(line: str) -> tuple[str, str] | None:
    """Return (key, value) when ``line`` is a trailer, else None."""
    match = TRAILER_LINE_RE.match(line)
    if match is None:
        return None
    return match.group(1), match.group(2).strip()


def parse_trailers(message: str) -> list[tuple[str, str]]:
    """Every trailer line in ``message`` (any paragraph), in order."""
    found: list[tuple[str, str]] = []
    for line in message.splitlines():
        parsed = parse_trailer_line(line)
        if parsed is not None:
            found.append(parsed)
    return found


def has_trailer(message: str, key: str) -> bool:
    return any(k == key for k, _value in parse_trailers(message))


def _trailer_block_span(lines: list[str]) -> tuple[int, int] | None:
    """(start, end_exclusive) line span of the trailer block, or None.

    Walks backwards from the last line over blanks, comments and trailer
    lines; the block is the trailing run of trailer lines inside that region.
    Returns None when the region holds no trailer line — the message has no
    trailer block yet.
    """
    end = len(lines)
    # Trim trailing blank lines.
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    # Walk backwards over blanks/comments/trailer lines to find the region.
    region_start = end
    while region_start > 0:
        line = lines[region_start - 1]
        if not line.strip() or is_comment(line) or parse_trailer_line(line):
            region_start -= 1
        else:
            break
    block_start = region_start
    while block_start < end and parse_trailer_line(lines[block_start]) is None:
        block_start += 1
    if block_start >= end:
        return None
    return block_start, end


def append_trailer(message: str, key: str, value: str) -> str:
    """Return ``message`` with ``Key: value`` added to the trailer block.

    Trailer-block aware: joins an existing block (so a message that already
    carries, e.g., ``Co-Authored-By`` keeps one trailer paragraph), never
    touches comment lines, and never duplicates — when the key is already
    present the message is returned unchanged (the commit-msg hook relies on
    this for idempotency).
    """
    if has_trailer(message, key):
        return message
    lines = message.split("\n")
    span = _trailer_block_span(lines)
    trailer_line = f"{key}: {value}"
    if span is not None:
        start, end = span
        lines.insert(end, trailer_line)
        return "\n".join(lines)
    # No trailer block: append at the very end (after any trailing comment
    # lines, which git strips before the message is finalised). A blank line
    # separates the body from the new trailer block.
    body_end = len(lines)
    while body_end > 0 and not lines[body_end - 1].strip():
        body_end -= 1
    del lines[body_end:]
    if any(line.strip() for line in lines):
        lines.append("")
    lines.append(trailer_line)
    return "\n".join(lines)
