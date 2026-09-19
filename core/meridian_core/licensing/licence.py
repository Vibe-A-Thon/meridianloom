"""The Meridian Loom licence file: format, signature check and evaluation.

A licence is a small JSON document signed with Ed25519::

    {
      "format": "meridian-loom-licence/1",
      "payload": { ...the terms, see below... },
      "signature": {"alg": "Ed25519", "keyId": "ml-2026-1", "value": "<base64>"}
    }

The signature covers the *canonical* JSON of ``payload`` (sorted keys, no
insignificant whitespace, ASCII only), so it does not depend on how the file
happens to be formatted. Verification needs only the vendor's public key,
which ships inside the product — **nothing is sent anywhere, ever**: the
product makes no network call to check a licence, in keeping with its
no-telemetry position (see ``docs/SECURITY-AND-DATA.md``).

Payload fields::

    licenceId   "ML-20260919-3F9A1C2B"           unique id, for support
    product     "meridian-loom"
    edition     "premium"
    licensee    {"name": "...", "contact": "..."}
    kind        "developer" | "machine"           what the licence is bound to
    bindings    {"developers": [emails]}          kind == developer
                {"machines":   [fingerprints]}    kind == machine
    seats       integer >= 1                      how many were purchased
    features    ["*"] or a subset of governor / orchestra / analytics
    issuedAt    ISO-8601 UTC, e.g. "2026-09-19T00:00:00Z"
    notBefore   optional, same format
    expiresAt   ISO-8601 UTC, or null for a perpetual licence
    trial       optional boolean, display only

What this can and cannot do — said plainly, because a licence check that
pretends to be tamper-proof teaches people to distrust the rest of the
product. It is an **honest-user control**: it makes the licensed and
unlicensed cases unambiguous and keeps the paid features from unlocking by
accident. The source is readable, so it cannot stop someone determined to
patch it out; the licence agreement (``LICENSE``) is what prohibits that.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

FORMAT = "meridian-loom-licence/1"
PRODUCT = "meridian-loom"
EDITION_PREMIUM = "premium"
EDITION_COMMUNITY = "community"

#: The separately licensable premium feature groups. ``"*"`` in a licence
#: grants all of them.
FEATURES: tuple[str, ...] = ("governor", "orchestra", "analytics")

KIND_DEVELOPER = "developer"
KIND_MACHINE = "machine"
KINDS = (KIND_DEVELOPER, KIND_MACHINE)

#: After ``expiresAt`` the premium features keep working for this long while
#: the product says so out loud — an expiring licence should never surprise a
#: team in the middle of a release. Stated in LICENSE §4.6; change both.
GRACE_DAYS = 14

#: Licence states. Only VALID and GRACE unlock premium features.
STATE_NONE = "none"
STATE_VALID = "valid"
STATE_GRACE = "grace"
STATE_EXPIRED = "expired"
STATE_NOT_YET_VALID = "not-yet-valid"
STATE_INVALID = "invalid"
STATE_UNTRUSTED = "untrusted-key"
STATE_WRONG_MACHINE = "wrong-machine"
STATE_WRONG_DEVELOPER = "wrong-developer"

ACTIVE_STATES = frozenset({STATE_VALID, STATE_GRACE})

_FINGERPRINT = re.compile(r"^MLM1(-[0-9A-F]{5}){5}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_LICENCE_BYTES = 64 * 1024


class LicenceError(ValueError):
    """A licence that cannot be trusted. ``state`` says why, in a form the UI
    can act on; ``str(error)`` says it in words."""

    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes that are signed."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def parse_time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise LicenceError(STATE_INVALID, f"{field_name} must be an ISO-8601 UTC string")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise LicenceError(STATE_INVALID, f"{field_name} is not a valid date: {value!r}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_time(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class TrustedKey:
    """A public key the product will accept a licence signature from."""

    key_id: str
    public_key: bytes
    #: A development key can also mint the ``"*"`` machine binding used by the
    #: test suite. It is only ever trusted from a source checkout (see keys.py).
    development: bool = False


@dataclass(frozen=True)
class Licence:
    licence_id: str
    licensee_name: str
    licensee_contact: str
    kind: str
    developers: tuple[str, ...]
    machines: tuple[str, ...]
    seats: int
    features: tuple[str, ...]
    issued_at: datetime
    not_before: datetime | None
    expires_at: datetime | None
    trial: bool
    key_id: str
    development_key: bool = False

    def grants(self, feature: str) -> bool:
        return "*" in self.features or feature in self.features

    def summary(self) -> dict[str, Any]:
        """What the UI may show. Never the signature, never other seats'
        machine fingerprints beyond a count."""
        return {
            "licenceId": self.licence_id,
            "licensee": self.licensee_name,
            "kind": self.kind,
            "seats": self.seats,
            "features": list(self.features),
            "issuedAt": format_time(self.issued_at),
            "expiresAt": format_time(self.expires_at) if self.expires_at else None,
            "trial": self.trial,
            "boundDevelopers": len(self.developers),
            "boundMachines": len(self.machines),
        }


@dataclass(frozen=True)
class LicenceStatus:
    """The result of looking for, verifying and evaluating a licence."""

    state: str
    reason: str
    licence: Licence | None = None
    source: str | None = None
    #: Days until expiry (negative once expired); None for a perpetual licence.
    days_remaining: int | None = None
    checked: tuple[str, ...] = field(default_factory=tuple)

    @property
    def premium_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def edition(self) -> str:
        return EDITION_PREMIUM if self.premium_active else EDITION_COMMUNITY

    def grants(self, feature: str) -> bool:
        return self.premium_active and self.licence is not None and self.licence.grants(feature)

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "edition": self.edition,
            "state": self.state,
            "reason": self.reason,
            "premiumActive": self.premium_active,
        }
        if self.licence is not None:
            wire["licence"] = self.licence.summary()
        if self.source:
            wire["source"] = self.source
        if self.days_remaining is not None:
            wire["daysRemaining"] = self.days_remaining
        if self.checked:
            wire["checked"] = list(self.checked)
        return wire


NO_LICENCE = LicenceStatus(
    state=STATE_NONE,
    reason="No Meridian Loom Premium licence is installed; the free Community "
    "edition is active.",
)


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LicenceError(STATE_INVALID, f"licence field {key!r} is missing or empty")
    return value.strip()


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise LicenceError(STATE_INVALID, f"licence {name} must be a non-empty list of strings")
    return [v.strip() for v in value]


def parse_and_verify(
    text: str | bytes, trusted: Mapping[str, TrustedKey], revoked_key_ids: frozenset[str] = frozenset()
) -> Licence:
    """Check structure and signature. Says nothing about *who* or *when* —
    :func:`evaluate` does that — so a licence for another machine still
    parses and can be shown to the person who installed it by mistake."""
    raw = text.encode("utf-8") if isinstance(text, str) else text
    if len(raw) > _MAX_LICENCE_BYTES:
        raise LicenceError(STATE_INVALID, "licence file is too large to be a licence")
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as error:
        raise LicenceError(STATE_INVALID, "licence file is not valid JSON") from error
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise LicenceError(STATE_INVALID, f"not a Meridian Loom licence (expected format {FORMAT!r})")
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        raise LicenceError(STATE_INVALID, "licence has no payload or signature")

    key_id = signature.get("keyId")
    if signature.get("alg") != "Ed25519" or not isinstance(key_id, str):
        raise LicenceError(STATE_INVALID, "licence signature is not Ed25519 with a key id")
    if key_id in revoked_key_ids:
        raise LicenceError(STATE_UNTRUSTED, f"signing key {key_id} has been revoked; request a re-issued licence")
    key = trusted.get(key_id)
    if key is None:
        raise LicenceError(
            STATE_UNTRUSTED,
            f"licence was signed by key {key_id!r}, which this version of Meridian "
            "Loom does not trust; update Meridian Loom or request a re-issued licence",
        )
    try:
        signature_bytes = base64.b64decode(str(signature.get("value")), validate=True)
    except (binascii.Error, ValueError) as error:
        raise LicenceError(STATE_INVALID, "licence signature is not valid base64") from error

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(key.public_key).verify(
            signature_bytes, canonical_payload(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise LicenceError(
            STATE_INVALID,
            "licence signature does not match its contents; the file was altered or corrupted",
        ) from error

    # Signature good: from here on we are validating what the vendor signed,
    # so a failure means a vendor-side issuing mistake, not tampering.
    if payload.get("product") != PRODUCT:
        raise LicenceError(STATE_INVALID, "licence is for a different product")
    if payload.get("edition") != EDITION_PREMIUM:
        raise LicenceError(STATE_INVALID, "licence edition is not 'premium'")
    kind = payload.get("kind")
    if kind not in KINDS:
        raise LicenceError(STATE_INVALID, f"licence kind must be one of {', '.join(KINDS)}")

    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        raise LicenceError(STATE_INVALID, "licence has no bindings")
    developers: list[str] = []
    machines: list[str] = []
    if kind == KIND_DEVELOPER:
        developers = [d.lower() for d in _string_list(bindings.get("developers"), "developers")]
        for email in developers:
            if not _EMAIL.match(email):
                raise LicenceError(STATE_INVALID, f"licence names an invalid developer email: {email!r}")
    else:
        machines = [m.upper() for m in _string_list(bindings.get("machines"), "machines")]
        for fingerprint in machines:
            if fingerprint == "*":
                if not key.development:
                    raise LicenceError(STATE_INVALID, "wildcard machine binding is not permitted")
            elif not _FINGERPRINT.match(fingerprint):
                raise LicenceError(STATE_INVALID, f"licence names an invalid machine fingerprint: {fingerprint!r}")

    seats = payload.get("seats")
    if not isinstance(seats, int) or isinstance(seats, bool) or seats < 1:
        raise LicenceError(STATE_INVALID, "licence seats must be an integer >= 1")
    bound = len(developers) or len(machines)
    if bound > seats:
        raise LicenceError(STATE_INVALID, f"licence binds {bound} identities but only {seats} seat(s) were purchased")

    features = _string_list(payload.get("features"), "features")
    for feature in features:
        if feature != "*" and feature not in FEATURES:
            raise LicenceError(STATE_INVALID, f"licence grants an unknown feature: {feature!r}")

    licensee = payload.get("licensee")
    if not isinstance(licensee, dict):
        raise LicenceError(STATE_INVALID, "licence has no licensee")

    expires = payload.get("expiresAt")
    not_before = payload.get("notBefore")
    return Licence(
        licence_id=_require_str(payload, "licenceId"),
        licensee_name=_require_str(licensee, "name"),
        licensee_contact=str(licensee.get("contact") or "").strip(),
        kind=kind,
        developers=tuple(developers),
        machines=tuple(machines),
        seats=seats,
        features=tuple(features),
        issued_at=parse_time(payload.get("issuedAt"), "issuedAt"),
        not_before=parse_time(not_before, "notBefore") if not_before is not None else None,
        expires_at=parse_time(expires, "expiresAt") if expires is not None else None,
        trial=bool(payload.get("trial", False)),
        key_id=key_id,
        development_key=key.development,
    )


def evaluate(
    licence: Licence,
    *,
    now: datetime,
    machine_fingerprint: str | None,
    developer_emails: frozenset[str],
    source: str | None = None,
) -> LicenceStatus:
    """Decide what an authentic licence entitles *this* machine and developer
    to, right now."""
    if licence.not_before is not None and now < licence.not_before:
        return LicenceStatus(
            STATE_NOT_YET_VALID,
            f"licence {licence.licence_id} is not valid until {format_time(licence.not_before)}",
            licence, source,
        )

    if licence.kind == KIND_MACHINE:
        allowed = set(licence.machines)
        if "*" not in allowed and (machine_fingerprint is None or machine_fingerprint not in allowed):
            where = machine_fingerprint or "unavailable on this system"
            return LicenceStatus(
                STATE_WRONG_MACHINE,
                f"licence {licence.licence_id} is bound to other machine(s); this machine's "
                f"fingerprint is {where}. Send it to your Meridian Loom licence contact.",
                licence, source,
            )
    else:
        matched = licence.developers and any(email in licence.developers for email in developer_emails)
        if not matched:
            who = ", ".join(sorted(developer_emails)) if developer_emails else "not set (git user.email is empty)"
            return LicenceStatus(
                STATE_WRONG_DEVELOPER,
                f"licence {licence.licence_id} is a per-developer licence and the git identity "
                f"in use ({who}) is not one of the named developers.",
                licence, source,
            )

    if licence.expires_at is None:
        return LicenceStatus(STATE_VALID, "Premium licence active (perpetual).", licence, source, None)

    remaining = licence.expires_at - now
    days = math.floor(remaining.total_seconds() / 86400)
    if remaining >= timedelta(0):
        return LicenceStatus(
            STATE_VALID,
            f"Premium licence active until {format_time(licence.expires_at)}.",
            licence, source, days,
        )
    if now <= licence.expires_at + timedelta(days=GRACE_DAYS):
        left = (licence.expires_at + timedelta(days=GRACE_DAYS) - now).days
        return LicenceStatus(
            STATE_GRACE,
            f"Licence {licence.licence_id} expired on {format_time(licence.expires_at)}; premium "
            f"features continue for {left} more day(s) of grace. Renew to avoid interruption.",
            licence, source, days,
        )
    return LicenceStatus(
        STATE_EXPIRED,
        f"licence {licence.licence_id} expired on {format_time(licence.expires_at)} and the "
        f"{GRACE_DAYS}-day grace period has ended; the free Community edition is active.",
        licence, source, days,
    )
