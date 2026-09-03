"""JSON-RPC method dispatch for the Meridian Core sidecar.

The server is a plain object so tests can drive it without real stdio:
``handle_message`` maps one decoded frame to zero or one response frame.
``serve`` is the production loop over stdin/stdout.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from collections.abc import Callable
from typing import Any

from . import protocol
from .rpc import (
    FramedReader,
    FramedWriter,
    make_error_response,
    make_response,
)

logger = logging.getLogger("meridian_core.server")

# Method handlers take (server, params) and return a JSON-able result.
Handler = Callable[["SidecarServer", Any], Any]


class SidecarServer:
    """Dispatches framed JSON-RPC requests to method handlers."""

    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._shutdown_requested = threading.Event()
        self._ping_seq = 0
        self._handlers: dict[str, Handler] = {
            "handshake": SidecarServer._handle_handshake,
            "ping": SidecarServer._handle_ping,
            "shutdown": SidecarServer._handle_shutdown,
        }

    @property
    def shutdown_requested(self) -> threading.Event:
        """Set when the peer asked us to exit (or stdin closed, task 7)."""
        return self._shutdown_requested

    # -- dispatch -----------------------------------------------------------

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Map one incoming frame to its response frame (or None)."""
        if message.get("jsonrpc") != "2.0":
            return make_error_response(
                message.get("id"), protocol.INVALID_REQUEST, "not JSON-RPC 2.0"
            )
        method = message.get("method")
        if not isinstance(method, str):
            return make_error_response(
                message.get("id"), protocol.INVALID_REQUEST, "missing method"
            )
        request_id = message.get("id")
        if request_id is None:
            # Notification: currently the sidecar has none to consume; the
            # extension only sends requests plus $/cancel (handled in task 10).
            logger.debug("ignoring notification %s", method)
            return None
        handler = self._handlers.get(method)
        if handler is None:
            return make_error_response(
                request_id, protocol.METHOD_NOT_FOUND, f"unknown method: {method}"
            )
        try:
            result = handler(self, message.get("params") or {})
        except _RpcError as error:
            return make_error_response(request_id, error.code, error.message, error.data)
        except Exception:  # noqa: BLE001 - never let a handler kill the loop
            logger.exception("handler for %s failed", method)
            return make_error_response(
                request_id, protocol.INTERNAL_ERROR, f"internal error in {method}"
            )
        return make_response(request_id, result)

    # -- main loop ----------------------------------------------------------

    def serve(self, reader: FramedReader, writer: FramedWriter) -> None:
        """Read frames until the peer closes stdin or asks for shutdown."""
        logger.info("sidecar serving (protocol v%s, core %s)",
                    protocol.PROTOCOL_VERSION, protocol.CORE_VERSION)
        while not self._shutdown_requested.is_set():
            try:
                message = reader.read_message()
            except ValueError as error:
                logger.warning("bad frame: %s", error)
                writer.write_message(
                    make_error_response(None, protocol.PARSE_ERROR, str(error))
                )
                continue
            if message is None:
                # stdin closed: the parent is gone or shutting down. Either
                # way the sidecar must not outlive its pipe (FR-M3-03).
                logger.info("stdin closed; shutting down")
                break
            response = self.handle_message(message)
            if response is not None:
                writer.write_message(response)
        logger.info("sidecar main loop exited")

    # -- methods ------------------------------------------------------------

    def _handle_handshake(self, params: Any) -> dict[str, Any]:
        client_version = (params or {}).get("protocolVersion")
        if client_version != protocol.PROTOCOL_VERSION:
            # FR-M3-08: refuse on mismatch; the extension surfaces this as
            # "reinstall" rather than operating against an incompatible core.
            raise _RpcError(
                protocol.ERROR_PROTOCOL_MISMATCH,
                "protocol version mismatch: "
                f"client={client_version} sidecar={protocol.PROTOCOL_VERSION}",
                data={
                    "expected": protocol.PROTOCOL_VERSION,
                    "actual": client_version,
                },
            )
        return {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "coreVersion": protocol.CORE_VERSION,
            "pythonVersion": platform.python_version(),
            "capabilities": {
                "methods": sorted(self._handlers),
                "framing": "ndjson",
            },
        }

    def _handle_ping(self, params: Any) -> dict[str, Any]:
        self._ping_seq += 1
        return {
            "pong": True,
            "seq": self._ping_seq,
            "uptimeSeconds": round(time.monotonic() - self._started_at, 3),
        }

    def _handle_shutdown(self, params: Any) -> dict[str, Any]:
        logger.info("shutdown requested: %s", (params or {}).get("reason", "no reason"))
        self._shutdown_requested.set()
        return {"ok": True}


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
