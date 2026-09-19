"""FR-M36-03 / D23: the opt-in ``commit-msg`` provenance trailer hook.

The hook appends ``Meridian-Ledger: <seq range>`` to every commit whose
staged content the host linked to ledger sequences beforehand (via the
``hook/pending`` RPC, keyed by the ``git write-tree`` hash of the index).
Commits with no pending record pass through untouched — the hook never
blocks a commit and never invents a range.

Lifecycle guarantees (D23):

- **Opt-in**: installed only by the ``hook/install`` RPC (the
  ``meridian.installHook`` command in the extension); nothing installs it
  implicitly.
- **Visible**: doctor's ``git-hooks`` check reports the same facts this
  module produces, and ``hook/status`` drives the UI.
- **One-action removal**: ``hook/remove`` deletes the Meridian hook and
  restores any backed-up foreign hook.
- **Never corrupts**: a foreign ``commit-msg`` is never overwritten — it is
  moved to ``commit-msg.meridian-backup`` and the Meridian hook invokes it
  first (chaining); the trailer edit is trailer-block aware (see
  :mod:`meridian_core.trailers`) and idempotent.

The hooks directory is resolved with ``git rev-parse --git-path hooks`` so a
configured ``core.hooksPath`` (repository, user or system level) is honoured;
the doctor check resolves it the same way.

The commit-msg entry point is executed by the installed shell script as a
plain script (``python <core>/meridian_core/hooks.py commit-msg ...``) so it
works in any POSIX sh, including the Git Bash that serves git's hooks on
Windows, with no PYTHONPATH separator pitfalls.
"""

from __future__ import annotations

# Executed as a script by the installed git hook: make the package importable
# before the absolute imports below run.
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from meridian_core import trailers as trailers_mod
from meridian_core.attribution._git import ensure_repo, run_git

HOOK_FILENAME = "commit-msg"
BACKUP_FILENAME = "commit-msg.meridian-backup"
STATE_DIR = Path(".meridian") / "hooks"
PENDING_FILENAME = "pending.json"
ATTRIBUTIONS_FILENAME = "attributions.jsonl"

#: Marker proving a commit-msg hook is Meridian's (doctor checks for this).
HOOK_MARKER = trailers_mod.MERIDIAN_LEDGER_KEY

_HOOK_SCRIPT = """#!/bin/sh
# {marker}: Meridian Loom commit-msg hook (FR-M36-03, D23).
# Appends "Meridian-Ledger: <seq range>" for commits whose staged content the
# host linked to ledger sequences (hook/pending RPC). Opt-in and removable in
# one action via the meridian.installHook command / hook/remove RPC.
# A pre-existing commit-msg hook was backed up to {backup} and is run first.
set -u
_hook_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
_backup="$_hook_dir/{backup}"
if [ -f "$_backup" ]; then
  if [ -x "$_backup" ]; then
    "$_backup" "$1" || exit $?
  else
    sh "$_backup" "$1" || exit $?
  fi
fi
_repo=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
exec "{python}" "{module_file}" commit-msg --repo "$_repo" "$1"
"""


class HookError(Exception):
    """A clean, user-actionable hook operation failure (never a crash)."""


# -- hooks-dir resolution -----------------------------------------------------


def resolve_hooks_dir(workspace: Path) -> Path:
    """The directory git will run commit-msg hooks from.

    ``git rev-parse --git-path hooks`` honours ``core.hooksPath`` at every
    config level and linked-worktree gitdirs; when git is unavailable or the
    path is relative it is resolved against the workspace. Raises HookError
    when the workspace is not a git repository.
    """
    repo = ensure_repo(workspace)
    try:
        raw = run_git(repo, "rev-parse", "--git-path", "hooks").strip()
    except Exception:  # noqa: BLE001 - fall back to the .git layout below
        raw = ""
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (repo / path).resolve()
    dot_git = repo / ".git"
    if dot_git.is_dir():
        return dot_git / "hooks"
    if dot_git.is_file():
        for line in dot_git.read_text(encoding="utf-8").splitlines():
            if line.startswith("gitdir:"):
                gitdir = Path(line.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (repo / gitdir).resolve()
                return gitdir / "hooks"
    raise HookError(f"cannot locate the git hooks directory in {repo}")


def _is_meridian_hook(path: Path) -> bool:
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


# -- install / status / remove ------------------------------------------------


def install(workspace: Path, python: str | None = None) -> dict[str, Any]:
    """Install (or re-affirm) the Meridian commit-msg hook. Idempotent.

    A foreign commit-msg hook is moved to ``commit-msg.meridian-backup`` and
    chained — never overwritten. Refuses to touch anything when a backup
    already exists and the live hook is foreign again.
    """
    repo = ensure_repo(workspace)
    hooks_dir = resolve_hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / HOOK_FILENAME
    backup = hooks_dir / BACKUP_FILENAME

    if hook.exists() and not _is_meridian_hook(hook):
        if backup.exists():
            raise HookError(
                f"{backup} already exists and {hook} is a new foreign hook — "
                "resolve the conflict manually; Meridian never overwrites "
                "foreign hooks"
            )
        backup.write_bytes(hook.read_bytes())
        hook.unlink()
        chained = True
    else:
        chained = backup.exists()

    already = hook.exists() and _is_meridian_hook(hook)
    if not already:
        interpreter = python or sys.executable or "python3"
        script = _HOOK_SCRIPT.format(
            marker=HOOK_MARKER,
            backup=BACKUP_FILENAME,
            python=_sh_quote(interpreter),
            module_file=_sh_quote(str(Path(__file__).resolve())),
        )
        hook.write_text(script, encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass  # Windows: git runs hooks via its own sh regardless of the bit
    return {
        "installed": True,
        "hookPath": str(hook),
        "chained": chained or backup.exists(),
        "alreadyInstalled": already,
        **({"backupPath": str(backup)} if backup.exists() else {}),
    }


def status(workspace: Path) -> dict[str, Any]:
    """The commit-msg hook facts, shared by the UI and doctor."""
    try:
        repo = ensure_repo(workspace)
        hooks_dir = resolve_hooks_dir(repo)
    except Exception as error:  # noqa: BLE001 - report, never crash
        return {
            "installed": False,
            "foreignHook": False,
            "detail": f"hook status unavailable: {error}",
        }
    hook = hooks_dir / HOOK_FILENAME
    backup = hooks_dir / BACKUP_FILENAME
    if not hook.exists():
        return {
            "installed": False,
            "foreignHook": False,
            "hookPath": str(hook),
            "detail": "commit-msg hook not installed (provenance trailers are opt-in)",
        }
    if _is_meridian_hook(hook):
        return {
            "installed": True,
            "foreignHook": False,
            "hookPath": str(hook),
            "chained": backup.exists(),
            **({"backupPath": str(backup)} if backup.exists() else {}),
            "detail": "Meridian commit-msg hook installed",
        }
    return {
        "installed": False,
        "foreignHook": True,
        "hookPath": str(hook),
        "detail": "a commit-msg hook exists that is not Meridian's — left untouched",
    }


def remove(workspace: Path) -> dict[str, Any]:
    """Remove the Meridian hook; restore a chained foreign hook. One action."""
    repo = ensure_repo(workspace)
    hooks_dir = resolve_hooks_dir(repo)
    hook = hooks_dir / HOOK_FILENAME
    backup = hooks_dir / BACKUP_FILENAME
    if not hook.exists() or not _is_meridian_hook(hook):
        return {
            "removed": False,
            "restoredBackup": False,
            "detail": "no Meridian commit-msg hook to remove; nothing changed",
        }
    hook.unlink()
    restored = False
    if backup.exists():
        backup.replace(hook)
        restored = True
    return {
        "removed": True,
        "restoredBackup": restored,
        **({"backupPath": str(backup)} if restored else {}),
        "detail": (
            "Meridian hook removed; previous commit-msg hook restored"
            if restored
            else "Meridian hook removed"
        ),
    }


def _sh_quote(value: str) -> str:
    """Escape ``value`` for embedding inside POSIX sh double quotes."""
    return (
        value.replace("\\", "\\\\").replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


# -- pending-commit linkage (hook/pending RPC) ---------------------------------


def _state_dir(repo: Path) -> Path:
    return repo / STATE_DIR


def record_pending(
    repo: Path,
    staged_hash: str,
    from_sequence: int,
    to_sequence: int,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Record the seq range a commit's staged content maps to (hook/pending)."""
    if not staged_hash or not isinstance(staged_hash, str):
        raise HookError("stagedHash must be the git write-tree hex of the index")
    if (
        not isinstance(from_sequence, int)
        or not isinstance(to_sequence, int)
        or from_sequence < 1
        or to_sequence < from_sequence
    ):
        raise HookError("need 1 <= fromSequence <= toSequence")
    directory = _state_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    pending_path = directory / PENDING_FILENAME
    records = _read_pending(pending_path)
    # Consumed records are archived to attributions.jsonl at consume time;
    # keep only open ones so pending.json cannot grow without bound.
    records = [record for record in records if not record.get("consumed")]
    records.append(
        {
            "stagedHash": staged_hash,
            "fromSequence": from_sequence,
            "toSequence": to_sequence,
            "recordedAt": recorded_at
            or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
        }
    )
    _write_json(pending_path, records)
    return {"recorded": True, "pendingPath": str(pending_path)}


def _read_pending(pending_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(pending_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def staged_tree_hash(repo: Path) -> str | None:
    """The content key for pending records: the tree hash of the index."""
    try:
        return run_git(repo, "write-tree").strip() or None
    except Exception:  # noqa: BLE001 - unborn branch/empty index: no key
        return None


# -- commit-msg entry point (run by the installed hook script) -----------------


def resolve_pending_for_message(repo: Path, message: str) -> dict[str, Any] | None:
    """The pending record for this commit, consuming it if a trailer lands.

    Returns the record appended to (and its trailer line), or None when the
    message already carries ``Meridian-Ledger`` (idempotent), no pending
    record matches the staged content, or the staged hash is unavailable.
    """
    if trailers_mod.has_trailer(message, trailers_mod.MERIDIAN_LEDGER_KEY):
        return None
    staged_hash = staged_tree_hash(repo)
    if staged_hash is None:
        return None
    pending_path = _state_dir(repo) / PENDING_FILENAME
    records = _read_pending(pending_path)
    match = next(
        (r for r in records if r["stagedHash"] == staged_hash and not r.get("consumed")),
        None,
    )
    if match is None:
        return None
    from_sequence = int(match["fromSequence"])
    to_sequence = int(match["toSequence"])
    value = (
        str(from_sequence)
        if from_sequence == to_sequence
        else f"{from_sequence}-{to_sequence}"
    )
    trailer_line = f"{trailers_mod.MERIDIAN_LEDGER_KEY}: {value}"
    match["consumed"] = True
    match["consumedAt"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    match["trailers"] = trailers_mod.parse_trailers(message)
    # The record is archived below; purge it (and any stale consumed
    # records) so pending.json holds only open linkages.
    _write_json(pending_path, [r for r in records if not r.get("consumed")])
    attributions = _state_dir(repo) / ATTRIBUTIONS_FILENAME
    _state_dir(repo).mkdir(parents=True, exist_ok=True)
    with attributions.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(match, ensure_ascii=False) + "\n")
    return {"record": match, "trailerLine": trailer_line, "value": value}


def commit_msg(repo: Path, msg_file: Path) -> int:
    """Apply the Meridian-Ledger trailer to ``msg_file``; exit code for git.

    Never fails the commit: any error logs to stderr and returns 0, because
    provenance must not block a commit (FR-M36-03 makes trailers opt-in
    evidence, not a gate).
    """
    try:
        message = msg_file.read_text(encoding="utf-8", errors="replace")
        resolved = resolve_pending_for_message(repo, message)
        if resolved is None:
            return 0
        updated = trailers_mod.append_trailer(
            message, trailers_mod.MERIDIAN_LEDGER_KEY, resolved["value"]
        )
        msg_file.write_text(updated, encoding="utf-8", newline="\n")
        return 0
    except Exception as error:  # noqa: BLE001 - never block the commit
        print(f"meridian commit-msg hook: {error}", file=sys.stderr)
        return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian-hooks")
    sub = parser.add_subparsers(dest="command", required=True)
    commit = sub.add_parser("commit-msg", help="commit-msg hook entry point")
    commit.add_argument("--repo", required=True)
    commit.add_argument("msg_file")
    args = parser.parse_args(argv)
    if args.command == "commit-msg":
        return commit_msg(Path(args.repo), Path(args.msg_file))
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
