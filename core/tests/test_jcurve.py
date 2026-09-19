"""The adoption J-curve (FR-M37-05; F1 Workstream E task 23).

Team-level throughput and stability before and after adoption, so the
initial productivity dip is visible as a phase rather than mistaken for
failure. Empty samples report insufficient_evidence, never zero.
"""

from __future__ import annotations

import pytest

import bus_types

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import compute_jcurve
from meridian_core.server import SidecarServer

#: Adoption cut: Wednesday 2026-03-04; adoption Monday is 2026-03-02.
ADOPTION = "2026-03-04T12:00:00Z"


def _entry(story, actor, ts, repo_id="edb", **extra):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": repo_id,
        "ts_utc": ts,
    }
    entry.update(extra)
    return entry


def _rejection_entry(rejected_sequence, story, ts, repo_id="edb"):
    return {
        "story_id": story,
        "phase": "review",
        "loop_id": "rejection",
        "loop_iteration": 0,
        "actor_id": "reviewer-human",
        "actor_version": "0",
        "actor_kind": "external",
        "policy_version": "f0",
        "action_type": "rejection",
        "decision": "rejected",
        "rework_reason": "other",
        "rejected_sequence": rejected_sequence,
        "repo_id": repo_id,
        "ts_utc": ts,
    }


def _server(tmp_path, entries):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger)
    for entry in entries:
        ledger.append(entry)
    return server, ledger


def _call(server, method, params):
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 11, "method": method, "params": params}
    )
    assert response is not None
    assert "error" not in response, response.get("error")
    return response["result"]


class TestJcurve:
    """FR-M37-05: before/dip/after throughput with stability, the dip
    visible as a phase."""

    @pytest.fixture()
    def world(self, tmp_path):
        """Baseline 2.5 diffs/week before adoption; a three-week dip
        (1, 0, 1) from the adoption week; recovery in week 3."""
        entries = [
            # Week -2: two diffs.
            _entry("A", "agent-one", "2026-02-16T10:00:00Z"),
            _entry("B", "agent-one", "2026-02-17T10:00:00Z"),
            # Week -1: three diffs, one rejected in review.
            _entry("C", "agent-one", "2026-02-23T10:00:00Z"),
            _entry("D", "agent-one", "2026-02-24T10:00:00Z"),
            _entry("E", "agent-one", "2026-02-25T10:00:00Z", decision="rejected"),
            # Week 0 (adoption): one diff.
            _entry("F", "agent-two", "2026-03-02T10:00:00Z"),
            # Week 1: empty (the dip IS the empty week).
            # Week 2: one diff.
            _entry("G", "agent-two", "2026-03-16T10:00:00Z"),
            # Week 3: recovery, four diffs.
            _entry("H", "agent-two", "2026-03-23T10:00:00Z"),
            _entry("I", "agent-two", "2026-03-23T11:00:00Z"),
            _entry("J", "agent-two", "2026-03-24T10:00:00Z"),
            _entry("K", "agent-two", "2026-03-25T10:00:00Z"),
        ]
        server, ledger = _server(tmp_path, entries)
        yield server, ledger
        ledger.close()

    def test_dip_visible_as_a_phase(self, world):
        server, _ledger = world
        result = _call(
            server, "trust/jcurve", {"adoptionDate": ADOPTION}
        )

        assert result["status"] == "ok"
        assert result["baseline"] == 2.5
        dip = result["dip"]
        assert dip["startWeek"] == 0  # the dip begins where adoption began
        assert dip["endWeek"] == 2
        assert dip["depth"] == -1.0  # the empty week: 0 vs baseline 2.5
        assert dip["recoveredWeek"] == 3

    def test_before_after_phases_carry_zero_weeks(self, world):
        server, _ledger = world
        result = _call(server, "trust/jcurve", {"adoptionDate": ADOPTION})

        before = result["phases"]["before"]
        assert before["weeks"] == 2
        assert before["weeklyThroughput"] == {"-2": 2, "-1": 3}
        assert before["throughputPerWeek"] == 2.5
        assert before["proposed"] == 5
        assert before["rejected"] == 1
        assert before["stabilityRate"] == 0.2

        after = result["phases"]["after"]
        assert after["weeks"] == 4  # the empty week 1 is a real week
        assert after["weeklyThroughput"] == {"0": 1, "1": 0, "2": 1, "3": 4}
        assert after["throughputPerWeek"] == 1.5
        assert after["proposed"] == 6
        assert after["rejected"] == 0
        assert after["stabilityRate"] == 0.0

    def test_reconciles_to_the_ledger(self, world):
        """Independent recomputation of the dip from raw rows."""
        server, ledger = world
        result = _call(server, "trust/jcurve", {"adoptionDate": ADOPTION})

        rows = ledger.query(action_type="diff", limit=1000)
        rejection_rows = ledger.query(action_type="rejection", limit=1000)
        assert len(rejection_rows) == 0
        from datetime import date as date_mod

        adoption_monday = date_mod(2026, 3, 2)

        def rel_week(ts):
            day = date_mod.fromisoformat(ts[:10])
            monday = day.fromordinal(day.toordinal() - day.weekday())
            return (monday - adoption_monday).days // 7

        weekly = {}
        for row in rows:
            rel = rel_week(row["ts_utc"])
            weekly[rel] = weekly.get(rel, 0) + 1
        before = list(range(min(w for w in weekly if w < 0), 0))
        after = list(range(0, max(weekly) + 1))
        baseline = sum(weekly.get(w, 0) for w in before) / len(before)
        assert result["baseline"] == baseline
        assert result["phases"]["before"]["weeklyThroughput"] == {
            str(w): weekly.get(w, 0) for w in before
        }
        assert result["phases"]["after"]["weeklyThroughput"] == {
            str(w): weekly.get(w, 0) for w in after
        }

    def test_empty_ledger_is_insufficient_evidence(self, tmp_path):
        server, ledger = _server(tmp_path, [])
        try:
            result = _call(server, "trust/jcurve", {"adoptionDate": ADOPTION})
        finally:
            ledger.close()
        assert result["status"] == "insufficient_evidence"
        assert result["baseline"] is None
        assert result["dip"] == {}
        assert result["phases"]["before"] is None
        assert result["phases"]["after"] is None

    def test_one_sided_sample_is_partial(self, tmp_path):
        entries = [
            _entry("A", "agent-one", "2026-03-02T10:00:00Z"),
            _entry("B", "agent-one", "2026-03-03T10:00:00Z"),
        ]
        server, ledger = _server(tmp_path, entries)
        try:
            result = _call(server, "trust/jcurve", {"adoptionDate": ADOPTION})
        finally:
            ledger.close()
        assert result["status"] == "partial"
        assert result["baseline"] is None  # no before phase to baseline on
        assert result["dip"] == {}
        assert result["phases"]["before"] is None
        assert result["phases"]["after"]["proposed"] == 2

    def test_linked_rejection_counts_in_stability(self, world):
        """The F0 linked-rejection shape also degrades stability — a
        post-merge revert in the after phase shows up in the rate."""
        server, ledger = world
        rows = ledger.query(action_type="diff", limit=1000)
        seq_g = next(row["seq"] for row in rows if row["story_id"] == "G")
        ledger.append(
            _rejection_entry(seq_g, "G", "2026-03-17T10:00:00Z")
        )
        result = _call(server, "trust/jcurve", {"adoptionDate": ADOPTION})
        assert result["phases"]["after"]["rejected"] == 1
        assert result["phases"]["after"]["stabilityRate"] == round(1 / 6, 6)
        # The rejection entry is not a diff: it does not move throughput.
        assert result["phases"]["after"]["proposed"] == 6

    def test_unparseable_adoption_date_refused(self, world):
        server, _ledger = world
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "trust/jcurve",
                "params": {"adoptionDate": "not-a-date"},
            }
        )
        assert response is not None
        assert response["error"]["code"] == -32602  # INVALID_PARAMS

    def test_result_is_cached_then_invalidated_on_append(self, world):
        server, ledger = world
        params = {"adoptionDate": ADOPTION}
        first = _call(server, "trust/jcurve", params)
        second = _call(server, "trust/jcurve", params)
        assert second["cacheHit"] is True

        ledger.append(_entry("L", "agent-two", "2026-03-25T12:00:00Z"))
        third = _call(server, "trust/jcurve", params)
        assert third["cacheHit"] is False
        assert third["phases"]["after"]["proposed"] == 7

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/jcurve" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"


class TestJcurveSplit:
    """G6: the J-curve reports the greenfield/brownfield split."""

    def test_split_buckets_per_phase(self, tmp_path):
        entries = [
            _entry("GF", "agent-one", "2026-02-23T10:00:00Z"),
            _entry("BF", "agent-one", "2026-02-24T10:00:00Z"),
            _entry("GF", "agent-one", "2026-03-16T10:00:00Z"),
            _entry("BF", "agent-one", "2026-03-17T10:00:00Z"),
            _entry("UC", "agent-one", "2026-03-18T10:00:00Z"),
        ]
        server, ledger = _server(tmp_path, entries)
        try:
            result = compute_jcurve(
                ledger,
                adoption_date=ADOPTION,
                classify=lambda story: {"GF": "greenfield", "BF": "brownfield"}.get(story),
            )
        finally:
            ledger.close()

        split = result["split"]
        assert split["greenfield"]["before"]["proposed"] == 1
        assert split["greenfield"]["after"]["proposed"] == 1
        assert split["brownfield"]["before"]["proposed"] == 1
        assert split["brownfield"]["after"]["proposed"] == 1
        # The unclassifiable story lands in unclassified, never dropped.
        assert split["unclassified"]["after"]["proposed"] == 1
        assert split["unclassified"]["before"] is None
