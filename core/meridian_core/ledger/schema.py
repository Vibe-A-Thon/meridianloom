"""FR-M10-01: append-only SQLite schema for the provenance ledger.

The column set is normative: Requirements_Final.md §7.2 (full DDL in
vision.md §6.2) plus the v2.1 merge fields (`human_role`, `worktree_ref`,
`repo_id`, `replay_of`, `blob_key_id`) plus the gaps additions (`vendor`,
`observation_confidence`, `external_session_id` — FR-M35-02/03) and the
`simulated` marker (FR-M32-02).

Append-only is enforced by database triggers that RAISE on UPDATE and
DELETE of `ledger_entry` (and `tree_head`): no code path in this process
or any other can mutate history through SQLite. The sole erasure story is
crypto-shredding (FR-M10-14): blob keys are destroyed, no row is ever
deleted, and the chain still verifies because it hashes ciphertext.

`schema_migrations` records applied versions; FR-M30-03 (migration
doctoring) reads it later. Migrations are append-only rows in
`MIGRATIONS`: (version, description, statements).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 3

# Statement lists (not executescript blobs) so each migration runs inside
# one explicit transaction with its schema_migrations row.
_V1_STATEMENTS = [
    """
    CREATE TABLE ledger_entry (
      seq            INTEGER PRIMARY KEY,   -- monotonic, gapless from 1
      ts_utc         TEXT    NOT NULL,      -- ISO 8601 UTC
      prev_hash      BLOB    NOT NULL,      -- previous entry's entry_hash
      entry_hash     BLOB    NOT NULL,      -- SHA-256 over canonical payload

      story_id       TEXT    NOT NULL,
      phase          TEXT    NOT NULL,
      loop_id        TEXT    NOT NULL,
      loop_iteration INTEGER NOT NULL,

      actor_id       TEXT    NOT NULL,
      actor_version  TEXT    NOT NULL,
      actor_kind     TEXT    NOT NULL,      -- orchestrator|role|stack|sub|xai|meta|external
      policy_version TEXT    NOT NULL,
      skill_id       TEXT,
      skill_version  TEXT,
      model_id       TEXT,
      model_version  TEXT,

      action_type    TEXT    NOT NULL,      -- plan|prompt|tool_call|diff|test_run|
                                            -- review|scan|gate|approval|policy_update|export
      input_digest   BLOB,                  -- SHA-256 of the (encrypted) input blob
      input_ref      TEXT,                  -- blob store path, relative
      output_digest  BLOB,
      output_ref     TEXT,
      tool_calls     TEXT,                  -- JSON array

      confidence     REAL,                  -- self-reported, uncalibrated at capture
      decision       TEXT,                  -- proposed|approved|rejected|reworked
      human_actor    TEXT,                  -- approver identity, when applicable
      rework_reason  TEXT,

      tokens_in      INTEGER,
      tokens_out     INTEGER,
      cost_usd       REAL,
      latency_ms     INTEGER,

      signature      BLOB,                  -- optional per-entry signature

      -- v2.1 merge fields (Requirements_Final.md §7.2)
      human_role     TEXT,                  -- M20
      worktree_ref   TEXT,                  -- M18
      repo_id        TEXT,                  -- M22
      replay_of      INTEGER,               -- source seq for a replay fork (FR-M4-07)
      blob_key_id    TEXT,                  -- per-subject blob key (FR-M10-14)

      -- gaps additions (FR-M35-02/03): external-agent observation
      vendor         TEXT NOT NULL DEFAULT 'meridian',
      observation_confidence TEXT NOT NULL DEFAULT 'direct'
        CHECK (observation_confidence IN ('direct', 'telemetry', 'inferred')),
      external_session_id TEXT,

      -- FR-M32-02: Simulation Core entries are marked, never hidden
      simulated      INTEGER NOT NULL DEFAULT 0 CHECK (simulated IN (0, 1))
    )
    """,
    """
    CREATE TABLE tree_head (
      seq         INTEGER PRIMARY KEY,      -- ledger seq this head covers
      root_hash   BLOB NOT NULL,            -- Merkle root over entries 1..seq
      signed_at   TEXT NOT NULL,
      signature   BLOB NOT NULL,            -- Ed25519 over the canonical head
      anchor_ref  TEXT                      -- external anchor, when configured
    )
    """,
    # Append-only enforcement (FR-M10-01): any UPDATE or DELETE of history
    # aborts, from any connection, including hand-rolled SQL. The
    # crypto-shredding carve-out never touches these tables — it deletes
    # key material, not rows.
    """
    CREATE TRIGGER ledger_entry_no_update
    BEFORE UPDATE ON ledger_entry
    BEGIN
      SELECT RAISE(ABORT, 'FR-M10-01: ledger_entry is append-only; UPDATE is forbidden');
    END
    """,
    """
    CREATE TRIGGER ledger_entry_no_delete
    BEFORE DELETE ON ledger_entry
    BEGIN
      SELECT RAISE(ABORT, 'FR-M10-01: ledger_entry is append-only; DELETE is forbidden');
    END
    """,
    """
    CREATE TRIGGER tree_head_no_update
    BEFORE UPDATE ON tree_head
    BEGIN
      SELECT RAISE(ABORT, 'FR-M10-01: tree_head is append-only; UPDATE is forbidden');
    END
    """,
    """
    CREATE TRIGGER tree_head_no_delete
    BEFORE DELETE ON tree_head
    BEGIN
      SELECT RAISE(ABORT, 'FR-M10-01: tree_head is append-only; DELETE is forbidden');
    END
    """,
    # Query hot paths (FR-M10-12): the Chain Viewer filters on these.
    "CREATE INDEX idx_ledger_entry_story ON ledger_entry (story_id)",
    "CREATE INDEX idx_ledger_entry_actor ON ledger_entry (actor_id)",
    "CREATE INDEX idx_ledger_entry_vendor ON ledger_entry (vendor)",
    "CREATE INDEX idx_ledger_entry_action ON ledger_entry (action_type)",
    "CREATE INDEX idx_ledger_entry_ts ON ledger_entry (ts_utc)",
]

_V2_STATEMENTS = [
    "ALTER TABLE ledger_entry ADD COLUMN run_id TEXT",
    (
        "ALTER TABLE ledger_entry ADD COLUMN origin TEXT"
        " CHECK (origin IN"
        " ('ui', 'command', 'omnibar', 'chat', 'editor', 'file', 'connector', 'api'))"
    ),
]

_V3_STATEMENTS = [
    # NOT append-only by design: erasure (FR-M10-14) destroys wrapped key
    # rows. Raw key material never appears here — only AES-GCM ciphertext.
    """
    CREATE TABLE blob_key (
      key_id      TEXT PRIMARY KEY,         -- e.g. bk:<subject_id>
      subject_id  TEXT NOT NULL UNIQUE,
      wrapped_key BLOB NOT NULL,            -- nonce || AES-GCM(subject key)
      created_at  TEXT NOT NULL
    )
    """,
]

MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "FR-M10-01: §7.2 ledger_entry + tree_head, append-only triggers, "
        "v2.1 fields, vendor/observation_confidence/external_session_id, simulated",
        _V1_STATEMENTS,
    ),
    (
        2,
        "FR-M40-02 amendment to FR-M10-01: run_id and origin columns so "
        "every story traces to how the run started (gaps_initiation.md §5); "
        "origin is written with the run's first entry",
        _V2_STATEMENTS,
    ),
    (
        3,
        "FR-M10-07/FR-M10-14: blob_key registry — per-subject blob keys "
        "wrapped under the workspace master key; deleting a row "
        "crypto-shreds the subject's blobs",
        _V3_STATEMENTS,
    ),
]


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the ledger database with durability and Windows-safe locking.

    WAL + synchronous=FULL: every commit is fsync'd before it returns
    (FR-M10-08 — an acked append survives a kill -9). A 30 s busy timeout
    absorbs the brief writer/reader contention Windows file locking
    produces instead of failing with SQLITE_BUSY.
    """
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Bring the database to SCHEMA_VERSION; return newly applied versions."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version     INTEGER PRIMARY KEY,
          applied_at  TEXT NOT NULL,
          description TEXT NOT NULL
        )
        """
    )
    conn.commit()
    applied = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    newly_applied: list[int] = []
    for version, description, statements in MIGRATIONS:
        if version in applied:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at, description)"
                " VALUES (?, ?, ?)",
                (version, datetime.now(timezone.utc).isoformat(), description),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        newly_applied.append(version)
    return newly_applied
