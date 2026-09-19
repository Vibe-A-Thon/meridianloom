"""M4 Loop Runtime — FR-M4-01…11, D1. Submodules: loops (definitions +
the six canonical loops), state (typed state + declared reducers), runner
(LangGraph + SQLite checkpointer behind the LoopRunner port)."""

from .loops import (
    BOUND_FIELDS,
    UNBOUNDED,
    LoopDefinition,
    LoopValidationError,
    WorkPacket,
    canonical_loops,
)
from .runner import (
    GateSuspend,
    LangGraphLoopRunner,
    LoopRunResult,
    LoopRunner,
    NodeContext,
    RunHandle,
)
from .state import (
    FieldSpec,
    LoopState,
    StateMergeError,
    add,
    append_unique,
    keep_max,
)

__all__ = [
    "BOUND_FIELDS",
    "UNBOUNDED",
    "LoopDefinition",
    "LoopValidationError",
    "WorkPacket",
    "canonical_loops",
    "GateSuspend",
    "LangGraphLoopRunner",
    "LoopRunResult",
    "LoopRunner",
    "NodeContext",
    "RunHandle",
    "FieldSpec",
    "LoopState",
    "StateMergeError",
    "add",
    "append_unique",
    "keep_max",
]
