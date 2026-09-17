"""FR-M43-11 / NFR-39 (N2 Workstream D task 18): the ``Meridian-Ledger:``
git-trailer specification and its reference parser.

A governed change may carry a ``Meridian-Ledger`` trailer binding its merge
commit to a signed ledger tree head (FR-M10-04), so a third party holding
only ``git log`` output can parse the trailer and independently verify the
signature against the embedded public key (AC-49). The full published
specification is ``docs/meridian-ledger-trailer.md``; this module is the
normative reference implementation of its parsing and verification rules.

Trailer value grammar (one line, single-space separated tokens)::

    Meridian-Ledger: v1 seq=<uint> root=<hex64> sig=<hex128> key=<base64> at=<rfc3339-utc>

- ``v1`` — schema version token; parsers must reject values they do not
  understand instead of mis-parsing (NFR-39).
- ``seq`` — ledger sequence number the tree head covers.
- ``root`` — the Merkle tree head root, 32 bytes as 64 lowercase hex chars
  (``ledger.merkle.frontier`` / ``Ledger.root_hash``).
- ``sig`` — Ed25519 signature, 64 bytes as 128 lowercase hex chars, over
  ``ledger.keys.tree_head_message(seq, root, at)``.
- ``key`` — the raw 32-byte Ed25519 public key, standard base64 (as used in
  exported bundles).
- ``at`` — the ``signed_at`` RFC 3339 UTC timestamp the signature commits to.

Multiple ``Meridian-Ledger`` trailers may appear (one per tree-head epoch);
all parse, in order. A malformed trailer never verifies and never raises —
it is reported as a warning, so a corrupt line can never crash a third
party's audit tooling.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from meridian_core.ledger import keys
from meridian_core.trailers import parse_trailers

TRAILER_KEY = "Meridian-Ledger"
SUPPORTED_VERSION = "v1"

_SEQ_RE = re.compile(r"^seq=(\d+)$")
_ROOT_RE = re.compile(r"^root=([0-9a-f]{64})$")
_SIG_RE = re.compile(r"^sig=([0-9a-f]{128})$")
_KEY_RE = re.compile(r"^key=([A-Za-z0-9+/]+={0,2})$")
_AT_RE = re.compile(r"^at=(\S+)$")


class TrailerSpecError(ValueError):
    """A trailer value is malformed. Carries the requirement ID (NFR-39)."""


@dataclass(frozen=True)
class TrailerRef:
    """One parsed ``Meridian-Ledger`` trailer."""

    version: str
    seq: int
    root: bytes
    signature: bytes
    public_key: bytes
    signed_at: str
    raw: str


@dataclass
class TrailerParseResult:
    """Outcome of parsing a commit message (or any ``git log`` body)."""

    refs: list[TrailerRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def latest(self) -> TrailerRef | None:
        """The most recent trailer, or None. ``None`` means *no trailer* —
        it must never be read as "verified" (AC-49)."""
        return self.refs[-1] if self.refs else None


def _parse_value(value: str) -> TrailerRef:
    tokens = value.split(" ")
    if not tokens or not tokens[0].startswith("v"):
        raise TrailerSpecError(
            f"FR-M43-11: missing schema version token in {value!r}"
        )
    version = tokens[0]
    if version != SUPPORTED_VERSION:
        raise TrailerSpecError(
            f"NFR-39: unsupported Meridian-Ledger schema version {version!r}"
        )
    attrs: dict[str, str] = {}
    for token in tokens[1:]:
        for name, pattern in (
            ("seq", _SEQ_RE),
            ("root", _ROOT_RE),
            ("sig", _SIG_RE),
            ("key", _KEY_RE),
            ("at", _AT_RE),
        ):
            match = pattern.match(token)
            if match is not None:
                if name in attrs:
                    raise TrailerSpecError(
                        f"FR-M43-11: duplicate {name}= token in {value!r}"
                    )
                attrs[name] = match.group(1)
                break
        else:
            raise TrailerSpecError(
                f"FR-M43-11: unrecognised token {token!r} in {value!r}"
            )
    missing = {"seq", "root", "sig", "key", "at"} - set(attrs)
    if missing:
        raise TrailerSpecError(
            f"FR-M43-11: trailer missing attributes {sorted(missing)}"
        )
    try:
        public_key = base64.b64decode(attrs["key"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrailerSpecError(f"FR-M43-11: key= is not valid base64: {exc}")
    if len(public_key) != 32:
        raise TrailerSpecError(
            f"FR-M43-11: key= must decode to 32 bytes, got {len(public_key)}"
        )
    return TrailerRef(
        version=version,
        seq=int(attrs["seq"]),
        root=bytes.fromhex(attrs["root"]),
        signature=bytes.fromhex(attrs["sig"]),
        public_key=public_key,
        signed_at=attrs["at"],
        raw=value,
    )


def parse_meridian_ledger_trailers(message: str) -> TrailerParseResult:
    """Every ``Meridian-Ledger`` trailer in ``message``, in order.

    Uses the shared trailer-block semantics (``meridian_core.trailers``):
    any trailer line counts, comment lines are skipped, malformed
    ``Meridian-Ledger`` values become warnings — never exceptions (AC-49).
    """
    result = TrailerParseResult()
    for key, value in parse_trailers(message):
        if key != TRAILER_KEY:
            continue
        try:
            result.refs.append(_parse_value(value))
        except TrailerSpecError as exc:
            result.warnings.append(str(exc))
    return result


def verify_trailer(ref: TrailerRef) -> bool:
    """True iff ``ref``'s signature is valid for its embedded public key.

    Signature validity only — signer *trust* is a separate verdict made by
    the independent verifier (``verifier/``) against the customer's
    enrolled-key history (FR-M43-02, SEC-36). This function deliberately
    makes no trust claim.
    """
    public_key = Ed25519PublicKey.from_public_bytes(ref.public_key)
    message = keys.tree_head_message(ref.seq, ref.root, ref.signed_at)
    try:
        public_key.verify(ref.signature, message)
    except InvalidSignature:
        return False
    return True


def format_trailer(
    seq: int,
    root_hash: bytes,
    signed_at: str,
    signature: bytes,
    public_key: bytes,
) -> str:
    """The exact trailer value for a signed tree head (FR-M10-04).

    Round-trips through :func:`parse_meridian_ledger_trailers` and
    :func:`verify_trailer`.
    """
    if len(root_hash) != 32 or len(signature) != 64 or len(public_key) != 32:
        raise TrailerSpecError(
            "FR-M43-11: root_hash/signature/public_key have fixed lengths"
            " (32/64/32 bytes)"
        )
    key_b64 = base64.b64encode(public_key).decode("ascii")
    return (
        f"{SUPPORTED_VERSION} seq={seq} root={root_hash.hex()}"
        f" sig={signature.hex()} key={key_b64} at={signed_at}"
    )


def trailer_from_tree_head(
    head: dict[str, Any], public_key: bytes
) -> str:
    """Format the trailer value for a signed tree head.

    Accepts both the camelCase dict from ``Ledger.emit_tree_head_now()``
    and the snake_case column dict from ``Ledger.latest_tree_head()``.
    """
    def _bytes32(value: Any) -> bytes:
        if isinstance(value, bytes):
            if len(value) != 32:
                raise TrailerSpecError("FR-M43-11: root_hash must be 32 bytes")
            return value
        return bytes.fromhex(str(value))

    def _bytes64(value: Any) -> bytes:
        if isinstance(value, bytes):
            if len(value) != 64:
                raise TrailerSpecError("FR-M43-11: signature must be 64 bytes")
            return value
        return bytes.fromhex(str(value))

    return format_trailer(
        seq=int(head.get("seq")),
        root_hash=_bytes32(head.get("rootHash") or head.get("root_hash")),
        signed_at=str(head.get("signedAt") or head.get("signed_at")),
        signature=_bytes64(head.get("signature")),
        public_key=public_key,
    )
