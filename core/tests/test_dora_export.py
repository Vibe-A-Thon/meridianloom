"""DORA four-keys export (FR-M37-08; F1 Workstream E task 25).

The four DORA keys — deployment frequency, lead time for changes, change
failure rate, time to restore — derived from the ledger and exported in
OTLP-friendly JSON. Keys the ledger cannot evidence are exported with
meridian.evidence=unknown and no value — never invented numbers.
"""

from __future__ import annotations

import pytest

import bus_types

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import compute_dora_metrics, export_otlp
from meridian_core.server import SidecarServer

EXPORTED_AT = "2026-03-01T00:00:00Z"


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


class TestDoraMetrics:
    """The four keys over a ledger with a failure-and-recovery story."""

    @pytest.fixture()
    def world(self, tmp_path):
        """Story A: proposed, approved, reverted (failure), restored.
        Story B: proposed, approved. Story C: proposed only (no approval).
        Deployments span two weeks: 2026-01-05 week and 2026-01-19 week."""
        entries = [
            # Week 1 (2026-01-05): story A lands and is approved 24h later.
            _entry("A", "agent-one", "2026-01-05T09:00:00Z"),
            _entry(
                "A",
                "agent-one",
                "2026-01-06T09:00:00Z",
                decision="approved",
                phase="review",
            ),
            # Week 2 (2026-01-12): story B lands and is approved 12h later.
            _entry("B", "agent-one", "2026-01-12T09:00:00Z"),
            _entry(
                "B",
                "agent-one",
                "2026-01-12T21:00:00Z",
                decision="approved",
                phase="review",
            ),
            # Story C: proposed but never approved — no lead time, not a
            # deployment.
            _entry("C", "agent-one", "2026-01-13T10:00:00Z"),
        ]
        server, ledger = _server(tmp_path, entries)
        # Story A fails post-merge (rejection entry carrying its approved
        # diff) and is restored 48h later by a new approved diff.
        approved_a = next(
            row
            for row in ledger.query(action_type="diff", limit=1000)
            if row["story_id"] == "A" and row.get("decision") == "approved"
        )
        ledger.append(
            _rejection_entry(approved_a["seq"], "A", "2026-01-20T10:00:00Z")
        )
        ledger.append(
            _entry(
                "A",
                "agent-one",
                "2026-01-22T10:00:00Z",
                decision="approved",
                phase="review",
            )
        )
        yield server, ledger
        ledger.close()

    def test_deployment_frequency(self, world):
        server, _ledger = world
        result = _call(server, "trust/doraExport", {})
        metric = result["metrics"]["deploymentFrequency"]
        assert metric["status"] == "ok"
        # 3 approved diffs (A x2, B) over the weeks of 01-05 and 01-19:
        # span = 3 calendar weeks -> 3/3 = 1.0 per week.
        assert metric["deployments"] == 3
        assert metric["spanWeeks"] == 3
        assert metric["value"] == 1.0

    def test_lead_time_for_changes(self, world):
        server, _ledger = world
        result = _call(server, "trust/doraExport", {})
        metric = result["metrics"]["leadTimeForChanges"]
        assert metric["status"] == "ok"
        # Story A: 24h. Story B: 12h. Story A's restore diff and story C
        # carry no first-proposed -> first-approved interval of their own.
        assert metric["stories"] == 2
        assert metric["value"] == 18.0  # median of 24 and 12

    def test_change_failure_rate(self, world):
        server, _ledger = world
        result = _call(server, "trust/doraExport", {})
        metric = result["metrics"]["changeFailureRate"]
        assert metric["status"] == "ok"
        assert metric["deployments"] == 3
        assert metric["failed"] == 1
        assert metric["value"] == round(1 / 3, 6)

    def test_time_to_restore(self, world):
        server, _ledger = world
        result = _call(server, "trust/doraExport", {})
        metric = result["metrics"]["timeToRestore"]
        assert metric["status"] == "ok"
        assert metric["failures"] == 1
        # Failure at 2026-01-20T10:00, restore approved 2026-01-22T10:00.
        assert metric["value"] == 48.0

    def test_otlp_export_shape(self, world):
        server, _ledger = world
        result = _call(
            server,
            "trust/doraExport",
            {"exportedAt": EXPORTED_AT, "resourceAttributes": {"team": "core"}},
        )
        export = result["export"]
        resource = export["resourceMetrics"][0]
        attributes = {
            attr["key"]: attr["value"]["stringValue"]
            for attr in resource["resource"]["attributes"]
        }
        assert attributes["service.name"] == "meridian-loom"
        assert attributes["team"] == "core"

        metrics = resource["scopeMetrics"][0]["metrics"]
        by_name = {metric["name"]: metric for metric in metrics}
        assert set(by_name) == {
            "dora.deployment_frequency",
            "dora.lead_time_for_changes",
            "dora.change_failure_rate",
            "dora.time_to_restore",
        }
        point = by_name["dora.deployment_frequency"]["gauge"]["dataPoints"][0]
        assert point["asDouble"] == 1.0
        assert point["timeUnixNano"] == str(
            1772323200 * 1_000_000_000  # 2026-03-01T00:00:00Z
        )
        assert by_name["dora.deployment_frequency"]["unit"] == "{deployment}/wk"

    def test_otlp_values_match_the_metrics_block(self, world):
        """The OTLP payload carries exactly the values the metrics block
        reports — one encoding, no divergence."""
        server, _ledger = world
        result = _call(
            server, "trust/doraExport", {"exportedAt": EXPORTED_AT}
        )
        metrics = result["export"]["resourceMetrics"][0]["scopeMetrics"][0][
            "metrics"
        ]
        values = {
            metric["name"]: metric["gauge"]["dataPoints"][0].get("asDouble")
            for metric in metrics
        }
        assert values["dora.deployment_frequency"] == result["metrics"][
            "deploymentFrequency"
        ]["value"]
        assert values["dora.change_failure_rate"] == result["metrics"][
            "changeFailureRate"
        ]["value"]

    def test_export_is_standard_library_only(self):
        """FR-M37-08: no OTLP SDK — the module's own imports are the
        standard library (datetime/typing) plus at most the in-package,
        itself-stdlib-only metrics.coverage (FR-M41-08's envelope helper;
        N1 Workstream A) — never a third-party dependency."""
        import inspect

        import meridian_core.metrics.dora as dora

        source = inspect.getsource(dora)
        imported = {
            line.split()[1].split(".")[0].strip(",")
            for line in source.splitlines()
            if line.startswith(("import ", "from "))
        }
        assert imported <= {"datetime", "typing", "__future__", "meridian_core"}

    def test_result_is_cached_then_invalidated_on_append(self, world):
        server, ledger = world
        params = {"exportedAt": EXPORTED_AT}
        first = _call(server, "trust/doraExport", params)
        second = _call(server, "trust/doraExport", params)
        assert second == first

        ledger.append(_entry("D", "agent-one", "2026-01-14T10:00:00Z"))
        third = _call(server, "trust/doraExport", params)
        assert third["metrics"]["deploymentFrequency"]["deployments"] == first[
            "metrics"
        ]["deploymentFrequency"]["deployments"]

    def test_repo_scope(self, world):
        server, ledger = world
        ledger.append(_entry("E", "agent-one", "2026-01-05T11:00:00Z", repo_id="other"))
        ledger.append(
            _entry(
                "E",
                "agent-one",
                "2026-01-06T11:00:00Z",
                repo_id="other",
                decision="approved",
                phase="review",
            )
        )
        result = _call(server, "trust/doraExport", {"repoId": "edb"})
        assert result["metrics"]["deploymentFrequency"]["deployments"] == 3
        unscoped = _call(server, "trust/doraExport", {})
        assert unscoped["metrics"]["deploymentFrequency"]["deployments"] == 4

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/doraExport" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"


class TestDoraUnknowns:
    """Keys with no evidence are unknown, exported with meridian.evidence=
    unknown and NO value — never invented numbers."""

    def test_empty_ledger_all_unknown(self, tmp_path):
        server, ledger = _server(tmp_path, [])
        try:
            result = _call(server, "trust/doraExport", {})
        finally:
            ledger.close()
        assert result["status"] == {
            "deploymentFrequency": "unknown",
            "leadTimeForChanges": "unknown",
            "changeFailureRate": "unknown",
            "timeToRestore": "unknown",
        }
        for metric in result["metrics"].values():
            assert metric["value"] is None

        metrics = result["export"]["resourceMetrics"][0]["scopeMetrics"][0][
            "metrics"
        ]
        for metric in metrics:
            point = metric["gauge"]["dataPoints"][0]
            assert "asDouble" not in point  # no invented number
            attrs = {
                attr["key"]: attr["value"]["stringValue"]
                for attr in point["attributes"]
            }
            assert attrs["meridian.evidence"] == "unknown"

    def test_failure_without_recovery_unknown(self, tmp_path):
        """A change that failed and was never restored: time to restore is
        unknown — absence of recovery is not a zero-hour restore."""
        entries = [
            _entry("A", "agent-one", "2026-01-05T09:00:00Z"),
            _entry(
                "A",
                "agent-one",
                "2026-01-06T09:00:00Z",
                decision="approved",
                phase="review",
            ),
        ]
        server, ledger = _server(tmp_path, entries)
        try:
            approved = ledger.query(action_type="diff", limit=1000)[1]
            ledger.append(
                _rejection_entry(approved["seq"], "A", "2026-01-20T10:00:00Z")
            )
            result = _call(server, "trust/doraExport", {})
        finally:
            ledger.close()
        restore = result["metrics"]["timeToRestore"]
        assert restore["status"] == "unknown"
        assert restore["value"] is None
        # The failure is still real in change failure rate.
        assert result["metrics"]["changeFailureRate"]["value"] == 1.0
