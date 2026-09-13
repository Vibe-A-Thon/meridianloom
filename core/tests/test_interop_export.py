"""Meridian's attributions, in formats other tools consume — `FR-M52-04` (CP1-T03).

What an export must get right is less about the format than about what it
refuses to do. It must not copy code into a file that travels. It must not
fold the lines it cannot attribute into human. It must not present a contested
attribution as settled. And it must not write into somebody's repository
unasked, or read its own notes back as another tool's record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core import interop, interop_export
from meridian_core.attribution.states import (
    ATTRIBUTION_AGENT,
    ATTRIBUTION_HUMAN,
    ATTRIBUTION_UNATTRIBUTED,
)

from test_attribution import ALICE, T0, git
from test_interop import write_note

CLAUDE = "Co-Authored-By: Claude <noreply@anthropic.com>"
SECRET = "proprietary-algorithm-do-not-leak"


def commit(repo: Path, name: str, body: str, subject: str, *trailers: str, step: int = 1) -> str:
    (repo / "src" / name).write_text(body, encoding="utf-8")
    git(repo, "add", ".", date=T0 + step * 600)
    message = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
    git(repo, "commit", "-m", message, date=T0 + step * 600)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture()
def worked(repo: Path) -> dict[str, str]:
    """A human commit, an agent commit, and a formatter sweep."""
    return {
        "human": git(repo, "rev-parse", "HEAD").strip(),
        # The secret opens the file: a span starts on its line, so any leak of
        # line content into a span would carry it.
        "agent": commit(repo, "agent.py", f"# {SECRET}\nx = 1\n", "add agent code", CLAUDE, step=1),
        "sweep": commit(repo, "sweep.py", "y = 2\n", "chore: run prettier", step=2),
    }


class TestTheLineLevelExport:
    def test_it_names_its_schema_and_says_what_it_is_not(self, repo, worked):
        document = interop_export.attribution_export(repo)
        assert document["schema"] == interop_export.EXPORT_SCHEMA
        assert "not another tool's format" in document["notClaimed"]

    def test_every_line_is_counted_in_one_of_three_states(self, repo, worked):
        document = interop_export.attribution_export(repo)
        by_path = {entry["path"]: entry for entry in document["files"]}
        assert by_path["src/agent.py"]["lines"][ATTRIBUTION_AGENT] == 2
        assert by_path["src/app.txt"]["lines"][ATTRIBUTION_HUMAN] == 3
        total = sum(document["totals"].values())
        assert total == sum(sum(entry["lines"].values()) for entry in document["files"])

    def test_lines_it_cannot_attribute_are_not_folded_into_human(self, repo, worked):
        document = interop_export.attribution_export(repo, paths=["src/sweep.py"])
        counts = document["files"][0]["lines"]
        assert counts[ATTRIBUTION_UNATTRIBUTED] == 1
        assert counts[ATTRIBUTION_HUMAN] == 0
        sweep = document["commits"][worked["sweep"]]
        assert sweep["unknownReason"] == "formatter_rewrite"

    def test_it_never_carries_the_code(self, repo, worked):
        assert SECRET not in json.dumps(interop_export.attribution_export(repo))

    def test_consecutive_lines_from_one_commit_are_one_span(self, repo, worked):
        document = interop_export.attribution_export(repo, paths=["src/agent.py"])
        assert document["files"][0]["spans"] == [
            {"startLine": 1, "endLine": 2, "commit": worked["agent"], "state": ATTRIBUTION_AGENT}
        ]

    def test_a_contested_attribution_carries_the_disagreement(self, repo, worked):
        write_note(repo, "refs/notes/aider", worked["agent"], json.dumps({"tool": "aider"}))
        document = interop_export.attribution_export(repo)
        found = interop.reconcile(repo).disagreements
        assert [item.commit for item in found] == [worked["agent"]]
        assert document["commits"][worked["agent"]]["disagreement"] == found[0].digest
        assert document["disagreements"] == [found[0].digest]

    def test_meridians_ledger_evidence_travels_with_the_attribution(self, repo):
        sha = commit(repo, "seen.py", "z = 3\n", "observed work", "Meridian-Ledger: 5", step=3)

        def rows(first, last):
            return [{"seq": 5, "vendor": "codex", "observation_confidence": "direct"}]

        entry = interop_export.attribution_export(repo, ledger_rows=rows)["commits"][sha]
        assert (entry["ledgerRange"], entry["ledgerAgents"], entry["ledgerConfidence"]) == (
            "5",
            ["codex"],
            "direct",
        )

    def test_a_bounded_export_says_it_is_bounded(self, repo, worked, monkeypatch):
        monkeypatch.setattr(interop_export, "MAX_FILES", 1)
        document = interop_export.attribution_export(repo)
        assert document["truncated"] is True
        assert len(document["files"]) == 1

    def test_a_bad_ref_is_an_error_not_an_empty_export(self, repo):
        with pytest.raises(interop_export.ExportError):
            interop_export.attribution_export(repo, ref="no-such-branch")


def notes_on(repo: Path) -> dict[str, dict]:
    listing = git(repo, "notes", "--ref", interop_export.NOTES_REF, "list")
    found = {}
    for line in listing.splitlines():
        blob, sha = line.split()
        found[sha] = json.loads(git(repo, "cat-file", "blob", blob))
    return found


class TestTheNotesExport:
    def test_without_write_nothing_is_written(self, repo, worked):
        plan = interop_export.export_notes(repo)
        assert plan["toWrite"] == 3 and plan["written"] == 0
        assert notes_on(repo) == {}

    def test_with_write_each_commit_gets_one_note_in_the_published_schema(self, repo, worked):
        result = interop_export.export_notes(repo, write=True)
        assert result["written"] == 3
        notes = notes_on(repo)
        assert set(notes) == set(worked.values())
        assert notes[worked["agent"]]["schema"] == interop_export.NOTE_SCHEMA
        assert notes[worked["agent"]]["agents"] == ["claude-code"]
        assert SECRET not in json.dumps(notes)

    def test_a_note_already_saying_the_same_thing_is_left_alone(self, repo, worked):
        interop_export.export_notes(repo, write=True)
        again = interop_export.export_notes(repo, write=True)
        assert (again["toWrite"], again["written"], again["unchanged"]) == (0, 0, 3)

    def test_the_notes_are_written_as_meridian_not_as_whoever_ran_it(self, repo, worked):
        interop_export.export_notes(repo, write=True)
        author = git(repo, "log", "-1", "--format=%an <%ae>", interop_export.NOTES_REF).strip()
        assert author == "Meridian Loom <meridian-loom@localhost>"

    def test_meridians_own_notes_are_never_read_back_as_another_tools_record(self, repo, worked):
        interop_export.export_notes(repo, write=True)
        assert interop.read_foreign_notes(repo) == []
