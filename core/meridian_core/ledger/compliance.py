"""The audit bundle's compliance section (FR-M36-04, FR-M12-11; F0-E task 25).

FR-M12-11 (Requirements_Final.md) is the source of truth for what the
mapping covers: ISO/IEC 42001 clauses and EU AI Act Article 12
record-keeping; the gaps-requirements M12 amendment adds NIST SSDF's AI
provenance recommendations because enterprise procurement grounds audit
requirements in SSDF first. The mappings are data, not legal advice: each
one names the standard, the clause/practice, the requirement in plain
language, and the bundle fields that satisfy it, so an auditor can check
the claim against the bundle in hand.
"""

from __future__ import annotations

from typing import Any

STANDARDS = [
    "NIST SSDF (SP 800-218 v1.1)",
    "ISO/IEC 42001:2023",
    "EU AI Act (Regulation (EU) 2024/1689), Article 12",
]

MAPPINGS: list[dict[str, Any]] = [
    {
        "framework": "NIST SSDF",
        "reference": "SP 800-218 v1.1, Practice PS.3 (Archive and Protect Software)",
        "requirement": (
            "Maintain provenance records for what the software pipeline "
            "produced and who produced it; per the gaps-requirements M12 "
            "amendment, AI provenance grounds in SSDF first: every agent "
            "action is an archived, integrity-protected artifact."
        ),
        "bundleFields": ["entries", "treeHead", "proofs", "signature"],
    },
    {
        "framework": "NIST SSDF",
        "reference": "SP 800-218 v1.1, Practice PW.1 (Design Software to Meet Security Requirements)",
        "requirement": (
            "Design decisions and their rationale are recorded and "
            "reviewable; the ledger's decision and humanActor fields carry "
            "the governance decision per action."
        ),
        "bundleFields": ["entries[].decision", "entries[].humanActor", "entries[].humanRole"],
    },
    {
        "framework": "ISO/IEC 42001:2023",
        "reference": "Clause 7.5 (Documented information)",
        "requirement": (
            "Documented information required by the AI management system is "
            "controlled and retained as evidence: the bundle is a "
            "self-contained, integrity-protected export of the provenance "
            "record."
        ),
        "bundleFields": ["entries", "generatedAt", "range", "filter"],
    },
    {
        "framework": "ISO/IEC 42001:2023",
        "reference": "Clause 9.1 (Monitoring, measurement, analysis and evaluation)",
        "requirement": (
            "The organisation retains appropriate evidence of AI system "
            "operation for evaluation: per-entry telemetry (timestamps, "
            "cost, latency, tokens, vendor, observation confidence) with "
            "tamper-evident integrity."
        ),
        "bundleFields": [
            "entries[].timestamp",
            "entries[].vendor",
            "entries[].observationConfidence",
            "entries[].costUsd",
            "entries[].latencyMs",
            "entries[].tokensIn",
            "entries[].tokensOut",
        ],
        "note": "Integrity is cryptographic, not procedural: entry hashes, Merkle proofs and the bundle signature (SEC-29).",
    },
    {
        "framework": "EU AI Act",
        "reference": "Article 12(1) (Record keeping — automatic recording of events)",
        "requirement": (
            "High-risk AI systems shall technically allow for the automatic "
            "recording of events (logs) over the lifetime of the system: "
            "the ledger appends every agent action as a hash-chained entry "
            "with a UTC timestamp."
        ),
        "bundleFields": ["entries[].sequence", "entries[].timestamp", "entries[].actionType"],
    },
    {
        "framework": "EU AI Act",
        "reference": "Article 12(3) (Record keeping — traceability of functioning)",
        "requirement": (
            "Logs enable the traceability of the AI system's functioning "
            "across its lifecycle: story, phase, actor, run and external "
            "session identifiers link each event to the work it belongs to, "
            "and the signed tree head anchors the log's order and "
            "completeness."
        ),
        "bundleFields": [
            "entries[].storyId",
            "entries[].phase",
            "entries[].actorId",
            "entries[].runId",
            "entries[].externalSessionId",
            "treeHead",
            "proofs",
        ],
    },
]


def compliance_section() -> dict[str, Any]:
    """The wire shape of the bundle's compliance section."""
    return {"standards": list(STANDARDS), "mappings": [dict(m) for m in MAPPINGS]}
