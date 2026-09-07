"""Governance: policy engine, merge gate, and human identity (FR-M12-*)."""

from .engine import CriterionResult, GateVerdict, evaluate
from .policy import (
    CriterionSpec,
    GateProfile,
    PolicyPack,
    fail_closed_pack,
    load_policy_pack,
    parse_policy_pack,
)

__all__ = [
    "CriterionResult",
    "CriterionSpec",
    "GateProfile",
    "GateVerdict",
    "PolicyPack",
    "evaluate",
    "fail_closed_pack",
    "load_policy_pack",
    "parse_policy_pack",
]
