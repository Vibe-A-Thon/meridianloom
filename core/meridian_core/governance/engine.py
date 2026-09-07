"""FR-M12-09: the policy engine — DoR/DoD as machine-checkable predicates.

A packet/PR payload (a plain mapping: fields, evidence artifacts, approvals)
is evaluated against a named gate profile from the policy pack. Each
criterion is a deterministic predicate — required fields, test evidence,
security-scan evidence, human approval — producing pass/fail with a reason.
The verdict is the conjunction: every criterion must pass, with human
judgement as the fallback rather than the default.

Zero model calls (FR-M36-07): every predicate reads only the payload and
the policy pack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .policy import CriterionSpec, GateProfile, PolicyPack

#: Evidence artifact kinds that count as test runs / security scans.
_TEST_KINDS = ("test", "test-run", "tests", "test_run")
_SCAN_KINDS = ("security-scan", "security_scan", "scan")
_DEFAULT_PASSING_STATUSES = ("passed", "success")


@dataclass(frozen=True)
class CriterionResult:
    id: str
    kind: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class GateVerdict:
    profile: str
    passed: bool
    criteria: tuple[CriterionResult, ...] = ()
    reasons: tuple[str, ...] = ()
    fail_closed: bool = False
    policy_version: str = "governance/invalid"


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _evidence(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = packet.get("evidence")
    if raw is None:
        raw = packet.get("artifacts")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _artifact_status(item: Mapping[str, Any]) -> str:
    status = item.get("status")
    return status.strip().lower() if isinstance(status, str) else ""


def _check_required_fields(packet: Mapping[str, Any], spec: CriterionSpec) -> CriterionResult:
    missing = [name for name in spec.fields if not _present(packet.get(name))]
    if not missing:
        return CriterionResult(spec.id, spec.kind, True, "all required fields present")
    return CriterionResult(
        spec.id, spec.kind, False, "missing required fields: " + ", ".join(missing)
    )


def _check_test_evidence(packet: Mapping[str, Any], spec: CriterionSpec) -> CriterionResult:
    statuses = spec.statuses or _DEFAULT_PASSING_STATUSES
    for item in _evidence(packet):
        kind = item.get("kind")
        kind = kind.strip().lower() if isinstance(kind, str) else ""
        if kind in _TEST_KINDS and _artifact_status(item) in statuses:
            return CriterionResult(spec.id, spec.kind, True, "passing test evidence present")
    seen = [item.get("kind") for item in _evidence(packet)]
    return CriterionResult(
        spec.id,
        spec.kind,
        False,
        "no passing test-run evidence "
        f"(kinds/statuses seen: {[(item.get('kind'), item.get('status')) for item in _evidence(packet)] or 'none'})",
    )


def _check_security_scan(packet: Mapping[str, Any], spec: CriterionSpec) -> CriterionResult:
    statuses = spec.statuses or _DEFAULT_PASSING_STATUSES
    for item in _evidence(packet):
        kind = item.get("kind")
        kind = kind.strip().lower() if isinstance(kind, str) else ""
        if kind not in _SCAN_KINDS:
            continue
        if _artifact_status(item) not in statuses:
            return CriterionResult(
                spec.id, spec.kind, False, f"security scan status '{item.get('status')}' is not passing"
            )
        findings = item.get("criticalFindings", 0)
        if not isinstance(findings, int) or isinstance(findings, bool):
            return CriterionResult(
                spec.id, spec.kind, False, "security scan criticalFindings is not an integer"
            )
        if findings > spec.max_critical:
            return CriterionResult(
                spec.id,
                spec.kind,
                False,
                f"security scan reports {findings} critical findings "
                f"(allowed: {spec.max_critical})",
            )
        return CriterionResult(
            spec.id, spec.kind, True, f"security scan clean ({findings} critical findings)"
        )
    return CriterionResult(spec.id, spec.kind, False, "no security-scan evidence")


def _check_human_approval(packet: Mapping[str, Any], spec: CriterionSpec) -> CriterionResult:
    raw = packet.get("approvals")
    approvals = [a for a in raw if isinstance(a, Mapping)] if isinstance(raw, list) else []
    seen: list[str] = []
    for approval in approvals:
        approver = approval.get("approver")
        name = email = ""
        if isinstance(approver, Mapping):
            raw_name = approver.get("name")
            raw_email = approver.get("email")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            email = raw_email.strip() if isinstance(raw_email, str) else ""
        if not name and not email:
            seen.append("<anonymous>")
            continue  # FR-M12-07: anonymous approval is not an approval.
        role = approval.get("role")
        role = role.strip() if isinstance(role, str) else ""
        who = name or email
        if spec.roles and role not in spec.roles:
            seen.append(f"{who} (role '{role or 'none'}')")
            continue
        return CriterionResult(
            spec.id, spec.kind, True, f"approved by {who}" + (f" ({role})" if role else "")
        )
    detail = "; ".join(seen) if seen else "no approvals supplied"
    roles = f" (roles: {', '.join(spec.roles)})" if spec.roles else ""
    return CriterionResult(
        spec.id, spec.kind, False, f"no recorded human approval{roles}: {detail}"
    )


_CHECKS = {
    "requiredFields": _check_required_fields,
    "testEvidence": _check_test_evidence,
    "securityScan": _check_security_scan,
    "humanApproval": _check_human_approval,
}


def evaluate(
    packet: Mapping[str, Any], profile: str, pack: PolicyPack
) -> GateVerdict:
    """Evaluate ``packet`` against the named profile of ``pack``.

    A fail-closed pack blocks with its errors as reasons; an unknown profile
    blocks with the known profile list. Otherwise the verdict is the
    conjunction of the profile's criteria.
    """
    if pack.fail_closed:
        return GateVerdict(
            profile=profile,
            passed=False,
            reasons=tuple(pack.errors),
            fail_closed=True,
            policy_version=pack.policy_version,
        )
    gate_profile: GateProfile | None = pack.profiles.get(profile)
    if gate_profile is None:
        known = ", ".join(sorted(pack.profiles)) or "(none)"
        return GateVerdict(
            profile=profile,
            passed=False,
            reasons=(f"unknown gate profile '{profile}' (known: {known})",),
            policy_version=pack.policy_version,
        )
    criteria = tuple(
        _CHECKS[spec.kind](packet, spec) for spec in gate_profile.criteria
    )
    reasons = tuple(c.reason for c in criteria if not c.passed)
    return GateVerdict(
        profile=profile,
        passed=not reasons,
        criteria=criteria,
        reasons=reasons,
        policy_version=pack.policy_version,
    )
