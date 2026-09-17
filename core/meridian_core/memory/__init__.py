"""M7 Memory fabric and Instruction Library — FR-M7-01…16. Submodules:
fabric (tiered memory, provenance, gated writeback, retention, layering,
budgeted retrieval, export), instructions (discovery, precedence, trust,
digest recording). Zero model calls."""

from .fabric import (
    DEFAULT_EPISODIC_HORIZON_DAYS,
    TIERS,
    TRUSTED_ORIGINS,
    UNTRUSTED_ORIGINS,
    AssembledContext,
    ContradictionError,
    MemoryEntry,
    MemoryError,
    MemoryFabric,
    Provenance,
    utc_now,
)
from .instructions import (
    DISCOVERY_NAMES,
    TRUST_TIERS,
    InstructionContext,
    InstructionFile,
    InstructionLibrary,
    digest_of,
)

__all__ = [
    "DEFAULT_EPISODIC_HORIZON_DAYS",
    "TIERS",
    "TRUSTED_ORIGINS",
    "UNTRUSTED_ORIGINS",
    "AssembledContext",
    "ContradictionError",
    "MemoryEntry",
    "MemoryError",
    "MemoryFabric",
    "Provenance",
    "utc_now",
    "DISCOVERY_NAMES",
    "TRUST_TIERS",
    "InstructionContext",
    "InstructionFile",
    "InstructionLibrary",
    "digest_of",
]
