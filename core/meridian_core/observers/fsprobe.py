"""Filesystem evidence probes shared by observer adapters.

Write-burst detection for the fallback chain's filesystem tier
(FR-M35-02): bounded, non-recursive-into-junk scans of the workspace for
files modified inside an observation window. Pure stdlib, zero model
calls (FR-M36-07), and no Meridian credentials involved (SEC-27).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Directories whose mtimes say nothing about agent activity.
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".meridian",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".cache",
}

# Walk budget: the probe must stay cheap (NFR-29) even in big workspaces.
_MAX_VISITED_DIRS = 2000


@dataclass(frozen=True)
class WriteBurst:
    files: tuple[str, ...]
    latest_mtime: float

    @property
    def file_count(self) -> int:
        return len(self.files)


def recent_writes(
    workspace: Path | str,
    now: datetime,
    window_seconds: float,
) -> WriteBurst | None:
    """Files under ``workspace`` modified in the last ``window_seconds``.

    Returns None when the workspace does not exist (tier unavailable) or
    nothing was written in the window (no evidence). Bounded walk so the
    observation stays within the NFR-29 overhead budget.
    """
    root = Path(workspace)
    if not root.is_dir():
        return None
    epoch = now.timestamp()
    newest: tuple[str, ...] = ()
    latest = 0.0
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root):
        visited += 1
        if visited > _MAX_VISITED_DIRS:
            break
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            try:
                mtime = (Path(dirpath) / name).stat().st_mtime
            except OSError:
                continue
            if not (epoch - window_seconds <= mtime <= epoch + 1):
                continue
            if mtime > latest:
                latest = mtime
            try:
                rel = (Path(dirpath) / name).relative_to(root).as_posix()
            except ValueError:
                rel = name
            newest = (*newest, rel)
    if not newest:
        return None
    return WriteBurst(files=newest, latest_mtime=latest)
