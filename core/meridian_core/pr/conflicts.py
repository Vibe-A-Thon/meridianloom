"""Multi-agent conflict detection (FR-M35-07; F1 Workstream B task 13).

When multiple agents (Meridian-native or external) touch the same story,
each hunk is attributed to its agent and agent-vs-agent conflicts are
surfaced as a DISTINCT rework class — ``agent-conflict`` — separate from
human-rejection reasons (E-GR-03's taxonomy lands in task 14; the class
literal is stable across both tasks).

Attribution is per commit, in FR-M35-02 precedence order: the commit's
``Co-Authored-By`` trailers (the agent's own recorded identity,
``telemetry``), the author mailbox against the vendor table, then name
markers; a commit with no agent evidence is a human actor (git blame is
``direct`` evidence).

A conflict between two agents is a hunk-level interval fact, not a
judgement: for hunks ``h1`` (agent A, earlier commit) and ``h2`` (agent
B, later commit) on the same file, the ranges conflict when h2's OLD-side
range intersects h1's NEW-side range — agent B edited or deleted lines
agent A wrote — or when both hunks' NEW-side ranges intersect. Same-agent
pairs are not conflicts: one agent reworking its own lines is ordinary
work.

Zero model calls (FR-M36-07): everything is git diff, blame and string
matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..attribution import diff as diff_mod
from ..attribution._git import ensure_repo, run_git
from ..trailers import co_author_attribution, parse_attributions

__all__ = [
    "AGENT_CONFLICT_REASON",
    "AgentHunk",
    "Conflict",
    "attribution_for_commit",
    "collect_agent_hunks",
    "detect_conflicts",
]

#: The distinct rework class for agent-vs-agent conflicts (FR-M35-07).
#: Also the E-GR-03 taxonomy id (task 14) — one literal everywhere.
AGENT_CONFLICT_REASON = "agent-conflict"

#: Vendor markers matched against author/committer names (lowered).
_NAME_MARKERS = (
    ("copilot", "github-copilot"),
    ("claude", "claude"),
    ("cursor", "cursor"),
    ("devin", "devin"),
    ("codex", "codex"),
)


@dataclass(frozen=True)
class CommitAgent:
    """The agent identity one commit is attributed to."""

    agent_id: str  # "<vendor>:<name>" — the ledger actor_id
    vendor: str
    name: str
    confidence: str  # telemetry (agent evidence) | direct (human author)
    source: str  # trailer | author-mailbox | name-marker | human


@dataclass(frozen=True)
class AgentHunk:
    """One hunk of one commit, attributed to the commit's agent."""

    path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    agent: CommitAgent
    commit: str


@dataclass(frozen=True)
class Conflict:
    """One agent-vs-agent conflict between two attributed hunks."""

    path: str
    kind: str  # "edited-over-agent-lines" | "added-in-same-region"
    earlier: AgentHunk
    later: AgentHunk

    @property
    def agents(self) -> tuple[str, str]:
        return (self.earlier.agent.agent_id, self.later.agent.agent_id)

    @property
    def idempotency_key(self) -> tuple[str, str, str, int, int]:
        """(earlier commit, later commit, path, new start, old start) —
        the duplicate guard the RPC uses before recording."""
        return (
            self.earlier.commit,
            self.later.commit,
            self.path,
            self.earlier.new_start,
            self.later.old_start,
        )


def _vendor_from_name(name: str) -> str | None:
    lowered = name.lower()
    for marker, vendor in _NAME_MARKERS:
        if marker in lowered:
            return vendor
    return None


def attribution_for_commit(repo: Path, sha: str) -> CommitAgent:
    """Attribute one commit to its agent (FR-M35-02 precedence)."""
    message = run_git(repo, "log", "-1", "--format=%B", sha)
    author_line = run_git(repo, "log", "-1", "--format=%an <%ae>", sha).strip()
    for trailer in parse_attributions(message):
        if trailer["meridianAuthored"]:
            continue
        vendor = str(trailer["vendor"])
        name = str(trailer["name"])
        if vendor in ("generic", "unknown"):
            marker = _vendor_from_name(name)
            if marker is not None:
                vendor = marker
        if vendor == "unknown":
            continue
        return CommitAgent(
            agent_id=f"{vendor}:{name}",
            vendor=vendor,
            name=name,
            confidence="telemetry",
            source="trailer",
        )
    if "<" in author_line:
        parsed = co_author_attribution(author_line)
        vendor = str(parsed["vendor"])
        name = str(parsed["name"])
        if vendor not in ("generic", "unknown"):
            return CommitAgent(
                agent_id=f"{vendor}:{name}",
                vendor=vendor,
                name=name,
                confidence="telemetry",
                source="author-mailbox",
            )
        marker = _vendor_from_name(name)
        if marker is not None:
            return CommitAgent(
                agent_id=f"{marker}:{name}",
                vendor=marker,
                name=name,
                confidence="telemetry",
                source="name-marker",
            )
        return CommitAgent(
            agent_id=f"human:{name}",
            vendor="human",
            name=name,
            confidence="direct",
            source="human",
        )
    return CommitAgent(
        agent_id="human:unknown",
        vendor="human",
        name="unknown",
        confidence="direct",
        source="human",
    )


def _range(start: int, count: int) -> tuple[int, int]:
    # A 0-count hunk anchors at the preceding line: its span is empty.
    return (start, start + max(count, 0))


def _intersects(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _non_merge_commits(repo: Path, base: str | None, ref: str) -> list[str]:
    args = ["log", "--no-merges", "--format=%H", "--reverse"]
    args.append(f"{base}..{ref}" if base else ref)
    return [line for line in run_git(repo, *args).splitlines() if line.strip()]


def collect_agent_hunks(
    repo_path: Path | str, base: str | None, ref: str
) -> list[AgentHunk]:
    """Every hunk of every non-merge commit in ``base..ref`` (or the whole
    ``ref`` history), attributed to its commit's agent, oldest first."""
    repo = ensure_repo(Path(repo_path))
    hunks: list[AgentHunk] = []
    for sha in _non_merge_commits(repo, base, ref):
        agent = attribution_for_commit(repo, sha)
        parents = run_git(repo, "log", "-1", "--format=%P", sha).split()
        base_ref = parents[0] if parents else None
        # A root commit diffs against the empty tree, exactly like the
        # rejection detector.
        if base_ref is None:
            from ..rejection.detector import EMPTY_TREE

            base_ref = EMPTY_TREE
        for file in diff_mod.diff(repo, base=base_ref, compare=sha):
            for hunk in file.hunks:
                if hunk.old_count == 0 and hunk.new_count == 0:
                    continue
                hunks.append(
                    AgentHunk(
                        path=file.path,
                        old_start=hunk.old_start,
                        old_count=hunk.old_count,
                        new_start=hunk.new_start,
                        new_count=hunk.new_count,
                        agent=agent,
                        commit=sha,
                    )
                )
    return hunks


def detect_conflicts(hunks: list[AgentHunk]) -> list[Conflict]:
    """Agent-vs-agent conflicts over attributed hunks (oldest first).

    Pairwise across commits of DIFFERENT agents on the same file: h2's
    old-side range intersecting h1's new-side range means the later agent
    edited or deleted the earlier agent's lines; intersecting new-side
    ranges mean both agents added into the same region.
    """
    conflicts: list[Conflict] = []
    for j, later in enumerate(hunks):
        for earlier in hunks[:j]:
            if earlier.agent.agent_id == later.agent.agent_id:
                continue
            if earlier.path != later.path:
                continue
            edited = _intersects(
                _range(earlier.new_start, earlier.new_count),
                _range(later.old_start, later.old_count),
            )
            added = _intersects(
                _range(earlier.new_start, earlier.new_count),
                _range(later.new_start, later.new_count),
            )
            if edited:
                conflicts.append(
                    Conflict(
                        path=later.path,
                        kind="edited-over-agent-lines",
                        earlier=earlier,
                        later=later,
                    )
                )
            elif added:
                conflicts.append(
                    Conflict(
                        path=later.path,
                        kind="added-in-same-region",
                        earlier=earlier,
                        later=later,
                    )
                )
    return conflicts
