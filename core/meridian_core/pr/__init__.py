"""External PR gating: PR ingest as a Meridian story (FR-M35-04, FR-M35-05).

A pull request opened by an external agent (Copilot's coding agent, Devin,
a bridged ACP agent) is ingested as a Meridian story: the PR becomes the
story's origin record, every hunk is attributed to its agent with an
observation confidence, and the payload is routed through the policy gate
engine (Verify/Security/Review profiles). Merge permission is NOT granted
here — it flows only through the merge gate with a recorded human approval
(:mod:`meridian_core.governance.merge_gate`, FR-M12-05), reconciled in one
ledger range (AC-32).

The ingest payload uses the recorded-real GitHub REST API shapes the
Copilot observer fixtures already carry (``pulls.json`` and friends):
the PR object, its ``commits`` (the list-commits-for-a-pull shape) and its
``files`` (the list-files shape with per-file ``patch``). No invented
field names. In production the SCM connectors of M23 source this payload;
the connectors land later — this module is the ingest PIPELINE they feed.

Agent attribution per hunk, in precedence order (FR-M35-02):

1. ``Co-Authored-By`` trailers in the PR's commit messages — the vendor
   identity the committing agent recorded itself (``direct``-strength
   evidence observed via the SCM API, labelled ``telemetry``).
2. Author markers — the PR author's login/type against the known vendor
   bot patterns (``telemetry``).
3. Heuristic fallback — the PR author as an unverified agent identity,
   always labelled ``inferred`` (G3: the floor, never presented as fact).

Zero model calls (FR-M36-07): every step is string matching and diff
parsing over the payload.
"""

from .ingest import (
    AgentAttribution,
    HunkAttribution,
    IngestError,
    PullRequest,
    attribute_hunks,
    parse_pr,
    resolve_agents,
    subject_for,
    ticket_for,
)

__all__ = [
    "AgentAttribution",
    "HunkAttribution",
    "IngestError",
    "PullRequest",
    "attribute_hunks",
    "parse_pr",
    "resolve_agents",
    "subject_for",
    "ticket_for",
]
