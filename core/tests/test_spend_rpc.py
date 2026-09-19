"""Spend RPCs (FR-M39-01/02/03/04; F1 Workstream F tasks 26-29).

End-to-end over a real ledger + SidecarServer: the six-dimension bill,
the hosted-pause / observed-warn ceiling split, the forecast + budget
alert, and the pricing table. Every requirement id has tests here and
in the module-level files (test_spend_series.py, test_spend_budget.py,
test_spend_pricing.py).
"""

from __future__ import annotations

import bus_types
import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.server import SidecarServer

STORY_META = """\
version: 1
stories:
  S-1:
    team: platform
    costCentre: CC-100
  S-2:
    team: payments
    costCentre: CC-210
"""

PRICING = """\
version: 1
currency: USD
models:
  anthropic:
    claude-sonnet-4-5:
      tokensInPerMillion: 3.0
      tokensOutPerMillion: 15.0
"""

GOVERNANCE = """\
version: 2
budgetCeilings:
  usdPerAgent: 0.04
  usdPerStory: 0.03
  usdPerMonth: 100
"""


def _entry(actor, story, ts, *, vendor="anthropic", model="claude-sonnet-4-5",
           session=None, tokens_in=1000, tokens_out=500, cost=0.01,
           action_type="prompt"):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "external",
        "policy_version": "policy-v1",
        "action_type": action_type,
        "vendor": vendor,
        "ts_utc": ts,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
    }
    if model:
        entry["model_id"] = model
    if session:
        entry["external_session_id"] = session
    return entry


def _session_begin(actor, session, ts):
    return {
        "story_id": f"acp:{session}",
        "phase": "build",
        "loop_id": "acp-host",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "1.0.0",
        "actor_kind": "external",
        "policy_version": "acp-permissions/v1",
        "action_type": "session_begin",
        "vendor": "acp",
        "external_session_id": session,
        "ts_utc": ts,
    }


def _call(server, method, params):
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": method, "params": params}
    )
    assert response is not None
    assert "error" not in response, response.get("error")
    return response["result"]


@pytest.fixture()
def world(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    story_path = tmp_path / "stories.yaml"
    story_path.write_text(STORY_META, encoding="utf-8")
    pricing_path = tmp_path / "pricing.yaml"
    pricing_path.write_text(PRICING, encoding="utf-8")
    policy_path = tmp_path / "governance.yaml"
    policy_path.write_text(GOVERNANCE, encoding="utf-8")
    base = {
        "storyPath": str(story_path),
        "pricingPath": str(pricing_path),
        "policyPath": str(policy_path),
    }
    yield ledger, base
    ledger.close()


class TestSpendSeriesRpc:
    """FR-M39-01: the six dimensions queryable from recorded data."""

    def _populate(self, ledger):
        # agent-one on S-1 (platform) W02 + W03, agent-two observed on S-2.
        ledger.append(_entry("agent-one", "S-1", "2026-01-05T10:00:00Z"))
        ledger.append(_entry("agent-one", "S-1", "2026-01-12T10:00:00Z", cost=0.02))
        ledger.append(
            _entry("agent-two", "S-2", "2026-01-12T11:00:00Z", session="sess-x")
        )
        # native row without cost or model: no pricing rate -> the cost is
        # unknown (estimated nothing), reported under 'unknown' per model.
        ledger.append(
            _entry("meridian-loop", "S-1", "2026-01-06T09:00:00Z",
                   vendor="meridian", model=None, cost=None)
        )
        # row with tokens but no cost, priced through the pack:
        # (1000*3 + 500*15)/1e6 = 0.0105 estimated.
        ledger.append(
            _entry("agent-est", "S-2", "2026-01-07T09:00:00Z", cost=None)
        )

    def test_all_six_dimensions(self, world):
        ledger, base = world
        self._populate(ledger)
        for dimension, key in [
            ("vendor", "anthropic"),
            ("model", "claude-sonnet-4-5"),
            ("agent", "agent-one"),
            ("story", "S-1"),
            ("team", "platform"),
            ("costCentre", "CC-100"),
        ]:
            result = _call(ledger_server(ledger), "spend/series",
                           {**base, "dimension": dimension})
            assert result["dimension"] == dimension
            assert key in result["byValue"], (dimension, result["byValue"])
        server = ledger_server(ledger)
        team = _call(server, "spend/series", {**base, "dimension": "team"})
        # platform: agent-one 3000 + meridian-loop 1500; payments: the two
        # S-2 rows at 1500 each.
        assert team["byValue"]["platform"]["tokens"] == 4500
        assert team["byValue"]["payments"]["tokens"] == 3000
        assert "unknown" not in team["byValue"]  # every row's story maps

    def test_dimension_without_evidence_is_unknown(self, world):
        ledger, base = world
        self._populate(ledger)
        result = _call(ledger_server(ledger), "spend/series",
                       {**base, "dimension": "model"})
        # The no-model row: 1000 in + 500 out = 1500 tokens, cost unknown.
        assert result["byValue"]["unknown"]["tokens"] == 1500
        assert result["byValue"]["unknown"]["recordedCostUsd"] == 0.0

    def test_recorded_and_estimated_cost_reported_separately(self, world):
        ledger, base = world
        self._populate(ledger)
        server = ledger_server(ledger)
        result = _call(server, "spend/series", base)
        totals = result["totals"]
        assert totals["recordedCostUsd"] == 0.04
        assert totals["estimatedCostUsd"] == 0.0105
        assert totals["costUsd"] == 0.0505
        # The estimated share is visible per value too (agent dimension).
        by_agent = _call(server, "spend/series", {**base, "dimension": "agent"})
        assert by_agent["byValue"]["agent-est"]["estimatedCostUsd"] == 0.0105
        assert by_agent["byValue"]["agent-one"]["estimatedCostUsd"] == 0.0

    def test_spend_series_feeds_tokenmaxxing(self, world):
        ledger, base = world
        self._populate(ledger)
        result = _call(ledger_server(ledger), "spend/series", base)
        series = result["spendSeries"]["agent-one"]
        assert series == [
            {"period": "2026-W02", "tokens": 1500},
            {"period": "2026-W03", "tokens": 1500},
        ]
        # And the detector accepts it verbatim.
        verdict = _call(
            ledger_server(ledger),
            "trust/tokenmaxxing",
            {"spendSeries": {"agent-one": series}},
        )
        assert "agent-one" in verdict["byAgent"]

    def test_result_cached_then_invalidated_on_append(self, world):
        ledger, base = world
        self._populate(ledger)
        server = ledger_server(ledger)
        first = _call(server, "spend/series", base)
        assert first["cacheHit"] is False
        assert _call(server, "spend/series", base)["cacheHit"] is True
        ledger.append(
            _entry("agent-one", "S-1", "2026-01-13T10:00:00Z", cost=0.05)
        )
        fresh = _call(server, "spend/series", base)
        assert fresh["cacheHit"] is False
        assert fresh["totals"]["recordedCostUsd"] == 0.09

    def test_bad_dimension_refused(self, world):
        ledger, base = world
        response = ledger_server(ledger).handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "spend/series",
             "params": {**base, "dimension": "colour"}}
        )
        assert response["error"]["code"] == -32602


def ledger_server(ledger, notifications=None):
    return SidecarServer(
        ledger=ledger,
        notification_sink=notifications.append if notifications is not None else None,
    )


class TestSpendCeilingCheckRpc:
    """FR-M39-02: hosted PAUSES at checkpoint; observed WARNS honestly."""

    def _populate(self, ledger):
        # agent-hosted: two hosted rows totaling 0.03 (< 0.04 ceiling).
        ledger.append(_session_begin("agent-hosted", "sess-h", "2026-01-05T09:00:00Z"))
        ledger.append(
            _entry("agent-hosted", "S-1", "2026-01-05T10:00:00Z",
                   vendor="acp", session="sess-h", cost=0.01)
        )
        # agent-observed: same spend, no session_begin — observed only.
        ledger.append(
            _entry("agent-observed", "S-2", "2026-01-05T10:00:00Z",
                   session="sess-o", cost=0.01)
        )

    def test_hosted_breach_pauses_at_checkpoint(self, world):
        ledger, base = world
        self._populate(ledger)
        ledger.append(
            _entry("agent-hosted", "S-1", "2026-01-06T10:00:00Z",
                   vendor="acp", session="sess-h", cost=0.03)
        )
        notifications = []
        server = ledger_server(ledger, notifications)
        result = _call(server, "spend/ceilingCheck",
                       {**base, "actorId": "agent-hosted", "sessionId": "sess-h"})
        assert result["ceilings"]["usdPerAgent"]["breached"] is True
        assert result["action"] == "paused_at_checkpoint"
        assert result["hosted"] is True
        assert result["advisory"] is False
        assert result["sequence"] is not None
        # FR-M10-08: the record is durable; the dispatch carries it.
        rows = ledger.query(action_type="spend_ceiling", limit=10)
        assert len(rows) == 1
        assert rows[0]["decision"] == "halted"
        assert [n["method"] for n in notifications] == ["spend/ceiling"]
        assert notifications[0]["params"]["action"] == "pauseAtCheckpoint"
        assert notifications[0]["params"]["sequence"] == result["sequence"]

    def test_observed_breach_warns_never_pauses(self, world):
        ledger, base = world
        self._populate(ledger)
        ledger.append(
            _entry("agent-observed", "S-2", "2026-01-06T10:00:00Z",
                   session="sess-o", cost=0.03)
        )
        notifications = []
        server = ledger_server(ledger, notifications)
        result = _call(server, "spend/ceilingCheck",
                       {**base, "actorId": "agent-observed", "sessionId": "sess-o"})
        assert result["ceilings"]["usdPerAgent"]["breached"] is True
        assert result["action"] == "warned"
        assert result["hosted"] is False
        assert result["advisory"] is True
        # The warning itself is honest about the limit of the control —
        # it names the NOT_HOSTED situation instead of refusing silently.
        assert "cannot pause" in result["note"]
        assert "FR-M35-06" in result["note"]
        assert notifications == []  # nothing to dispatch: cannot pause.
        # The warning is still durable (FR-M10-08).
        rows = ledger.query(action_type="spend_ceiling", limit=10)
        assert len(rows) == 1

    def test_below_ceiling_no_action_no_record(self, world):
        ledger, base = world
        self._populate(ledger)
        result = _call(ledger_server(ledger), "spend/ceilingCheck",
                       {**base, "actorId": "agent-hosted", "sessionId": "sess-h"})
        assert result["action"] == "none"
        assert result["ceilings"]["usdPerAgent"]["breached"] is False
        assert result["sequence"] is None
        assert ledger.query(action_type="spend_ceiling", limit=10) == []

    def test_per_story_ceiling_checked_when_story_given(self, world):
        ledger, base = world
        ledger.append(_entry("agent-one", "S-1", "2026-01-05T10:00:00Z", cost=0.05))
        result = _call(ledger_server(ledger), "spend/ceilingCheck",
                       {**base, "actorId": "agent-one", "storyId": "S-1"})
        assert result["ceilings"]["usdPerStory"]["breached"] is True
        assert result["ceilings"]["usdPerStory"]["limitUsd"] == 0.03

    def test_missing_actor_refused(self, world):
        ledger, base = world
        response = ledger_server(ledger).handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "spend/ceilingCheck",
             "params": base}
        )
        assert response["error"]["code"] == -32602

    def test_ceiling_config_comes_from_pack_not_code(self, world, tmp_path):
        ledger, base = world
        # Same spend, ceiling lifted by config alone.
        high = tmp_path / "governance-high.yaml"
        high.write_text(
            "version: 2\nbudgetCeilings:\n  usdPerAgent: 1000\n",
            encoding="utf-8",
        )
        ledger.append(
            _entry("agent-one", "S-1", "2026-01-05T10:00:00Z", cost=500.0)
        )
        result = _call(ledger_server(ledger), "spend/ceilingCheck",
                       {**base, "policyPath": str(high), "actorId": "agent-one"})
        assert result["ceilings"]["usdPerAgent"]["limitUsd"] == 1000
        assert result["ceilings"]["usdPerAgent"]["breached"] is False
        assert result["action"] == "none"


class TestSpendForecastRpc:
    """FR-M39-03: monthly forecast + budget alert from config."""

    def test_forecast_projects_and_alerts_on_configured_budget(self, world, monkeypatch):
        ledger, base = world
        # Rising months 10, 20, 30 in Dec/Jan/Feb, "today" is March.
        for month, usd in [("2025-12", 10.0), ("2026-01", 20.0), ("2026-02", 30.0)]:
            ledger.append(
                _entry("agent-one", "S-1", f"{month}-15T10:00:00Z", cost=usd)
            )
        # Actual March spend already past the tiny budget in GOVERNANCE
        # (usdPerMonth: 100)? No — keep under; forecast 40 < 100 too.
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        result = _call(ledger_server(ledger), "spend/forecast", base)
        assert result["forecast"]["status"] == "ok"
        assert result["forecast"]["projectedUsd"] == 40.0
        assert result["budget"]["status"] == "ok"
        assert result["budget"]["limitUsd"] == 100  # from the pack, not code
        assert result["status"] == "ok"
        assert result["months"] == {"2025-12": 10.0, "2026-01": 20.0, "2026-02": 30.0}

    def test_actual_breach_alerts(self, world, monkeypatch):
        ledger, base = world
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        ledger.append(_entry("agent-one", "S-1", "2026-03-01T10:00:00Z", cost=150.0))
        result = _call(ledger_server(ledger), "spend/forecast", base)
        assert result["budget"]["status"] == "actual_breach"
        assert result["status"] == "actual_breach"

    def test_forecast_breach_alerts_before_the_bill(self, world, monkeypatch):
        ledger, base = world
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        for month, usd in [("2026-01", 80.0), ("2026-02", 90.0)]:
            ledger.append(
                _entry("agent-one", "S-1", f"{month}-15T10:00:00Z", cost=usd)
            )
        ledger.append(_entry("agent-one", "S-1", "2026-03-01T10:00:00Z", cost=5.0))
        result = _call(ledger_server(ledger), "spend/forecast", base)
        # The line over Dec(0), Jan(80), Feb(90) extrapolated to March
        # projects 146.666667 — already over the 100 budget, so the alert
        # fires before the bill arrives.
        assert result["forecast"]["projectedUsd"] == 146.666667
        assert result["budget"]["status"] == "forecast_breach"
        assert result["status"] == "forecast_breach"

    def test_unconfigured_budget_reported_not_invented(self, world, tmp_path, monkeypatch):
        ledger, base = world
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        no_budget = tmp_path / "gov-none.yaml"
        no_budget.write_text("version: 2\nbudgetCeilings: {}\n", encoding="utf-8")
        ledger.append(_entry("agent-one", "S-1", "2026-02-15T10:00:00Z", cost=9.0))
        ledger.append(_entry("agent-one", "S-1", "2026-01-15T10:00:00Z", cost=7.0))
        result = _call(ledger_server(ledger), "spend/forecast",
                       {**base, "policyPath": str(no_budget)})
        assert result["budget"]["status"] == "unconfigured"
        assert result["budget"]["limitUsd"] is None
        assert result["forecast"]["status"] == "ok"
        assert result["status"] == "unconfigured"

    def test_insufficient_evidence_never_projects(self, world, monkeypatch):
        ledger, base = world
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        ledger.append(_entry("agent-one", "S-1", "2026-02-15T10:00:00Z", cost=9.0))
        result = _call(ledger_server(ledger), "spend/forecast", base)
        assert result["forecast"]["status"] == "insufficient_evidence"
        assert result["forecast"]["projectedUsd"] is None
        assert result["status"] == "insufficient_evidence"

    def test_team_filter_resolves_through_story_metadata(self, world, monkeypatch):
        ledger, base = world
        import meridian_core.ledger.core as core_mod

        monkeypatch.setattr(core_mod, "utc_now", lambda: "2026-03-10T00:00:00Z")
        # platform (S-1) rises 10/20, payments (S-2) flat 5/5.
        for month, usd in [("2026-01", 10.0), ("2026-02", 20.0)]:
            ledger.append(_entry("a", "S-1", f"{month}-15T10:00:00Z", cost=usd))
        for month in ("2026-01", "2026-02"):
            ledger.append(_entry("b", "S-2", f"{month}-15T10:00:00Z", cost=5.0))
        result = _call(ledger_server(ledger), "spend/forecast",
                       {**base, "team": "platform"})
        assert result["team"] == "platform"
        assert result["months"] == {"2026-01": 10.0, "2026-02": 20.0}
        assert result["forecast"]["projectedUsd"] == 30.0


class TestSpendPricingRpc:
    """FR-M39-04: the pricing table over RPC, all rates from config."""

    def test_rates_come_from_the_pack(self, world):
        ledger, base = world
        result = _call(ledger_server(ledger), "spend/pricing", base)
        assert result["errors"] == []
        assert result["currency"] == "USD"
        assert {
            "vendor": "anthropic",
            "model": "claude-sonnet-4-5",
            "tokensInPerMillion": 3.0,
            "tokensOutPerMillion": 15.0,
        } in result["models"]

    def test_malformed_pack_reports_errors_and_no_rates(self, world, tmp_path):
        ledger, base = world
        bad = tmp_path / "pricing-bad.yaml"
        bad.write_text("version: nope\n", encoding="utf-8")
        result = _call(ledger_server(ledger), "spend/pricing",
                       {"pricingPath": str(bad)})
        assert result["errors"]
        assert result["models"] == []


class TestTierOwnership:
    def test_spend_capability_is_flight_recorder_read_only_observability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "spend/series" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        capability = owning[0]
        assert capability["tier"] == "flight-recorder"
        for method in (
            "spend/series", "spend/ceilingCheck", "spend/forecast", "spend/pricing"
        ):
            assert method in capability["rpcMethods"]
