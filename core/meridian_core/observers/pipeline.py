"""Queued, debounced, single-writer observation pipeline (NFR-29).

Observation hooks from the editor/host side (file-write notifications)
must never block the caller and never block the observed agent:

* ``submit()`` is a non-blocking enqueue (``queue.put_nowait``) — it takes
  no application lock at all, so it is safe to call from any hook the
  observed agent's activity triggers.
* A single writer thread drains the queue, debounces bursts (quiet period
  of at least ``debounce_seconds``, so a 100-file write burst becomes ONE
  batch), and runs the handler. All observer IO stays on this one thread.
* Readers never wait on the writer: they consume whatever state the
  handler last published (the session monitor's cache).

The debounce floor is 250 ms per the NFR-29 architecture mandate.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

MIN_DEBOUNCE_SECONDS = 0.25


class ObservationPipeline:
    """Single-writer, debounced batch pipeline for observation events."""

    def __init__(
        self,
        debounce_seconds: float = MIN_DEBOUNCE_SECONDS,
        max_batch_wait_seconds: float = 2.0,
        name: str = "meridian-observation-pipeline",
    ) -> None:
        if debounce_seconds < MIN_DEBOUNCE_SECONDS:
            raise ValueError(
                f"NFR-29 architecture mandate: debounce must be >= "
                f"{MIN_DEBOUNCE_SECONDS}s, got {debounce_seconds}"
            )
        self.debounce_seconds = debounce_seconds
        self._max_batch_wait = max_batch_wait_seconds
        self._queue: queue.Queue[Any] = queue.Queue()
        self._handler: Callable[[list[Any]], None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._name = name
        # Observability for doctor/tests — single-writer, no locks needed.
        self.batches_processed = 0
        self.events_processed = 0
        self.last_batch_size = 0
        self.last_batch_at: float | None = None
        self.writer_thread_ident: int | None = None

    def set_handler(self, handler: Callable[[list[Any]], None]) -> None:
        self._handler = handler

    def submit(self, event: Any) -> None:
        """Enqueue one observation event. Never blocks; takes no lock."""
        self._queue.put_nowait(event)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name=self._name, daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pending_count(self) -> int:
        return self._queue.qsize()

    # -- writer thread ---------------------------------------------------------

    def _run(self) -> None:
        self.writer_thread_ident = threading.get_ident()
        pending: list[Any] = []
        while not self._stop.is_set():
            # Block for the first event of a new batch.
            try:
                first = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._stop.is_set():
                break
            pending.append(first)
            batch_started = time.monotonic()
            self._drain(pending)
            # Debounce: flush only after a quiet period (or max batch wait).
            while not self._stop.is_set():
                quiet_deadline = time.monotonic() + self.debounce_seconds
                over_deadline = batch_started + self._max_batch_wait
                wait = min(quiet_deadline, over_deadline) - time.monotonic()
                if wait <= 0:
                    break
                try:
                    pending.append(self._queue.get(timeout=wait))
                except queue.Empty:
                    break
                self._drain(pending)
                if time.monotonic() >= over_deadline:
                    break
            self._flush(pending)
            pending = []

    def _drain(self, pending: list[Any]) -> None:
        while True:
            try:
                pending.append(self._queue.get_nowait())
            except queue.Empty:
                return

    def _flush(self, batch: list[Any]) -> None:
        if not batch:
            return
        handler = self._handler
        if handler is not None:
            try:
                handler(batch)
            except Exception:  # noqa: BLE001 - a bad handler must not kill the writer
                pass
        self.batches_processed += 1
        self.events_processed += len(batch)
        self.last_batch_size = len(batch)
        self.last_batch_at = time.monotonic()
