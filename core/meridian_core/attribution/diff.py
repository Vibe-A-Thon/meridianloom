"""Unified-diff attribution (FR-M33-02 subset).

Covers the changes blame cannot see: uncommitted and staged working-tree
changes, and commit ranges. Every hunk line carries its old/new line
numbers and content; added lines in a commit-range diff are annotated with
the blame attribution (commit, author, timestamp) taken at the compare ref,
so a range answer names who introduced each line, not only that it changed.
Rename detection (-M) is on. Working-tree added lines carry ``commit: None``
— there is no commit yet, and inventing one would be a lie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import blame as blame_mod
from ._git import AttributionError, ensure_repo, normalise_repo_path, run_git

__all__ = ["AttributionError", "DiffLine", "FileDiff", "Hunk", "diff"]


@dataclass
class DiffLine:
    kind: str  # "added" | "removed" | "context"
    old_line: int | None  # 1-based in the base version; None for pure adds
    new_line: int | None  # 1-based in the compare version; None for removals
    content: str  # without the line terminator (CRLF tolerated)
    commit: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    author_time: str | None = None


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str  # compare-side path
    old_path: str | None  # set for renames/copies
    status: str  # "added" | "modified" | "deleted" | "renamed"
    hunks: list[Hunk] = field(default_factory=list)


def _parse_range(spec: str) -> tuple[int, int]:
    # "@@ -a[,b] +c[,d] @@" — a missing count means 1; a count of 0 anchors
    # the hunk at the line *before* the given number.
    start, _, count = spec.partition(",")
    return int(start), int(count or "1")


def _parse_diff_text(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    # State for the file currently being described. Pure renames emit no
    # ---/+++ pair, so the FileDiff is materialised on flush (next
    # "diff --git" line or EOF), not on the "+++" line.
    pending_old: str | None = None
    pending_new: str | None = None
    new_file = deleted = renamed = False
    current: FileDiff | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0

    def flush() -> None:
        nonlocal current, pending_old, pending_new, new_file, deleted, renamed
        if current is None and renamed:
            # Pure rename: no ---/+++ pair, only rename headers.
            current = FileDiff(
                path=pending_new or "?", old_path=pending_old, status="renamed"
            )
        if current is not None:
            if renamed and current.status == "modified":
                current.status = "renamed"
                current.old_path = pending_old
            files.append(current)
        current = None
        pending_old = pending_new = None
        new_file = deleted = renamed = False

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            flush()
            # "diff --git a/<old> b/<new>"; quoted forms (core.quotepath is
            # off, but spaces are still safe here) are split on " b/".
            _, _, rest = raw.partition("diff --git a/")
            old_raw, _, new_raw = rest.rpartition(" b/")
            pending_old, pending_new = old_raw, new_raw
            continue
        if current is None:
            if raw.startswith("new file mode"):
                new_file = True
                continue
            if raw.startswith("deleted file mode"):
                deleted = True
                continue
            if raw.startswith("rename from "):
                pending_old = raw[len("rename from "):]
                renamed = True
                continue
            if raw.startswith("rename to "):
                pending_new = raw[len("rename to "):]
                renamed = True
                continue
            if raw.startswith("--- "):
                side = raw[4:]
                if not new_file and side.startswith("a/"):
                    pending_old = side[2:]
                status = "added" if new_file else "deleted" if deleted else "modified"
                current = FileDiff(path=pending_new or "?", old_path=None, status=status)
                continue
            continue
        if raw.startswith("+++ "):
            side = raw[4:]
            if current.status != "added" and side.startswith("b/"):
                current.path = side[2:]
            continue
        if raw.startswith("@@ "):
            _, _, ranges = raw.partition("@@ ")
            old_spec, _, tail = ranges.partition(" ")
            new_spec = tail.split(" ", 1)[0]
            old_start, old_count = _parse_range(old_spec.lstrip("-"))
            new_start, new_count = _parse_range(new_spec.lstrip("+"))
            old_no, new_no = old_start, new_start
            hunk = Hunk(old_start, old_count, new_start, new_count)
            current.hunks.append(hunk)
            continue
        if raw.startswith(
            ("index ", "similarity ", "dissimilarity ", "old mode", "new mode",
             "Binary files", "GIT binary patch", "\\")
        ):
            continue
        if hunk is None or len(raw) < 1:
            continue
        content = raw[1:].rstrip("\r") if len(raw) >= 1 else ""
        marker, line = raw[:1], content
        if marker == "+":
            hunk.lines.append(DiffLine("added", None, new_no, line))
            new_no += 1
        elif marker == "-":
            hunk.lines.append(DiffLine("removed", old_no, None, line))
            old_no += 1
        elif marker == " ":
            hunk.lines.append(DiffLine("context", old_no, new_no, line))
            old_no += 1
            new_no += 1
        # Anything else is ignored defensively.
    flush()
    return files


def _annotate_range_attribution(repo: Path, files: list[FileDiff], compare: str) -> None:
    """Join range-diff added lines with blame at ``compare`` (in place)."""
    touched = sorted({file.path for file in files if file.status != "deleted"})
    if not touched:
        return
    try:
        blamed = blame_mod.blame(repo, ref=compare, paths=touched)
    except AttributionError:
        # compare may not be blame-able (e.g. a range whose compare side no
        # longer contains the path); attribution simply stays unknown.
        return
    by_key = {(line.path, line.line): line for line in blamed}
    for file in files:
        for hunk in file.hunks:
            for line in hunk.lines:
                if line.kind != "added" or line.new_line is None:
                    continue
                hit = by_key.get((file.path, line.new_line))
                if hit is None:
                    continue
                line.commit = hit.commit
                line.author_name = hit.author_name
                line.author_email = hit.author_email
                line.author_time = hit.author_time


def diff_with_repo(
    repo_path: Path | str,
    base: str | None = None,
    compare: str | None = None,
    staged: bool = False,
    paths: list[str] | None = None,
) -> tuple[Path, list[FileDiff]]:
    """Like :func:`diff` but also returns the resolved repository toplevel."""
    repo = ensure_repo(Path(repo_path))
    return repo, diff(repo, base=base, compare=compare, staged=staged, paths=paths)


def diff(
    repo_path: Path | str,
    base: str | None = None,
    compare: str | None = None,
    staged: bool = False,
    paths: list[str] | None = None,
) -> list[FileDiff]:
    """Diff the working tree (default), the index (staged), or a range.

    ``base``+``compare`` must both be commit-ish when given; added lines are
    then annotated with blame attribution at ``compare``.
    """
    repo = ensure_repo(Path(repo_path))
    rel = [normalise_repo_path(repo, p) for p in paths] if paths else []
    args = ["diff", "--unified=3", "-M"]
    range_attribution_ref: str | None = None
    if staged:
        args.append("--cached")
        if base:
            args.append(base)
    elif base and compare:
        args.append(f"{base}..{compare}")
        range_attribution_ref = compare
    elif base:
        args.append(base)
    args.append("--")
    args.extend(rel)
    out = run_git(repo, *args)
    files = _parse_diff_text(out)
    if not staged and base is None and compare is None:
        files.extend(_untracked_files(repo, rel))
    if range_attribution_ref:
        _annotate_range_attribution(repo, files, range_attribution_ref)
    return files


def _untracked_files(repo: Path, rel: list[str]) -> list[FileDiff]:
    """Synthesize "added" FileDiffs for untracked worktree files.

    ``git diff`` is silent about untracked files, but an agent that drops a
    new file into the worktree is exactly the change attribution must see.
    """
    out = run_git(repo, "ls-files", "--others", "--exclude-standard", "--", *rel)
    result: list[FileDiff] = []
    for path in [line for line in out.splitlines() if line]:
        target = repo / path
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable or binary: reported by the tracked diff only
        text_lines = content.split("\n")
        if content.endswith("\n"):
            text_lines.pop()  # split() leaves a phantom after the terminator
        lines = [
            DiffLine("added", None, index, text.rstrip("\r"))
            for index, text in enumerate(text_lines, start=1)
        ]
        result.append(FileDiff(path=path, old_path=None, status="added", hunks=[Hunk(0, 0, 1, len(lines), lines)]))
    return result
