"""One place that decides how this process invokes git.

Every git call in the sidecar used to be a bare ``subprocess.run`` with no
timeout and an inherited stdin. That is fine until it is not, and the ways it
is not are all the same shape: the command blocks and never returns.

* an ``index.lock`` held by the user's own editor or a concurrent hook;
* a credential prompt — git will happily wait forever on a terminal that is
  not there, and with ``capture_output=True`` it inherits this process's
  stdin, so nothing ever answers it;
* an ``ssh`` host-key confirmation, same story;
* a stalled network mount or a filesystem the OS is still waking up.

The sidecar handles one request at a time, so any of these wedges the whole
governance and metrics layer. There is no recovery path and no message: the
extension simply stops answering, and the user reports that "Meridian froze".
A hung worker in the test suite is what surfaced it, but nothing about it was
specific to tests.

So git is invoked here, once, with:

* **a timeout** — a git command that has not answered in this long is not
  going to; a clean failure the caller can report beats an unbounded wait;
* **stdin closed** — git cannot prompt for something nobody can type;
* **prompting disabled explicitly** — ``GIT_TERMINAL_PROMPT=0`` and empty
  askpass hooks, so git fails fast instead of trying to ask;
* **deterministic output** — no pager, no colour, no path quoting.

Callers keep their own error vocabulary; this only decides how the process is
started and how long it is allowed to take.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: How long any single git command may take before it is treated as hung.
#:
#: Generous on purpose: a ``blame`` over a large file or a ``log`` over deep
#: history is legitimately slow, and killing real work would be a worse bug
#: than the one this guards against. What it rules out is the *unbounded*
#: wait — a prompt nobody answers, a lock nobody releases.
DEFAULT_GIT_TIMEOUT_SECONDS = 120


class GitTimeout(Exception):
    """A git command exceeded its budget and was killed.

    Separate from the callers' own error types because the remedy is
    different: a failing git command is usually the repository's state, while
    a hanging one is usually a lock, a prompt, or a stalled filesystem.
    """

    def __init__(self, args: tuple[str, ...], seconds: int):
        self.args_run = args
        self.seconds = seconds
        super().__init__(
            f"git {' '.join(args)} did not finish within {seconds}s and was "
            "stopped. This usually means a lock another process is holding "
            "(check for a stale .git/index.lock), a credential or host-key "
            "prompt with nothing to answer it, or a stalled filesystem."
        )


def git_timeout_seconds() -> int:
    """The per-command budget, overridable for unusually large repositories.

    Read per call so an operator can change it without a restart. A malformed
    value falls back rather than crashing the sidecar over a diagnostic knob.
    """
    raw = os.environ.get("MERIDIAN_GIT_TIMEOUT_SECONDS")
    if raw:
        try:
            configured = int(raw)
            if configured > 0:
                return configured
        except ValueError:
            pass
    return DEFAULT_GIT_TIMEOUT_SECONDS


def git_environment() -> dict[str, str]:
    """The environment git runs under: never interactive.

    Every one of these disables a different way git can decide to ask a human
    a question. Meridian runs git on behalf of an extension host; there is no
    human at this end of the pipe, and a question here is an unbounded wait.
    """
    env = dict(os.environ)
    env.update(
        {
            # The main one: git refuses rather than prompting for credentials.
            "GIT_TERMINAL_PROMPT": "0",
            # Belt and braces — an askpass helper would bypass the above.
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
            # Never block on an unknown host key.
            "GIT_SSH_COMMAND": env.get(
                "GIT_SSH_COMMAND",
                "ssh -oBatchMode=yes -oStrictHostKeyChecking=accept-new",
            ),
            # Deterministic, parseable output regardless of user config.
            "GIT_PAGER": "cat",
            "LC_ALL": "C",
        }
    )
    return env


def run_git_command(
    repo: Path | str | None,
    *args: str,
    timeout: int | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """Run one git command with the process policy above.

    Returns the CompletedProcess unexamined — a non-zero exit is the caller's
    to interpret, because "no such ref" means something different to the
    attribution engine than it does to the doctor. Only the *hang* is decided
    here, and it raises.
    """
    budget = timeout if timeout is not None else git_timeout_seconds()
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", "--no-pager", *args],
            cwd=str(repo) if repo is not None else None,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            # git cannot prompt for what nobody can type.
            stdin=subprocess.DEVNULL,
            env=git_environment(),
            timeout=budget,
        )
    except subprocess.TimeoutExpired as error:
        raise GitTimeout(args, budget) from error
