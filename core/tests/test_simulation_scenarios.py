"""TASK-020: the ten FR-M32-04 scenarios materialize, replay, and write
replay_of-tagged ledger entries through SimulationCore."""

from __future__ import annotations

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.simulation import SCENARIO_NAMES, SimulationCore
from meridian_core.simulation.scenarios import all_scenarios, load_scenario


def test_all_ten_scenarios_materialize() -> None:
    scenarios = all_scenarios()
    assert set(scenarios) == set(SCENARIO_NAMES)
    for name, scenario in scenarios.items():
        assert scenario.steps, f"{name} has no steps"
        sequences = [s.sequence for s in scenario.steps]
        assert sequences == sorted(sequences), f"{name} sequences out of order"


def test_each_scenario_replays_and_tags_the_ledger(tmp_path) -> None:
    for name in SCENARIO_NAMES:
        scenario = load_scenario(name)
        ledger = Ledger(tmp_path / name, EphemeralSigningKeyProvider())
        try:
            core = SimulationCore(ledger=ledger, scenario=scenario)
            for step in scenario.steps:
                response = core.serve(step.method, dict(step.params))
                assert "error" not in response, (name, step.method, response)
            rows = [
                row for row in ledger.query(action_type=None, limit=1000)
                if row.get("replay_of")
            ]
            assert ledger.verify().ok is True
        finally:
            ledger.close()


def test_unknown_scenario_refused() -> None:
    with pytest.raises(KeyError, match="unknown scenario"):
        load_scenario("no-such-story")
