"""Adversarial regression corpus — FR-M46-09/10, SEC-34 (N2 Workstream G
task 33).

Crafted inputs driven through the REAL controls (never mocks): the ledger's
append-only triggers and hash chain, blob redaction, privacy erasure,
tree-head signatures, the trailer parser, and interop notarisation.

Two surfaces, tested separately (FR-M46-10):

- ``hosted_execution`` — the path where Meridian executes or records work:
  every block must also produce a usable evidence record (a named refusal,
  a trigger ABORT, or a chain entry), never a silent failure.
- ``passive_observation`` — the path where Meridian verifies or observes:
  every detection must be a verdict a human can read, never a bare False.

Coverage limits (FR-M46-10, stated rather than implied): the corpus
exercises the surfaces above. It makes NO general-resistance claim — it
does not probe the extension host, the VS Code sandbox, network
adversaries, or physical access. "No known critical escape" is scoped to
these families and is a floor that grows by batches, not a ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SURFACE_HOSTED = "hosted_execution"
SURFACE_PASSIVE = "passive_observation"

KIND_BLOCKED = "blocked"  # the control refused before/at the effect
KIND_DETECTED = "detected"  # a tamper was detected after the fact
KIND_REDACTED = "redacted"  # sensitive content never persisted
KIND_RECORDED = "recorded"  # an evidence record exists


@dataclass(frozen=True)
class Fixture:
    """One adversarial case. ``fn`` receives a fresh tmp dir and must
    assert, inside itself, both the control behaviour and the evidence
    record — the harness fails any fixture that asserts only half."""

    id: str
    family: str
    surface: str
    kind: str
    description: str
    fn: Callable[[Path], None]


@dataclass(frozen=True)
class FixtureReport:
    id: str
    family: str
    surface: str
    kind: str
    description: str


def run_fixture(fixture: Fixture, tmp: Path) -> FixtureReport:
    fixture.fn(tmp)
    return FixtureReport(
        id=fixture.id,
        family=fixture.family,
        surface=fixture.surface,
        kind=fixture.kind,
        description=fixture.description,
    )
