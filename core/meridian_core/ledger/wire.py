"""Mapping between the bus wire shapes (camelCase) and ledger rows.

Single ownership of the field lists: the bus contract is generated from
shared/schema/methods.json, and the ledger columns are normative §7.2 —
this module is where the two meet, and a typo here fails loudly at
import time against both.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .blobs import BlobError

#: ledger.append params (camelCase) -> ledger_entry columns (snake_case).
APPEND_PARAM_TO_COLUMN: dict[str, str] = {
    "storyId": "story_id",
    "phase": "phase",
    "loopId": "loop_id",
    "loopIteration": "loop_iteration",
    "actorId": "actor_id",
    "actorVersion": "actor_version",
    "actorKind": "actor_kind",
    "policyVersion": "policy_version",
    "skillId": "skill_id",
    "skillVersion": "skill_version",
    "modelId": "model_id",
    "modelVersion": "model_version",
    "actionType": "action_type",
    "confidence": "confidence",
    "decision": "decision",
    "humanActor": "human_actor",
    "humanRole": "human_role",
    "reworkReason": "rework_reason",
    "tokensIn": "tokens_in",
    "tokensOut": "tokens_out",
    "costUsd": "cost_usd",
    "latencyMs": "latency_ms",
    "worktreeRef": "worktree_ref",
    "repoId": "repo_id",
    "replayOf": "replay_of",
    "vendor": "vendor",
    "observationConfidence": "observation_confidence",
    "externalSessionId": "external_session_id",
    "runId": "run_id",
    "origin": "origin",
    "simulated": "simulated",
    "timestamp": "ts_utc",
    "rejectedSequence": "rejected_sequence",
    "rejectedCommit": "rejected_commit",
    "rejectingCommit": "rejecting_commit",
}

#: Convenience params handled by Ledger.append, not columns.
APPEND_PAYLOAD_PARAMS = frozenset({"input", "output", "blob_subject"})


def append_params_to_entry(params: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for wire_key, column in APPEND_PARAM_TO_COLUMN.items():
        if wire_key in params:
            entry[column] = params[wire_key]
    for wire_key in ("input", "output", "blobSubject"):
        if wire_key in params:
            entry[{"blobSubject": "blob_subject"}.get(wire_key, wire_key)] = params[
                wire_key
            ]
    if "toolCalls" in params:
        entry["tool_calls"] = json.dumps(params["toolCalls"], ensure_ascii=False)
    return entry


def _hex(value: bytes | None) -> str | None:
    return value.hex() if value is not None else None


def row_to_wire(row: dict[str, Any]) -> dict[str, Any]:
    """A full ledger_entry row -> the FR-M11-02 LedgerEntry wire shape."""
    tool_calls = row.get("tool_calls")
    return {
        "sequence": row["seq"],
        "timestamp": row["ts_utc"],
        "storyId": row["story_id"],
        "phase": row["phase"],
        "loopId": row["loop_id"],
        "loopIteration": row["loop_iteration"],
        "actorId": row["actor_id"],
        "actorVersion": row["actor_version"],
        "actorKind": row["actor_kind"],
        "policyVersion": row["policy_version"],
        "skillId": row.get("skill_id"),
        "skillVersion": row.get("skill_version"),
        "modelId": row.get("model_id"),
        "modelVersion": row.get("model_version"),
        "actionType": row["action_type"],
        "toolCallsSummary": len(json.loads(tool_calls)) if tool_calls else None,
        "confidence": row.get("confidence"),
        "decision": row.get("decision"),
        "humanActor": row.get("human_actor"),
        "humanRole": row.get("human_role"),
        "reworkReason": row.get("rework_reason"),
        "tokensIn": row.get("tokens_in"),
        "tokensOut": row.get("tokens_out"),
        "costUsd": row.get("cost_usd"),
        "latencyMs": row.get("latency_ms"),
        "worktreeRef": row.get("worktree_ref"),
        "repoId": row.get("repo_id"),
        "replayOf": row.get("replay_of"),
        "vendor": row["vendor"],
        "observationConfidence": row["observation_confidence"],
        "externalSessionId": row.get("external_session_id"),
        "runId": row.get("run_id"),
        "origin": row.get("origin"),
        "simulated": bool(row["simulated"]),
        "rejectedSequence": row.get("rejected_sequence"),
        "rejectedCommit": row.get("rejected_commit"),
        "rejectingCommit": row.get("rejecting_commit"),
        "entryHash": _hex(row["entry_hash"]),
        "previousHash": _hex(row["prev_hash"]),
        "hasInputBlob": row.get("input_ref") is not None,
        "hasOutputBlob": row.get("output_ref") is not None,
    }


def row_to_detail(
    row: dict[str, Any], decrypt: Callable[[str, str], bytes]
) -> dict[str, Any]:
    """FR-M11-03 entry detail: the stream shape plus digests, tool calls
    and decrypted payloads. `decrypt(ref, key_id)` raises BlobError when
    the key is shredded — reported as *Available False, never an error."""
    detail = row_to_wire(row)
    tool_calls = row.get("tool_calls")
    detail["toolCalls"] = json.loads(tool_calls) if tool_calls else None
    detail["inputDigest"] = _hex(row.get("input_digest"))
    detail["inputRef"] = row.get("input_ref")
    detail["outputDigest"] = _hex(row.get("output_digest"))
    detail["outputRef"] = row.get("output_ref")
    detail["blobKeyId"] = row.get("blob_key_id")
    for prefix in ("input", "output"):
        ref = row.get(f"{prefix}_ref")
        key_id = row.get("blob_key_id")
        if ref is None or key_id is None:
            detail[prefix] = None
            detail[f"{prefix}Available"] = False
            continue
        try:
            detail[prefix] = decrypt(ref, key_id).decode("utf-8", errors="replace")
            detail[f"{prefix}Available"] = True
        except BlobError:
            detail[prefix] = None
            detail[f"{prefix}Available"] = False
    return detail


def row_to_bundle_entry(row: dict[str, Any]) -> dict[str, Any]:
    """One entry inside an audit bundle (FR-M11-05/FR-M36-04): stream shape
    plus ciphertext refs/digests — a third party checks the chain without
    keys — and ``hashPayload``, the exact JSON-native preimage of
    ``entry_hash`` (canonical.hashable_payload) so the open verifier
    recomputes the hash with no column knowledge."""
    from .canonical import hashable_payload

    bundle = row_to_wire(row)
    bundle["inputDigest"] = _hex(row.get("input_digest"))
    bundle["inputRef"] = row.get("input_ref")
    bundle["outputDigest"] = _hex(row.get("output_digest"))
    bundle["outputRef"] = row.get("output_ref")
    bundle.pop("toolCallsSummary", None)
    bundle["hashPayload"] = hashable_payload(row)
    return bundle


def tree_head_to_wire(head: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": head["seq"],
        "rootHash": head["root_hash"].hex(),
        "signedAt": head["signed_at"],
        "signature": head["signature"].hex(),
        **({"anchorRef": head["anchor_ref"]} if head.get("anchor_ref") else {}),
    }
