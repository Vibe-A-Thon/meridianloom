"""Minimal MCP stdio client — FR-M9-01.

The sidecar acts as an MCP client over stdio (newline-delimited JSON-RPC
2.0): ``initialize`` -> ``notifications/initialized`` -> ``tools/list``
-> ``tools/call``. No third-party MCP SDK is pinned in v1 (the protocol
subset the tool surface needs is small and stable); the transport is
isolated here so swapping in the official SDK later touches one module.

Servers are pinned and trust-acknowledged before they may run
(FR-M9-08, enforced by ``validate_mcp_server``); this client only speaks
to a server that passed that gate.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence

from meridian_core.childenv import child_environment
from .surface import PinnedMcpServer, validate_mcp_server

PROTOCOL_VERSION = "2025-06-18"


class McpProtocolError(RuntimeError):
    """The server answered off-protocol or with a JSON-RPC error."""


@dataclass
class McpStdioClient:
    """One stdio MCP server session. The server is only ever spawned
    through :meth:`start``, which enforces the pinning gate — there is no
    code path that speaks to an unvalidated server config."""

    server: PinnedMcpServer
    timeout_s: float = 60.0
    _process: subprocess.Popen | None = None
    _next_id: int = 1

    def start(self) -> dict[str, Any]:
        """Spawn the server and complete the handshake. Returns the
        server's initialize result."""
        validate_mcp_server(self.server)  # FR-M9-08 gate, no bypass path
        self._process = subprocess.Popen(
            list(self.server.command),
            env=child_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "meridian-sidecar", "version": "1"},
            },
        )
        self._notify("notifications/initialized", {})
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    # -- wire -------------------------------------------------------------

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._read()
            # Notifications carry no id; skip them while waiting.
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpProtocolError(
                    f"MCP {method} failed: {message['error']}"
                )
            return message.get("result", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.write(
            (json.dumps(message) + "\n").encode("utf-8")
        )
        self._process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self._process is not None and self._process.stdout is not None
        line = self._process.stdout.readline()
        if not line:
            raise McpProtocolError(
                f"MCP server '{self.server.server_id}' closed the connection"
            )
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise McpProtocolError(
                f"MCP server '{self.server.server_id}' sent non-JSON: {exc}"
            )
