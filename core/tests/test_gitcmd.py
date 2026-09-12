"""How this process invokes git, and what it refuses to wait for.

Every git call in the sidecar was a bare ``subprocess.run`` with no timeout
and an inherited stdin. A hung worker in the test suite surfaced it, but
nothing about it was specific to tests: the sidecar handles one request at a
time, so a git command that blocks — an ``index.lock``, a credential prompt
with nobody to answer it, a stalled filesystem — wedges the whole governance
and metrics layer with no message and no recovery. The extension simply stops
answering.

These tests pin the policy that replaced it. They are about the failure mode,
not the happy path: the happy path is exercised by every attribution test in
the suite.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from meridian_core.gitcmd import (
    DEFAULT_GIT_TIMEOUT_SECONDS,
    GitTimeout,
    git_environment,
    git_timeout_seconds,
    run_git_command,
)


class TestGitCannotBeAskedAQuestion:
    """Every way git decides to prompt a human is closed off.

    There is no human at this end of the pipe. A prompt is not a prompt here,
    it is an unbounded wait.
    """

    def test_terminal_prompting_is_disabled(self):
        assert git_environment()["GIT_TERMINAL_PROMPT"] == "0"

    def test_askpass_helpers_cannot_bypass_it(self):
        # An askpass helper configured in the user's environment would
        # happily answer a prompt GIT_TERMINAL_PROMPT was meant to refuse.
        env = git_environment()
        assert env["GIT_ASKPASS"] == ""
        assert env["SSH_ASKPASS"] == ""

    def test_ssh_never_blocks_on_an_unknown_host_key(self):
        assert "BatchMode=yes" in git_environment()["GIT_SSH_COMMAND"]

    def test_an_existing_ssh_command_is_respected(self, monkeypatch):
        # An operator who has configured a jump host keeps it; we are closing
        # a prompt, not overriding their transport.
        monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -J bastion")
        assert git_environment()["GIT_SSH_COMMAND"] == "ssh -J bastion"

    def test_output_is_deterministic_regardless_of_user_config(self):
        env = git_environment()
        assert env["GIT_PAGER"] == "cat"
        assert env["LC_ALL"] == "C"

    def test_stdin_is_closed_so_a_prompt_has_nothing_to_read(self, tmp_path):
        # The real guarantee, end to end: git gets DEVNULL, so anything that
        # tries to read a human's answer gets EOF immediately.
        result = run_git_command(tmp_path, "hash-object", "--stdin")
        assert result.returncode == 0
        # The hash of the empty input, proving stdin was open-and-empty
        # rather than inherited from this process.
        assert result.stdout.strip() == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


class TestGitNeverHoldsAMeridianSecret:
    """SEC-27, extended to git.

    Git runs code the repository controls — hooks, ``core.fsmonitor``,
    textconv and external diff drivers — so git's environment is readable by
    whoever wrote the repository. It used to carry the ledger signing key.
    """

    def test_meridian_variables_are_stripped(self, monkeypatch):
        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        monkeypatch.setenv("MERIDIAN_SOMETHING_NEW", "also-secret")
        env = git_environment()
        assert not [key for key in env if key.startswith("MERIDIAN_")]

    def test_ordinary_variables_still_reach_git(self, monkeypatch):
        # Scrubbing is not emptying: PATH, HOME and friends are how git finds
        # its own config and helpers.
        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        env = git_environment()
        assert env.get("PATH") == os.environ.get("PATH")

    def test_it_agrees_with_the_observer_scrubber(self, monkeypatch):
        # One rule, two implementations — kept apart only so every git call
        # site does not import the observer package. This keeps them honest.
        from meridian_core.observers.isolation import scrub_env

        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        clean, _ = scrub_env()
        mine = git_environment()
        for key in clean:
            if key in mine:
                continue
            # Anything missing from git's environment must be one git's own
            # policy overrides, never a variable scrub_env kept.
            raise AssertionError(f"{key} kept by scrub_env but dropped for git")
        assert not set(mine) - set(clean) - {
            "GIT_TERMINAL_PROMPT",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "GIT_SSH_COMMAND",
            "GIT_PAGER",
            "LC_ALL",
        }

    def test_a_repository_hook_cannot_see_the_signing_key(
        self, tmp_path, monkeypatch
    ):
        """The threat itself, end to end: a hook the repository ships."""
        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret-signing-key")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "probe@example.invalid"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "probe"], cwd=tmp_path, check=True)
        seen = tmp_path / "hook-saw.txt"
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        hook.write_text(
            f'#!/bin/sh\nenv > "{seen.as_posix()}"\n', encoding="utf-8", newline="\n"
        )
        hook.chmod(0o755)
        (tmp_path / "file.txt").write_text("x", encoding="utf-8")
        run_git_command(tmp_path, "add", "file.txt")
        result = run_git_command(tmp_path, "commit", "-q", "-m", "probe")
        assert result.returncode == 0, result.stderr
        # Without this, a hook that silently failed to run would pass the test.
        assert seen.exists(), "the hook never ran, so this proves nothing"
        captured = seen.read_text(encoding="utf-8", errors="replace")
        assert "s3cret-signing-key" not in captured
        assert "MERIDIAN_LEDGER_SIGNING_KEY" not in captured


class TestItRefusesToWaitForever:
    def test_a_command_past_its_budget_raises_rather_than_hanging(
        self, tmp_path, monkeypatch
    ):
        """A TimeoutExpired becomes a GitTimeout, not a bare subprocess error.

        The first version of this test tried to *cause* a hang with `git
        credential fill`, and could not — because closing stdin already fixed
        that case, which is the point of the change. What is left to verify is
        the part this module owns: translating the kill into an error that
        names causes an operator can act on.
        """
        def explode(*args, **kwargs):
            assert kwargs.get("timeout") == 1
            raise subprocess.TimeoutExpired(cmd=kwargs.get("args", "git"), timeout=1)

        monkeypatch.setattr(subprocess, "run", explode)
        with pytest.raises(GitTimeout) as caught:
            run_git_command(tmp_path, "blame", "huge.txt", timeout=1)
        assert caught.value.seconds == 1
        assert caught.value.args_run == ("blame", "huge.txt")

    def test_closing_stdin_already_prevents_the_commonest_hang(self, tmp_path):
        # `git credential fill` reads a request from stdin and, on a terminal,
        # waits. With DEVNULL it gets EOF and exits. This used to be one of
        # the unbounded waits; now it is a fast, ordinary failure.
        result = run_git_command(tmp_path, "credential", "fill", timeout=15)
        assert result is not None

    def test_the_message_names_the_causes_an_operator_can_act_on(self, tmp_path):
        error = GitTimeout(("blame", "x"), 120)
        message = str(error)
        # Not "timed out" — the three things that actually cause it.
        assert "index.lock" in message
        assert "prompt" in message
        assert "filesystem" in message
        assert "120s" in message


class TestTheBudget:
    def test_it_is_generous_enough_not_to_kill_real_work(self):
        # A blame over a large file or a log over deep history is legitimately
        # slow. Killing real work would be a worse bug than the hang.
        assert DEFAULT_GIT_TIMEOUT_SECONDS >= 60

    def test_an_operator_can_raise_it_without_a_restart(self, monkeypatch):
        monkeypatch.setenv("MERIDIAN_GIT_TIMEOUT_SECONDS", "600")
        assert git_timeout_seconds() == 600

    @pytest.mark.parametrize("value", ["", "abc", "0", "-5", "12.5"])
    def test_a_malformed_budget_falls_back_rather_than_crashing(
        self, monkeypatch, value
    ):
        # A diagnostic knob must never be the thing that takes the sidecar
        # down. Nothing about a bad env var justifies refusing to start.
        monkeypatch.setenv("MERIDIAN_GIT_TIMEOUT_SECONDS", value)
        assert git_timeout_seconds() == DEFAULT_GIT_TIMEOUT_SECONDS


class TestItStillRunsGit:
    def test_a_real_command_in_a_real_repository(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        result = run_git_command(tmp_path, "rev-parse", "--is-inside-work-tree")
        assert result.returncode == 0
        assert result.stdout.strip() == "true"

    def test_a_failing_command_is_returned_not_raised(self, tmp_path):
        # The caller interprets a non-zero exit: "no such ref" means something
        # different to attribution than it does to the doctor. Only the hang
        # is decided here.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        result = run_git_command(tmp_path, "rev-parse", "does-not-exist")
        assert result.returncode != 0
        assert result.stderr

    def test_paths_are_not_quoted_so_output_stays_parseable(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "spaced name.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        result = run_git_command(tmp_path, "diff", "--cached", "--name-only")
        assert "spaced name.txt" in result.stdout
        assert '"' not in result.stdout


def test_no_git_call_site_bypasses_the_policy():
    """Nothing in the package spawns git directly any more.

    This is the assertion that keeps the fix from eroding: adding a bare
    ``subprocess.run(["git", ...])`` somewhere reintroduces exactly the hang
    that motivated this module, and nobody would notice until a user's
    extension froze.
    """
    root = Path(__file__).resolve().parents[1] / "meridian_core"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "gitcmd.py":
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '"git"' in stripped and (
                "subprocess.run" in stripped or "subprocess.Popen" in stripped
            ):
                offenders.append(f"{path.relative_to(root)}:{number}")
            # The multi-line form: a bare run(...) whose first list element is git.
            if stripped in {'["git",', '["git",]'} or stripped.startswith('["git", '):
                window = "\n".join(text.splitlines()[max(0, number - 4) : number])
                if "subprocess.run" in window or "subprocess.Popen" in window:
                    offenders.append(f"{path.relative_to(root)}:{number}")
    assert not offenders, (
        "these call git without the timeout and no-prompt policy, so they can "
        f"hang the sidecar indefinitely: {', '.join(sorted(set(offenders)))}. "
        "Use meridian_core.gitcmd.run_git_command."
    )
