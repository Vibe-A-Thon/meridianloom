"""FR-M32-04 scripted scenarios (audit TASK-020): the ten named scenario
families, materialized as real `Scenario` objects whose canned responses
carry the data each screen needs. `SimulationCore` accepts a scenario by
name via :func:`load_scenario`; the AC-28 parity harness (TASK-021) and
the golden runner (TASK-022) consume these.
"""

from __future__ import annotations

from typing import Any

from . import Scenario, ScenarioStep

STORY = "EDB-SIM"


def _step(seq: int, method: str, params: dict[str, Any], response: dict[str, Any],
          payloads: tuple[dict[str, Any], ...] = ()) -> ScenarioStep:
    return ScenarioStep(
        sequence=seq, method=method, params=params, response=response,
        ledger_payloads=payloads,
    )


def clean_story() -> Scenario:
    """A story that flows Intake → Design → Plan → Build → Verify →
    Security → Review without rework."""
    chain = ("intake", "design", "plan", "build", "verify", "security", "review")
    steps = []
    for index, phase in enumerate(chain, start=1):
        steps.append(_step(
            index, "ledger.query", {"storyId": STORY, "phase": phase},
            {"entries": [{"storyId": STORY, "phase": phase, "state": "complete"}],
             "truncated": False, "nextAfterSequence": None},
            ({"story_id": STORY, "phase": phase, "action_type": "diff",
              "loop_iteration": index},),
        ))
    steps.append(_step(
        len(chain) + 1, "gate.status", {"subject": STORY},
        {"status": "approved", "subject": STORY},
    ))
    return Scenario(name="clean-story", steps=tuple(steps))


def rework_and_unravel() -> Scenario:
    return Scenario(name="rework-and-unravel", steps=(
        _step(1, "ledger.query", {"storyId": STORY},
              {"entries": [{"seq": 4, "decision": "rejected",
                         "rework_reason": "tests failed on boundary input"}],
              "truncated": False, "nextAfterSequence": None},
              ({"story_id": STORY, "phase": "build", "action_type": "rejection",
                "decision": "rejected", "loop_iteration": 1},)),
        _step(2, "ledger.query", {"storyId": STORY, "reworked": True},
              {"entries": [{"seq": 7, "decision": "reworked",
                         "rework_reason": "tests failed on boundary input"}],
              "truncated": False, "nextAfterSequence": None},
              ({"story_id": STORY, "phase": "build", "action_type": "diff",
                "decision": "reworked", "loop_iteration": 2},)),
    ))


def loop_bound_hit() -> Scenario:
    return Scenario(name="loop-bound-hit", steps=(
        _step(1, "loop.status", {"loopId": "L-bound"},
              {"loopId": "L-bound", "kind": "L2-task", "state": "breached", "iteration": 5}),
        _step(2, "ledger.query", {"storyId": STORY, "event": "bound_breached"},
              {"entries": [{"event": "bound_breached", "bound": "iterations",
                         "limit": 5, "escalation_target": "human"}],
              "truncated": False, "nextAfterSequence": None},
              ({"story_id": STORY, "phase": "build", "action_type": "loop_event",
                "loop_iteration": 5},)),
    ))


def blocked_gate() -> Scenario:
    return Scenario(name="blocked-gate", steps=(
        _step(1, "gate.status", {"subject": STORY},
              {"status": "blocked", "missing": ["human approval"],
               "requiredApprovals": 1, "approvalsReceived": 0}),
    ))


def clarifying_question() -> Scenario:
    return Scenario(name="clarifying-question", steps=(
        _step(1, "steer/status", {"sessionId": "sess-q"},
              {"gate": "clarifying-question",
               "question": "Which currency should the refund mirror?",
               "awaiting": "operator answer"}),
    ))


def mid_loop_steer() -> Scenario:
    return Scenario(name="mid-loop-steer", steps=(
        _step(1, "ledger.query", {"storyId": STORY, "event": "steer"},
              {"entries": [{"event": "steer_injected", "text": "prefer table-driven tests"}],
              "truncated": False, "nextAfterSequence": None},
              ({"story_id": STORY, "phase": "build", "action_type": "note",
                "loop_iteration": 3},)),
    ))


def multi_story_portfolio() -> Scenario:
    return Scenario(name="multi-story-portfolio", steps=(
        _step(1, "ledger.query", {"portfolio": True},
              {"entries": [
                  {"storyId": "EDB-1", "phase": "build", "state": "running"},
                  {"storyId": "EDB-2", "phase": "verify", "state": "running"},
                  {"storyId": "EDB-3", "phase": "review", "state": "gated"},
              ], "truncated": False, "nextAfterSequence": None}),
    ))


def tamper_detected_ledger() -> Scenario:
    return Scenario(name="tamper-detected-ledger", steps=(
        _step(1, "ledger.verify", {},
              {"ok": False, "detail": "chain verification failed at seq 4",
               "failedSeq": 4}),
    ))


def budget_breach() -> Scenario:
    return Scenario(name="budget-breach", steps=(
        _step(1, "ledger.query", {"storyId": STORY, "event": "bound_breached"},
              {"entries": [{"event": "bound_breached", "bound": "cost_usd",
                         "limit": 3.0, "observed": 3.12}],
              "truncated": False, "nextAfterSequence": None},
              ({"story_id": STORY, "phase": "build", "action_type": "loop_event",
                "loop_iteration": 4},)),
    ))


def adapter_plug_unplug() -> Scenario:
    return Scenario(name="adapter-plug-unplug", steps=(
        _step(1, "adapters/discover", {},
              {"adapters": [{"id": "developer", "version": "1.0.0",
                             "valid": True, "errors": []}],
               "states": {"developer": "probation"}}),
        _step(2, "adapters/unplug", {"id": "developer"},
              {"retired": True, "checkpointed": True}),
    ))


BUILDERS = {
    "clean-story": clean_story,
    "rework-and-unravel": rework_and_unravel,
    "loop-bound-hit": loop_bound_hit,
    "blocked-gate": blocked_gate,
    "clarifying-question": clarifying_question,
    "mid-loop-steer": mid_loop_steer,
    "multi-story-portfolio": multi_story_portfolio,
    "tamper-detected-ledger": tamper_detected_ledger,
    "budget-breach": budget_breach,
    "adapter-plug-unplug": adapter_plug_unplug,
}


def load_scenario(name: str) -> Scenario:
    builder = BUILDERS.get(name)
    if builder is None:
        raise KeyError(
            f"unknown scenario {name!r}; known: {sorted(BUILDERS)}"
        )
    return builder()


def all_scenarios() -> dict[str, Scenario]:
    return {name: builder() for name, builder in BUILDERS.items()}
