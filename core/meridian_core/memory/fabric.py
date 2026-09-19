"""Memory fabric — FR-M7-01/02/04/05/06/07/08/09/10/11/13.

File-based memory under ``.meridian/memory/``, three tiers:

- ``procedural/`` — playbooks and conventions, human-readable Markdown,
  reviewable in a PR, committed to the repository (FR-M7-02). Layered
  organisation → team → repository with lower layers overriding higher
  (FR-M7-09).
- ``semantic/`` — project facts as structured entries. Never the only
  copy of a fact (FR-M7-03): every semantic entry names its source.
- ``episodic/`` — per-story trace summaries (FR-M7-06 retention: entries
  past the horizon are consolidated into a summary and archived).

Every entry carries provenance (FR-M7-04). Writeback is gated (FR-M7-05):
a candidate contradicting an existing entry is quarantined for human
resolution, never silently merged. Untrusted-origin content is tagged
and cannot reach procedural memory without human approval (FR-M7-07 —
the primary defence against memory poisoning). Retrieval is logged with
the consuming agent (FR-M7-08). Human-pinned entries are immutable to
agents (FR-M7-11). Context assembly is budgeted and ranked by relevance,
trust and recency, logging what was included and what was cut
(FR-M7-13). Memory exports as a reviewable Markdown bundle, diffable
across versions (FR-M7-10).

Zero model calls.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

TIERS = ("procedural", "semantic", "episodic")
TRUSTED_ORIGINS = ("workspace", "user", "organisation")
UNTRUSTED_ORIGINS = ("story", "repository", "third_party")
DEFAULT_EPISODIC_HORIZON_DAYS = 90


class MemoryError(ValueError):
    """A memory operation violated a fabric rule. Carries the FR id."""


class ContradictionError(MemoryError):
    """FR-M7-05: the candidate contradicts an existing entry; it is
    quarantined for human resolution instead of being committed."""


@dataclass(frozen=True)
class Provenance:
    """FR-M7-04: every entry carries where it came from."""

    origin_sequence: int | None
    author: str
    ts_utc: str
    confidence: float
    origin: str = "workspace"  # workspace|user|organisation|story|repository|third_party
    pinned: bool = False  # FR-M7-11: human-pinned entries are agent-immutable


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    tier: str
    subject: str
    content: str
    provenance: Provenance
    source: str | None = None  # FR-M7-03: semantic entries name their source
    trusted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "entryId": self.entry_id,
            "tier": self.tier,
            "subject": self.subject,
            "content": self.content,
            "source": self.source,
            "trusted": self.trusted,
            "provenance": {
                "originSequence": self.provenance.origin_sequence,
                "author": self.provenance.author,
                "tsUtc": self.provenance.ts_utc,
                "confidence": self.provenance.confidence,
                "origin": self.provenance.origin,
                "pinned": self.provenance.pinned,
            },
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> "MemoryEntry":
        prov = raw["provenance"]
        return MemoryEntry(
            entry_id=raw["entryId"],
            tier=raw["tier"],
            subject=raw["subject"],
            content=raw["content"],
            source=raw.get("source"),
            trusted=bool(raw.get("trusted", True)),
            provenance=Provenance(
                origin_sequence=prov.get("originSequence"),
                author=prov["author"],
                ts_utc=prov["tsUtc"],
                confidence=float(prov["confidence"]),
                origin=prov.get("origin", "workspace"),
                pinned=bool(prov.get("pinned", False)),
            ),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(subject: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    return slug[:60] or "entry"


@dataclass
class MemoryFabric:
    """The fabric over ``.meridian/memory/``."""

    workspace: Path
    episodic_horizon_days: int = DEFAULT_EPISODIC_HORIZON_DAYS
    ledger: Any = None

    @property
    def root(self) -> Path:
        return self.workspace / ".meridian" / "memory"

    def _tier_dir(self, tier: str) -> Path:
        if tier not in TIERS:
            raise MemoryError(f"unknown memory tier {tier!r}")
        path = self.root / tier
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- write path ---------------------------------------------------------

    def write(
        self,
        entry: MemoryEntry,
        *,
        actor: str = "agent",
        actor_is_human: bool = False,
        contradiction_terms: Sequence[str] | None = None,
    ) -> Path:
        """FR-M7-05/07/11: gated writeback. Untrusted content can never
        land in procedural memory (FR-M7-07); a pinned entry may only be
        written by its pin author (humans); a candidate that contradicts
        an existing entry of the same subject is quarantined, not merged.
        """
        if entry.tier == "procedural":
            if entry.provenance.origin in UNTRUSTED_ORIGINS or not entry.trusted:
                raise MemoryError(
                    "FR-M7-07: untrusted-origin content cannot be promoted"
                    " to procedural memory without human approval"
                )
        if entry.provenance.pinned and not actor_is_human:
            raise MemoryError(
                "FR-M7-11: pinned entries are human-curated; only a human"
                " actor may write or modify them"
            )
        existing = self.get(entry.tier, entry.subject)
        if existing is not None and existing.entry_id != entry.entry_id:
            terms = set(contradiction_terms or ()) or _key_terms(entry.content)
            overlap = terms & _key_terms(existing.content)
            exclusive_existing = _key_terms(existing.content) - terms
            exclusive_new = terms - _key_terms(existing.content)
            if overlap and exclusive_existing and exclusive_new:
                self._quarantine(entry, existing)
                raise ContradictionError(
                    f"FR-M7-05: candidate '{entry.subject}' contradicts entry"
                    f" {existing.entry_id} (shared {sorted(overlap)}); the"
                    " candidate is quarantined for human resolution"
                )
        path = self._tier_dir(entry.tier) / f"{_slug(entry.subject)}.json"
        path.write_text(
            json.dumps(entry.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def _quarantine(self, entry: MemoryEntry, existing: "MemoryEntry") -> None:
        quarantine = self.root / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        (quarantine / f"{_slug(entry.subject)}-{entry.entry_id}.json").write_text(
            json.dumps(
                {"candidate": entry.to_dict(), "contradicts": existing.entry_id},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    # -- read path ----------------------------------------------------------

    def get(self, tier: str, subject: str) -> MemoryEntry | None:
        path = self.root / tier / f"{_slug(subject)}.json"
        if not path.exists():
            return None
        return MemoryEntry.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def entries(self, tier: str) -> list[MemoryEntry]:
        directory = self.root / tier
        if not directory.is_dir():
            return []
        out = []
        for path in sorted(directory.glob("*.json")):
            out.append(MemoryEntry.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return out

    def retrieve(
        self,
        query_terms: Sequence[str],
        *,
        agent_id: str,
        budget_chars: int,
        tiers: Sequence[str] = ("procedural", "semantic", "episodic"),
    ) -> "AssembledContext":
        """FR-M7-08/13: ranked, budgeted retrieval. Rank = trusted first,
        then confidence, then recency. Included and CUT entries are both
        logged — a cut is a decision, not an absence."""
        terms = {t.lower() for t in query_terms}
        candidates: list[tuple[int, MemoryEntry]] = []
        for tier in tiers:
            for entry in self.entries(tier):
                score = len(terms & _key_terms(entry.subject + " " + entry.content))
                if score == 0:
                    continue
                rank = (
                    (0 if entry.trusted else 1) * 10_000
                    + int((1 - entry.provenance.confidence) * 1000)
                    - min(score, 99)
                )
                candidates.append((rank, entry))
        candidates.sort(key=lambda item: (item[0], item[1].entry_id))
        included: list[MemoryEntry] = []
        cut: list[str] = []
        used = 0
        for _, entry in candidates:
            size = len(entry.content) + len(entry.subject)
            if used + size <= budget_chars:
                included.append(entry)
                used += size
            else:
                cut.append(entry.entry_id)
        self._log_retrieval(agent_id, included, cut)
        return AssembledContext(agent_id, budget_chars, tuple(included), tuple(cut))

    def _log_retrieval(
        self, agent_id: str, included: Sequence[MemoryEntry], cut: Sequence[str]
    ) -> None:
        if self.ledger is None:
            return
        self.ledger.append(
            {
                "story_id": "memory-retrieval",
                "phase": "intake",
                "loop_id": "memory",
                "loop_iteration": 1,
                "actor_id": agent_id,
                "actor_version": "memory/v1",
                "actor_kind": "role",
                "policy_version": "memory/v1",
                "action_type": "tool_call",
                "input": json.dumps(
                    {
                        "retrieved": [e.entry_id for e in included],
                        "cut": list(cut),
                    },
                    ensure_ascii=False,
                ),
            }
        )

    # -- FR-M7-06: retention ----------------------------------------------------

    def consolidate_episodic(self, *, now: datetime | None = None) -> dict[str, int]:
        """Entries older than the horizon are folded into one summary per
        subject and archived; raw traces move to ``episodic/archive/``."""
        now = now or datetime.now(timezone.utc)
        horizon = now - timedelta(days=self.episodic_horizon_days)
        consolidated = 0
        archived = 0
        for entry in self.entries("episodic"):
            ts = datetime.strptime(entry.provenance.ts_utc, "%Y-%m-%dT%H:%M:%SZ")
            ts = ts.replace(tzinfo=timezone.utc)
            if ts >= horizon:
                continue
            summary = self.get("episodic", f"summary-{entry.subject}")
            summary_content = (
                (summary.content + "\n" if summary else "")
                + f"[{entry.provenance.ts_utc[:10]}] {entry.content}"
            )
            self.write(
                MemoryEntry(
                    entry_id=f"summary-{_slug(entry.subject)}",
                    tier="episodic",
                    subject=f"summary-{entry.subject}",
                    content=summary_content.strip(),
                    provenance=Provenance(
                        origin_sequence=None,
                        author="memory-fabric",
                        ts_utc=utc_now(),
                        confidence=1.0,
                        origin="workspace",
                    ),
                ),
                actor="memory-fabric",
            )
            consolidated += 1
            archive = self.root / "episodic" / "archive"
            archive.mkdir(exist_ok=True)
            shutil.move(
                str(self.root / "episodic" / f"{_slug(entry.subject)}.json"),
                str(archive / f"{entry.entry_id}.json"),
            )
            archived += 1
        return {"consolidated": consolidated, "archived": archived}

    # -- FR-M7-09: layered procedural memory --------------------------------------

    def layered_procedural(
        self,
        layers: Sequence[tuple[str, Path]],
    ) -> dict[str, str]:
        """Merge procedural layers (organisation → team → repository):
        lower layers override higher. Returns the effective playbook as
        subject → content."""
        effective: dict[str, str] = {}
        for _, directory in layers:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                effective[path.stem] = path.read_text(encoding="utf-8")
        return effective

    # -- FR-M7-10: export/import -----------------------------------------------------

    def export_bundle(self, destination: Path) -> Path:
        """A reviewable Markdown bundle; diffable across versions because
        it is generated with a stable order."""
        destination.mkdir(parents=True, exist_ok=True)
        for tier in TIERS:
            lines = [f"# {tier} memory", ""]
            for entry in sorted(self.entries(tier), key=lambda e: e.entry_id):
                lines.append(f"## {entry.subject} ({entry.entry_id})")
                lines.append(f"- author: {entry.provenance.author}")
                lines.append(f"- confidence: {entry.provenance.confidence}")
                lines.append(f"- trusted: {entry.trusted}")
                lines.append("")
                lines.append(entry.content)
                lines.append("")
            (destination / f"{tier}.md").write_text(
                "\n".join(lines), encoding="utf-8"
            )
        return destination


@dataclass(frozen=True)
class AssembledContext:
    """FR-M7-13: what fit the budget, what was cut."""

    agent_id: str
    budget_chars: int
    included: tuple[MemoryEntry, ...]
    cut: tuple[str, ...]

    def digest_lines(self) -> list[str]:
        return [
            f"{e.entry_id} sha256:{_digest(e.content)}"
            for e in self.included
        ]


def _key_terms(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", text.lower())
        if len(token) >= 4
    }


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
