"""The loop runtime — FR-M4-01/05/06/07/08/10/11.

D1: LangGraph executes the body graph and the SQLite checkpointer
(``SqliteSaver``) gives durable per-node checkpoints, so a process kill
loses at most one node's work (FR-M4-05). The runtime owns what LangGraph
deliberately does not: bound enforcement between iterations, per-iteration
ledger entries, human-gate suspension, replay tagging, and the typed merge
of parallel-branch updates (FR-M4-04 — the merge lives in ``state.py``;
a reducer-less field written by more than one branch in one pass raises
before any merge can silently order it away).

One super-step is ONE PASS over the body: FR-M4-01's cycles are rework
routing realised ACROSS iterations by the runner's while loop. Inside the
compiled graph a back-edge (target already reachable through kept edges)
is dropped, so the kept subgraph is a DAG visiting every node once per
pass, in dependency order.

FR-M4-07 honesty note: resuming a live thread from ANY of its checkpoints
is native (checkpoint_id addressing). A MODIFIED-STATE fork re-runs the
loop from its first iteration with the overrides applied — deterministic
node callables make the re-run faithful, and every entry is tagged
``replay_of``. Checkpoint-precise forks need a checkpointer state copy,
recorded in DECISIONS as the follow-up.
"""

from __future__ import annotations

import json
import operator
import time
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Mapping, Protocol, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import END, START

from .loops import LoopDefinition, LoopValidationError
from .state import FieldSpec, LoopState, StateMergeError

__all__ = [
    "BoundBreached",
    "GateSuspend",
    "LangGraphLoopRunner",
    "LoopRunner",
    "LoopRunResult",
    "NodeContext",
    "RunHandle",
]


class GateSuspend(Exception):
    """Raise from a node callable to suspend the loop at a human gate
    (FR-M4-06). The runner persists state, records the suspension, and
    returns a handle; ``resume`` continues from the checkpoint."""

    def __init__(self, gate: str, awaiting: str) -> None:
        super().__init__(f"gate '{gate}' awaits {awaiting}")
        self.gate = gate
        self.awaiting = awaiting


@dataclass(frozen=True)
class BoundBreached:
    """FR-M4-08: which bound halted the loop."""

    bound: str  # iterations | tokens | wall_clock_s | cost_usd
    limit: Any
    observed: Any


@dataclass(frozen=True)
class NodeContext:
    """What a node callable sees."""

    loop: LoopDefinition
    iteration: int
    state: LoopState
    packet: Any = None


#: A node callable returns state updates: {field: (branch, value)}.
NodeFn = Callable[[NodeContext], Mapping[str, tuple[str, Any]]]


class _GraphState(TypedDict):
    payload: dict[str, Any]
    writes: Annotated[list, operator.add]


class LoopRunResult(TypedDict, total=False):
    status: str  # completed | breached | suspended
    iterations: int
    breach: Mapping[str, Any] | None
    gate: str | None
    run_id: str
    story_id: str


@dataclass
class RunHandle:
    """A suspended or completed run. ``thread_id`` addresses the
    checkpointer thread; ``state_snapshot`` carries the merged typed state
    at suspension/completion so ``resume`` continues from exactly what the
    gate saw (the checkpointer covers node-level progress; the snapshot
    covers the loop-level merge)."""

    run_id: str
    thread_id: str
    definition: LoopDefinition
    result: LoopRunResult
    state_snapshot: Mapping[str, Any] = field(default_factory=dict)
    #: The state the run STARTED from. ``resume`` continues from the
    #: snapshot (what the gate saw); ``replay`` forks from the initial
    #: state plus the caller's overrides — re-executing the work, not
    #: inheriting a finished one.
    initial_state: Mapping[str, Any] = field(default_factory=dict)


class LoopRunner(Protocol):
    """The substitutable runtime port (D1). ``LangGraphLoopRunner`` is the
    reference implementation; anything honouring this protocol can back
    the runtime instead."""

    def start(
        self,
        definition: LoopDefinition,
        nodes: Mapping[str, NodeFn],
        schema: Mapping[str, FieldSpec],
        *,
        initial: Mapping[str, Any] | None = None,
        story_id: str = "loop-run",
    ) -> RunHandle: ...

    def resume(self, handle: RunHandle) -> RunHandle: ...

    def replay(
        self,
        handle: RunHandle,
        *,
        state_overrides: Mapping[str, Any],
        from_iteration: int = 1,
    ) -> RunHandle: ...


class LangGraphLoopRunner:
    """The reference loop runner (D1).

    One runner instance serves one run at a time (``start`` → terminal
    handle → ``resume``/``replay``); the retained node/schema maps make
    resume and replay addressable without serialising callables.
    """

    def __init__(
        self,
        checkpointer: SqliteSaver,
        *,
        ledger: Any = None,
        concurrency_cap: int = 4,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._checkpointer = checkpointer
        self._ledger = ledger
        #: FR-M4-10: global concurrency cap; a fan-out wider than the cap
        #: is refused at load, before anything is scheduled.
        self._concurrency_cap = concurrency_cap
        self._now = now
        self._nodes: Mapping[str, NodeFn] = {}
        self._schemas: Mapping[str, FieldSpec] = {}
        self._exit_checks: dict[int, Callable[[LoopState], bool]] = {}

    # -- public API ------------------------------------------------------------

    def with_exit_check(
        self, definition: LoopDefinition, checker: Callable[[LoopState], bool]
    ) -> None:
        """FR-M4-03 exit criteria are evaluated by the caller-supplied
        checker — the definition declares the criterion in words; the
        checker is the executable predicate."""
        self._exit_checks[definition.loop_id] = checker

    def start(
        self,
        definition: LoopDefinition,
        nodes: Mapping[str, NodeFn],
        schema: Mapping[str, FieldSpec],
        *,
        initial: Mapping[str, Any] | None = None,
        story_id: str = "loop-run",
    ) -> RunHandle:
        definition.validate()  # FR-M4-02: load-time, before anything runs
        self._validate_fanout(definition)
        self._nodes = dict(nodes)
        self._schemas = dict(schema)
        state = LoopState.initial(schema)
        for name, value in (initial or {}).items():
            state.set(name, value)
        return self._run(
            definition, state, story_id, run_id=None, thread_id=None, replay_of=None,
            initial_state=dict(state.values),
        )

    def resume(self, handle: RunHandle) -> RunHandle:
        """FR-M4-06: continue a suspended run from exactly the state the
        gate saw. The caller updates what the gate awaited (e.g. marks a
        human approval in the state) before resuming."""
        state = LoopState.initial(self._schemas)
        for name, value in handle.state_snapshot.items():
            state.values[name] = value
        return self._run(
            handle.definition,
            state,
            handle.result.get("story_id", "loop-run"),
            run_id=handle.run_id,
            thread_id=handle.thread_id,
            replay_of=None,
            initial_state=dict(handle.initial_state),
        )

    def replay(
        self,
        handle: RunHandle,
        *,
        state_overrides: Mapping[str, Any],
        from_iteration: int = 1,
    ) -> RunHandle:
        """FR-M4-07: a MODIFIED-STATE fork. Re-runs from the loop's first
        iteration with the overrides applied; every emitted ledger entry
        is tagged ``replay_of`` and never counted as live work."""
        state = LoopState.initial(self._schemas)
        for name, value in handle.initial_state.items():
            state.values[name] = value
        for name, value in state_overrides.items():
            state.set(name, value, branch="replay")
        return self._run(
            handle.definition,
            state,
            handle.result.get("story_id", "loop-run"),
            run_id=None,
            thread_id=None,
            replay_of=handle.run_id,
            from_iteration=from_iteration,
            initial_state=dict(handle.initial_state),
        )

    # -- internals ---------------------------------------------------------------

    def _run(
        self,
        definition: LoopDefinition,
        state: LoopState,
        story_id: str,
        run_id: str | None,
        thread_id: str | None,
        replay_of: str | None,
        from_iteration: int = 1,
        initial_state: Mapping[str, Any] | None = None,
    ) -> RunHandle:
        run_id = run_id or uuid.uuid4().hex[:12]
        thread_id = thread_id or f"loop-{run_id}"
        graph = self._compile(definition)
        app = graph.compile(checkpointer=self._checkpointer)
        tokens_used = 0
        cost_used = 0.0
        started = self._now()
        config = {"configurable": {"thread_id": thread_id}}
        iteration = from_iteration
        schema = self._schemas
        self._pending_writes: list[tuple[str, dict]] = []

        while True:
            # Exit criteria before bounds: a loop that has finished has
            # consumed nothing further and must not breach (FR-M4-08
            # governs runs that are still going).
            if self._exit_checks[definition.loop_id](state):
                break
            breach = self._check_bounds(
                definition, iteration, tokens_used, cost_used, started
            )
            if breach is not None:
                self._record_breach(definition, story_id, run_id, replay_of, breach)
                return RunHandle(
                    run_id=run_id,
                    thread_id=thread_id,
                    definition=definition,
                    state_snapshot=dict(state.values),
                    initial_state=dict(initial_state or {}),
                    result={
                        "status": "breached",
                        "iterations": iteration - from_iteration,
                        "breach": {
                            "bound": breach.bound,
                            "limit": breach.limit,
                            "observed": breach.observed,
                        },
                        "story_id": story_id,
                    },
                )
            try:
                outcome = app.invoke(
                    {
                        "payload": {"state": state.values, "iteration": iteration},
                        "writes": [],
                    },
                    config,
                )
            except GateSuspend as suspend:
                # The pass aborted mid-graph: nodes that already ran kept
                # their writes in _pending_writes — apply them so the
                # suspension persists what the gate saw (FR-M4-06).
                state = self._apply_writes(schema, state, self._pending_writes)
                # FR-M4-06: persist (checkpointer already did), record, stop.
                self._record(
                    definition, story_id, run_id, replay_of, iteration,
                    "gate_suspended",
                    {"gate": suspend.gate, "awaiting": suspend.awaiting},
                )
                return RunHandle(
                    run_id=run_id,
                    thread_id=thread_id,
                    definition=definition,
                    state_snapshot=dict(state.values),
                    initial_state=dict(initial_state or {}),
                    result={
                        "status": "suspended",
                        "iterations": iteration - from_iteration,
                        "gate": suspend.gate,
                        "story_id": story_id,
                    },
                )
            state = self._apply_writes(schema, state, list(outcome["writes"]))
            tokens_used += self._sum_field(state, "tokens_used")
            cost_used += self._sum_field(state, "cost_usd")
            # FR-M4-11: at least one ledger entry before the next iteration.
            self._record(
                definition, story_id, run_id, replay_of, iteration,
                "loop_iteration",
                {"tokens_used": tokens_used, "cost_usd": cost_used},
            )
            iteration += 1
        return RunHandle(
            run_id=run_id,
            thread_id=thread_id,
            definition=definition,
            state_snapshot=dict(state.values),
            initial_state=dict(initial_state or {}),
            result={
                "status": "completed",
                "iterations": iteration - from_iteration,
                "story_id": story_id,
            },
        )

    def _compile(self, definition: LoopDefinition) -> StateGraph:
        graph = StateGraph(_GraphState)
        for node_id in definition.body_graph:
            fn = self._nodes.get(node_id)
            if fn is None:
                raise LoopValidationError(
                    f"FR-M4-02: loop '{definition.loop_id}' references node"
                    f" '{node_id}' with no callable"
                )
            graph.add_node(node_id, self._wrap(definition, node_id, fn))
        entry = next(iter(definition.body_graph))
        graph.add_edge(START, entry)
        # One super-step = one pass. Back-edges (rework routing) are
        # realised ACROSS iterations; drop an edge whose target is already
        # reachable through kept edges so the compiled graph is a DAG
        # visiting every node once per pass, in dependency order.
        kept: dict[str, list[str]] = {n: [] for n in definition.body_graph}
        for source in definition.body_graph:
            for target in definition.body_graph[source]:
                # Adding u->v closes a cycle iff v can already reach u.
                # The trivial path counts: a self-loop (u == v) is always
                # a cycle and must be dropped for the one-pass DAG.
                if source == target or not self._reachable(kept, target, source):
                    kept[source].append(target) if source != target else None
        for source, targets in kept.items():
            for target in targets:
                graph.add_edge(source, target)
        terminal = [n for n, t in kept.items() if not t]
        for node_id in terminal:
            graph.add_edge(node_id, END)
        if not terminal:
            graph.add_edge(entry, END)
        return graph

    @staticmethod
    def _reachable(edges: Mapping[str, list[str]], source: str, target: str) -> bool:
        stack = list(edges.get(source, []))
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(edges.get(node, []))
        return False

    def _wrap(self, definition: LoopDefinition, node_id: str, fn: NodeFn):
        def node(state: _GraphState) -> dict[str, Any]:
            loop_state = LoopState.initial(self._schemas)
            loop_state.values = dict(state["payload"]["state"])
            ctx = NodeContext(
                loop=definition,
                iteration=state["payload"].get("iteration", 1),
                state=loop_state,
            )
            updates = fn(ctx) or {}
            self._pending_writes.append((node_id, dict(updates)))
            return {"writes": [(node_id, dict(updates))]}

        return node

    def _check_bounds(
        self,
        definition: LoopDefinition,
        iteration: int,
        tokens_used: int,
        cost_used: float,
        started: float,
    ) -> BoundBreached | None:
        if (
            isinstance(definition.max_iterations, int)
            and iteration > definition.max_iterations
        ):
            return BoundBreached("iterations", definition.max_iterations, iteration)
        if (
            isinstance(definition.token_budget, int)
            and tokens_used > definition.token_budget
        ):
            return BoundBreached("tokens", definition.token_budget, tokens_used)
        if (
            isinstance(definition.wall_clock_budget_s, int)
            and (self._now() - started) > definition.wall_clock_budget_s
        ):
            return BoundBreached(
                "wall_clock_s",
                definition.wall_clock_budget_s,
                round(self._now() - started, 3),
            )
        if (
            isinstance(definition.cost_ceiling_usd, (int, float))
            and cost_used > definition.cost_ceiling_usd
        ):
            return BoundBreached("cost_usd", definition.cost_ceiling_usd, cost_used)
        return None

    @staticmethod
    def _apply_writes(
        schema: Mapping[str, FieldSpec],
        state: LoopState,
        writes: list[tuple[str, dict]],
    ) -> LoopState:
        # FR-M4-04 pre-check: a reducer-less field written by more than
        # one branch IN THE SAME PASS is a conflict that surfaces here —
        # before any merge can silently order it away.
        field_branches: dict[str, set[str]] = {}
        for branch, update in writes:
            for name in update:
                field_branches.setdefault(name, set()).add(branch)
        for name, branches in field_branches.items():
            spec = schema.get(name)
            if spec is not None and spec.reducer is None and len(branches) > 1:
                raise StateMergeError(
                    f"FR-M4-04: field {name!r} written by parallel"
                    f" branches {sorted(branches)} in one pass with no"
                    " declared reducer"
                )
        merged = LoopState.initial(schema)
        merged.values = dict(state.values)
        merged.provenance = dict(state.provenance)
        for branch, update in writes:
            merged.merge({k: v for k, v in update.items()})
        return merged

    def _validate_fanout(self, definition: LoopDefinition) -> None:
        # FR-M4-10: the concurrency cap bounds parallel packets; a fan-out
        # wider than the cap is refused at load. (Path-overlap refusal is
        # FR-M4-09 in LoopDefinition.validate.)
        if len(definition.fan_out_packets) > self._concurrency_cap:
            raise LoopValidationError(
                f"FR-M4-10: fan-out of {len(definition.fan_out_packets)} packets"
                f" exceeds the concurrency cap {self._concurrency_cap}"
            )

    @staticmethod
    def _sum_field(state: LoopState, name: str) -> Any:
        value = state.values.get(name)
        return value if isinstance(value, (int, float)) else 0

    def _record(
        self,
        definition: LoopDefinition,
        story_id: str,
        run_id: str,
        replay_of: str | None,
        iteration: int,
        event: str,
        detail: Mapping[str, Any],
    ) -> None:
        if self._ledger is None:
            return
        entry = {
            "story_id": story_id,
            "phase": "build",
            "loop_id": definition.loop_id,
            "loop_iteration": iteration,
            "actor_id": "loop-runtime",
            "actor_version": "m4/v1",
            "actor_kind": "meta",
            "policy_version": "loops/v1",
            "action_type": "loop_event",
            "run_id": run_id,
            "input": json.dumps({"event": event, **detail}, ensure_ascii=False),
        }
        if replay_of is not None:
            entry["replay_of"] = replay_of
        self._ledger.append(entry)

    def _record_breach(
        self,
        definition: LoopDefinition,
        story_id: str,
        run_id: str,
        replay_of: str | None,
        breach: BoundBreached,
    ) -> None:
        # FR-M4-08: halt + ledger entry naming the breach + the declared
        # escalation target. Never silently continue, never silently stop.
        self._record(
            definition, story_id, run_id, replay_of, 0,
            "bound_breached",
            {
                "bound": breach.bound,
                "limit": breach.limit,
                "observed": breach.observed,
                "escalation_target": definition.escalation_target,
            },
        )
