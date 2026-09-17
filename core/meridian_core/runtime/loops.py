"""Loop definitions and the six canonical loops — FR-M4-02/03.

FR-M4-02: every loop declares eight bound fields. A loop missing ANY
field fails validation at load time and never executes — partial bounds
are how runaway loops happen.

FR-M4-03: the six canonical loops with the §6.1 default bounds. L4's
exit criterion carries the §3 amendment: "merged AND CI green".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


class LoopValidationError(ValueError):
    """A loop definition is missing a bound field or is otherwise invalid
    at load time (FR-M4-02). Carries the requirement ID."""


#: The eight bound fields of FR-M4-02. ``None`` is meaningful ONLY where
#: §6.1 declares the loop unbounded (L4 iterations, L6 budgets) — a
#: missing KEY is never the same as a declared unbounded field.
BOUND_FIELDS = (
    "entry_condition",
    "body_graph",
    "exit_criteria",
    "max_iterations",
    "token_budget",
    "wall_clock_budget_s",
    "cost_ceiling_usd",
    "escalation_target",
)

#: Sentinel for a field §6.1 declares unbounded (L4 max_iterations, L6
#: budgets). Distinct from "absent": the declaration is explicit.
UNBOUNDED = "unbounded"


@dataclass(frozen=True)
class WorkPacket:
    """One fan-out packet (FR-M4-09). ``target_paths`` is the file-path
    granularity at which the Tech Lead Agent declared non-overlap."""

    packet_id: str
    target_paths: tuple[str, ...]
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoopDefinition:
    """One loop. ``body_graph`` maps node id -> list of successor node ids
    (cycles permitted, FR-M4-01). Nodes are agent-invocation callables
    supplied by the runner, not by this definition."""

    loop_id: str
    entry_condition: str
    body_graph: Mapping[str, tuple[str, ...]]
    exit_criteria: str
    max_iterations: int | str | None  # UNBOUNDED as declared, else int
    token_budget: int | str | None
    wall_clock_budget_s: int | str | None
    cost_ceiling_usd: float | str | None
    escalation_target: str
    fan_out_packets: tuple[WorkPacket, ...] = ()

    def validate(self) -> None:
        """FR-M4-02: fail at load time — never execute a partially-bound
        loop. Every bound field must be PRESENT (declared); UNBOUNDED is
        allowed only where §6.1 says so."""
        declared = {
            name: getattr(self, name) for name in BOUND_FIELDS
        }
        missing = [name for name, value in declared.items() if value is None]
        if missing:
            raise LoopValidationError(
                f"FR-M4-02: loop '{self.loop_id}' is missing bound fields"
                f" {missing}; a partially bound loop must not execute"
            )
        if self.body_graph is None or not self.body_graph:
            raise LoopValidationError(
                f"FR-M4-02: loop '{self.loop_id}' has an empty body graph"
            )
        nodes = set(self.body_graph)
        for successors in self.body_graph.values():
            unknown = set(successors) - nodes
            if unknown:
                raise LoopValidationError(
                    f"FR-M4-02: loop '{self.loop_id}' edges point at unknown"
                    f" nodes {sorted(unknown)}"
                )
        # L4 alone may declare UNBOUNDED iterations; L6 alone may declare
        # UNBOUNDED budgets (§6.1). Any other loop doing so is invalid —
        # unboundedness is a reviewed declaration, not a default.
        if self.max_iterations == UNBOUNDED and self.loop_id not in ("L4", "L6"):
            raise LoopValidationError(
                f"FR-M4-02: only L4 (delivery) and L6 (organisation) may"
                f" declare unbounded iterations per section 6.1;"
                f" '{self.loop_id}' may not"
            )
        for name in ("token_budget", "wall_clock_budget_s", "cost_ceiling_usd"):
            if declared[name] == UNBOUNDED and self.loop_id != "L6":
                raise LoopValidationError(
                    f"FR-M4-02: only L6 may declare {name} unbounded; "
                    f"'{self.loop_id}' may not"
                )
        if isinstance(self.max_iterations, int) and self.max_iterations < 1:
            raise LoopValidationError(
                f"FR-M4-02: max_iterations must be >= 1, got"
                f" {self.max_iterations}"
            )
        # FR-M4-09: a fan-out whose packets share a target path is rejected
        # at load — before any work is scheduled.
        seen: set[str] = set()
        for packet in self.fan_out_packets:
            overlap = seen & set(packet.target_paths)
            if overlap:
                raise LoopValidationError(
                    f"FR-M4-09: fan-out packets in '{self.loop_id}' share"
                    f" target paths {sorted(overlap)}; the Tech Lead must"
                    " declare file-path-granular non-overlap"
                )
            seen |= set(packet.target_paths)

    @property
    def bounded(self) -> bool:
        return self.validate() is None


def _graph(*edges: tuple[str, str]) -> dict[str, tuple[str, ...]]:
    nodes: dict[str, list[str]] = {}
    for source, target in edges:
        nodes.setdefault(source, []).append(target)
        nodes.setdefault(target, [])
    return {k: tuple(v) for k, v in nodes.items()}


def canonical_loops() -> dict[str, LoopDefinition]:
    """FR-M4-03: the six canonical loops with §6.1 default bounds."""
    return {
        "L1": LoopDefinition(
            loop_id="L1",
            entry_condition="a unit of work with its tests is scoped",
            body_graph=_graph(("micro", "verify"), ("verify", "micro")),
            exit_criteria="unit compiles, its tests pass",
            max_iterations=3,
            token_budget=50_000,
            wall_clock_budget_s=5 * 60,
            cost_ceiling_usd=0.50,
            escalation_target="L2 with failure trace",
        ),
        "L2": LoopDefinition(
            loop_id="L2",
            entry_condition="a story work packet is ready in its worktree",
            body_graph=_graph(
                ("build", "review"), ("review", "build"), ("review", "verify")
            ),
            exit_criteria="reviewer approves and tests green",
            max_iterations=5,
            token_budget=300_000,
            wall_clock_budget_s=30 * 60,
            cost_ceiling_usd=3.00,
            escalation_target="human, with the work packet",
        ),
        "L3": LoopDefinition(
            loop_id="L3",
            entry_condition="phase entry gate satisfied",
            body_graph=_graph(
                ("execute", "gate"), ("gate", "execute"), ("gate", "done")
            ),
            exit_criteria="exit gate satisfied",
            max_iterations=3,
            token_budget=800_000,
            wall_clock_budget_s=2 * 3600,
            cost_ceiling_usd=8.00,
            escalation_target="phase escalation with gate diff",
        ),
        "L4": LoopDefinition(
            loop_id="L4",
            entry_condition="delivery run started from a confirmed preflight",
            body_graph=_graph(("intake", "design"), ("design", "plan"),
                              ("plan", "build"), ("build", "verify"),
                              ("verify", "security"), ("security", "review"),
                              ("review", "verify")),
            # §3 amendment: merged AND CI green (FR-M23-01/02).
            exit_criteria="PR merged and CI green",
            max_iterations=UNBOUNDED,
            token_budget=2_000_000,
            wall_clock_budget_s=8 * 3600,
            cost_ceiling_usd=20.00,
            escalation_target="chief orchestrator",
        ),
        "L5": LoopDefinition(
            loop_id="L5",
            entry_condition="a learning candidate and regression pack exist",
            body_graph=_graph(("train", "evaluate")),
            exit_criteria="candidate beats incumbent on the regression pack",
            max_iterations=1,
            token_budget=500_000,
            wall_clock_budget_s=3600,
            cost_ceiling_usd=5.00,
            escalation_target="discard candidate, log the attempt",
        ),
        "L6": LoopDefinition(
            loop_id="L6",
            entry_condition="the organisation is running",
            body_graph=_graph(("observe", "adjust"), ("adjust", "observe")),
            exit_criteria="continuous",
            max_iterations=UNBOUNDED,
            token_budget=UNBOUNDED,
            wall_clock_budget_s=UNBOUNDED,
            cost_ceiling_usd=UNBOUNDED,
            escalation_target="governance review",
        ),
    }
