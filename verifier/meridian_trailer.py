#!/usr/bin/env python3
"""Reference parser for the ``Meridian-Ledger:`` commit trailer (FR-M43-11).

This is the whole of what a third party needs in order to go from a commit in
somebody else's repository to a verifiable range of ledger entries, without
Meridian installed and without trusting anything Meridian says about itself:

    git log -1 --format=%B <commit> | python meridian_trailer.py
    python meridian_trailer.py --message-file MSG --bundle bundle.json
    python verify.py bundle.json

The specification it implements is ``docs/spec/meridian-ledger-trailer.md``,
version 1. This file is the *reference* implementation of that document — if
the two ever disagree, the document is the specification and this is the bug.

Python standard library only, one file, no imports from Meridian. That is the
point: a claim that evidence outlives the tool is worth nothing if checking it
requires the tool (NFR-39, AC-49).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Iterable

#: The version of the trailer specification this parser implements. A parser
#: MUST refuse a trailer whose form it does not recognise rather than guess:
#: a future version may widen the grammar, and a silent misread of a range is
#: worse than a refusal to read it.
SPEC_VERSION = 1

#: The trailer key. Case-insensitive on read, per git's own trailer handling.
LEDGER_KEY = "Meridian-Ledger"

#: One trailer line: token, colon, single space or tab, value.
_TRAILER_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*):[ \t](.*)$")

#: A ledger range: one sequence, or two separated by a single hyphen.
_RANGE = re.compile(r"^([0-9]+)(?:-([0-9]+))?$")


class TrailerError(ValueError):
    """The trailer is present but does not conform to the specification."""


def parse_trailers(message: str) -> list[tuple[str, str]]:
    """Every trailer in a commit message, in order.

    Trailers are the lines of the **last** non-empty paragraph that all look
    like ``Key: value``. That is git's rule, and the reason it matters here is
    that a message body can legitimately contain a line such as
    ``Meridian-Ledger: see below`` in prose; only the final block is binding.
    """
    lines = message.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return []

    start = len(lines)
    while start > 0 and lines[start - 1].strip():
        start -= 1
    block = lines[start:]

    trailers: list[tuple[str, str]] = []
    for line in block:
        match = _TRAILER_LINE.match(line)
        if match is None:
            # A paragraph that is not entirely trailers is not a trailer
            # block. Git is stricter than "contains some colons", and so is
            # this: a prose paragraph ending in a URL must not become one.
            return []
        trailers.append((match.group(1), match.group(2).strip()))
    return trailers


def ledger_range(message: str) -> tuple[int, int] | None:
    """The ``(first, last)`` ledger sequences a commit claims, or ``None``.

    ``None`` means the commit carries no ledger trailer — an ordinary commit,
    which is not an error. A trailer that is present but malformed raises,
    because that is a claim this parser could not check and silently
    discarding it would report "no evidence" for a commit that asserted some.

    Both ends are inclusive. A single sequence is written bare and means the
    range ``(n, n)``.
    """
    found: str | None = None
    for key, value in parse_trailers(message):
        if key.lower() == LEDGER_KEY.lower():
            if found is not None and value != found:
                raise TrailerError(
                    f"conflicting {LEDGER_KEY} trailers: {found!r} and {value!r}"
                )
            found = value
    if found is None:
        return None

    match = _RANGE.match(found)
    if match is None:
        raise TrailerError(
            f"{LEDGER_KEY} value {found!r} is not a sequence or a "
            "hyphenated range of sequences (specification version "
            f"{SPEC_VERSION})"
        )
    first = int(match.group(1))
    last = int(match.group(2)) if match.group(2) is not None else first
    if first < 1:
        raise TrailerError(f"ledger sequences start at 1; got {first}")
    if last < first:
        raise TrailerError(f"range {found!r} ends before it starts")
    return first, last


def bundle_sequences(bundle: Any) -> set[int]:
    """Every entry sequence present in an exported bundle."""
    if not isinstance(bundle, dict):
        raise TrailerError("bundle is not a JSON object")
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        raise TrailerError("bundle has no entries array")
    sequences: set[int] = set()
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("sequence"), int):
            sequences.add(entry["sequence"])
    return sequences


def missing_from_bundle(bundle: Any, first: int, last: int) -> list[int]:
    """Which sequences of ``first..last`` the bundle does not contain.

    Returned rather than reduced to a boolean so the answer can say *which*
    entries are absent. "The bundle does not cover this commit" is a very
    different conversation from "entry 47 of 1..100 is missing".
    """
    present = bundle_sequences(bundle)
    return [sequence for sequence in range(first, last + 1) if sequence not in present]


# -- command line -------------------------------------------------------------

_USAGE = """\
usage: meridian_trailer.py [--message-file FILE] [--bundle FILE]

Reads a commit message on stdin, or from --message-file, and prints the
ledger range its Meridian-Ledger trailer claims:

    git log -1 --format=%B <commit> | python meridian_trailer.py

With --bundle, also checks that the bundle contains every entry in that
range, and exits non-zero if it does not. Verifying the bundle's signatures
and proofs is a separate step:

    python verify.py bundle.json

Exit status: 0 covered (or simply parsed), 1 not covered or malformed,
2 usage error. A commit with no trailer prints {"trailer": null} and exits 0 —
an ordinary commit is not a failure.
"""


def _read(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    message_file: str | None = None
    bundle_file: str | None = None
    index = 0
    while index < len(args):
        argument = args[index]
        if argument in ("-h", "--help"):
            sys.stdout.write(_USAGE)
            return 0
        if argument in ("--message-file", "--bundle"):
            index += 1
            if index >= len(args):
                sys.stderr.write(f"{argument} needs a file path\n{_USAGE}")
                return 2
            if argument == "--message-file":
                message_file = args[index]
            else:
                bundle_file = args[index]
        else:
            sys.stderr.write(f"unknown argument {argument!r}\n{_USAGE}")
            return 2
        index += 1

    try:
        claimed = ledger_range(_read(message_file))
    except TrailerError as error:
        sys.stderr.write(f"FAIL: {error}\n")
        return 1
    except OSError as error:
        sys.stderr.write(f"FAIL: cannot read the commit message: {error}\n")
        return 2

    report: dict[str, Any] = {"specVersion": SPEC_VERSION}
    if claimed is None:
        report["trailer"] = None
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0

    first, last = claimed
    report["trailer"] = {"from": first, "to": last, "count": last - first + 1}

    if bundle_file is not None:
        try:
            with open(bundle_file, "r", encoding="utf-8") as handle:
                bundle = json.load(handle)
            missing = missing_from_bundle(bundle, first, last)
        except (OSError, json.JSONDecodeError) as error:
            sys.stderr.write(f"FAIL: cannot read the bundle: {error}\n")
            return 2
        except TrailerError as error:
            sys.stderr.write(f"FAIL: {error}\n")
            return 1
        report["covered"] = not missing
        if missing:
            # Bounded: a bundle missing ten thousand entries should say so
            # without printing ten thousand numbers.
            report["missing"] = missing[:20]
            report["missingCount"] = len(missing)
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        if missing:
            sys.stderr.write(
                f"FAIL: the bundle does not contain {len(missing)} of the "
                f"{last - first + 1} entries this commit claims\n"
            )
            return 1
        sys.stderr.write(
            "OK: the bundle contains every entry this commit claims. "
            "Now verify the bundle itself: python verify.py <bundle>\n"
        )
        return 0

    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main(sys.argv[1:]))
