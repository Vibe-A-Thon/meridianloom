"""When provenance records disagree — `FR-M52-05`, `AC-60`, `NFR-53` (CP1-T02).

`AC-60`: *two provenance records claim the same span with different
authorship; the disagreement is reported, and neither is silently preferred.*

The trap is a detector that finds disagreements that are not there. One agent
spelled two ways (`claude` in a trailer, `claude-code` in the ledger), two
co-author lines in one message, a recorder's note that names no agent, a human
who happens to be called Devin: each of those, handled carelessly, is a false
alarm, and a report that cries wolf is a report nobody reads. So half of these
tests pin what is *not* a disagreement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core import interop

from test_attribution import ALICE, T0, git
from test_interop import write_note

CLAUDE = "Co-Authored-By: Claude <noreply@anthropic.com>"
CURSOR = "Co-Authored-By: Cursor Agent <cursor@cursor.com>"


def commit(repo: Path, subject: str, *trailers: str, step: int = 1, author=ALICE) -> str:
    target = repo / "src" / "app.txt"
    target.write_text(target.read_text(encoding="utf-8") + f"{subject}\n", encoding="utf-8")
    git(repo, "add", ".", author=author, date=T0 + step * 600)
    message = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
    git(repo, "commit", "-m", message, author=author, date=T0 + step * 600)
    return git(repo, "rev-parse", "HEAD").strip()


def disagreements_on(repo: Path, sha: str, rows=None):
    result = interop.reconcile(repo, ledger_rows=rows)
    return [item for item in result.disagreements if item.commit == sha], result


class TestWhatIsNotADisagreement:
    def test_one_agent_spelled_two_ways_is_one_agent(self):
        assert interop.canonical_agent("claude") == "claude-code"
        assert interop.canonical_agent("claude-code") == "claude-code"
        assert interop.canonical_agent("github-copilot") == "copilot"
        # Not guessed into an agent: an unfamiliar name is not one.
        assert interop.canonical_agent("Ada Lovelace") is None

    def test_a_name_that_contains_an_agents_name_is_not_that_agent(self):
        # A note field naming "devin-helper-script" is somebody's script, and
        # substring matching would turn it into a claim that Devin did the work.
        assert interop.canonical_agent("Devin Smith") is None
        assert interop.canonical_agent("devin-helper-script") is None
        assert interop.canonical_agent("aider-wrapper") is None

    def test_an_agents_name_without_a_bot_marker_is_not_a_bot_author(self):
        # A person whose git name is "Copilot" typed a name; only a [bot]
        # identity or an agent's known commit address is an author claim.
        assert interop.author_claim("Copilot", "someone@example.com") is None
        assert interop.author_claim("Copilot[bot]", "someone@example.com") is not None

    def test_two_co_author_lines_are_one_statement_naming_two_agents(self, repo):
        sha = commit(repo, "pairing", CLAUDE, CURSOR)
        claims = interop.record_claims(interop.read_foreign_trailers(repo, sha))
        assert [(claim.claimant, claim.agents) for claim in claims] == [
            ("Co-Authored-By", ("claude-code", "cursor"))
        ]
        found, _ = disagreements_on(repo, sha)
        assert found == []

    def test_a_tool_and_its_own_session_trailer_agree(self, repo):
        sha = commit(repo, "aider work", "Aider-Session: s-1")
        write_note(repo, "refs/notes/aider", sha, json.dumps({"model": "gpt-4o"}))
        found, result = disagreements_on(repo, sha)
        assert found == []
        assert result.agreeing == 1

    def test_a_recorder_note_that_names_no_agent_claims_nothing(self, repo):
        sha = commit(repo, "claude work", CLAUDE)
        write_note(repo, "refs/notes/gitbutler", sha, json.dumps({"branch": "feature"}))
        found, _ = disagreements_on(repo, sha)
        assert found == []

    def test_a_human_called_devin_is_a_human(self):
        assert interop.author_claim("Devin Smith", "devin@example.com") is None
        bot = interop.author_claim(
            "devin-ai-integration[bot]",
            "devin-ai-integration[bot]@users.noreply.github.com",
        )
        assert bot is not None and bot.agents == ("devin",)

    def test_a_malformed_ledger_range_is_not_read_as_one(self):
        assert interop.ledger_ranges("x\n\nMeridian-Ledger: 7") == [(7, 7)]
        assert interop.ledger_ranges("x\n\nMeridian-Ledger: 3-4") == [(3, 4)]
        assert interop.ledger_ranges("x\n\nMeridian-Ledger: 3-") == []
        assert interop.ledger_ranges("x\n\nMeridian-Ledger: 9-4") == []

    def test_meridians_own_governance_entries_are_not_an_authorship_claim(self):
        rows = [{"seq": 5, "vendor": "meridian", "observation_confidence": "direct"}]
        assert interop.ledger_claim(rows, [(5, 5)]) is None


class TestTwoRecordsDisagree:
    def test_the_disagreement_is_reported_with_both_claims(self, repo):
        sha = commit(repo, "who wrote this", CLAUDE)
        write_note(repo, "refs/notes/aider", sha, json.dumps({"tool": "aider"}))
        found, _ = disagreements_on(repo, sha)
        assert len(found) == 1
        assert found[0].kind == interop.CONFLICTING
        assert sorted(claim.agents for claim in found[0].claims) == [("aider",), ("claude-code",)]

    def test_no_claim_is_preferred(self, repo):
        sha = commit(repo, "who wrote this", CLAUDE)
        write_note(repo, "refs/notes/aider", sha, json.dumps({"tool": "aider"}))
        wire = disagreements_on(repo, sha)[0][0].as_wire()
        # Nothing in the shape can carry a verdict: no winner, no ranking.
        assert set(wire) == {"commit", "kind", "claims", "digest", "notResolved"}
        assert "no claim is preferred" in wire["notResolved"]

    def test_meridians_own_ledger_is_not_preferred_either(self, repo):
        sha = commit(repo, "observed by meridian", "Meridian-Ledger: 3-4")
        write_note(repo, "refs/notes/aider", sha, json.dumps({"tool": "aider"}))

        def rows(first, last):
            assert (first, last) == (3, 4)
            return [
                {"seq": 3, "vendor": "copilot", "observation_confidence": "direct"},
                {"seq": 4, "vendor": "meridian", "observation_confidence": "direct"},
            ]

        disagreement = disagreements_on(repo, sha, rows)[0][0]
        own = next(claim for claim in disagreement.claims if claim.claimant == "meridian-ledger")
        assert (own.agents, own.confidence, own.evidence) == (("copilot",), "direct", "ledger 3-4")
        assert disagreement.kind == interop.CONFLICTING
        assert set(disagreement.as_wire()) == {"commit", "kind", "claims", "digest", "notResolved"}

    def test_overlapping_but_different_claims_are_incomplete(self, repo):
        sha = commit(repo, "pairing", CLAUDE, CURSOR)
        write_note(repo, "refs/notes/cursor", sha, json.dumps({"tool": "cursor"}))
        found, _ = disagreements_on(repo, sha)
        assert found[0].kind == interop.INCOMPLETE

    def test_a_recorder_note_that_names_an_agent_is_a_claim(self, repo):
        sha = commit(repo, "cursor work", CURSOR)
        write_note(repo, "refs/notes/exceeds-ink", sha, json.dumps({"tool": "claude"}))
        found, _ = disagreements_on(repo, sha)
        assert found[0].kind == interop.CONFLICTING
        assert any(
            claim.tool == "exceeds-ink" and claim.agents == ("claude-code",)
            for claim in found[0].claims
        )

    def test_the_report_carries_digests_not_what_the_records_say(self, repo):
        sha = commit(repo, "who", CLAUDE)
        secret = "private-session-transcript-XYZ"
        write_note(repo, "refs/notes/aider", sha, json.dumps({"tool": "aider", "transcript": secret}))
        found, _ = disagreements_on(repo, sha)
        assert secret not in json.dumps(found[0].as_wire())

    def test_the_same_disagreement_has_the_same_digest_on_every_read(self, repo):
        sha = commit(repo, "who", CLAUDE)
        write_note(repo, "refs/notes/aider", sha, json.dumps({"tool": "aider"}))
        first = disagreements_on(repo, sha)[0][0].digest
        assert disagreements_on(repo, sha)[0][0].digest == first


class TestTheWalk:
    def test_a_walk_that_stops_early_says_so(self, repo):
        for step in range(1, 5):
            commit(repo, f"change {step}", step=step)
        stopped = interop.reconcile(repo, max_commits=2)
        assert (stopped.examined, stopped.truncated) == (2, True)
        assert interop.reconcile(repo, max_commits=50).truncated is False

    def test_a_note_on_a_commit_older_than_the_walk_is_still_compared(self, repo):
        old = commit(repo, "old work", CLAUDE, step=1)
        for step in range(2, 5):
            commit(repo, f"newer {step}", step=step)
        write_note(repo, "refs/notes/aider", old, json.dumps({"tool": "aider"}))
        result = interop.reconcile(repo, max_commits=2)
        assert [item.commit for item in result.disagreements] == [old]

    def test_a_repository_with_nothing_to_compare_reports_nothing(self, repo):
        result = interop.reconcile(repo)
        assert result.disagreements == ()
        assert result.examined == 1

    def test_a_bad_ref_is_an_error_not_an_empty_report(self, repo):
        with pytest.raises(interop.InteropError):
            interop.reconcile(repo, ref="no-such-branch")
