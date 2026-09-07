"""Worktree isolation for hosted agents (FR-M18; F1 Workstream A task 5)."""

from .manager import (
    BRANCH_PREFIX,
    DEFAULT_BASE_BRANCH,
    TRAILER_KEY,
    WORKTREES_DIR,
    ConflictReport,
    WorktreeConflict,
    WorktreeDirtyError,
    WorktreeError,
    WorktreeExistsError,
    WorktreeInfo,
    WorktreeManager,
    WorktreeNotFoundError,
    agent_identity,
)

__all__ = [
    "BRANCH_PREFIX",
    "DEFAULT_BASE_BRANCH",
    "TRAILER_KEY",
    "WORKTREES_DIR",
    "ConflictReport",
    "WorktreeConflict",
    "WorktreeDirtyError",
    "WorktreeError",
    "WorktreeExistsError",
    "WorktreeInfo",
    "WorktreeManager",
    "WorktreeNotFoundError",
    "agent_identity",
]
