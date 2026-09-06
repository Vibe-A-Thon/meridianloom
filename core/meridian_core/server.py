"""JSON-RPC method dispatch for the Meridian Core sidecar.

The server is a plain object so tests can drive it without real stdio:
``handle_message`` maps one decoded frame to zero or one response frame.
``serve`` is the production loop over stdin/stdout.

FR-M32-09: handler signatures are typed with the generated bus types
(shared/py/bus_types.py, from shared/schema/). Lifecycle and observer
methods are real; loop and gate methods are registered placeholders that
answer with the contracted NOT_IMPLEMENTED error until later phases fill
them in.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import logging
import os
import platform
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import bus_types

from . import doctor, protocol, tiers
from .attribution import blame, diff as attribution_diff, wire as attribution_wire
from .attribution import symbols as symbols_mod
from .attribution import heuristics
from .attribution import AttributionError
from .attribution._git import normalise_repo_path as attribution_normalise
from . import hooks as provenance_hooks
from . import metrics as metrics_mod
from . import rejection as rejection_mod
from .ledger import core as ledger_core
from .ledger import keys as ledger_keys
from .ledger import wire as ledger_wire
from .observers import claude as observer_claude
from .observers import copilot as observer_copilot
from .observers import manager as observer_manager
from .observers import sessions as observer_sessions
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

    def __init__(self, ledger: ledger_core.Ledger | None = None) -> None:
        self._started_at = time.monotonic()
        self._shutdown_requested = threading.Event()
        self._ping_seq = 0
        # FR-M36-05: enabled tiers default to the base tier only; the
        # handshake and tiers/set notifications widen the set (G5).
        self._enabled_tiers = tiers.normalise_enabled_tiers(None)
        # FR-M10-01/SEC-06: the ledger lives in the workspace and its
        # signing key is provisioned over the handshake. Either may be
        # injected directly by tests instead.
        self._ledger = ledger
        self._workspace_dir: str | None = None
        self._signing_seed: bytes | None = None
        # FR-M35-08/X-29: the observer manager exists from boot (cheap,
        # credential-free constructors); the session monitor thread starts
        # once the handshake carries a workspace. Observer IO happens only
        # on the monitor thread — observe/* RPCs read its cache (NFR-29).
        self._observers = observer_manager.ObserverManager(
            [
                observer_claude.ClaudeCodeObserver(),
                observer_copilot.CopilotObserver(),
            ]
        )
        self._session_monitor: observer_sessions.SessionMonitor | None = None
        self._handlers: dict[str, Handler] = {
            "handshake": SidecarServer._handle_handshake,
            "ping": SidecarServer._handle_ping,
            "shutdown": SidecarServer._handle_shutdown,
            "health": SidecarServer._handle_health,
            "doctor/run": SidecarServer._handle_doctor_run,
            "observe/sessions": SidecarServer._handle_observe_sessions,
            "observe/health": SidecarServer._handle_observe_health,
            "attrib/blame": SidecarServer._handle_attrib_blame,
            "attrib/diff": SidecarServer._handle_attrib_diff,
            "attrib/symbol": SidecarServer._handle_attrib_symbol,
            "attrib/classify": SidecarServer._handle_attrib_classify,
            "ledger.append": SidecarServer._handle_ledger_append,
            "ledger.query": SidecarServer._handle_ledger_query,
            "ledger.getEntry": SidecarServer._handle_ledger_get_entry,
            "ledger.verify": SidecarServer._handle_ledger_verify,
            "ledger.proof": SidecarServer._handle_ledger_proof,
            "ledger.exportBundle": SidecarServer._handle_ledger_export_bundle,
            "hook/install": SidecarServer._handle_hook_install,
            "hook/status": SidecarServer._handle_hook_status,
            "hook/remove": SidecarServer._handle_hook_remove,
            "hook/pending": SidecarServer._handle_hook_pending,
            "trailers/parse": SidecarServer._handle_trailers_parse,
            "trust/detectRejections": SidecarServer._handle_trust_detect_rejections,
            "trust/classify": SidecarServer._handle_trust_classify,
            "loop.start": lambda self, params: self._not_implemented("loop.start", "F3 (Orchestra)"),
            "loop.stop": lambda self, params: self._not_implemented("loop.stop", "F3 (Orchestra)"),
            "loop.status": lambda self, params: self._not_implemented("loop.status", "F3 (Orchestra)"),
            "gate.evaluate": lambda self, params: self._not_implemented("gate.evaluate", "F1 (Governor)"),
            "steer.send": lambda self, params: self._not_implemented("steer.send", "F1 (Governor)"),
            "trust.summary": lambda self, params: self._not_implemented("trust.summary", "F1 (Governor)"),
        }
        # The registry must exactly cover the contracted request methods.
        assert set(self._handlers) == set(bus_types.REQUEST_METHODS), (
            f"handler registry drifted from the schema: "
            f"missing={set(bus_types.REQUEST_METHODS) - set(self._handlers)}, "
            f"extra={set(self._handlers) - set(bus_types.REQUEST_METHODS)}"
        )
        # FR-M36-05: every contracted method must be owned by exactly one
        # capability, or the tier gate has a hole.
        claims = [
            method
            for capability in bus_types.CAPABILITIES
            for method in capability["rpcMethods"]
        ]
        assert len(claims) == len(set(claims)) and set(claims) == set(
            bus_types.REQUEST_METHODS
        ), (
            "tier registry drifted from the schema: every request method must "
            "be owned by exactly one capability in shared/schema/tiers.json"
        )

    @property
    def shutdown_requested(self) -> threading.Event:
        """Set when the peer asked us to exit (or stdin closed, task 7)."""
        return self._shutdown_requested

    @property
    def enabled_tiers(self) -> set[str]:
        """FR-M36-05: the current enabled tier set (exposed for tests)."""
        return set(self._enabled_tiers)

    @property
    def ledger(self) -> ledger_core.Ledger | None:
        """The open ledger, or None until a ledger RPC touches it (tests
        may inject one via the constructor)."""
        return self._ledger

    def _ensure_ledger(self) -> ledger_core.Ledger:
        """Open the ledger lazily on the first ledger RPC (FR-M10-01).

        Requires workspaceDir from the handshake; without it the RPC
        answers LEDGER_UNAVAILABLE — a configuration error, not a crash.
        """
        if self._ledger is None:
            if not self._workspace_dir:
                raise _RpcError(
                    protocol.ERROR_LEDGER_UNAVAILABLE,
                    "no workspace configured: the handshake must carry "
                    "workspaceDir before ledger methods are usable",
                )
            provider: ledger_keys.SigningKeyProvider
            if self._signing_seed is not None:
                provider = ledger_keys.ProvisionedSigningKeyProvider(self._signing_seed)
            else:
                logger.warning("no ledgerSigningKey provisioned: ephemeral signer")
                provider = ledger_keys.EphemeralSigningKeyProvider()
            self._ledger = ledger_core.Ledger(
                Path(self._workspace_dir) / ".meridian" / "ledger", provider
            )
        return self._ledger

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
            # Notification: $/cancel is accepted (the cancelled request will
            # simply be dropped when loops exist); tiers/set re-configures the
            # enabled tier set (FR-M36-05); anything else is ignored.
            if method == "tiers/set":
                new_tiers = (message.get("params") or {}).get("tiers")
                self._enabled_tiers = tiers.normalise_enabled_tiers(new_tiers)
                logger.info("enabled tiers now: %s", sorted(self._enabled_tiers))
            elif method != "$/cancel":
                logger.debug("ignoring unknown notification %s", method)
            return None
        # FR-M36-05: the tier gate runs before dispatch. A method owned by a
        # disabled tier is refused with a structured, actionable error; a
        # method nobody owns falls through to METHOD_NOT_FOUND.
        if not tiers.is_method_enabled(method, self._enabled_tiers):
            return make_error_response(
                request_id,
                protocol.ERROR_TIER_DISABLED,
                tiers.tier_disabled_message(method),
                tiers.tier_disabled_data(method, self._enabled_tiers),
            )
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

    def _handle_handshake(
        self, params: bus_types.HandshakeParams
    ) -> bus_types.HandshakeResult:
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
        # FR-M36-05: adopt the workspace's enabled tiers (clamped to known
        # tiers plus the always-on base tier).
        self._enabled_tiers = tiers.normalise_enabled_tiers((params or {}).get("tiers"))
        # FR-M10-01: the workspace path locates the ledger and feeds the
        # X-29 session monitor.
        workspace_dir = (params or {}).get("workspaceDir")
        if isinstance(workspace_dir, str) and workspace_dir:
            self._workspace_dir = workspace_dir
            self._ensure_session_monitor()
        # FR-M10-04/SEC-06: signing-key material arrives from the OS-keychain
        # (host-side SecretStorage) as a base64 32-byte seed. Decoded here
        # once, held in memory only, and rejected if malformed rather than
        # silently downgrading the signer.
        seed_b64 = (params or {}).get("ledgerSigningKey")
        if seed_b64 is not None:
            try:
                seed = base64.b64decode(seed_b64, validate=True)
            except (binascii.Error, ValueError) as error:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "ledgerSigningKey is not valid base64",
                ) from error
            if len(seed) != ledger_keys.SEED_BYTES:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "ledgerSigningKey must decode to a 32-byte Ed25519 seed",
                    data={"decodedBytes": len(seed)},
                )
            self._signing_seed = seed
        logger.info("enabled tiers: %s", sorted(self._enabled_tiers))
        return {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "coreVersion": protocol.CORE_VERSION,
            "pythonVersion": platform.python_version(),
            "capabilities": {
                "methods": sorted(self._handlers),
                "framing": "ndjson",
            },
        }

    def _handle_ping(self, params: bus_types.PingParams) -> bus_types.PingResult:
        self._ping_seq += 1
        return {
            "pong": True,
            "seq": self._ping_seq,
            "uptimeSeconds": round(time.monotonic() - self._started_at, 3),
        }

    def _handle_shutdown(
        self, params: bus_types.ShutdownParams
    ) -> bus_types.ShutdownResult:
        logger.info("shutdown requested: %s", (params or {}).get("reason", "no reason"))
        if self._session_monitor is not None:
            self._session_monitor.stop()
        self._shutdown_requested.set()
        return {"ok": True}

    def _handle_health(self, params: bus_types.HealthParams) -> bus_types.HealthResult:
        return {
            "status": "shutting-down" if self._shutdown_requested.is_set() else "ok",
            "uptimeSeconds": round(time.monotonic() - self._started_at, 3),
            "pid": os.getpid(),
            "activeLoops": 0,  # loops land in Workstream E
        }

    def _handle_doctor_run(
        self, params: bus_types.DoctorRunParams
    ) -> bus_types.DoctorRunResult:
        # FR-M30-01. The context wires in the subsystems that exist; the
        # not-yet-built ones (trailer hook installer) take the registry's
        # not-installed path with remediation instead of failing.
        context = doctor.DoctorContext(
            started_at=self._started_at,
            # FR-M35-08: the real observer manager, not a stub.
            observer_health=self._observers.health,
        )
        if self._ledger is not None:
            # FR-M10-04/FR-M10-09: real probes once the ledger is open.
            ledger = self._ledger
            context = dataclasses.replace(
                context,
                signing_key_present=lambda: self._signing_seed is not None,
                ledger_verifier=lambda: self._verify_for_doctor(ledger),
            )
        try:
            return doctor.run_doctor(params, context)
        except doctor.UnknownCheckError as error:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                str(error),
                data={"validChecks": doctor.check_ids()},
            ) from error

    def _ensure_session_monitor(self) -> observer_sessions.SessionMonitor:
        """Start the X-29 session monitor once a workspace is known.

        All observer IO runs on the monitor thread; RPC handlers only ever
        read its cache (NFR-29 — observation never blocks the caller).
        """
        if self._session_monitor is None:
            assert self._workspace_dir is not None
            self._session_monitor = observer_sessions.SessionMonitor(
                self._observers, self._workspace_dir
            )
            self._session_monitor.start()
        return self._session_monitor

    def _handle_observe_sessions(
        self, params: bus_types.ObserveSessionsParams
    ) -> bus_types.ObserveSessionsResult:
        # X-29: served from the monitor's cache — never blocks on observer
        # IO (a slow gh probe or OTLP parse cannot delay this response).
        monitor = self._session_monitor
        if monitor is None or not monitor.running:
            return {
                "sessions": [],
                "warnings": [
                    "session observation not started — no workspaceDir handshake yet"
                ],
            }
        snapshot = monitor.snapshot()
        return {"sessions": snapshot["sessions"], "warnings": snapshot["warnings"]}

    def _handle_observe_health(
        self, params: bus_types.ObserveHealthParams
    ) -> bus_types.ObserveHealthResult:
        # FR-M35-08: pure in-memory health records; safe to compute inline.
        return {
            "observers": self._observers.health(),
            "monitorRunning": bool(
                self._session_monitor and self._session_monitor.running
            ),
        }

    @staticmethod
    def _verify_for_doctor(ledger: ledger_core.Ledger) -> tuple[bool, str]:
        # Prefer the verdict from ledger open (FR-M10-09 runs there); run
        # on demand only when the ledger changed since.
        result = ledger.last_verify or ledger.verify()
        return result.ok, result.detail

    def _not_implemented(self, method: str, lands_with: str) -> None:
        raise _RpcError(
            protocol.ERROR_NOT_IMPLEMENTED,
            f"{method} is contracted but not implemented yet (lands with {lands_with})",
        )

    # -- attribution (FR-M33-02 subset, F0 Workstream C) ----------------------

    def _attrib_repo_path(self, params: dict[str, Any]) -> str:
        repo_path = (params or {}).get("repoPath") or self._workspace_dir
        if not repo_path:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "attrib methods need repoPath (or a workspaceDir handshake)",
            )
        return repo_path

    @staticmethod
    def _attrib_error(error: AttributionError) -> _RpcError:
        return _RpcError(protocol.INVALID_PARAMS, str(error))

    def _handle_attrib_blame(
        self, params: bus_types.AttribBlameParams
    ) -> bus_types.AttribBlameResult:
        params = params or {}
        try:
            repo, lines = blame.blame_with_repo(
                self._attrib_repo_path(params),
                ref=params.get("ref") or "HEAD",
                paths=params.get("paths"),
            )
        except AttributionError as error:
            raise self._attrib_error(error) from error
        return {
            "repoPath": str(repo),
            "ref": params.get("ref") or "HEAD",
            "lines": attribution_wire.blame_lines_to_wire(lines),
        }

    def _handle_attrib_diff(
        self, params: bus_types.AttribDiffParams
    ) -> bus_types.AttribDiffResult:
        params = params or {}
        base = params.get("base")
        compare = params.get("compare")
        staged = bool(params.get("staged"))
        try:
            repo, files = attribution_diff.diff_with_repo(
                self._attrib_repo_path(params),
                base=base,
                compare=compare,
                staged=staged,
                paths=params.get("paths"),
            )
        except AttributionError as error:
            raise self._attrib_error(error) from error
        return {
            "repoPath": str(repo),
            "base": base,
            "compare": compare,
            "staged": staged,
            "files": attribution_wire.file_diffs_to_wire(files),
        }

    def _handle_attrib_symbol(
        self, params: bus_types.AttribSymbolParams
    ) -> bus_types.AttribSymbolResult:
        params = params or {}
        line = params.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise _RpcError(
                protocol.INVALID_PARAMS, "line must be a positive integer"
            )
        raw_path = params.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise _RpcError(
                protocol.INVALID_PARAMS, "path must be a worktree-relative file"
            )
        try:
            repo = self._ensure_attrib_repo(params)
            rel = attribution_normalise(repo, raw_path)
            result = symbols_mod.symbol_at(repo / rel, line)
        except AttributionError as error:
            raise self._attrib_error(error) from error
        except symbols_mod.SymbolsError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        return {
            "path": rel,
            "line": line,
            "language": result.language,
            "symbol": result.symbol,
        }

    def _ensure_attrib_repo(self, params: dict[str, Any]) -> Path:
        from .attribution._git import ensure_repo

        return ensure_repo(Path(self._attrib_repo_path(params)))

    def _handle_attrib_classify(
        self, params: bus_types.AttribClassifyParams
    ) -> bus_types.AttribClassifyResult:
        params = params or {}
        try:
            repo, result = heuristics.classify_with_repo(
                self._attrib_repo_path(params),
                base=params.get("base"),
                compare=params.get("compare"),
                staged=bool(params.get("staged")),
                paths=params.get("paths"),
                observed_sessions=params.get("observedSessions"),
            )
        except AttributionError as error:
            raise self._attrib_error(error) from error
        return {
            "repoPath": str(repo),
            "files": [
                {
                    "path": file.path,
                    "linesAdded": file.lines_added,
                    "linesRemoved": file.lines_removed,
                    "burstLines": file.burst_lines,
                    "multiLineInsertRate": file.multi_line_insert_rate,
                    "editTimestamp": file.edit_timestamp,
                    "attribution": file.attribution,
                    "agentWeight": file.agent_weight,
                    "observationConfidence": file.observation_confidence,
                    "rationale": file.rationale,
                }
                for file in result.files
            ],
        }

    # -- provenance hook (FR-M36-03, D23; F0 Workstream E tasks 23-24) --------

    def _hook_repo(self, params: dict[str, Any]) -> Path:
        workspace = (params or {}).get("workspaceDir") or self._workspace_dir
        if not workspace:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "hook methods need workspaceDir (param or handshake)",
            )
        try:
            return provenance_hooks.ensure_repo(Path(workspace))
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    def _handle_hook_install(
        self, params: bus_types.HookInstallParams
    ) -> bus_types.HookInstallResult:
        try:
            return provenance_hooks.install(
                self._hook_repo(params), python=sys.executable or None
            )  # type: ignore[return-value]
        except provenance_hooks.HookError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    def _handle_hook_status(
        self, params: bus_types.HookStatusParams
    ) -> bus_types.HookStatusResult:
        workspace = (params or {}).get("workspaceDir") or self._workspace_dir
        if not workspace:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "hook/status needs workspaceDir (param or handshake)",
            )
        return provenance_hooks.status(Path(workspace))  # type: ignore[return-value]

    def _handle_hook_remove(
        self, params: bus_types.HookRemoveParams
    ) -> bus_types.HookRemoveResult:
        try:
            return provenance_hooks.remove(self._hook_repo(params))  # type: ignore[return-value]
        except provenance_hooks.HookError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    def _handle_hook_pending(
        self, params: bus_types.HookPendingParams
    ) -> bus_types.HookPendingResult:
        params = params or {}
        try:
            return provenance_hooks.record_pending(
                self._hook_repo(params),
                params.get("stagedHash", ""),
                params.get("fromSequence", 0),
                params.get("toSequence", 0),
                recorded_at=params.get("recordedAt"),
            )
        except provenance_hooks.HookError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    def _handle_trailers_parse(
        self, params: bus_types.TrailersParseParams
    ) -> bus_types.TrailersParseResult:
        """FR-M36-03 (task 24): agent-identity trailers as attribution records.

        Either a raw `message` (parsed directly, no repository) or a git
        walk over repoPath/ref/since, in the newest-first log order.
        """
        params = params or {}
        from . import trailers as trailers_mod

        def commit_payload(
            commit: str | None,
            authored_at: str | None,
            body: str,
        ) -> bus_types.TrailerCommit:
            return {
                "commit": commit,
                "authoredAt": authored_at,
                "attributions": trailers_mod.parse_attributions(body),
                "meridianLedger": [
                    value
                    for key, value in trailers_mod.parse_trailers(body)
                    if key == trailers_mod.MERIDIAN_LEDGER_KEY
                ],
            }

        message = params.get("message")
        if message is not None:
            if not isinstance(message, str):
                raise _RpcError(protocol.INVALID_PARAMS, "message must be a string")
            return {"commits": [commit_payload(None, None, message)]}

        try:
            repo = self._ensure_attrib_repo(params)
        except AttributionError as error:
            raise self._attrib_error(error) from error
        ref = params.get("ref") or "HEAD"
        log_args = ["log", f"--format=%H%x1f%cI%x1f%B%x1e"]
        since = params.get("since")
        if since:
            log_args.append(f"--since={since}")
        log_args.append(ref)
        try:
            log = provenance_hooks.run_git(repo, *log_args)
        except Exception as error:  # noqa: BLE001 - bad ref/since: actionable error
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"cannot read commit messages from {repo}: {error}",
            ) from error
        commits: list[bus_types.TrailerCommit] = []
        for record in log.split("\x1e"):
            record = record.strip("\n")
            if not record.strip():
                continue
            fields = record.split("\x1f", 2)
            if len(fields) < 3:
                continue
            commit, authored_at, body = fields
            payload = commit_payload(commit.strip(), authored_at.strip(), body)
            # Commits carrying no trailer facts are not provenance evidence;
            # the stream stays limited to what actually attributes.
            if payload["attributions"] or payload["meridianLedger"]:
                commits.append(payload)
        return {"commits": commits}

    # -- rejection capture (FR-M37-01 subset, F0 Workstream F task 28) --------

    def _handle_trust_detect_rejections(
        self, params: bus_types.TrustDetectRejectionsParams
    ) -> bus_types.TrustDetectRejectionsResult:
        """Detect rejections from git history and record each in the ledger.

        Detection is pure git attribution (zero model calls, FR-M36-07) and
        idempotent: a rejection whose (rejectedCommit, rejectingCommit,
        reason, repoId) already exists in the ledger is reported with
        alreadyRecorded=True and never double-appended.
        """
        params = params or {}
        window_days = params.get("windowDays")
        if window_days is None:
            window_days = rejection_mod.DEFAULT_REJECTION_WINDOW_DAYS
        if (
            not isinstance(window_days, int)
            or isinstance(window_days, bool)
            or not 1 <= window_days <= 3650
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"windowDays must be an integer between 1 and 3650, got {window_days!r}",
            )
        ref = params.get("ref") or "HEAD"
        base = params.get("base")
        try:
            repo = self._ensure_attrib_repo({"repoPath": params.get("repoPath")})
            rejections = rejection_mod.detect(
                repo, base=base, ref=ref, window_days=window_days
            )
        except AttributionError as error:
            raise self._attrib_error(error) from error

        ledger = self._ensure_ledger()
        repo_id = params.get("repoId") or repo.name
        # Idempotency: rejection entries already recorded for this repo.
        existing = ledger.query(action_type="rejection", limit=1000)
        known: dict[tuple, int] = {}
        for row in existing:
            key = (
                row.get("rejected_commit"),
                row.get("rejecting_commit"),
                row.get("rework_reason"),
                row.get("repo_id"),
            )
            known[key] = row["seq"]

        wire: list[bus_types.TrustRejection] = []
        recorded = 0
        duplicates = 0
        for rejection in rejections:
            key = (
                rejection.rejected_commit,
                rejection.rejecting_commit,
                rejection.reason,
                repo_id,
            )
            if key in known:
                duplicates += 1
                wire.append(
                    self._rejection_wire(rejection, None, known[key], True)
                )
                continue
            rejected_sequence = rejection_mod.resolve_ledger_sequence(
                repo, rejection.rejected_commit
            )
            source = (
                ledger.get_entry(rejected_sequence) if rejected_sequence else None
            )
            # The rejection entry inherits the rejected entry's story and
            # actor when the trailer link resolves; otherwise the caller's
            # fallbacks (an untracked external change).
            entry = {
                "story_id": (source or {}).get("story_id")
                or params.get("storyId")
                or "untracked",
                "phase": (source or {}).get("phase") or "review",
                "loop_id": "rejection",
                "loop_iteration": 0,
                "actor_id": (source or {}).get("actor_id")
                or params.get("actorId")
                or "unknown",
                "actor_version": (source or {}).get("actor_version")
                or params.get("actorVersion")
                or "0",
                "actor_kind": (source or {}).get("actor_kind")
                or params.get("actorKind")
                or "external",
                "policy_version": (source or {}).get("policy_version")
                or params.get("policyVersion")
                or "f0",
                "vendor": (source or {}).get("vendor") or "meridian",
                "action_type": "rejection",
                "decision": "rejected",
                "rework_reason": rejection.reason,
                "rejected_sequence": rejected_sequence,
                "rejected_commit": rejection.rejected_commit,
                "rejecting_commit": rejection.rejecting_commit,
                "repo_id": repo_id,
                "tool_calls": [
                    {
                        "paths": list(rejection.paths),
                        "linesRejected": rejection.lines_rejected,
                        "rejectedAt": rejection.rejected_at,
                    }
                ],
            }
            try:
                result = ledger.append(entry)
            except (ValueError, sqlite3.IntegrityError) as error:
                raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
            known[key] = result.sequence
            recorded += 1
            wire.append(
                self._rejection_wire(rejection, rejected_sequence, result.sequence, False)
            )
        return {
            "repoPath": str(repo),
            "ref": ref,
            "windowDays": window_days,
            "rejections": wire,
            "recorded": recorded,
            "duplicatesSkipped": duplicates,
        }

    @staticmethod
    def _rejection_wire(
        rejection: rejection_mod.Rejection,
        rejected_sequence: int | None,
        recorded_sequence: int | None,
        already_recorded: bool,
    ) -> bus_types.TrustRejection:
        return {
            "rejectedCommit": rejection.rejected_commit,
            "rejectingCommit": rejection.rejecting_commit,
            "reason": rejection.reason,  # type: ignore[typeddict-item]
            "paths": list(rejection.paths),
            "linesRejected": rejection.lines_rejected,
            "rejectedAt": rejection.rejected_at,
            "rejectedSequence": rejected_sequence,
            "recordedSequence": recorded_sequence,
            "alreadyRecorded": already_recorded,
        }

    # -- greenfield/brownfield classification (FR-M37-06, task 29) ------------

    def _handle_trust_classify(
        self, params: bus_types.TrustClassifyParams
    ) -> bus_types.TrustClassifyResult:
        params = params or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        if ratio_threshold is None:
            ratio_threshold = metrics_mod.DEFAULT_NEW_FILE_RATIO_THRESHOLD
        max_age_days = params.get("maxMedianAgeDays")
        if max_age_days is None:
            max_age_days = metrics_mod.DEFAULT_MAX_MEDIAN_AGE_DAYS
        try:
            repo = self._ensure_attrib_repo({"repoPath": params.get("repoPath")})
            result = metrics_mod.classify(
                repo,
                commits=params.get("commits"),
                base=params.get("base"),
                compare=params.get("compare"),
                new_file_ratio_threshold=ratio_threshold,
                max_median_age_days=max_age_days,
            )
        except AttributionError as error:
            raise self._attrib_error(error) from error
        return {
            "repoPath": str(repo),
            "newFiles": result.new_files,
            "modifiedFiles": result.modified_files,
            "newFileRatio": result.new_file_ratio,
            "medianTouchedCodeAgeDays": result.median_touched_code_age_days,
            "classification": result.classification,  # type: ignore[typeddict-item]
            "thresholds": {
                "newFileRatioThreshold": ratio_threshold,
                "maxMedianAgeDays": max_age_days,
            },
        }

    # -- ledger (FR-M10-01/02/07/08/12) -------------------------------------

    def _handle_ledger_append(
        self, params: bus_types.LedgerAppendParams
    ) -> bus_types.LedgerAppendResult:
        # FR-M10-08: Ledger.append commits (WAL, synchronous=FULL) before
        # returning, and this response goes out only after that — an acked
        # append survives a kill -9 (tested in test_ledger_verify.py).
        ledger = self._ensure_ledger()
        entry = ledger_wire.append_params_to_entry(params or {})
        try:
            result = ledger.append(entry)
        except ValueError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        except sqlite3.IntegrityError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        return {
            "sequence": result.sequence,
            "hash": result.entry_hash.hex(),
            "previousHash": result.prev_hash.hex(),
            "timestamp": result.ts_utc,
            **({"treeHead": result.tree_head} if result.tree_head else {}),
        }

    def _handle_ledger_query(
        self, params: bus_types.LedgerQueryParams
    ) -> bus_types.LedgerQueryResult:
        ledger = self._ensure_ledger()
        rows = ledger.query(
            story_id=(params or {}).get("storyId"),
            actor_id=(params or {}).get("actorId"),
            vendor=(params or {}).get("vendor"),
            action_type=(params or {}).get("actionType"),
            from_sequence=(params or {}).get("fromSequence"),
            to_sequence=(params or {}).get("toSequence"),
            from_timestamp=(params or {}).get("fromTimestamp"),
            to_timestamp=(params or {}).get("toTimestamp"),
            limit=(params or {}).get("limit") or 100,
        )
        return {"entries": [ledger_wire.row_to_wire(row) for row in rows]}

    def _handle_ledger_get_entry(
        self, params: bus_types.LedgerGetEntryParams
    ) -> bus_types.LedgerGetEntryResult:
        ledger = self._ensure_ledger()
        sequence = (params or {}).get("sequence")
        row = ledger.get_entry(sequence)
        if row is None:
            raise _RpcError(
                protocol.INVALID_PARAMS, f"no ledger entry at sequence {sequence}"
            )
        return ledger_wire.row_to_detail(row, ledger.read_blob)

    def _handle_ledger_verify(
        self, params: bus_types.LedgerVerifyParams
    ) -> bus_types.LedgerVerifyResult:
        ledger = self._ensure_ledger()
        result = ledger.verify(up_to=(params or {}).get("upTo"))
        return {
            "ok": result.ok,
            "entriesChecked": result.entries_checked,
            "firstDivergentSequence": result.first_divergent_sequence,
            "detail": result.detail,
            "verifiedAt": ledger_core.utc_now(),
        }

    def _handle_ledger_proof(
        self, params: bus_types.LedgerProofParams
    ) -> bus_types.LedgerProofResult:
        from .ledger import merkle as ledger_merkle

        ledger = self._ensure_ledger()
        sequence = (params or {}).get("sequence")
        from_size = (params or {}).get("fromSize")
        to_size = (params or {}).get("toSize")
        if sequence is not None and (from_size is not None or to_size is not None):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "pass either sequence (inclusion) or fromSize+toSize"
                " (consistency), not both",
            )
        if sequence is not None:
            row = ledger.get_entry(sequence)
            if row is None:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"no ledger entry at sequence {sequence}",
                )
            leaves = ledger.leaf_hashes()
            path = ledger_merkle.inclusion_proof(leaves, sequence - 1)
            return {
                "inclusion": {
                    "treeSize": len(leaves),
                    "leafIndex": sequence - 1,
                    "leafHash": row["entry_hash"].hex(),
                    "rootHash": ledger.root_hash().hex(),
                    "path": [node.hex() for node in path],
                }
            }
        if from_size is None or to_size is None:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "ledger.proof needs sequence, or both fromSize and toSize",
            )
        last = ledger.last_sequence
        if not 1 <= from_size <= to_size <= max(last, 1):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"need 1 <= fromSize <= toSize <= {last},"
                f" got fromSize={from_size}, toSize={to_size}",
            )
        leaves = ledger.leaf_hashes()
        to_leaves = leaves[:to_size]
        path = ledger_merkle.consistency_proof(to_leaves, from_size)
        return {
            "consistency": {
                "fromSize": from_size,
                "toSize": to_size,
                "fromRootHash": ledger_merkle.root(leaves[:from_size]).hex(),
                "toRootHash": ledger_merkle.root(to_leaves).hex(),
                "path": [node.hex() for node in path],
            }
        }

    def _handle_ledger_export_bundle(
        self, params: bus_types.LedgerExportBundleParams
    ) -> bus_types.LedgerExportBundleResult:
        # FR-M36-04/SEC-29 (task 25): the full signed audit bundle —
        # assembly lives in ledger/bundle.py so the wire shape, proofs,
        # signature block and compliance section stay testable in isolation.
        ledger = self._ensure_ledger()
        from .ledger import bundle as ledger_bundle

        return ledger_bundle.build_bundle(ledger, params or {})  # type: ignore[return-value]


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
