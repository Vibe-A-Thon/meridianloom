"""Instruction Library — FR-M7-14/15/16.

``AGENTS.md``, ``CONVENTIONS.md`` and any ``*.md`` under
``.meridian/instructions/`` or an adapter's ``instructions/`` are
first-class artifacts: discovered, versioned (content digest), diffable,
human-editable, and assembled into context by declared precedence —
adapter → workspace → user → organisation (FR-M7-14).

Trust is origin-based (FR-M7-16): files from the workspace, user, or
organisation tiers under version control are trusted; instruction-like
content found in repository or story text is untrusted (FR-M7-07) and is
NEVER discovered by this library.

Every invocation records the digest of each instruction file that
entered its context (FR-M7-15) — a behaviour change traces to an
instruction change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

TRUST_TIERS = ("adapter", "workspace", "user", "organisation")
REPOSITORY_TIER = "repository"  # discovered NEVER: untrusted by default

DISCOVERY_NAMES = ("AGENTS.md", "CONVENTIONS.md")


@dataclass(frozen=True)
class InstructionFile:
    """One instruction artifact."""

    path: Path
    tier: str  # adapter|workspace|user|organisation
    digest: str
    trusted: bool

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "tier": self.tier,
            "digest": self.digest,
            "trusted": self.trusted,
        }


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstructionLibrary:
    """Discovery + precedence assembly over explicit roots."""

    def __init__(
        self,
        *,
        adapter_dirs: Sequence[Path] = (),
        workspace: Path | None = None,
        user_dir: Path | None = None,
        organisation_dir: Path | None = None,
        ledger: Any = None,
    ) -> None:
        self._roots = {
            "adapter": tuple(adapter_dirs),
            "workspace": (workspace,) if workspace else (),
            "user": (user_dir,) if user_dir else (),
            "organisation": (organisation_dir,) if organisation_dir else (),
        }
        self._ledger = ledger

    def discover(self) -> list[InstructionFile]:
        """All instruction files, ordered by precedence (adapter first)."""
        found: list[InstructionFile] = []
        for tier in TRUST_TIERS:
            for root in self._roots[tier]:
                if root is None or not root.is_dir():
                    continue
                for name in DISCOVERY_NAMES:
                    candidate = root / name
                    if candidate.is_file():
                        found.append(self._file(candidate, tier))
                instructions_dir = root / "instructions"
                if instructions_dir.is_dir():
                    for path in sorted(instructions_dir.rglob("*.md")):
                        found.append(self._file(path, tier))
        return found

    @staticmethod
    def _file(path: Path, tier: str) -> InstructionFile:
        return InstructionFile(
            path=path,
            tier=tier,
            digest=digest_of(path),
            trusted=True,  # only trusted tiers are ever discovered
        )

    def assemble(
        self,
        *,
        agent_id: str,
        budget_chars: int,
    ) -> "InstructionContext":
        """FR-M7-14/15: fill the budget by precedence; record every
        included file's digest in the ledger so a behaviour change traces
        to an instruction change."""
        included: list[InstructionFile] = []
        cut: list[str] = []
        used = 0
        for instruction in self.discover():
            size = len(instruction.read())
            if used + size <= budget_chars:
                included.append(instruction)
                used += size
            else:
                cut.append(str(instruction.path))
        if self._ledger is not None:
            self._ledger.append(
                {
                    "story_id": "instruction-context",
                    "phase": "intake",
                    "loop_id": "instructions",
                    "loop_iteration": 1,
                    "actor_id": agent_id,
                    "actor_version": "instructions/v1",
                    "actor_kind": "role",
                    "policy_version": "instructions/v1",
                    "action_type": "prompt",
                    "input": json.dumps(
                        {
                            "instructionDigests": [
                                {"path": str(i.path), "digest": i.digest}
                                for i in included
                            ],
                            "cut": cut,
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return InstructionContext(agent_id, budget_chars, tuple(included), tuple(cut))

    def diff(self, other: "InstructionLibrary") -> dict[str, Any]:
        """FR-M7-14: two libraries are diffable — same path, digest moved."""
        mine = {str(f.path): f.digest for f in self.discover()}
        theirs = {str(f.path): f.digest for f in other.discover()}
        changed = sorted(p for p in mine if p in theirs and mine[p] != theirs[p])
        removed = sorted(set(mine) - set(theirs))
        added = sorted(set(theirs) - set(mine))
        return {"changed": changed, "added": added, "removed": removed}


@dataclass(frozen=True)
class InstructionContext:
    agent_id: str
    budget_chars: int
    included: tuple[InstructionFile, ...]
    cut: tuple[str, ...]

    def combined_text(self) -> str:
        return "\n\n".join(f.read() for f in self.included)
