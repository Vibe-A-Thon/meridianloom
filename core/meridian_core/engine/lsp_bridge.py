"""LSP symbol-resolution bridge (FR-M33-02; FR-M28-01).

Spawns a language server as a subprocess and speaks JSON-RPC over the
LSP Content-Length framing on its stdio. The server command comes ONLY from
policy/workspace configuration — the payload's ``config.servers[language]``
mapping — never from a hard-coded table. The bridge:

* initializes the server on the workspace root (``initialize`` /
  ``initialized``), then answers one query — ``definition``, ``references``
  or ``symbols`` (workspace/symbol) — then shuts the server down;
* times out every request (``config.timeout_seconds``, default 10 s) and
  treats a timeout as ``no_deterministic_path``, not as an empty answer;
* degrades honestly: a language with no configured server, a server binary
  that cannot be spawned, or a server that exits mid-session all report
  ``handled=False`` with the cause named. Results are passed through exactly
  as the server returned them — an empty location list is a real answer and
  is reported as one; nothing is ever fabricated.

Zero model calls: this module only spawns the configured server and relays
its answers.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from ..childenv import child_environment
from .capabilities import CapabilityOutcome

__all__ = ["SymbolResolutionCapability", "LspError"]

_CAPABILITY_NAME = "symbol_resolution"

_QUERIES = ("definition", "references", "symbols")
_DEFAULT_TIMEOUT = 10.0


class LspError(Exception):
    """A clean LSP bridge failure — config, transport or timeout."""


def _path_to_uri(path: str) -> str:
    absolute = Path(path).resolve()
    posix = quote(str(absolute).replace(os.sep, "/"), safe="/:")
    return f"file:///{posix}" if not posix.startswith("file:") else posix


@dataclass
class _RpcPeer:
    """One subprocess speaking Content-Length-framed JSON-RPC on stdio.

    A reader thread pushes decoded messages onto a queue so every request
    can carry a wall-clock timeout (stdout has no portable deadline).
    """

    process: subprocess.Popen
    inbox: queue.Queue = field(default_factory=queue.Queue)
    _next_id: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def spawn(cls, command: Sequence[str]) -> "_RpcPeer":
        try:
            process = subprocess.Popen(
                list(command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                # Language servers load project configuration and plugins; none
                # of that gets the sidecar's MERIDIAN_* secrets (SEC-27).
                env=child_environment(),
            )
        except OSError as error:
            raise LspError(f"cannot spawn language server {list(command)!r}: {error}") from error
        peer = cls(process=process)
        threading.Thread(target=peer._reader, daemon=True).start()
        return peer

    def _reader(self) -> None:
        stdout = self.process.stdout
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = stdout.readline()
                    if not line:
                        return  # server closed the pipe
                    line = line.strip()
                    if not line:
                        break
                    name, _, value = line.partition(b":")
                    headers[name.strip().lower().decode("ascii", errors="replace")] = (
                        value.strip().decode("ascii", errors="replace")
                    )
                length = int(headers.get("content-length", "0"))
                body = stdout.read(length)
                if len(body) != length:
                    return
                self.inbox.put(json.loads(body.decode("utf-8", errors="replace")))
        except (OSError, ValueError):
            return  # a malformed frame kills the reader; requests then time out

    def _send(self, message: Mapping[str, Any]) -> None:
        body = json.dumps(message).encode("utf-8")
        try:
            self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
            self.process.stdin.flush()
        except (OSError, BrokenPipeError) as error:
            raise LspError(f"language server is not accepting input: {error}") from error

    def request(self, method: str, params: Mapping[str, Any], timeout: float) -> Any:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = timeout
        while True:
            try:
                message = self.inbox.get(timeout=deadline)
            except queue.Empty as error:
                raise LspError(f"timed out after {timeout}s waiting for {method}") from error
            if message.get("id") != request_id:
                continue  # a notification or another response; keep waiting
            if "error" in message:
                raise LspError(f"server error on {method}: {message['error']}")
            return message.get("result")

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        try:
            if self.process.stdin:
                self.process.stdin.close()
        except OSError:
            pass
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()


class SymbolResolutionCapability:
    """The ``symbol_resolution`` capability, owned by the ``resolve_symbol``
    action class (FR-M33-01).

    Payload: ``{workspace, language, query, path, line, character, config}``
    where ``query`` is ``definition`` / ``references`` / ``symbols`` and
    ``config`` is ``{servers: {<language>: {command: [...]}},
    timeout_seconds: float}``. ``line``/``character`` are 0-based, as in LSP.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        missing = [key for key in ("workspace", "language", "query", "config") if key not in action]
        if missing:
            return CapabilityOutcome(handled=False, reason=f"missing payload keys: {', '.join(missing)}")
        language = action["language"]
        query = action["query"]
        if query not in _QUERIES:
            return CapabilityOutcome(
                handled=False, reason=f"query must be one of {_QUERIES}, got {query!r}"
            )
        config = action.get("config")
        if not isinstance(config, Mapping):
            return CapabilityOutcome(handled=False, reason="'config' must be a mapping")
        servers = config.get("servers")
        server = servers.get(language) if isinstance(servers, Mapping) else None
        if not isinstance(server, Mapping):
            return CapabilityOutcome(
                handled=False,
                reason=f"no language server configured for '{language}' — "
                f"symbol resolution unavailable; refusing rather than fabricating",
            )
        command = server.get("command")
        if (
            not isinstance(command, Sequence)
            or isinstance(command, (str, bytes))
            or not command
            or any(not isinstance(part, (str, bytes)) for part in command)
        ):
            return CapabilityOutcome(
                handled=False, reason=f"server config for '{language}' needs a non-empty 'command' list"
            )
        timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            return CapabilityOutcome(
                handled=False, reason="'timeout_seconds' must be a positive number"
            )

        try:
            result = self._query(action, query, [str(part) for part in command], float(timeout))
        except LspError as error:
            return CapabilityOutcome(handled=False, reason=str(error))
        return CapabilityOutcome(
            handled=True,
            result={
                "language": language,
                "query": query,
                "locations": result if result is not None else [],
            },
            reason="resolved via language server (FR-M28-01)",
        )

    def _query(
        self, action: Mapping[str, Any], query: str, command: list[str], timeout: float
    ) -> Any:
        peer = _RpcPeer.spawn(command)
        try:
            peer.request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": _path_to_uri(str(action["workspace"])),
                    "capabilities": {},
                    "workspaceFolders": None,
                },
                timeout,
            )
            peer.notify("initialized", {})
            if query == "symbols":
                result = peer.request(
                    "workspace/symbol",
                    {"query": str(action.get("symbol_query", ""))},
                    timeout,
                )
            else:
                uri = _path_to_uri(str(action.get("path", "")))
                position = {
                    "line": int(action.get("line", 0)),
                    "character": int(action.get("character", 0)),
                }
                if query == "definition":
                    result = peer.request(
                        "textDocument/definition",
                        {"textDocument": {"uri": uri}, "position": position},
                        timeout,
                    )
                else:  # references
                    result = peer.request(
                        "textDocument/references",
                        {
                            "textDocument": {"uri": uri},
                            "position": position,
                            "context": {"includeDeclaration": True},
                        },
                        timeout,
                    )
            try:
                peer.request("shutdown", None, timeout)
                peer.notify("exit", {})
            except LspError:
                pass  # a dead server at shutdown is not a resolution failure
            return result
        finally:
            peer.close()
