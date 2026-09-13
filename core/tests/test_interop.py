"""Another tool's provenance record, read and notarised — M52, `MVP-R7.1`,
`FR-M52-01`…`03`, `SEC-42`/`43`, `AC-59` (MV3-T06).

The differentiating claim is narrow and it has to be held narrow, because the
adjacent claims are all false:

* Meridian can prove a foreign record **said exactly this when Meridian read
  it**. That is what a signed digest buys.
* Meridian cannot say the record was **true**. It did not see the act.
* Meridian therefore never presents a foreign record as its own observation,
  and never above `inferred` (`FR-M52-02`).
* A signature beside somebody else's claim reads as a signature *on* the
  claim unless something stops it (`SEC-43`), so the entry carries the
  sentence that stops it.

The test with teeth is `TestAlteringANotarisedRecord`: the whole feature is
worth nothing if a rewritten note still verifies.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import interop

from test_attribution import ALICE, T0, git


def write_note(repo: Path, ref: str, commit: str, body: str) -> None:
    """Write a note under another tool's ref, the way that tool would.

    Via ``-F`` rather than ``-m``: a note large enough to exercise the size
    cap is also large enough to exceed the Windows command-line limit, and
    the failure there is a FileNotFoundError about the *executable* — which
    is a confusing way to learn you passed too long an argument.
    """
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


@pytest.fixture()
def rival_repo(repo: Path) -> Path:
    """A repository another provenance tool has been working in."""
    head = git(repo, "rev-parse", "HEAD").strip()
    write_note(
        repo,
        "refs/notes/aider",
        head,
        json.dumps(
            {
                "tool": "aider",
                "model": "gpt-4o",
                "files": ["src/app.txt"],
                "session": "2026-03-11T09:00:00Z",
            }
        ),
    )
    return repo


def head_of(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


class TestReadingSomebodyElsesRecord:
    def test_a_note_under_another_tools_ref_is_found(self, rival_repo):
        records = interop.read_foreign_notes(rival_repo)
        assert [record.tool for record in records] == ["aider"]
        assert records[0].kind == "git-note"
        assert records[0].source == "refs/notes/aider"

    def test_it_is_attributed_to_that_tool_and_not_to_meridian(self, rival_repo):
        # FR-M52-02. A record that arrives labelled `meridian` is a record
        # this product is claiming to have produced, which is a lie about
        # provenance in a provenance tool.
        record = interop.read_foreign_notes(rival_repo)[0]
        assert record.tool == "aider"
        assert record.as_wire()["tool"] == "aider"

    def test_it_is_never_above_inferred(self, rival_repo):
        # Meridian did not see the act. It saw a file claiming the act
        # happened, which is the definition of the bottom rung.
        record = interop.read_foreign_notes(rival_repo)[0]
        assert record.confidence == "inferred"
        assert interop.notarisation_entry(record)["observationConfidence"] == "inferred"

    def test_the_confidence_cannot_be_constructed_otherwise(self):
        # A property, not a field, so no caller anywhere can build a
        # ForeignRecord that claims direct observation.
        record = interop.ForeignRecord(
            tool="aider",
            kind="git-note",
            source="refs/notes/aider",
            commit="abc",
            content="x",
            digest=interop.digest_of("x"),
            observed_at="2026-09-13T10:00:00Z",
        )
        with pytest.raises(AttributeError):
            record.confidence = "direct"  # type: ignore[misc]

    def test_meridians_own_notes_are_not_notarised(self, repo):
        # Circular, and it would put a second, weaker copy of something
        # already in the ledger beside it.
        head = head_of(repo)
        write_note(repo, "refs/notes/meridian", head, "our own record")
        assert interop.read_foreign_notes(repo) == []

    def test_a_repository_with_no_notes_is_not_an_error(self, repo):
        # The normal case. A provenance reader that raises on a clean
        # repository would make every other tool's absence look like a fault.
        assert interop.read_foreign_notes(repo) == []

    def test_an_unrecognised_ref_is_named_unknown_rather_than_guessed(self, repo):
        head = head_of(repo)
        write_note(repo, "refs/notes/some-new-tool", head, "a record")
        record = interop.read_foreign_notes(repo)[0]
        assert record.tool == "unknown-tool"
        assert record.source == "refs/notes/some-new-tool"


class TestTrailersAreRecordsToo:
    def test_a_session_trailer_is_read_as_that_tools_record(self, repo):
        (repo / "f.txt").write_text("x\n", encoding="utf-8")
        git(repo, "add", ".")
        git(
            repo,
            "commit",
            "-m",
            "Add a thing\n\nAider-Session: sess-4417\n",
            date=T0 + 600,
        )
        records = interop.read_foreign_trailers(repo, head_of(repo))
        assert [(r.tool, r.source) for r in records] == [("aider", "Aider-Session")]
        assert records[0].content == "sess-4417"

    def test_a_vendor_co_author_is_that_vendors_record(self, repo):
        (repo / "g.txt").write_text("y\n", encoding="utf-8")
        git(repo, "add", ".")
        git(
            repo,
            "commit",
            "-m",
            "Another thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
            date=T0 + 1200,
        )
        records = interop.read_foreign_trailers(repo, head_of(repo))
        assert [r.tool for r in records] == ["claude"]

    def test_a_human_co_author_is_not_a_provenance_record(self, repo):
        # A colleague is not another provenance tool, and notarising their
        # name would be recording a person as a piece of evidence.
        (repo / "h.txt").write_text("z\n", encoding="utf-8")
        git(repo, "add", ".")
        git(
            repo,
            "commit",
            "-m",
            "A third thing\n\nCo-Authored-By: Bob B <bob@example.com>\n",
            date=T0 + 1800,
        )
        assert interop.read_foreign_trailers(repo, head_of(repo)) == []


class TestUntrustedInput:
    """`SEC-42`: parsed under an allow-list, never executed."""

    def test_json_is_parsed_and_only_scalar_fields_surface(self):
        record = interop.ForeignRecord(
            tool="aider",
            kind="git-note",
            source="refs/notes/aider",
            commit="abc",
            content=json.dumps(
                {
                    "model": "gpt-4o",
                    "cost": 0.42,
                    "nested": {"a": {"b": "deep"}},
                    "list": [1, 2, 3],
                }
            ),
            digest="sha256:x",
            observed_at="2026-09-13T10:00:00Z",
        )
        payload = interop.parsed_payload(record)
        assert payload["fields"] == {"model": "gpt-4o", "cost": 0.42}
        # A nested structure from an untrusted file is where a surface ends
        # up rendering something nobody designed for.
        assert "nested" not in payload["fields"]
        assert "list" not in payload["fields"]

    def test_a_format_meridian_does_not_read_is_not_an_error(self):
        record = interop.ForeignRecord(
            tool="aider",
            kind="git-note",
            source="refs/notes/aider",
            commit="abc",
            content="<xml>somebody else's format</xml>",
            digest="sha256:x",
            observed_at="2026-09-13T10:00:00Z",
        )
        payload = interop.parsed_payload(record)
        assert payload == {"format": "text", "parsed": False}

    def test_malformed_json_degrades_to_text(self):
        record = interop.ForeignRecord(
            tool="aider",
            kind="git-note",
            source="refs/notes/aider",
            commit="abc",
            content='{"unterminated": ',
            digest="sha256:x",
            observed_at="2026-09-13T10:00:00Z",
        )
        assert interop.parsed_payload(record)["parsed"] is False

    def test_an_oversized_record_is_truncated_and_says_so(self, repo):
        # A repository can carry a note of any size. A reader that can be
        # made to allocate a gigabyte by someone committing one is a
        # denial-of-service with extra steps; dropping it silently would
        # hide a record instead.
        head = head_of(repo)
        write_note(repo, "refs/notes/aider", head, "x" * (interop.MAX_RECORD_BYTES + 500))
        record = interop.read_foreign_notes(repo)[0]
        assert record.truncated is True
        assert len(record.content.encode("utf-8")) <= interop.MAX_RECORD_BYTES

    def test_nothing_in_this_module_evaluates_what_it_reads(self):
        # The guard, in the style of the spawn and initiation guards: a
        # parser that becomes an evaluator is how somebody else's file
        # becomes somebody else's code.
        import ast

        source = Path(interop.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"eval", "exec", "compile", "__import__", "loads_pickle"}
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), (
            f"interop.py calls {called & forbidden}; SEC-42 forbids executing "
            "a third-party provenance record"
        )


class TestNotarisingIsNotEndorsing:
    """`SEC-43`."""

    def test_the_entry_carries_the_digest_and_not_the_content(self, rival_repo):
        # Notarising, not copying. Taking a copy would make Meridian the
        # custodian of another tool's data, with the retention, erasure and
        # disclosure obligations that follow.
        record = interop.read_foreign_notes(rival_repo)[0]
        entry = interop.notarisation_entry(record)
        assert entry["detail"]["digest"] == record.digest
        assert "content" not in entry["detail"]
        assert record.content not in json.dumps(entry)

    def test_the_entry_says_what_the_signature_does_not_cover(self, rival_repo):
        # A signature beside a claim is read as a signature ON the claim
        # unless something stops it being read that way.
        record = interop.read_foreign_notes(rival_repo)[0]
        entry = interop.notarisation_entry(record)
        note = entry["detail"]["notEndorsed"]
        assert "not its content" in note
        assert "does not vouch" in note

    def test_the_entry_names_the_other_tool_as_vendor(self, rival_repo):
        record = interop.read_foreign_notes(rival_repo)[0]
        assert interop.notarisation_entry(record)["vendor"] == "aider"


class TestAlteringANotarisedRecord:
    """`AC-59`'s second half — the whole feature is worth nothing without it."""

    def test_an_unaltered_record_verifies(self, rival_repo):
        record = interop.read_foreign_notes(rival_repo)[0]
        again = interop.read_foreign_notes(rival_repo)[0]
        verdict = interop.verify_notarisation(record.digest, again)
        assert verdict.ok is True

    def test_a_rewritten_note_is_detected(self, rival_repo):
        record = interop.read_foreign_notes(rival_repo)[0]
        # Somebody rewrites history about what an agent did last March.
        write_note(
            rival_repo,
            "refs/notes/aider",
            record.commit,
            json.dumps({"tool": "aider", "model": "a-cheaper-one", "files": []}),
        )
        after = interop.read_foreign_notes(rival_repo)[0]
        verdict = interop.verify_notarisation(record.digest, after)
        assert verdict.ok is False
        assert verdict.digest_at_notarisation == record.digest
        assert verdict.digest_now == after.digest
        assert "altered since Meridian notarised it" in verdict.detail

    def test_a_removed_record_reads_as_gone_rather_than_altered(self, rival_repo):
        # Different events. A tool cleaning up its own notes is ordinary, and
        # accusing it of tampering would make this the boy who cried wolf.
        record = interop.read_foreign_notes(rival_repo)[0]
        verdict = interop.verify_notarisation(record.digest, None)
        assert verdict.ok is False
        assert verdict.digest_now is None
        assert "no longer in the repository" in verdict.detail

    def test_the_digest_is_over_exact_bytes(self):
        # No normalisation. Stripping trailing whitespace or normalising
        # newlines would make a record that HAD been altered digest
        # identically, which is the one thing this must never do.
        assert interop.digest_of("a\n") != interop.digest_of("a")
        assert interop.digest_of("a \n") != interop.digest_of("a\n")
        assert interop.digest_of("a\r\n") != interop.digest_of("a\n")
