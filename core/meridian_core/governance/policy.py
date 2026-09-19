"""FR-M12-01/FR-M12-08: governance policy packs — declarative, versioned YAML.

The general pack lives at ``policy/governance.yaml`` in the repository; a
workspace overrides it at ``.meridian/policy/governance.yaml`` (first
readable file wins — the same convention as the FR-M34-04 allow-list). The
pack carries every FR-M12-08 section: coding standards references, gate
criteria (as named profiles of machine-checkable predicates, FR-M12-09),
budget ceilings, egress allow-lists, permitted tools, tier thresholds, the
protected-branch list, and the F1-A4 ACP permission allow-list as one
section (``acpPermissions``) — the extension host keeps consuming the
dedicated ``policy/acp-permissions.yaml`` unchanged while the engine treats
that same allow-list as part of the general pack.

Parsing is fail-closed exactly like the FR-M34-4 allow-list parser: YAML
syntax errors and schema violations come back as ``errors`` and a pack with
any error blocks every gate evaluation — a malformed policy NEVER opens a
gate. This module never raises on policy content.

Absent-file behaviour (D43 uniformity rule, stated once in
``governance/bootstrap.py``): the sidecar bootstrap scaffolds the shipped
default into ``<ws>/.meridian/policy/`` before this loader runs, so a
workspace handshake always leaves a readable pack; absent everywhere, the
pack fails closed with the remedy named (fix the file, or delete it and
restart to re-scaffold the shipped default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .bootstrap import FAIL_CLOSED_REMEDY

#: Criterion kinds the engine implements (FR-M12-09 machine-checkable
#: predicates over a packet/PR payload).
CRITERION_KINDS = ("requiredFields", "testEvidence", "securityScan", "humanApproval")

#: FR-M12-08 section names the general pack understands. Unknown top-level
#: keys are rejected — a typo'd section must not silently not apply.
_TOP_LEVEL_KEYS = (
    "version",
    "profiles",
    "protectedBranches",
    "acpPermissions",
    "codingStandards",
    "egressAllowlist",
    "permittedTools",
    "budgetCeilings",
    "tierThresholds",
    "attributionCoverageFloor",
    "requiresVerifiedIdentity",
)

_CRITERION_KEYS = (
    "id",
    "kind",
    "fields",
    "roles",
    "statuses",
    "maxCriticalFindings",
)


@dataclass(frozen=True)
class CriterionSpec:
    """One machine-checkable DoR/DoD criterion (FR-M12-09)."""

    id: str
    kind: str
    #: requiredFields: the packet fields that must be present and non-blank.
    fields: tuple[str, ...] = ()
    #: humanApproval: the approver roles that satisfy the criterion
    #: (empty = any named human approver).
    roles: tuple[str, ...] = ()
    #: testEvidence/securityScan: artifact statuses that count as passing.
    statuses: tuple[str, ...] = ()
    #: securityScan: highest acceptable critical-finding count.
    max_critical: int = 0


@dataclass(frozen=True)
class GateProfile:
    """A named gate profile: an ordered set of criteria (a DoR or DoD)."""

    name: str
    description: str
    criteria: tuple[CriterionSpec, ...]


@dataclass
class PolicyPack:
    """The parsed general pack. ``errors`` non-empty means fail-closed:
    every evaluation blocks with the errors as its reasons."""

    version: int
    source: str
    errors: list[str] = field(default_factory=list)
    profiles: dict[str, GateProfile] = field(default_factory=dict)
    protected_branches: list[str] = field(default_factory=list)
    acp_permissions: dict[str, Any] = field(default_factory=dict)
    coding_standards: list[str] = field(default_factory=list)
    egress_allowlist: list[str] = field(default_factory=list)
    permitted_tools: list[str] = field(default_factory=list)
    budget_ceilings: dict[str, Any] = field(default_factory=dict)
    tier_thresholds: dict[str, Any] = field(default_factory=dict)
    #: FR-M41-06: the attribution-coverage floor (0..1) under which a trust
    #: metric reads insufficient_coverage and shows no value; None when the
    #: pack does not configure one (unconfigured — no suppression).
    attribution_coverage_floor: float | None = None
    #: FR-M42-05 (N2-T07): when True, a merge subject's recorded approvals
    #: must come from ``verified``-assurance identities — an ``asserted``
    #: (git) identity never satisfies the requirement and is refused with
    #: the level named. Default for subjects without a per-branch entry.
    requires_verified_default: bool = False
    #: FR-M42-05 per-branch overrides: branch name -> requirement.
    requires_verified_branches: dict[str, bool] = field(default_factory=dict)

    def requires_verified_identity(self, subject: "str | None" = None) -> bool:
        """FR-M42-05: does this subject's gate require a verified identity?
        A per-branch entry wins over the global default; unset anywhere
        means ``asserted`` is accepted (and recorded as ``asserted`` —
        never silently upgraded to ``verified``)."""
        if subject:
            key = subject.strip()
            if key in self.requires_verified_branches:
                return self.requires_verified_branches[key]
        return self.requires_verified_default

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    @property
    def policy_version(self) -> str:
        return f"governance/v{self.version}" if self.version >= 1 else "governance/invalid"


def fail_closed_pack(source: str, errors: Sequence[str]) -> PolicyPack:
    """The pack that denies everything, with the reasons it does."""
    return PolicyPack(version=0, source=source, errors=list(errors))


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _string_list(value: Any, where: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{where}: expected a list of non-empty strings")
        return []
    return list(value)


def _parse_criterion(raw: Any, where: str, errors: list[str]) -> CriterionSpec | None:
    if not _is_mapping(raw):
        errors.append(f"{where}: expected a mapping with id/kind")
        return None
    unknown = set(raw) - set(_CRITERION_KEYS)
    if unknown:
        errors.append(
            f"{where}: unknown keys {sorted(unknown)} (expected {_CRITERION_KEYS})"
        )
    criterion_id = raw.get("id")
    if not isinstance(criterion_id, str) or not criterion_id.strip():
        errors.append(f"{where}.id: expected a non-empty string")
        return None
    kind = raw.get("kind")
    if kind not in CRITERION_KINDS:
        errors.append(
            f"{where}.kind: '{kind}' is not a criterion kind "
            f"({', '.join(CRITERION_KINDS)})"
        )
        return None
    fields = _string_list(raw.get("fields"), f"{where}.fields", errors)
    if kind == "requiredFields" and not fields:
        errors.append(f"{where}.fields: requiredFields needs a non-empty field list")
    roles = _string_list(raw.get("roles"), f"{where}.roles", errors)
    statuses = _string_list(raw.get("statuses"), f"{where}.statuses", errors)
    max_critical = 0
    if raw.get("maxCriticalFindings") is not None:
        value = raw.get("maxCriticalFindings")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(
                f"{where}.maxCriticalFindings: expected an integer >= 0, got {value!r}"
            )
        else:
            max_critical = value
    return CriterionSpec(
        id=criterion_id.strip(),
        kind=kind,
        fields=tuple(fields),
        roles=tuple(roles),
        statuses=tuple(statuses),
        max_critical=max_critical,
    )


def parse_policy_pack(text: str, source: str) -> PolicyPack:
    """Parse and validate a policy pack document. Never raises on content:
    every violation lands in ``errors`` and the pack fails closed."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return fail_closed_pack(
            source,
            [f"{source}: policy is not valid YAML: {error}", FAIL_CLOSED_REMEDY],
        )
    if raw is None:
        raw = {}
    if not _is_mapping(raw):
        return fail_closed_pack(
            source,
            [f"{source}: policy must be a mapping at the top level", FAIL_CLOSED_REMEDY],
        )

    errors: list[str] = []
    version = 0
    raw_version = raw.get("version")
    if isinstance(raw_version, int) and not isinstance(raw_version, bool) and raw_version >= 1:
        version = raw_version
    else:
        errors.append(f"version: expected an integer >= 1, got {raw_version!r}")

    unknown_sections = set(raw) - set(_TOP_LEVEL_KEYS)
    for name in sorted(unknown_sections):
        errors.append(f"{name}: unknown top-level section")

    profiles: dict[str, GateProfile] = {}
    raw_profiles = raw.get("profiles", {})
    if not _is_mapping(raw_profiles):
        errors.append("profiles: expected a mapping of profile name to criteria")
    else:
        for name, spec in raw_profiles.items():
            where = f"profiles.{name}"
            if not isinstance(name, str) or not name.strip():
                errors.append(f"profiles: profile names must be non-empty strings")
                continue
            if not _is_mapping(spec):
                errors.append(f"{where}: expected a mapping with description/criteria")
                continue
            description = spec.get("description", "")
            if not isinstance(description, str):
                errors.append(f"{where}.description: expected a string")
                description = ""
            raw_criteria = spec.get("criteria", [])
            if not isinstance(raw_criteria, list):
                errors.append(f"{where}.criteria: expected a list of criteria")
                continue
            criteria: list[CriterionSpec] = []
            seen_ids: set[str] = set()
            for index, raw_criterion in enumerate(raw_criteria):
                criterion = _parse_criterion(raw_criterion, f"{where}.criteria[{index}]", errors)
                if criterion is None:
                    continue
                if criterion.id in seen_ids:
                    errors.append(f"{where}.criteria[{index}]: duplicate id '{criterion.id}'")
                    continue
                seen_ids.add(criterion.id)
                criteria.append(criterion)
            profiles[name.strip()] = GateProfile(
                name=name.strip(), description=description, criteria=tuple(criteria)
            )

    protected_branches = _string_list(
        raw.get("protectedBranches"), "protectedBranches", errors
    )
    coding_standards = _string_list(raw.get("codingStandards"), "codingStandards", errors)
    egress_allowlist = _string_list(raw.get("egressAllowlist"), "egressAllowlist", errors)
    permitted_tools = _string_list(raw.get("permittedTools"), "permittedTools", errors)

    budget_ceilings = raw.get("budgetCeilings", {})
    if not _is_mapping(budget_ceilings):
        errors.append("budgetCeilings: expected a mapping")
        budget_ceilings = {}
    tier_thresholds = raw.get("tierThresholds", {})
    if not _is_mapping(tier_thresholds):
        errors.append("tierThresholds: expected a mapping")
        tier_thresholds = {}

    acp_permissions = raw.get("acpPermissions", {})
    if not _is_mapping(acp_permissions):
        errors.append("acpPermissions: expected a mapping (the FR-M34-04 allow-list shape)")
        acp_permissions = {}
    else:
        adapters = acp_permissions.get("adapters", {})
        if not _is_mapping(adapters):
            errors.append("acpPermissions.adapters: expected a mapping of adapter id to rules")
        else:
            for adapter_id, rules in adapters.items():
                if not _is_mapping(rules):
                    errors.append(f"acpPermissions.adapters.{adapter_id}: expected a mapping")

    attribution_floor = raw.get("attributionCoverageFloor")
    attribution_coverage_floor: float | None = None
    if attribution_floor is not None:
        if (
            isinstance(attribution_floor, (int, float))
            and not isinstance(attribution_floor, bool)
            and 0.0 <= float(attribution_floor) <= 1.0
        ):
            attribution_coverage_floor = float(attribution_floor)
        else:
            errors.append(
                "attributionCoverageFloor: expected a number between 0 and 1, "
                f"got {attribution_floor!r}"
            )

    requires_verified_default = False
    requires_verified_branches: dict[str, bool] = {}
    raw_verified = raw.get("requiresVerifiedIdentity")
    if raw_verified is not None:
        if isinstance(raw_verified, bool):
            requires_verified_default = raw_verified
        elif _is_mapping(raw_verified):
            unknown = set(raw_verified) - {"default", "branches"}
            for key in sorted(unknown):
                errors.append(f"requiresVerifiedIdentity.{key}: unknown key")
            default_flag = raw_verified.get("default", False)
            if not isinstance(default_flag, bool):
                errors.append(
                    "requiresVerifiedIdentity.default: expected a boolean, "
                    f"got {default_flag!r}"
                )
            else:
                requires_verified_default = default_flag
            raw_branches = raw_verified.get("branches", {})
            if not _is_mapping(raw_branches):
                errors.append(
                    "requiresVerifiedIdentity.branches: expected a mapping "
                    "of branch name to boolean"
                )
            else:
                for branch, flag in raw_branches.items():
                    where = f"requiresVerifiedIdentity.branches.{branch}"
                    if not isinstance(branch, str) or not branch.strip():
                        errors.append(f"{where}: branch names must be non-empty strings")
                        continue
                    if not isinstance(flag, bool):
                        errors.append(f"{where}: expected a boolean, got {flag!r}")
                        continue
                    requires_verified_branches[branch.strip()] = flag
        else:
            errors.append(
                "requiresVerifiedIdentity: expected a boolean or a mapping "
                f"with default/branches, got {raw_verified!r}"
            )

    if errors:
        errors.append(FAIL_CLOSED_REMEDY)
        return fail_closed_pack(
            source, [f"{source}: {error}" for error in errors]
        )
    return PolicyPack(
        version=version,
        source=source,
        profiles=profiles,
        protected_branches=protected_branches,
        acp_permissions=dict(acp_permissions),
        coding_standards=coding_standards,
        egress_allowlist=egress_allowlist,
        permitted_tools=permitted_tools,
        budget_ceilings=dict(budget_ceilings),
        tier_thresholds=dict(tier_thresholds),
        attribution_coverage_floor=attribution_coverage_floor,
        requires_verified_default=requires_verified_default,
        requires_verified_branches=requires_verified_branches,
    )


def load_policy_pack(paths: Sequence[str | Path]) -> PolicyPack:
    """The first readable file wins (workspace override, then repository
    default). No readable file is a fail-closed pack, never an exception."""
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
        return parse_policy_pack(text, str(candidate))
    return fail_closed_pack(
        "governance-pack",
        [
            "no policy file found (tried: " + ", ".join(tried) + ")",
            FAIL_CLOSED_REMEDY,
        ],
    )
