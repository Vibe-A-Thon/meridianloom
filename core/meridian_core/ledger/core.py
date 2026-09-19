"""The Ledger facade: append with hash-chain + Merkle + signed tree heads.

FR-M10-02: every entry chains `prev_hash -> entry_hash`.
FR-M10-03: a Merkle tree (frontier) is maintained over entries; roots
are reproducible as RFC 6962 tree hashes.
FR-M10-04: signed tree heads are emitted at a configurable cadence
(default: every 100 entries or 10 minutes), Ed25519 over the canonical
head, key memory-resident (keys.py).
FR-M10-08: append commits (WAL, synchronous=FULL) before returning —
see tests for the kill -9 durability proof.

Query/verify/proof/export surfaces land in later tasks (FR-M10-09/12,
FR-M11-01..05) and hang off this class.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

logger = logging.getLogger("meridian_core.ledger")

from . import canonical, keys, merkle, schema
from .blobs import BlobStore
from .keystore import (
    BlobKeyStore,
    WrappedBlobKeyStore,
    derive_blob_master_key,
    key_id_for,
)
from .redaction import redact_secrets

# Columns that must be present in every append() call (NOT NULL, no default).
REQUIRED_FIELDS = frozenset(
    {
        "story_id",
        "phase",
        "loop_id",
        "loop_iteration",
        "actor_id",
        "actor_version",
        "actor_kind",
        "policy_version",
        "action_type",
    }
)

DEFAULTS: dict[str, Any] = {
    "vendor": "meridian",
    "observation_confidence": "direct",
    "simulated": 0,
}

TREE_HEAD_INTERVAL_ENTRIES = 100
TREE_HEAD_MAX_AGE_S = 600

#: Ledgers at or above this size verify across worker processes (FR-M10-09).
_PARALLEL_VERIFY_MIN = 20_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class AppendResult:
    sequence: int
    ts_utc: str
    prev_hash: bytes
    entry_hash: bytes
    tree_head: dict[str, Any] | None


@dataclass(frozen=True)
class VerifyResult:
    """FR-M10-09 verdict. `first_divergent_sequence` names the first
    sequence number where the chain stops matching the stored rows."""

    ok: bool
    entries_checked: int
    first_divergent_sequence: int | None
    detail: str


class Ledger:
    """An open ledger database. Not thread-safe; the sidecar serialises."""

    def __init__(
        self,
        ledger_dir: Path,
        signing_key: keys.SigningKeyProvider,
        *,
        tree_head_interval: int = TREE_HEAD_INTERVAL_ENTRIES,
        tree_head_max_age_s: float = TREE_HEAD_MAX_AGE_S,
        blob_key_store: BlobKeyStore | None = None,
        verify_on_open: bool = True,
    ) -> None:
        self.dir = Path(ledger_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._signing_key = signing_key
        self._tree_head_interval = tree_head_interval
        self._tree_head_max_age_s = tree_head_max_age_s
        self.conn = schema.connect(self.dir / "ledger.db")
        schema.apply_migrations(self.conn)

        # FR-M10-07: blobs live beside the database; per-subject keys come
        # from the wrapped registry unless a caller injects a store (tests).
        self._blob_keys = blob_key_store or WrappedBlobKeyStore(
            self.conn,
            derive_blob_master_key(
                signing_key.private_key().private_bytes_raw()
            ),
        )
        self._blobs = BlobStore(self.dir / "blobs", self._blob_keys)

        self._columns: tuple[str, ...] = tuple(
            row[1]
            for row in self.conn.execute("PRAGMA table_info(ledger_entry)")
        )
        unknown_hashable = canonical.HASH_EXCLUDED_COLUMNS - set(self._columns)
        if unknown_hashable:
            raise RuntimeError(f"schema drift: {unknown_hashable} not in table")

        self._frontier = merkle.MerkleFrontier()
        last = self.conn.execute(
            "SELECT seq, entry_hash FROM ledger_entry ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self._last_seq: int = last[0] if last else 0
        self._last_hash: bytes = last[1] if last else canonical.GENESIS_HASH
        for (entry_hash,) in self.conn.execute(
            "SELECT entry_hash FROM ledger_entry ORDER BY seq"
        ):
            self._frontier.append(entry_hash)

        head = self.conn.execute(
            "SELECT seq FROM tree_head ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self._last_head_seq: int = head[0] if head else 0
        self._head_opened_monotonic = time.monotonic()

        # FR-M10-09: verification runs when the ledger opens (sidecar
        # start) and on demand; a failure is logged, never fatal.
        self.last_verify: VerifyResult | None = None
        if verify_on_open and self._last_seq:
            self.last_verify = self.verify()
            if not self.last_verify.ok:
                logger.error(
                    "ledger chain verification failed at open: %s",
                    self.last_verify.detail,
                )

    # -- state -------------------------------------------------------------

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @property
    def last_sequence(self) -> int:
        return self._last_seq

    @property
    def signing_public_key(self) -> bytes:
        return keys.public_key_bytes(self._signing_key.private_key())

    def sign(self, data: bytes) -> bytes:
        """Sign arbitrary bytes with the ledger key (audit-bundle block)."""
        return self._signing_key.private_key().sign(data)

    def root_hash(self) -> bytes:
        return self._frontier.root()

    # -- verification (FR-M10-09) -------------------------------------------

    def verify(
        self, up_to: int | None = None, workers: int | None = None
    ) -> VerifyResult:
        """Recompute the chain from genesis; name the first divergence.

        Large ledgers verify in parallel: worker processes each check a
        contiguous range against the stored chain over their own
        read-only connection (no row data crosses process boundaries),
        and this process checks the boundary linkage. Runs on the main
        connection when `workers` is 1 or the ledger is small.
        """
        ceiling = up_to if up_to is not None else self._last_seq
        if ceiling <= 0:
            return VerifyResult(True, 0, None, "chain verified through sequence 0")
        cpu = os.cpu_count() or 1
        worker_count = 1 if workers is None else max(1, workers)
        if workers is None:
            worker_count = min(4, cpu) if ceiling >= _PARALLEL_VERIFY_MIN else 1
        if worker_count <= 1:
            return self._verify_inline(up_to)
        return self._verify_parallel(ceiling, worker_count)

    def _verify_inline(self, up_to: int | None) -> VerifyResult:
        if up_to is None:
            cursor = self.conn.execute("SELECT * FROM ledger_entry ORDER BY seq")
        else:
            cursor = self.conn.execute(
                "SELECT * FROM ledger_entry WHERE seq <= ? ORDER BY seq", (up_to,)
            )
        cursor.arraysize = 10000
        columns = [d[0] for d in cursor.description]
        hasher = canonical.make_verify_hasher(columns)
        index_seq = columns.index("seq")
        index_prev = columns.index("prev_hash")
        index_hash = columns.index("entry_hash")

        expected_seq = 1
        expected_prev = canonical.GENESIS_HASH
        checked = 0
        while True:
            batch = cursor.fetchmany(10000)
            if not batch:
                break
            for values in batch:
                seq = values[index_seq]
                if seq != expected_seq:
                    return VerifyResult(
                        False,
                        checked,
                        expected_seq,
                        f"sequence gap: expected {expected_seq}, found {seq}",
                    )
                if values[index_prev] != expected_prev:
                    return VerifyResult(
                        False,
                        checked,
                        seq,
                        f"prev_hash of sequence {seq} does not match the"
                        " previous entry_hash",
                    )
                recomputed = hasher(expected_prev, values)
                if recomputed != values[index_hash]:
                    return VerifyResult(
                        False,
                        checked,
                        seq,
                        f"entry_hash of sequence {seq} does not match the"
                        " recomputed canonical hash",
                    )
                expected_prev = recomputed
                expected_seq += 1
                checked += 1
        return VerifyResult(
            True, checked, None, f"chain verified through sequence {checked}"
        )

    def _verify_parallel(self, ceiling: int, worker_count: int) -> VerifyResult:
        from concurrent.futures import ProcessPoolExecutor

        from .range_verify import verify_range

        # Contiguous, gap-free ranges over 1..ceiling.
        per = ceiling // worker_count
        ranges: list[tuple[int, int]] = []
        lo = 1
        for _ in range(worker_count):
            hi = lo + per - 1 if len(ranges) < worker_count - 1 else ceiling
            ranges.append((lo, hi))
            lo = hi + 1
        db_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2])

        results: list[tuple[bool, int | None, int, bytes]] = []
        with ProcessPoolExecutor(max_workers=worker_count) as pool:
            for result in pool.map(
                verify_range, [(db_path, lo, hi) for lo, hi in ranges]
            ):
                results.append(result)

        expected_prev = canonical.GENESIS_HASH
        checked = 0
        for (lo, hi), (ok, divergent, count, last_computed) in zip(ranges, results):
            # Boundary: the range's link-in must be where our chain is.
            link = self.conn.execute(
                "SELECT prev_hash FROM ledger_entry WHERE seq = ?", (lo,)
            ).fetchone()
            if link is None:
                return VerifyResult(
                    False, checked, lo, f"sequence gap at range start {lo}"
                )
            if link[0] != expected_prev:
                return VerifyResult(
                    False,
                    checked,
                    lo,
                    f"prev_hash of sequence {lo} does not match the"
                    " previous entry_hash",
                )
            if not ok:
                return VerifyResult(
                    False,
                    checked + max(0, (divergent or lo) - lo),
                    divergent,
                    f"entry_hash of sequence {divergent} does not match the"
                    " recomputed canonical hash",
                )
            checked += count
            expected_prev = last_computed
        return VerifyResult(
            True, checked, None, f"chain verified through sequence {checked}"
        )

    # -- append (FR-M10-02/07/08) -------------------------------------------

    def append(self, entry: dict[str, Any]) -> AppendResult:
        """Append one entry; the chain update is committed before returning.

        `entry` carries the normative columns. Two conveniences on top:
        `input` / `output` (str or bytes) are secret-redacted (SEC-07),
        encrypted and content-addressed into the blob store before the row
        is written; `blob_subject` selects the per-subject key (defaults
        to the caller-supplied `blob_key_id`, else "default").
        """
        return self.append_many([entry])[0]

    def append_many(
        self, entries: Sequence[Mapping[str, Any]]
    ) -> list[AppendResult]:
        """Append a batch in ONE transaction (FR-M41-11 ingestion batches):

        every row lands or none does, so a mid-batch failure cannot leave
        a half-ingested batch behind. Each entry is hashed and linked
        exactly as :meth:`append` would link it — the batch is a
        performance shape, never a different chain."""
        prepared: list[dict[str, Any]] = []
        for entry in entries:
            row_entry = dict(entry)
            input_data = row_entry.pop("input", None)
            output_data = row_entry.pop("output", None)
            blob_subject = row_entry.pop("blob_subject", None)
            row = self._prepare_row(row_entry)
            if input_data is not None or output_data is not None:
                self._attach_blobs(row, input_data, output_data, blob_subject)
            prepared.append(row)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            results = self._insert_rows(prepared)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        head = self._maybe_emit_tree_head()
        if head is not None and results:
            # Cadence preserved: the batch's last result carries the head
            # exactly as a same-tip single append would.
            results[-1] = dataclasses.replace(results[-1], tree_head=head)
        return results

    def _insert_rows(self, rows: list[dict[str, Any]]) -> list[AppendResult]:
        """Insert prepared rows into the open transaction. The caller
        holds the BEGIN IMMEDIATE (append_many, or the event ingester
        writing ledger rows and its ingest state atomically)."""
        results: list[AppendResult] = []
        for row in rows:
            prev_hash = self._last_hash
            row.update(
                seq=self._last_seq + 1,
                ts_utc=row.get("ts_utc") or utc_now(),
                prev_hash=prev_hash,
            )
            row["entry_hash"] = canonical.entry_hash(prev_hash, row)
            columns = list(row)
            self.conn.execute(
                f"INSERT INTO ledger_entry ({', '.join(columns)})"
                f" VALUES ({', '.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
            self._frontier.append(row["entry_hash"])
            self._last_seq = row["seq"]
            self._last_hash = row["entry_hash"]
            results.append(
                AppendResult(
                    sequence=row["seq"],
                    ts_utc=row["ts_utc"],
                    prev_hash=prev_hash,
                    entry_hash=row["entry_hash"],
                    tree_head=None,  # emitted once, by the committing caller
                )
            )
        return results

    def _attach_blobs(
        self,
        row: dict[str, Any],
        input_data: Any,
        output_data: Any,
        blob_subject: str | None,
    ) -> None:
        if isinstance(input_data, str):
            input_data = redact_secrets(input_data).encode("utf-8")
        if isinstance(output_data, str):
            output_data = redact_secrets(output_data).encode("utf-8")
        key_id = row.get("blob_key_id")
        if key_id is None:
            key_id = self._blob_keys.key_for(blob_subject or "default")
            row["blob_key_id"] = key_id
        for prefix, data in (("input", input_data), ("output", output_data)):
            if data is None:
                continue
            digest, ref = self._blobs.put(data, key_id)
            row[f"{prefix}_digest"] = bytes.fromhex(digest)
            row[f"{prefix}_ref"] = ref

    # -- blobs (FR-M10-07/14) -----------------------------------------------

    def read_blob(self, ref: str, blob_key_id: str) -> bytes:
        """Decrypt a referenced blob; raises when the key was shredded."""
        return self._blobs.get(ref, blob_key_id)

    def shred_subject(self, subject_id: str) -> bool:
        """FR-M10-14 groundwork: destroy a subject's blob key.

        Rows stay, the chain still verifies (it hashes ciphertext), the
        blobs become unreadable. The erasure-event ledger entry lands
        with the full crypto-shredding flow in F4.
        """
        return self._blob_keys.destroy(key_id_for(subject_id))

    # -- query (FR-M10-12, FR-M41-07) -----------------------------------------

    def _scope_clauses(
        self,
        *,
        story_id: str | None = None,
        actor_id: str | None = None,
        vendor: str | None = None,
        action_type: str | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        after_sequence: int | None = None,
    ) -> tuple[str, list[Any]]:
        """The shared WHERE fragment for query/count. FR-M41-07's cursor
        keys on ``seq`` (the gapless primary key): ``after_sequence`` is
        exclusive, so a caller pages by feeding the last returned row's
        sequence back in."""
        clauses: list[str] = []
        arguments: list[Any] = []
        for column, value in (
            ("story_id", story_id),
            ("actor_id", actor_id),
            ("vendor", vendor),
            ("action_type", action_type),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                arguments.append(value)
        if from_sequence is not None:
            clauses.append("seq >= ?")
            arguments.append(from_sequence)
        if to_sequence is not None:
            clauses.append("seq <= ?")
            arguments.append(to_sequence)
        if from_timestamp is not None:
            clauses.append("ts_utc >= ?")
            arguments.append(from_timestamp)
        if to_timestamp is not None:
            clauses.append("ts_utc <= ?")
            arguments.append(to_timestamp)
        if after_sequence is not None:
            clauses.append("seq > ?")
            arguments.append(after_sequence)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, arguments

    def query(
        self,
        *,
        story_id: str | None = None,
        actor_id: str | None = None,
        vendor: str | None = None,
        action_type: str | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Filtered entry stream, ascending by sequence (FR-M11-02).

        FR-M41-07: ``limit`` is a PAGE size (clamped to [1, 1000], the
        default page), never the only bound — a caller walks the full
        history with ``after_sequence`` (exclusive cursor keyed on the
        gapless ``seq``): pass the last row's sequence of one page as the
        next page's ``after_sequence`` until a page comes back short.
        """
        where, arguments = self._scope_clauses(
            story_id=story_id,
            actor_id=actor_id,
            vendor=vendor,
            action_type=action_type,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            after_sequence=after_sequence,
        )
        sql = "SELECT * FROM ledger_entry" + where + " ORDER BY seq LIMIT ?"
        arguments.append(min(max(limit, 1), 1000))
        cursor = self.conn.execute(sql, arguments)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    #: Rows fetched per round trip by :meth:`iter_query`.
    QUERY_PAGE = 1000

    def iter_query(
        self,
        *,
        story_id: str | None = None,
        actor_id: str | None = None,
        vendor: str | None = None,
        action_type: str | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        after_sequence: int | None = None,
        max_rows: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Every matching entry, ascending by sequence — the whole history.

        :meth:`query` returns ONE page (at most 1,000 rows, however large a
        ``limit`` is asked for). A caller that needs *the answer over all of
        history* — is this identity revoked? is a halt in force? which
        subjects were erased? — must not use it: past the first page the
        newer rows are simply absent, and a governance check that cannot see
        the newest halt or revocation fails **open** (audit CLD-B01,
        reproduced: a halt recorded after 1,000 gate rows was invisible).

        This walks the FR-M41-07 ``after_sequence`` cursor to exhaustion.
        ``max_rows`` exists only for callers that genuinely want a bounded
        prefix; it is a total, not a page size.
        """
        cursor_after = after_sequence
        yielded = 0
        while True:
            page = self.query(
                story_id=story_id, actor_id=actor_id, vendor=vendor,
                action_type=action_type, from_sequence=from_sequence,
                to_sequence=to_sequence, from_timestamp=from_timestamp,
                to_timestamp=to_timestamp, after_sequence=cursor_after,
                limit=self.QUERY_PAGE,
            )
            for row in page:
                yield row
                yielded += 1
                if max_rows is not None and yielded >= max_rows:
                    return
            if len(page) < self.QUERY_PAGE:
                return
            cursor_after = page[-1]["seq"]

    def query_all(self, **filters: Any) -> list[dict[str, Any]]:
        """:meth:`iter_query` as a list, for callers that need it in memory."""
        return list(self.iter_query(**filters))

    def count(
        self,
        *,
        story_id: str | None = None,
        actor_id: str | None = None,
        vendor: str | None = None,
        action_type: str | None = None,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> int:
        """Rows matching the same scope filters as :meth:`query` — the
        ``rowsAvailable`` half of the FR-M41-08 coverage disclosure,
        computed in the same operation as the figure (NFR-34)."""
        where, arguments = self._scope_clauses(
            story_id=story_id,
            actor_id=actor_id,
            vendor=vendor,
            action_type=action_type,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        row = self.conn.execute(
            "SELECT COUNT(*) FROM ledger_entry" + where, arguments
        ).fetchone()
        return int(row[0])

    def get_entry(self, sequence: int) -> dict[str, Any] | None:
        """One full row, or None when the sequence does not exist."""
        cursor = self.conn.execute(
            "SELECT * FROM ledger_entry WHERE seq = ?", (sequence,)
        )
        columns = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row is not None else None

    def leaf_hashes(self) -> list[bytes]:
        """All entry hashes in sequence order — Merkle leaves (FR-M10-03)."""
        return [
            row[0]
            for row in self.conn.execute(
                "SELECT entry_hash FROM ledger_entry ORDER BY seq"
            )
        ]

    def _prepare_row(self, entry: dict[str, Any]) -> dict[str, Any]:
        unknown = set(entry) - set(self._columns) - {"ts_utc"}
        if unknown:
            raise ValueError(f"unknown entry fields: {sorted(unknown)}")
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(f"missing required fields: {sorted(missing)}")
        row: dict[str, Any] = {}
        for column in self._columns:
            if column == "seq":
                continue  # assigned at insert time
            value = entry.get(column, DEFAULTS.get(column))
            if column == "simulated" and isinstance(value, bool):
                value = int(value)
            if column == "tool_calls" and value is not None and not isinstance(
                value, str
            ):
                value = json.dumps(value, ensure_ascii=False)
            row[column] = value
        if row["observation_confidence"] not in ("direct", "telemetry", "inferred"):
            raise ValueError("observation_confidence must be direct|telemetry|inferred")
        if row.get("origin") is not None and row["origin"] not in (
            "ui", "command", "omnibar", "chat", "editor", "file", "connector", "api",
        ):
            raise ValueError("origin must be one of the FR-M40-02 doors or null")
        return row

    # -- tree heads (FR-M10-04) ----------------------------------------------

    def latest_tree_head(self) -> dict[str, Any] | None:
        """The most recent signed tree head, as a column dict, or None."""
        cursor = self.conn.execute(
            "SELECT seq, root_hash, signed_at, signature, anchor_ref"
            " FROM tree_head ORDER BY seq DESC LIMIT 1"
        )
        columns = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row is not None else None

    def emit_tree_head_now(self) -> dict[str, Any] | None:
        """Sign and store a head at the current tip (idempotent per seq).

        Used by the tree-head cadence and by ledger.exportBundle, which
        needs a head covering the exported range.
        """
        if self._last_seq == 0 or self._last_head_seq == self._last_seq:
            return None
        signed_at = utc_now()
        root = self._frontier.root()
        signature = keys.sign_tree_head(
            self._signing_key, self._last_seq, root, signed_at
        )
        self.conn.execute(
            "INSERT INTO tree_head (seq, root_hash, signed_at, signature)"
            " VALUES (?, ?, ?, ?)",
            (self._last_seq, root, signed_at, signature),
        )
        self.conn.commit()
        self._last_head_seq = self._last_seq
        self._head_opened_monotonic = time.monotonic()
        return {
            "seq": self._last_seq,
            "rootHash": root.hex(),
            "signedAt": signed_at,
            "signature": signature.hex(),
        }

    def _maybe_emit_tree_head(self) -> dict[str, Any] | None:
        age = time.monotonic() - self._head_opened_monotonic
        due = (
            self._last_seq - self._last_head_seq >= self._tree_head_interval
            or age >= self._tree_head_max_age_s
        )
        if not due:
            return None
        return self.emit_tree_head_now()

    def tree_heads(self) -> list[sqlite3.Row | Any]:
        return self.conn.execute(
            "SELECT seq, root_hash, signed_at, signature, anchor_ref"
            " FROM tree_head ORDER BY seq"
        ).fetchall()
