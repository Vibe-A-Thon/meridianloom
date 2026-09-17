"""FR-M4-01…11 (F3 step 3): the Loop Runtime — bounds validated at load,
typed state with declared reducers, LangGraph + SQLite checkpoints,
gate suspension/resume, replay tagging, bound-breach halts with ledger
evidence. Node callables are deterministic test doubles; zero model calls.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.runtime import (
    UNBOUNDED,
    FieldSpec,
    GateSuspend,
    LangGraphLoopRunner,
    LoopDefinition,
    LoopState,
    LoopValidationError,
    StateMergeError,
    WorkPacket,
    add,
    append_unique,
    canonical_loops,
)


def _graph(*edges):
    nodes = {}
    for a, b in edges:
        nodes.setdefault(a, []).append(b)
        nodes.setdefault(b, [])
    return {k: tuple(v) for k, v in nodes.items()}


SCHEMA = {
    "progress": FieldSpec("progress", list, reducer=append_unique, default=[]),
    "tokens_used": FieldSpec("tokens_used", int, reducer=add, default=0),
    "cost_usd": FieldSpec("cost_usd", float, reducer=add, default=0.0),
    "approved": FieldSpec("approved", bool, default=False),  # single-writer
}


@pytest.fixture()
def checkpointer(tmp_path):
    conn = sqlite3.connect(tmp_path / "cp.db", check_same_thread=False)
    yield SqliteSaver(conn)
    conn.close()


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


def detail(led, row):
    return json.loads(led.read_blob(row["input_ref"], row["blob_key_id"]).decode())


# -- FR-M4-02: load-time validation ------------------------------------------


def test_missing_bound_field_fails_at_load() -> None:
    with pytest.raises(LoopValidationError, match="FR-M4-02"):
        LoopDefinition(
            loop_id="BAD",
            entry_condition="x",
            body_graph=_graph(("a", "b")),
            exit_criteria="done",
            max_iterations=None,  # MISSING — not declared, not UNBOUNDED
            token_budget=100,
            wall_clock_budget_s=60,
            cost_ceiling_usd=1.0,
            escalation_target="human",
        ).validate()


def test_unbounded_is_a_declaration_not_an_absence() -> None:
    # L4 may declare UNBOUNDED iterations; a lookalike loop may not.
    lookalike = LoopDefinition(
        loop_id="L2",
        entry_condition="x",
        body_graph=_graph(("a", "b")),
        exit_criteria="done",
        max_iterations=UNBOUNDED,
        token_budget=100,
        wall_clock_budget_s=60,
        cost_ceiling_usd=1.0,
        escalation_target="human",
    )
    with pytest.raises(LoopValidationError, match="only L4"):
        lookalike.validate()


def test_edge_to_unknown_node_fails_at_load() -> None:
    loop = LoopDefinition(
        loop_id="BAD2",
        entry_condition="x",
        body_graph={"a": ("ghost",)},
        exit_criteria="done",
        max_iterations=1,
        token_budget=100,
        wall_clock_budget_s=60,
        cost_ceiling_usd=1.0,
        escalation_target="human",
    )
    with pytest.raises(LoopValidationError, match="unknown nodes"):
        loop.validate()


# -- FR-M4-03: the six canonical loops ------------------------------------------


def test_canonical_loops_carry_section_61_bounds() -> None:
    loops = canonical_loops()
    assert set(loops) == {"L1", "L2", "L3", "L4", "L5", "L6"}
    assert loops["L1"].max_iterations == 3
    assert loops["L1"].token_budget == 50_000
    assert loops["L1"].wall_clock_budget_s == 300
    assert loops["L2"].max_iterations == 5
    assert loops["L2"].token_budget == 300_000
    # §3 amendment: L4 exits at merged AND CI green.
    assert "merged" in loops["L4"].exit_criteria
    assert "CI green" in loops["L4"].exit_criteria
    assert loops["L4"].max_iterations == UNBOUNDED
    # L6 is the only loop with unbounded budgets.
    assert loops["L6"].token_budget == UNBOUNDED
    assert loops["L6"].cost_ceiling_usd == UNBOUNDED
    for loop in loops.values():
        loop.validate()  # every canonical loop loads clean


# -- FR-M4-09/10: fan-out refusals -------------------------------------------------


def test_overlapping_fan_out_rejected_at_load() -> None:
    loop = LoopDefinition(
        loop_id="FAN",
        entry_condition="x",
        body_graph=_graph(("a", "b")),
        exit_criteria="done",
        max_iterations=1,
        token_budget=100,
        wall_clock_budget_s=60,
        cost_ceiling_usd=1.0,
        escalation_target="human",
        fan_out_packets=(
            WorkPacket("p1", ("src/a.py", "src/b.py")),
            WorkPacket("p2", ("src/b.py",)),
        ),
    )
    with pytest.raises(LoopValidationError, match="FR-M4-09"):
        loop.validate()


def test_fan_out_wider_than_concurrency_cap_refused(checkpointer) -> None:
    loop = LoopDefinition(
        loop_id="WIDE",
        entry_condition="x",
        body_graph=_graph(("a", "b")),
        exit_criteria="done",
        max_iterations=1,
        token_budget=100,
        wall_clock_budget_s=60,
        cost_ceiling_usd=1.0,
        escalation_target="human",
        fan_out_packets=tuple(
            WorkPacket(f"p{i}", (f"src/f{i}.py",)) for i in range(3)
        ),
    )
    runner = LangGraphLoopRunner(checkpointer, concurrency_cap=2)
    with pytest.raises(LoopValidationError, match="FR-M4-10"):
        runner.start(loop, {"a": lambda ctx: {}, "b": lambda ctx: {}}, SCHEMA)


# -- FR-M4-04: typed state, declared reducers ---------------------------------------


def test_concurrent_writes_merge_through_declared_reducer() -> None:
    state = LoopState.initial(SCHEMA)
    state.set("progress", [], branch="main")
    state.merge({
        "progress": ("build", ["built x"]),
        "tokens_used": ("build", 10),
    })
    state.merge({
        "progress": ("verify", ["verified y"]),
        "tokens_used": ("verify", 5),
    })
    assert state.get("progress") == ["built x", "verified y"]
    assert state.get("tokens_used") == 15


def test_reducer_less_concurrent_write_raises_not_lww() -> None:
    # The single-merge API takes one write per field, so the concurrent
    # conflict it cannot express is exactly what the runner's per-pass
    # pre-check exists to catch (FR-M4-04).
    state = LoopState.initial(SCHEMA)
    writes = [("review", {"approved": ("review", True)}),
              ("audit", {"approved": ("audit", False)})]
    with pytest.raises(StateMergeError, match="FR-M4-04"):
        LangGraphLoopRunner._apply_writes(SCHEMA, state, writes)
    assert state.get("approved") is False  # default, untouched — the merge is a copy


def test_type_violation_refused() -> None:
    state = LoopState.initial(SCHEMA)
    with pytest.raises(StateMergeError, match="expects"):
        state.set("tokens_used", "lots")


# -- FR-M4-01/05/08/11: running a loop ------------------------------------------------


def test_loop_runs_cycles_until_exit_with_per_iteration_ledger(
    checkpointer, ledger
) -> None:
    loop = LoopDefinition(
        loop_id="L1",
        entry_condition="unit scoped",
        body_graph=_graph(("micro", "verify"), ("verify", "micro")),
        exit_criteria="tests pass",
        max_iterations=3,
        token_budget=50_000,
        wall_clock_budget_s=300,
        cost_ceiling_usd=0.50,
        escalation_target="L2",
    )

    def micro(ctx):
        progress = list(ctx.state.get("progress") or [])
        if "built" not in progress:
            return {"progress": ("micro", ["built"]), "tokens_used": ("micro", 10)}
        return {"tokens_used": ("micro", 2)}

    def verify(ctx):
        progress = list(ctx.state.get("progress") or [])
        if "built" in progress and not ctx.state.get("approved"):
            return {"approved": ("verify", True)}
        return {}

    runner = LangGraphLoopRunner(checkpointer, ledger=ledger)
    runner.with_exit_check(loop, lambda state: state.get("approved") is True)
    handle = runner.start(loop, {"micro": micro, "verify": verify}, SCHEMA)

    assert handle.result["status"] == "completed"
    assert handle.result["iterations"] == 2  # micro, verify; exit on check
    # FR-M4-11: one ledger entry per iteration, chain verifies.
    events = ledger.query(action_type="loop_event", story_id="loop-run")
    iterations = [e for e in events if detail(ledger, e)["event"] == "loop_iteration"]
    assert len(iterations) == handle.result["iterations"]
    assert ledger.verify().ok is True


def test_iteration_bound_breach_halts_with_evidence(checkpointer, ledger) -> None:
    loop = LoopDefinition(
        loop_id="L1",
        entry_condition="never exits",
        body_graph=_graph(("spin", "spin")),
        exit_criteria="unreachable",
        max_iterations=3,
        token_budget=50_000,
        wall_clock_budget_s=300,
        cost_ceiling_usd=0.50,
        escalation_target="L2 with failure trace",
    )
    runner = LangGraphLoopRunner(checkpointer, ledger=ledger)
    runner.with_exit_check(loop, lambda state: False)
    handle = runner.start(loop, {"spin": lambda ctx: {}}, SCHEMA)
    assert handle.result["status"] == "breached"
    assert handle.result["breach"]["bound"] == "iterations"
    assert handle.result["breach"]["limit"] == 3
    # FR-M4-08: breach entry names the bound and the escalation target.
    breaches = [
        e for e in ledger.query(action_type="loop_event")
        if detail(ledger, e)["event"] == "bound_breached"
    ]
    assert len(breaches) == 1
    assert breaches[0]["loop_id"] == "L1"
    assert detail(ledger, breaches[0])["escalation_target"] == "L2 with failure trace"
    assert ledger.verify().ok is True


def test_cost_bound_breach_halts(checkpointer, ledger) -> None:
    loop = LoopDefinition(
        loop_id="L2",
        entry_condition="work",
        body_graph=_graph(("spend", "spend")),
        exit_criteria="never",
        max_iterations=100,
        token_budget=50_000,
        wall_clock_budget_s=3600,
        cost_ceiling_usd=0.05,
        escalation_target="human",
    )
    runner = LangGraphLoopRunner(checkpointer, ledger=ledger)
    runner.with_exit_check(loop, lambda state: False)
    handle = runner.start(
        loop, {"spend": lambda ctx: {"cost_usd": ("spend", 0.02)}}, SCHEMA
    )
    assert handle.result["status"] == "breached"
    assert handle.result["breach"]["bound"] == "cost_usd"


# -- FR-M4-06: interrupt/resume at a human gate -----------------------------------------


def test_gate_suspend_persists_and_resume_completes(checkpointer, ledger) -> None:
    loop = LoopDefinition(
        loop_id="L2",
        entry_condition="story ready",
        body_graph=_graph(("build", "review")),
        exit_criteria="approved",
        max_iterations=5,
        token_budget=300_000,
        wall_clock_budget_s=1800,
        cost_ceiling_usd=3.0,
        escalation_target="human",
    )

    def build(ctx):
        if not ctx.state.get("progress"):
            return {"progress": ("build", ["built"])}
        return {}

    def review(ctx):
        if not ctx.state.get("approved"):
            raise GateSuspend(gate="human-approval", awaiting="approver decision")
        return {}

    runner = LangGraphLoopRunner(checkpointer, ledger=ledger)
    runner.with_exit_check(loop, lambda state: state.get("approved") is True)

    handle = runner.start(loop, {"build": build, "review": review}, SCHEMA)
    assert handle.result["status"] == "suspended"
    assert handle.result["gate"] == "human-approval"
    assert handle.state_snapshot["progress"] == ["built"]
    suspensions = [
        e for e in ledger.query(action_type="loop_event")
        if detail(ledger, e)["event"] == "gate_suspended"
    ]
    assert len(suspensions) == 1

    # The dashboard action: mark the approval, then resume from exactly
    # the state the gate saw.
    snapshot = dict(handle.state_snapshot)
    snapshot["approved"] = True

    def review_pass(ctx):
        return {"approved": ("review", True)}

    runner._nodes = {"build": build, "review": review_pass}
    resumed_state = LoopState.initial(SCHEMA)
    for name, value in snapshot.items():
        resumed_state.values[name] = value
    # Drive resume through the public API by re-attaching the snapshot.
    handle.state_snapshot = snapshot
    finished = runner.resume(handle)
    assert finished.result["status"] == "completed"
    assert finished.run_id == handle.run_id  # same run, not a fork
    assert ledger.verify().ok is True


# -- FR-M4-07: time travel forks are tagged, never live -------------------------------------


def test_replay_fork_is_tagged_replay_and_never_live(checkpointer, ledger) -> None:
    loop = LoopDefinition(
        loop_id="L5",
        entry_condition="candidate ready",
        body_graph=_graph(("train", "evaluate")),
        exit_criteria="beats incumbent",
        max_iterations=1,
        token_budget=500_000,
        wall_clock_budget_s=3600,
        cost_ceiling_usd=5.0,
        escalation_target="discard candidate",
    )
    runner = LangGraphLoopRunner(checkpointer, ledger=ledger)
    # Exit after the first pass: once train has written its progress.
    runner.with_exit_check(loop, lambda state: bool(state.get("progress")))
    nodes = {
        "train": lambda ctx: {"progress": ("train", ["v1"])},
        "evaluate": lambda ctx: {},
    }
    handle = runner.start(loop, nodes, SCHEMA, story_id="LEARN-1")
    assert handle.result["status"] == "completed"

    fork = runner.replay(handle, state_overrides={"approved": True})
    assert fork.result["status"] == "completed"
    assert fork.run_id != handle.run_id  # a fork, not the live run
    fork_events = [
        e for e in ledger.query(action_type="loop_event", story_id="LEARN-1")
        if e.get("replay_of") == handle.run_id
    ]
    assert len(fork_events) >= 1  # FR-M4-11 holds in the fork too
    live_events = [
        e for e in ledger.query(action_type="loop_event", story_id="LEARN-1")
        if not e.get("replay_of")
    ]
    assert len(live_events) >= 1  # live run's entries untouched
    assert ledger.verify().ok is True
