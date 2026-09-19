"""Reliable event ingestion into the ledger (FR-M41-10/11/12; N1
Workstream C task 16).

FR-M41-10: every imported source event carries a stable deduplication
key, a source offset, an ingest timestamp and a replay status. FR-M41-11:
ingestion is correct under duplicate delivery, out-of-order arrival,
clock skew, process restart, partial files, API pagination, offline
queueing and disk exhaustion — a replayed fixture reconciles exactly,
with no silent loss and no double counting. FR-M41-12 (task 17): anything
intentionally dropped surfaces as a named coverage gap
(:class:`~meridian_core.metrics.coverage.DataGap`), never as an absence.

Design, and why:

* **Every accepted event becomes a ledger entry** — the ledger is the
  system of record, so reconciliation compares the ledger against the
  source stream, not a side table.
* **Ingest state rides the ledger's own SQLite database** (separate
  operational tables — the same precedent as ``blob_key``: not part of
  the append-only ``ledger_entry`` chain) and, critically, in the SAME
  transaction as the ledger rows: :meth:`EventIngester.ingest_batch`
  holds one ``BEGIN IMMEDIATE`` across the ledger inserts, the
  per-event state rows, the checkpoint and the drop counters. A crash
  mid-batch rolls everything back — the batch is re-fed from the
  checkpoint and lands exactly once. Exactly-once is a transaction
  property here, not a hope.
* **The four FR-M41-10 fields** are recorded per event in ``ingest_event``
  (key, offset, ingest timestamp, replay status) bound to the ledger
  sequence the event produced — the event carries them, queryable by
  either side of the mapping.
* **Deduplication is by source key** (FR-M41-10): an event whose key was
  already ingested is DROPPED AND COUNTED as a ``duplicate`` gap — never
  silently, never double-counted into the ledger.
* **Ordering is by source offset, not arrival**: events may arrive
  reordered (offline queueing) or paginated (API pages); the checkpoint
  tracks the high-water offset and reconciliation sorts by offset, so
  arrival order is irrelevant to correctness.
* **Clock skew** is contained by stamping ``ingested_at`` from the
  LOCAL trusted clock at ingest time; a skewed source timestamp in the
  payload is the source's own claim and does not perturb ingest order.
* **Disk exhaustion is a named failure**: a free-space probe runs before
  the batch, and an SQLite ``database or disk is full`` error mid-batch
  is translated — both raise :class:`DiskExhaustedError`, the whole
  batch rolls back, the checkpoint does not advance, and ingestion
  resumes once space returns. It surfaces; it never crashes or
  half-commits.

Zero model calls (FR-M36-07): validation, dedup and counting over rows.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .ledger.core import utc_now
from .metrics.coverage import DataGap

__all__ = [
    "BatchResult",
    "DiskExhaustedError",
    "EventIngester",
    "IngestError",
    "SourceEvent",
]

#: Gap classes this module emits (FR-M41-12 vocabulary — stable strings
#: shared with the envelope's DataGap).
GAP_DUPLICATE = "duplicate"
GAP_UNPARSEABLE = "unparseable"
GAP_EXCLUDED_PATH = "excluded_path"
GAP_UNSUPPORTED_VENDOR = "unsupported_vendor"

#: Reserve the ingester refuses to dip below (bytes) when a free-space
#: probe is configured — a batch may not start with the disk already full.
DEFAULT_DISK_RESERVE_BYTES = 1024 * 1024


class IngestError(Exception):
    """Ingestion failed in a named, recoverable way."""


class DiskExhaustedError(IngestError):
    """FR-M41-11: the disk is (or would become) full. Named, not a crash:
    the batch rolled back whole, the checkpoint did not advance, and the
    caller may retry after freeing space."""


@dataclass(frozen=True)
class SourceEvent:
    """One event of an imported source stream.

    ``key`` is the stable deduplication key (FR-M41-10) — the source's
    own idempotency identity; ``offset`` is the source's monotonic offset
    defining canonical order; ``body`` maps onto the ledger entry's
    normative columns; ``path`` is the optional source path, checked
    against the ingester's excluded prefixes."""

    key: str
    offset: int
    body: Mapping[str, Any]
    path: str | None = None


@dataclass(frozen=True)
class BatchResult:
    """What one :meth:`EventIngester.ingest_batch` call did — the audit
    twin of the batch, returned AND reflected in the persisted state."""

    batchId: str
    source: str
    replay: bool
    ingested: int
    ledgerFrom: int | None  # first ledger sequence of the batch
    ledgerTo: int | None  # last ledger sequence (None when ingested == 0)
    nextOffset: int  # the persisted high-water checkpoint after the batch
    drops: Mapping[str, int] = field(default_factory=dict)  # class -> count

    def to_dict(self) -> dict[str, Any]:
        return {
            "batchId": self.batchId,
            "source": self.source,
            "replay": self.replay,
            "ingested": self.ingested,
            "ledgerFrom": self.ledgerFrom,
            "ledgerTo": self.ledgerTo,
            "nextOffset": self.nextOffset,
            "drops": dict(self.drops),
        }


class EventIngester:
    """Exactly-once event ingestion into a ledger.

    ``source`` names the stream (a connector id, a fixture name) — keys
    and checkpoints are namespaced per source. ``supported_vendors`` /
    ``excluded_path_prefixes`` declare intentional drop policies (each
    drop counted as its named gap, FR-M41-12). ``disk_free_bytes`` is an
    injectable probe (bytes free) for the disk-exhausted path — None
    means "not probeable", and the mid-batch SQLite error translation
    still applies.
    """

    def __init__(
        self,
        ledger,
        *,
        source: str = "default",
        supported_vendors: Sequence[str] | None = None,
        excluded_path_prefixes: Sequence[str] = (),
        disk_free_bytes: Callable[[], int] | None = None,
        disk_reserve_bytes: int = DEFAULT_DISK_RESERVE_BYTES,
        now: Callable[[], str] = utc_now,
    ) -> None:
        self._ledger = ledger
        self._source = str(source)
        self._supported_vendors = (
            None if supported_vendors is None else frozenset(supported_vendors)
        )
        self._excluded = tuple(excluded_path_prefixes)
        self._disk_probe = disk_free_bytes
        self._disk_reserve = int(disk_reserve_bytes)
        self._now = now
        self._ensure_state_tables()

    # -- state schema -----------------------------------------------------

    def _ensure_state_tables(self) -> None:
        # Operational state, deliberately NOT part of the append-only
        # ledger_entry chain (the blob_key precedent): checkpointers and
        # counters are mutable by design.
        self._ledger.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ingest_event (
              source       TEXT NOT NULL,
              source_key   TEXT NOT NULL,
              source_offset INTEGER NOT NULL,
              ledger_seq   INTEGER NOT NULL,
              ingested_at  TEXT NOT NULL,
              batch_id     TEXT NOT NULL,
              replay       TEXT NOT NULL CHECK (replay IN ('live', 'replay')),
              PRIMARY KEY (source, source_key)
            );
            CREATE INDEX IF NOT EXISTS ingest_event_seq
              ON ingest_event (source, ledger_seq);
            CREATE TABLE IF NOT EXISTS ingest_checkpoint (
              source       TEXT PRIMARY KEY,
              next_offset  INTEGER NOT NULL,
              updated_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ingest_drops (
              source     TEXT NOT NULL,
              gap_class  TEXT NOT NULL,
              count      INTEGER NOT NULL,
              PRIMARY KEY (source, gap_class)
            );
            """
        )
        self._ledger.conn.commit()

    # -- reads ------------------------------------------------------------

    def resume_offset(self) -> int:
        """The persisted high-water offset — where a (re)started ingester
        resumes (FR-M41-11 restart): re-feeding from here cannot double
        count; overlapping keys are dropped and counted."""
        row = self._ledger.conn.execute(
            "SELECT next_offset FROM ingest_checkpoint WHERE source = ?",
            (self._source,),
        ).fetchone()
        return int(row[0]) if row else 0

    def gaps(self) -> list[DataGap]:
        """Every named drop this source has accumulated (FR-M41-12), as
        envelope-ready DataGaps — wire into the coverage envelope, never
        report as a silent absence."""
        rows = self._ledger.conn.execute(
            "SELECT gap_class, count FROM ingest_drops WHERE source = ?"
            " ORDER BY gap_class",
            (self._source,),
        ).fetchall()
        return [DataGap(gapClass=str(cls), count=int(count)) for cls, count in rows]

    def replay_status(self, key: str) -> str | None:
        """The recorded replay status ('live' | 'replay') of an ingested
        key, or None when the key is unknown."""
        row = self._ledger.conn.execute(
            "SELECT replay FROM ingest_event WHERE source = ? AND source_key = ?",
            (self._source, str(key)),
        ).fetchone()
        return str(row[0]) if row else None

    # -- the batch --------------------------------------------------------

    def ingest_batch(
        self,
        events: Sequence[SourceEvent],
        *,
        replay: bool = False,
        batch_id: str | None = None,
    ) -> BatchResult:
        """Ingest one batch exactly once (see the module docstring).

        Drops are counted per class and persisted; duplicates and
        policy drops never reach the ledger. The whole batch — ledger
        rows, event state, checkpoint, counters — commits or rolls back
        together, and disk exhaustion raises :class:`DiskExhaustedError`
        with the checkpoint untouched."""
        if self._disk_probe is not None:
            try:
                free = int(self._disk_probe())
            except OSError as error:
                raise DiskExhaustedError(
                    f"cannot probe free disk space: {error}"
                ) from error
            if free < self._disk_reserve:
                raise DiskExhaustedError(
                    f"disk exhausted: {free} bytes free, {self._disk_reserve}"
                    " reserved — batch refused, checkpoint unchanged"
                )

        batch_id = batch_id or uuid.uuid4().hex
        ingested_at = self._now()
        replay_status = "replay" if replay else "live"
        seen: set[str] = set()
        prepared: list[dict[str, Any]] = []
        accepted: list[SourceEvent] = []
        drops: dict[str, int] = {}
        for event in events:
            key = str(event.key)
            if key in seen or self._already_ingested(key):
                drops[GAP_DUPLICATE] = drops.get(GAP_DUPLICATE, 0) + 1
                continue
            seen.add(key)
            gap = self._policy_drop(event)
            if gap is not None:
                drops[gap] = drops.get(gap, 0) + 1
                continue
            try:
                prepared.append(self._ledger._prepare_row(dict(event.body)))
            except (ValueError, TypeError):
                drops[GAP_UNPARSEABLE] = drops.get(GAP_UNPARSEABLE, 0) + 1
                continue
            accepted.append(event)

        ledger_from: int | None = None
        ledger_to: int | None = None
        conn = self._ledger.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            results = self._ledger._insert_rows(prepared)
            for event, result in zip(accepted, results):
                conn.execute(
                    "INSERT INTO ingest_event"
                    " (source, source_key, source_offset, ledger_seq,"
                    "  ingested_at, batch_id, replay)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        self._source,
                        str(event.key),
                        int(event.offset),
                        result.sequence,
                        ingested_at,
                        batch_id,
                        replay_status,
                    ),
                )
            if results:
                ledger_from = results[0].sequence
                ledger_to = results[-1].sequence
            if accepted:
                high_water = max(int(event.offset) for event in accepted) + 1
                next_offset = max(self.resume_offset(), high_water)
                conn.execute(
                    "INSERT INTO ingest_checkpoint (source, next_offset, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(source) DO UPDATE SET"
                    " next_offset = excluded.next_offset,"
                    " updated_at = excluded.updated_at",
                    (self._source, next_offset, ingested_at),
                )
            for gap_class, count in drops.items():
                conn.execute(
                    "INSERT INTO ingest_drops (source, gap_class, count)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(source, gap_class) DO UPDATE SET"
                    " count = count + excluded.count",
                    (self._source, gap_class, count),
                )
            conn.commit()
        except sqlite3.OperationalError as error:
            conn.rollback()
            if "disk" in str(error).lower() or "full" in str(error).lower():
                raise DiskExhaustedError(
                    f"disk exhausted mid-batch: {error} — batch rolled back,"
                    " checkpoint unchanged"
                ) from error
            raise
        except Exception:
            conn.rollback()
            raise

        return BatchResult(
            batchId=batch_id,
            source=self._source,
            replay=replay,
            ingested=len(accepted),
            ledgerFrom=ledger_from,
            ledgerTo=ledger_to,
            nextOffset=self.resume_offset(),
            drops=drops,
        )

    def _already_ingested(self, key: str) -> bool:
        row = self._ledger.conn.execute(
            "SELECT 1 FROM ingest_event WHERE source = ? AND source_key = ?",
            (self._source, key),
        ).fetchone()
        return row is not None

    def _policy_drop(self, event: SourceEvent) -> str | None:
        """The named gap class for an intentionally dropped event, or None
        when the event is accepted (FR-M41-12 — every intentional drop is
        named and counted)."""
        if self._excluded and event.path is not None:
            if any(event.path.startswith(prefix) for prefix in self._excluded):
                return GAP_EXCLUDED_PATH
        if self._supported_vendors is not None:
            vendor = event.body.get("vendor") or "meridian"
            if vendor not in self._supported_vendors:
                return GAP_UNSUPPORTED_VENDOR
        return None
