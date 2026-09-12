"""Framed JSON-RPC 2.0 transport over stdio (FR-M3-01).

Framing: newline-delimited JSON. Each frame is one complete JSON value on a
single line, UTF-8 encoded, terminated by ``\\n``. ``json.dumps`` never emits
a literal newline, so a line boundary is always a frame boundary.

FR-M3-09: writes go ONLY to the stdout stream handed to :class:`FramedWriter`;
the sidecar passes the real stdout and nothing else may write to it.
"""

from __future__ import annotations

import json
from typing import Any, BinaryIO

MAX_FRAME_BYTES = 16 * 1024 * 1024  # 16 MiB guard against a runaway peer

#: How much is read at a time while skipping past an oversized frame. Small,
#: because the whole point of that path is to stop holding the peer's data.
_DISCARD_CHUNK_BYTES = 64 * 1024


class FrameTooLargeError(ValueError):
    """A single incoming frame exceeded MAX_FRAME_BYTES."""


class FramedReader:
    """Reads NDJSON frames from a binary stream."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def _discard_to_frame_boundary(self) -> None:
        """Skip the remainder of an oversized frame, a chunk at a time.

        Without this the unread tail of the giant line would be parsed as the
        frames that follow it, so one oversized frame would become a cascade
        of parse errors instead of one.

        Bounded in time as well as memory: a peer that never sends a newline
        would otherwise spin here forever, which is a different way to wedge
        the sidecar than the one being fixed. Past the budget it gives up, and
        the next read starts mid-line and fails the same bounded way until the
        stream either resynchronises at a newline or closes.
        """
        discarded = 0
        while discarded < MAX_FRAME_BYTES:
            chunk = self._stream.readline(_DISCARD_CHUNK_BYTES)
            if chunk == b"" or chunk.endswith(b"\n"):
                return
            discarded += len(chunk)

    def read_message(self) -> dict[str, Any] | None:
        """Return the next decoded message, or None on clean EOF.

        EOF mid-frame is treated as a truncated frame and raises ValueError;
        EOF at a frame boundary is the normal peer-closed-stdin signal.

        The read is **bounded**. ``readline()`` with no argument reads until a
        newline however far away that is, so the size check used to run after
        the entire line was already in memory: a peer sending four gigabytes
        without a newline got four gigabytes allocated, and MAX_FRAME_BYTES —
        which calls itself a guard against a runaway peer — only reported the
        problem afterwards. The TypeScript decoder had this right, checking as
        it accumulated; this side did not.
        """
        line = self._stream.readline(MAX_FRAME_BYTES + 1)
        if line == b"":
            return None
        if len(line) > MAX_FRAME_BYTES:
            # A line that filled the budget without terminating still has its
            # tail in the pipe; one that ended exactly at the limit does not.
            if not line.endswith(b"\n"):
                self._discard_to_frame_boundary()
            raise FrameTooLargeError(f"frame exceeds {MAX_FRAME_BYTES} bytes")
        if not line.endswith(b"\n"):
            raise ValueError("truncated frame: EOF before newline terminator")
        message = json.loads(line.decode("utf-8"))
        if not isinstance(message, dict):
            raise ValueError("frame is not a JSON object")
        return message


class FramedWriter:
    """Writes NDJSON frames to a binary stream, one lock-free caller at a time.

    The sidecar is single-threaded on the write path (responses are written by
    the main loop; notification sends serialise on the same writer), so a
    plain write+flush keeps frames atomic.
    """

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def write_message(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        self._stream.write(payload)
        self._stream.flush()


def make_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error_response(
    request_id: Any, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def make_notification(method: str, params: Any = None) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    return message
