"""trailers/parse over the bus (FR-M36-03, F0 Workstream E task 24).

Real git repositories carry every vendor's Co-Authored-By variants; the RPC
surfaces per-commit attribution records plus Meridian-Ledger ranges. Runs
against the dispatch layer with an injected ledger like the other RPC tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import bus_types

from meridian_core import protocol
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.server import SidecarServer
from test_attribution import T0, git


@pytest.fixture()
def server(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
    yield instance
    ledger.close()


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    assert response is not None and response["id"] == request_id
    return response


def result(server, method, params=None):
    response = call(server, 7, method, params or {})
    assert "error" not in response, response["error"]
    return response["result"]


@pytest.fixture()
def vendor_repo(tmp_path):
    """A real repository with one commit per vendor trailer variant."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "chore: base", date=T0)

    commits = {}
    variants = [
        ("claude", "Co-Authored-By: Claude <noreply@anthropic.com>"),
        ("copilot", "Co-Authored-By: GitHub Copilot <copilot@github.com>"),
        ("cursor", "Co-Authored-By: Cursor <cursor@anysphere.inc>"),
        ("generic", "Co-Authored-By: Ada Lovelace <ada@example.com>"),
        ("meridian", "Co-Authored-By: Meridian <meridian@meridianloom.dev>"),
    ]
    for index, (vendor, line) in enumerate(variants, start=1):
        (repo / "f.txt").write_text(f"base\n{vendor}\n", encoding="utf-8")
        git(repo, "add", ".")
        message = (
            f"feat: {vendor} change\n\n"
            f"{line}\n"
            "Co-Authored-By: Partner Dev <partner@example.com>\n"
        )
        if vendor == "claude":
            message += "Meridian-Ledger: 7-9\n"
        git(repo, "commit", "-m", message, date=T0 + index)
        commits[vendor] = git(repo, "rev-parse", "HEAD").strip()
    return repo, commits


def commit_by_id(commits_payload, commit_id):
    return next(c for c in commits_payload if c["commit"] == commit_id)


class TestTrailersParse:
    def test_vendors_parsed_from_real_history(self, server, vendor_repo):
        repo, commits = vendor_repo
        payload = result(server, "trailers/parse", {"repoPath": str(repo)})
        found = {c["commit"]: c for c in payload["commits"]}
        assert set(found) == set(commits.values())

        claude = found[commits["claude"]]
        vendors = {a["vendor"] for a in claude["attributions"]}
        assert vendors == {"claude", "generic"}
        claude_record = next(
            a for a in claude["attributions"] if a["vendor"] == "claude"
        )
        assert claude_record["email"] == "noreply@anthropic.com"
        assert claude_record["meridianAuthored"] is False
        # The base commit has no Co-Authored-By: it is not in the stream.
        assert claude["meridianLedger"] == ["7-9"]

    def test_meridian_commit_is_reserved(self, server, vendor_repo):
        repo, commits = vendor_repo
        payload = result(server, "trailers/parse", {"repoPath": str(repo)})
        found = {c["commit"]: c for c in payload["commits"]}
        meridian = found[commits["meridian"]]
        record = meridian["attributions"][0]
        assert record["vendor"] == "meridian"
        assert record["meridianAuthored"] is True

    def test_ref_and_since_filter_the_walk(self, server, vendor_repo):
        repo, commits = vendor_repo
        payload = result(
            server,
            "trailers/parse",
            {"repoPath": str(repo), "ref": f"{commits['cursor']}..HEAD"},
        )
        vendors = {
            a["vendor"] for c in payload["commits"] for a in c["attributions"]
        }
        assert "cursor" not in vendors
        assert {"generic", "meridian"} <= vendors

    def test_since_cutoff_excludes_older_commits(self, server, vendor_repo):
        repo, commits = vendor_repo
        payload = result(
            server,
            "trailers/parse",
            {"repoPath": str(repo), "since": "2023-11-14T22:13:25Z"},
        )
        # T0 + 1..4 are before the cutoff; only the meridian commit remains.
        assert [c["commit"] for c in payload["commits"]] == [commits["meridian"]]

    def test_message_param_parses_without_git(self, server):
        payload = result(
            server,
            "trailers/parse",
            {
                "message": (
                    "fix: direct parse\n\n"
                    "Co-Authored-By: GitHub Copilot <copilot@github.com>\n"
                    "Meridian-Ledger: 42\n"
                )
            },
        )
        assert len(payload["commits"]) == 1
        entry = payload["commits"][0]
        assert entry["commit"] is None
        assert entry["attributions"][0]["vendor"] == "github-copilot"
        assert entry["meridianLedger"] == ["42"]

    def test_repo_resolution_and_errors(self, server, vendor_repo):
        # Neither repoPath nor a workspace handshake: actionable INVALID_PARAMS.
        response = call(server, 3, "trailers/parse", {})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        response = call(server, 4, "trailers/parse", {"repoPath": str(vendor_repo[0].parent)})
        assert response["error"]["code"] == protocol.INVALID_PARAMS


class TestTierOwnership:
    def test_trailers_parse_owned_by_provenance_hooks(self):
        methods = [
            method
            for capability in bus_types.CAPABILITIES
            if capability["id"] == "recorder.provenance-hooks"
            for method in capability["rpcMethods"]
        ]
        assert "trailers/parse" in methods
        # Single ownership across the whole registry.
        claims = [
            method
            for capability in bus_types.CAPABILITIES
            for method in capability["rpcMethods"]
        ]
        assert len(claims) == len(set(claims))
