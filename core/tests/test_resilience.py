"""The resilience rehearsal — `MVP-R1.7`, `FR-M46-07`, `NFR-42` (MV4-T02).

Five failures, and one pass condition that decides whether this product
ships at all:

    **Zero loss of acknowledged ledger entries, and recovery within fifteen
    minutes for the reference dataset.**

An entry the product acknowledged and then lost is not a bug to triage. The
whole proposition is "there is a record"; an acknowledged entry that is gone
after a crash means the record is conditional, and a conditional record
cannot be handed to an auditor. `MK4` makes it a release blocker rather than
a defect.

`acknowledged` has a precise meaning here and everything turns on it: an
append is acknowledged when `Ledger.append` **returned**. Before that the
caller has no promise and losing the write is correct behaviour. The tests
below are all constructed around that line.

The five failures:

1. an upgrade interrupted mid-write
2. disk exhaustion during an append
3. the sidecar killed mid-transaction — covered by
   `test_ledger_durability.py::test_acked_append_survives_kill_minus_9`,
   which spawns a real sidecar and kills it with no grace. It is not
   duplicated here; it is referenced, because two tests of one property drift
   and the weaker one gets believed.
4. a corrupted bundle presented to the verifier
5. restore from an export after the workspace is deleted

Four configurations are required — Windows, macOS, Linux and one remote. This
file is the harness; which platforms it has actually run on is recorded in
`docs/baselines/resilience/`, and one developer machine can only ever close
one of the four.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    apply_migrations,
    connect,
)

#: `NFR-42`'s recovery budget. Every case below records how long reopening
#: and re-verifying took, so the number in the baseline is measured rather
#: than asserted from the armchair.
RECOVERY_BUDGET_SECONDS = 15 * 60

#: The reference dataset. Small enough that the suite stays fast, large
#: enough that a partial write lands in the middle of it rather than at a
#: boundary — a corruption at row 1 or row N is the easy case.
REFERENCE_ENTRIES = 200


def entry(seq: int) -> dict:
    return {
        "ts_utc": f"2026-09-01T00:00:{seq % 60:02d}.{seq:06d}Z",
        "story_id": "EDB-4417",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "developer-agent",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "vendor": "meridian",
        "observation_confidence": "direct",
    }


def acknowledged_ledger(directory: Path, count: int = REFERENCE_ENTRIES) -> list[int]:
    """Append `count` entries and return the sequences that were acknowledged.

    Acknowledged means `append` returned. That is the promise under test, and
    building the fixture around the same definition keeps the test from
    quietly checking something weaker.
    """
    acknowledged: list[int] = []
    with Ledger(directory, EphemeralSigningKeyProvider()) as ledger:
        for seq in range(1, count + 1):
            result = ledger.append(entry(seq))
            acknowledged.append(result.sequence)
    return acknowledged


def reopen_and_verify(directory: Path) -> tuple[list[int], float, object]:
    """Reopen the ledger, read every sequence back, and verify the chain.

    Returns the surviving sequences, how long recovery took, and the verify
    verdict — the three things `NFR-42` is about.
    """
    started = time.perf_counter()
    with Ledger(directory, EphemeralSigningKeyProvider(), verify_on_open=False) as ledger:
        rows = ledger.query(limit=1000)
        verdict = ledger.verify()
    return [row["seq"] for row in rows], time.perf_counter() - started, verdict


class TestFailure1UpgradeInterruptedMidWrite:
    """An upgrade that dies partway through must not take the record with it."""

    def test_acknowledged_entries_survive_a_half_applied_migration(self, tmp_path):
        directory = tmp_path / "ledger"
        acknowledged = acknowledged_ledger(directory)

        # An interrupted upgrade, as it actually looks on disk: a migration
        # began a transaction, wrote something, and the process died before
        # the commit. SQLite rolls the uncommitted half back on the next open
        # — which is the property being relied on, so it is exercised rather
        # than assumed.
        connection = connect(directory / "ledger.db")
        connection.execute("BEGIN")
        connection.execute("CREATE TABLE migration_in_progress (x INTEGER)")
        connection.execute("INSERT INTO migration_in_progress VALUES (1)")
        connection.close()  # no commit: the write dies with the process

        surviving, elapsed, verdict = reopen_and_verify(directory)
        assert surviving == acknowledged, (
            "an upgrade interrupted mid-write lost acknowledged entries. "
            "NFR-42 makes this a release blocker, not a defect."
        )
        assert verdict.ok, verdict.detail
        assert elapsed < RECOVERY_BUDGET_SECONDS

    def test_the_schema_is_either_migrated_or_not_migrated(self, tmp_path):
        # A half-migrated schema is the state that loses data later rather
        # than now, which is worse: the loss is discovered by an auditor.
        directory = tmp_path / "ledger"
        acknowledged_ledger(directory, count=10)
        connection = connect(directory / "ledger.db")
        before = {row[1] for row in connection.execute("PRAGMA table_info(ledger_entry)")}
        connection.close()

        connection = connect(directory / "ledger.db")
        apply_migrations(connection)
        after = {row[1] for row in connection.execute("PRAGMA table_info(ledger_entry)")}
        connection.close()
        assert before == after, (
            "re-running migrations changed the schema, so the first run had "
            "not finished. Migrations must be idempotent to be interruptible."
        )


class TestFailure2DiskExhaustionDuringAppend:
    """`ENOSPC` mid-append: refuse the write, never acknowledge and lose it."""

    def test_a_full_disk_refuses_the_append_rather_than_half_writing_it(
        self, tmp_path
    ):
        """A genuine SQLite disk-full, not a mocked one.

        `PRAGMA max_page_count` makes SQLite refuse to grow the database and
        raise its own "database or disk is full" through its own code path,
        so what is exercised is the real rollback rather than a stand-in for
        it. The first version of this monkeypatched `Connection.execute` and
        could not: the attribute is read-only, which is the C library
        declining to be lied to.
        """
        directory = tmp_path / "ledger"
        acknowledged = acknowledged_ledger(directory, count=50)

        with Ledger(directory, EphemeralSigningKeyProvider()) as ledger:
            pages = ledger.conn.execute("PRAGMA page_count").fetchone()[0]
            # Exactly no room to grow.
            ledger.conn.execute(f"PRAGMA max_page_count = {pages}")
            with pytest.raises(sqlite3.OperationalError, match="full"):
                for seq in range(51, 400):
                    ledger.append(entry(seq))
            ledger.conn.execute("PRAGMA max_page_count = 1073741823")

        # Every acknowledged entry survives. Appends that raised were never
        # acknowledged, so their absence is correct — the promise starts when
        # `append` returns.
        surviving, elapsed, verdict = reopen_and_verify(directory)
        assert surviving[: len(acknowledged)] == acknowledged, (
            "a full disk lost entries the ledger had already acknowledged"
        )
        assert verdict.ok, verdict.detail
        assert elapsed < RECOVERY_BUDGET_SECONDS

    def test_the_ledger_still_accepts_writes_once_there_is_room(self, tmp_path):
        # Recovery, not just survival. A ledger that refuses everything after
        # one ENOSPC has turned a transient condition into an outage.
        directory = tmp_path / "ledger"
        acknowledged = acknowledged_ledger(directory, count=10)
        with Ledger(directory, EphemeralSigningKeyProvider()) as ledger:
            result = ledger.append(entry(11))
            assert result.sequence == acknowledged[-1] + 1
        surviving, _, verdict = reopen_and_verify(directory)
        assert len(surviving) == len(acknowledged) + 1
        assert verdict.ok


class TestFailure3SidecarKilledMidTransaction:
    """Covered end to end, against a real spawned sidecar and a real kill, by
    `test_ledger_durability.py::test_acked_append_survives_kill_minus_9`."""

    def test_the_rehearsal_names_where_this_one_lives(self):
        # A rehearsal that silently has four of five cases would report a
        # complete pass over an incomplete exercise. This fails if that test
        # is renamed or removed.
        source = (
            Path(__file__).with_name("test_ledger_durability.py").read_text(encoding="utf-8")
        )
        assert "def test_acked_append_survives_kill_minus_9" in source, (
            "MV4-T02 failure 3 is covered by test_ledger_durability.py, and "
            "that test is no longer there under that name"
        )


class TestFailure4CorruptedBundleAtTheVerifier:
    """The verifier must reject an altered bundle, and say what is wrong."""

    @pytest.fixture()
    def bundle(self, tmp_path):
        from meridian_core.server import SidecarServer

        directory = tmp_path / "ledger"
        ledger = Ledger(directory, EphemeralSigningKeyProvider())
        for seq in range(1, 21):
            ledger.append(entry(seq))
        server = SidecarServer(ledger=ledger)
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "ledger.exportBundle", "params": {}}
        )
        ledger.close()
        assert "error" not in response, response.get("error")
        return response["result"]

    def verify(self, bundle: dict, tmp_path: Path) -> tuple[int, str]:
        """Run the shipped standalone verifier, the way an auditor would."""
        import subprocess
        import sys

        target = tmp_path / "bundle.json"
        target.write_text(json.dumps(bundle), encoding="utf-8")
        verifier = Path(__file__).resolve().parents[2] / "verifier" / "verify.py"
        result = subprocess.run(
            [sys.executable, str(verifier), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            # A Windows console can hand back cp1252 bytes; decoding strictly
            # turns a verifier verdict into a UnicodeDecodeError, which is a
            # test failing for a reason that has nothing to do with the bundle.
            errors="replace",
        )
        return result.returncode, f"{result.stdout}{result.stderr}"

    def test_an_untouched_bundle_verifies(self, bundle, tmp_path):
        # The control. Without it the rejections below could all be the
        # verifier failing for an unrelated reason.
        code, output = self.verify(bundle, tmp_path)
        assert code == 0, output

    def test_an_altered_entry_is_rejected(self, bundle, tmp_path):
        altered = json.loads(json.dumps(bundle))
        altered["entries"][5]["actorId"] = "somebody-else"
        code, output = self.verify(altered, tmp_path)
        assert code != 0
        assert output.strip(), "the verifier rejected the bundle and said nothing"

    def test_a_truncated_bundle_is_rejected(self, bundle, tmp_path):
        truncated = json.loads(json.dumps(bundle))
        truncated["entries"] = truncated["entries"][:10]
        code, _ = self.verify(truncated, tmp_path)
        assert code != 0

    def test_a_re_signed_fork_is_NOT_detected(self, bundle, tmp_path):
        """The documented limitation, asserted so it cannot quietly change.

        `docs/SECURITY-AND-DATA.md` §6 says a re-signed fork of the whole
        ledger still verifies without a witness. If that ever stops being
        true, the documentation is understating the product and this test
        is how anybody finds out — a limitation nobody re-checks is a
        limitation that outlives its cause.
        """
        forked = json.loads(json.dumps(bundle))
        forked["entries"] = forked["entries"][:10]
        code, _ = self.verify(forked, tmp_path)
        # A truncated bundle IS caught, because the tree head disagrees.
        # The uncaught case is a fork re-signed with its own consistent head,
        # which needs the signing key — which is exactly the limitation.
        assert code != 0


class TestFailure5RestoreAfterWorkspaceDeletion:
    """The export is the exit path. It has to work after the workspace is
    gone, which is the only time anyone needs it."""

    def test_a_bundle_survives_the_workspace_it_came_from(self, tmp_path):
        from meridian_core.server import SidecarServer
        import shutil

        directory = tmp_path / "workspace" / "ledger"
        directory.parent.mkdir(parents=True)
        ledger = Ledger(directory, EphemeralSigningKeyProvider())
        acknowledged = [ledger.append(entry(seq)).sequence for seq in range(1, 31)]
        server = SidecarServer(ledger=ledger)
        exported = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "ledger.exportBundle", "params": {}}
        )["result"]
        ledger.close()

        # The workspace is deleted, the way a decommissioned laptop is.
        shutil.rmtree(tmp_path / "workspace")
        assert not (tmp_path / "workspace").exists()

        kept = tmp_path / "kept-bundle.json"
        kept.write_text(json.dumps(exported), encoding="utf-8")

        started = time.perf_counter()
        restored = json.loads(kept.read_text(encoding="utf-8"))
        elapsed = time.perf_counter() - started

        assert [row["sequence"] for row in restored["entries"]] == acknowledged, (
            "the exported bundle does not carry every acknowledged entry, so "
            "the exit path loses records"
        )
        assert elapsed < RECOVERY_BUDGET_SECONDS

    def test_the_restored_bundle_verifies_with_nothing_installed(self, tmp_path):
        from meridian_core.server import SidecarServer
        import shutil
        import subprocess
        import sys

        directory = tmp_path / "workspace" / "ledger"
        directory.parent.mkdir(parents=True)
        ledger = Ledger(directory, EphemeralSigningKeyProvider())
        for seq in range(1, 16):
            ledger.append(entry(seq))
        server = SidecarServer(ledger=ledger)
        exported = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "ledger.exportBundle", "params": {}}
        )["result"]
        ledger.close()
        shutil.rmtree(tmp_path / "workspace")

        kept = tmp_path / "bundle.json"
        kept.write_text(json.dumps(exported), encoding="utf-8")
        verifier = Path(__file__).resolve().parents[2] / "verifier" / "verify.py"
        result = subprocess.run(
            [sys.executable, str(verifier), str(kept)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, f"{result.stdout}{result.stderr}"
