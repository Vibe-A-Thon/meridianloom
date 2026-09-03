"""Entry point: ``python -m meridian_core`` (FR-M3-01).

Spawns no threads and opens no sockets by itself (FR-M3-10); it configures
logging, then runs the JSON-RPC loop over stdin/stdout until the peer closes
the pipe or sends ``shutdown``.
"""

from __future__ import annotations

import sys

from .log_setup import configure_logging
from .rpc import FramedReader, FramedWriter
from .server import SidecarServer


def main() -> int:
    configure_logging()
    server = SidecarServer()
    server.serve(
        FramedReader(sys.stdin.buffer),
        FramedWriter(sys.stdout.buffer),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
