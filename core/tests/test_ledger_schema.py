"""Tests for the append-only ledger schema (FR-M10-01).

The column list asserted here is the normative §7.2 schema
(Requirements_Final.md / vision.md §6.2) plus the v2.1 merge fields and
the gaps additions; a drift in either direction fails this test.
"""

from __future__ import annotations

import sqlite3

import pytest

from meridian_core.ledger import SCHEMA_VERSION, apply_migrations, connect


@pytest.fixture()
def conn(tmp_path):
    connection = connect(tmp_path / "ledger.db")
    yield connection
    connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def _insert_entry(connection: sqlite3.Connection, seq: int = 1) -> None:
    connection.execute(
        """
        INSERT INTO ledger_entry (
          seq, ts_utc, prev_hash, entry_hash, story_id, phase, loop_id,
          loop_iteration, actor_id, actor_version, actor_kind,
          policy_version, action_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            seq,
            "2026-09-01T00:00:00Z",
            b"\x00" * 32,
            b"\x01" * 32,
            "EDB-12345",
            "build",
            "L2-task",
            1,
            "developer-agent",
            "0.0.1",
            "role",
            "policy-v1",
            "diff",
        ),
    )
    connection.commit()


class TestNormativeSchema:
    def test_ledger_entry_columns_are_exactly_the_normative_set(self, conn):
        apply_migrations(conn)
        assert _columns(conn, "ledger_entry") == [
            # vision.md §6.2 (normative via Requirements_Final.md §7.2)
            "seq", "ts_utc", "prev_hash", "entry_hash",
            "story_id", "phase", "loop_id", "loop_iteration",
            "actor_id", "actor_version", "actor_kind", "policy_version",
            "skill_id", "skill_version", "model_id", "model_version",
            "action_type", "input_digest", "input_ref",
            "output_digest", "output_ref", "tool_calls",
            "confidence", "decision", "human_actor", "rework_reason",
            "tokens_in", "tokens_out", "cost_usd", "latency_ms",
            "signature",
            # v2.1 merge fields (§7.2 note)
            "human_role", "worktree_ref", "repo_id", "replay_of", "blob_key_id",
            # gaps additions (FR-M35-02/03)
            "vendor", "observation_confidence", "external_session_id",
            # FR-M32-02 simulation marker
            "simulated",
            # FR-M40-02 amendment to FR-M10-01 (gaps_initiation.md §5)
            "run_id", "origin",
        ]

    def test_tree_head_columns_match_vision_ddl(self, conn):
        apply_migrations(conn)
        assert _columns(conn, "tree_head") == [
            "seq", "root_hash", "signed_at", "signature", "anchor_ref",
        ]

    def test_new_columns_defaults(self, conn):
        apply_migrations(conn)
        _insert_entry(conn)
        row = conn.execute(
            "SELECT vendor, observation_confidence, external_session_id, simulated"
            " FROM ledger_entry WHERE seq = 1"
        ).fetchone()
        assert row == ("meridian", "direct", None, 0)

    def test_observation_confidence_is_constrained(self, conn):
        apply_migrations(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ledger_entry (seq, ts_utc, prev_hash, entry_hash,"
                " story_id, phase, loop_id, loop_iteration, actor_id,"
                " actor_version, actor_kind, policy_version, action_type,"
                " observation_confidence)"
                " VALUES (1, 't', x'00', x'00', 's', 'p', 'l', 0, 'a', 'v',"
                " 'role', 'pol', 'diff', 'guessed')"
            )


class TestAppendOnlyTriggers:
    def test_update_of_ledger_entry_raises(self, conn):
        apply_migrations(conn)
        _insert_entry(conn)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE ledger_entry SET story_id = 'X' WHERE seq = 1")

    def test_delete_of_ledger_entry_raises(self, conn):
        apply_migrations(conn)
        _insert_entry(conn)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM ledger_entry WHERE seq = 1")

    def test_tree_head_is_append_only_too(self, conn):
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO tree_head (seq, root_hash, signed_at, signature)"
            " VALUES (1, x'00', 't', x'00')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE tree_head SET anchor_ref = 'x' WHERE seq = 1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM tree_head WHERE seq = 1")

    def test_trigger_survives_rollback_and_still_allows_appends(self, conn):
        apply_migrations(conn)
        _insert_entry(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM ledger_entry")
        _insert_entry(conn, seq=2)
        count = conn.execute("SELECT COUNT(*) FROM ledger_entry").fetchone()[0]
        assert count == 2


class TestMigrations:
    def test_migration_is_recorded(self, conn):
        newly = apply_migrations(conn)
        assert newly == [1, 2]
        rows = conn.execute(
            "SELECT version, description FROM schema_migrations"
        ).fetchall()
        assert [row[0] for row in rows] == [1, SCHEMA_VERSION]
        assert "FR-M10-01" in rows[0][1]
        assert "FR-M40-02" in rows[1][1]

    def test_reapply_is_a_noop(self, conn):
        apply_migrations(conn)
        assert apply_migrations(conn) == []

    def test_v1_database_is_upgraded(self, tmp_path):
        """A ledger created at v1 gains run_id/origin via the v2 migration."""
        db = tmp_path / "ledger.db"
        old = connect(db)
        old.execute(
            "CREATE TABLE schema_migrations ("
            " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL,"
            " description TEXT NOT NULL)"
        )
        old.execute(
            "INSERT INTO schema_migrations VALUES (1, 't', 'FR-M10-01: v1')"
        )
        for statement in [
            "CREATE TABLE ledger_entry (seq INTEGER PRIMARY KEY, ts_utc TEXT)",
        ]:
            old.execute(statement)
        old.commit()
        old.close()

        upgraded = connect(db)
        assert apply_migrations(upgraded) == [2]
        cols = _columns(upgraded, "ledger_entry")
        assert "run_id" in cols and "origin" in cols
        upgraded.close()

    def test_origin_is_constrained(self, conn):
        apply_migrations(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ledger_entry (seq, ts_utc, prev_hash, entry_hash,"
                " story_id, phase, loop_id, loop_iteration, actor_id,"
                " actor_version, actor_kind, policy_version, action_type,"
                " origin)"
                " VALUES (1, 't', x'00', x'00', 's', 'p', 'l', 0, 'a', 'v',"
                " 'role', 'pol', 'diff', 'telepathy')"
            )

    def test_migrations_survive_reopen(self, tmp_path):
        db = tmp_path / "ledger.db"
        first = connect(db)
        apply_migrations(first)
        first.close()
        second = connect(db)
        assert apply_migrations(second) == []
        assert "ledger_entry" in {
            row[0]
            for row in second.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        second.close()


class TestDurabilityPragmas:
    def test_wal_and_full_sync(self, conn):
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL

    def test_busy_timeout_set_for_windows_locking(self, conn):
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
