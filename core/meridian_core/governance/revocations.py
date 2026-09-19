"""Identity revocation (FR-M42-06, NFR-36, SEC-31, AC-46; N2 Workstream B
task T08).

The revocation list is ledger-recorded: one ``identity_revocation`` row per
event (``revoked`` or ``reinstated``), newest entry per identity wins. The
list binds two enforcement points:

* ``gate.approve`` (server.py) refuses a NEW approval from a revoked
  identity, naming the recorded ``revokedAt`` — the refusal is effective
  from the instant the revocation row commits (AC-46);
* the merge gate (``merge_gate.check_merge``) excludes approvals a revoked
  identity recorded and blocks an in-flight merge authorisation whose
  bound approver has since been revoked (SEC-31: a session valid at issue
  SHALL NOT authorise a merge after its identity was revoked).

Propagation timing (NFR-36): within one sidecar process the effect is
IMMEDIATE — every check above reads the ledger anew, so a revocation
committed by any handler in this process binds the very next evaluation,
with no cache in between. The documented five-minute bound of NFR-36/AC-46
is the worst-case OUTER ENVELOPE for other replicas (e.g. an SCM-side
status-check consumer that polls or syncs the ledger); it is not the
in-process latency, which is one ledger read. ``revokedAt`` is the
provider-side instant the revocation took effect; in-process enforcement
uses row commit order, so a revocation back-dated before an in-flight
approval still binds that approval at its next evaluation (revocation is
not limited to approvals recorded after ``revokedAt``).

Zero model calls (FR-M36-07): reads and appends only.
"""

from __future__ import annotations

import json
from typing import Any

from ..ledger.core import Ledger, utc_now

#: Ledger action_type/decision values this module reads and writes.
REVOKE_ACTION = "identity_revocation"
REVOKED_DECISION = "revoked"
REINSTATED_DECISION = "reinstated"

#: Detail method markers (which surface recorded the row).
REVOKE_METHOD = "identity.revoke"
REINSTATE_METHOD = "identity.reinstate"


def _read_detail(ledger: Ledger, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def record_revocation(
    ledger: Ledger,
    *,
    email: str,
    revoked_by: str | None = None,
    reason: str | None = None,
    revoked_at: str | None = None,
    policy_version: str = "governance/revocation",
) -> int:
    """Append the ``revoked`` row (FR-M42-06/AC-46). Durable before the
    caller acts on it (FR-M10-08); effective in-process from commit."""
    address = _normalise_email(email)
    if not address:
        raise ValueError("revocation needs a non-empty identity email")
    detail: dict[str, Any] = {
        "method": REVOKE_METHOD,
        "email": address,
        "revokedAt": revoked_at or utc_now(),
    }
    if revoked_by:
        detail["revokedBy"] = revoked_by
    if reason:
        detail["reason"] = reason
    result = ledger.append(
        {
            "story_id": f"identity:{address}",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": policy_version,
            "action_type": REVOKE_ACTION,
            "decision": REVOKED_DECISION,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(detail, ensure_ascii=False),
        }
    )
    return result.sequence


def active_revocations(ledger: Ledger) -> dict[str, str]:
    """Revoked identities: lower-cased email -> ``revokedAt``. Newest entry
    per identity wins, so a later ``reinstated`` row clears the entry."""
    revoked: dict[str, str] = {}
    seen: set[str] = set()
    for row in reversed(ledger.query_all(action_type=REVOKE_ACTION)):
        detail = _read_detail(ledger, row)
        email = _normalise_email(str(detail.get("email") or ""))
        if not email or email in seen:
            continue
        seen.add(email)
        if row.get("decision") == REVOKED_DECISION:
            revoked[email] = str(detail.get("revokedAt") or row.get("ts_utc") or "")
    return revoked


def revoked_at(ledger: Ledger, email: str) -> str | None:
    """The ``revokedAt`` timestamp when ``email`` is revoked, else None."""
    return active_revocations(ledger).get(_normalise_email(email))
