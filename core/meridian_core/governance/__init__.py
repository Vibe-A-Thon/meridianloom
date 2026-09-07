"""Governance: policy engine, merge gate, and human identity (FR-M12-*)."""

from .engine import CriterionResult, GateVerdict, evaluate
from .identity import (
    GitIdentityProvider,
    HumanIdentity,
    IdentityProvider,
    IdentityUnavailableError,
    StaticIdentityProvider,
)
from .merge_gate import Approval, MergeVerdict, check_merge
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
    "CriterionResult",
    "CriterionSpec",
    "GateProfile",
    "GateVerdict",
    "GitIdentityProvider",
    "HumanIdentity",
    "IdentityProvider",
    "IdentityUnavailableError",
    "MergeVerdict",
    "PolicyPack",
    "StaticIdentityProvider",
    "check_merge",
    "evaluate",
    "fail_closed_pack",
    "load_policy_pack",
    "parse_policy_pack",
]
