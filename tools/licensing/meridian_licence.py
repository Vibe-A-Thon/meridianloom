#!/usr/bin/env python3
"""Licensor tool: create signing keys, issue and inspect Meridian Loom licences.

THIS TOOL IS FOR THE LICENSOR. It is not part of the product, is not packaged
into the VSIX, and needs the private signing key — which must never be
committed, emailed, or stored in the repository.

    # once: create the signing key pair (keep the private file offline/backed up)
    python tools/licensing/meridian_licence.py keygen --out-dir ~/secure/meridian-signing

    # per-developer licence (named users; the customer supplies the git emails)
    python tools/licensing/meridian_licence.py issue \\
        --key ~/secure/meridian-signing/ml-2026-1.private.key --key-id ml-2026-1 \\
        --licensee "Acme Software Ltd" --contact it@acme.example \\
        --kind developer --developer alice@acme.example --developer bob@acme.example \\
        --seats 2 --days 365 --out acme-developers.mlic

    # per-machine licence (the customer runs `meridian licence fingerprint` on each machine)
    python tools/licensing/meridian_licence.py issue ... \\
        --kind machine --machine MLM1-1A2B3-... --seats 1 --days 365 --out acme-build01.mlic

    # 30-day trial of everything
    python tools/licensing/meridian_licence.py issue ... --trial --days 30

    # check what a file says and whether it verifies
    python tools/licensing/meridian_licence.py inspect acme-developers.mlic

The customer installs the resulting ``.mlic`` file; see LICENSING.md.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from meridian_core.licensing import keys as trust_keys  # noqa: E402
from meridian_core.licensing import licence as lic  # noqa: E402
from meridian_core.licensing import machine  # noqa: E402


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _load_private(path: str) -> Ed25519PrivateKey:
    seed = base64.b64decode(Path(path).read_text(encoding="ascii").strip(), validate=True)
    if len(seed) != 32:
        raise SystemExit(f"{path}: not a 32-byte Ed25519 seed (base64)")
    return Ed25519PrivateKey.from_private_bytes(seed)


def cmd_keygen(args: argparse.Namespace) -> int:
    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    key_id = args.key_id or f"ml-{datetime.now(timezone.utc).year}-1"
    private = out / f"{key_id}.private.key"
    public = out / f"{key_id}.public.key"
    if private.exists() and not args.force:
        raise SystemExit(f"{private} already exists; refusing to overwrite (use --force to replace it)")
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private.write_text(_b64(seed) + "\n", encoding="ascii")
    try:
        os.chmod(private, 0o600)
    except OSError:
        pass
    public.write_text(_b64(pub) + "\n", encoding="ascii")
    print(f"key id      : {key_id}")
    print(f"private key : {private}   <- SECRET: back it up offline, never commit it")
    print(f"public key  : {public}")
    print(f"public (b64): {_b64(pub)}")
    print()
    print("To trust this key in the product, add to PRODUCTION_KEYS in")
    print(f'core/meridian_core/licensing/keys.py:   "{key_id}": "{_b64(pub)}",')
    return 0


def _expiry(args: argparse.Namespace, issued: datetime) -> str | None:
    if args.perpetual:
        return None
    if args.expires:
        return lic.format_time(lic.parse_time(args.expires, "--expires"))
    days = args.days if args.days is not None else (30 if args.trial else 365)
    return lic.format_time(issued + timedelta(days=days))


def cmd_issue(args: argparse.Namespace) -> int:
    key = _load_private(args.key)
    issued = datetime.now(timezone.utc)
    if args.kind == lic.KIND_DEVELOPER:
        if not args.developer:
            raise SystemExit("--kind developer needs at least one --developer EMAIL")
        bindings = {"developers": sorted({d.strip().lower() for d in args.developer})}
    else:
        if not args.machine:
            raise SystemExit("--kind machine needs at least one --machine MLM1-... fingerprint")
        bindings = {"machines": sorted({m.strip().upper() for m in args.machine})}
    bound = len(next(iter(bindings.values())))
    seats = args.seats if args.seats is not None else bound
    features = args.feature or ["*"]
    payload = {
        "licenceId": args.licence_id or f"ML-{issued:%Y%m%d}-{secrets.token_hex(4).upper()}",
        "product": lic.PRODUCT,
        "edition": lic.EDITION_PREMIUM,
        "licensee": {"name": args.licensee, "contact": args.contact or ""},
        "kind": args.kind,
        "bindings": bindings,
        "seats": seats,
        "features": features,
        "issuedAt": lic.format_time(issued),
        "expiresAt": _expiry(args, issued),
        "trial": bool(args.trial),
    }
    if args.not_before:
        payload["notBefore"] = lic.format_time(lic.parse_time(args.not_before, "--not-before"))
    signature = key.sign(lic.canonical_payload(payload))
    document = {
        "format": lic.FORMAT,
        "payload": payload,
        "signature": {"alg": "Ed25519", "keyId": args.key_id, "value": _b64(signature)},
    }
    Path(args.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"  licence id : {payload['licenceId']}")
    print(f"  kind       : {args.kind}   seats: {seats}   features: {', '.join(features)}")
    print(f"  expires    : {payload['expiresAt'] or 'never (perpetual)'}")
    # Verify what we just wrote, with the public half of the signing key, so
    # a mis-typed --key-id is caught here and not by the customer.
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    lic.parse_and_verify(
        Path(args.out).read_bytes(), {args.key_id: lic.TrustedKey(args.key_id, public)}
    )
    print("  self-check : signature verifies")
    if args.key_id not in trust_keys.PRODUCTION_KEYS:
        print(f"  WARNING    : key id {args.key_id!r} is not in keys.py PRODUCTION_KEYS; "
              "the product will reject this licence until it is added and released.")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    text = Path(args.file).read_bytes()
    document = json.loads(text.decode("utf-8-sig"))
    print(json.dumps(document.get("payload"), indent=2, sort_keys=True))
    trust = trust_keys.trusted_keys()
    if args.public_key:
        raw = base64.b64decode(Path(args.public_key).read_text(encoding="ascii").strip())
        kid = document.get("signature", {}).get("keyId", "unknown")
        trust = {kid: lic.TrustedKey(kid, raw)}
    try:
        licence = lic.parse_and_verify(text, trust, trust_keys.REVOKED_KEY_IDS)
    except lic.LicenceError as error:
        print(f"\nSIGNATURE/STRUCTURE: FAILED ({error.state}) — {error}")
        return 1
    print("\nSIGNATURE/STRUCTURE: OK")
    status = lic.evaluate(
        licence, now=datetime.now(timezone.utc),
        machine_fingerprint=machine.machine_fingerprint(),
        developer_emails=frozenset(), source=args.file,
    )
    print(f"time/validity here : {status.state} — {status.reason}")
    return 0


def cmd_fingerprint(_: argparse.Namespace) -> int:
    value = machine.machine_fingerprint()
    if value is None:
        print("no machine identifier available on this system", file=sys.stderr)
        return 1
    print(value)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    keygen = sub.add_parser("keygen", help="create an Ed25519 signing key pair")
    keygen.add_argument("--out-dir", required=True)
    keygen.add_argument("--key-id", help="default: ml-<year>-1")
    keygen.add_argument("--force", action="store_true")
    keygen.set_defaults(run=cmd_keygen)

    issue = sub.add_parser("issue", help="sign a licence file")
    issue.add_argument("--key", required=True, help="private key file from keygen")
    issue.add_argument("--key-id", required=True)
    issue.add_argument("--licensee", required=True, help="the customer's legal name")
    issue.add_argument("--contact", help="customer licence contact email")
    issue.add_argument("--kind", choices=lic.KINDS, required=True)
    issue.add_argument("--developer", action="append", help="git email of a named developer; repeatable")
    issue.add_argument("--machine", action="append", help="machine fingerprint (MLM1-...); repeatable")
    issue.add_argument("--seats", type=int, help="seats purchased (default: number of bindings)")
    issue.add_argument("--feature", action="append", choices=("*",) + lic.FEATURES,
                       help="repeatable; default '*' (all Premium features)")
    issue.add_argument("--days", type=int, help="term in days from now (default 365, or 30 for --trial)")
    issue.add_argument("--expires", help="explicit expiry, ISO-8601 UTC")
    issue.add_argument("--perpetual", action="store_true", help="no expiry")
    issue.add_argument("--not-before", help="ISO-8601 UTC start")
    issue.add_argument("--trial", action="store_true", help="mark as a trial (display only)")
    issue.add_argument("--licence-id")
    issue.add_argument("--out", required=True)
    issue.set_defaults(run=cmd_issue)

    inspect = sub.add_parser("inspect", help="show a licence and check its signature")
    inspect.add_argument("file")
    inspect.add_argument("--public-key", help="verify against this public key file instead of the built-in keys")
    inspect.set_defaults(run=cmd_inspect)

    sub.add_parser("fingerprint", help="this machine's fingerprint").set_defaults(run=cmd_fingerprint)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
