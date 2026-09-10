"""FR-M43-01 / SEC-36 / D39: customer-controlled receipt storage for signed
ledger roots.

A *receipt* is a durable, independently verifiable record that a signed
tree head existed at a point in time. Receipts are what make rollback and
wholesale-replacement detection possible later (FR-M43-02, see witness.py):
the verifier compares the tree a bundle presents against the root a
witness countersigned earlier.

Receipt shape (canonical JSON, versioned):

    {
      "formatVersion": 1,
      "kind": "meridian-tree-head-receipt",
      "witness": {"id": str, "publicKey": base64 Ed25519},
      "ledgerPublicKey": base64 Ed25519,     -- the ledger signer, for context
      "treeHead": {"seq", "rootHash", "signedAt", "signature"},
      "receivedAt": iso8601,
      "witnessSignature": hex                -- Ed25519 over the receipt minus
                                              -- this field, by the witness key
    }

SEC-36: verification of a receipt needs only the receipt document and
public keys — nothing from Meridian's servers and nothing from the
witness operator's servers beyond the receipt itself.

D39 (closed): v1 ships a *local file receipt store* as the default and a
*customer-controlled HTTP endpoint* behind configuration, off by default.
When no remote witness is configured, remote witnessing is a no-op and the
limitation is stated honestly (FR-M43-03): without a witness, Meridian
cannot claim to detect wholesale ledger replacement by a machine
administrator — see `unwitnessed_limitation()`.

Signer lifecycle (FR-M43-01): enrolment, rotation and revocation of
ledger signing keys are recorded as ordinary ledger entries
(`record_signer_event`), so the trusted-key history is itself hash-chained
and verifiable rather than living in a side table an administrator could
edit silently.
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.client
import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from . import canonical, keys

RECEIPT_KIND = "meridian-tree-head-receipt"
RECEIPT_FORMAT_VERSION = 1

#: FR-M43-03 / T15: the honest limitation, stated in the interface.
UNWITNESSED_LIMITATION = (
    "No witness receipts are configured. Without a witness, Meridian cannot "
    "claim to detect wholesale ledger replacement or rollback by a machine "
    "administrator: a re-signed fork of the ledger still verifies "
    "cryptographically. Changed-entry and chain-link tampering ARE detected "
    "by signature verification alone."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def unwitnessed_limitation() -> str:
    """FR-M43-03: the stated limitation of unwitnessed ledgers."""
    return UNWITNESSED_LIMITATION


# -- receipts -----------------------------------------------------------------


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _receipt_body(receipt: dict[str, Any]) -> bytes:
    """Canonical bytes the witness signature commits to."""
    body = {k: v for k, v in receipt.items() if k != "witnessSignature"}
    return canonical.canonical_json(body)


def make_receipt(
    tree_head: dict[str, Any],
    ledger_public_key: bytes,
    witness_id: str,
    witness_key: Ed25519PrivateKey | None = None,
) -> dict[str, Any]:
    """Countersign a signed tree head into a receipt.

    `tree_head` is the wire shape from ``Ledger.emit_tree_head_now``. With
    `witness_key` None the receipt records *reception* (the local file
    store's default — the store itself is the witness of record); with a
    key the receipt carries a detachable witness signature verifiable by
    anyone holding the public key (SEC-36).
    """
    receipt: dict[str, Any] = {
        "formatVersion": RECEIPT_FORMAT_VERSION,
        "kind": RECEIPT_KIND,
        "witness": {
            "id": witness_id,
            "publicKey": _b64(
                witness_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            )
            if witness_key is not None
            else None,
        },
        "ledgerPublicKey": _b64(ledger_public_key),
        "treeHead": {
            "seq": tree_head["seq"],
            "rootHash": tree_head["rootHash"],
            "signedAt": tree_head["signedAt"],
            "signature": tree_head["signature"],
        },
        "receivedAt": utc_now(),
    }
    if witness_key is not None:
        receipt["witnessSignature"] = witness_key.sign(_receipt_body(receipt)).hex()
    return receipt


def receipt_id(receipt: dict[str, Any]) -> str:
    """Content address: SHA-256 of the canonical receipt, hex."""
    return hashlib.sha256(_receipt_body(receipt)).hexdigest()


def verify_witness_signature(receipt: dict[str, Any]) -> bool:
    """True when the embedded witness signature verifies with the embedded
    witness public key. Callers wanting witness *trust* must pin the key
    out of band and compare — the embedded key is self-asserted."""
    signature = receipt.get("witnessSignature")
    witness = receipt.get("witness") or {}
    public_key = witness.get("publicKey")
    if not isinstance(signature, str) or not isinstance(public_key, str):
        return False
    try:
        import base64

        key_bytes = base64.b64decode(public_key, validate=True)
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(
            bytes.fromhex(signature), _receipt_body(receipt)
        )
    except Exception:
        return False
    return True


def verify_receipt_tree_head(receipt: dict[str, Any]) -> bool:
    """The receipt's embedded ledger signature must verify against the
    embedded ledger public key — a receipt for a head the ledger signer
    never signed is worthless."""
    try:
        import base64

        head = receipt["treeHead"]
        return keys.verify_tree_head(
            base64.b64decode(receipt["ledgerPublicKey"], validate=True),
            head["seq"],
            bytes.fromhex(head["rootHash"]),
            head["signedAt"],
            bytes.fromhex(head["signature"]),
        )
    except Exception:
        return False


# -- store --------------------------------------------------------------------


class ReceiptStoreError(Exception):
    """Receipt store failure (transport, shape, IO)."""


@runtime_checkable
class ReceiptStore(Protocol):
    """Where receipts for signed roots durably live. Customer-controlled:
    the default is local files; an HTTP endpoint is configured explicitly."""

    def store(self, receipt: dict[str, Any]) -> str:
        """Persist a receipt; return its receipt id."""
        ...

    def list(self) -> list[dict[str, Any]]:
        """All stored receipts, oldest first."""
        ...

    def get(self, receipt_id: str) -> dict[str, Any] | None:
        """One receipt by id, or None."""
        ...


class FileReceiptStore:
    """The v1 default: JSON receipts under a local directory.

    Writes are atomic (tmp file + os.replace) and fsync'd, so a receipt
    acknowledged to the caller survives a hard kill (the same FR-M10-08
    durability standard as ledger appends).
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, rid: str) -> Path:
        # Two-level sharding keeps large receipt sets manageable.
        return self._root / rid[:2] / f"{rid}.json"

    def store(self, receipt: dict[str, Any]) -> str:
        if receipt.get("kind") != RECEIPT_KIND:
            raise ReceiptStoreError(f"not a {RECEIPT_KIND}: {receipt.get('kind')!r}")
        rid = receipt_id(receipt)
        path = self._path_for(rid)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return rid

    def list(self) -> list[dict[str, Any]]:
        receipts: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(self._root.glob("*/*.json")):
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            receipts.append((receipt.get("receivedAt", ""), receipt))
        receipts.sort(key=lambda item: item[0])
        return [receipt for _, receipt in receipts]

    def get(self, receipt_id: str) -> dict[str, Any] | None:
        path = self._path_for(receipt_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class HttpReceiptStore:
    """Customer-controlled remote receipt endpoint (FR-M43-01, D39).

    OFF unless explicitly configured: `ReceiptConfig.remote_url` unset
    means this store is never constructed. POSTs the canonical receipt
    JSON to the endpoint; `list`/`get` follow a tiny REST convention
    (GET endpoint, GET endpoint/<id>). Failures raise
    ReceiptStoreError — receipt transport must never break appends.
    """

    def __init__(
        self, endpoint: str, *, token: str | None = None, timeout: float = 5.0
    ) -> None:
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ReceiptStoreError(
                "receipt endpoint must be https (or localhost for tests): "
                f"{endpoint!r}"
            )
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self, method: str, path: str, body: bytes | None = None
    ) -> tuple[int, bytes]:
        parsed = urllib.parse.urlparse(self._endpoint + path)
        connection = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = connection(parsed.hostname, parsed.port, timeout=self._timeout)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            conn.request(method, target, body=body, headers=self._headers())
            response = conn.getresponse()
            payload = response.read()
            return response.status, payload
        except OSError as error:
            raise ReceiptStoreError(f"receipt endpoint unreachable: {error}") from error
        finally:
            conn.close()

    def store(self, receipt: dict[str, Any]) -> str:
        if receipt.get("kind") != RECEIPT_KIND:
            raise ReceiptStoreError(f"not a {RECEIPT_KIND}: {receipt.get('kind')!r}")
        status, payload = self._request(
            "POST", "/", canonical.canonical_json(receipt)
        )
        if status >= 400:
            raise ReceiptStoreError(f"receipt endpoint returned HTTP {status}")
        return receipt_id(receipt)

    def list(self) -> list[dict[str, Any]]:
        status, payload = self._request("GET", "/")
        if status >= 400:
            raise ReceiptStoreError(f"receipt endpoint returned HTTP {status}")
        try:
            decoded = json.loads(payload)
        except ValueError as error:
            raise ReceiptStoreError("receipt endpoint returned non-JSON") from error
        if not isinstance(decoded, list):
            raise ReceiptStoreError("receipt endpoint list() must return an array")
        return decoded

    def get(self, receipt_id: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
            raise ReceiptStoreError("invalid receipt id")
        status, payload = self._request("GET", f"/{receipt_id}")
        if status == 404:
            return None
        if status >= 400:
            raise ReceiptStoreError(f"receipt endpoint returned HTTP {status}")
        return json.loads(payload)


class NullReceiptStore:
    """The no-op store used when no receipt storage is configured.

    store() returns "" and list() is empty; `limitation` states the
    FR-M43-03 consequence plainly so the interface itself says so.
    """

    limitation = UNWITNESSED_LIMITATION

    def store(self, receipt: dict[str, Any]) -> str:
        return ""

    def list(self) -> list[dict[str, Any]]:
        return []

    def get(self, receipt_id: str) -> dict[str, Any] | None:
        return None


# -- configuration ------------------------------------------------------------


@dataclass(frozen=True)
class ReceiptConfig:
    """Customer-controlled receipt configuration (D39).

    `remote_url` unset (the default) means: no remote witness, local file
    store only, and `remote_witnessing()` is False — remote witnessing is
    a no-op with the limitation stated in `unwitnessed_limitation()`.
    """

    store_dir: Path | None = None
    remote_url: str | None = None
    remote_token: str | None = None
    timeout_s: float = 5.0


def receipt_store_from_config(config: ReceiptConfig) -> ReceiptStore:
    """Resolve the effective store: remote endpoint when configured, else
    the local file store under `store_dir` (a NullReceiptStore when no
    directory is configured either — fully off)."""
    if config.remote_url:
        return HttpReceiptStore(
            config.remote_url,
            token=config.remote_token,
            timeout=config.timeout_s,
        )
    if config.store_dir is not None:
        return FileReceiptStore(config.store_dir)
    return NullReceiptStore()


def remote_witnessing(config: ReceiptConfig) -> bool:
    """Whether a customer-controlled remote witness endpoint is set (D39:
    off by default)."""
    return bool(config.remote_url)


# -- signer lifecycle (FR-M43-01) ---------------------------------------------


SIGNER_EVENTS = ("enrol", "rotate", "revoke")


def record_signer_event(
    ledger: Any,
    event: str,
    *,
    key_id: str,
    public_key: bytes | None = None,
    previous_key_id: str | None = None,
    reason: str | None = None,
    actor: str = "admin",
    at: str | None = None,
) -> Any:
    """Record signer enrolment / rotation / revocation as a ledger entry.

    These entries are ordinary chain links: the trusted-key history
    cannot be edited without breaking the hash chain, and the open
    verifier reproduces it from an exported bundle. `key_id` is the
    stable identifier (e.g. "signer:2026-Q3"); `public_key` is the raw
    Ed25519 public key being enrolled/rotated-to (revocation carries
    None — the key is named, not published).
    """
    if event not in SIGNER_EVENTS:
        raise ValueError(f"event must be one of {SIGNER_EVENTS}")
    payload: dict[str, Any] = {
        "event": f"signer_{event}",
        "keyId": key_id,
        "previousKeyId": previous_key_id,
        "reason": reason,
    }
    if public_key is not None:
        payload["publicKey"] = _b64(public_key)
    entry = {
        "story_id": "meridian-signer-lifecycle",
        "phase": "govern",
        "loop_id": "signer-lifecycle",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "local",
        "actor_kind": "role",
        "policy_version": "signer-lifecycle/v1",
        "action_type": "policy_update",
        "tool_calls": [payload],
        "ts_utc": at,
    }
    return ledger.append(entry)


@dataclass(frozen=True)
class SignerEvent:
    sequence: int
    ts_utc: str
    event: str
    key_id: str
    previous_key_id: str | None
    public_key: bytes | None
    reason: str | None
    actor: str


def signer_history(ledger: Any) -> list[SignerEvent]:
    """The recorded signer lifecycle, oldest first, replayed from ledger
    entries — the trusted-key history as a verifiable chain artifact."""
    import base64

    history: list[SignerEvent] = []
    for row in ledger.query(action_type="policy_update", limit=1000):
        tool_calls = row.get("tool_calls")
        if not tool_calls:
            continue
        try:
            calls = json.loads(tool_calls)
        except (TypeError, ValueError):
            continue
        for call in calls:
            if not isinstance(call, dict) or not str(call.get("event", "")).startswith(
                "signer_"
            ):
                continue
            public_key = call.get("publicKey")
            history.append(
                SignerEvent(
                    sequence=row["seq"],
                    ts_utc=row["ts_utc"],
                    event=call["event"],
                    key_id=call["keyId"],
                    previous_key_id=call.get("previousKeyId"),
                    public_key=(
                        base64.b64decode(public_key, validate=True)
                        if public_key
                        else None
                    ),
                    reason=call.get("reason"),
                    actor=row["actor_id"],
                )
            )
    return history


def trusted_keys_at(history: list[SignerEvent], sequence: int) -> set[str]:
    """Trusted key ids as of `sequence`: enrol/rotate add, revoke removes.

    A verifier uses this to decide `trusted_signer` for historical heads
    instead of trusting today's key set for yesterday's signatures.
    """
    trusted: set[str] = set()
    for event in history:
        if event.sequence > sequence:
            break
        if event.event in ("signer_enrol", "signer_rotate"):
            trusted.add(event.key_id)
        elif event.event == "signer_revoke":
            trusted.discard(event.key_id)
    return trusted
