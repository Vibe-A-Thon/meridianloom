"""Worktree isolation for hosted agents (FR-M18-01..08; F1 Workstream A task 5).

Meridian *launches* hosted ACP agents (unlike observed ones), so every write
those agents make must land in a dedicated git worktree — never the user's
primary working tree (``FR-M18-01``, amended ``FR-M1-05``). One linked
worktree per story/run lives under ``<repo>/.meridian/worktrees/<story-id>/``
on a dedicated branch ``meridian/<story-id>`` forked from a configurable base
branch (``FR-M18-02``).

The manager owns five concerns, all pure git (zero model calls,
``FR-M36-07``):

* create / list / remove the story worktree;
* worktree-local agent identity (``FR-M18-05``) — ``user.name`` /
  ``user.email`` derived deterministically from the adapter id, so
  ``git blame`` attributes authorship to the agent, never the human;
* a commit trailer on every agent commit (``FR-M18-07``) — a worktree-local
  ``commit-msg`` hook (``core.hooksPath`` per worktree, enabled via
  ``extensions.worktreeConfig``) appending ``Meridian-Hosted-Agent:
  <adapter-id>`` with ``git interpret-trailers`` — the standard trailer
  mechanics (G2), not a bespoke parser;
* story abort (``FR-M18-04``) — remove the worktree, delete the never-pushed
  branch, leave the primary tree byte-identical (AC-14);
* pre-flight conflict detection (``FR-M18-03``, AC-13) surfacing a
  structured report before a packet starts.

Where the metadata lives: everything Meridian owns for a worktree (the hook
script, the creation metadata) lives in the worktree's git admin dir
(``.git/worktrees/<name>/``), *outside* the working tree. The worktree's
``git status`` therefore stays honest — only the agent's own files make it
dirty — and ``git worktree remove`` reclaims all of it in one action.

The manager never touches the ledger; the server RPC layer records
create/remove/abort facts with ``worktree_ref`` set.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..attribution._git import AttributionError, ensure_repo, run_git

#: Meridian-managed worktrees always live here, relative to the repo root.
WORKTREES_DIR = ".meridian/worktrees"

#: Default story-branch naming convention (FR-M18-02; configurable per call).
DEFAULT_BASE_BRANCH = "main"
BRANCH_PREFIX = "meridian/"

#: The commit trailer every hosted-agent commit carries (FR-M18-07).
TRAILER_KEY = "Meridian-Hosted-Agent"

#: Hook script + creation metadata inside the worktree's git admin dir.
_HOOKS_DIR_NAME = "meridian-hooks"
_META_FILE_NAME = "meridian-meta.json"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")


class WorktreeError(Exception):
    """A clean, user-actionable worktree failure (never a crash)."""


class WorktreeExistsError(WorktreeError):
    """A worktree for this story already exists."""


class WorktreeNotFoundError(WorktreeError):
    """No Meridian-managed worktree for this story."""


class WorktreeDirtyError(WorktreeError):
    """Removal refused: the worktree has uncommitted or untracked state."""

    def __init__(self, story_id: str, files: list[str]) -> None:
        self.story_id = story_id
        self.files = files
        preview = ", ".join(files[:5])
        suffix = "…" if len(files) > 5 else ""
        super().__init__(
            f"story worktree '{story_id}' is not clean "
            f"({len(files)} modified/untracked: {preview}{suffix}); "
            "pass force only when that content is expendable"
        )


@dataclass(frozen=True)
class WorktreeInfo:
    """One Meridian-managed story worktree (wire shape: WorktreeInfo)."""

    story_id: str
    branch: str
    path: Path
    base_branch: str
    base_commit: str | None
    head_commit: str
    adapter_id: str
    dirty: bool
    unpushed_commits: int

    @property
    def worktree_ref(self) -> str:
        return f"{WORKTREES_DIR}/{self.story_id}"


@dataclass(frozen=True)
class WorktreeConflict:
    """One detected pre-flight conflict (wire shape: WorktreeConflict)."""

    kind: str  # unmerged_upstream | primary_uncommitted |
    # worktree_uncommitted | worktree_unpushed
    path: str | None
    detail: str


@dataclass(frozen=True)
class ConflictReport:
    """FR-M18-03: the structured pre-flight report. blocked = any conflict."""

    repo: Path
    base_branch: str
    conflicts: tuple[WorktreeConflict, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.conflicts)


def agent_identity(adapter_id: str) -> tuple[str, str]:
    """The deterministic hosted-agent git identity for an adapter (FR-M18-05).

    Derived from the adapter id only — no fabricated human-looking names,
    no PII: ``Meridian Agent (<adapter-id>)`` /
    ``<adapter-id>@agents.meridian.local``.
    """
    _validate_id(adapter_id, "adapterId")
    return f"Meridian Agent ({adapter_id})", f"{adapter_id}@agents.meridian.local"


def _validate_id(value: str, what: str) -> None:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise WorktreeError(
            f"{what} must match [A-Za-z0-9][A-Za-z0-9._-]*, got {value!r}"
        )


def _validate_branch(branch: str) -> None:
    if (
        not isinstance(branch, str)
        or not _BRANCH_RE.match(branch)
        or ".." in branch
        or branch.endswith("/")
        or "//" in branch
    ):
        raise WorktreeError(f"invalid story branch name: {branch!r}")


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Like run_git but without raising — for existence probes."""
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", "--no-pager", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:
        raise WorktreeError("git executable not found on PATH") from error


def _ref_exists(repo: Path, ref: str) -> bool:
    return _run(repo, "rev-parse", "--verify", "--quiet", ref).returncode == 0


def _head(repo: Path) -> str:
    return run_git(repo, "rev-parse", "HEAD").strip()


def _status_paths(repo: Path) -> list[str]:
    """Worktree-relative dirty paths (modified, staged, untracked).

    Meridian's own ``.meridian/worktrees/`` subtree is excluded: a linked
    worktree nested inside the primary tree reads as one untracked entry
    there, and it is Meridian's scratch space, not human or agent content.
    """
    out = run_git(repo, "status", "--porcelain", "--untracked-files=all")
    prefix = WORKTREES_DIR + "/"
    paths: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        entry = line[3:]
        if " -> " in entry:  # rename: the new path is what a packet would hit
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        if entry.startswith(prefix):
            continue
        paths.append(entry)
    return paths


def _matches_targets(path: str, target_paths: list[str] | None) -> bool:
    if not target_paths:
        return True  # no targets given: every dirty file is reported
    posix = Path(path).as_posix()
    for raw in target_paths:
        target = Path(raw).as_posix().rstrip("/")
        if posix == target or posix.startswith(target + "/"):
            return True
    return False


class WorktreeManager:
    """Owns the Meridian-managed story worktrees of one repository."""

    def __init__(self, repo: Path) -> None:
        self._repo = ensure_repo(Path(repo))

    @property
    def repo(self) -> Path:
        return self._repo

    def worktree_path(self, story_id: str) -> Path:
        _validate_id(story_id, "storyId")
        return self._repo / WORKTREES_DIR / story_id

    # -- create --------------------------------------------------------------

    def create(
        self,
        story_id: str,
        adapter_id: str,
        base_branch: str = DEFAULT_BASE_BRANCH,
        branch: str | None = None,
    ) -> WorktreeInfo:
        """FR-M18-01/02/05/07: create the story worktree on its own branch."""
        _validate_id(story_id, "storyId")
        agent_identity(adapter_id)  # validates the adapter id up front
        _validate_id(base_branch, "baseBranch")
        branch = branch or f"{BRANCH_PREFIX}{story_id}"
        _validate_branch(branch)

        path = self.worktree_path(story_id)
        if path.exists():
            raise WorktreeExistsError(
                f"story worktree already exists: {path} "
                f"(worktree/list to inspect, worktree/remove to reclaim it)"
            )
        if not _ref_exists(self._repo, f"refs/heads/{base_branch}"):
            raise WorktreeError(
                f"base branch '{base_branch}' does not exist in {self._repo}"
            )
        base_commit = run_git(
            self._repo, "rev-parse", f"refs/heads/{base_branch}^{{commit}}"
        ).strip()

        branch_created = False
        if _ref_exists(self._repo, f"refs/heads/{branch}"):
            # Resume path: the branch already exists (e.g. a retried run) —
            # check it out rather than rewriting it.
            run_git(self._repo, "worktree", "add", str(path), branch)
        else:
            run_git(
                self._repo,
                "worktree",
                "add",
                "-b",
                branch,
                str(path),
                base_branch,
            )
            branch_created = True
        try:
            self._configure_agent_worktree(
                path, story_id, adapter_id, base_branch, base_commit, branch
            )
        except Exception:
            # Creation is all-or-nothing: never leave a half-configured
            # worktree (no identity, no trailer) behind for the agent.
            _run(self._repo, "worktree", "remove", "--force", str(path))
            if branch_created:
                _run(self._repo, "branch", "-D", branch)
            raise
        return self.get(story_id)

    def _configure_agent_worktree(
        self,
        path: Path,
        story_id: str,
        adapter_id: str,
        base_branch: str,
        base_commit: str,
        branch: str,
    ) -> None:
        git_dir = Path(run_git(path, "rev-parse", "--git-dir").strip())
        name, email = agent_identity(adapter_id)

        # Per-worktree config (hooks path + identity) requires git's
        # worktree-config extension; enabling it is idempotent and repo-local.
        run_git(self._repo, "config", "extensions.worktreeConfig", "true")

        hooks_dir = git_dir / _HOOKS_DIR_NAME
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook = hooks_dir / "commit-msg"
        # LF line endings matter: a CRLF shebang breaks the hook on POSIX git.
        hook.write_text(
            "#!/bin/sh\n"
            f"# Meridian-hosted agent trailer (FR-M18-07): standard trailer\n"
            f"# mechanics (git interpret-trailers) append {TRAILER_KEY} to every\n"
            f"# commit made in this story worktree.\n"
            f'git interpret-trailers --in-place --trailer "{TRAILER_KEY}: {adapter_id}" "$1"\n',
            encoding="utf-8",
            newline="\n",
        )
        try:
            hook.chmod(0o755)
        except OSError:
            pass  # Windows: git runs shebang hooks via sh regardless

        run_git(path, "config", "--worktree", "core.hooksPath", str(hooks_dir))
        run_git(path, "config", "--worktree", "user.name", name)
        run_git(path, "config", "--worktree", "user.email", email)

        (git_dir / _META_FILE_NAME).write_text(
            json.dumps(
                {
                    "storyId": story_id,
                    "adapterId": adapter_id,
                    "baseBranch": base_branch,
                    "baseCommit": base_commit,
                    "branch": branch,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- inspect -------------------------------------------------------------

    def _meta(self, git_dir: Path) -> dict[str, Any]:
        meta_path = git_dir / _META_FILE_NAME
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}  # metadata degrades, the worktree facts never do

    def _info_for_path(self, path: Path) -> WorktreeInfo:
        story_id = path.name
        git_dir = Path(run_git(path, "rev-parse", "--git-dir").strip())
        meta = self._meta(git_dir)
        branch = run_git(
            path, "symbolic-ref", "--quiet", "--short", "HEAD"
        ).strip()
        base_branch = meta.get("baseBranch") or DEFAULT_BASE_BRANCH
        unpushed = 0
        if _ref_exists(path, f"refs/heads/{base_branch}"):
            unpushed = int(
                run_git(path, "rev-list", "--count", f"{base_branch}..{branch}").strip()
                or "0"
            )
        return WorktreeInfo(
            story_id=story_id,
            branch=branch,
            path=path,
            base_branch=base_branch,
            base_commit=meta.get("baseCommit"),
            head_commit=_head(path),
            adapter_id=meta.get("adapterId") or "unknown",
            dirty=bool(_status_paths(path)),
            unpushed_commits=unpushed,
        )

    def get(self, story_id: str) -> WorktreeInfo:
        path = self.worktree_path(story_id)
        if not path.exists():
            raise WorktreeNotFoundError(
                f"no story worktree at {path} "
                f"(worktree/create makes one for a story)"
            )
        return self._info_for_path(path)

    def exists(self, story_id: str) -> bool:
        return self.worktree_path(story_id).exists()

    def list(self) -> list[WorktreeInfo]:
        """Every Meridian-managed worktree, stale admin entries pruned."""
        run_git(self._repo, "worktree", "prune")
        out = run_git(self._repo, "worktree", "list", "--porcelain")
        root = (self._repo / WORKTREES_DIR).resolve()
        infos: list[WorktreeInfo] = []
        for block in out.split("\n\n"):
            fields = dict(
                line.split(" ", 1) for line in block.splitlines() if " " in line
            )
            raw_path = fields.get("worktree")
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                inside = path.resolve().is_relative_to(root)
            except OSError:
                inside = False
            if inside and path.exists():
                infos.append(self._info_for_path(path))
        return sorted(infos, key=lambda info: info.story_id)

    # -- remove / abort ------------------------------------------------------

    def remove(self, story_id: str, force: bool = False) -> WorktreeInfo:
        """Remove the worktree. The branch survives — abort deletes it."""
        info = self.get(story_id)
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(info.path))
        result = _run(self._repo, *args)
        if result.returncode != 0:
            files = _status_paths(info.path)
            if files and not force:
                raise WorktreeDirtyError(story_id, files)
            raise WorktreeError(
                f"git worktree remove failed for {info.path}: "
                f"{(result.stderr or '').strip()}"
            )
        return info

    def abort(self, story_id: str) -> tuple[WorktreeInfo, bool, str | None]:
        """FR-M18-04 / AC-14: story abort.

        Removes the worktree (the human's explicit abort discards in-flight
        agent output), deletes the story branch when it has never been pushed
        (a pushed branch is kept for the record), and never writes anywhere
        near the primary working tree.
        """
        info = self.get(story_id)
        self.remove(story_id, force=True)

        kept_reason: str | None = None
        branch = info.branch
        pushed_on = self._remote_hosting(branch)
        if pushed_on is not None:
            kept_reason = (
                f"branch '{branch}' exists on remote '{pushed_on}'; "
                "abort keeps it for the record"
            )
        elif _ref_exists(self._repo, f"refs/heads/{branch}"):
            run_git(self._repo, "branch", "-D", branch)
        return info, kept_reason is None, kept_reason

    def _remote_hosting(self, branch: str) -> str | None:
        """The remote whose namespace carries this branch, if any."""
        out = run_git(self._repo, "for-each-ref", "--format=%(refname)", "refs/remotes")
        suffix = f"/{branch}"
        for refname in out.splitlines():
            refname = refname.strip()
            if refname.endswith(suffix):
                remote = refname[: -len(suffix)].removeprefix("refs/remotes/")
                if remote:
                    return remote
        return None

    # -- pre-flight conflict detection (FR-M18-03, AC-13) ---------------------

    def conflicts(
        self,
        story_id: str | None = None,
        base_branch: str = DEFAULT_BASE_BRANCH,
        target_paths: list[str] | None = None,
    ) -> ConflictReport:
        """Detect what would collide if a packet started now.

        * unmerged_upstream — the story branch is behind the base branch;
        * primary_uncommitted — dirty files in the PRIMARY tree colliding
          with the packet's target paths (AC-13: the human's edit is never
          lost because the packet never starts);
        * worktree_uncommitted / worktree_unpushed — a story worktree
          carrying state that starting over would clobber.

        The report is data, not a verdict UI: blocked = any conflict.
        """
        _validate_id(base_branch, "baseBranch")
        found: list[WorktreeConflict] = []

        # Primary tree first — this check runs even without a story id.
        for path in _status_paths(self._repo):
            if _matches_targets(path, target_paths):
                found.append(
                    WorktreeConflict(
                        kind="primary_uncommitted",
                        path=path,
                        detail=(
                            "the primary working tree has uncommitted changes "
                            f"to '{path}' that the packet targets"
                        ),
                    )
                )

        if story_id is not None:
            _validate_id(story_id, "storyId")
            branch = f"{BRANCH_PREFIX}{story_id}"
            if _ref_exists(self._repo, f"refs/heads/{branch}"):
                behind = int(
                    run_git(
                        self._repo,
                        "rev-list",
                        "--count",
                        f"{branch}..refs/heads/{base_branch}",
                    ).strip()
                    or "0"
                )
                if behind:
                    found.append(
                        WorktreeConflict(
                            kind="unmerged_upstream",
                            path=None,
                            detail=(
                                f"base branch '{base_branch}' has {behind} "
                                f"commit(s) not on story branch '{branch}'"
                            ),
                        )
                    )
            if self.exists(story_id):
                wt_path = self.worktree_path(story_id)
                wt_branch = run_git(
                    wt_path, "symbolic-ref", "--quiet", "--short", "HEAD"
                ).strip()
                for path in _status_paths(wt_path):
                    found.append(
                        WorktreeConflict(
                            kind="worktree_uncommitted",
                            path=path,
                            detail=(
                                f"story worktree '{story_id}' has uncommitted "
                                f"state at '{path}'; starting a packet would "
                                "clobber it"
                            ),
                        )
                    )
                if _ref_exists(wt_path, f"refs/heads/{base_branch}"):
                    unpushed = int(
                        run_git(
                            wt_path,
                            "rev-list",
                            "--count",
                            f"{base_branch}..{wt_branch}",
                        ).strip()
                        or "0"
                    )
                    if unpushed:
                        found.append(
                            WorktreeConflict(
                                kind="worktree_unpushed",
                                path=None,
                                detail=(
                                    f"story branch '{wt_branch}' has {unpushed} "
                                    "commit(s) not on "
                                    f"'{base_branch}' — unmerged agent work "
                                    "would be discarded"
                                ),
                            )
                        )
        return ConflictReport(
            repo=self._repo, base_branch=base_branch, conflicts=tuple(found)
        )
