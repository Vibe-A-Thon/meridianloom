"""Corpus batch 1 — ledger chain tampering, redaction, privacy erasure,
signatures, trailers, interop notarisation, canonical edge cases.

Every fixture drives a real control and asserts the block/detection AND
the evidence record. Families here are the floor (FR-M46-10); batches add
policy, worktree-boundary, identity, and economics-injection families.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from meridian_core import interop
from meridian_core.ledger import (
    BlobError,
    EphemeralSigningKeyProvider,
    Ledger,
)
from meridian_core.ledger import keys as ledger_keys
from meridian_core.ledger import privacy as ledger_privacy
from meridian_core.ledger import trailer_spec as ts
from meridian_core.trailers import append_trailer

from .harness import (
    Fixture,
    KIND_BLOCKED,
    KIND_DETECTED,
    KIND_REDACTED,
    KIND_RECORDED,
    SURFACE_HOSTED,
    SURFACE_PASSIVE,
)


def _entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": f"ADV-{seq}",
        "phase": "build",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": "agent-adv",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-17T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


def _ledger(tmp: Path) -> Ledger:
    led = Ledger(tmp / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 4):
        led.append(_entry(seq))
    return led


def _expect_append_only_refusal(tmp: Path, mutate: str) -> None:
    """FR-M10-01's triggers ABORT any UPDATE/DELETE of recorded rows; a raw
    forged INSERT (mutate == "insert_forged") is NOT refused at write time —
    the gapless invariant lives in the Ledger facade, so a raw SQL attack
    reaching the file directly is *detected* by chain verification instead.
    Both layers are asserted here, classified honestly per case."""
    led = _ledger(tmp)
    try:
        seq, entry_hash, prev = led.conn.execute(
            "SELECT seq, entry_hash, prev_hash FROM ledger_entry WHERE seq = 2"
        ).fetchone()
        if mutate == "insert_forged":
            led.conn.execute(
                "INSERT INTO ledger_entry (seq, ts_utc, prev_hash, entry_hash,"
                " story_id, phase, loop_id, loop_iteration, actor_id,"
                " actor_version, actor_kind, policy_version, action_type)"
                " VALUES (99, '2026-09-17T00:00:00Z', ?, ?, 'FORGED', 'build',"
                " 'L1', 1, 'mallory', '0.0.1', 'role', 'policy-v1', 'diff')",
                (entry_hash, b"\xff" * 32),
            )
            led.conn.commit()
            # Detection layer: the forged row breaks the hash chain — the
            # verify verdict is the usable evidence record.
            assert led.verify().ok is False
            return
        statements: dict[str, tuple[str, tuple]] = {
            "entry_hash": (
                "UPDATE ledger_entry SET entry_hash = ? WHERE seq = ?",
                (b"\x00" * 32, seq),
            ),
            "prev_hash": (
                "UPDATE ledger_entry SET prev_hash = ? WHERE seq = ?",
                (prev, seq),
            ),
            "seq": ("UPDATE ledger_entry SET seq = 99 WHERE seq = ?", (seq,)),
            "ts": (
                "UPDATE ledger_entry SET ts_utc = '2000-01-01T00:00:00Z'"
                " WHERE seq = ?",
                (seq,),
            ),
            "delete": ("DELETE FROM ledger_entry WHERE seq = ?", (seq,)),
        }
        assert mutate in statements, f"unknown mutation {mutate}"
        sql, params = statements[mutate]
        # The ABORT fires at execute time; the named FR-M10-01 message is
        # the evidence record of the refusal.
        with pytest.raises(sqlite3.IntegrityError, match="FR-M10-01"):
            led.conn.execute(sql, params)
        led.conn.rollback()
        # Evidence the refusal is real: the chain still verifies untouched.
        assert led.verify().ok is True
    finally:
        led.close()


# -- hosted: append-only enforcement (SEC-34 blocks) --------------------------


def _f_chain(mutate: str, description: str):
    return Fixture(
        id=f"CHAIN-{mutate.upper()}",
        family="ledger_chain_tamper",
        surface=SURFACE_HOSTED,
        kind=KIND_BLOCKED,
        description=description,
        fn=lambda tmp: _expect_append_only_refusal(tmp, mutate),
    )


# -- hosted: redaction (SEC-07; secrets must never persist) --------------------


def _f_redaction(secret: str, marker: str, description: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = _ledger(tmp)
        try:
            led.append(
                _entry(4, input=f"output contained {secret}", blob_subject="adv")
            )
            row = led.query(action_type="diff", story_id="ADV-4")[0]
            persisted = led.read_blob(row["input_ref"], row["blob_key_id"]).decode()
            # The secret never reaches the blob store; the redaction marker
            # does — that marker IS the evidence record of the block.
            assert secret not in persisted, (
                f"SECRET LEAKED via {marker}: {persisted!r}"
            )
            assert "REDACTED" in persisted
            assert led.verify().ok is True
        finally:
            led.close()

    return Fixture(
        id=f"REDACT-{marker}",
        family="secret_redaction",
        surface=SURFACE_HOSTED,
        kind=KIND_REDACTED,
        description=description,
        fn=fn,
    )


_PEM = (
    "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
    "ymee27uBm+vItb0=\n-----END PRIVATE KEY-----"
)

REDACTION_FIXTURES = [
    _f_redaction(_PEM, "PEM", "PEM private key block in agent output"),
    _f_redaction(
        "AKIAIOSFODNN7EXAMPLE", "AWS", "AWS access key id in tool output"
    ),
    _f_redaction(
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0",
        "GHP",
        "GitHub classic PAT",
    ),
    _f_redaction(
        "github_pat_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2",
        "GHPAT",
        "GitHub fine-grained PAT",
    ),
    _f_redaction(
        "xoxb-" + "123456789012-abcdefghijkl", "SLACK", "Slack bot token"
    ),
    _f_redaction(
        "sk-" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr", "OPENAI", "OpenAI-style API key"
    ),
    _f_redaction(
        'api_key = "' + "z9y8x7w6v5u4t3s2r1q0" + '"',
        "ASSIGN",
        "api_key assignment in log line",
    ),
    _f_redaction(
        "Authorization: Bearer " + "m1n2o3p4q5r6s7t8u9v0",
        "BEARER",
        "bearer token in a header dump",
    ),
    _f_redaction(
        json.dumps({"nested": {"token": "gho_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"}}),
        "NESTED",
        "token nested inside JSON agent output",
    ),
    _f_redaction(
        "password=hunter2secretvalue123", "PASSWORD", "password assignment"
    ),
]


# -- hosted: privacy erasure ----------------------------------------------------


def _f_erasure(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.append(
            _entry(4, input="personal content of alice", blob_subject="alice")
        )
        controller = ledger_privacy.PrivacyController(led)
        controller.erase_subject("alice", reason="adversarial corpus fixture")
        row = led.query(action_type="diff", story_id="ADV-4")[0]
        with pytest.raises(BlobError):
            led.read_blob(row["input_ref"], row["blob_key_id"])
        # The erasure itself is an auditable chain entry (the evidence).
        assert any(
            e.subject_id == "alice" for e in controller.erasures()
        )
        assert led.verify().ok is True
    finally:
        led.close()


# -- hosted: required fields / encoding edges ------------------------------------


def _f_missing_required(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        with pytest.raises(ValueError, match="missing required fields"):
            led.append({"story_id": "X"})  # type: ignore[arg-type]
        assert led.verify().ok is True
    finally:
        led.close()


def _f_unicode_actor(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        # Homoglyph/confusable actor id: recorded as given (no silent
        # rewrite), chained, verifiable — the record IS the evidence.
        led.append(
            _entry(4, actor_id="аgent-аdmin")  # Cyrillic а
        )
        row = led.query(action_type="diff", story_id="ADV-4")[0]
        assert row["actor_id"] == "аgent-аdmin"
        assert led.verify().ok is True
    finally:
        led.close()


def _f_large_detail(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.append(
            _entry(4, input="x" * 1_000_000, blob_subject="adv-large")
        )
        assert led.verify().ok is True
    finally:
        led.close()


# -- passive: signatures ----------------------------------------------------------


def _f_forged_signature(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.emit_tree_head_now()
        head = led.latest_tree_head()
        stranger = Ed25519PrivateKey.generate()
        forged = stranger.sign(
            ledger_keys.tree_head_message(
                head["seq"], head["root_hash"], head["signed_at"]
            )
        )
        # The forgery is a VALID signature — by the wrong key. It verifies
        # against the stranger's key (that is what a signed replacement
        # history looks like) and the detection verdict is that it fails
        # against the ledger's enrolled key.
        assert (
            ledger_keys.verify_tree_head(
                ledger_keys.public_key_bytes(stranger),
                head["seq"],
                head["root_hash"],
                head["signed_at"],
                forged,
            )
            is True
        )
        assert (
            ledger_keys.verify_tree_head(
                ledger_keys.public_key_bytes(led._signing_key.private_key()),
                head["seq"],
                head["root_hash"],
                head["signed_at"],
                forged,
            )
            is False
        )
    finally:
        led.close()


def _f_wrong_key(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.emit_tree_head_now()
        head = led.latest_tree_head()
        stranger = Ed25519PrivateKey.generate()
        assert (
            ledger_keys.verify_tree_head(
                ledger_keys.public_key_bytes(stranger),
                head["seq"],
                head["root_hash"],
                head["signed_at"],
                head["signature"],
            )
            is False
        )
    finally:
        led.close()


def _f_truncated_root(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.emit_tree_head_now()
        head = led.latest_tree_head()
        truncated = head["root_hash"][:16]
        assert (
            ledger_keys.verify_tree_head(
                ledger_keys.public_key_bytes(led._signing_key.private_key()),
                head["seq"],
                truncated,
                head["signed_at"],
                head["signature"],
            )
            is False
        )
    finally:
        led.close()


# -- passive: trailers --------------------------------------------------------------


def _f_trailer(forge: str) -> Fixture:
    def fn(tmp: Path) -> None:
        led = _ledger(tmp)
        try:
            led.emit_tree_head_now()
            head = led.latest_tree_head()
            value = ts.trailer_from_tree_head(head, led.signing_public_key)
            if forge == "TAMPERED":
                value = value.replace(
                    "root=" + head["root_hash"].hex(), "root=" + "0" * 64, 1
                )
            elif forge == "UNKNOWN_KEY":
                other = Ledger(tmp / "other", EphemeralSigningKeyProvider())
                other.append(_entry(1))
                other.emit_tree_head_now()
                ohead = other.latest_tree_head()
                value = ts.trailer_from_tree_head(ohead, led.signing_public_key)
                other.close()
            elif forge == "MALFORMED":
                value = "v1 seq=abc"
            parsed = ts.parse_meridian_ledger_trailers(
                append_trailer("merge governed change", ts.TRAILER_KEY, value)
            )
            assert parsed.latest is not None or forge == "MALFORMED"
            if forge == "MALFORMED":
                assert parsed.refs == [] and parsed.warnings
            else:
                assert ts.verify_trailer(parsed.latest) is False
        finally:
            led.close()

    return Fixture(
        id=f"TRAILER-{forge}",
        family="trailer_forgery",
        surface=SURFACE_PASSIVE,
        kind=KIND_DETECTED,
        description=f"Meridian-Ledger trailer: {forge.lower()} variant fails closed",
        fn=fn,
    )


# -- passive: interop notarisation --------------------------------------------------


def _interop_record(tool: str, payload: dict, tmp: Path) -> interop.ForeignRecord:
    import hashlib
    from datetime import datetime, timezone

    raw = json.dumps(payload).encode("utf-8")
    return interop.ForeignRecord(
        tool=tool,
        kind="git-note",
        source=f"refs/notes/{tool}",
        commit="a" * 40,
        content=raw.decode("utf-8"),
        digest="sha256:" + hashlib.sha256(raw).hexdigest(),
        observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _f_notarisation(case: str) -> Fixture:
    def fn(tmp: Path) -> None:
        payload = {"tool": "aider", "files": ["a.py"]}
        before = _interop_record("aider", payload, tmp)
        if case == "REWRITTEN":
            after = _interop_record("aider", {"tool": "aider", "files": ["b.py"]}, tmp)
            verdict = interop.verify_notarisation(before.digest, after)
            assert verdict.ok is False
            assert "altered" in verdict.detail
        elif case == "GONE":
            verdict = interop.verify_notarisation(before.digest, None)
            assert verdict.ok is False
            assert "no longer" in verdict.detail
        else:  # SANITY: unchanged verifies — the detector is not a hair-trigger
            verdict = interop.verify_notarisation(before.digest, before)
            assert verdict.ok is True

    return Fixture(
        id=f"NOTARISE-{case}",
        family="notarisation_tamper",
        surface=SURFACE_PASSIVE,
        kind=KIND_DETECTED if case != "SANITY" else KIND_RECORDED,
        description=f"notarised record {case.lower()}",
        fn=fn,
    )


def fixtures() -> list[Fixture]:
    chain = [
        _f_chain("entry_hash", "rewriting an entry_hash is ABORTed by trigger"),
        _f_chain("prev_hash", "rewriting a prev_hash is ABORTed by trigger"),
        _f_chain("seq", "rewriting a sequence number is ABORTed by trigger"),
        _f_chain("ts", "backdating a timestamp is ABORTed by trigger"),
        _f_chain("delete", "deleting an entry is ABORTed by trigger"),
        Fixture(
            id="CHAIN-INSERT_FORGED",
            family="ledger_chain_tamper",
            surface=SURFACE_HOSTED,
            kind=KIND_DETECTED,
            description=(
                "raw forged INSERT (seq 99, forged hash) bypasses the write"
                " path; chain verification detects it — enforcement layer"
                " is verify, not a write-time refusal"
            ),
            fn=lambda tmp: _expect_append_only_refusal(tmp, "insert_forged"),
        ),
    ]
    return [
        *chain,
        Fixture(
            id="CHAIN-TREEHEAD-UPDATE",
            family="ledger_chain_tamper",
            surface=SURFACE_HOSTED,
            kind=KIND_BLOCKED,
            description="UPDATE of a signed tree head is ABORTed by trigger",
            fn=_treehead_update_refused,
        ),
        *REDACTION_FIXTURES,
        Fixture(
            id="PRIV-ERASE",
            family="privacy_erasure",
            surface=SURFACE_HOSTED,
            kind=KIND_BLOCKED,
            description="erased subject's blob is unreadable (crypto-shredded), erasure is chained",
            fn=_f_erasure,
        ),
        Fixture(
            id="REQ-MISSING",
            family="schema_refusal",
            surface=SURFACE_HOSTED,
            kind=KIND_BLOCKED,
            description="entry missing required fields is refused before any write",
            fn=_f_missing_required,
        ),
        Fixture(
            id="ENC-UNICODE-ACTOR",
            family="canonical_encoding",
            surface=SURFACE_HOSTED,
            kind=KIND_RECORDED,
            description="Cyrillic-homoglyph actor id recorded as given, chain verifies",
            fn=_f_unicode_actor,
        ),
        Fixture(
            id="ENC-LARGE-BLOB",
            family="canonical_encoding",
            surface=SURFACE_HOSTED,
            kind=KIND_RECORDED,
            description="1MB blob content is encrypted, chained and verifiable",
            fn=_f_large_detail,
        ),
        Fixture(
            id="SIG-FORGED",
            family="tree_head_signature",
            surface=SURFACE_PASSIVE,
            kind=KIND_DETECTED,
            description="tree head signed by a stranger key does not verify against the ledger key",
            fn=_f_forged_signature,
        ),
        Fixture(
            id="SIG-WRONGKEY",
            family="tree_head_signature",
            surface=SURFACE_PASSIVE,
            kind=KIND_DETECTED,
            description="honest signature verified against the wrong public key fails",
            fn=_f_wrong_key,
        ),
        Fixture(
            id="SIG-TRUNCATED",
            family="tree_head_signature",
            surface=SURFACE_PASSIVE,
            kind=KIND_DETECTED,
            description="truncated root hash does not verify",
            fn=_f_truncated_root,
        ),
        _f_trailer("TAMPERED"),
        _f_trailer("UNKNOWN_KEY"),
        _f_trailer("MALFORMED"),
        _f_notarisation("REWRITTEN"),
        _f_notarisation("GONE"),
        _f_notarisation("SANITY"),
    ]


def _treehead_update_refused(tmp: Path) -> None:
    led = _ledger(tmp)
    try:
        led.emit_tree_head_now()
        head_seq = led.latest_tree_head()["seq"]
        with pytest.raises(sqlite3.IntegrityError, match="FR-M10-01"):
            led.conn.execute(
                "UPDATE tree_head SET root_hash = ? WHERE seq = ?",
                (b"\x00" * 32, head_seq),
            )
        led.conn.rollback()
        assert led.verify().ok is True
    finally:
        led.close()
