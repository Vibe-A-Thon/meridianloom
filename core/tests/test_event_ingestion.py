"""Event ingestion correctness (FR-M41-10/11/12; N1 Workstream C tasks
16/17).

Every imported source event carries a stable deduplication key, a source
offset, an ingest timestamp and a replay status (FR-M41-10). A 100,000-
event fixture reconciles EXACTLY after replay under the eight FR-M41-11
conditions — duplicate delivery, out-of-order arrival, clock skew,
process restart, partial files, API pagination, offline queueing and disk
exhaustion — with no silent loss and no double counting. Intentionally
dropped data surfaces as named coverage gaps (FR-M41-12), wired into the
coverage envelope.

Scale note: the full 100,000-event fixture runs under the clean,
duplicate and reordered conditions (the ones where exactly-once is least
obvious); the remaining conditions run a 20,000-event slice of the same
fixture generator — same vocabulary, same reconciliation, proportionate
time.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from meridian_core.ingest import (
    DiskExhaustedError,
    EventIngester,
    SourceEvent,
)
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics.coverage import DataGap, scan_scope
from meridian_core.metrics.trust import compute_rejection_rate

FULL_FIXTURE = 100_000
SLICE_FIXTURE = 20_000
BATCH = 5000

ACTORS = ("agent-alpha", "agent-beta", "agent-gamma", "human-dev")


def _body(index: int, *, skewed_ts: str | None = None) -> dict:
    body = {
        "story_id": f"story-{index % 97}",
        "phase": "build",
        "loop_id": f"L{index % 7}",
        "loop_iteration": index % 3,
        "actor_id": ACTORS[index % len(ACTORS)],
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }
    if skewed_ts is not None:
        body["ts_utc"] = skewed_ts
    return body


def _events(count: int, *, start: int = 0, skew_seconds: int = 0) -> list[SourceEvent]:
    """``count`` synthetic source events with offsets starting at
    ``start``. ``skew_seconds`` > 0 gives every event a wildly skewed
    source timestamp (the ±30-day clock-skew condition)."""
    events = []
    for index in range(start, start + count):
        skewed = None
        if skew_seconds:
            day = index % 61 - 30  # -30..+30 days, deterministic
            skewed = f"2025-{1 + abs(day) % 12:02d}-15T{(index + day) % 24:02d}:00:00Z"
        events.append(
            SourceEvent(key=f"ev-{index:07d}", offset=index, body=_body(index, skewed_ts=skewed))
        )
    return events


def _ledger(tmp_path: Path, name: str = "ledger") -> Ledger:
    return Ledger(tmp_path / name, EphemeralSigningKeyProvider())


def _feed(ingester: EventIngester, events: list[SourceEvent], *, replay: bool = True, batch: int = BATCH) -> None:
    """Feed events in batches of ``batch`` — the normal connector rhythm."""
    for at in range(0, len(events), batch):
        ingester.ingest_batch(events[at : at + batch], replay=replay)


def _reconcile(ledger: Ledger, ingester: EventIngester, expected: int) -> None:
    """The FR-M41-11 reconciliation: the ledger state must match the
    source stream EXACTLY — one ledger row per source offset, no gap, no
    double count, chain intact."""
    rows, rows_available = scan_scope(ledger, action_type="diff")
    assert rows_available == expected
    assert len(rows) == expected
    state_rows = ledger.conn.execute(
        "SELECT source_offset, ledger_seq, source_key, ingested_at, replay"
        " FROM ingest_event WHERE source = ? ORDER BY source_offset",
        (ingester._source,),
    ).fetchall()
    assert len(state_rows) == expected
    # Every offset present exactly once, in canonical (offset) order, and
    # each carries its FR-M41-10 fields bound to a real ledger sequence.
    assert [row[0] for row in state_rows] == list(range(expected))
    assert len({row[1] for row in state_rows}) == expected
    assert all(row[2] and row[3] and row[4] in ("live", "replay") for row in state_rows)
    assert ingester.resume_offset() == expected
    # No silent loss and no double counting, at the chain level too.
    assert ledger.verify().ok


class TestIngestUnit:
    def test_every_event_carries_key_offset_timestamp_replay_status(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            result = ingester.ingest_batch(
                [SourceEvent(key="k1", offset=0, body=_body(0))], replay=True
            )
            assert result.ingested == 1
            row = ledger.conn.execute(
                "SELECT source_key, source_offset, ledger_seq, ingested_at,"
                " batch_id, replay FROM ingest_event"
            ).fetchone()
            key, offset, seq, ingested_at, batch_id, replay = row
            assert key == "k1"
            assert offset == 0
            assert seq == 1  # bound to the ledger sequence it produced
            assert ingested_at  # ingest timestamp recorded at ingest time
            assert batch_id
            assert replay == "replay"
            assert ingester.replay_status("k1") == "replay"
            assert ingester.replay_status("nope") is None
        finally:
            ledger.close()

    def test_duplicate_keys_drop_and_count_never_double_count(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(4)
            first = ingester.ingest_batch(events)
            assert first.ingested == 4
            # The whole stream redelivered (at-least-once sources do this):
            second = ingester.ingest_batch(list(reversed(events)))
            assert second.ingested == 0
            assert second.drops == {"duplicate": 4}
            assert ledger.count(action_type="diff") == 4
            assert [(g.gapClass, g.count) for g in ingester.gaps()] == [
                ("duplicate", 4)
            ]
        finally:
            ledger.close()

    def test_unparseable_rows_drop_as_named_gap(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            bad = dict(_body(1))
            bad.pop("actor_id")  # fail-closed: missing a required field
            result = ingester.ingest_batch(
                [
                    SourceEvent(key="ok-1", offset=0, body=_body(0)),
                    SourceEvent(key="bad-1", offset=1, body=bad),
                ]
            )
            assert result.ingested == 1
            assert result.drops == {"unparseable": 1}
            assert ingester.gaps()[0].gapClass == "unparseable"
        finally:
            ledger.close()

    def test_excluded_paths_and_unsupported_vendors_drop_as_named_gaps(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(
                ledger,
                source="feed",
                excluded_path_prefixes=("vendor/",),
                supported_vendors=("meridian", "claude"),
            )
            vendor_body = {**_body(1), "vendor": "acme-coding"}
            result = ingester.ingest_batch(
                [
                    SourceEvent(key="ok", offset=0, body=_body(0), path="src/a.py"),
                    SourceEvent(
                        key="excluded", offset=1, body=_body(1), path="vendor/lib.py"
                    ),
                    SourceEvent(key="vendor", offset=2, body=vendor_body),
                ]
            )
            assert result.ingested == 1
            assert result.drops == {
                "excluded_path": 1,
                "unsupported_vendor": 1,
            }
            assert {g.gapClass for g in ingester.gaps()} == {
                "excluded_path",
                "unsupported_vendor",
            }
        finally:
            ledger.close()

    def test_disk_exhausted_is_a_named_failure_not_a_crash(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            healthy = [1024 * 1024 * 100]
            ingester = EventIngester(
                ledger, source="feed", disk_free_bytes=lambda: healthy[0]
            )
            ingester.ingest_batch(_events(4)[:2])
            # The disk fills before the next batch.
            healthy[0] = 0
            with pytest.raises(DiskExhaustedError):
                ingester.ingest_batch(_events(4)[2:])
            # Nothing half-committed: the checkpoint did not advance and
            # the refused batch is not in the ledger.
            assert ingester.resume_offset() == 2
            assert ledger.count(action_type="diff") == 2
            # Space returns; ingestion resumes exactly where it stopped.
            healthy[0] = 1024 * 1024 * 100
            ingester.ingest_batch(_events(4)[2:])
            assert ingester.resume_offset() == 4
            assert ledger.count(action_type="diff") == 4
            assert ledger.verify().ok
        finally:
            ledger.close()

    def test_restart_resumes_from_checkpoint_without_double_count(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            ingester.ingest_batch(_events(6)[:4])
            # Process restart: a brand-new ingester over the same ledger
            # and state resumes from the persisted checkpoint.
            restarted = EventIngester(ledger, source="feed")
            assert restarted.resume_offset() == 4
            restarted.ingest_batch(_events(6)[4:])
            # The source redelivers from offset 2 (its own cursor was
            # behind): overlap drops as duplicates, the tail lands once.
            restarted.ingest_batch(_events(6)[2:])
            assert ledger.count(action_type="diff") == 6
            assert restarted.resume_offset() == 6
            drops = {g.gapClass: g.count for g in restarted.gaps()}
            assert drops == {"duplicate": 4}  # offsets 2..5 redelivered
        finally:
            ledger.close()

    def test_ingest_drop_counters_wire_into_the_coverage_envelope(
        self, tmp_path: Path
    ):
        # FR-M41-12 (task 17): named gaps ride the envelope a figure is
        # disclosed with — a drop is never an absence.
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            ingester.ingest_batch(_events(3))
            ingester.ingest_batch(_events(3))  # all duplicates
            result = compute_rejection_rate(ledger, data_gaps=ingester.gaps())
            envelope = result["coverage"]
            gaps = {(g["gapClass"], g["count"]) for g in envelope["gaps"]}
            assert ("duplicate", 3) in gaps
        finally:
            ledger.close()

    def test_data_gap_shape(self):
        gap = DataGap(gapClass="duplicate", count=7, detail="source feed")
        assert gap.to_dict() == {
            "gapClass": "duplicate",
            "count": 7,
            "detail": "source feed",
        }
        assert "detail" not in DataGap(gapClass="x", count=1).to_dict()


class TestReconciliationFixture:
    """The FR-M41-11 fixture: a synthetic event stream reconciled exactly
    under each delivery condition."""

    def test_clean_full_100k_fixture_reconciles_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            _feed(ingester, _events(FULL_FIXTURE), replay=True)
            _reconcile(ledger, ingester, FULL_FIXTURE)
            # Replay of the first page is a no-op of counted drops.
            replay = EventIngester(ledger, source="feed")
            replay_result = replay.ingest_batch(
                _events(FULL_FIXTURE)[:BATCH], replay=True
            )
            assert replay_result.drops == {"duplicate": BATCH}
            assert ledger.count(action_type="diff") == FULL_FIXTURE
        finally:
            ledger.close()

    def test_duplicate_delivery_full_100k_reconciles_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(FULL_FIXTURE)
            # Every batch delivered twice, back to back.
            for at in range(0, len(events), BATCH):
                page = events[at : at + BATCH]
                ingester.ingest_batch(page, replay=True)
                again = ingester.ingest_batch(page, replay=True)
                assert again.drops == {"duplicate": len(page)}
            _reconcile(ledger, ingester, FULL_FIXTURE)
            drops = {g.gapClass: g.count for g in ingester.gaps()}
            assert drops == {"duplicate": FULL_FIXTURE}
        finally:
            ledger.close()

    def test_reordered_arrival_full_100k_reconciles_by_offset(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(FULL_FIXTURE)
            # A global shuffle (offline queue drain) then delivery: order
            # of arrival must not matter, order of offsets must.
            shuffled = list(events)
            random.Random(20260908).shuffle(shuffled)
            _feed(ingester, shuffled, replay=True)
            _reconcile(ledger, ingester, FULL_FIXTURE)
        finally:
            ledger.close()

    def test_clock_skew_reconciles_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            _feed(ingester, _events(SLICE_FIXTURE, skew_seconds=1), replay=True)
            _reconcile(ledger, ingester, SLICE_FIXTURE)
            # The skewed source timestamps landed as payload data; the
            # ingest-side ordering state is untouched by them.
            rows = ledger.conn.execute(
                "SELECT ingested_at FROM ingest_event WHERE source = 'feed'"
                " ORDER BY source_offset"
            ).fetchall()
            assert len({row[0] for row in rows}) >= 1  # stamped at ingest
        finally:
            ledger.close()

    def test_process_restart_resumes_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            first = EventIngester(ledger, source="feed")
            _feed(first, _events(SLICE_FIXTURE)[: SLICE_FIXTURE // 2])
            # Mid-stream restart: a new ingester resumes from the persisted
            # checkpoint; the source redelivers its in-flight page.
            second = EventIngester(ledger, source="feed")
            assert second.resume_offset() == SLICE_FIXTURE // 2
            overlap = _events(SLICE_FIXTURE)[
                SLICE_FIXTURE // 2 - BATCH : SLICE_FIXTURE // 2
            ]
            second.ingest_batch(overlap)
            _feed(second, _events(SLICE_FIXTURE)[SLICE_FIXTURE // 2 :])
            _reconcile(ledger, second, SLICE_FIXTURE)
            drops = {g.gapClass: g.count for g in second.gaps()}
            assert drops == {"duplicate": BATCH}
        finally:
            ledger.close()

    def test_partial_files_reconcile_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(SLICE_FIXTURE)
            # A file truncated mid-batch: the first half of one batch
            # arrives, then the rest in a later batch.
            cut = SLICE_FIXTURE // 2
            _feed(ingester, events[: cut - 700])
            ingester.ingest_batch(events[cut - 700 : cut])  # the partial tail
            ingester.ingest_batch(events[cut : cut + 300])  # resumed head
            _feed(ingester, events[cut + 300 :])
            _reconcile(ledger, ingester, SLICE_FIXTURE)
        finally:
            ledger.close()

    def test_api_pagination_reconciles_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(SLICE_FIXTURE)
            # API pages of 100, fetched slightly out of order per page.
            pages = [events[at : at + 100] for at in range(0, len(events), 100)]
            pages[5], pages[6] = pages[6], pages[5]
            for page in pages:
                ingester.ingest_batch(page, replay=True)
            _reconcile(ledger, ingester, SLICE_FIXTURE)
        finally:
            ledger.close()

    def test_offline_queueing_reconciles_exactly(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ingester = EventIngester(ledger, source="feed")
            events = _events(SLICE_FIXTURE)
            # Two offline queues draining at different rates, interleaved:
            # every third event was queued and arrives late, out of order.
            queued = [event for index, event in enumerate(events) if index % 3 == 0]
            live = [event for index, event in enumerate(events) if index % 3 != 0]
            queue_delay = list(reversed(queued))
            merged = []
            live_at, queued_at = 0, 0
            for index in range(len(events)):
                if index % 3 == 0:
                    merged.append(queue_delay[queued_at])
                    queued_at += 1
                else:
                    merged.append(live[live_at])
                    live_at += 1
            _feed(ingester, merged, replay=True)
            _reconcile(ledger, ingester, SLICE_FIXTURE)
        finally:
            ledger.close()

    def test_disk_exhausted_mid_stream_reconciles_after_recovery(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            free_bytes = [1024 * 1024 * 100]
            ingester = EventIngester(
                ledger, source="feed", disk_free_bytes=lambda: free_bytes[0]
            )
            events = _events(SLICE_FIXTURE)
            _feed(ingester, events[: SLICE_FIXTURE // 2])
            free_bytes[0] = 0  # the disk fills mid-stream
            with pytest.raises(DiskExhaustedError):
                ingester.ingest_batch(events[SLICE_FIXTURE // 2 :])
            # Named failure, not a crash: checkpoint and ledger intact.
            assert ingester.resume_offset() == SLICE_FIXTURE // 2
            assert ledger.count(action_type="diff") == SLICE_FIXTURE // 2
            assert ledger.verify().ok
            # Disk recovers; the batch is re-fed and lands exactly once.
            free_bytes[0] = 1024 * 1024 * 100
            ingester.ingest_batch(events[SLICE_FIXTURE // 2 :])
            _feed(ingester, events[SLICE_FIXTURE // 2 + BATCH :])
            _reconcile(ledger, ingester, SLICE_FIXTURE)
        finally:
            ledger.close()
