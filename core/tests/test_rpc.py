"""Framing + dispatch tests for the sidecar RPC core (FR-M3-01, FR-M3-09)."""

from __future__ import annotations

import io
import json

import pytest

from meridian_core import protocol
from meridian_core.rpc import (
    FramedReader,
    FramedWriter,
    FrameTooLargeError,
    make_error_response,
    make_response,
)
from meridian_core.server import SidecarServer


class TestFraming:
    def test_round_trip_single_frame(self):
        buffer = io.BytesIO()
        writer = FramedWriter(buffer)
        writer.write_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        buffer.seek(0)
        assert FramedReader(buffer).read_message() == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"ok": True},
        }

    def test_frame_is_exactly_one_line(self):
        buffer = io.BytesIO()
        FramedWriter(buffer).write_message({"text": "line1\nline2"})
        payload = buffer.getvalue()
        # json.dumps escapes embedded newlines, so exactly one raw LF exists.
        assert payload.count(b"\n") == 1
        assert payload.endswith(b"\n")

    def test_reader_handles_split_frames(self):
        stream = io.BytesIO(b'{"a": 1}\n{"b": 2}\n')
        reader = FramedReader(stream)
        assert reader.read_message() == {"a": 1}
        assert reader.read_message() == {"b": 2}
        assert reader.read_message() is None  # clean EOF

    def test_truncated_frame_raises(self):
        with pytest.raises(ValueError, match="truncated"):
            FramedReader(io.BytesIO(b'{"a": 1')).read_message()

    def test_oversized_frame_rejected(self):
        with pytest.raises(FrameTooLargeError):
            FramedReader(io.BytesIO(b"x" * (17 * 1024 * 1024) + b"\n")).read_message()

    def test_the_read_is_bounded_before_the_size_is_checked(self):
        """The guard has to run *before* the bytes are in memory.

        This test exists because the one above does not distinguish the two.
        `readline()` with no argument reads to the next newline however far
        away it is, so the size check ran after the whole line was already
        allocated: a peer sending four gigabytes without a newline got four
        gigabytes allocated, and MAX_FRAME_BYTES only said so afterwards.
        """

        class Endless:
            """A peer that never sends a newline, and refuses to be asked for
            an unbounded read — which is precisely the defect."""

            def __init__(self) -> None:
                self.served = 0

            def readline(self, size: int = -1) -> bytes:
                if size is None or size < 0:
                    raise AssertionError(
                        "unbounded readline: the frame guard cannot protect "
                        "memory it has already allocated"
                    )
                self.served += size
                return b"x" * size

        stream = Endless()
        with pytest.raises(FrameTooLargeError):
            FramedReader(stream).read_message()
        # Bounded in time as well: the skip-ahead gives up rather than
        # spinning on a peer that never sends a newline.
        assert stream.served <= 3 * (16 * 1024 * 1024)

    def test_the_frame_after_an_oversized_one_still_parses(self):
        # The tail of the giant line must not be read as the frames that
        # follow it, or one bad frame becomes a cascade of parse errors.
        stream = io.BytesIO(b"x" * (17 * 1024 * 1024) + b"\n" + b'{"a": 1}\n')
        reader = FramedReader(stream)
        with pytest.raises(FrameTooLargeError):
            reader.read_message()
        assert reader.read_message() == {"a": 1}

    def test_non_object_frame_rejected(self):
        with pytest.raises(ValueError, match="not a JSON object"):
            FramedReader(io.BytesIO(b"[1, 2]\n")).read_message()


class TestDispatch:
    def setup_method(self):
        self.server = SidecarServer()

    def test_handshake_returns_protocol_and_capabilities(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {"protocolVersion": 1, "client": "test"},
            }
        )
        assert response["id"] == 1
        result = response["result"]
        assert result["protocolVersion"] == protocol.PROTOCOL_VERSION
        assert result["coreVersion"] == protocol.CORE_VERSION
        assert "handshake" in result["capabilities"]["methods"]

    def test_handshake_refuses_version_mismatch(self):
        response = self.server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {"protocolVersion": 999, "client": "test"},
            }
        )
        assert response["error"]["code"] == protocol.ERROR_PROTOCOL_MISMATCH
        assert response["error"]["data"] == {"expected": 1, "actual": 999}

    def test_ping_increments_and_reports_uptime(self):
        first = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        second = self.server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        assert first["result"]["pong"] is True
        assert second["result"]["seq"] == first["result"]["seq"] + 1
        assert second["result"]["uptimeSeconds"] >= 0

    def test_shutdown_sets_event_and_confirms(self):
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "shutdown", "params": {"reason": "test"}}
        )
        assert response["result"] == {"ok": True}
        assert self.server.shutdown_requested.is_set()

    def test_unknown_method(self):
        response = self.server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "nope"})
        assert response["error"]["code"] == protocol.METHOD_NOT_FOUND

    def test_notification_gets_no_response(self):
        assert (
            self.server.handle_message({"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": 1}})
            is None
        )

    def test_missing_jsonrpc_field_rejected(self):
        response = self.server.handle_message({"id": 1, "method": "ping"})
        assert response["error"]["code"] == protocol.INVALID_REQUEST


class TestServeLoop:
    def test_serve_exits_on_eof(self):
        reader = FramedReader(io.BytesIO(b""))
        out = io.BytesIO()
        SidecarServer().serve(reader, FramedWriter(out))
        assert out.getvalue() == b""

    def test_serve_answers_ping_then_shutdown(self):
        frames = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
            + b"\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}).encode()
            + b"\n"
        )
        out = io.BytesIO()
        SidecarServer().serve(FramedReader(io.BytesIO(frames)), FramedWriter(out))
        lines = out.getvalue().decode().strip().split("\n")
        responses = [json.loads(line) for line in lines]
        assert responses[0]["result"]["pong"] is True
        assert responses[1]["result"] == {"ok": True}

    def test_serve_reports_parse_error_and_continues(self):
        frames = b'{"broken": true\n' + json.dumps(
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}
        ).encode() + b"\n"
        out = io.BytesIO()
        SidecarServer().serve(FramedReader(io.BytesIO(frames)), FramedWriter(out))
        responses = [json.loads(line) for line in out.getvalue().decode().strip().split("\n")]
        assert responses[0]["error"]["code"] == protocol.PARSE_ERROR
        assert responses[1]["result"]["pong"] is True


def test_response_builders():
    assert make_response(1, {"a": 1}) == {"jsonrpc": "2.0", "id": 1, "result": {"a": 1}}
    error = make_error_response(None, -32601, "nope", data={"m": "nope"})
    assert error["error"] == {"code": -32601, "message": "nope", "data": {"m": "nope"}}
