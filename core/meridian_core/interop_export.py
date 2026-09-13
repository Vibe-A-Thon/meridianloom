"""Meridian's attributions, in formats other tools consume — `FR-M52-04` (CP1-T03).

`P24`: adopting Meridian must not strand a team's existing tooling. The same
holds the other way round. A team that also runs another tool should be able
to read what Meridian concluded without running Meridian. Two formats:

* **Git notes** under `refs/notes/meridian-attribution`, one JSON note per
  commit. Any tool that reads git notes reads these without knowing anything
  about Meridian, and they travel with the repository wherever notes are
  pushed.
* **A line-level export**, `meridian-loom/attribution-export@1`. Every line of
  the files asked for is grouped into spans, and each span's commit is in one
  of the three states with its evidence and confidence. Each file carries
  counts, and the lines Meridian cannot attribute are counted as unattributed,
  never folded into human.

**Neither format claims to match another tool's schema.** The competitive
review describes other tools' formats in prose, and none is specified in this
repository. Asserting a match nobody has checked against the real thing is the
unbacked claim `MP5` exists to stop.

**Both carry the disagreements.** Where another record disagrees about a
commit, the disagreement's digest travels with the attribution, so whoever
reads Meridian's conclusion also learns that it is contested. The claims are
assembled by `interop.commit_claims`, the same function the disagreement walk
uses, so the two cannot reach different answers about one commit.

**Neither copies code.** The export names lines by number and commit; it
never carries their content.

**Writing notes changes the repository's refs**, so it happens only when asked
(`write=True`). A note that already says the same thing is left alone.

Zero model calls (FR-M36-07).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import interop
from .attribution._git import AttributionError, ensure_repo
from .attribution.blame import blame
from .attribution.spans import classify_span
from .attribution.states import (
    ATTRIBUTION_AGENT,
    ATTRIBUTION_HUMAN,
    ATTRIBUTION_UNATTRIBUTED,
)
from .gitcmd import run_git_command
from .trailers import CO_AUTHORED_BY_KEY

#: Starts with `refs/notes/meridian`, so `interop.read_foreign_notes` skips it:
#: Meridian never reads its own export back as another tool's record.
NOTES_REF = "refs/notes/meridian-attribution"
EXPORT_SCHEMA = "meridian-loom/attribution-export@1"
NOTE_SCHEMA = "meridian-loom/commit-attribution@1"

#: A bound on one export, reported when reached (`P26`).
MAX_FILES = 2000

#: Who git records as the author of the notes commits. Explicit, so writing
#: works in a repository with no git identity configured, and honest: Meridian
#: wrote these notes.
NOTES_AUTHOR = ("Meridian Loom", "meridian-loom@localhost")

NOT_CLAIMED = (
    "Meridian's attribution and the evidence for it. This is not another tool's "
    "format, and where another record disagrees about a commit, the "
    "disagreement's digest is carried here rather than resolved."
)

_CHUNK = 100


class ExportError(Exception):
    """An export that cannot be produced: a bad ref, a path not in the tree."""


@dataclass(frozen=True)
class CommitAttribution:
    """Meridian's conclusion about one commit, with every input to it named."""

    commit: str
    state: str
    unknown_reason: str | None
    #: The attribution vocabulary: observed · inferred · unknown.
    confidence: str
    evidence: str
    #: Agents named by the commit's own git evidence, when the state is agent.
    agents: tuple[str, ...]
    ledger_range: str | None
    ledger_agents: tuple[str, ...]
    ledger_confidence: str | None
    disagreement: str | None

    def as_wire(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "state": self.state,
            "unknownReason": self.unknown_reason,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "agents": list(self.agents),
            "ledgerRange": self.ledger_range,
            "ledgerAgents": list(self.ledger_agents),
            "ledgerConfidence": self.ledger_confidence,
            "disagreement": self.disagreement,
        }

    def note(self) -> str:
        """The note body. Deterministic, so an unchanged note is recognised."""
        body = {"schema": NOTE_SCHEMA, **self.as_wire(), "notClaimed": NOT_CLAIMED}
        return json.dumps(body, indent=2, sort_keys=True) + "\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _commit_facts(repo: Path, commits: list[str]) -> dict[str, tuple[str, str, str, str]]:
    """Author name, email, time and message for each commit, in chunks."""
    facts: dict[str, tuple[str, str, str, str]] = {}
    for start in range(0, len(commits), _CHUNK):
        chunk = commits[start : start + _CHUNK]
        result = run_git_command(
            repo,
            "log",
            "--no-walk=unsorted",
            "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x1e",
            *chunk,
        )
        if result.returncode != 0:
            raise ExportError(f"cannot read commits: {(result.stderr or '').strip()}")
        for entry in result.stdout.split("\x1e"):
            entry = entry.strip("\n")
            if not entry.strip():
                continue
            fields = entry.split("\x1f", 4)
            if len(fields) == 5:
                facts[fields[0]] = (fields[1], fields[2], fields[3], fields[4])
    return facts


def attribute_commits(
    repo: Path | str,
    commits: list[str],
    *,
    ledger_rows: Any = None,
    installed_at: Any = None,
    now: Any = None,
) -> dict[str, CommitAttribution]:
    """Meridian's attribution of each commit, with its disagreements named."""
    root = Path(repo)
    stamp = (now or _now)()
    notes: dict[str, list[interop.ForeignRecord]] = {}
    for record in interop.read_foreign_notes(root, now=lambda: stamp):
        notes.setdefault(record.commit, []).append(record)

    attributions: dict[str, CommitAttribution] = {}
    for commit, (name, email, when, message) in _commit_facts(root, list(commits)).items():
        span = classify_span(
            author_name=name,
            author_email=email,
            message=message,
            author_time=when,
            installed_at=installed_at,
        )
        claims = interop.commit_claims(
            commit,
            name,
            email,
            message,
            notes=notes.get(commit, []),
            ledger_rows=ledger_rows,
            stamp=stamp,
        )
        own = next((claim for claim in claims if claim.claimant == "meridian-ledger"), None)
        git_agents: tuple[str, ...] = ()
        if span.state == ATTRIBUTION_AGENT:
            git_agents = tuple(
                sorted(
                    {
                        agent
                        for claim in claims
                        if claim.claimant in (CO_AUTHORED_BY_KEY, "commit-author")
                        for agent in claim.agents
                    }
                )
            )
        disagreement = interop.disagreement_for(commit, claims)
        ranges = interop.ledger_ranges(message)
        attributions[commit] = CommitAttribution(
            commit=commit,
            state=span.state,
            unknown_reason=span.unknown_reason,
            confidence=span.confidence,
            evidence=span.evidence,
            agents=git_agents,
            ledger_range=", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges) or None,
            ledger_agents=own.agents if own else (),
            ledger_confidence=own.confidence if own else None,
            disagreement=disagreement.digest if disagreement else None,
        )
    return attributions


def attribution_export(
    repo: Path | str,
    *,
    ref: str = "HEAD",
    paths: list[str] | None = None,
    ledger_rows: Any = None,
    installed_at: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """The line-level export, `meridian-loom/attribution-export@1`."""
    stamp = (now or _now)()
    try:
        root = ensure_repo(Path(repo))
    except AttributionError as error:
        raise ExportError(str(error)) from error
    head = run_git_command(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if head.returncode != 0:
        raise ExportError(f"no such commit: {ref}")

    if paths:
        wanted = list(paths)
    else:
        listing = run_git_command(root, "ls-tree", "-r", "--name-only", ref, "--")
        wanted = [line for line in listing.stdout.splitlines() if line]
    truncated = len(wanted) > MAX_FILES
    wanted = wanted[:MAX_FILES]

    try:
        lines = blame(root, ref=ref, paths=wanted) if wanted else []
    except AttributionError as error:
        raise ExportError(str(error)) from error

    attributions = attribute_commits(
        root,
        sorted({line.commit for line in lines}),
        ledger_rows=ledger_rows,
        installed_at=installed_at,
        now=lambda: stamp,
    )

    states = (ATTRIBUTION_AGENT, ATTRIBUTION_HUMAN, ATTRIBUTION_UNATTRIBUTED)
    totals = dict.fromkeys(states, 0)
    by_path: dict[str, list[Any]] = {}
    for line in lines:
        by_path.setdefault(line.path, []).append(line)

    files: list[dict[str, Any]] = []
    for path, file_lines in by_path.items():
        counts = dict.fromkeys(states, 0)
        spans: list[dict[str, Any]] = []
        for line in sorted(file_lines, key=lambda item: item.line):
            attribution = attributions.get(line.commit)
            state = attribution.state if attribution else ATTRIBUTION_UNATTRIBUTED
            counts[state] = counts.get(state, 0) + 1
            previous = spans[-1] if spans else None
            if previous and previous["commit"] == line.commit and previous["endLine"] == line.line - 1:
                previous["endLine"] = line.line
            else:
                spans.append(
                    {"startLine": line.line, "endLine": line.line, "commit": line.commit, "state": state}
                )
        for state, count in counts.items():
            totals[state] = totals.get(state, 0) + count
        files.append({"path": path, "lines": counts, "spans": spans})

    return {
        "schema": EXPORT_SCHEMA,
        "generatedAt": stamp,
        "ref": ref,
        "head": head.stdout.strip(),
        "truncated": truncated,
        "files": files,
        "commits": {commit: item.as_wire() for commit, item in sorted(attributions.items())},
        "totals": totals,
        "disagreements": sorted(
            {item.disagreement for item in attributions.values() if item.disagreement}
        ),
        "notClaimed": NOT_CLAIMED,
    }


def _existing_notes(root: Path) -> dict[str, str]:
    listing = run_git_command(root, "notes", "--ref", NOTES_REF, "list")
    if listing.returncode != 0:
        return {}
    existing: dict[str, str] = {}
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        blob, commit = parts
        shown = run_git_command(root, "cat-file", "blob", blob)
        if shown.returncode == 0:
            existing[commit] = shown.stdout
    return existing


def export_notes(
    repo: Path | str,
    *,
    ref: str = "HEAD",
    max_commits: int = 200,
    write: bool = False,
    ledger_rows: Any = None,
    installed_at: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """Meridian's attribution as one git note per commit.

    Without `write` this only reports what would be written.
    """
    try:
        root = ensure_repo(Path(repo))
    except AttributionError as error:
        raise ExportError(str(error)) from error
    log = run_git_command(root, "log", f"--max-count={max_commits + 1}", "--format=%H", ref)
    if log.returncode != 0:
        if "does not have any commits" in (log.stderr or ""):
            return {"ref": NOTES_REF, "commits": 0, "truncated": False, "toWrite": 0, "unchanged": 0, "written": 0}
        raise ExportError(f"cannot read history at {ref!r}: {(log.stderr or '').strip()}")
    commits = [line.strip() for line in log.stdout.splitlines() if line.strip()]
    truncated = len(commits) > max_commits
    commits = commits[:max_commits]

    attributions = attribute_commits(
        root, commits, ledger_rows=ledger_rows, installed_at=installed_at, now=now
    )
    existing = _existing_notes(root)
    pending = [
        (commit, attributions[commit].note())
        for commit in commits
        if commit in attributions and existing.get(commit) != attributions[commit].note()
    ]

    written = 0
    if write:
        for commit, body in pending:
            handle, name = tempfile.mkstemp(prefix="meridian-note-", suffix=".json")
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
                    out.write(body)
                result = run_git_command(
                    root,
                    "-c", f"user.name={NOTES_AUTHOR[0]}",
                    "-c", f"user.email={NOTES_AUTHOR[1]}",
                    "notes", "--ref", NOTES_REF, "add", "-f", "-F", name, commit,
                )
            finally:
                os.unlink(name)
            if result.returncode != 0:
                raise ExportError(
                    f"could not write the note on {commit}: {(result.stderr or '').strip()}"
                )
            written += 1

    return {
        "ref": NOTES_REF,
        "commits": len(commits),
        "truncated": truncated,
        "toWrite": len(pending),
        "unchanged": len(commits) - len(pending),
        "written": written,
    }
