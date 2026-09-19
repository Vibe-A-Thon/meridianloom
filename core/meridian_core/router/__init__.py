"""FR-M8-15/16/17 (gaps_implementation.md F3, step 2): the Model Router
sits BEHIND the Deterministic Engine — every agent action is dispatched to
the engine first (FR-M33-03), and only an engine outcome that is
``router_eligible`` may reach a model call.

- FR-M8-15: a model call for an action class whose engine outcome is not
  router-eligible is REFUSED — unless policy explicitly permits it (the
  human-override path). Refusals are ledger-recorded.
- FR-M8-16: every permitted call carries ``why_llm`` from the closed
  vocabulary (``no_deterministic_path`` · ``assisted_gap`` ·
  ``generative_by_policy`` · ``human_override``), recorded in the ledger.
  ``human_override`` is assigned HERE, never by the engine.
- FR-M8-17: the LLM dependency ratio per agent/phase/story/action class,
  with a policy ceiling that escalates (ledger-recorded) when breached.

Zero model calls: this module decides and records; it never invokes a
model client.
"""

from .routing import (
    WHY_HUMAN_OVERRIDE,
    WHY_LLM_VOCABULARY,
    DependencyRatio,
    RouteDecision,
    Router,
    RouterError,
)

__all__ = [
    "WHY_HUMAN_OVERRIDE",
    "WHY_LLM_VOCABULARY",
    "DependencyRatio",
    "RouteDecision",
    "Router",
    "RouterError",
]
