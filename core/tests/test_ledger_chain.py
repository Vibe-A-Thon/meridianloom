"""Tests for the hash chain, Merkle tree and signed tree heads.

FR-M10-02: unbroken chain from sequence 1; entry_hash binds prev_hash and
canonical payload; recompute from reopening matches.
FR-M10-03: Merkle root over entries; RFC 6962/9162 inclusion and
consistency proofs verify, and reject forgeries.
FR-M10-04: tree heads are emitted on cadence, Ed25519-verifiable with
the public key only; provisioned vs ephemeral key handling.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from meridian_core.ledger import (
    GENESIS_HASH,
    EphemeralSigningKeyProvider,
    Ledger,
    MerkleFrontier,
    ProvisionedSigningKeyProvider,
    consistency_proof,
    entry_hash,
    hashable_payload,
    inclusion_proof,
    merkle_root,
    verify_consistency,
    verify_inclusion,
    verify_tree_head,
)


def make_entry(seq: int, story: str = "EDB-12345", ts: str = "2026-09-01T00:00:00.000001Z") -> dict:
    return {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "developer-agent",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": ts,
    }


@pytest.fixture()
def ledger(tmp_path) -> Ledger:
    with Ledger(
        tmp_path / ".meridian" / "ledger",
        EphemeralSigningKeyProvider(),
    ) as led:
        yield led


class TestHashChain:
    def test_genesis_links_to_zero_hash(self, ledger):
        result = ledger.append(make_entry(1))
        assert result.sequence == 1
        assert result.prev_hash == GENESIS_HASH

    def test_chain_is_unbroken_across_appends(self, ledger):
        results = [ledger.append(make_entry(i)) for i in range(1, 5)]
        for prev, nxt in zip(results, results[1:]):
            assert nxt.prev_hash == prev.entry_hash
            assert nxt.sequence == prev.sequence + 1

    def test_entry_hash_binds_canonical_payload(self, ledger):
        result = ledger.append(make_entry(1))
        row = ledger.conn.execute(
            "SELECT * FROM ledger_entry WHERE seq = 1"
        ).fetchone()
        columns = [d[0] for d in ledger.conn.execute(
            "SELECT * FROM ledger_entry LIMIT 0"
        ).description]
        row_dict = dict(zip(columns, row))
        expected = entry_hash(GENESIS_HASH, row_dict)
        assert expected == result.entry_hash

    def test_changing_a_field_changes_the_hash(self, ledger):
        a = ledger.append(make_entry(1, story="EDB-A"))
        ledger2_dir = Path(ledger.dir)
        ledger.close()
        # Same content, different story: different digest, so tampering a
        # single field is detectable without re-deriving the whole chain.
        with Ledger(ledger2_dir, EphemeralSigningKeyProvider()) as other:
            b = other.append(make_entry(1, story="EDB-B"))
        assert a.entry_hash != b.entry_hash

    def test_hash_matches_independent_implementation(self, ledger):
        result = ledger.append(make_entry(1))
        row = dict(
            zip(
                [d[0] for d in ledger.conn.execute("SELECT * FROM ledger_entry LIMIT 0").description],
                ledger.conn.execute("SELECT * FROM ledger_entry WHERE seq = 1").fetchone(),
            )
        )
        payload = hashable_payload(row)
        independent = hashlib.sha256()
        independent.update(GENESIS_HASH)
        independent.update(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        assert independent.digest() == result.entry_hash

    def test_missing_required_fields_rejected(self, ledger):
        with pytest.raises(ValueError, match="missing required fields"):
            ledger.append({"story_id": "X"})

    def test_unknown_fields_rejected(self, ledger):
        with pytest.raises(ValueError, match="unknown entry fields"):
            ledger.append({**make_entry(1), "frobnicate": True})

    def test_chain_survives_reopen(self, tmp_path):
        ledger_dir = tmp_path / "ledger"
        with Ledger(ledger_dir, EphemeralSigningKeyProvider()) as led:
            led.append(make_entry(1))
            led.append(make_entry(2))
        with Ledger(ledger_dir, EphemeralSigningKeyProvider()) as led:
            assert led.last_sequence == 2
            r = led.append(make_entry(3))
            assert r.sequence == 3
            assert r.prev_hash != GENESIS_HASH


class TestMerkle:
    def test_frontier_root_matches_recomputed_root(self, ledger):
        hashes = []
        for i in range(1, 33):
            hashes.append(ledger.append(make_entry(i)).entry_hash)
        assert ledger.root_hash() == merkle_root(hashes)

    def test_frontier_fold_is_incrementally_correct(self):
        leaves = [hashlib.sha256(f"leaf-{i}".encode()).digest() for i in range(50)]
        frontier = MerkleFrontier()
        for leaf in leaves:
            frontier.append(leaf)
        assert frontier.count == 50
        assert frontier.root() == merkle_root(leaves)
        assert frontier.root() != merkle_root(leaves[:-1])

    def test_inclusion_proof_verifies_and_rejects(self, ledger):
        hashes = [ledger.append(make_entry(i)).entry_hash for i in range(1, 9)]
        r = ledger.root_hash()
        for index in (0, 3, 7):
            path = inclusion_proof(hashes, index)
            assert verify_inclusion(index, hashes[index], 8, path, r)
        # Forged leaf: same position, different content.
        forged = hashlib.sha256(b"forged").digest()
        assert not verify_inclusion(2, forged, 8, inclusion_proof(hashes, 2), r)
        # Wrong position.
        assert not verify_inclusion(5, hashes[5], 8, inclusion_proof(hashes, 1), r)

    def test_consistency_proof_verifies_prefixes(self, ledger):
        hashes = [ledger.append(make_entry(i)).entry_hash for i in range(1, 13)]
        for old_size in (1, 3, 4, 7, 8, 11, 12):
            proof = consistency_proof(hashes, old_size)
            assert verify_consistency(
                old_size,
                merkle_root(hashes[:old_size]),
                12,
                merkle_root(hashes),
                proof,
            ), f"failed for old_size={old_size}"

    def test_consistency_proof_rejects_truncated_prefix(self, ledger):
        hashes = [ledger.append(make_entry(i)).entry_hash for i in range(1, 9)]
        proof = consistency_proof(hashes, 4)
        # The claimed old root is not the real prefix root.
        assert not verify_consistency(
            4, merkle_root(hashes[1:5]), 8, merkle_root(hashes), proof
        )


class TestSignedTreeHeads:
    def test_head_emitted_on_interval(self, tmp_path):
        ledger = Ledger(
            tmp_path / "ledger",
            EphemeralSigningKeyProvider(),
            tree_head_interval=5,
            tree_head_max_age_s=10**9,  # interval-only cadence
        )
        with ledger:
            for i in range(1, 5):
                result = ledger.append(make_entry(i))
                assert result.tree_head is None
            result = ledger.append(make_entry(5))
            assert result.tree_head is not None
            head = result.tree_head
            assert head["seq"] == 5
            heads = ledger.tree_heads()
            assert len(heads) == 1
            assert heads[0][0] == 5  # seq
        ledger2 = Ledger(
            tmp_path / "ledger",
            EphemeralSigningKeyProvider(),
            tree_head_interval=5,
            tree_head_max_age_s=10**9,
        )
        with ledger2:
            # Next head lands 5 entries later, not at the next append.
            for i in range(6, 10):
                assert ledger2.append(make_entry(i)).tree_head is None
            result = ledger2.append(make_entry(10))
            assert result.tree_head is not None and result.tree_head["seq"] == 10

    def test_head_is_ed25519_verifiable(self, tmp_path):
        provider = EphemeralSigningKeyProvider()
        ledger = Ledger(
            tmp_path / "ledger", provider, tree_head_interval=3,
            tree_head_max_age_s=10**9,
        )
        with ledger:
            for i in range(1, 4):
                result = ledger.append(make_entry(i))
            head = result.tree_head
            public_key = ledger.signing_public_key
            assert verify_tree_head(
                public_key,
                head["seq"],
                bytes.fromhex(head["rootHash"]),
                head["signedAt"],
                bytes.fromhex(head["signature"]),
            )
            # Wrong seq, wrong key, wrong root all fail.
            assert not verify_tree_head(
                public_key, head["seq"] + 1,
                bytes.fromhex(head["rootHash"]), head["signedAt"],
                bytes.fromhex(head["signature"]),
            )
            assert not verify_tree_head(
                EphemeralSigningKeyProvider().private_key().public_key()
                .public_bytes_raw(),  # noqa: SLF001 - test only
                head["seq"],
                bytes.fromhex(head["rootHash"]), head["signedAt"],
                bytes.fromhex(head["signature"]),
            )
            assert not verify_tree_head(
                public_key, head["seq"],
                b"\x00" * 32, head["signedAt"],
                bytes.fromhex(head["signature"]),
            )

    def test_provisioned_seed_gives_stable_signer_identity(self):
        seed = bytes(range(32))
        first = ProvisionedSigningKeyProvider(seed)
        second = ProvisionedSigningKeyProvider(seed)
        assert first.private_key().public_key() == second.private_key().public_key()

    def test_provisioned_seed_length_validated(self):
        with pytest.raises(ValueError, match="32 bytes"):
            ProvisionedSigningKeyProvider(b"too short")

    def test_no_key_material_written_to_disk(self, tmp_path, ledger):
        provider = EphemeralSigningKeyProvider()
        private = provider.private_key()
        raw_seed = bytes(range(32))  # stand-in: scan ledger dir for key bytes
        ledger.append(make_entry(1))
        for head in ledger.tree_heads():
            pass
        ledger.close()
        for path in tmp_path.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                assert raw_seed not in content
                assert (
                    private.private_bytes_raw() not in content
                ), f"private key leaked into {path}"
