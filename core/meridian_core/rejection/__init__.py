"""Rejection capture (FR-M37-01 subset; F0 Workstream F task 28).

A *rejection* is detected deterministically from git history — no model
calls, no heuristics (FR-M36-07). Three shapes exist:

* ``reverted`` — a later commit removes every line the change added AND
  restores the lines the change removed (a revert, manual or ``git revert``).
* ``force_amended`` — the commit is no longer reachable from the ref (it was
  force-amended or reset away) and at least one line it added does not exist
  at the ref: its content disappeared from its commit's final form.
* ``replaced_within_window`` — a later commit removes every line the change
  added and replaces them with different content, within ``window_days``
  (default 7, the ``meridian.rejectionWindowDays`` workspace setting) of the
  change's commit date. Removal after the window is evolution, not rejection.

Conservative rules, by design: a change is only rejected when a single later
commit removes *all* of its added lines (multiset of path+content), so
partial edits never produce a rejection; and a change whose lines are
gradually removed across several commits is never flagged. Missed
rejections are preferred over false ones — this number feeds trust metrics.

No gate exists here and none is implied: detection records facts.
"""

from .detector import (
    DEFAULT_REJECTION_WINDOW_DAYS,
    REASON_FORCE_AMENDED,
    REASON_REPLACED_WITHIN_WINDOW,
    REASON_REVERTED,
    REJECTION_REASONS,
    Rejection,
    detect,
    resolve_ledger_sequence,
)
from ..attribution._git import AttributionError

__all__ = [
    "AttributionError",
    "DEFAULT_REJECTION_WINDOW_DAYS",
    "REASON_FORCE_AMENDED",
    "REASON_REPLACED_WITHIN_WINDOW",
    "REASON_REVERTED",
    "REJECTION_REASONS",
    "Rejection",
    "detect",
    "resolve_ledger_sequence",
]
