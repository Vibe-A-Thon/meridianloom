"""Three-state attribution and the closed unknown-reason vocabulary
(FR-M41-04, FR-M41-05; principle P26; N1 Workstream B T07/T08).

FR-M41-04: attribution reports exactly three mutually exclusive states —
``agent``, ``human``, ``unattributed`` — and NEVER derives any state by
subtracting the others from a total. ``human = not agent`` is banned: the
human state requires positive human evidence, exactly as the agent state
requires positive agent evidence. A span with evidence for neither (or
evidence that resolves to neither) is ``unattributed`` — unknown is a
state, never a residual (P26).

FR-M41-05: every ``unattributed`` span carries the reason it could not be
resolved, from a CLOSED, VERSIONED vocabulary — recorded with each
classification so a corpus evaluated against vocabulary v1 stays
comparable to a corpus evaluated against v2:

* ``no_signal`` — no decisive authorship signal fired (including the
  non-decisive middle band where agent and human evidence conflict);
* ``formatter_rewrite`` — the introducing commit is a mechanical
  formatting sweep (message/change shape), so its lines carry no
  authorship signal;
* ``squashed_history`` — the introducing commit is a squash merge whose
  per-author detail was destroyed;
* ``pre_installation`` — the commit predates Meridian's installation and
  no positive authorship evidence survives in git;
* ``unsupported_vendor`` — the author markers indicate a bot/agent from a
  vendor Meridian does not recognise, so no positive state can be claimed;
* ``excluded_path`` — the path is excluded from attribution (policy or
  caller), so no signal was sought there.

FR-M41-01/02 (T10): every provenance field carries one of exactly four
states — ``observed`` / ``inferred`` / ``unknown`` / ``redacted`` — plus
its source, capture method, contract version and capture timestamp.
Signing never promotes ``inferred`` to ``observed``.

Zero model calls (FR-M36-07): constants and integer arithmetic only.
"""

from __future__ import annotations

__all__ = [
    "ATTRIBUTION_AGENT",
    "ATTRIBUTION_CONTRACT_VERSION",
    "ATTRIBUTION_HUMAN",
    "ATTRIBUTION_STATES",
    "ATTRIBUTION_UNATTRIBUTED",
    "PROVENANCE_INFERRED",
    "PROVENANCE_OBSERVED",
    "PROVENANCE_REDACTED",
    "PROVENANCE_STATES",
    "PROVENANCE_UNKNOWN",
    "UNKNOWN_REASONS",
    "UNKNOWN_REASON_EXCLUDED_PATH",
    "UNKNOWN_REASON_FORMATTER_REWRITE",
    "UNKNOWN_REASON_NO_SIGNAL",
    "UNKNOWN_REASON_PRE_INSTALLATION",
    "UNKNOWN_REASON_SQUASHED_HISTORY",
    "UNKNOWN_REASON_UNSUPPORTED_VENDOR",
    "UNKNOWN_REASON_VOCABULARY_VERSION",
    "decide_attribution",
    "is_unknown_reason",
]

#: The three mutually exclusive attribution states (FR-M41-04).
ATTRIBUTION_AGENT = "agent"
ATTRIBUTION_HUMAN = "human"
ATTRIBUTION_UNATTRIBUTED = "unattributed"
ATTRIBUTION_STATES = (ATTRIBUTION_AGENT, ATTRIBUTION_HUMAN, ATTRIBUTION_UNATTRIBUTED)

#: The closed unknown-reason vocabulary (FR-M41-05), in canonical order.
UNKNOWN_REASON_NO_SIGNAL = "no_signal"
UNKNOWN_REASON_FORMATTER_REWRITE = "formatter_rewrite"
UNKNOWN_REASON_SQUASHED_HISTORY = "squashed_history"
UNKNOWN_REASON_PRE_INSTALLATION = "pre_installation"
UNKNOWN_REASON_UNSUPPORTED_VENDOR = "unsupported_vendor"
UNKNOWN_REASON_EXCLUDED_PATH = "excluded_path"
UNKNOWN_REASONS = (
    UNKNOWN_REASON_NO_SIGNAL,
    UNKNOWN_REASON_FORMATTER_REWRITE,
    UNKNOWN_REASON_SQUASHED_HISTORY,
    UNKNOWN_REASON_PRE_INSTALLATION,
    UNKNOWN_REASON_UNSUPPORTED_VENDOR,
    UNKNOWN_REASON_EXCLUDED_PATH,
)

#: Bumped whenever the vocabulary or a reason's meaning changes; recorded
#: with every classification so evaluated corpora stay versioned.
UNKNOWN_REASON_VOCABULARY_VERSION = 1

#: The provenance contract version recorded with every provenance answer
#: (FR-M41-01) and every classification.
ATTRIBUTION_CONTRACT_VERSION = "attrib-provenance/v1"

#: The four provenance field states (FR-M41-02). Signing an artefact never
#: promotes ``inferred`` to ``observed``.
PROVENANCE_OBSERVED = "observed"
PROVENANCE_INFERRED = "inferred"
PROVENANCE_UNKNOWN = "unknown"
PROVENANCE_REDACTED = "redacted"
PROVENANCE_STATES = (
    PROVENANCE_OBSERVED,
    PROVENANCE_INFERRED,
    PROVENANCE_UNKNOWN,
    PROVENANCE_REDACTED,
)


def is_unknown_reason(reason: str | None) -> bool:
    """The vocabulary is closed: a reason is admissible only if it is one
    of the six (FR-M41-05). ``None`` is admissible only on attributed
    spans — callers pair this with the state."""
    return reason in UNKNOWN_REASONS


def decide_attribution(
    agent_points: int,
    human_points: int,
    agent_cutoff: float = 0.66,
    human_cutoff: float = 0.33,
) -> tuple[str, float]:
    """The FR-M41-04 decision in one auditable place, positive evidence only.

    * agent evidence present and dominant (weight >= ``agent_cutoff``)
      -> ``agent``;
    * human evidence present and dominant (weight <= ``human_cutoff``)
      -> ``human``;
    * anything else — no evidence fired, or the evidence is non-decisive
      (agent and human signals in the middle band) -> ``unattributed``.

    The complement of one state is never another state: a span is human
    only on positive human evidence, never because it is "not agent".
    Returns ``(state, weight)`` where weight is 0.5 when no evidence
    fired (the documented "no evidence" marker).
    """
    if agent_points <= 0 and human_points <= 0:
        return ATTRIBUTION_UNATTRIBUTED, 0.5
    weight = round(agent_points / (agent_points + human_points), 2)
    if agent_points > 0 and weight >= agent_cutoff:
        return ATTRIBUTION_AGENT, weight
    if human_points > 0 and weight <= human_cutoff:
        return ATTRIBUTION_HUMAN, weight
    return ATTRIBUTION_UNATTRIBUTED, weight
