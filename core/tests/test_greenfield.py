"""Greenfield/brownfield classification (F0 Workstream F task 29; FR-M37-06).

Fixture repositories use pinned dates so per-line touched-code ages are
exact. The rule under test (defaults; both thresholds configurable via the
meridian.greenfieldNewFileRatio / meridian.greenfieldMaxMedianAgeDays
workspace settings):

  greenfield iff new-file ratio >= 0.5
              OR median touched-code age < 30 days
"""

from __future__ import annotations

from pathlib import Path

import pytest

import bus_types

from meridian_core import metrics as metrics_mod
from test_attribution import ALICE, BOB, T0, git

DAY = 86_400
WEEK = 7 * DAY
YEAR = 365 * DAY


def _repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path


def _commit(repo: Path, date: int, message: str = "work", author=BOB) -> str:
    git(repo, "add", ".")
    git(repo, "commit", "-m", message, author=author, date=date)
    return git(repo, "rev-parse", "HEAD").strip()


def _new_file_story(repo: Path) -> list[str]:
    (repo / "src" / "feature.txt").write_text("fresh\ncode\n", encoding="utf-8")
    return [_commit(repo, T0 + 600)]


def _old_code_modification_story(repo: Path) -> list[str]:
    # The touched line was introduced a year before the story commit.
    _new_file_story(repo)
    (repo / "src" / "app.txt").write_text("one\ntwo-old\nthree\n", encoding="utf-8")
    return [_commit(repo, T0 + YEAR)]


def _young_code_modification_story(repo: Path) -> list[str]:
    # The touched line ("two") was introduced by the initial commit, five
    # days before the story modifies it.
    _new_file_story(repo)
    (repo / "src" / "app.txt").write_text("one\ntwo-young\nthree\n", encoding="utf-8")
    return [_commit(repo, T0 + 5 * DAY)]


class TestRatioLimb:
    def test_all_new_files_is_greenfield(self, repo):
        (sha,) = _new_file_story(repo)

        result = metrics_mod.classify(repo, commits=[sha])

        assert result.classification == metrics_mod.GREENFIELD
        assert result.new_files == 1
        assert result.modified_files == 0
        assert result.new_file_ratio == 1.0
        assert result.median_touched_code_age_days is None  # nothing pre-existing touched

    def test_half_new_half_modified_is_greenfield_at_default(self, repo):
        (sha,) = _new_file_story(repo)
        (repo / "src" / "app.txt").write_text("one\ntwo-old\nthree\n", encoding="utf-8")
        second = _commit(repo, T0 + YEAR)

        result = metrics_mod.classify(repo, commits=[sha, second])

        assert result.new_files == 1
        assert result.modified_files == 1
        assert result.new_file_ratio == 0.5
        assert result.classification == metrics_mod.GREENFIELD  # 0.5 >= 0.5

    def test_same_story_is_brownfield_at_higher_threshold(self, repo):
        (sha,) = _new_file_story(repo)
        (repo / "src" / "app.txt").write_text("one\ntwo-old\nthree\n", encoding="utf-8")
        second = _commit(repo, T0 + YEAR)

        result = metrics_mod.classify(
            repo, commits=[sha, second], new_file_ratio_threshold=0.6
        )

        assert result.new_file_ratio == 0.5
        assert result.classification == metrics_mod.BROWNFIELD

    def test_only_modified_files_is_brownfield(self, repo):
        _new_file_story(repo)  # history noise, outside the classified commits
        (repo / "src" / "app.txt").write_text("one\ntwo-old\nthree\n", encoding="utf-8")
        story = _commit(repo, T0 + YEAR)

        result = metrics_mod.classify(repo, commits=[story])

        assert result.new_files == 0
        assert result.new_file_ratio == 0.0
        assert result.classification == metrics_mod.BROWNFIELD


class TestAgeLimb:
    def test_old_code_modification_is_brownfield(self, repo):
        _old_code_modification_story(repo)
        story = git(repo, "rev-parse", "HEAD").strip()

        result = metrics_mod.classify(repo, commits=[story])

        assert result.new_files == 0
        assert result.median_touched_code_age_days == pytest.approx(365.0, abs=0.01)
        assert result.classification == metrics_mod.BROWNFIELD

    def test_young_code_modification_is_greenfield_on_age(self, repo):
        _young_code_modification_story(repo)
        story = git(repo, "rev-parse", "HEAD").strip()

        result = metrics_mod.classify(repo, commits=[story])

        assert result.new_files == 0
        assert result.median_touched_code_age_days == pytest.approx(5.0, abs=0.01)
        assert result.classification == metrics_mod.GREENFIELD

    def test_age_boundary_is_strict(self, repo):
        # Touched code exactly 30 days old: NOT < 30 -> brownfield unless
        # the ratio limb fires.
        _new_file_story(repo)
        (repo / "src" / "app.txt").write_text("one\ntwo-young\nthree\n", encoding="utf-8")
        story = _commit(repo, T0 + 30 * DAY)

        result = metrics_mod.classify(repo, commits=[story])

        assert result.median_touched_code_age_days == pytest.approx(30.0, abs=0.01)
        assert result.classification == metrics_mod.BROWNFIELD

    def test_custom_age_threshold_flips_classification(self, repo):
        _young_code_modification_story(repo)
        story = git(repo, "rev-parse", "HEAD").strip()

        tight = metrics_mod.classify(repo, commits=[story], max_median_age_days=3)
        loose = metrics_mod.classify(repo, commits=[story], max_median_age_days=10)

        assert tight.classification == metrics_mod.BROWNFIELD
        assert loose.classification == metrics_mod.GREENFIELD


class TestRangeForm:
    def test_base_compare_range_classifies(self, repo):
        first = _new_file_story(repo)[0]
        (repo / "src" / "another.txt").write_text("more\n", encoding="utf-8")
        second = _commit(repo, T0 + 2 * WEEK)

        result = metrics_mod.classify(repo, base=first + "~1", compare=second)

        assert result.new_files == 2
        assert result.classification == metrics_mod.GREENFIELD

    def test_neither_commits_nor_range_is_a_clean_error(self, repo):
        from meridian_core.attribution import AttributionError

        with pytest.raises(AttributionError, match="commits list or both base"):
            metrics_mod.classify(repo)

    def test_invalid_thresholds_are_clean_errors(self, repo):
        from meridian_core.attribution import AttributionError

        (sha,) = _new_file_story(repo)
        with pytest.raises(AttributionError, match="new_file_ratio_threshold"):
            metrics_mod.classify(repo, commits=[sha], new_file_ratio_threshold=1.5)
        with pytest.raises(AttributionError, match="max_median_age_days"):
            metrics_mod.classify(repo, commits=[sha], max_median_age_days=0)


class TestClassifyRpc:
    def _server(self, tmp_path):
        from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
        from meridian_core.server import SidecarServer

        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        server = SidecarServer(ledger=ledger)
        return server, ledger

    def _call(self, server, params):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 9, "method": "trust/classify", "params": params}
        )
        assert response is not None
        assert "error" not in response, response.get("error")
        return response["result"]

    def test_round_trip(self, tmp_path):
        repo = _repo(tmp_path / "repo")
        (sha,) = _new_file_story(repo)
        server, ledger = self._server(tmp_path)
        try:
            result = self._call(server, {"repoPath": str(repo), "commits": [sha]})
        finally:
            ledger.close()

        assert result["classification"] == "greenfield"
        assert result["newFiles"] == 1
        assert result["newFileRatio"] == 1.0
        assert result["medianTouchedCodeAgeDays"] is None
        assert result["thresholds"] == {
            "newFileRatioThreshold": 0.5,
            "maxMedianAgeDays": 30,
        }

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/classify" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"
