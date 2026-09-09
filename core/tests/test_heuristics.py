"""Human vs. agent change heuristics (FR-M35-02 attribution aid; gaps G3).

Deterministic, rule-based classification of uncommitted changes. Signals:

* burst size — lines added in one timestamp-second sweep (agents write
  whole files at once; humans rarely save N files in the same second);
* multi-line insertion rate — fraction of insertion hunks adding >=5 lines
  at once (editors insert incrementally, file-writing agents in blocks);
* new-file size — a brand-new large file appearing in one write;
* observed-session cross-reference — an active observed agent session
  raises the agent attribution weight for files it covers.

Keystroke cadence is deliberately NOT a signal: agents acting via file
writes leave no keystroke telemetry, and git/filesystem observation cannot
see inter-keystroke timing — the heuristic uses burst/timing patterns from
fs/git timestamps only (documented in heuristics.py).

G3: every result is labelled observationConfidence direct|telemetry|
inferred; heuristic output is never better than telemetry, and the floor
is inferred — labelled, never presented as fact.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from meridian_core.attribution import heuristics

T_EDIT = 1_750_000_000  # pinned edit timestamp for fixtures


def _touch_at(path: Path, content: str, mtime: int = T_EDIT) -> None:
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _apply_edits(base: list[str], edits: dict[int, list[str]]) -> str:
    """Insert/replace after the given base line, keeping hunks separated.

    Edits land >6 context lines apart so git never merges their hunks.
    """
    out: list[str] = []
    for index, text in enumerate(base):
        out.append(text)
        if index in edits:
            out.extend(edits[index])
    return "\n".join(out) + "\n"


@pytest.fixture()
def dirty_repo(repo) -> Path:
    """A committed repo returned to a clean state for per-test edits."""
    return repo


class TestAgentLikeChanges:
    def test_burst_of_new_files_same_second_with_observed_session(self, dirty_repo):
        big = "".join(f"line {i}\n" for i in range(60))
        for name in ("a.py", "b.py", "c.py"):
            _touch_at(dirty_repo / name, big)
        observed = [{"sessionId": "sess-1", "vendor": "claude-code"}]

        result = heuristics.classify(dirty_repo, observed_sessions=observed)

        assert len(result.files) == 3
        for file in result.files:
            assert file.attribution == "agent"
            assert file.agent_weight == 1.0
            assert file.observation_confidence == "telemetry"
            assert file.burst_lines == 180
            assert file.multi_line_insert_rate == 1.0
            assert any("observed session" in r for r in file.rationale)
            assert any("burst" in r for r in file.rationale)

    def test_agent_like_without_observed_session_is_inferred(self, dirty_repo):
        big = "".join(f"line {i}\n" for i in range(60))
        _touch_at(dirty_repo / "solo.py", big)

        result = heuristics.classify(dirty_repo)

        assert result.files[0].attribution == "agent"
        # No observer evidence: the label is the floor, per G3.
        assert result.files[0].observation_confidence == "inferred"

    def test_session_started_after_edit_does_not_cover_file(self, dirty_repo):
        big = "".join(f"line {i}\n" for i in range(60))
        _touch_at(dirty_repo / "solo.py", big, mtime=T_EDIT)
        observed = [
            {
                "sessionId": "sess-2",
                "vendor": "claude-code",
                "startedAt": "2025-07-15T12:00:00+00:00",  # after T_EDIT
            }
        ]

        result = heuristics.classify(dirty_repo, observed_sessions=observed)

        assert result.files[0].observation_confidence == "inferred"


class TestHumanLikeChanges:
    def test_small_single_line_edits_across_files(self, dirty_repo):
        # Two tiny edits, different seconds, no burst, single-line hunks.
        _touch_at(dirty_repo / "src" / "app.txt", "one\ntwo\nthree\nfour\n",
                  mtime=T_EDIT)
        _touch_at(dirty_repo / "README.md", "hello\nworld\n", mtime=T_EDIT + 600)

        result = heuristics.classify(dirty_repo)

        by_path = {file.path: file for file in result.files}
        assert by_path["src/app.txt"].attribution == "human"
        assert by_path["src/app.txt"].agent_weight == 0.0
        assert by_path["README.md"].attribution == "human"
        for file in result.files:
            assert file.observation_confidence == "inferred"
            assert any("incremental" in r for r in file.rationale)


def _commit_base(repo: Path, content: str) -> None:
    """Replace src/app.txt with a long committed base, then dirty it."""
    from test_attribution import git

    (repo / "src" / "app.txt").write_text(content, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "long base")


class TestAmbiguousChanges:
    def test_mixed_signals_report_unattributed(self, dirty_repo):
        # One 10-line block plus four spaced single-line edits: burst says
        # agent, insertion pattern says human — the non-decisive middle
        # band is unattributed, never silently resolved (FR-M41-04, P26).
        base = [f"L{i}" for i in range(80)]
        _commit_base(dirty_repo, "\n".join(base) + "\n")
        edits = {
            10: [f"B{i}" for i in range(10)],  # 10-line block after L10
            30: ["X30"],
            40: ["X40"],
            50: ["X50"],
            60: ["X60"],
        }
        text = _apply_edits(base, edits)
        _touch_at(dirty_repo / "src" / "app.txt", text)

        result = heuristics.classify(dirty_repo, paths=["src/app.txt"])

        (file,) = result.files
        assert file.attribution == "unattributed"
        assert file.unknown_reason == "no_signal"
        assert file.unknown_reason_version >= 1
        assert 0.0 < file.agent_weight < 1.0
        assert file.lines_added == 14

    def test_no_signals_report_unattributed(self, dirty_repo):
        # 8 added lines in three well-separated hunks (6+1+1): rate 0.33,
        # burst 8 — every threshold missed, so the honest answer is
        # unattributed/no_signal.
        base = [f"L{i}" for i in range(80)]
        _commit_base(dirty_repo, "\n".join(base) + "\n")
        edits = {10: [f"H{i}" for i in range(6)], 40: ["X40"], 60: ["X60"]}
        _touch_at(dirty_repo / "src" / "app.txt", _apply_edits(base, edits))

        result = heuristics.classify(dirty_repo, paths=["src/app.txt"])

        assert result.files[0].attribution == "unattributed"
        assert result.files[0].unknown_reason == "no_signal"
        assert result.files[0].agent_weight == 0.5

    def test_clean_tree_reports_no_files(self, dirty_repo):
        result = heuristics.classify(dirty_repo)
        assert result.files == []


class TestDeterminism:
    def test_same_input_same_output(self, dirty_repo):
        big = "".join(f"line {i}\n" for i in range(60))
        _touch_at(dirty_repo / "solo.py", big)

        first = heuristics.classify(dirty_repo)
        second = heuristics.classify(dirty_repo)

        assert first == second

    def test_weights_are_rounded_for_stable_wire_output(self, dirty_repo):
        _touch_at(dirty_repo / "src" / "app.txt", "one\ntwo\nthree\nfour\n")
        (dirty_repo / "mid.py").write_text(
            "".join(f"line {i}\n" for i in range(30)), encoding="utf-8"
        )

        result = heuristics.classify(dirty_repo)

        for file in result.files:
            assert file.agent_weight == round(file.agent_weight, 2)


class TestClassifyRpc:
    def _server(self, repo):
        from meridian_core import protocol
        from meridian_core.server import SidecarServer

        server = SidecarServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "workspaceDir": str(repo),
                },
            }
        )
        assert "result" in response
        return server

    def test_classify_round_trip(self, dirty_repo):
        big = "".join(f"line {i}\n" for i in range(60))
        _touch_at(dirty_repo / "agent.py", big)
        server = self._server(dirty_repo)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "attrib/classify",
                "params": {
                    "repoPath": str(dirty_repo),
                    # Scope to the file under test: the D43 policy scaffold
                    # writes .meridian/policy packs into the workspace on
                    # handshake, and those untracked files legitimately
                    # classify too.
                    "paths": ["agent.py"],
                    "observedSessions": [
                        {"sessionId": "s1", "vendor": "claude-code"}
                    ],
                },
            }
        )
        assert "result" in response, response
        (file,) = response["result"]["files"]
        assert file["path"] == "agent.py"
        assert file["attribution"] == "agent"
        assert file["observationConfidence"] == "telemetry"
        assert file["agentWeight"] == 1.0
        assert file["multiLineInsertRate"] == 1.0
        assert isinstance(file["rationale"], list) and file["rationale"]

    def test_classify_owned_by_flight_recorder(self):
        import bus_types

        owners = [
            capability
            for capability in bus_types.CAPABILITIES
            if "attrib/classify" in capability["rpcMethods"]
        ]
        assert len(owners) == 1
        assert owners[0]["tier"] == "flight-recorder"
