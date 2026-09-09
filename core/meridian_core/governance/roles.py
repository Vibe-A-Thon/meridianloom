"""Human roles and approval mechanics (FR-M20-02…08; F1 Workstream C task 16).

The role pack is the second policy document beside the governance pack
(``policy/roles.yaml`` in the repository; ``.meridian/policy/roles.yaml``
overrides it in the workspace). It defines the FR-M20-02 roles — Engineer,
Reviewer, Approver, Governor, Auditor — and maps them to permitted gate
actions:

* ``approve`` — record a merge-gate approval;
* ``halt`` — governance halts (FR-M12-06);
* ``policy-change`` — FR-M20-07: only Governor changes policy or promotes;
* ``delegate`` — grant an approval right onward (FR-M20-05);
* ``export-audit`` — FR-M20-08: the Auditor's audit-bundle export.

Parsing is fail-closed exactly like the governance pack: YAML errors and
schema violations come back as ``errors`` and the pack refuses every
check. One deliberate difference: when NO file exists anywhere AND no
shipped default was packaged (a broken install), the built-in default
(the same five roles, SoD on, N-of-M empty, delegation 2-deep/30-day,
hygiene floors) keeps the merge gate functional — a last resort the D43
bootstrap makes unreachable in a normal workspace. Absent-file behaviour
otherwise follows the uniform contract (stated once in
``governance/bootstrap.py``): the bootstrap scaffolds the shipped
``roles.yaml`` into ``<ws>/.meridian/policy/`` on workspace handshake. A
PRESENT but malformed file fails closed instead, with the remedy named.

The module also carries the three ledger-backed mechanics the merge gate
and the RPCs consume: N-of-M counting support lives in merge_gate; here
live the delegation ledger scans (:func:`find_active_delegation`) and the
approval-hygiene signals (:func:`assess_hygiene`, FR-M20-06) measured from
ledger history — the F2 measurement hook.

Zero model calls (FR-M36-07): everything is YAML parsing and ledger reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .bootstrap import FAIL_CLOSED_REMEDY

#: Gate actions the pack maps roles to (FR-M20-02/07/08).
ACTIONS = ("approve", "halt", "policy-change", "delegate", "export-audit")

_TOP_LEVEL_KEYS = (
    "version",
    "defaultRole",
    "roles",
    "approvals",
    "soD",
    "delegation",
    "hygiene",
)

_ROLE_KEYS = ("description", "permissions", "readOnly")


@dataclass(frozen=True)
class RoleSpec:
    """One FR-M20-02 role and its permitted gate actions."""

    name: str
    description: str = ""
    permissions: frozenset[str] = frozenset()
    read_only: bool = False

    def may(self, action: str) -> bool:
        return action in self.permissions


@dataclass(frozen=True)
class PermissionCheck:
    """The structured answer roles/check and gate.approve consume."""

    permitted: bool
    reason: str


@dataclass
class RolePack:
    """The parsed role pack. ``errors`` non-empty means fail-closed."""

    version: int
    source: str
    errors: list[str] = field(default_factory=list)
    roles: dict[str, RoleSpec] = field(default_factory=dict)
    default_role: str = "approver"
    n_of_m: dict[str, int] = field(default_factory=dict)
    sod_forbid_self_approval: bool = True
    delegation_max_chain_depth: int = 2
    delegation_max_ttl_days: int = 30
    hygiene_approve_latency_floor_seconds: int = 30
    hygiene_bulk_window_minutes: int = 10
    hygiene_bulk_min_count: int = 3

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    @property
    def policy_version(self) -> str:
        return f"roles/v{self.version}" if self.version >= 1 else "roles/invalid"

    def approving_roles(self) -> set[str]:
        return {name for name, spec in self.roles.items() if spec.may("approve")}


#: The built-in default, used when no roles.yaml exists anywhere. Same
#: shape as policy/roles.yaml — keep the two in sync deliberately.
BUILTIN_DEFAULT_YAML = """
version: 1
defaultRole: approver
roles:
  engineer:
    description: Authors and proposes changes; never approves gates.
    permissions: []
  reviewer:
    description: Reviews agent and external work; may approve merge gates.
    permissions: [approve]
  approver:
    description: Accountable human approver for protected branches.
    permissions: [approve, delegate]
  governor:
    description: Runs governance; the only role that changes policy (FR-M20-07).
    permissions: [approve, halt, policy-change, delegate]
  auditor:
    description: Read-only across the ledger; exports audit bundles (FR-M20-08).
    permissions: [export-audit]
    readOnly: true
approvals:
  nOfM: {}
soD:
  forbidSelfApproval: true
delegation:
  maxChainDepth: 2
  maxTtlDays: 30
hygiene:
  approveLatencyFloorSeconds: 30
  bulkWindowMinutes: 10
  bulkMinCount: 3
"""


def fail_closed_pack(source: str, errors: Sequence[str]) -> RolePack:
    return RolePack(version=0, source=source, errors=list(errors))


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _parse_roles(raw: Any, errors: list[str]) -> dict[str, RoleSpec]:
    if raw is None:
        return {}
    if not _is_mapping(raw):
        errors.append("roles: expected a mapping of role name to spec")
        return {}
    parsed: dict[str, RoleSpec] = {}
    for name, spec in raw.items():
        where = f"roles.{name}"
        if not isinstance(name, str) or not name.strip():
            errors.append("roles: role names must be non-empty strings")
            continue
        if not _is_mapping(spec):
            errors.append(f"{where}: expected a mapping with permissions")
            continue
        unknown = set(spec) - set(_ROLE_KEYS)
        for key in sorted(unknown):
            errors.append(f"{where}: unknown key '{key}'")
        description = spec.get("description", "")
        if not isinstance(description, str):
            errors.append(f"{where}.description: expected a string")
            description = ""
        permissions_raw = spec.get("permissions", [])
        permissions: set[str] = set()
        if not isinstance(permissions_raw, list) or any(
            not isinstance(item, str) for item in permissions_raw
        ):
            errors.append(f"{where}.permissions: expected a list of action names")
        else:
            for action in permissions_raw:
                if action not in ACTIONS:
                    errors.append(
                        f"{where}.permissions: '{action}' is not a gate action "
                        f"({', '.join(ACTIONS)})"
                    )
                else:
                    permissions.add(action)
        read_only = spec.get("readOnly", False)
        if not isinstance(read_only, bool):
            errors.append(f"{where}.readOnly: expected a boolean")
            read_only = False
        if read_only and permissions - {"export-audit"}:
            errors.append(
                f"{where}: a read-only role may only hold export-audit (FR-M20-08)"
            )
        parsed[name.strip()] = RoleSpec(
            name=name.strip(),
            description=description,
            permissions=frozenset(permissions),
            read_only=read_only,
        )
    return parsed


def _positive_int(value: Any, where: str, errors: list[str]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        errors.append(f"{where}: expected an integer >= 1, got {value!r}")
        return None
    return value


def parse_role_pack(text: str, source: str) -> RolePack:
    """Parse and validate a role pack document. Never raises on content:
    every violation lands in ``errors`` and the pack fails closed."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return fail_closed_pack(
            source,
            [f"{source}: roles policy is not valid YAML: {error}", FAIL_CLOSED_REMEDY],
        )
    if raw is None:
        raw = {}
    if not _is_mapping(raw):
        return fail_closed_pack(
            source,
            [f"{source}: roles policy must be a mapping at the top level", FAIL_CLOSED_REMEDY],
        )

    errors: list[str] = []
    version = 0
    raw_version = raw.get("version")
    if isinstance(raw_version, int) and not isinstance(raw_version, bool) and raw_version >= 1:
        version = raw_version
    else:
        errors.append(f"version: expected an integer >= 1, got {raw_version!r}")

    for name in sorted(set(raw) - set(_TOP_LEVEL_KEYS)):
        errors.append(f"{name}: unknown top-level section")

    roles = _parse_roles(raw.get("roles"), errors)

    default_role = raw.get("defaultRole", "approver")
    if not isinstance(default_role, str) or not default_role.strip():
        errors.append("defaultRole: expected a non-empty string")
        default_role = "approver"

    n_of_m: dict[str, int] = {}
    approvals = raw.get("approvals", {})
    if not _is_mapping(approvals):
        errors.append("approvals: expected a mapping")
    else:
        unknown = set(approvals) - {"nOfM"}
        for key in sorted(unknown):
            errors.append(f"approvals.{key}: unknown key")
        raw_n_of_m = approvals.get("nOfM", {})
        if not _is_mapping(raw_n_of_m):
            errors.append("approvals.nOfM: expected a mapping of branch to count")
        else:
            for branch, count in raw_n_of_m.items():
                if not isinstance(branch, str) or not branch.strip():
                    errors.append("approvals.nOfM: branch names must be non-empty strings")
                    continue
                parsed = _positive_int(count, f"approvals.nOfM.{branch}", errors)
                if parsed is not None:
                    n_of_m[branch.strip()] = parsed

    sod_forbid = True
    sod = raw.get("soD", {})
    if not _is_mapping(sod):
        errors.append("soD: expected a mapping")
    else:
        unknown = set(sod) - {"forbidSelfApproval"}
        for key in sorted(unknown):
            errors.append(f"soD.{key}: unknown key")
        raw_flag = sod.get("forbidSelfApproval", True)
        if not isinstance(raw_flag, bool):
            errors.append("soD.forbidSelfApproval: expected a boolean")
        else:
            sod_forbid = raw_flag

    max_chain_depth = 2
    max_ttl_days = 30
    delegation = raw.get("delegation", {})
    if not _is_mapping(delegation):
        errors.append("delegation: expected a mapping")
    else:
        unknown = set(delegation) - {"maxChainDepth", "maxTtlDays"}
        for key in sorted(unknown):
            errors.append(f"delegation.{key}: unknown key")
        depth = _positive_int(delegation.get("maxChainDepth", 2), "delegation.maxChainDepth", errors)
        if depth is not None:
            max_chain_depth = depth
        ttl = _positive_int(delegation.get("maxTtlDays", 30), "delegation.maxTtlDays", errors)
        if ttl is not None:
            max_ttl_days = ttl

    latency_floor = 30
    bulk_window = 10
    bulk_min = 3
    hygiene = raw.get("hygiene", {})
    if not _is_mapping(hygiene):
        errors.append("hygiene: expected a mapping")
    else:
        unknown = set(hygiene) - {
            "approveLatencyFloorSeconds",
            "bulkWindowMinutes",
            "bulkMinCount",
        }
        for key in sorted(unknown):
            errors.append(f"hygiene.{key}: unknown key")
        raw_floor = hygiene.get("approveLatencyFloorSeconds", 30)
        if not isinstance(raw_floor, int) or isinstance(raw_floor, bool) or raw_floor < 0:
            errors.append(
                f"hygiene.approveLatencyFloorSeconds: expected an integer >= 0, got {raw_floor!r}"
            )
        else:
            latency_floor = raw_floor
        parsed_window = _positive_int(
            hygiene.get("bulkWindowMinutes", 10), "hygiene.bulkWindowMinutes", errors
        )
        if parsed_window is not None:
            bulk_window = parsed_window
        parsed_min = _positive_int(
            hygiene.get("bulkMinCount", 3), "hygiene.bulkMinCount", errors
        )
        if parsed_min is not None:
            bulk_min = parsed_min

    if default_role.strip() not in roles:
        errors.append(f"defaultRole: '{default_role}' is not a defined role")

    if errors:
        errors.append(FAIL_CLOSED_REMEDY)
        return fail_closed_pack(source, [f"{source}: {error}" for error in errors])
    return RolePack(
        version=version,
        source=source,
        roles=roles,
        default_role=default_role.strip(),
        n_of_m=n_of_m,
        sod_forbid_self_approval=sod_forbid,
        delegation_max_chain_depth=max_chain_depth,
        delegation_max_ttl_days=max_ttl_days,
        hygiene_approve_latency_floor_seconds=latency_floor,
        hygiene_bulk_window_minutes=bulk_window,
        hygiene_bulk_min_count=bulk_min,
    )


def load_role_pack(paths: Sequence[str | Path]) -> RolePack:
    """The first readable file wins (workspace override, then repository).

    No readable file falls back to the built-in default — a last resort for
    a loader invoked outside a bootstrapped workspace (the D43 bootstrap
    scaffolds the shipped roles.yaml into ``<ws>/.meridian/policy/`` on
    handshake, so a handshaken workspace always has a readable pack). A
    present but malformed file fails closed with the remedy named (see
    parse_role_pack).
    """
    tried: list[str] = []
    for path in paths:
        if path is None:
            continue
        candidate = Path(path)
        tried.append(str(candidate))
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        return parse_role_pack(text, str(candidate))
    pack = parse_role_pack(BUILTIN_DEFAULT_YAML, "builtin-default-roles")
    pack.source = "builtin-default (no roles.yaml found; tried: " + ", ".join(tried) + ")"
    return pack


def check_permission(pack: RolePack, role: str | None, action: str) -> PermissionCheck:
    """FR-M20-02/07/08: may ``role`` perform ``action``? A fail-closed pack
    refuses everything, naming the errors."""
    if pack.fail_closed:
        return PermissionCheck(
            permitted=False,
            reason="roles policy is fail-closed: " + "; ".join(pack.errors),
        )
    if action not in ACTIONS:
        return PermissionCheck(
            permitted=False,
            reason=f"'{action}' is not a gate action ({', '.join(ACTIONS)})",
        )
    if role is None or not str(role).strip():
        return PermissionCheck(permitted=False, reason="no role was given")
    name = str(role).strip()
    spec = pack.roles.get(name)
    if spec is None:
        return PermissionCheck(
            permitted=False,
            reason=f"role '{name}' is not defined in {pack.source}; "
            f"defined roles: {', '.join(sorted(pack.roles))}",
        )
    if spec.may(action):
        return PermissionCheck(permitted=True, reason=f"{name} may {action}")
    permitted = sorted(
        role_name
        for role_name, role_spec in pack.roles.items()
        if role_spec.may(action)
    )
    suffix = " (FR-M20-07: only the Governor role may)" if action == "policy-change" else ""
    return PermissionCheck(
        permitted=False,
        reason=f"role '{name}' may not {action}{suffix}; permitted roles: "
        + (", ".join(permitted) if permitted else "none"),
    )


# -- delegation (FR-M20-05) -------------------------------------------------------


def _read_detail(ledger: Any, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def iter_delegations(ledger: Any) -> list[dict[str, Any]]:
    """Active-shape delegation details, newest first (unfiltered by expiry)."""
    found: list[dict[str, Any]] = []
    for row in reversed(ledger.query(action_type="delegation", limit=1000)):
        detail = _read_detail(ledger, row)
        if detail.get("method") == "roles/delegate":
            detail = dict(detail)
            detail["_seq"] = row["seq"]
            detail["_ts"] = row["ts_utc"]
            found.append(detail)
    return found


def find_active_delegation(
    ledger: Any, principal: str, role: str, now_utc: str
) -> dict[str, Any] | None:
    """The freshest unexpired delegation granting ``role`` to ``principal``.

    Expiry compares ISO-8601 UTC strings — every timestamp in this system
    comes from one clock format, so lexicographic order is chronological.
    """
    principal = principal.strip().lower()
    for detail in iter_delegations(ledger):
        if str(detail.get("to", "")).strip().lower() != principal:
            continue
        if detail.get("role") != role:
            continue
        expires = str(detail.get("expiresAt") or "")
        if expires and expires <= now_utc:
            continue
        return detail
    return None


def delegation_chain_depth(ledger: Any, principal: str, role: str, now_utc: str) -> int:
    """How deep ``principal`` holds ``role`` through delegations (0 = not
    via delegation)."""
    principal = principal.strip().lower()
    depth = 0
    for detail in iter_delegations(ledger):
        if str(detail.get("to", "")).strip().lower() != principal:
            continue
        if detail.get("role") != role:
            continue
        expires = str(detail.get("expiresAt") or "")
        if expires and expires <= now_utc:
            continue
        try:
            depth = max(depth, int(detail.get("depth") or 1))
        except (TypeError, ValueError):
            depth = max(depth, 1)
    return depth


def delegation_reaches(ledger: Any, start: str, target: str, now_utc: str) -> bool:
    """True when ``target`` already holds through an active delegation
    chain starting at ``start`` (cycle detection for a new start->... edge)."""
    start = start.strip().lower()
    target = target.strip().lower()
    edges: list[tuple[str, str]] = []
    for detail in iter_delegations(ledger):
        expires = str(detail.get("expiresAt") or "")
        if expires and expires <= now_utc:
            continue
        edges.append(
            (
                str(detail.get("from", {}).get("email", "")).strip().lower(),
                str(detail.get("to", "")).strip().lower(),
            )
        )
    frontier = [start]
    seen: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(to for frm, to in edges if frm == current and to not in seen)
    return False


# -- approval hygiene (FR-M20-06) ---------------------------------------------------


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def assess_hygiene(ledger: Any, pack: RolePack, *, subject: str) -> list[str]:
    """Rubber-stamping signals measured from ledger history. These warnings
    are advisory (they never block) and are the F2 measurement hook:

    * approve latency under the configured floor — approval faster than a
      human could plausibly have read the change, measured against the
      newest preceding gate-open event (pr_ingest or gate evaluation) for
      the same subject;
    * approver == requester — the approving identity is the one that
      ingested the change (overlaps SoD; here it is surfaced, not refused,
      for changes ingested before SoD applied);
    * back-to-back bulk approvals — one approver recording bulkMinCount or
      more approvals inside any bulkWindowMinutes window, the
      rubber-stamping shape at volume.
    """
    warnings: list[str] = []
    if pack.fail_closed:
        return warnings

    approval_rows = [
        row
        for row in ledger.query(action_type="approval", limit=1000)
        if row.get("decision") == "approved" and str(row.get("human_actor") or "").strip()
    ]

    # Approver == requester + latency for this subject's approvals.
    ingest_rows = [
        (row, _read_detail(ledger, row))
        for row in ledger.query(action_type="pr_ingest", limit=1000)
    ]
    ingester_emails = {
        str(detail.get("ingestedBy", {}).get("email", "")).strip().lower()
        for _, detail in ingest_rows
        if isinstance(detail.get("ingestedBy"), Mapping)
    }
    gate_open_ts: list[str] = []
    for row, detail in ingest_rows:
        if detail.get("subject") == subject:
            gate_open_ts.append(str(row.get("ts_utc") or ""))
    for row in ledger.query(action_type="gate", limit=1000):
        detail = _read_detail(ledger, row)
        if detail.get("subject") == subject:
            gate_open_ts.append(str(row.get("ts_utc") or ""))
    gate_open_ts = sorted(t for t in gate_open_ts if t)

    floor = pack.hygiene_approve_latency_floor_seconds
    for row in approval_rows:
        detail = _read_detail(ledger, row)
        if detail.get("subject") != subject:
            continue
        actor = str(row.get("human_actor") or "")
        email = actor.rpartition("<")[2].rstrip(">").strip().lower()
        if email and email in ingester_emails:
            warnings.append(
                f"FR-M20-06: {actor} approved '{subject}' but also ingested the "
                "change — approver is the requester"
            )
        if floor and gate_open_ts:
            approved_at = _parse_ts(str(row.get("ts_utc") or ""))
            opened_at = _parse_ts(gate_open_ts[-1])
            if approved_at is not None and opened_at is not None:
                latency = (approved_at - opened_at).total_seconds()
                if 0 <= latency < floor:
                    warnings.append(
                        f"FR-M20-06: approval at seq {row['seq']} has approve "
                        f"latency {latency:.1f}s (gate opened to decision) — "
                        f"under the {floor}s rubber-stamp floor"
                    )

    # Back-to-back bulk approvals across everything this ledger recorded.
    window = pack.hygiene_bulk_window_minutes
    minimum = pack.hygiene_bulk_min_count
    by_approver: dict[str, list[datetime]] = {}
    for row in approval_rows:
        at = _parse_ts(str(row.get("ts_utc") or ""))
        if at is None:
            continue
        by_approver.setdefault(str(row.get("human_actor") or ""), []).append(at)
    for actor, stamps in sorted(by_approver.items()):
        stamps.sort()
        for index in range(len(stamps) - minimum + 1):
            span = (stamps[index + minimum - 1] - stamps[index]).total_seconds()
            if span <= window * 60:
                warnings.append(
                    f"FR-M20-06: {actor} recorded {minimum} approvals within "
                    f"{window} minutes (back-to-back bulk approvals)"
                )
                break

    return warnings
