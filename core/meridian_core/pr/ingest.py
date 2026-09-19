"""PR payload normalisation and per-hunk agent attribution (FR-M35-04/05).

The payload is the recorded-real GitHub REST API shape (see the package
docstring). This module never talks to the network: tests inject recorded
fixtures, production injects connector output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..attribution.diff import FileDiff, _parse_diff_text
from ..trailers import parse_attributions

__all__ = [
    "AgentAttribution",
    "HunkAttribution",
    "IngestError",
    "PullRequest",
    "attribute_hunks",
    "parse_pr",
    "resolve_agents",
    "subject_for",
    "ticket_for",
]

#: Default gate profile chain an ingested PR is routed through
#: (FR-M35-04: Verify, Security, Review before merge).
DEFAULT_GATES = ("verify", "security", "review")

#: Vendor bot login markers (lowercase substring -> vendor). The SCM
#: connectors keep this list current per vendor release (FR-M35-08).
AUTHOR_MARKERS = (
    ("copilot", "github-copilot"),
    ("claude", "claude"),
    ("cursor", "cursor"),
    ("devin", "devin"),
    ("codex", "codex"),
    ("dependabot", "dependabot"),
    ("renovate", "renovate"),
)

#: A Jira-style ticket key (the ticket-to-PR flow FR-M35-05 names).
_TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class IngestError(ValueError):
    """The PR payload is not a usable gh-api pull-request shape."""


@dataclass(frozen=True)
class PullRequest:
    """The normalised ingest view of a gh-api PR object."""

    repo: str  # head repo full_name (falls back to base repo)
    number: int
    title: str
    state: str
    author_login: str
    author_type: str  # gh api user.type: User | Bot
    author_association: str
    branch: str  # head.ref
    head_commit: str  # head.sha
    base_branch: str  # base.ref
    base_commit: str  # base.sha
    url: str
    body: str
    commits: tuple[Mapping[str, Any], ...] = ()  # gh api pull-commits shape
    files: tuple[Mapping[str, Any], ...] = ()  # gh api pull-files shape

    @property
    def subject(self) -> str:
        return subject_for(self.repo, self.number)


@dataclass(frozen=True)
class AgentAttribution:
    """One agent identity resolved for a PR, with its evidence."""

    agent_id: str  # "<vendor>:<login-or-name>" — the ledger actor_id
    vendor: str
    login: str
    confidence: str  # telemetry | inferred (FR-M35-02 vocabulary)
    source: str  # trailer | author-marker | heuristic


@dataclass(frozen=True)
class HunkAttribution:
    """One PR hunk attributed to an agent."""

    path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    agent: AgentAttribution
    rationale: str


def subject_for(repo: str, number: int) -> str:
    """The canonical merge-gate subject for a PR (what gate.approve binds)."""
    return f"pr:{repo}#{number}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IngestError(message)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_pr(raw: Any) -> PullRequest:
    """Validate and normalise a gh-api PR object. Raises :class:`IngestError`
    on any missing/ malformed required field — ingest is fail-closed."""
    if not isinstance(raw, Mapping):
        raise IngestError("pr must be the gh-api pull-request object")
    number = raw.get("number")
    _require(
        isinstance(number, int) and not isinstance(number, bool) and number >= 1,
        "pr.number must be a positive integer (gh-api shape)",
    )
    head = raw.get("head")
    base = raw.get("base")
    _require(isinstance(head, Mapping), "pr.head missing (gh-api shape)")
    _require(isinstance(base, Mapping), "pr.base missing (gh-api shape)")
    branch = head.get("ref")
    head_commit = head.get("sha")
    base_branch = base.get("ref")
    base_commit = base.get("sha")
    _require(_nonempty_str(branch), "pr.head.ref must be a non-empty string")
    _require(_nonempty_str(head_commit), "pr.head.sha must be a non-empty string")
    _require(_nonempty_str(base_branch), "pr.base.ref must be a non-empty string")
    _require(_nonempty_str(base_commit), "pr.base.sha must be a non-empty string")
    head_repo = head.get("repo")
    base_repo = base.get("repo")
    repo = ""
    if isinstance(head_repo, Mapping):
        repo = str(head_repo.get("full_name") or "").strip()
    if not repo and isinstance(base_repo, Mapping):
        repo = str(base_repo.get("full_name") or "").strip()
    _require(bool(repo), "pr head/base repo.full_name missing (gh-api shape)")
    user = raw.get("user")
    _require(isinstance(user, Mapping), "pr.user missing (gh-api shape)")
    login = user.get("login")
    _require(_nonempty_str(login), "pr.user.login must be a non-empty string")

    commits = raw.get("commits") or ()
    files = raw.get("files") or ()
    _require(isinstance(commits, (list, tuple)), "pr.commits must be a list")
    _require(isinstance(files, (list, tuple)), "pr.files must be a list")

    association = raw.get("author_association")
    return PullRequest(
        repo=repo,
        number=number,
        title=str(raw.get("title") or ""),
        state=str(raw.get("state") or ""),
        author_login=str(login).strip(),
        author_type=str(user.get("type") or ""),
        author_association=str(association or ""),
        branch=str(branch).strip(),
        head_commit=str(head_commit).strip(),
        base_branch=str(base_branch).strip(),
        base_commit=str(base_commit).strip(),
        url=str(raw.get("html_url") or raw.get("url") or ""),
        body=str(raw.get("body") or ""),
        commits=tuple(commits),
        files=tuple(files),
    )


def ticket_for(pr: PullRequest) -> str | None:
    """The linked ticket key (Jira-style) from the body, title or branch —
    the ticket-to-PR flow (FR-M35-05). None when no key is present."""
    for text in (pr.body, pr.title, pr.branch):
        match = _TICKET_RE.search(text or "")
        if match:
            return match.group(0)
    return None


def resolve_agents(pr: PullRequest) -> list[AgentAttribution]:
    """Every agent identity evidenced on the PR, strongest evidence first.

    Precedence: ``Co-Authored-By`` trailers (the agent's own recorded
    identity), then author login markers, then the heuristic fallback.
    """
    agents: list[AgentAttribution] = []
    seen: set[str] = set()

    def add(agent: AgentAttribution) -> None:
        if agent.agent_id not in seen:
            seen.add(agent.agent_id)
            agents.append(agent)

    for commit in pr.commits:
        if not isinstance(commit, Mapping):
            continue
        inner = commit.get("commit")
        message = inner.get("message") if isinstance(inner, Mapping) else None
        if not isinstance(message, str):
            continue
        for attribution in parse_attributions(message):
            if attribution["meridianAuthored"]:
                continue  # Meridian's own line is reserved for Meridian commits
            vendor = str(attribution["vendor"])
            name = str(attribution["name"])
            if vendor in ("generic", "unknown"):
                # The mailbox is not a known vendor address (agents often
                # trailer with a users.noreply.github.com identity): fall
                # back to the vendor markers on the recorded name.
                marker = _marker_vendor(name, "")
                if marker is not None:
                    vendor = marker
            login = name or str(attribution["email"] or "")
            add(
                AgentAttribution(
                    agent_id=f"{vendor}:{login}",
                    vendor=vendor,
                    login=login,
                    confidence="telemetry",
                    source="trailer",
                )
            )

    marker_vendor = _marker_vendor(pr.author_login, pr.author_type)
    if marker_vendor is not None and marker_vendor not in {a.vendor for a in agents}:
        # The author marker is weaker evidence than a trailer: when the
        # trailer already named this vendor the marker adds no identity.
        add(
            AgentAttribution(
                agent_id=f"{marker_vendor}:{pr.author_login}",
                vendor=marker_vendor,
                login=pr.author_login,
                confidence="telemetry",
                source="author-marker",
            )
        )

    if not agents:
        add(
            AgentAttribution(
                agent_id=f"unknown:{pr.author_login}",
                vendor="unknown",
                login=pr.author_login,
                confidence="inferred",
                source="heuristic",
            )
        )
    return agents


def _marker_vendor(login: str, user_type: str) -> str | None:
    lowered = login.lower()
    for marker, vendor in AUTHOR_MARKERS:
        if marker in lowered:
            return vendor
    if user_type == "Bot":
        return "unknown-bot"
    return None


def _diff_files(pr: PullRequest) -> list[FileDiff]:
    """The PR's hunks as FileDiffs: the gh-api ``files`` shape when present
    (per-file ``patch``), else a raw unified ``diff`` text payload."""
    files: list[FileDiff] = []
    for item in pr.files:
        if not isinstance(item, Mapping):
            continue
        filename = item.get("filename")
        patch = item.get("patch")
        if not isinstance(filename, str) or not isinstance(patch, str):
            continue  # binary/large files carry no patch — recorded, no hunks
        parsed = _parse_diff_text(
            f"diff --git a/{filename} b/{filename}\n--- a/{filename}\n+++ b/{filename}\n{patch}"
        )
        files.extend(parsed)
    return files


def attribute_hunks(pr: PullRequest) -> list[HunkAttribution]:
    """Every hunk of the PR attributed to an agent, confidence-labelled.

    The gh-api payload has no per-hunk commit mapping, so a hunk takes the
    strongest resolved agent; when several agents are evidenced the
    attribution is still per-hunk (each hunk names the primary agent) but
    the confidence drops to ``inferred`` and the rationale says the
    per-hunk split is unavailable from the SCM payload — confidence is
    labelled, never overclaimed (G3).
    """
    agents = resolve_agents(pr)
    primary = agents[0]
    ambiguous = len(agents) > 1
    attributions: list[HunkAttribution] = []
    for file in _diff_files(pr):
        for hunk in file.hunks:
            agent = primary
            if ambiguous:
                agent = AgentAttribution(
                    agent_id=primary.agent_id,
                    vendor=primary.vendor,
                    login=primary.login,
                    confidence="inferred",
                    source=primary.source,
                )
            rationale = f"{agent.source} evidence"
            if ambiguous:
                rationale += (
                    "; multiple agents evidenced on the PR — per-hunk split "
                    "unavailable from the SCM payload"
                )
            attributions.append(
                HunkAttribution(
                    path=file.path,
                    old_start=hunk.old_start,
                    old_count=hunk.old_count,
                    new_start=hunk.new_start,
                    new_count=hunk.new_count,
                    agent=agent,
                    rationale=rationale,
                )
            )
    return attributions
