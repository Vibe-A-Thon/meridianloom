"""AC-49 / FR-M43-11 / NFR-39 (N2 Workstream D task 18): a third party with
ONLY ``git log`` output can parse a ``Meridian-Ledger:`` trailer and
independently verify the signed ledger root it points at — no Meridian
server, no workspace access, no credentials.

The test builds a real ledger, signs a real tree head, writes the trailer
into a real git commit, then throws away every Meridian object and works
from the raw ``git log --format=%B`` byte stream alone.
"""

from __future__ import annotations

import subprocess

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.ledger import trailer_spec as ts
from meridian_core.trailers import append_trailer


def _head_hex(head, camel: str, snake: str) -> str:
    value = head.get(camel) or head[snake]
    return value.hex() if isinstance(value, bytes) else value


def make_entry(seq: int) -> dict:
    return {
        "story_id": "AC49-1",
        "phase": "review",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": "agent-ac49",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "note",
        "ts_utc": f"2026-09-12T00:00:{seq:06d}Z",
    }


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 4):
        led.append(make_entry(seq))
    led.emit_tree_head_now()
    yield led
    led.close()


@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.name", "AC49 Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "ac49@example.test"],
        cwd=repo,
        check=True,
    )
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    return repo


def git_log_bodies(repo) -> str:
    """Exactly what a third party extracts: commit messages only."""
    return subprocess.run(
        ["git", "log", "--format=%B"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def merge_commit_with_trailer(repo, trailer_value: str | None) -> None:
    message = "Merge governed change AC49"
    if trailer_value is not None:
        message = append_trailer(message, ts.TRAILER_KEY, trailer_value)
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=repo, check=True
    )


def test_ac49_third_party_parse_and_verify_from_git_log(
    ledger: Ledger, git_repo
) -> None:
    head = ledger.latest_tree_head()
    assert head is not None
    trailer_value = ts.trailer_from_tree_head(head, ledger.signing_public_key)
    merge_commit_with_trailer(git_repo, trailer_value)

    # Third party: only the git log stream from here on.
    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)

    assert result.warnings == []
    assert result.latest is not None
    assert ts.verify_trailer(result.latest) is True
    assert result.latest.seq == head["seq"]
    assert result.latest.root.hex() == _head_hex(head, "rootHash", "root_hash")


def test_ac49_tampered_root_fails(ledger: Ledger, git_repo) -> None:
    head = ledger.latest_tree_head()
    assert head is not None
    trailer_value = ts.trailer_from_tree_head(head, ledger.signing_public_key)
    # Flip one hex char of the root digest.
    tampered = trailer_value.replace("root=" + _head_hex(head, "rootHash", "root_hash"), "root=" + "0" * 64, 1)
    merge_commit_with_trailer(git_repo, tampered)

    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)
    assert result.latest is not None
    assert ts.verify_trailer(result.latest) is False


def test_ac49_unknown_key_fails(ledger: Ledger, git_repo) -> None:
    head = ledger.latest_tree_head()
    assert head is not None
    # A DIFFERENT key signs an honestly-formatted trailer: parses cleanly
    # but the signature does not verify against the embedded key.
    stranger = Ledger(git_repo / "stranger-ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 2):
        stranger.append(make_entry(seq))
    stranger.emit_tree_head_now()
    strange_head = stranger.latest_tree_head()
    stranger.close()
    assert strange_head is not None
    trailer_value = ts.trailer_from_tree_head(strange_head, ledger.signing_public_key)

    merge_commit_with_trailer(git_repo, trailer_value)
    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)
    assert result.latest is not None
    assert ts.verify_trailer(result.latest) is False


def test_ac49_no_trailer_is_not_verified(git_repo) -> None:
    merge_commit_with_trailer(git_repo, None)
    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)

    assert result.latest is None
    # "No trailer" must never be readable as a verified state.
    assert all(not ts.verify_trailer(r) for r in result.refs)


def test_malformed_trailer_warns_and_does_not_raise(git_repo) -> None:
    merge_commit_with_trailer(git_repo, "v1 seq=abc root=zz")
    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)

    assert result.refs == []
    assert len(result.warnings) == 1
    assert "FR-M43-11" in result.warnings[0]


def test_unsupported_version_is_rejected_not_misparsed(git_repo) -> None:
    value = (
        "v99 seq=1 root=" + "ab" * 32 + " sig=" + "cd" * 64
        + " key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= at=2026-09-12T00:00:00Z"
    )
    merge_commit_with_trailer(git_repo, value)
    bodies = git_log_bodies(git_repo)
    result = ts.parse_meridian_ledger_trailers(bodies)

    assert result.refs == []
    assert any("NFR-39" in w for w in result.warnings)


def test_format_parse_round_trip(ledger: Ledger) -> None:
    head = ledger.latest_tree_head()
    assert head is not None
    value = ts.trailer_from_tree_head(head, ledger.signing_public_key)
    parsed = ts._parse_value(value)
    assert parsed.seq == head["seq"]
    assert parsed.root.hex() == _head_hex(head, "rootHash", "root_hash")
    assert ts.verify_trailer(parsed) is True
