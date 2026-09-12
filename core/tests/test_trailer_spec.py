"""AC-49 / FR-M43-11 / NFR-39 — evidence outlives the tool.

The claim being tested is not "Meridian can read its own trailer". It is that
a **third party** can start from a commit in somebody else's repository and
finish at verified evidence, using only the published specification and the
reference tools, on a machine with no Meridian installation.

So the parser is exercised the way that third party would reach it: as a
subprocess, by path, with ``PYTHONPATH`` emptied so nothing in this repository
is importable. A test that imported ``meridian_core`` to check the standalone
path would be testing the opposite of the requirement.

The specification is ``docs/spec/meridian-ledger-trailer.md`` version 1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAILER_TOOL = REPO_ROOT / "verifier" / "meridian_trailer.py"
VERIFY_TOOL = REPO_ROOT / "verifier" / "verify.py"
SPEC = REPO_ROOT / "docs" / "spec" / "meridian-ledger-trailer.md"


def run_tool(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    """The reference parser as an outsider runs it: no Meridian on the path."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ""
    return subprocess.run(
        [sys.executable, str(TRAILER_TOOL), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=tempfile.gettempdir(),  # nowhere near the repository
        env=environment,
    )


class TestTheSpecificationIsPublished:
    def test_the_document_exists_and_is_versioned(self):
        # FR-M43-11 asks for a *published, versioned* specification. A parser
        # with no document is an implementation, not a specification.
        assert SPEC.is_file()
        text = SPEC.read_text(encoding="utf-8")
        assert "**Version:** 1" in text
        assert "Meridian-Ledger" in text

    def test_the_reference_parser_ships_inside_the_extension(self):
        # The specification names the installed location. If packaging stops
        # staging it, a third party following the document finds nothing.
        packager = (REPO_ROOT / "scripts" / "package-extension.mjs").read_text(
            encoding="utf-8"
        )
        assert "meridian_trailer.py" in packager

    def test_it_needs_nothing_installed(self):
        # NFR-39: the reference tools are standard library only, so "verify on
        # a clean machine" does not quietly mean "after pip install".
        source = TRAILER_TOOL.read_text(encoding="utf-8")
        third_party = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from "))
            and not line.startswith(("from __future__",))
            and line.split()[1].split(".")[0]
            not in {"json", "re", "sys", "typing"}
        ]
        assert not third_party, third_party


class TestParsingFromGitLogAlone:
    def test_a_range_resolves(self):
        result = run_tool(stdin="Fix the thing\n\nMeridian-Ledger: 412-418\n")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["trailer"] == {
            "from": 412,
            "to": 418,
            "count": 7,
        }

    def test_a_single_sequence_is_a_one_entry_range(self):
        result = run_tool(stdin="Subject\n\nMeridian-Ledger: 9\n")
        assert json.loads(result.stdout)["trailer"] == {"from": 9, "to": 9, "count": 1}

    def test_an_ordinary_commit_is_not_an_error(self):
        # Most commits in most repositories have no trailer. Treating that as
        # a failure would make the tool useless on a real history.
        result = run_tool(stdin="Just a commit\n\nCo-Authored-By: A <a@b.c>\n")
        assert result.returncode == 0
        assert json.loads(result.stdout)["trailer"] is None

    def test_the_trailer_must_be_in_the_trailer_block(self):
        # A line in prose that looks like a trailer is not one — otherwise
        # quoting the trailer while discussing it would change what the commit
        # claims.
        message = (
            "Subject\n\n"
            "We considered writing Meridian-Ledger: 1-5 here but did not.\n\n"
            "Co-Authored-By: A <a@b.c>\n"
        )
        assert json.loads(run_tool(stdin=message).stdout)["trailer"] is None

    @pytest.mark.parametrize(
        "value",
        ["", "abc", "1-", "-5", "0", "5-1", "1 - 5", "1,5", "1-2-3", "０-５"],
    )
    def test_a_malformed_value_is_refused_not_guessed(self, value):
        # A misread range reports evidence for the wrong entries, which is
        # worse than reporting none.
        result = run_tool(stdin=f"Subject\n\nMeridian-Ledger: {value}\n")
        assert result.returncode == 1, result.stdout

    def test_two_conflicting_trailers_are_refused(self):
        message = "Subject\n\nMeridian-Ledger: 1-5\nMeridian-Ledger: 9-12\n"
        result = run_tool(stdin=message)
        assert result.returncode == 1
        assert "conflicting" in result.stderr


class TestResolvingToABundleRange:
    @staticmethod
    def bundle(sequences) -> str:
        path = Path(tempfile.mkdtemp()) / "bundle.json"
        path.write_text(
            json.dumps({"entries": [{"sequence": s} for s in sequences]}),
            encoding="utf-8",
        )
        return str(path)

    def test_a_covering_bundle_passes(self, tmp_path):
        message = tmp_path / "msg.txt"
        message.write_text("Subject\n\nMeridian-Ledger: 3-5\n", encoding="utf-8")
        result = run_tool(
            "--message-file", str(message), "--bundle", self.bundle([1, 2, 3, 4, 5, 6])
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["covered"] is True

    def test_a_gap_is_reported_by_sequence(self, tmp_path):
        # "Does not cover this commit" and "entry 4 is missing" are very
        # different conversations to have with an auditor.
        message = tmp_path / "msg.txt"
        message.write_text("Subject\n\nMeridian-Ledger: 3-5\n", encoding="utf-8")
        result = run_tool(
            "--message-file", str(message), "--bundle", self.bundle([3, 5])
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert report["covered"] is False
        assert report["missing"] == [4]


def test_ac49_a_third_party_goes_from_git_log_to_verified_evidence(tmp_path):
    """The acceptance criterion itself, end to end.

    A real repository, a real commit carrying a real trailer, a real exported
    bundle — then the two reference tools, by path, with nothing of Meridian
    importable. Every step is the one the specification tells an outsider to
    take.
    """
    from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
    from meridian_core.ledger.bundle import build_bundle

    # --- what the customer keeps: a ledger, and a repository ----------------
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for index in range(1, 6):
        ledger.append(
            {
                "story_id": "AC-49",
                "phase": "build",
                "loop_id": "L2-task",
                "loop_iteration": 1,
                "actor_id": "developer-agent",
                "actor_version": "1.0.0",
                "actor_kind": "role",
                "policy_version": "policy-v1",
                "action_type": "diff",
                "ts_utc": f"2026-09-01T00:00:{index:06d}Z",
            }
        )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(build_bundle(ledger, {})), encoding="utf-8"
    )
    ledger.close()

    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (
        ["init", "-q"],
        ["config", "user.email", "dev@example.invalid"],
        ["config", "user.name", "dev"],
    ):
        subprocess.run(["git", *argv], cwd=repo, check=True)
    (repo / "file.txt").write_text("work", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Add the thing\n\nMeridian-Ledger: 2-4"],
        cwd=repo,
        check=True,
    )

    # --- what the third party does, from here on ---------------------------
    # 1. Read the message with git alone.
    message = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Meridian-Ledger: 2-4" in message

    # 2. Resolve it to a range, and check the bundle covers it.
    message_file = tmp_path / "msg.txt"
    message_file.write_text(message, encoding="utf-8")
    resolved = run_tool(
        "--message-file", str(message_file), "--bundle", str(bundle_path)
    )
    assert resolved.returncode == 0, resolved.stderr
    report = json.loads(resolved.stdout)
    assert report["trailer"] == {"from": 2, "to": 4, "count": 3}
    assert report["covered"] is True

    # 3. Verify the bundle with the shipped verifier — the step that makes
    #    the range mean anything. Same isolation: no Meridian importable.
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ""
    verified = subprocess.run(
        [sys.executable, str(VERIFY_TOOL), str(bundle_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=tempfile.gettempdir(),
        env=environment,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr

    # 4. And the honest part: the verifier states what it did not establish
    #    rather than letting a reader infer more than was proven.
    assert "witness" in (verified.stdout + verified.stderr).lower()


# -- FR-M43-13: what a customer keeps when they leave --------------------------


class TestAnExportStaysReadableAfterMeridian:
    """The bundle has to answer questions its reader cannot ask us.

    Someone reading an export years later, without Meridian and without us,
    needs to know which schema the entries were written under and whether a
    missing field means "nothing happened" or "policy said do not record it".
    Neither was in the bundle, and neither is recoverable from the entries.
    """

    @staticmethod
    def exported(tmp_path):
        from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
        from meridian_core.ledger.bundle import build_bundle

        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        try:
            return build_bundle(ledger, {})
        finally:
            ledger.close()

    def test_it_states_the_schema_its_entries_were_written_under(self, tmp_path):
        from meridian_core.ledger import schema

        bundle = self.exported(tmp_path)
        # Not the bundle's own format version — the entry schema, which has
        # changed across versions. A reader without it has to guess.
        assert bundle["schemaVersion"] == schema.SCHEMA_VERSION
        assert bundle["formatVersion"] == 1

    def test_it_states_what_was_captured_and_what_was_withheld(self, tmp_path):
        from meridian_core.ledger import privacy, redaction

        section = self.exported(tmp_path)["redaction"]
        assert section["defaultProfile"] == privacy.DEFAULT_PROFILE
        # The marker is included verbatim so a reader can search for it
        # instead of having to already know it.
        assert section["redactedMarker"] == redaction.REDACTED
        for name, profile in privacy.COLLECTION_PROFILES.items():
            assert section["profiles"][name]["capturesInput"] == profile.capture_input
        # And the distinction is stated, not left to be inferred.
        assert "never produced" in section["note"]

    def test_the_new_fields_are_covered_by_the_signature(self, tmp_path):
        # A section describing how to read the evidence is itself evidence. If
        # it sat outside the signed digest, anyone could relabel a redacted
        # export as a full one.
        import hashlib

        from meridian_core.ledger import canonical

        bundle = self.exported(tmp_path)
        core = {key: value for key, value in bundle.items() if key != "signature"}
        assert (
            hashlib.sha256(canonical.canonical_json(core)).hexdigest()
            == bundle["signature"]["digest"]
        )
        tampered = dict(core)
        tampered["redaction"] = {**core["redaction"], "defaultProfile": "content_full"}
        assert (
            hashlib.sha256(canonical.canonical_json(tampered)).hexdigest()
            != bundle["signature"]["digest"]
        )
