"""``git blame`` line attribution (FR-M33-02 subset).

Parses ``git blame --porcelain`` into one record per line: commit, author
name/email, author timestamp (ISO 8601 UTC) and line content. Blame never
lands on merge commits — each line is attributed to the commit that
introduced it — and follows renames natively. Uncommitted lines are out of
scope here: ``diff`` covers the working tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ._git import (
    AttributionError,
    ensure_repo,
    epoch_to_iso,
    normalise_repo_path,
    run_git,
)

__all__ = ["AttributionError", "BlameLine", "blame"]


@dataclass(frozen=True)
class BlameLine:
    path: str
    line: int  # 1-based, in the blamed ref's version of the file
    commit: str  # full hex sha; never a merge commit
    author_name: str
    author_email: str
    author_time: str  # ISO 8601 UTC
    content: str  # without the line terminator (CRLF tolerated)


def _tracked_files(repo: Path, ref: str) -> list[str]:
    out = run_git(repo, "ls-tree", "-r", "--name-only", ref, "--")
    return [line for line in out.splitlines() if line]


def blame_with_repo(
    repo_path: Path | str,
    ref: str = "HEAD",
    paths: list[str] | None = None,
) -> tuple[Path, list[BlameLine]]:
    """Like :func:`blame` but also returns the resolved repository toplevel
    (the wire names the repo it actually attributed)."""
    repo = ensure_repo(Path(repo_path))
    return repo, blame(repo, ref=ref, paths=paths)


def blame(
    repo_path: Path | str,
    ref: str = "HEAD",
    paths: list[str] | None = None,
) -> list[BlameLine]:
    """Attribute every line of ``paths`` (or all tracked files) at ``ref``."""
    repo = ensure_repo(Path(repo_path))
    rel = [normalise_repo_path(repo, p) for p in (paths or _tracked_files(repo, ref))]
    if not rel:
        return []
    # git blame takes exactly one file per invocation; loop and concatenate.
    lines: list[BlameLine] = []
    for one in rel:
        out = run_git(repo, "blame", "--porcelain", "-M", "-C", ref, "--", one)
        lines.extend(_parse_porcelain(out))
    if not lines and rel:
        missing = ", ".join(rel)
        raise AttributionError(f"no such path in {ref}: {missing}")
    return lines


# A group header repeats author fields only on its first line, which carries
# the 4th (group count) field; bare "sha orig final" lines are continuations
# inside the group and must keep the current author block.
_GROUP_RE = re.compile(r"^\^?[0-9a-f]{40} \d+ (\d+) \d+$")
_CONT_RE = re.compile(r"^\^?[0-9a-f]{40} \d+ (\d+)$")


def _parse_porcelain(out: str) -> list[BlameLine]:
    lines: list[BlameLine] = []
    header: dict[str, str] = {}
    current_filename = ""
    final_line = 0
    for raw in out.splitlines():
        if raw.startswith("\t"):
            # Content line: the terminating \r of a CRLF file is part of the
            # line ending, not the content.
            lines.append(
                BlameLine(
                    path=current_filename,
                    line=final_line,
                    commit=header["sha"],
                    author_name=header["author"],
                    author_email=header["author-mail"].strip("<>"),
                    author_time=epoch_to_iso(header["author-time"]),
                    content=raw[1:].rstrip("\r"),
                )
            )
            continue
        match = _GROUP_RE.match(raw) or _CONT_RE.match(raw)
        if match:
            header["sha"] = raw.split(" ", 1)[0].lstrip("^")
            header["filename"] = current_filename
            final_line = int(match.group(1))
            continue
        parts = raw.split(" ", 1)
        if parts[0] in (
            "author",
            "author-mail",
            "author-time",
            "committer",
            "committer-mail",
            "committer-time",
            "summary",
            "filename",
        ):
            header[parts[0]] = parts[1] if len(parts) > 1 else ""
            if parts[0] == "filename":
                current_filename = header["filename"]
            continue
        # boundary / previous / author-tz and unknown porcelain keys are
        # informational; skip.
    return lines
