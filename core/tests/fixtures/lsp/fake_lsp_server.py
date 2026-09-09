"""Fake language server for the LSP bridge tests (FR-M33-02).

A real subprocess speaking JSON-RPC Content-Length framing on stdio, but
with canned, deterministic answers — no language intelligence. Behaviour is
fully derivable from the request so tests can assert exact pass-through:

* ``initialize``        → minimal server capabilities
* ``textDocument/definition``  → one location at (line-1, 4)-(line-1, 20)
                          of the SAME uri that was asked about
* ``textDocument/references``  → two locations: the asked position and the
                          line after it, same uri
* ``workspace/symbol``  → one symbol named exactly the query string
* ``shutdown``/``exit`` → lifecycle

Environment knobs (used by the degradation tests):
* ``FAKE_LSP_DELAY_SECONDS`` — sleep that long before answering any request,
  to exercise the bridge's per-request timeout.
"""

from __future__ import annotations

import json
import os
import sys
import time


def _read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        name, _, value = line.partition(b":")
        headers[name.strip().lower().decode("ascii", errors="replace")] = (
            value.strip().decode("ascii", errors="replace")
        )
    length = int(headers.get("content-length", "0"))
    body = sys.stdin.buffer.read(length)
    if len(body) != length:
        return None
    return json.loads(body.decode("utf-8", errors="replace"))


def _send(message):
    body = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def main():
    delay = float(os.environ.get("FAKE_LSP_DELAY_SECONDS", "0"))
    while True:
        message = _read_message()
        if message is None:
            return
        method = message.get("method")
        if method == "exit":
            return
        if "id" not in message:
            continue  # notification from the client — acknowledge nothing

        if delay:
            time.sleep(delay)

        params = message.get("params") or {}
        if method == "initialize":
            result = {
                "capabilities": {
                    "definitionProvider": True,
                    "referencesProvider": True,
                    "workspaceSymbolProvider": True,
                }
            }
        elif method == "shutdown":
            result = None
        elif method == "textDocument/definition":
            uri = params["textDocument"]["uri"]
            line = params["position"]["line"]
            result = [
                {
                    "uri": uri,
                    "range": {
                        "start": {"line": line - 1, "character": 4},
                        "end": {"line": line - 1, "character": 20},
                    },
                }
            ]
        elif method == "textDocument/references":
            uri = params["textDocument"]["uri"]
            line = params["position"]["line"]
            result = [
                {
                    "uri": uri,
                    "range": {
                        "start": {"line": line, "character": 0},
                        "end": {"line": line, "character": 10},
                    },
                },
                {
                    "uri": uri,
                    "range": {
                        "start": {"line": line + 1, "character": 0},
                        "end": {"line": line + 1, "character": 10},
                    },
                },
            ]
        elif method == "workspace/symbol":
            result = [
                {
                    "name": params.get("query", ""),
                    "kind": 12,
                    "location": {
                        "uri": "file:///workspace/symbol.py",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 10},
                        },
                    },
                }
            ]
        else:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
            continue

        _send({"jsonrpc": "2.0", "id": message["id"], "result": result})


if __name__ == "__main__":
    main()
