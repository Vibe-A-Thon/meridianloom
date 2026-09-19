"""Chain verification (FR-M10-09): correctness, first-divergent naming,
and the 100k-entry performance floor.

The perf test bulk-loads a 100,000-entry chain (single transaction,
reference hashing) and times Ledger.verify(). It always runs in CI; the
assertion is a generous-but-real floor so genuinely slow machines are not
flaky, and the measured rate plus the FR-M10-09 <5 s verdict is reported.
"""

from __future__ import annotations

import os
import time

import pytest

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    apply_migrations,
    connect,
    entry_hash,
    GENESIS_HASH,
    make_verify_hasher,
)

PERF_ENTRY_COUNT = 100_000
# Generous floor: ~2.3x slower than the development machine still passes,
# while any algorithmic regression (per-row sorting reintroduced, hash
# recomputed through dict copies, etc.) fails loudly.
PERF_MIN_ENTRIES_PER_S = 12_000

# The `perf` marker keeps this out of the parallel suite, which is the first
# line of defence and the important one. This is the second: three sibling
# budgets elsewhere in this suite stand down when MERIDIAN_PERF_REPORT_ONLY
# says the runner is sharing the machine, and this one did not honour the
# same switch. A flag that some budgets obey and others ignore is worse than
# no flag: it invites someone to set it, see a timing failure anyway, and
# conclude the number means something when it only means the machine was
# busy.
#
# The measurement is always taken and always printed. Only the assertion
# stands down, and only on request; the CI perf job sets nothing and so
# enforces the floor on a serial runner.
_PERF_REPORT_ONLY = os.environ.get("MERIDIAN_PERF_REPORT_ONLY") == "1"

BASE_ENTRY = {
    "ts_utc": "2026-09-01T00:00:00.000001Z",
    "story_id": "EDB-12345",
    "phase": "build",
    "loop_id": "L2-task",
    "loop_iteration": 1,
    "actor_id": "developer-agent",
    "actor_version": "0.0.1",
    "actor_kind": "role",
    "policy_version": "policy-v1",
    "action_type": "diff",
    "simulated": 0,
    "vendor": "meridian",
    "observation_confidence": "direct",
    "confidence": 0.9,
    "cost_usd": 1.5,
}


def make_entry(seq: int, ts: str = "2026-09-01T00:00:00.000001Z") -> dict:
    return {**BASE_ENTRY, "seq": seq, "ts_utc": ts}


@pytest.fixture()
def ledger(tmp_path):
    with Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()) as led:
        yield led


def _append(ledger: Ledger, seq: int, **extra):
    return ledger.append(make_entry(seq, **extra))


class TestVerify:
    def test_clean_chain_verifies(self, ledger):
        _append(ledger, 1)
        _append(ledger, 2)
        result = ledger.verify()
        assert result.ok
        assert result.entries_checked == 2
        assert result.first_divergent_sequence is None

    def test_empty_ledger_verifies(self, tmp_path):
        with Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()) as led:
            result = led.verify()
            assert result.ok and result.entries_checked == 0

    def test_corrupted_payload_names_the_sequence(self, ledger):
        _append(ledger, 1)
        _append(ledger, 2)
        _append(ledger, 3)
        # An attacker with file access drops the trigger and edits a row;
        # verification must name exactly this sequence.
        ledger.conn.execute("DROP TRIGGER ledger_entry_no_update")
        ledger.conn.execute(
            "UPDATE ledger_entry SET confidence = 0.42 WHERE seq = 2"
        )
        ledger.conn.commit()
        result = ledger.verify()
        assert not result.ok
        assert result.first_divergent_sequence == 2
        assert result.entries_checked == 1

    def test_corrupted_prev_hash_detected(self, ledger):
        _append(ledger, 1)
        _append(ledger, 2)
        ledger.conn.execute("DROP TRIGGER ledger_entry_no_update")
        ledger.conn.execute(
            "UPDATE ledger_entry SET prev_hash ="
            " CAST(x'11' || substr(prev_hash, 2) AS BLOB) WHERE seq = 2"
        )
        ledger.conn.commit()
        result = ledger.verify()
        assert not result.ok
        assert result.first_divergent_sequence == 2

    def test_sequence_gap_detected(self, ledger):
        _append(ledger, 1)
        _append(ledger, 2)
        _append(ledger, 3)
        ledger.conn.execute("DROP TRIGGER ledger_entry_no_delete")
        # Removing a MIDDLE entry creates a gap at seq 2. (Deleting a
        # trailing entry is an honest prefix — verify must still pass.)
        ledger.conn.execute("DELETE FROM ledger_entry WHERE seq = 2")
        ledger.conn.commit()
        result = ledger.verify()
        assert not result.ok
        assert result.first_divergent_sequence == 2

    def test_appended_entry_invalidates_prior_verify(self, ledger):
        _append(ledger, 1)
        first = ledger.verify()
        assert first.ok and first.entries_checked == 1
        _append(ledger, 2)
        assert ledger.verify().entries_checked == 2

    def test_verify_runs_at_open(self, tmp_path):
        ledger_dir = tmp_path / "ledger"
        with Ledger(ledger_dir, EphemeralSigningKeyProvider()) as led:
            _append(led, 1)
            assert led.last_verify is None  # nothing to verify yet
        with Ledger(ledger_dir, EphemeralSigningKeyProvider()) as led:
            assert led.last_verify is not None and led.last_verify.ok
            assert led.last_verify.entries_checked == 1


class TestFastHasherAgreement:
    def test_precompiled_hasher_matches_reference_implementation(self, ledger):
        _append(ledger, 1)
        _append(ledger, 2)
        columns = [row[1] for row in ledger.conn.execute("PRAGMA table_info(ledger_entry)")]
        hasher = make_verify_hasher(columns)
        cursor = ledger.conn.execute("SELECT * FROM ledger_entry ORDER BY seq")
        prev = GENESIS_HASH
        for values in cursor.fetchall():
            row = dict(zip(columns, values))
            assert hasher(prev, values) == entry_hash(prev, row)
            assert hasher(prev, values) == row["entry_hash"]
            prev = row["entry_hash"]


@pytest.mark.perf
class TestVerifyPerformance:
    def _bulk_load(self, ledger_dir, count: int) -> None:
        """Build `count` chained rows in one transaction (not via append:
        the perf subject is verify(), not insert throughput)."""
        ledger_dir.mkdir(parents=True, exist_ok=True)
        conn = connect(ledger_dir / "ledger.db")
        apply_migrations(conn)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(ledger_entry)")]
        prev = GENESIS_HASH
        batch = []
        for seq in range(1, count + 1):
            # Every column participates in the hash (NULL -> null), exactly
            # as Ledger.append writes it.
            row = {c: None for c in columns}
            row.update(BASE_ENTRY, seq=seq, prev_hash=prev)
            row["entry_hash"] = entry_hash(prev, row)
            prev = row["entry_hash"]
            batch.append(tuple(row.get(c) for c in columns))
            if len(batch) == 5000:
                conn.executemany(
                    f"INSERT INTO ledger_entry ({', '.join(columns)})"
                    f" VALUES ({', '.join('?' for _ in columns)})",
                    batch,
                )
                batch = []
        if batch:
            conn.executemany(
                f"INSERT INTO ledger_entry ({', '.join(columns)})"
                f" VALUES ({', '.join('?' for _ in columns)})",
                batch,
            )
        conn.commit()
        conn.close()

    def test_parallel_and_inline_agree_on_first_divergent(self, tmp_path):
        ledger_dir = tmp_path / "ledger"
        count = 25_000  # above _PARALLEL_VERIFY_MIN
        self._bulk_load(ledger_dir, count)
        with Ledger(
            ledger_dir, EphemeralSigningKeyProvider(), verify_on_open=False
        ) as led:
            led.conn.execute("DROP TRIGGER ledger_entry_no_update")
            led.conn.execute(
                "UPDATE ledger_entry SET confidence = 0.42 WHERE seq = 12345"
            )
            led.conn.commit()
            inline = led.verify(workers=1)
            parallel = led.verify()  # auto: parallel at this size
        assert not inline.ok and inline.first_divergent_sequence == 12345
        assert not parallel.ok
        assert parallel.first_divergent_sequence == inline.first_divergent_sequence
        assert parallel.entries_checked == inline.entries_checked

    def test_verify_100k_under_budget(self, tmp_path):
        ledger_dir = tmp_path / "ledger"
        self._bulk_load(ledger_dir, PERF_ENTRY_COUNT)
        with Ledger(
            ledger_dir,
            EphemeralSigningKeyProvider(),
            verify_on_open=False,  # measure verify() itself
        ) as led:
            assert led.last_sequence == PERF_ENTRY_COUNT
            start = time.perf_counter()
            result = led.verify()
            elapsed = time.perf_counter() - start
        assert result.ok, result.detail
        rate = result.entries_checked / elapsed
        print(
            f"\nFR-M10-09 100k verify: {elapsed:.2f}s "
            f"({rate:,.0f} entries/s) — "
            f"<5s target {'MET' if elapsed < 5 else 'MISSED on this machine'}"
            + (" [reported only, shared runner]" if _PERF_REPORT_ONLY else "")
        )
        # `result.ok` above is asserted on every runner: the chain either
        # verifies or it does not, and that is not a question about speed.
        if not _PERF_REPORT_ONLY:
            assert rate >= PERF_MIN_ENTRIES_PER_S, (
                f"verify too slow: {rate:,.0f} entries/s "
                f"(floor {PERF_MIN_ENTRIES_PER_S:,})"
            )
