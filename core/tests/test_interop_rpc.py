"""Notarisation over the bus, end to end — `AC-59` (MV3-T06).

`test_interop.py` pins the reading and the digesting. This drives the real
`SidecarServer` against a real repository and a real signed ledger, because
`AC-59` is a claim about the product and not about a dataclass:

  *a repository carrying another tool's provenance notes is opened; the notes
  appear attributed to that tool at `inferred`; their digest appears in the
  signed ledger; and the bundle verifies.*

The load-bearing test is `test_a_rewritten_note_is_caught_by_verify`. A
notarisation that cannot detect the alteration it exists to detect is a row
in a database.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import interop, protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

from test_attribution import T0, git


def write_note(repo: Path, ref: str, commit: str, body: str) -> None:
    note_file = repo / ".note-fixture"
    note_file.write_text(body, encoding="utf-8", newline="")
    try:
        subprocess.run(
            [
                "git",
                "-c", "user.name=Aider",
                "-c", "user.email=aider@example.com",
                "notes", "--ref", ref, "add", "-f", "-F", str(note_file), commit,
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        note_file.unlink(missing_ok=True)


AIDER_NOTE = json.dumps(
    {"tool": "aider", "model": "gpt-4o", "files": ["src/app.txt"]}
)


@pytest.fixture()
def rival_repo(repo: Path) -> Path:
    head = git(repo, "rev-parse", "HEAD").strip()
    write_note(repo, "refs/notes/aider", head, AIDER_NOTE)
    return repo


@pytest.fixture()
def server(rival_repo: Path, tmp_path_factory) -> SidecarServer:
    instance = SidecarServer(
        ledger=Ledger(tmp_path_factory.mktemp("ledger"), EphemeralSigningKeyProvider())
    )
    instance.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(rival_repo),
                "tiers": ["flight-recorder"],
            },
        }
    )
    return instance


def call(server: SidecarServer, method: str, params: dict | None = None) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 9, "method": method, "params": params or {}}
    )
    assert "error" not in response, response.get("error")
    return response["result"]


def blob_digest(repo: Path, ref: str) -> str:
    """The digest an auditor would compute, independently, through git.

    Re-derived from the stored blob rather than from the string the fixture
    wrote: git decides what it stores for a note, and a test that assumed
    otherwise would be asserting the fixture rather than the product.
    """
    listing = subprocess.run(
        ["git", "notes", "--ref", ref, "list"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.split()
    raw = subprocess.run(
        ["git", "cat-file", "blob", listing[0]],
        cwd=repo, capture_output=True, check=True,
    ).stdout
    return interop.digest_of_bytes(raw)


def notarised_details(server: SidecarServer) -> list[dict]:
    """What the notarisation entries recorded, out of their blobs.

    The detail is encrypted into the blob store rather than sitting in a
    column, so reading it back is how a reviewer would read it too.
    """
    ledger = server._ensure_ledger()
    out = []
    for row in ledger.query(action_type="foreign_record_notarised", limit=100):
        raw = ledger.read_blob(row["input_ref"], row["blob_key_id"])
        out.append(json.loads(raw.decode("utf-8")))
    return out


class TestAC59:
    def test_the_notes_appear_attributed_to_that_tool_at_inferred(
        self, server, rival_repo
    ):
        result = call(server, "interop/records")
        assert [record["tool"] for record in result["records"]] == ["aider"]
        assert result["records"][0]["confidence"] == "inferred"

    def test_reading_records_nothing(self, server):
        # A surface must be able to show what is there before anybody commits
        # to recording it. Reading that wrote would make looking an action.
        call(server, "interop/records")
        ledger = server._ensure_ledger()
        assert list(ledger.query(action_type="foreign_record_notarised")) == []

    def test_the_digest_lands_in_the_signed_ledger(self, server, rival_repo):
        result = call(server, "interop/notarise")
        assert result["notarised"] == 1
        rows = list(
            server._ensure_ledger().query(action_type="foreign_record_notarised")
        )
        assert len(rows) == 1
        assert rows[0]["vendor"] == "aider"
        assert rows[0]["observation_confidence"] == "inferred"
        assert notarised_details(server)[0]["digest"] == blob_digest(
            rival_repo, "refs/notes/aider"
        )

    def test_the_chain_still_verifies_afterwards(self, server):
        # The bundle half of AC-59: a notarisation entry is an ordinary
        # ledger entry and must not be a special case the verifier trips on.
        call(server, "interop/notarise")
        verdict = server._ensure_ledger().verify()
        assert verdict.ok, verdict.detail

    def test_the_content_is_not_copied_into_the_ledger(self, server):
        # P31: notarise, do not duplicate. A copy would make Meridian the
        # custodian of another tool's data.
        call(server, "interop/notarise")
        recorded = json.dumps(notarised_details(server)[0])
        assert AIDER_NOTE not in recorded
        assert "gpt-4o" not in recorded

    def test_the_entry_says_the_signature_does_not_cover_the_claim(self, server):
        call(server, "interop/notarise")
        assert "does not vouch" in notarised_details(server)[0]["notEndorsed"]

    def test_notarising_twice_records_nothing_new(self, server):
        # Proving the same unchanged thing again adds a row and no evidence.
        first = call(server, "interop/notarise")
        second = call(server, "interop/notarise")
        assert first["notarised"] == 1
        assert second["notarised"] == 0
        assert second["alreadyNotarised"] == 1


class TestTheAlterationIsCaught:
    def test_an_unchanged_record_verifies(self, server):
        call(server, "interop/notarise")
        verdict = call(server, "interop/verify")
        assert verdict["altered"] == 0 and verdict["missing"] == 0
        assert all(entry["ok"] for entry in verdict["verdicts"])

    def test_a_rewritten_note_is_caught_by_verify(self, server, rival_repo):
        """The test the whole feature exists for.

        Somebody rewrites what another tool recorded about an agent's work.
        The note in the repository is mutable and always was; what is not
        mutable is Meridian's signed digest of what it said.
        """
        before = blob_digest(rival_repo, "refs/notes/aider")
        call(server, "interop/notarise")
        head = git(rival_repo, "rev-parse", "HEAD").strip()
        write_note(
            rival_repo,
            "refs/notes/aider",
            head,
            json.dumps({"tool": "aider", "model": "something-cheaper", "files": []}),
        )

        verdict = call(server, "interop/verify")
        assert verdict["altered"] == 1
        bad = next(entry for entry in verdict["verdicts"] if not entry["ok"])
        assert bad["digestAtNotarisation"] == before
        assert bad["digestNow"] != bad["digestAtNotarisation"]
        assert "altered since Meridian notarised it" in bad["detail"]

    def test_a_deleted_note_reads_as_gone_rather_than_altered(
        self, server, rival_repo
    ):
        call(server, "interop/notarise")
        head = git(rival_repo, "rev-parse", "HEAD").strip()
        subprocess.run(
            ["git", "notes", "--ref", "refs/notes/aider", "remove", head],
            cwd=rival_repo,
            capture_output=True,
            check=True,
        )
        verdict = call(server, "interop/verify")
        assert verdict["missing"] == 1
        assert verdict["altered"] == 0
        gone = next(entry for entry in verdict["verdicts"] if not entry["ok"])
        assert gone["digestNow"] is None


class TestTheOrdinaryCase:
    def test_a_repository_with_no_other_tool_is_quiet(self, repo, tmp_path_factory):
        # Most repositories. A provenance reader that reported a fault here
        # would teach people to ignore the surface that matters.
        instance = SidecarServer(
            ledger=Ledger(
                tmp_path_factory.mktemp("ledger"), EphemeralSigningKeyProvider()
            )
        )
        instance.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "workspaceDir": str(repo),
                    "tiers": ["flight-recorder"],
                },
            }
        )
        assert call(instance, "interop/records")["records"] == []
        assert call(instance, "interop/notarise")["notarised"] == 0
        assert call(instance, "interop/verify")["verdicts"] == []


class TestDisagreementsOverTheBus:
    """CP1-T02: `AC-60` through the real sidecar and a real signed ledger."""

    @staticmethod
    def disagree(rival_repo: Path) -> str:
        """The aider note on HEAD, and a cursor note on the same commit."""
        head = git(rival_repo, "rev-parse", "HEAD").strip()
        write_note(rival_repo, "refs/notes/cursor", head, json.dumps({"tool": "cursor"}))
        return head

    @staticmethod
    def recorded(server: SidecarServer) -> tuple[list[dict], list[dict]]:
        rows = server.ledger.query(action_type="provenance_disagreement", limit=100)
        details = [
            json.loads(
                server.ledger.read_blob(
                    row["input_ref"], str(row.get("blob_key_id") or "default")
                ).decode("utf-8")
            )
            for row in rows
        ]
        return details, rows

    def test_reading_reports_the_disagreement_and_writes_nothing(self, server, rival_repo):
        head = self.disagree(rival_repo)
        result = call(server, "interop/conflicts")
        assert [item["commit"] for item in result["disagreements"]] == [head]
        assert result["disagreements"][0]["kind"] == "conflicting"
        assert result["recorded"] == 0
        assert server.ledger.query(action_type="provenance_disagreement", limit=10) == []

    def test_recording_appends_each_disagreement_once_as_digests(self, server, rival_repo):
        self.disagree(rival_repo)
        first = call(server, "interop/conflicts", {"record": True})
        second = call(server, "interop/conflicts", {"record": True})
        assert (first["recorded"], second["recorded"]) == (1, 0)
        details, rows = self.recorded(server)
        assert len(rows) == 1
        # Meridian directly observed the disagreement, and nothing about which
        # record is right.
        assert rows[0]["vendor"] == "meridian"
        assert rows[0]["observation_confidence"] == "direct"
        assert details[0]["digest"] == first["disagreements"][0]["digest"]
        # The aider note names its model; the entry carries a digest of the
        # note, never what the note says.
        assert "gpt-4o" not in json.dumps(details[0])

    def test_an_out_of_range_walk_is_refused(self, server):
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "interop/conflicts",
                "params": {"maxCommits": 0},
            }
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS

    def test_the_chain_still_verifies_after_recording(self, server, rival_repo):
        self.disagree(rival_repo)
        call(server, "interop/conflicts", {"record": True})
        assert server.ledger.verify().ok


class TestExportOverTheBus:
    """CP1-T03: `FR-M52-04` through the real sidecar."""

    NOTES_REF = "refs/notes/meridian-attribution"

    @staticmethod
    def refused(server: SidecarServer, params: dict) -> dict:
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "interop/export", "params": params}
        )
        assert "error" in response, response
        return response["error"]

    def notes(self, repo: Path) -> str:
        return subprocess.run(
            ["git", "notes", "--ref", self.NOTES_REF, "list"],
            cwd=repo, capture_output=True, text=True,
        ).stdout.strip()

    def test_the_line_level_export_is_returned_and_writes_nothing(self, server, rival_repo):
        result = call(server, "interop/export", {"format": "attribution-json"})
        assert result["format"] == "attribution-json"
        assert result["document"]["schema"] == "meridian-loom/attribution-export@1"
        assert self.notes(rival_repo) == ""

    def test_notes_are_written_only_when_write_is_exactly_true(self, server, rival_repo):
        planned = call(server, "interop/export", {"format": "git-notes"})["notes"]
        assert planned["toWrite"] == 1 and planned["written"] == 0
        assert self.notes(rival_repo) == ""

        # A string is not a yes. Writing into somebody's refs needs a boolean.
        stringly = self.refused(server, {"format": "git-notes", "write": "true"})
        assert stringly["code"] == protocol.INVALID_PARAMS
        assert self.notes(rival_repo) == ""

        written = call(server, "interop/export", {"format": "git-notes", "write": True})["notes"]
        assert written["written"] == 1
        assert self.notes(rival_repo) != ""

    def test_an_unknown_format_is_refused(self, server):
        assert self.refused(server, {"format": "exceeds-ink"})["code"] == protocol.INVALID_PARAMS

    def test_a_bad_bound_or_path_list_is_refused(self, server):
        assert self.refused(server, {"format": "git-notes", "maxCommits": 0})["code"] == protocol.INVALID_PARAMS
        assert self.refused(server, {"format": "attribution-json", "paths": "src"})["code"] == protocol.INVALID_PARAMS
