"""Nothing leaves the machine through a third-party library's back door.

The sidecar depends on LangGraph, which pulls in ``langchain-core`` and
``langsmith``. LangSmith is an *observability upload*: when its environment
variables are set (``LANGSMITH_TRACING=true`` plus an API key, the standard
setup for anyone who uses LangSmith for other work), every graph run is sent to
LangChain's cloud — inputs, outputs and state included. The sidecar inherits
its environment from the editor, so a developer who exported those variables
for an unrelated project would have started uploading Meridian's loop state
without ever being asked (audit finding CLD-C01; reproduced with a local
listener: three ``POST /runs/multipart`` requests from one ``loop.start``).

Meridian's position — ``docs/SECURITY-AND-DATA.md`` — is that nothing leaves
the machine unless the user configures an export sink. So this module, in two
layers:

1. :func:`disable_third_party_telemetry` runs when ``meridian_core`` is
   imported. It removes the LangChain/LangSmith/LangGraph variable families
   from the process environment and pins tracing off, so the headless CLI and
   any other launcher are covered, not only the extension.
2. :func:`no_tracing` wraps graph execution in an explicit "tracing disabled"
   context, so even a variable set *after* import cannot turn uploads on.

There is deliberately no opt-out switch here. A user who wants LangSmith traces
of their own LangGraph code can have them — in their own process.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, MutableMapping

#: Variable families that configure uploads or remote endpoints. Removed.
SCRUBBED_PREFIXES: tuple[str, ...] = ("LANGSMITH_", "LANGCHAIN_", "LANGGRAPH_")

#: Set after scrubbing so a library that defaults to "on" when unset stays off.
FORCED_OFF: dict[str, str] = {
    "LANGSMITH_TRACING": "false",
    "LANGSMITH_TRACING_V2": "false",
    "LANGCHAIN_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "OTEL_SDK_DISABLED": "true",
}


def disable_third_party_telemetry(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Scrub and pin ``environ`` (default ``os.environ``); return the names
    removed, for diagnostics. Idempotent."""
    env = os.environ if environ is None else environ
    removed = [key for key in list(env) if key.upper().startswith(SCRUBBED_PREFIXES)]
    for key in removed:
        del env[key]
    env.update(FORCED_OFF)
    return removed


@contextmanager
def no_tracing() -> Iterator[None]:
    """Run a block with LangSmith tracing explicitly disabled, whatever the
    environment says at that moment."""
    try:
        from langsmith import tracing_context
    except ImportError:  # langsmith is a transitive dependency; absent is fine
        yield
        return
    with tracing_context(enabled=False):
        yield
