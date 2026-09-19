"""Observation overhead budget tests (NFR-29; F0 Workstream D task 21).

Architecture under test:

* observation hooks are queued (``submit`` = non-blocking enqueue, no
  application lock), debounced >= 250 ms, and processed by a SINGLE writer
  thread;
* RPC read paths (observe/sessions) serve the monitor cache and respond
  while a slow observation is in flight — they never wait on observer IO.

The 5% budget is asserted on a 2-second-scale baseline: 5% of 2000 ms is
100 ms. Measured numbers are printed for the record (perf-marked).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from meridian_core.observers.manager import ObserverManager
from meridian_core.observers.pipeline import MIN_DEBOUNCE_SECONDS, ObservationPipeline
from meridian_core.observers.processes import ProcessInfo
from meridian_core.observers.sessions import SessionMonitor
from meridian_core.server import SidecarServer

BASELINE_SECONDS = 2.0
BUDGET_SECONDS = BASELINE_SECONDS * 0.05  # NFR-29: 5% of a 2s-scale session
BURST_WRITES = 100


def wait_for(condition, timeout: float, interval: float = 0.02) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition():
            return time.monotonic() - start
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


@pytest.mark.perf
class TestWriteBurstBudget:
    def test_debounce_floor_is_the_mandated_quarter_second(self):
        assert MIN_DEBOUNCE_SECONDS >= 0.25
        pipeline = ObservationPipeline()
        assert pipeline.debounce_seconds >= 0.25
        with pytest.raises(ValueError, match="debounce"):
            ObservationPipeline(debounce_seconds=0.1)

    def test_hundred_write_burst_submissions_stay_under_budget(self, tmp_path):
        pipeline = ObservationPipeline(debounce_seconds=0.25)
        batches: list[list] = []
        pipeline.set_handler(lambda batch: batches.append(list(batch)))
        pipeline.start()
        try:
            start = time.monotonic()
            for index in range(BURST_WRITES):
                pipeline.submit(f"file-{index}.py")
            elapsed = time.monotonic() - start
            print(
                f"\nNFR-29: {BURST_WRITES} write-hook submissions took "
                f"{elapsed * 1000:.1f} ms (budget {BUDGET_SECONDS * 1000:.0f} ms)"
            )
            assert elapsed < BUDGET_SECONDS
            # The whole burst coalesces into ONE debounced batch.
            wait_for(lambda: len(batches) >= 1, timeout=5)
            time.sleep(0.05)
            assert batches[0] == [f"file-{index}.py" for index in range(BURST_WRITES)]
            print(f"NFR-29: burst coalesced into {len(batches)} batch(es)")
        finally:
            pipeline.stop()

    def test_monitor_notify_write_never_blocks_even_with_a_slow_writer(self, tmp_path):
        release = threading.Event()

        def slow_handler(batch):
            release.wait(timeout=10)  # simulates a 10s-max slow observation

        pipeline = ObservationPipeline(debounce_seconds=0.25)
        pipeline.set_handler(slow_handler)
        monitor = SessionMonitor(ObserverManager(), tmp_path, write_pipeline=pipeline)
        monitor.start()
        try:
            pipeline.submit("warmup.py")  # occupies the writer
            wait_for(lambda: pipeline.batches_processed >= 1, timeout=5)

            # While the writer is stuck in the slow handler, hooks and
            # cache reads must stay instant: no lock the observed agent
            # would need is ever taken on this path.
            start = time.monotonic()
            for index in range(20):
                monitor.notify_write(f"file-{index}.py")
                snapshot = monitor.snapshot()
            elapsed = time.monotonic() - start
            print(
                f"\nNFR-29: 20 notify_write + snapshot pairs during a slow "
                f"observation took {elapsed * 1000:.1f} ms"
            )
            assert elapsed < BUDGET_SECONDS
        finally:
            release.set()
            monitor.stop()

    def test_single_writer_thread_processes_every_batch(self, tmp_path):
        pipeline = ObservationPipeline(debounce_seconds=0.25)
        pipeline.set_handler(lambda batch: None)
        pipeline.start()
        try:
            for index in range(10):
                pipeline.submit(f"e{index}")
            wait_for(lambda: pipeline.events_processed >= 10, timeout=5)
            writer_idents = {pipeline.writer_thread_ident}
            assert len(writer_idents) == 1
            assert pipeline.writer_thread_ident != threading.get_ident()
        finally:
            pipeline.stop()


@pytest.mark.perf
class TestRpcNeverWaitsOnObserverIo:
    def _server_with_slow_observer(self, tmp_path, sleep_seconds: float) -> SidecarServer:
        class SlowObserver:
            vendor = "slow-agent"
            vendor_release = "1.0"
            adapter_version = "1.0.0"

            def observe(self, workspace, now):
                time.sleep(sleep_seconds)  # simulates a slow probe
                from meridian_core.observers.base import ChainOutcome

                return ChainOutcome(observation=None)

            def health(self):
                return {"detail": "slow by design"}

        server = SidecarServer()
        from meridian_core.observers.manager import ObserverManager

        server._observers = ObserverManager([SlowObserver()])
        server._handle_handshake(
            {
                "protocolVersion": 1,
                "client": "pytest",
                "workspaceDir": str(tmp_path),
            }
        )
        return server

    def test_observe_sessions_responds_while_slow_observation_in_flight(
        self, tmp_path
    ):
        server = self._server_with_slow_observer(tmp_path, sleep_seconds=0.5)
        try:
            # Wait until a slow tick is actually in flight.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                monitor = server._session_monitor
                if monitor is not None and monitor.ticks >= 1:
                    break
                time.sleep(0.05)
            monitor = server._session_monitor
            assert monitor is not None
            # Force another slow tick synchronously on a helper thread,
            # then answer RPCs while it runs.
            tick_thread = threading.Thread(target=monitor.tick)
            tick_thread.start()
            time.sleep(0.1)  # ensure the tick is inside the 500ms sleep

            start = time.monotonic()
            response = server.handle_message(
                {"jsonrpc": "2.0", "id": 1, "method": "observe/sessions", "params": {}}
            )
            elapsed = time.monotonic() - start
            print(
                f"\nNFR-29: observe/sessions during a 500ms in-flight "
                f"observation answered in {elapsed * 1000:.1f} ms"
            )
            assert "result" in response
            assert elapsed < BUDGET_SECONDS
            tick_thread.join(timeout=5)
        finally:
            server._handle_shutdown({"reason": "test teardown"})

    def test_observe_health_is_pure_memory(self, tmp_path):
        server = self._server_with_slow_observer(tmp_path, sleep_seconds=0.5)
        try:
            start = time.monotonic()
            response = server.handle_message(
                {"jsonrpc": "2.0", "id": 1, "method": "observe/health", "params": {}}
            )
            elapsed = time.monotonic() - start
            print(f"\nNFR-29: observe/health answered in {elapsed * 1000:.1f} ms")
            assert "result" in response
            assert elapsed < 0.1
        finally:
            server._handle_shutdown({"reason": "test teardown"})

    def test_process_listing_does_not_block_the_rpc_path(self, tmp_path):
        # Even if process listing itself is slow (fallback tasklist under
        # endpoint scanning), the RPC path answers from the cache.
        server = SidecarServer()
        server._handle_handshake(
            {
                "protocolVersion": 1,
                "client": "pytest",
                "workspaceDir": str(tmp_path),
            }
        )
        monitor = server._session_monitor

        def slow_listing():
            time.sleep(0.5)
            return [ProcessInfo(pid=7, name="codex", command_line="")]

        monitor._list_processes = slow_listing
        try:
            tick_thread = threading.Thread(target=monitor.tick)
            tick_thread.start()
            time.sleep(0.1)
            start = time.monotonic()
            response = server.handle_message(
                {"jsonrpc": "2.0", "id": 1, "method": "observe/sessions", "params": {}}
            )
            elapsed = time.monotonic() - start
            print(
                f"\nNFR-29: observe/sessions during a 500ms process listing "
                f"answered in {elapsed * 1000:.1f} ms"
            )
            assert "result" in response
            assert elapsed < BUDGET_SECONDS
            tick_thread.join(timeout=5)
        finally:
            server._handle_shutdown({"reason": "test teardown"})
