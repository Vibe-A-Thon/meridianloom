"""Governance: policy engine, merge gate, and human identity (FR-M12-*)."""

from .bypass import (
    BypassDetection,
    BypassEvidence,
    bypass_gaps,
    downgraded_surfaces,
    open_detections,
    run_detections,
)
from .engine import CriterionResult, GateVerdict, evaluate
from .identity import (
    GitIdentityProvider,
    HumanIdentity,
    IdentityProvider,
    IdentityUnavailableError,
    StaticIdentityProvider,
)
from .merge_gate import Approval, MergeVerdict, check_merge
from .policy_bundle import (
    BundleEvaluation,
    PolicyBundle,
    PolicyLease,
    evaluate_bundle,
    lease_checkpoint,
    revoke_bundle,
    select_policy,
    sign_bundle,
)
from .policy_simulator import SimulationReport, VerdictDiff, simulate_policy_change
from .policy import (
    CriterionSpec,
    GateProfile,
    PolicyPack,
    fail_closed_pack,
    load_policy_pack,
    parse_policy_pack,
)

__all__ = [
    "Approval",
    "BundleEvaluation",
    "BypassDetection",
    "BypassEvidence",
    "CriterionResult",
    "CriterionSpec",
    "GateProfile",
    "GateVerdict",
    "GitIdentityProvider",
    "HumanIdentity",
    "IdentityProvider",
    "IdentityUnavailableError",
    "MergeVerdict",
    "PolicyBundle",
    "PolicyLease",
    "PolicyPack",
    "SimulationReport",
    "StaticIdentityProvider",
    "VerdictDiff",
    "bypass_gaps",
    "check_merge",
    "downgraded_surfaces",
    "evaluate",
    "evaluate_bundle",
    "fail_closed_pack",
    "lease_checkpoint",
    "load_policy_pack",
    "open_detections",
    "parse_policy_pack",
    "revoke_bundle",
    "run_detections",
    "select_policy",
    "sign_bundle",
    "simulate_policy_change",
]
