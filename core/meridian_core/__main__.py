"""Entry point: ``python -m meridian_core`` (FR-M3-01).

With no arguments it spawns no threads and opens no sockets by itself
(FR-M3-10); it configures logging, then runs the JSON-RPC loop over
stdin/stdout until the peer closes the pipe or sends ``shutdown``.

With a headless subcommand (``collect`` / ``export`` / ``erase`` /
``uninstall``, FR-M43-12…14) it runs that command and exits — the
sidecar contract is unchanged because the extension host always launches
it with no arguments.
"""

from __future__ import annotations

import argparse
import json
import sys

from .log_setup import configure_logging


def _run_headless(argv: list[str]) -> int:
    from . import collector

    parser = argparse.ArgumentParser(
        prog="python -m meridian_core",
        description="Meridian headless collector (FR-M43-12...14)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="observe + ingest a workspace")
    p_collect.add_argument("--workspace", required=True)

    p_export = sub.add_parser("export", help="portable signed evidence export")
    p_export.add_argument("--workspace", required=True)
    p_export.add_argument("--out", required=True)
    p_export.add_argument(
        "--sink",
        default=None,
        help="opt-in observability URL; the local ledger stays the record"
        " of authority (FR-M43-14)",
    )

    p_erase = sub.add_parser("erase", help="erase one privacy subject")
    p_erase.add_argument("--workspace", required=True)
    p_erase.add_argument("--subject", required=True)

    p_uninstall = sub.add_parser(
        "uninstall", help="remove Meridian state, preserve the evidence record"
    )
    p_uninstall.add_argument("--workspace", required=True)

    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collector.collect(args.workspace)
    elif args.command == "export":
        result = collector.export_portable(args.workspace, args.out, sink=args.sink)
    elif args.command == "erase":
        result = collector.erase_subject(args.workspace, args.subject)
    else:
        result = collector.uninstall(args.workspace)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    configure_logging()
    argv = sys.argv[1:]
    if argv and argv[0] in {"collect", "export", "erase", "uninstall"}:
        try:
            return _run_headless(argv)
        except Exception as exc:  # noqa: BLE001 — CLI must fail truthfully
            json.dump({"error": str(exc)}, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 1
    from .orphan import monitor_from_environment
    from .rpc import FramedReader, FramedWriter
    from .server import SidecarServer

    server = SidecarServer()
    # FR-M3-03: second half of the dual teardown contract. If the extension
    # host dies without closing our stdin, the monitor self-terminates us.
    monitor_from_environment(on_orphaned=server.shutdown_requested)
    server.serve(
        FramedReader(sys.stdin.buffer),
        FramedWriter(sys.stdout.buffer),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
