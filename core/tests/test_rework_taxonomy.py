"""Rework reason taxonomy (E-GR-03; FR-M37-02; F1 Workstream B task 14).

FR-M37-02 requires every rejection to carry a reason from "the taxonomy
(E-GR-03)"; no spec document defines the list, so it is DEFINED in
policy/rework-reasons.yaml (versioned, git-backed) and classified here —
the decision rationale lives in
core/meridian_core/rejection/taxonomy.py's docstring.

Covered end to end:

* the policy file parses: eight classes, versioned, default other;
* every class stamps a real rejection record via trust/detectRejections
  (and the conflict detector stamps agent-conflict via pr/conflicts);
* unknown / absent input fails closed: other + free-text note — an
  unclassified record is not allowed;
* the embedded canonical fallback matches the policy file's classes.

Zero model calls (FR-M36-07): classification is string normalisation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.rejection import taxonomy
from meridian_core.server import SidecarServer
from test_pr_conflicts import (
    commit_claude_overlap,
    commit_copilot_edit,
)

POLICY_FILE = Path(__file__).resolve().parents[2] / "policy" / "rework-reasons.yaml"

CANONICAL_IDS = (
    "wrong-requirement",
    "incorrect-implementation",
    "style-convention",
    "missing-tests",
    "security-concern",
    "agent-conflict",
    "obsolete-superseded",
    "other",
)


# -- the taxonomy document ----------------------------------------------------


class TestTaxonomyDocument:
    def test_policy_file_parses(self):
        loaded = taxonomy.load_taxonomy([POLICY_FILE])
        assert loaded.version == 1
        assert [cls.id for cls in loaded.classes] == list(CANONICAL_IDS)
        assert loaded.default.id == "other"
        assert loaded.source == str(POLICY_FILE)

    def test_embedded_canonical_matches_policy_classes(self):
        embedded = taxonomy.load_taxonomy([])
        assert [cls.id for cls in embedded.classes] == list(CANONICAL_IDS)
        assert embedded.default.id == "other"

    def test_missing_file_falls_back_to_embedded(self):
        loaded = taxonomy.load_taxonomy([Path("/nonexistent/rework-reasons.yaml")])
        assert loaded.source == "embedded-canonical"
        assert loaded.is_valid("security-concern")

    def test_malformed_file_falls_back_to_embedded(self, tmp_path: Path):
        broken = tmp_path / "rework-reasons.yaml"
        broken.write_text("version: [not-a-mapping", encoding="utf-8")
        loaded = taxonomy.load_taxonomy([broken])
        assert loaded.source == "embedded-canonical"

    def test_malformed_content_raises_on_direct_parse(self):
        with pytest.raises(taxonomy.TaxonomyError):
            taxonomy.parse_taxonomy("version: 1\ndefault: ghost\nclasses: []\n", "t")
        with pytest.raises(taxonomy.TaxonomyError):
            taxonomy.parse_taxonomy("version: 1\ndefault: other\nclasses:\n  - id: other\n  - id: other\n", "t")


# -- the classifier ------------------------------------------------------------


class TestClassifyReason:
    def test_every_class_id_stamps(self):
        for class_id in CANONICAL_IDS:
            stamp = taxonomy.classify_reason(class_id)
            assert stamp.reason == class_id

    def test_aliases_resolve(self):
        assert taxonomy.classify_reason("style/convention").reason == "style-convention"
        assert taxonomy.classify_reason("obsolete/superseded").reason == "obsolete-superseded"

    def test_case_and_whitespace_normalise(self):
        assert taxonomy.classify_reason("  Security-Concern ").reason == "security-concern"

    def test_unknown_input_fails_closed_with_note(self):
        stamp = taxonomy.classify_reason("ai-generated-slop")
        assert stamp.reason == "other"
        assert "ai-generated-slop" in (stamp.note or "")

    def test_absent_input_fails_closed_with_note(self):
        stamp = taxonomy.classify_reason(None)
        assert stamp.reason == "other"
        assert stamp.note

    def test_other_without_note_gets_a_note(self):
        stamp = taxonomy.classify_reason("other")
        assert stamp.reason == "other"
        assert stamp.note

    def test_caller_note_is_preserved(self):
        stamp = taxonomy.classify_reason("missing-tests", note="no tests for the retry path")
        assert stamp.reason == "missing-tests"
        assert stamp.note == "no tests for the retry path"


# -- end-to-end stamping --------------------------------------------------------


def _git_env(author: dict) -> dict:
    import os

    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": author["name"],
            "GIT_AUTHOR_EMAIL": author["email"],
            "GIT_COMMITTER_NAME": author["name"],
            "GIT_COMMITTER_EMAIL": author["email"],
        }
    )
    return env


def _reverted_repo(base_dir: Path) -> Path:
    """initial commit + a commit whose change a later commit reverts."""
    import subprocess

    def git(repo: Path, *args: str, env: dict | None = None) -> str:
        result = subprocess.run(
            [
                "git",
                "-c", "core.autocrlf=false",
                "-c", "commit.gpgsign=false",
                "-c", "init.defaultBranch=main",
                "-c", "user.name=Fixture",
                "-c", "user.email=fixture@example.com",
                *args,
            ],
            cwd=repo,
            env=env or _git_env({"name": "Fixture", "email": "fixture@example.com"}),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    repo = base_dir / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    (repo / "app.txt").write_text("one\ntwo-agent\nthree\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "agent change")
    (repo / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "revert the agent change")
    return repo


@pytest.fixture()
def server(tmp_path: Path) -> SidecarServer:
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
    instance.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    return instance


def _detect(server: SidecarServer, repo: Path, **extra) -> dict:
    params = {"repoPath": str(repo), "repoId": "edb"}
    params.update(extra)
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "trust/detectRejections", "params": params}
    )
    assert "result" in response, response
    return response["result"]


def _rejection_row(server: SidecarServer) -> dict:
    rows = server.ledger.query(action_type="rejection", limit=10)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("class_id", CANONICAL_IDS)
def test_each_class_stamps_a_rejection_end_to_end(
    server: SidecarServer, tmp_path: Path, class_id: str
):
    repo = _reverted_repo(tmp_path)
    result = _detect(server, repo, reason=class_id, reasonNote=f"classified as {class_id}")
    (rejection,) = result["rejections"]
    assert rejection["reworkReason"] == class_id
    assert rejection["reasonNote"] == f"classified as {class_id}"
    row = _rejection_row(server)
    assert row["rework_reason"] == class_id
    detail = json.loads(row["tool_calls"])
    assert detail[0]["reasonNote"] == f"classified as {class_id}"
    # The mechanical shape is preserved alongside the taxonomy class.
    assert detail[0]["shape"] == "reverted"


def test_unknown_reason_fails_closed_end_to_end(server: SidecarServer, tmp_path: Path):
    repo = _reverted_repo(tmp_path)
    result = _detect(server, repo, reason="made-the-tests-angry")
    (rejection,) = result["rejections"]
    assert rejection["reworkReason"] == "other"
    assert "made-the-tests-angry" in rejection["reasonNote"]
    row = _rejection_row(server)
    assert row["rework_reason"] == "other"
    assert "made-the-tests-angry" in json.loads(row["tool_calls"])[0]["reasonNote"]


def test_absent_reason_stamps_other_with_explanatory_note(
    server: SidecarServer, tmp_path: Path
):
    repo = _reverted_repo(tmp_path)
    result = _detect(server, repo)
    (rejection,) = result["rejections"]
    assert rejection["reworkReason"] == "other"
    assert "requires human classification" in rejection["reasonNote"]
    row = _rejection_row(server)
    assert row["rework_reason"] == "other"


def test_rerun_reports_the_recorded_class(server: SidecarServer, tmp_path: Path):
    repo = _reverted_repo(tmp_path)
    first = _detect(server, repo, reason="incorrect-implementation")
    assert first["rejections"][0]["reworkReason"] == "incorrect-implementation"
    second = _detect(server, repo)  # no reason on the re-run
    assert second["recorded"] == 0
    assert second["rejections"][0]["alreadyRecorded"] is True
    # The recorded class from the first run is reported, not re-classified.
    assert second["rejections"][0]["reworkReason"] == "incorrect-implementation"
    assert len(server.ledger.query(action_type="rejection", limit=10)) == 1


def test_conflict_detector_stamps_agent_conflict_with_note(
    server: SidecarServer, tmp_path: Path
):
    from test_pr_conflicts import git  # noqa: PLC0415 - shared helper

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "app.txt").write_text(
        "".join(f"line {i}\n" for i in range(1, 13)), encoding="utf-8"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    git(repo, "checkout", "-b", "work")
    commit_copilot_edit(repo)
    commit_claude_overlap(repo)

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "pr/conflicts",
            "params": {"repoPath": str(repo), "base": "main", "ref": "HEAD"},
        }
    )
    assert "result" in response, response
    row = _rejection_row(server)
    assert row["rework_reason"] == "agent-conflict"
    detail = json.loads(row["tool_calls"])
    assert detail[0]["class"] == "agent-conflict"
    assert "edited-over-agent-lines" in detail[0]["reasonNote"]
    assert "app.txt" in detail[0]["reasonNote"]
