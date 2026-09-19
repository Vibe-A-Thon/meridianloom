"""M38 Brownfield Comprehension — FR-M38-01…06, AC-35.

Before any agent modifies a module, Meridian produces a **comprehension
record** for it — deterministically, no model call (FR-M38-01): the
dependency/import graph, callers and callees, test coverage, change
frequency and authorship from git history, known incidents, and detected
conventions. The record feeds context assembly with precedence over
skill-pack defaults (FR-M38-02: repository reality outranks skill
defaults).

FR-M38-03: a brownfield risk score per packet from module age, coupling,
coverage, and change-failure history; high-risk packets raise gate
strictness and the blast-radius classification automatically.

AC-35 / FR-M38-04: a packet targeting an UNCOVERED HIGH-RISK module is
blocked until characterisation tests exist, and the block explains
itself with the module's comprehension record.

FR-M38-05: per-repository comprehension memory — accumulated records as
procedural memory (deposited into the M7 fabric), so the second change
to a module is cheaper than the first.

Zero model calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from meridian_core.gitcmd import run_git_command
from meridian_core.memory.fabric import MemoryEntry, MemoryFabric, Provenance

IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
INCIDENT_RE = re.compile(r"\b(incident|hotfix|rollback|revert|sev[123]|outage)\b", re.I)
CHARACTERIZATION_MARKERS = ("characterization", "characterisation", "golden master", "approval test")


class ComprehensionError(ValueError):
    """A comprehension operation could not proceed honestly."""


@dataclass(frozen=True)
class FileComprehension:
    """FR-M38-01: one module's deterministic comprehension record."""

    path: str
    imports: tuple[str, ...]              # dependency graph (out-edges)
    imported_by: tuple[str, ...]          # callers (in-edges)
    test_files: tuple[str, ...]           # coverage proxy: tests referencing it
    covered: bool
    characterization_tests: tuple[str, ...]
    change_count: int
    last_change_ts: str | None
    primary_authors: tuple[str, ...]
    incidents: tuple[str, ...]
    conventions: tuple[str, ...]          # detected naming/shape conventions
    age_days: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "imports": list(self.imports),
            "importedBy": list(self.imported_by),
            "testFiles": list(self.test_files),
            "covered": self.covered,
            "characterizationTests": list(self.characterization_tests),
            "changeCount": self.change_count,
            "lastChangeTs": self.last_change_ts,
            "primaryAuthors": list(self.primary_authors),
            "incidents": list(self.incidents),
            "conventions": list(self.conventions),
            "ageDays": self.age_days,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """FR-M38-03: the brownfield risk score and what it escalates."""

    path: str
    score: float  # 0..1
    factors: Mapping[str, float]
    high_risk: bool
    blast_radius: str  # contained | elevated | wide
    gate_strictness: str  # standard | heightened

    def explanation(self) -> str:
        parts = ", ".join(
            f"{k}={v:.2f}" for k, v in sorted(self.factors.items())
        )
        return (
            f"brownfield risk {self.score:.2f} ({parts}); blast radius"
            f" {self.blast_radius}; gate strictness {self.gate_strictness}"
        )


@dataclass(frozen=True)
class GateVerdict:
    """AC-35: allowed or blocked, with the comprehension record cited."""

    allowed: bool
    path: str
    reason: str
    record: Mapping[str, Any]


def _git(repo: Path, *args: str) -> str:
    result = run_git_command(repo, *args, timeout=60)
    return result.stdout if result.returncode == 0 else ""


class ComprehensionEngine:
    """Builds comprehension records and risk assessments for one
    repository. All signals are deterministic (imports parse, git
    history, test adjacency) — no model call (FR-M38-01)."""

    def __init__(
        self,
        repo: Path,
        *,
        source_suffixes: tuple[str, ...] = (".py", ".java", ".ts", ".js", ".kt"),
        test_pattern: str = r"test|spec",
    ) -> None:
        self.repo = repo
        self.source_suffixes = source_suffixes
        self.test_re = re.compile(test_pattern, re.I)

    # -- record -------------------------------------------------------------

    def record(self, path: str) -> FileComprehension:
        target = self.repo / path
        if not target.exists():
            raise ComprehensionError(f"{path} does not exist in {self.repo}")
        text = target.read_text(encoding="utf-8", errors="replace")
        imports = tuple(sorted(self._imports_of(text)))
        all_files = self._source_files()
        imported_by = tuple(
            sorted(
                rel
                for rel, other in all_files.items()
                if rel != path and self._module_of(path) in self._imports_of(other)
            )
        )
        test_files = tuple(
            sorted(rel for rel in all_files if self._references(rel, path))
        )
        characterization = tuple(
            rel for rel in test_files if self._is_characterization(self.repo / rel)
        )
        history = self._history(path)
        return FileComprehension(
            path=path,
            imports=imports,
            imported_by=imported_by,
            test_files=test_files,
            covered=bool(test_files),
            characterization_tests=characterization,
            change_count=history["change_count"],
            last_change_ts=history["last_change_ts"],
            primary_authors=history["authors"],
            incidents=history["incidents"],
            conventions=self._conventions(text, path),
            age_days=history["age_days"],
        )

    def _source_files(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in sorted(self.repo.rglob("*")):
            if not path.is_file() or path.suffix not in self.source_suffixes:
                continue
            rel = path.relative_to(self.repo).as_posix()
            if ".meridian" in rel or "node_modules" in rel or ".git" in rel:
                continue
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
        return out

    @staticmethod
    def _imports_of(text: str) -> set[str]:
        found = set()
        for match in IMPORT_RE.finditer(text):
            module = match.group(1) or match.group(2)
            if module:
                found.add(module.split(".")[0])
        return found

    def _module_of(self, path: str) -> str:
        stem = Path(path).stem
        return stem

    def _references(self, test_rel: str, target_rel: str) -> bool:
        if not self.test_re.search(test_rel):
            return False
        text = (self.repo / test_rel).read_text(encoding="utf-8", errors="replace")
        target_module = self._module_of(target_rel)
        target_name = Path(target_rel).stem.lower()
        return (
            target_module in self._imports_of(text)
            or target_name in text.lower()
        )

    @staticmethod
    def _is_characterization(path: Path) -> bool:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            return False
        lowered = head.lower()
        return any(marker in lowered for marker in CHARACTERIZATION_MARKERS)

    def _history(self, path: str) -> dict[str, Any]:
        log = _git(
            self.repo, "log", "--follow", "--format=%at%x00%an%x00%s", "--", path
        )
        commits = [line for line in log.splitlines() if line.strip()]
        authors: dict[str, int] = {}
        incidents: list[str] = []
        last_ts: str | None = None
        for line in commits:
            ts, author, subject = (line.split("\x00") + ["", "", ""])[:3]
            authors[author] = authors.get(author, 0) + 1
            if INCIDENT_RE.search(subject):
                incidents.append(subject[:120])
            if ts and last_ts is None:
                from datetime import datetime, timezone

                last_ts = datetime.fromtimestamp(
                    int(ts), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
        age_days = None
        first = _git(
            self.repo, "log", "--follow", "--diff-filter=A", "--format=%at", "--", path
        ).strip().splitlines()
        if first:
            from datetime import datetime, timezone

            added = datetime.fromtimestamp(int(first[-1]), tz=timezone.utc)
            # Whole days: sub-day precision is noise, and unrounded
            # ageDays made two consecutive records differ by the time it
            # took to build them — determinism (FR-M38-01) beats false
            # precision.
            age_days = int(
                (datetime.now(timezone.utc) - added).total_seconds() / 86400
            )
        return {
            "change_count": len(commits),
            "last_change_ts": last_ts,
            "authors": tuple(
                a for a, _ in sorted(authors.items(), key=lambda kv: -kv[1])[:3]
            ),
            "incidents": tuple(incidents),
            "age_days": age_days,
        }

    @staticmethod
    def _conventions(text: str, path: str) -> tuple[str, ...]:
        conventions: list[str] = []
        stem = Path(path).stem
        if re.search(r"[a-z][A-Z]", stem):
            conventions.append("PascalCase modules (class-per-file)")
        if "_" in stem:
            conventions.append("snake_case modules")
        if re.search(r"^class\s+\w+", text, re.MULTILINE):
            conventions.append("class-based structure")
        if re.search(r"^def\s+|^function\s+", text, re.MULTILINE):
            conventions.append("function-based structure")
        return tuple(conventions)

    # -- FR-M38-03: risk --------------------------------------------------------

    def assess(self, path: str) -> RiskAssessment:
        rec = self.record(path)
        factors: dict[str, float] = {}
        factors["age"] = min((rec.age_days or 0) / 3650, 1.0) * 0.3
        coupling = len(rec.imported_by) + len(rec.imports)
        factors["coupling"] = min(coupling / 20, 1.0) * 0.25
        factors["coverage"] = (0.0 if rec.covered else 1.0) * 0.3
        failure_history = min(len(rec.incidents) / 5, 1.0)
        factors["change_failure"] = failure_history * 0.15
        score = round(sum(factors.values()), 3)
        high = score >= 0.5
        blast = "wide" if len(rec.imported_by) >= 5 else (
            "elevated" if len(rec.imported_by) >= 2 else "contained"
        )
        if len(rec.imported_by) >= 5:
            blast = "wide"
        return RiskAssessment(
            path=path,
            score=score,
            factors=factors,
            high_risk=high,
            blast_radius=blast,
            gate_strictness="heightened" if high else "standard",
        )

    # -- AC-35 / FR-M38-04: the characterisation gate ------------------------------

    def gate(self, path: str) -> GateVerdict:
        """A packet targeting an uncovered high-risk module is blocked
        until characterisation tests exist; the block cites the
        comprehension record (AC-35)."""
        rec = self.record(path)
        risk = self.assess(path)
        if risk.high_risk and not rec.covered:
            reason = (
                "AC-35: blocked — "
                + risk.explanation()
                + f"; {path} is an uncovered high-risk legacy module;"
                " the Legacy Comprehension Agent must generate"
                " characterisation tests before modification"
            )
            return GateVerdict(False, path, reason, rec.to_dict())
        return GateVerdict(
            True,
            path,
            f"allowed — {risk.explanation()}",
            rec.to_dict(),
        )

    # -- FR-M38-05: comprehension memory -------------------------------------------

    def deposit_memory(self, fabric: MemoryFabric, path: str) -> Path:
        """Accumulate the record as procedural memory so the next change
        to this module starts smarter."""
        rec = self.record(path)
        return fabric.write(
            MemoryEntry(
                entry_id=f"comprehension-{rec.path.replace('/', '-')}",
                tier="procedural",
                subject=f"comprehension:{rec.path}",
                content=json.dumps(rec.to_dict(), indent=2, sort_keys=True),
                provenance=Provenance(
                    origin_sequence=None,
                    author="comprehension-engine",
                    ts_utc=_utc_now(),
                    confidence=1.0,
                    origin="workspace",
                ),
            ),
            actor="comprehension-engine",
            contradiction_terms={rec.path},
        )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
