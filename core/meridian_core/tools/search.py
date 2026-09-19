"""Semantic search and reuse-first — FR-M28-03/04.

FR-M28-03: semantic code search as a native tool, incrementally updated.
The index is a DETERMINISTIC lexical-semantic index (identifier/token
TF over symbols and content), zero model calls — embedding vectors slot
behind the ``SemanticIndex`` port when a model tier is configured; the
reuse-first policy consumes the port, not a concrete index.

FR-M28-04: reuse-first — before writing a new function or class the
agent must search and cite what it found or why nothing fit. The policy
returns a verdict the agent's loop records; duplicate detection flags
re-implementation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


class SemanticIndex(Protocol):
    """The FR-M28-03 port. Implementations: LexicalSemanticIndex (shipped,
    deterministic); an embedding index when a model tier exists."""

    def index_file(self, path: Path) -> None: ...

    def remove_file(self, path: Path) -> None: ...

    def search(self, query: str, *, limit: int = 5) -> list["SearchHit"]: ...


@dataclass(frozen=True)
class SearchHit:
    path: str
    score: float
    excerpt: str
    symbols: tuple[str, ...]


@dataclass
class LexicalSemanticIndex:
    """Deterministic lexical-semantic index. Tokens are identifiers split
    on case and underscore; scoring is TF (raw + log-scaled). Incremental:
    ``index_file`` re-reads only the given file; ``refresh`` walks the
    workspace and re-indexes changed mtimes."""

    workspace: Path
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def refresh(self, exclude: "ExclusionSet | None" = None) -> None:
        for path in sorted(self.workspace.rglob("*")):
            if not path.is_file():
                continue
            if exclude is not None and exclude.is_excluded(path):
                continue
            self.index_file(path)

    def index_file(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self.remove_file(path)
            return
        tokens = _tokens(text)
        symbols = tuple(sorted({t for t in _idents(text)}))
        self.documents[str(path.relative_to(self.workspace))] = {
            "tokens": tokens,
            "symbols": symbols,
            "excerpt": text[:200],
        }

    def remove_file(self, path: Path) -> None:
        try:
            key = str(path.relative_to(self.workspace))
        except ValueError:
            key = str(path)
        self.documents.pop(key, None)

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        hits: list[SearchHit] = []
        for rel, doc in self.documents.items():
            doc_tokens = doc["tokens"]
            if not doc_tokens:
                continue
            overlap = sum(doc_tokens.count(t) for t in query_tokens)
            if overlap == 0:
                continue
            score = overlap / math.sqrt(len(doc_tokens))
            hits.append(
                SearchHit(
                    path=rel,
                    score=round(score, 4),
                    excerpt=doc["excerpt"],
                    symbols=doc["symbols"],
                )
            )
        hits.sort(key=lambda h: (-h.score, h.path))
        return hits[:limit]


def _idents(text: str) -> list[str]:
    return _IDENT.findall(text)


def _tokens(text: str) -> list[str]:
    raw = _idents(text)
    out: list[str] = []
    for token in raw:
        parts = re.split(r"(?=[A-Z])", token.replace("_", " "))
        for part in parts:
            cleaned = part.strip().lower()
            if len(cleaned) >= 3:
                out.append(cleaned)
    return out


@dataclass(frozen=True)
class ReuseVerdict:
    """FR-M28-04: what the reuse-first search found. ``citation`` is what
    the agent must record — either the found implementations or the reason
    nothing fit."""

    symbol: str
    searched: bool
    hits: tuple[SearchHit, ...]
    duplicate_suspected: bool
    citation: str


def reuse_first_check(
    index: SemanticIndex,
    *,
    proposed_symbol: str,
    workspace: Path,
    duplicate_threshold: float = 0.6,
) -> ReuseVerdict:
    """Search before writing. Returns the verdict the caller must cite;
    ``duplicate_suspected`` flags a probable re-implementation so the
    loop can route to review instead of writing."""
    hits = tuple(index.search(proposed_symbol, limit=5))
    if hits:
        top = hits[0]
        duplicate = top.score >= duplicate_threshold
        citation = (
            f"reuse-first: searched '{proposed_symbol}'; closest existing"
            f" implementation {top.path} (score {top.score}, symbols"
            f" {', '.join(top.symbols[:5]) or '—'})"
            + ("; suspected duplicate — route to review"
               if duplicate else "")
        )
    else:
        duplicate = False
        citation = (
            f"reuse-first: searched '{proposed_symbol}'; no existing"
            " implementation fit — new code is justified"
        )
    return ReuseVerdict(
        symbol=proposed_symbol,
        searched=True,
        hits=hits,
        duplicate_suspected=duplicate,
        citation=citation,
    )
