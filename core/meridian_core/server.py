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
import json
import logging
import os
import platform
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bus_types

from . import doctor, protocol, tiers
from . import identity as authenticated_identity
from .attribution import blame, diff as attribution_diff, wire as attribution_wire
from .attribution import symbols as symbols_mod
from .attribution import heuristics
from .attribution import AttributionError
from .attribution._git import normalise_repo_path as attribution_normalise
from .governance import engine as governance_engine
from .governance import identity as governance_identity
from .governance import merge_gate as governance_merge_gate
from .governance import policy as governance_policy
from .governance import roles as governance_roles
from . import hooks as provenance_hooks
from . import metrics as metrics_mod
from . import rejection as rejection_mod
from .rejection import taxonomy as rejection_taxonomy
from .ledger import core as ledger_core
from .ledger import keys as ledger_keys
from .ledger import wire as ledger_wire
from .pr import ingest as pr_ingest
from .pr import conflicts as pr_conflicts
from .worktree import manager as worktree_mod
from .observers import claude as observer_claude
from .observers import codex as observer_codex
from .observers import copilot as observer_copilot
from .observers import cursor as observer_cursor
from .observers import devin as observer_devin
from .observers import manager as observer_manager
from .observers import sessions as observer_sessions
from .rpc import (
    FramedReader,
    FramedWriter,
    make_error_response,
    make_notification,
    make_response,
)

logger = logging.getLogger("meridian_core.server")

# Method handlers take (server, params) and return a JSON-able result.
Handler = Callable[["SidecarServer", Any], Any]


class SidecarServer:
    """Dispatches framed JSON-RPC requests to method handlers."""

    def __init__(
        self,
        ledger: ledger_core.Ledger | None = None,
        identity_provider: Any | None = None,
        notification_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
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
        # FR-M12-07/FR-M20-01/D9: acting human identity (approver, halting
        # operator, ingesting human) resolves through the identity
        # interface — v1 git user.name/email (assurance "local"), the
        # handshake identityProvider selection, or a test injection. Never
        # a free-text param (FR-M20-01).
        self._identity_provider = identity_provider
        # FR-M12-06: sidecar -> host notifications (gate/halt dispatch) ride
        # the same framed writer as responses; serve() installs the writer
        # here, tests inject a capture callable.
        self._notification_sink = notification_sink
        self._workspace_dir: str | None = None
        self._signing_seed: bytes | None = None
        # FR-M17-05: trust metrics derive from the ledger and cache
        # in-process; the cache is invalidated on every append below.
        self._trust_cache = metrics_mod.TrustMetricsCache()
        # FR-M35-08/X-29: the observer manager exists from boot (cheap,
        # credential-free constructors); the session monitor thread starts
        # once the handshake carries a workspace. Observer IO happens only
        # on the monitor thread — observe/* RPCs read its cache (NFR-29).
        self._observers = observer_manager.ObserverManager(
            [
                observer_claude.ClaudeCodeObserver(),
                observer_copilot.CopilotObserver(),
                # FR-M35-08/D20 (F1 Workstream G task 30): Cursor, Codex and
                # Devin observe at inferred-confidence floor (telemetry at
                # best) — no first-party telemetry surface is parseable.
                observer_cursor.CursorObserver(),
                observer_codex.CodexObserver(),
                observer_devin.DevinObserver(),
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
            "trust/rejectionRate": SidecarServer._handle_trust_rejection_rate,
            "trust/reasonDistribution": SidecarServer._handle_trust_reason_distribution,
            "trust/score": SidecarServer._handle_trust_score,
            "trust/scoreDecomposition": SidecarServer._handle_trust_score,
            "trust/compareAgents": SidecarServer._handle_trust_compare_agents,
            "trust/jcurve": SidecarServer._handle_trust_jcurve,
            "trust/tokenmaxxing": SidecarServer._handle_trust_tokenmaxxing,
            "trust/doraExport": SidecarServer._handle_trust_dora_export,
            # FR-M39-01/02/03/04 (F1 Workstream F tasks 26-29): cross-vendor
            # spend — the real feed onto the SpendSeries protocol, config-
            # driven ceilings (pause hosted / warn observed), the monthly
            # forecast + budget alert, and the predictable pricing table.
            "spend/series": SidecarServer._handle_spend_series,
            "spend/ceilingCheck": SidecarServer._handle_spend_ceiling_check,
            "spend/forecast": SidecarServer._handle_spend_forecast,
            "spend/pricing": SidecarServer._handle_spend_pricing,
            "loop.start": lambda self, params: self._not_implemented("loop.start", "F3 (Orchestra)"),
            "loop.stop": lambda self, params: self._not_implemented("loop.stop", "F3 (Orchestra)"),
            "loop.status": lambda self, params: self._not_implemented("loop.status", "F3 (Orchestra)"),
            "gate.evaluate": SidecarServer._handle_gate_evaluate,
            "gate.profiles": SidecarServer._handle_gate_profiles,
            "gate.approve": SidecarServer._handle_gate_approve,
            "gate.status": SidecarServer._handle_gate_status,
            "gate.halt": SidecarServer._handle_gate_halt,
            # FR-M35-04/05 (F1 Workstream B task 12): external PR gating —
            # a PR payload (gh-api shape, sourced from the M23 SCM connectors
            # in production, injected fixtures in tests) becomes a Meridian
            # story: origin record, per-agent attributed hunks, and routing
            # through the Verify/Security/Review gate profiles. Merge is
            # permitted only via the merge gate with a recorded approval.
            "pr/ingest": SidecarServer._handle_pr_ingest,
            "pr/status": SidecarServer._handle_pr_status,
            # FR-M35-07 (F1 Workstream B task 13): multi-agent conflict
            # detection — per-hunk agent attribution over a commit range,
            # agent-vs-agent conflicts surfaced as the distinct rework
            # class agent-conflict and ledger-recorded (FR-M10-08).
            "pr/conflicts": SidecarServer._handle_pr_conflicts,
            # FR-M25-01/02/03/04/06 (F1 Workstream D task 17): steer &
            # clarify over hosted ACP sessions — the durable half of the
            # M25 steering surface. The extension host owns the wire; the
            # sidecar owns the record, and every entry lands BEFORE the
            # RPC returns (FR-M10-08).
            "steer.send": SidecarServer._handle_steer_send,
            "steer/question": SidecarServer._handle_steer_question,
            "steer/answer": SidecarServer._handle_steer_answer,
            "steer/escalate": SidecarServer._handle_steer_escalate,
            "steer/accept": SidecarServer._handle_steer_accept,
            "steer/acceptanceStatus": SidecarServer._handle_steer_acceptance_status,
            # F1 Workstream D task 18: the honest capability payload —
            # hosted: false for observed sessions so a dead control is
            # impossible by construction.
            "steer/status": SidecarServer._handle_steer_status,
            "steer/plan": SidecarServer._handle_steer_plan,
            "trust.summary": lambda self, params: self._not_implemented("trust.summary", "F1 (Governor)"),
            # FR-M34-01/02/04 (F1 Workstream A task 4): hosted-session ledger
            # recording — the extension-host ACP client reports session facts
            # and the sidecar makes them durable (see the handlers below).
            "acp/sessionBegin": SidecarServer._handle_acp_session_begin,
            "acp/sessionEnd": SidecarServer._handle_acp_session_end,
            "acp/permissionDecision": SidecarServer._handle_acp_permission_decision,
            # FR-M18-01..08 (F1 Workstream A task 5): worktree isolation for
            # hosted agents — creation/removal/abort are ledger-recorded with
            # worktree_ref set; conflicts is the pre-flight report (FR-M18-03)
            # the RunRequest/preflight flow (M40) consumes before a packet.
            "worktree/create": SidecarServer._handle_worktree_create,
            "worktree/list": SidecarServer._handle_worktree_list,
            "worktree/remove": SidecarServer._handle_worktree_remove,
            "worktree/abortStory": SidecarServer._handle_worktree_abort_story,
            "worktree/conflicts": SidecarServer._handle_worktree_conflicts,
            # FR-M34-06 (F1 Workstream A task 6): the MCP server gateway —
            # the standalone MCP server process forwards each tools/call as
            # one mcp/invoke; the tier gate is the permission gate, the call
            # is ledger-recorded before it runs, and the tool maps onto the
            # existing read-only handler (see the handler below).
            "mcp/invoke": SidecarServer._handle_mcp_invoke,
            # FR-M20-02…08 (F1 Workstream C task 16): the role pack — who
            # may approve/halt/change policy (roles/list, roles/check), and
            # approval-right delegation with expiry, recorded in the ledger
            # (roles/delegate). The merge gate consumes the same pack for
            # N-of-M thresholds, SoD exclusion and role filtering.
            "roles/list": SidecarServer._handle_roles_list,
            "roles/check": SidecarServer._handle_roles_check,
            "roles/delegate": SidecarServer._handle_roles_delegate,
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
        # FR-M12-06: gate/halt notifications to the host share the response
        # writer (frames are atomic on the single write path, FR-M3-01).
        self._notification_sink = writer.write_message
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
        # FR-M20-01/D9: the host selects the identity provider over the
        # handshake (same pattern as the signing key): the extension host
        # can see git config today and will hold OIDC tokens in
        # SecretStorage later. Unknown names are an actionable refusal;
        # a test-injected provider still wins over the selection.
        identity_provider = (params or {}).get("identityProvider")
        if identity_provider is not None:
            if not self._workspace_dir:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "identityProvider needs workspaceDir: the git provider "
                    "resolves user.name/user.email from the workspace repository",
                )
            try:
                selected = authenticated_identity.provider_from_config(
                    identity_provider, Path(self._workspace_dir)
                )
            except authenticated_identity.IdentityProviderError as error:
                raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
            if self._identity_provider is None:
                self._identity_provider = selected
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

    # -- governance policy engine (FR-M12-01/08/09; F1 Workstream B task 9) ---

    def _governance_pack(self, params: dict[str, Any]) -> governance_policy.PolicyPack:
        """Resolve the active policy pack: an explicit policyPath param, then
        the workspace override, then the repository policy directory. A
        missing file is a fail-closed pack, never an error."""
        paths: list[Any] = []
        if params.get("policyPath"):
            paths.append(params["policyPath"])
        if self._workspace_dir:
            workspace = Path(self._workspace_dir)
            paths.append(workspace / ".meridian" / "policy" / "governance.yaml")
            paths.append(workspace / "policy" / "governance.yaml")
        return governance_policy.load_policy_pack(paths)

    def _role_pack(self, params: dict[str, Any]) -> governance_roles.RolePack:
        """FR-M20-02: the active role pack — an explicit rolePath param, then
        the workspace override, then the repository policy directory. A
        missing file yields the built-in default pack; a malformed file
        fails closed (see governance/roles.py)."""
        paths: list[Any] = []
        if params.get("rolePath"):
            paths.append(params["rolePath"])
        if self._workspace_dir:
            workspace = Path(self._workspace_dir)
            paths.append(workspace / ".meridian" / "policy" / "roles.yaml")
            paths.append(workspace / "policy" / "roles.yaml")
        return governance_roles.load_role_pack(paths)

    def _merge_verdict(
        self,
        params: dict[str, Any],
        *,
        subject: str,
        head_commit: str | None,
        requires_approval: bool | None = None,
        approval_subject: str | None = None,
    ) -> governance_merge_gate.MergeVerdict:
        """check_merge with the role pack's mechanics applied (FR-M20-03/04):
        N-of-M threshold, role filtering, and SoD exclusion of the
        ingester's own approval. Read-only."""
        pack = self._governance_pack(params)
        role_pack = self._role_pack(params)
        ledger = self._ensure_ledger()
        n_of_m_subject = approval_subject if approval_subject is not None else subject
        required = 1
        permitted = None
        excluded: set[str] = set()
        if not role_pack.fail_closed:
            required = role_pack.n_of_m.get(n_of_m_subject, 1)
            permitted = role_pack.approving_roles()
            if role_pack.sod_forbid_self_approval:
                ingest = self._find_pr_ingest(ledger, subject)
                if ingest is not None:
                    ingested_by = ingest["detail"].get("ingestedBy")
                    if isinstance(ingested_by, dict):
                        email = str(ingested_by.get("email") or "").strip().lower()
                        if email:
                            excluded.add(email)
        return governance_merge_gate.check_merge(
            ledger,
            pack,
            subject=subject,
            head_commit=head_commit,
            requires_approval=requires_approval,
            required_approvals=required,
            permitted_roles=permitted,
            excluded_identities=excluded,
        )

    def _append_gate_entry(
        self,
        *,
        story_id: str,
        pack: governance_policy.PolicyPack,
        decision: str,
        detail: dict[str, Any],
        action_type: str = "gate",
        human_actor: str | None = None,
        human_role: str | None = None,
        rework_reason: str | None = None,
        actor_kind: str = "meta",
        vendor: str = "meridian",
        observation_confidence: str = "direct",
        run_id: str | None = None,
        origin: str | None = None,
        phase: str = "review",
    ) -> int:
        """FR-M10-08: the gate decision is committed to the ledger BEFORE the
        RPC returns; the encrypted input blob carries the full detail."""
        ledger = self._ensure_ledger()
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": story_id,
            "phase": phase,
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": protocol.CORE_VERSION,
            "actor_kind": actor_kind,
            "policy_version": pack.policy_version,
            "action_type": action_type,
            "decision": decision,
            "vendor": vendor,
            "observation_confidence": observation_confidence,
            "input": json.dumps(detail, ensure_ascii=False),
        }
        if human_actor:
            entry["human_actor"] = human_actor
        if human_role:
            entry["human_role"] = human_role
        if rework_reason is None and detail.get("reasons"):
            rework_reason = "; ".join(detail["reasons"])
        if rework_reason:
            entry["rework_reason"] = rework_reason[:4000]
        if run_id is not None:
            entry["run_id"] = run_id
        if origin is not None:
            entry["origin"] = origin
        result = ledger.append(entry)
        self._trust_cache.invalidate()
        return result.sequence

    def _handle_gate_evaluate(
        self, params: bus_types.GateEvaluateParams
    ) -> bus_types.GateEvaluateResult:
        params = params or {}
        packet = params.get("packet")
        if not isinstance(packet, dict):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "gate.evaluate needs a packet object (the PR/payload to check)",
            )
        story_id = params.get("storyId")
        if not isinstance(story_id, str) or not story_id.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "storyId must be a non-empty string")
        gate = params.get("gate")
        if not isinstance(gate, str) or not gate.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "gate must be a non-empty profile name")
        pack = self._governance_pack(params)
        verdict = governance_engine.evaluate(packet, gate.strip(), pack)
        self._append_gate_entry(
            story_id=story_id.strip(),
            pack=pack,
            decision="approved" if verdict.passed else "rejected",
            detail={
                "method": "gate.evaluate",
                "gate": gate.strip(),
                "packet": packet,
                "criteria": [
                    {
                        "id": c.id,
                        "kind": c.kind,
                        "passed": c.passed,
                        "reason": c.reason,
                    }
                    for c in verdict.criteria
                ],
                "reasons": list(verdict.reasons),
                "failClosed": verdict.fail_closed,
            },
        )
        return {
            "decision": "pass" if verdict.passed else "block",
            "profile": verdict.profile,
            "policyVersion": verdict.policy_version,
            "failClosed": verdict.fail_closed,
            "criteria": [
                {"id": c.id, "kind": c.kind, "passed": c.passed, "reason": c.reason}
                for c in verdict.criteria
            ],
            "reasons": list(verdict.reasons),
        }

    def _handle_gate_profiles(
        self, params: bus_types.GateProfilesParams
    ) -> bus_types.GateProfilesResult:
        pack = self._governance_pack(params or {})
        return {
            "profiles": [
                {
                    "name": profile.name,
                    "description": profile.description,
                    "criteria": [criterion.id for criterion in profile.criteria],
                }
                for profile in pack.profiles.values()
            ],
            "policyVersion": pack.policy_version,
            "failClosed": pack.fail_closed,
            "errors": list(pack.errors),
        }

    # -- merge gate (FR-M12-05/07; F1 Workstream B task 10) -------------------

    # -- human identity (FR-M20-01/D9; F1 Workstream C task 15) -------------

    def _human_identity(self) -> authenticated_identity.ResolvedIdentity:
        """The acting human identity, resolved through the provider.

        FR-M20-01: approver, halting operator and ingesting human all come
        from the identity interface, never a raw string param. Unavailable
        identity is a refusal (FR-M12-07 forbids anonymous approval); the
        OIDC stub's NotImplementedError carries the FR id through verbatim.
        Legacy ``identity()``-shaped providers (governance.identity) are
        still accepted and map onto local assurance.
        """
        provider = self._identity_provider
        if provider is None:
            if not self._workspace_dir:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "human identity unavailable: no workspaceDir handshake "
                    "and no identity provider configured (FR-M12-07: anonymous "
                    "approval is not possible)",
                )
            provider = authenticated_identity.GitIdentityProvider(
                Path(self._workspace_dir)
            )
            self._identity_provider = provider
        resolve = getattr(provider, "resolve", None)
        if callable(resolve):
            try:
                return resolve()
            except (
                authenticated_identity.IdentityUnavailableError,
                NotImplementedError,
            ) as error:
                raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        # Legacy provider shape (pre-FR-M20-01 seam): identity() -> HumanIdentity.
        try:
            human = provider.identity()
        except governance_identity.IdentityUnavailableError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        return authenticated_identity.ResolvedIdentity(
            id=human.email or human.name,
            display_name=human.name or human.email,
            email=human.email,
            assurance="local",
        )

    def _handle_gate_approve(
        self, params: bus_types.GateApproveParams
    ) -> bus_types.GateApproveResult:
        params = params or {}
        subject = params.get("subject")
        commit = params.get("commit")
        if not isinstance(subject, str) or not subject.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "subject must be a non-empty branch name or PR id",
            )
        if not isinstance(commit, str) or not commit.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "commit must be the non-empty head digest the approval binds",
            )
        who = self._human_identity()
        pack = self._governance_pack(params)
        ledger = self._ensure_ledger()
        role_pack = self._role_pack(params)
        role_value = params.get("role")
        role = (
            role_value.strip()
            if isinstance(role_value, str) and role_value.strip()
            else role_pack.default_role
        )
        # FR-M20-02: the acting role must hold the approve permission. An
        # active, unexpired delegation granting this principal the right
        # satisfies the check instead (FR-M20-05).
        permission = governance_roles.check_permission(role_pack, role, "approve")
        if not permission.permitted:
            grant = governance_roles.find_active_delegation(
                ledger, who.email, role, ledger_core.utc_now()
            )
            if grant is None:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    permission.reason,
                    data={
                        "code": "ROLE_NOT_PERMITTED",
                        "role": role,
                        "action": "approve",
                        "permittedRoles": sorted(role_pack.approving_roles()),
                    },
                )
        # FR-M20-03 separation of duties: the identity that ingested the
        # change cannot approve its own merge gate. The refusal names the
        # rule and records nothing.
        if not role_pack.fail_closed and role_pack.sod_forbid_self_approval:
            ingest = self._find_pr_ingest(ledger, subject.strip())
            if ingest is not None:
                ingested_by = ingest["detail"].get("ingestedBy")
                if isinstance(ingested_by, dict) and (
                    str(ingested_by.get("email") or "").strip().lower()
                    == who.email.strip().lower()
                ):
                    raise _RpcError(
                        protocol.INVALID_PARAMS,
                        f"FR-M20-03 separation of duties: {who.display()} "
                        "ingested this change and cannot approve its own "
                        "merge gate",
                        data={
                            "code": "SOD_SELF_APPROVAL",
                            "subject": subject.strip(),
                            "ingester": ingested_by,
                        },
                    )
        # FR-M10-08: the approval is durable BEFORE this response returns.
        sequence = self._append_gate_entry(
            story_id=(params.get("storyId") or f"gate:{subject.strip()}"),
            pack=pack,
            action_type="approval",
            decision="approved",
            human_actor=who.display(),
            human_role=role if isinstance(role, str) and role.strip() else None,
            detail={
                "method": "gate.approve",
                "subject": subject.strip(),
                "commit": commit.strip(),
                "role": role if isinstance(role, str) else None,
                # FR-M20-01: the full provider-resolved identity (with
                # assurance) rides the encrypted detail blob.
                "approver": who.wire(),
            },
        )
        return {
            "recorded": True,
            "sequence": sequence,
            "approver": {"name": who.display_name, "email": who.email},
            "subject": subject.strip(),
            "commit": commit.strip(),
        }

    def _handle_gate_status(
        self, params: bus_types.GateStatusParams
    ) -> bus_types.GateStatusResult:
        params = params or {}
        subject = params.get("subject")
        if not isinstance(subject, str) or not subject.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "subject must be a non-empty branch name or PR id",
            )
        commit = params.get("commit")
        if commit is not None and (not isinstance(commit, str) or not commit.strip()):
            raise _RpcError(
                protocol.INVALID_PARAMS, "commit must be a non-empty digest when given"
            )
        # Read-only: a status query decides and records nothing.
        verdict = self._merge_verdict(
            params, subject=subject.strip(), head_commit=commit.strip() if isinstance(commit, str) else None
        )
        result: bus_types.GateStatusResult = {
            "status": "approved" if verdict.allowed else "blocked",
            "subject": verdict.subject,
            "requiredApproval": verdict.required_approval,
            "halted": verdict.halted,
            "missing": list(verdict.missing),
            # FR-M20-04: the N-of-M threshold and how many distinct
            # approvers the ledger currently holds for this subject.
            "requiredApprovals": verdict.required_approvals,
            "approvalsReceived": len(
                {a.approver.email for a in verdict.approvals if a.approver.email}
            ),
        }
        # FR-M20-06: rubber-stamping signals ride the status payload — the
        # F2 measurement hook. Advisory; they never change the verdict.
        role_pack = self._role_pack(params)
        if not role_pack.fail_closed:
            warnings = governance_roles.assess_hygiene(
                self._ensure_ledger(), role_pack, subject=subject.strip()
            )
            if warnings:
                result["hygieneWarnings"] = warnings
        if verdict.approval is not None:
            result["approvalSequence"] = verdict.approval.sequence
            result["approver"] = {
                "name": verdict.approval.approver.name,
                "email": verdict.approval.approver.email,
            }
        return result

    # -- governance halt (FR-M12-06; F1 Workstream B task 11) -------------------

    #: FR-M12-06: what each scope can enforce. Observe-only agents are never
    #: intercepted (FR-M35-06) — the halt records, blocks merges, warns.
    HALT_SCOPES = ("hosted-session", "merge", "observe-only")

    def _handle_gate_halt(
        self, params: bus_types.GateHaltParams
    ) -> bus_types.GateHaltResult:
        params = params or {}
        reason = params.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, "reason must be a non-empty string"
            )
        scope = params.get("scope")
        if scope not in self.HALT_SCOPES:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"scope must be one of {', '.join(self.HALT_SCOPES)}",
            )
        subject = params.get("subject")
        if subject is not None and (not isinstance(subject, str) or not subject.strip()):
            raise _RpcError(
                protocol.INVALID_PARAMS, "subject must be a non-empty string when given"
            )
        session_id = params.get("sessionId")
        if scope == "hosted-session" and (
            not isinstance(session_id, str) or not session_id.strip()
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "scope hosted-session needs the sessionId to terminate",
            )
        who = self._human_identity()
        pack = self._governance_pack(params)
        detail: dict[str, Any] = {
            "method": "gate.halt",
            "scope": scope,
            "subject": subject.strip() if isinstance(subject, str) else None,
            "sessionId": session_id if isinstance(session_id, str) else None,
            "reason": reason.strip(),
            # FR-M20-01: the halting operator's provider-resolved identity.
            "haltedBy": who.wire(),
        }
        # FR-M10-08: the halt is durable BEFORE any action or response.
        sequence = self._append_gate_entry(
            story_id=f"gate:halt:{subject.strip() if isinstance(subject, str) else 'all'}",
            pack=pack,
            decision="halted",
            human_actor=who.display(),
            rework_reason=reason.strip(),
            detail=detail,
        )
        actions: list[bus_types.GateHaltAction] = []
        warning: str | None = None
        enforceable = True
        subject_desc = detail["subject"] or "all branches"
        if scope == "hosted-session":
            # The kill itself is the extension registry's job (it owns the
            # child process); the sidecar owns the record and the dispatch.
            if self._notification_sink is not None:
                self._notification_sink(
                    make_notification(
                        "gate/halt",
                        {
                            "sequence": sequence,
                            "sessionId": detail["sessionId"],
                            "reason": reason.strip(),
                        },
                    )
                )
            actions.append(
                {
                    "scope": "hosted-session",
                    "action": "terminated",
                    "detail": (
                        f"halt dispatched to the extension's ACP session registry "
                        f"for session '{detail['sessionId']}'; the registry owns "
                        f"the process kill"
                    ),
                }
            )
        elif scope == "merge":
            actions.append(
                {
                    "scope": "merge",
                    "action": "blocked",
                    "detail": (
                        f"merge attempts for {subject_desc} are refused until the "
                        f"halt lifts; the halt wins over recorded approvals"
                    ),
                }
            )
        else:  # observe-only: FR-M35-06 — observation never intercepts.
            enforceable = False
            actions.append(
                {
                    "scope": "observe-only",
                    "action": "warned",
                    "detail": (
                        "external agent cannot be force-stopped: observation "
                        "never intercepts (FR-M35-06); the operator is warned "
                        "and the agent's merge is blocked instead"
                    ),
                }
            )
            actions.append(
                {
                    "scope": "merge",
                    "action": "blocked",
                    "detail": (
                        f"merge attempts for {subject_desc} are refused while the "
                        f"observe-only halt stands"
                    ),
                }
            )
            warning = (
                f"observe-only halt recorded (seq {sequence}): the external agent "
                "cannot be force-stopped (FR-M35-06) and keeps running; its merge "
                "is blocked and the operator is warned."
            )
        result: bus_types.GateHaltResult = {
            "recorded": True,
            "sequence": sequence,
            "scope": scope,
            "enforceable": enforceable,
            "actions": actions,
        }
        if warning is not None:
            result["warning"] = warning
        return result

    # -- roles, N-of-M, delegation, hygiene (FR-M20-02…08; task 16) ---------

    def _handle_roles_list(
        self, params: bus_types.RolesListParams
    ) -> bus_types.RolesListResult:
        """FR-M20-02: the active role pack — the five roles, their
        permissions, and the approval mechanics configuration."""
        pack = self._role_pack(params or {})
        return {
            "policyVersion": pack.policy_version,
            "source": pack.source,
            "failClosed": pack.fail_closed,
            "errors": list(pack.errors),
            "defaultRole": pack.default_role if not pack.fail_closed else None,
            "roles": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "permissions": sorted(spec.permissions),
                    "readOnly": spec.read_only,
                }
                for spec in pack.roles.values()
            ],
            "approvals": {
                "nOfM": dict(pack.n_of_m),
                "soD": {"forbidSelfApproval": pack.sod_forbid_self_approval},
            },
            "delegation": {
                "maxChainDepth": pack.delegation_max_chain_depth,
                "maxTtlDays": pack.delegation_max_ttl_days,
            },
            "hygiene": {
                "approveLatencyFloorSeconds": pack.hygiene_approve_latency_floor_seconds,
                "bulkWindowMinutes": pack.hygiene_bulk_window_minutes,
                "bulkMinCount": pack.hygiene_bulk_min_count,
            },
        }

    def _handle_roles_check(
        self, params: bus_types.RolesCheckParams
    ) -> bus_types.RolesCheckResult:
        """FR-M20-02/07/08: may ``role`` perform ``action``? The structured
        answer the Gate Room renders; a fail-closed pack refuses everything
        with the parse errors as the reason."""
        params = params or {}
        role = params.get("role")
        action = params.get("action")
        if not isinstance(action, str) or not action.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "action must be one of: " + ", ".join(governance_roles.ACTIONS),
                data={"validActions": list(governance_roles.ACTIONS)},
            )
        pack = self._role_pack(params)
        check = governance_roles.check_permission(pack, role, action.strip())
        return {"permitted": check.permitted, "reason": check.reason}

    def _handle_roles_delegate(
        self, params: bus_types.RolesDelegateParams
    ) -> bus_types.RolesDelegateResult:
        """FR-M20-05: delegate an approval right to another principal with
        expiry. The delegator is the acting human identity (the provider —
        FR-M20-01); they must hold the right themselves, by role or through
        an active delegation chain. Chains are depth-bounded and cycles are
        refused. The delegation is ledger-recorded BEFORE the response
        returns (FR-M10-08)."""
        params = params or {}
        to = params.get("to")
        if not isinstance(to, str) or not to.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "to must name the delegating principal (email or role holder)",
            )
        role = params.get("role")
        if not isinstance(role, str) or not role.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "role must be a non-empty string")
        role = role.strip()
        pack = self._role_pack(params)
        if pack.fail_closed:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "roles policy is fail-closed: " + "; ".join(pack.errors),
            )
        role_spec = pack.roles.get(role)
        if role_spec is None:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"cannot delegate role '{role}': not defined in {pack.source}; "
                f"defined roles: {', '.join(sorted(pack.roles))}",
            )
        if not role_spec.may("approve"):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"cannot delegate role '{role}': it does not hold the approve "
                "right, so there is nothing to delegate",
            )
        who = self._human_identity()
        now = ledger_core.utc_now()
        expires_at: str | None = None
        raw_expiry = params.get("expiresAt")
        if raw_expiry is not None:
            if not isinstance(raw_expiry, str) or not raw_expiry.strip():
                raise _RpcError(
                    protocol.INVALID_PARAMS, "expiresAt must be an ISO-8601 UTC timestamp"
                )
            expires_at = raw_expiry.strip()
            parsed = None
            try:
                parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is None:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"expiresAt '{expires_at}' is not an ISO-8601 timestamp",
                )
            if expires_at <= now:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"expiresAt '{expires_at}' is already expired; delegations "
                    "must outlive their creation",
                )
        else:
            ttl_days = params.get("ttlDays", pack.delegation_max_ttl_days)
            if not isinstance(ttl_days, int) or isinstance(ttl_days, bool) or ttl_days < 1:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"ttlDays must be an integer >= 1, got {ttl_days!r}",
                )
            if ttl_days > pack.delegation_max_ttl_days:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"ttlDays {ttl_days} exceeds the policy maximum "
                    f"{pack.delegation_max_ttl_days} (delegation.maxTtlDays)",
                )
            expires_at = (
                (datetime.now(timezone.utc) + timedelta(days=ttl_days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        ledger = self._ensure_ledger()
        # The delegator must hold the right: by their own (declared and
        # pack-validated) role, or through an active delegation chain. The
        # new link's depth always builds on the ledger-resolved chain, so
        # re-delegation cannot launder itself back to depth 1.
        holder_role = params.get("holderRole")
        holds_by_role = (
            isinstance(holder_role, str)
            and holder_role.strip()
            and holder_role.strip() == role
            and governance_roles.check_permission(
                pack, holder_role.strip(), "approve"
            ).permitted
        )
        chain_depth = governance_roles.delegation_chain_depth(ledger, who.email, role, now)
        if not holds_by_role and chain_depth == 0:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"{who.display()} does not hold role '{role}' and has no "
                "active delegation granting it — pass holderRole naming "
                "the held role, or obtain a delegation first",
                data={"code": "DELEGATION_NOT_HELD", "role": role},
            )
        new_depth = chain_depth + 1
        if new_depth > pack.delegation_max_chain_depth:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"delegation chain depth {new_depth} exceeds the policy "
                f"maximum {pack.delegation_max_chain_depth} "
                "(delegation.maxChainDepth)",
                data={"code": "DELEGATION_CHAIN_TOO_DEEP", "depth": new_depth},
            )
        if governance_roles.delegation_reaches(ledger, to.strip(), who.email, now):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"delegating to '{to.strip()}' would create a delegation "
                "cycle — that principal already holds through a chain that "
                "reaches the delegator",
                data={"code": "DELEGATION_CYCLE"},
            )
        detail: dict[str, Any] = {
            "method": "roles/delegate",
            "from": who.wire(),
            "to": to.strip(),
            "role": role,
            "expiresAt": expires_at,
            "depth": new_depth,
        }
        sequence = self._append_gate_entry(
            story_id=f"delegation:{role}",
            pack=self._governance_pack(params),
            action_type="delegation",
            decision="delegated",
            human_actor=who.display(),
            detail=detail,
        )
        return {
            "recorded": True,
            "sequence": sequence,
            "delegation": {
                "delegator": {"name": who.display_name, "email": who.email},
                "to": to.strip(),
                "role": role,
                "expiresAt": expires_at,
                "depth": new_depth,
            },
        }

    # -- external PR gating (FR-M35-04/05; F1 Workstream B task 12) -----------

    def _handle_pr_ingest(
        self, params: bus_types.PrIngestParams
    ) -> bus_types.PrIngestResult:
        """Ingest a gh-api PR payload as a Meridian story.

        FR-M10-08: every record below is committed to the ledger BEFORE this
        response returns. The PR does not gain merge permission here — that
        is the merge gate's job with a recorded human approval (FR-M12-05),
        checked by pr/status.
        """
        params = params or {}
        raw_pr = params.get("pr")
        try:
            pr = pr_ingest.parse_pr(raw_pr)
        except pr_ingest.IngestError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        pack = self._governance_pack(params)
        # FR-M20-01/FR-M20-03: the ingesting human is recorded with the PR's
        # origin record — separation of duties compares the merge approver
        # against this identity, never against a raw string param.
        ingester = self._human_identity()

        ticket = params.get("linkedTicket")
        if not isinstance(ticket, str) or not ticket.strip():
            ticket = pr_ingest.ticket_for(pr)
        story_id = ticket.strip() if isinstance(ticket, str) and ticket.strip() else pr.subject

        gates = params.get("gates")
        if gates is None:
            gate = params.get("gate")
            gates = [gate] if isinstance(gate, str) and gate.strip() else list(pr_ingest.DEFAULT_GATES)
        if not isinstance(gates, list) or not gates or not all(
            isinstance(g, str) and g.strip() for g in gates
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "gates must be a non-empty list of gate profile names",
            )
        gates = [g.strip() for g in gates]

        agents = pr_ingest.resolve_agents(pr)
        hunks = pr_ingest.attribute_hunks(pr)
        ledger = self._ensure_ledger()

        # 1. The ledger origin record: the PR as the story's origin
        #    (FR-M35-05). origin "connector" — in production this payload
        #    arrives from the SCM connectors (M23).
        origin_sequence = self._append_gate_entry(
            story_id=story_id,
            pack=pack,
            action_type="pr_ingest",
            decision="proposed",
            actor_kind="external",
            vendor=agents[0].vendor,
            observation_confidence=agents[0].confidence,
            run_id=pr.subject,
            origin="connector",
            phase="intake",
            human_actor=ingester.display(),
            detail={
                "method": "pr/ingest",
                "subject": pr.subject,
                "repo": pr.repo,
                "number": pr.number,
                "url": pr.url,
                "title": pr.title,
                "state": pr.state,
                "author": {
                    "login": pr.author_login,
                    "type": pr.author_type,
                    "association": pr.author_association,
                },
                "branch": pr.branch,
                "headCommit": pr.head_commit,
                "baseBranch": pr.base_branch,
                "baseCommit": pr.base_commit,
                "linkedTicket": ticket if isinstance(ticket, str) else None,
                "ingestedBy": ingester.wire(),
                "payload": raw_pr,
            },
        )

        # 2. The external agent's pass: one proposed-change entry per agent
        #    carrying its attributed hunks (AC-32: the agent's pass, the
        #    gates and the approver land in one ledger range).
        hunk_sequences: list[int] = []
        by_agent: dict[str, list[pr_ingest.HunkAttribution]] = {}
        for hunk in hunks:
            by_agent.setdefault(hunk.agent.agent_id, []).append(hunk)
        for agent in agents:
            agent_hunks = by_agent.get(agent.agent_id, [])
            sequence = self._append_agent_pass(
                ledger=ledger,
                story_id=story_id,
                pack=pack,
                pr=pr,
                agent=agent,
                hunks=agent_hunks,
            )
            hunk_sequences.append(sequence)

        # 3. Gate routing: the packet is evaluated against every requested
        #    profile and each verdict is recorded (FR-M35-04).
        packet = self._pr_packet(params, pr, story_id)
        gate_results: list[dict[str, Any]] = []
        for gate in gates:
            verdict = governance_engine.evaluate(packet, gate, pack)
            sequence = self._append_gate_entry(
                story_id=story_id,
                pack=pack,
                decision="approved" if verdict.passed else "rejected",
                detail={
                    "method": "pr/ingest",
                    "subject": pr.subject,
                    "gate": gate,
                    "packet": packet,
                    "criteria": [
                        {
                            "id": c.id,
                            "kind": c.kind,
                            "passed": c.passed,
                            "reason": c.reason,
                        }
                        for c in verdict.criteria
                    ],
                    "reasons": list(verdict.reasons),
                    "failClosed": verdict.fail_closed,
                },
            )
            gate_results.append(
                {
                    "gate": gate,
                    "decision": "pass" if verdict.passed else "block",
                    "sequence": sequence,
                    "reasons": list(verdict.reasons),
                }
            )

        return {
            "storyId": story_id,
            "subject": pr.subject,
            "repo": pr.repo,
            "number": pr.number,
            "branch": pr.branch,
            "headCommit": pr.head_commit,
            "baseBranch": pr.base_branch,
            "ingestedBy": {
                "name": ingester.display_name,
                "email": ingester.email,
                "assurance": ingester.assurance,
            },
            "agents": [self._agent_wire(agent) for agent in agents],
            "hunks": [self._hunk_wire(h) for h in hunks],
            "gates": gate_results,
            "sequences": {
                "origin": origin_sequence,
                "passes": hunk_sequences,
                "gates": [g["sequence"] for g in gate_results],
            },
        }

    def _handle_pr_status(
        self, params: bus_types.PrStatusParams
    ) -> bus_types.PrStatusResult:
        """Gate state for an ingested PR: the recorded evaluations plus the
        merge gate verdict. Read-only — status decides and records nothing.
        """
        params = params or {}
        pack = self._governance_pack(params)
        subject = params.get("subject")
        if not isinstance(subject, str) or not subject.strip():
            repo = params.get("repo")
            number = params.get("number")
            if (
                not isinstance(repo, str)
                or not repo.strip()
                or not isinstance(number, int)
                or isinstance(number, bool)
            ):
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "pr/status needs subject or (repo, number)",
                )
            subject = pr_ingest.subject_for(repo.strip(), number)

        ledger = self._ensure_ledger()
        ingest = self._find_pr_ingest(ledger, subject.strip())
        head_commit: str | None = None
        base_branch: str | None = None
        story_id: str | None = None
        gates: list[dict[str, Any]] = []
        if ingest is not None:
            story_id = ingest["row"].get("story_id")
            head_commit = ingest["detail"].get("headCommit")
            base_branch = ingest["detail"].get("baseBranch")
            for row in ledger.query(action_type="gate", story_id=story_id, limit=1000):
                detail = self._read_entry_detail(ledger, row)
                if detail.get("subject") != subject.strip():
                    continue
                gates.append(
                    {
                        "gate": detail.get("gate"),
                        "decision": "pass" if row.get("decision") == "approved" else "block",
                        "sequence": row["seq"],
                    }
                )
            gates.sort(key=lambda g: g["sequence"])

        # FR-M35-04: merging the PR lands on its base branch; when that
        # branch is protected, a recorded human approval bound to the head
        # commit is required — the merge gate decides, this RPC only asks.
        # The role pack's N-of-M threshold is looked up by the base branch.
        requires_approval = None
        if base_branch is not None:
            requires_approval = base_branch in pack.protected_branches
        verdict = self._merge_verdict(
            params,
            subject=subject.strip(),
            head_commit=head_commit,
            requires_approval=requires_approval,
            approval_subject=base_branch,
        )
        merge: bus_types.GateStatusResult = {
            "status": "approved" if verdict.allowed else "blocked",
            "subject": verdict.subject,
            "requiredApproval": verdict.required_approval,
            "halted": verdict.halted,
            "missing": list(verdict.missing),
            "requiredApprovals": verdict.required_approvals,
            "approvalsReceived": len(
                {a.approver.email for a in verdict.approvals if a.approver.email}
            ),
        }
        role_pack = self._role_pack(params)
        if not role_pack.fail_closed:
            warnings = governance_roles.assess_hygiene(
                self._ensure_ledger(), role_pack, subject=subject.strip()
            )
            if warnings:
                merge["hygieneWarnings"] = warnings
        if verdict.approval is not None:
            merge["approvalSequence"] = verdict.approval.sequence
            merge["approver"] = {
                "name": verdict.approval.approver.name,
                "email": verdict.approval.approver.email,
            }
        result: bus_types.PrStatusResult = {
            "subject": subject.strip(),
            "ingested": ingest is not None,
            "storyId": story_id,
            "headCommit": head_commit,
            "baseBranch": base_branch,
            "gates": gates,
            "merge": merge,
        }
        return result

    # -- PR ingest helpers -----------------------------------------------------

    @staticmethod
    def _agent_wire(agent: pr_ingest.AgentAttribution) -> dict[str, Any]:
        return {
            "agentId": agent.agent_id,
            "vendor": agent.vendor,
            "login": agent.login,
            "confidence": agent.confidence,
            "source": agent.source,
        }

    @staticmethod
    def _hunk_wire(hunk: pr_ingest.HunkAttribution) -> dict[str, Any]:
        return {
            "path": hunk.path,
            "oldStart": hunk.old_start,
            "oldCount": hunk.old_count,
            "newStart": hunk.new_start,
            "newCount": hunk.new_count,
            "agent": SidecarServer._agent_wire(hunk.agent),
            "rationale": hunk.rationale,
        }

    def _pr_packet(
        self, params: dict[str, Any], pr: pr_ingest.PullRequest, story_id: str
    ) -> dict[str, Any]:
        """The gate-engine packet for an ingested PR: required fields plus
        any evidence artifacts and approvals the caller attached (gh-api
        check-run / review shapes, injected by the connector or the test)."""
        packet: dict[str, Any] = {
            "storyId": story_id,
            "subject": pr.subject,
            "branch": pr.branch,
            "headCommit": pr.head_commit,
            "baseBranch": pr.base_branch,
        }
        evidence = params.get("evidence")
        if isinstance(evidence, list):
            packet["evidence"] = evidence
        approvals = params.get("approvals")
        if isinstance(approvals, list):
            packet["approvals"] = approvals
        return packet

    def _append_agent_pass(
        self,
        *,
        ledger: ledger_core.Ledger,
        story_id: str,
        pack: governance_policy.PolicyPack,
        pr: pr_ingest.PullRequest,
        agent: pr_ingest.AgentAttribution,
        hunks: list[pr_ingest.HunkAttribution],
    ) -> int:
        """One proposed-change entry for an agent's pass on the PR — the
        entry AC-32 reconciles against the gates and the approver."""
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": story_id,
            "phase": "build",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": agent.agent_id,
            "actor_version": protocol.CORE_VERSION,
            "actor_kind": "external",
            "policy_version": pack.policy_version,
            "action_type": "diff",
            "decision": "proposed",
            "vendor": agent.vendor,
            "observation_confidence": agent.confidence,
            "input": json.dumps(
                {
                    "method": "pr/ingest",
                    "subject": pr.subject,
                    "headCommit": pr.head_commit,
                    "baseCommit": pr.base_commit,
                    "source": agent.source,
                },
                ensure_ascii=False,
            ),
            "repo_id": pr.repo,
            "run_id": pr.subject,
            "origin": "connector",
            "tool_calls": [
                {
                    "path": h.path,
                    "oldStart": h.old_start,
                    "oldCount": h.old_count,
                    "newStart": h.new_start,
                    "newCount": h.new_count,
                    "rationale": h.rationale,
                }
                for h in hunks
            ],
        }
        result = ledger.append(entry)
        self._trust_cache.invalidate()
        return result.sequence

    def _find_pr_ingest(
        self, ledger: ledger_core.Ledger, subject: str
    ) -> dict[str, Any] | None:
        """The newest pr_ingest entry for ``subject``: (row, decoded detail)."""
        for row in reversed(ledger.query(action_type="pr_ingest", limit=1000)):
            detail = self._read_entry_detail(ledger, row)
            if detail.get("subject") == subject:
                return {"row": row, "detail": detail}
        return None

    def _read_entry_detail(self, ledger: ledger_core.Ledger, row: dict[str, Any]) -> dict[str, Any]:
        ref = row.get("input_ref")
        key_id = row.get("blob_key_id")
        if not ref or not key_id:
            return {}
        try:
            return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
        except (ValueError, KeyError, OSError):
            return {}

    # -- multi-agent conflict detection (FR-M35-07; task 13) -------------------

    def _handle_pr_conflicts(
        self, params: bus_types.PrConflictsParams
    ) -> bus_types.PrConflictsResult:
        """Attribute every hunk in a commit range to its agent and surface
        agent-vs-agent conflicts as the distinct rework class agent-conflict.

        FR-M10-08: each newly detected conflict is a ledger entry (actionType
        rejection, reworkReason agent-conflict) BEFORE the response returns;
        re-runs are idempotent (already-recorded conflicts are reported, never
        double-appended).
        """
        params = params or {}
        ref = params.get("ref") or "HEAD"
        base = params.get("base")
        try:
            repo = self._ensure_attrib_repo({"repoPath": params.get("repoPath")})
            hunks = pr_conflicts.collect_agent_hunks(repo, base=base, ref=ref)
        except AttributionError as error:
            raise self._attrib_error(error) from error

        conflicts = pr_conflicts.detect_conflicts(hunks)
        ledger = self._ensure_ledger()
        repo_id = params.get("repoId") or repo.name
        story_id = params.get("storyId") or f"conflicts:{repo_id}"
        pack = self._governance_pack(params)

        known = self._recorded_conflict_keys(ledger, repo_id)
        wire_conflicts: list[dict[str, Any]] = []
        recorded = 0
        duplicates = 0
        for conflict in conflicts:
            key = conflict.idempotency_key
            already = key in known
            sequence: int | None = known.get(key)
            if not already:
                sequence = self._append_conflict_entry(
                    ledger=ledger,
                    story_id=story_id,
                    pack=pack,
                    repo_id=repo_id,
                    conflict=conflict,
                )
                known[key] = sequence
                recorded += 1
            else:
                duplicates += 1
            wire_conflicts.append(
                {
                    "path": conflict.path,
                    "kind": conflict.kind,
                    "agents": [
                        self._commit_agent_wire(conflict.earlier.agent),
                        self._commit_agent_wire(conflict.later.agent),
                    ],
                    "earlier": self._agent_hunk_wire(conflict.earlier),
                    "later": self._agent_hunk_wire(conflict.later),
                    "recordedSequence": sequence,
                    "alreadyRecorded": already,
                }
            )
        return {
            "repoPath": str(repo),
            "base": base,
            "ref": ref,
            "storyId": story_id,
            "hunks": [self._agent_hunk_wire(h) for h in hunks],
            "conflicts": wire_conflicts,
            "recorded": recorded,
            "duplicatesSkipped": duplicates,
        }

    @staticmethod
    def _commit_agent_wire(agent: pr_conflicts.CommitAgent) -> dict[str, Any]:
        return {
            "agentId": agent.agent_id,
            "vendor": agent.vendor,
            "name": agent.name,
            "confidence": agent.confidence,
            "source": agent.source,
        }

    @staticmethod
    def _agent_hunk_wire(hunk: pr_conflicts.AgentHunk) -> dict[str, Any]:
        return {
            "path": hunk.path,
            "oldStart": hunk.old_start,
            "oldCount": hunk.old_count,
            "newStart": hunk.new_start,
            "newCount": hunk.new_count,
            "agent": SidecarServer._commit_agent_wire(hunk.agent),
            "commit": hunk.commit,
        }

    @staticmethod
    def _recorded_conflict_keys(
        ledger: ledger_core.Ledger, repo_id: str
    ) -> dict[tuple[str, str, str, int, int], int]:
        """The conflict idempotency keys already in the ledger for this repo:
        (earlier commit, later commit, path, new start, old start) -> seq.

        The key round-trips through the rejection-linkage columns
        (rejected_commit = the earlier agent's commit whose lines were
        edited, rejecting_commit = the later agent's commit) plus the
        tool_calls JSON detail.
        """
        known: dict[tuple[str, str, str, int, int], int] = {}
        rows = ledger.query(action_type="rejection", limit=1000)
        for row in rows:
            if row.get("repo_id") != repo_id:
                continue
            if row.get("rework_reason") != pr_conflicts.AGENT_CONFLICT_REASON:
                continue
            detail_raw = row.get("tool_calls")
            if not isinstance(detail_raw, str) or not detail_raw:
                continue
            try:
                detail = json.loads(detail_raw)
            except ValueError:
                continue
            info = detail[0] if isinstance(detail, list) and detail else {}
            key = (
                str(row.get("rejected_commit") or ""),
                str(row.get("rejecting_commit") or ""),
                str(info.get("path") or ""),
                int(info.get("earlierNewStart", -1)),
                int(info.get("laterOldStart", -1)),
            )
            known[key] = row["seq"]
        return known

    def _append_conflict_entry(
        self,
        *,
        ledger: ledger_core.Ledger,
        story_id: str,
        pack: governance_policy.PolicyPack,
        repo_id: str,
        conflict: pr_conflicts.Conflict,
    ) -> int:
        """The ledger record of one agent-vs-agent conflict: the distinct
        rework class agent-conflict (FR-M35-07), stamped through the E-GR-03
        taxonomy (task 14) — the class is canonical and carries a note."""
        stamp = rejection_taxonomy.classify_reason(
            pr_conflicts.AGENT_CONFLICT_REASON,
            note=(
                f"{conflict.kind} in {conflict.path} between "
                f"{conflict.earlier.agent.agent_id} and "
                f"{conflict.later.agent.agent_id}"
            ),
        )
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": story_id,
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 0,
            "actor_id": conflict.later.agent.agent_id,
            "actor_version": protocol.CORE_VERSION,
            "actor_kind": "external",
            "policy_version": pack.policy_version,
            "action_type": "rejection",
            "decision": "rejected",
            "rework_reason": stamp.reason,
            "vendor": conflict.later.agent.vendor,
            "observation_confidence": conflict.later.agent.confidence,
            "rejected_commit": conflict.earlier.commit,
            "rejecting_commit": conflict.later.commit,
            "repo_id": repo_id,
            "input": json.dumps(
                {
                    "method": "pr/conflicts",
                    "class": stamp.reason,
                    "kind": conflict.kind,
                    "path": conflict.path,
                    "agents": list(conflict.agents),
                    "reasonNote": stamp.note,
                },
                ensure_ascii=False,
            ),
            "tool_calls": [
                {
                    "class": stamp.reason,
                    "kind": conflict.kind,
                    "path": conflict.path,
                    "agents": list(conflict.agents),
                    "earlierNewStart": conflict.earlier.new_start,
                    "laterOldStart": conflict.later.old_start,
                    "reasonNote": stamp.note,
                }
            ],
        }
        result = ledger.append(entry)
        self._trust_cache.invalidate()
        return result.sequence

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
        # The taxonomy stamp (E-GR-03, FR-M37-02): the caller's reason class
        # when supplied, else the fail-closed default with an explanatory
        # note — a rejection record is never unclassified.
        caller_reason = params.get("reason")
        caller_note = params.get("reasonNote")
        taxonomy = rejection_taxonomy.load_taxonomy()

        def stamp_for(rejection: rejection_mod.Rejection) -> rejection_taxonomy.ReasonStamp:
            note = caller_note
            if not isinstance(caller_reason, str) or not caller_reason.strip():
                # Detection knows the mechanical shape, not WHY a human
                # rejected the change — the note says exactly that.
                note = note or (
                    f"auto-detected rejection (shape: {rejection.reason}); "
                    "taxonomy reason requires human classification"
                )
            return rejection_taxonomy.classify_reason(
                caller_reason, note=note, taxonomy=taxonomy
            )

        # Idempotency: rejection entries already recorded for this repo.
        # The key is the mechanical identity (commits + shape), NOT the
        # taxonomy class — a later human classification must not re-record.
        existing = ledger.query(action_type="rejection", limit=1000)
        known: dict[tuple, int] = {}
        for row in existing:
            key = (
                row.get("rejected_commit"),
                row.get("rejecting_commit"),
                self._rejection_shape(row),
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
                row = ledger.get_entry(known[key])
                wire.append(
                    self._rejection_wire(
                        rejection,
                        None,
                        known[key],
                        True,
                        rework_reason=row.get("rework_reason") if row else None,
                        reason_note=self._rejection_note(row) if row else None,
                    )
                )
                continue
            rejected_sequence = rejection_mod.resolve_ledger_sequence(
                repo, rejection.rejected_commit
            )
            source = (
                ledger.get_entry(rejected_sequence) if rejected_sequence else None
            )
            stamp = stamp_for(rejection)
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
                "rework_reason": stamp.reason,
                "rejected_sequence": rejected_sequence,
                "rejected_commit": rejection.rejected_commit,
                "rejecting_commit": rejection.rejecting_commit,
                "repo_id": repo_id,
                "tool_calls": [
                    {
                        "shape": rejection.reason,
                        "paths": list(rejection.paths),
                        "linesRejected": rejection.lines_rejected,
                        "rejectedAt": rejection.rejected_at,
                        "reasonNote": stamp.note,
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
                self._rejection_wire(
                    rejection,
                    rejected_sequence,
                    result.sequence,
                    False,
                    rework_reason=stamp.reason,
                    reason_note=stamp.note,
                )
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
    def _rejection_shape(row: dict[str, Any]) -> str | None:
        """The mechanical detection shape stored in tool_calls (rows from
        before the taxonomy carried the shape in rework_reason itself)."""
        raw = row.get("tool_calls")
        if isinstance(raw, str) and raw:
            try:
                detail = json.loads(raw)
            except ValueError:
                return None
            if isinstance(detail, list) and detail and isinstance(detail[0], dict):
                shape = detail[0].get("shape")
                if isinstance(shape, str):
                    return shape
        return row.get("rework_reason")

    @staticmethod
    def _rejection_note(row: dict[str, Any] | None) -> str | None:
        if not row:
            return None
        raw = row.get("tool_calls")
        if isinstance(raw, str) and raw:
            try:
                detail = json.loads(raw)
            except ValueError:
                return None
            if isinstance(detail, list) and detail and isinstance(detail[0], dict):
                note = detail[0].get("reasonNote")
                return note if isinstance(note, str) else None
        return None

    @staticmethod
    def _rejection_wire(
        rejection: rejection_mod.Rejection,
        rejected_sequence: int | None,
        recorded_sequence: int | None,
        already_recorded: bool,
        *,
        rework_reason: str | None = None,
        reason_note: str | None = None,
    ) -> bus_types.TrustRejection:
        return {
            "rejectedCommit": rejection.rejected_commit,
            "rejectingCommit": rejection.rejecting_commit,
            "reason": rejection.reason,  # type: ignore[typeddict-item]
            "reworkReason": rework_reason or "other",
            "reasonNote": reason_note,
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

    # -- rejection rate (FR-M17-05 + FR-M37-01, task 30) ----------------------

    def _handle_trust_rejection_rate(
        self, params: bus_types.TrustRejectionRateParams
    ) -> bus_types.TrustRejectionRateResult:
        params = params or {}
        ledger = self._ensure_ledger()
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": params.get("repoId"),
                    "storyId": params.get("storyId"),
                    "actorId": params.get("actorId"),
                    "phase": params.get("phase"),
                    "actionType": params.get("actionType"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        classify_fn = None
        if story_commits:
            try:
                repo = self._ensure_attrib_repo({"repoPath": params.get("repoPath")})
            except AttributionError as error:
                raise self._attrib_error(error) from error

            def classify_fn(story_id: str) -> str | None:  # type: ignore[no-redef]
                commits = story_commits.get(story_id)
                if not commits:
                    return None
                try:
                    return metrics_mod.classify(
                        repo,
                        commits=list(commits),
                        new_file_ratio_threshold=ratio_threshold
                        if ratio_threshold is not None
                        else metrics_mod.DEFAULT_NEW_FILE_RATIO_THRESHOLD,
                        max_median_age_days=max_age_days
                        if max_age_days is not None
                        else metrics_mod.DEFAULT_MAX_MEDIAN_AGE_DAYS,
                    ).classification
                except AttributionError:
                    # A story whose commits cannot be classified (rewritten
                    # away, foreign repo) reports unclassified — a metric
                    # degrades, never goes silent.
                    return None

        result = metrics_mod.compute_rejection_rate(
            ledger,
            repo_id=params.get("repoId"),
            story_id=params.get("storyId"),
            actor_id=params.get("actorId"),
            phase=params.get("phase"),
            action_type=params.get("actionType"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            classify=classify_fn,
        )
        result["cacheHit"] = False
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- rejection reason distribution (FR-M37-02, task 20) --------------------

    def _trust_classifier(
        self,
        params: dict[str, Any],
        story_commits: dict[str, Any],
        ratio_threshold: float | None,
        max_age_days: float | None,
    ):
        """The storyCommits -> greenfield/brownfield callable shared by the
        trust metrics (stories without commit data degrade to unclassified,
        never to a failed metric)."""
        if not story_commits:
            return None
        try:
            repo = self._ensure_attrib_repo({"repoPath": params.get("repoPath")})
        except AttributionError as error:
            raise self._attrib_error(error) from error

        def classify_fn(story_id: str) -> str | None:
            commits = story_commits.get(story_id)
            if not commits:
                return None
            try:
                return metrics_mod.classify(
                    repo,
                    commits=list(commits),
                    new_file_ratio_threshold=ratio_threshold
                    if ratio_threshold is not None
                    else metrics_mod.DEFAULT_NEW_FILE_RATIO_THRESHOLD,
                    max_median_age_days=max_age_days
                    if max_age_days is not None
                    else metrics_mod.DEFAULT_MAX_MEDIAN_AGE_DAYS,
                ).classification
            except AttributionError:
                # A story whose commits cannot be classified (rewritten
                # away, foreign repo) reports unclassified — a metric
                # degrades, never goes silent.
                return None

        return classify_fn

    def _handle_trust_reason_distribution(
        self, params: bus_types.TrustReasonDistributionParams
    ) -> bus_types.TrustReasonDistributionResult:
        params = params or {}
        ledger = self._ensure_ledger()
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": params.get("repoId"),
                    "actorId": params.get("actorId"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        classify_fn = self._trust_classifier(
            params, story_commits, ratio_threshold, max_age_days
        )
        result = metrics_mod.compute_reason_distribution(
            ledger,
            repo_id=params.get("repoId"),
            actor_id=params.get("actorId"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            classify=classify_fn,
        )
        result["cacheHit"] = False
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- trust score with decomposition (FR-M37-03, task 21) -------------------

    def _handle_trust_score(
        self, params: bus_types.TrustScoreParams
    ) -> bus_types.TrustScoreResult:
        # One implementation behind both trust/score and
        # trust/scoreDecomposition: the decomposition is always exposed in
        # full, and the aggregate can never hide a bad component.
        params = params or {}
        actor_id = params.get("actorId")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, "trust/score needs the actorId"
            )
        ledger = self._ensure_ledger()
        task_class_by_story = params.get("taskClassByStory") or {}
        if not isinstance(task_class_by_story, dict):
            raise _RpcError(
                protocol.INVALID_PARAMS, "taskClassByStory must be an object"
            )

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": params.get("repoId"),
                    "actorId": actor_id,
                    "taskClass": params.get("taskClass"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "taskClassByStory": task_class_by_story,
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        result = metrics_mod.compute_trust_score(
            ledger,
            actor_id=actor_id,
            repo_id=params.get("repoId"),
            task_class=params.get("taskClass"),
            task_class_by_story=task_class_by_story,
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
        )
        result["cacheHit"] = False
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- agent-vs-agent comparison (FR-M37-04, task 22) ----------------------

    def _handle_trust_compare_agents(
        self, params: bus_types.TrustCompareAgentsParams
    ) -> bus_types.TrustCompareAgentsResult:
        params = params or {}
        story_id = params.get("storyId")
        if not isinstance(story_id, str) or not story_id.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, "trust/compareAgents needs the storyId"
            )
        ledger = self._ensure_ledger()
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

        cache_key = json.dumps(
            {
                "scope": {
                    "storyId": story_id,
                    "repoId": params.get("repoId"),
                    "actorIds": params.get("actorIds"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        classify_fn = self._trust_classifier(
            params, story_commits, ratio_threshold, max_age_days
        )
        result = metrics_mod.compute_agent_comparison(
            ledger,
            story_id=story_id,
            actor_ids=params.get("actorIds"),
            repo_id=params.get("repoId"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            classify=classify_fn,
        )
        result["cacheHit"] = False
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- J-curve (FR-M37-05, task 23) -----------------------------------------

    def _handle_trust_jcurve(
        self, params: bus_types.TrustJcurveParams
    ) -> bus_types.TrustJcurveResult:
        params = params or {}
        adoption_date = params.get("adoptionDate")
        if not isinstance(adoption_date, str) or not adoption_date.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, "trust/jcurve needs the adoptionDate"
            )
        ledger = self._ensure_ledger()
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

        cache_key = json.dumps(
            {
                "scope": {
                    "adoptionDate": adoption_date,
                    "repoId": params.get("repoId"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        classify_fn = self._trust_classifier(
            params, story_commits, ratio_threshold, max_age_days
        )
        try:
            result = metrics_mod.compute_jcurve(
                ledger,
                adoption_date=adoption_date,
                repo_id=params.get("repoId"),
                from_sequence=params.get("fromSequence"),
                to_sequence=params.get("toSequence"),
                classify=classify_fn,
            )
        except ValueError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        result["cacheHit"] = False
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- tokenmaxxing detector (FR-M37-07, task 24) ---------------------------

    def _handle_trust_tokenmaxxing(
        self, params: bus_types.TrustTokenmaxxingParams
    ) -> bus_types.TrustTokenmaxxingResult:
        params = params or {}
        spend_series = params.get("spendSeries")
        if not isinstance(spend_series, dict) or not spend_series:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "trust/tokenmaxxing needs the spendSeries object",
            )
        ledger = self._ensure_ledger()
        repo_id = params.get("repoId")
        from_sequence = params.get("fromSequence")
        to_sequence = params.get("toSequence")
        rise_threshold = params.get("spendRiseThreshold")
        min_periods = params.get("minPeriods")
        detector_kwargs: dict[str, Any] = {}
        if rise_threshold is not None:
            detector_kwargs["spend_rise_threshold"] = rise_threshold
        if min_periods is not None:
            detector_kwargs["min_periods"] = min_periods

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": repo_id,
                    "fromSequence": from_sequence,
                    "toSequence": to_sequence,
                },
                "spendSeries": spend_series,
                "detector": [rise_threshold, min_periods],
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        # First-pass yield per period comes from the ledger: the agent's
        # in-scope diffs bucketed by ISO week (the period labels the spend
        # feed uses), yield = 1 - rejected/proposed per bucket.
        rows = ledger.query(
            action_type="diff",
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            limit=1000,
        )
        if repo_id is not None:
            rows = [row for row in rows if row.get("repo_id") == repo_id]
        rejection_rows = ledger.query(action_type="rejection", limit=1000)
        if repo_id is not None:
            rejection_rows = [
                row for row in rejection_rows if row.get("repo_id") == repo_id
            ]
        if from_sequence is not None:
            rejection_rows = [
                row for row in rejection_rows if row["seq"] >= from_sequence
            ]
        if to_sequence is not None:
            rejection_rows = [
                row for row in rejection_rows if row["seq"] <= to_sequence
            ]
        rejected_sequences = {
            row["rejected_sequence"]
            for row in rejection_rows
            if row.get("rejected_sequence") is not None
        }

        def iso_week(ts_utc: str | None) -> str | None:
            parsed = metrics_mod.parse_utc(ts_utc)
            if parsed is None:
                return None
            year, week, _ = parsed.date().isocalendar()
            return f"{year}-W{week:02d}"

        def yield_points(actor_id: str | None) -> list[metrics_mod.YieldPoint]:
            buckets: dict[str, dict[str, int]] = {}
            for row in rows:
                if actor_id is not None and row["actor_id"] != actor_id:
                    continue
                period = iso_week(row.get("ts_utc"))
                if period is None:
                    continue
                bucket = buckets.setdefault(period, {"proposed": 0, "rejected": 0})
                bucket["proposed"] += 1
                if (
                    row["seq"] in rejected_sequences
                    or row.get("decision") in ("rejected", "reworked")
                ):
                    bucket["rejected"] += 1
            return [
                metrics_mod.YieldPoint(
                    period=period,
                    first_pass_yield=round(
                        1 - counts["rejected"] / counts["proposed"], 6
                    ),
                )
                for period, counts in sorted(buckets.items())
                if counts["proposed"]
            ]

        by_agent: dict[str, Any] = {}
        team_spend: dict[str, float] = {}
        for actor, series in sorted(spend_series.items()):
            if not isinstance(actor, str) or not isinstance(series, list):
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "spendSeries maps agentId -> [{period, tokens}]",
                )
            points: list[metrics_mod.SpendPoint] = []
            for raw in series:
                if not isinstance(raw, dict):
                    raise _RpcError(
                        protocol.INVALID_PARAMS,
                        "spendSeries maps agentId -> [{period, tokens}]",
                    )
                period = raw.get("period")
                tokens = raw.get("tokens")
                if not isinstance(period, str) or not isinstance(
                    tokens, (int, float)
                ):
                    raise _RpcError(
                        protocol.INVALID_PARAMS,
                        "each spend point needs a string period and numeric tokens",
                    )
                points.append(metrics_mod.SpendPoint(period=period, tokens=tokens))
                team_spend[period] = team_spend.get(period, 0.0) + tokens
            by_agent[actor] = metrics_mod.detect_tokenmaxxing(
                points, yield_points(actor), **detector_kwargs
            )

        team = metrics_mod.detect_tokenmaxxing(
            [
                metrics_mod.SpendPoint(period=period, tokens=tokens)
                for period, tokens in sorted(team_spend.items())
            ],
            yield_points(None),
            **detector_kwargs,
        )
        result = {
            "scope": {
                "repoId": repo_id,
                "fromSequence": from_sequence,
                "toSequence": to_sequence,
            },
            "byAgent": by_agent,
            "team": team,
        }
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- DORA export (FR-M37-08, task 25) -------------------------------------

    def _handle_trust_dora_export(
        self, params: bus_types.TrustDoraExportParams
    ) -> bus_types.TrustDoraExportResult:
        params = params or {}
        ledger = self._ensure_ledger()
        resource_attributes = params.get("resourceAttributes") or {}
        if not isinstance(resource_attributes, dict):
            raise _RpcError(
                protocol.INVALID_PARAMS, "resourceAttributes must be an object"
            )
        exported_at = params.get("exportedAt")

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": params.get("repoId"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "resourceAttributes": resource_attributes,
                "exportedAt": exported_at,
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        computed = metrics_mod.compute_dora_metrics(
            ledger,
            repo_id=params.get("repoId"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
        )
        export = metrics_mod.export_otlp(
            computed,
            exported_at=exported_at if isinstance(exported_at, str) else None,
            resource_attributes=resource_attributes,
        )
        result = {
            "status": computed["status"],
            "metrics": computed["metrics"],
            "export": export,
        }
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    # -- cross-vendor spend (FR-M39-01/02/03/04; F1 Workstream F tasks 26-29)

    def _spend_pricing_pack(self, params: dict[str, Any]) -> Any:
        """The active pricing pack: an explicit pricingPath param, then the
        workspace override, then the repository policy directory (the
        workspace IS the repository in production)."""
        paths: list[Any] = []
        if params.get("pricingPath"):
            paths.append(params["pricingPath"])
        if self._workspace_dir:
            workspace = Path(self._workspace_dir)
            paths.append(workspace / ".meridian" / "policy" / "pricing.yaml")
            paths.append(workspace / "policy" / "pricing.yaml")
        return metrics_mod.load_pricing_pack(paths)

    def _spend_story_meta(self, params: dict[str, Any]) -> Any:
        """The active story-metadata pack (FR-M26-03 attribution), with an
        inline storyMetadata param merged over it — callers with story
        metadata in hand supply it directly; the pack covers the rest.
        A fail-closed pack yields 'unknown' for everything, never an
        error, and inline entries apply on top."""
        paths: list[Any] = []
        if params.get("storyPath"):
            paths.append(params["storyPath"])
        if self._workspace_dir:
            workspace = Path(self._workspace_dir)
            paths.append(workspace / ".meridian" / "policy" / "stories.yaml")
            paths.append(workspace / "policy" / "stories.yaml")
        meta = metrics_mod.load_story_metadata(paths)
        inline = params.get("storyMetadata")
        if isinstance(inline, dict):
            entries = dict(meta.entries)
            for story_id, story_meta in inline.items():
                if isinstance(story_id, str) and isinstance(story_meta, dict):
                    entry: dict[str, str] = {}
                    for key in ("team", "costCentre"):
                        value = story_meta.get(key)
                        entry[key] = (
                            value.strip()
                            if isinstance(value, str) and value.strip()
                            else "unknown"
                        )
                    entries[story_id.strip()] = entry
            meta = metrics_mod.StoryMetadata(
                source=f"{meta.source}+inline", entries=entries, errors=list(meta.errors)
            )
        return meta

    def _handle_spend_series(
        self, params: bus_types.SpendSeriesParams
    ) -> bus_types.SpendSeriesResult:
        params = params or {}
        ledger = self._ensure_ledger()
        dimension = params.get("dimension") or "vendor"
        if dimension not in metrics_mod.DIMENSIONS:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"dimension must be one of {', '.join(metrics_mod.DIMENSIONS)}",
            )
        scope = {
            "dimension": dimension,
            "actorId": params.get("actorId"),
            "storyId": params.get("storyId"),
            "vendor": params.get("vendor"),
            "repoId": params.get("repoId"),
            "fromSequence": params.get("fromSequence"),
            "toSequence": params.get("toSequence"),
        }
        cache_key = json.dumps(
            {"spendSeries": scope, "tip": ledger.last_sequence}, sort_keys=True
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        pricing = self._spend_pricing_pack(params)
        price = None if pricing.fail_closed else pricing.price
        rows = self._spend_rows(ledger, params)
        aggregated = metrics_mod.spend_by_dimension(
            rows,
            dimension,
            story_meta=self._spend_story_meta(params),
            price=price,
        )
        series = metrics_mod.LedgerSpendSeries(rows, price)
        result = {
            "scope": scope,
            "dimension": aggregated["dimension"],
            "totals": aggregated["totals"],
            "byValue": aggregated["byValue"],
            "spendSeries": {
                agent: [
                    {"period": point.period, "tokens": point.tokens}
                    for point in series.points(agent)
                ]
                for agent in series.agents()
            },
            "cacheHit": False,
        }
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    def _spend_rows(
        self, ledger: Any, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Token/cost-bearing rows in scope, newest-history cap like the
        other trust metrics (the ledger is the metrics store — FR-M17-05
        makes derivation on demand, not warehousing)."""
        rows = ledger.query(
            actor_id=params.get("actorId"),
            story_id=params.get("storyId"),
            vendor=params.get("vendor"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            limit=1000,
        )
        repo_id = params.get("repoId")
        if repo_id is not None:
            rows = [row for row in rows if row.get("repo_id") == repo_id]
        return rows

    def _handle_spend_ceiling_check(
        self, params: bus_types.SpendCeilingCheckParams
    ) -> bus_types.SpendCeilingCheckResult:
        params = params or {}
        ledger = self._ensure_ledger()
        actor_id = params.get("actorId")
        session_id = params.get("sessionId")
        story_id = params.get("storyId")
        if not isinstance(actor_id, str) or not actor_id.strip():
            if not isinstance(session_id, str) or not session_id.strip():
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    "spend/ceilingCheck needs the actorId (or the sessionId)",
                )
            actor_id = None
        actor_id = actor_id.strip() if actor_id else None

        scope_rows = self._spend_rows(
            ledger,
            {
                "actorId": actor_id,
                "fromSequence": params.get("fromSequence"),
                "toSequence": params.get("toSequence"),
            },
        )
        pricing = self._spend_pricing_pack(params)
        price = None if pricing.fail_closed else pricing.price
        spent_usd, estimated_usd = 0.0, 0.0
        for record in metrics_mod.spend_records(scope_rows, price):
            spent_usd += record["recordedCostUsd"]
            if record["estimatedCostUsd"] is not None:
                estimated_usd += record["estimatedCostUsd"]
        spent_usd = round(spent_usd, 6)

        pack = self._governance_pack(params)
        ceilings_key = f"{pack.source}#budgetCeilings"
        ceilings: dict[str, Any] = {}
        any_breach = False
        agent_check = metrics_mod.check_spend_ceiling(
            spent_usd, pack.budget_ceilings.get("usdPerAgent")
        )
        ceilings["usdPerAgent"] = agent_check
        any_breach = any_breach or agent_check["breached"]
        story_check: dict[str, Any] | None = None
        if story_id is not None:
            story_rows = self._spend_rows(
                ledger,
                {
                    "storyId": story_id,
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
            )
            story_spent = 0.0
            for record in metrics_mod.spend_records(story_rows, price):
                story_spent += record["recordedCostUsd"] + (
                    record["estimatedCostUsd"] or 0.0
                )
            story_check = metrics_mod.check_spend_ceiling(
                round(story_spent, 6), pack.budget_ceilings.get("usdPerStory")
            )
            ceilings["usdPerStory"] = story_check
            any_breach = any_breach or story_check["breached"]

        # What Meridian controls: a hosted session (session_begin on
        # record — the row IS the hosted fact, F1-D t18) or a
        # meridian-native actor (Meridian hosts its own loops) can be
        # paused at a checkpoint; anything else is observed-only and
        # gets the advisory warning, the same NOT_HOSTED honesty as
        # steer — never a fake pause.
        hosted = False
        if session_id is not None:
            hosted = self._steer_hosted_begin(session_id) is not None
        elif actor_id is not None:
            vendors = {row.get("vendor") or "meridian" for row in scope_rows}
            sessions = {
                row.get("external_session_id")
                for row in scope_rows
                if row.get("external_session_id")
            }
            if any(self._steer_hosted_begin(s) is not None for s in sessions):
                hosted = True
            elif vendors and vendors <= {"meridian"}:
                hosted = True  # Meridian-native: its own runtime pauses.

        action = "none"
        sequence: int | None = None
        advisory = False
        note = "no ceiling breached"
        if any_breach:
            if hosted:
                action = "paused_at_checkpoint"
                note = (
                    "ceiling breached on a session Meridian hosts: recorded "
                    "and dispatched; the extension host pauses the session "
                    "at its next checkpoint (it owns the wire)"
                )
            else:
                action = "warned"
                advisory = True
                note = (
                    "ceiling breached on an observed agent: Meridian did not "
                    "launch this agent and cannot pause its session "
                    "(FR-M35-06 — observation never intercepts); the breach "
                    "is recorded and the operator warned, the same NOT_HOSTED "
                    "honesty as the steer surface"
                )
            # FR-M10-08: the enforcement/warning is durable BEFORE the RPC
            # returns; the encrypted blob carries the full detail.
            detail = {
                "method": "spend/ceilingCheck",
                "actorId": actor_id,
                "storyId": story_id,
                "sessionId": session_id,
                "hosted": hosted,
                "action": action,
                "spentUsd": spent_usd,
                "estimatedShareUsd": round(estimated_usd, 6),
                "ceilings": ceilings,
                "policySource": ceilings_key,
                "advisory": advisory,
            }
            sequence = ledger.append(
                {
                    "story_id": f"spend:ceiling:{actor_id or session_id}",
                    "phase": "build",
                    "loop_id": "spend-ceilings",
                    "loop_iteration": 1,
                    "actor_id": actor_id or "unknown-agent",
                    "actor_version": "0.0.0",
                    "actor_kind": "external" if not hosted else "role",
                    "policy_version": pack.policy_version,
                    "action_type": "spend_ceiling",
                    "decision": "halted" if hosted else None,
                    "rework_reason": "spend_ceiling",
                    "vendor": "meridian",
                    "input": json.dumps(detail, ensure_ascii=False),
                }
            ).sequence
            self._trust_cache.invalidate()
            if hosted and self._notification_sink is not None:
                self._notification_sink(
                    make_notification(
                        "spend/ceiling",
                        {
                            "sequence": sequence,
                            "sessionId": session_id,
                            "actorId": actor_id,
                            "action": "pauseAtCheckpoint",
                            "spentUsd": spent_usd,
                        },
                    )
                )
        return {
            "scope": {
                "actorId": actor_id,
                "storyId": story_id,
                "sessionId": session_id,
                "fromSequence": params.get("fromSequence"),
                "toSequence": params.get("toSequence"),
            },
            "spentUsd": spent_usd,
            "estimatedShareUsd": round(estimated_usd, 6),
            "ceilings": ceilings,
            "action": action,
            "hosted": hosted,
            "advisory": advisory,
            "sequence": sequence,
            "note": note,
        }

    def _handle_spend_forecast(
        self, params: bus_types.SpendForecastParams
    ) -> bus_types.SpendForecastResult:
        params = params or {}
        ledger = self._ensure_ledger()
        team = params.get("team")
        window = params.get("windowMonths")
        if window is not None and (
            not isinstance(window, int) or isinstance(window, bool) or window < 2
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS, "windowMonths must be an integer >= 2"
            )
        scope = {
            "team": team,
            "repoId": params.get("repoId"),
            "fromSequence": params.get("fromSequence"),
            "toSequence": params.get("toSequence"),
            "windowMonths": window,
        }
        cache_key = json.dumps(
            {"spendForecast": scope, "tip": ledger.last_sequence}, sort_keys=True
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            result = dict(cached)
            result["cacheHit"] = True
            return result  # type: ignore[return-value]

        rows = self._spend_rows(ledger, params)
        unmapped = 0
        if isinstance(team, str) and team.strip():
            meta = self._spend_story_meta(params)
            mapped = [
                row
                for row in rows
                if meta.lookup(row.get("story_id")).get("team") == team.strip()
            ]
            unmapped = len(rows) - len(mapped)
            rows = mapped
        pricing = self._spend_pricing_pack(params)
        price = None if pricing.fail_closed else pricing.price
        months = metrics_mod.monthly_spend_totals(rows, price)
        current_month = ledger_core.utc_now()[:7]
        forecast = metrics_mod.forecast_monthly_spend(
            months, current_month, window_months=window or 3
        )

        pack = self._governance_pack(params)
        budget_limit = pack.budget_ceilings.get("usdPerMonth")
        actual_month_usd = months.get(current_month)
        if not isinstance(budget_limit, (int, float)) or isinstance(budget_limit, bool):
            budget = {
                "limitUsd": None,
                "source": pack.source,
                "status": "unconfigured",
                "headroomUsd": None,
            }
        else:
            limit = float(budget_limit)
            if actual_month_usd is not None and actual_month_usd >= limit:
                budget_status = "actual_breach"
            elif (
                forecast["projectedUsd"] is not None
                and forecast["projectedUsd"] >= limit
            ):
                budget_status = "forecast_breach"
            else:
                budget_status = "ok"
            budget = {
                "limitUsd": limit,
                "source": pack.source,
                "status": budget_status,
                "headroomUsd": round(limit - (actual_month_usd or 0.0), 6),
            }
        # An actual or forecast breach is the alert FR-M39-03 exists for —
        # it outranks forecast evidence insufficiency (the bill is already
        # over budget; not projecting changes nothing).
        if budget["status"] in ("actual_breach", "forecast_breach"):
            status = budget["status"]
        elif forecast["status"] == "insufficient_evidence":
            status = "insufficient_evidence"
        else:
            status = budget["status"]
        result = {
            "scope": {**scope, "unmappedStoriesExcluded": unmapped},
            "team": team.strip() if isinstance(team, str) and team.strip() else None,
            "months": months,
            "forecast": forecast,
            "budget": budget,
            "status": status,
            "cacheHit": False,
        }
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    def _handle_spend_pricing(
        self, params: bus_types.SpendPricingParams
    ) -> bus_types.SpendPricingResult:
        params = params or {}
        pack = self._spend_pricing_pack(params)
        return {
            "source": pack.source,
            "version": pack.version,
            "currency": pack.currency,
            "models": [
                {
                    "vendor": rate.vendor,
                    "model": rate.model,
                    "tokensInPerMillion": rate.tokens_in_per_million,
                    "tokensOutPerMillion": rate.tokens_out_per_million,
                }
                for rate in pack.rates
            ],
            "errors": list(pack.errors),
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
        # FR-M17-05: derived trust metrics may not outlive the facts they
        # derive from — every append invalidates the in-process cache.
        self._trust_cache.invalidate()
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

    # -- ACP hosted-session recording (FR-M34-02/04, SEC-28; task 4) ----------

    #: Fallback policy tag when the host does not name the policy file version.
    ACP_DEFAULT_POLICY_VERSION = "acp-permissions/v1"

    def _append_acp_entry(self, entry: dict[str, Any], detail: dict[str, Any]) -> None:
        """Append one hosted-session fact; the encrypted input blob carries
        the wire detail (cwd, stop reason, tool call) alongside the row."""
        ledger = self._ensure_ledger()
        ledger.append({**entry, "input": json.dumps(detail, ensure_ascii=False)})
        # FR-M17-05: derived trust metrics may not outlive new facts.
        self._trust_cache.invalidate()

    def _handle_acp_session_begin(
        self, params: bus_types.AcpSessionBeginParams
    ) -> bus_types.AcpSessionRecordResult:
        # The session exists in the ledger BEFORE the agent's first turn:
        # hosted work is governed work from sequence one.
        detail = {
            "cwd": params["cwd"],
            "agentVersion": params.get("agentVersion"),
            # FR-M25-06: dry-run sessions plan and cost but write nothing;
            # the mode is part of the durable session fact.
            "mode": params.get("mode") or "normal",
        }
        self._append_acp_entry(
            {
                "ts_utc": params.get("startedAt") or ledger_core.utc_now(),
                "story_id": f"acp:{params['sessionId']}",
                "phase": "build",
                "loop_id": "acp-host",
                "loop_iteration": 1,
                "actor_id": params["agentId"],
                "actor_version": params.get("agentVersion") or "0.0.0",
                "actor_kind": "external",
                "policy_version": params.get("policyVersion")
                or self.ACP_DEFAULT_POLICY_VERSION,
                "action_type": "session_begin",
                "vendor": "acp",
                "observation_confidence": "direct",
                "external_session_id": params["sessionId"],
            },
            detail,
        )
        return {"recorded": True}

    def _acp_actor_for_session(self, session_id: str) -> str:
        """Best-effort attribution of a session end to the begin entry's
        actor; 'unknown' when no begin was recorded (never a crash)."""
        ledger = self._ensure_ledger()
        begins = ledger.query(action_type="session_begin", limit=10_000)
        for row in reversed(begins):
            if row.get("external_session_id") == session_id:
                return str(row["actor_id"])
        return "unknown"

    def _handle_acp_session_end(
        self, params: bus_types.AcpSessionEndParams
    ) -> bus_types.AcpSessionRecordResult:
        actor = params.get("agentId") or self._acp_actor_for_session(params["sessionId"])
        detail = {"sessionId": params["sessionId"], "stopReason": params.get("stopReason")}
        self._append_acp_entry(
            {
                "ts_utc": params.get("endedAt") or ledger_core.utc_now(),
                "story_id": f"acp:{params['sessionId']}",
                "phase": "build",
                "loop_id": "acp-host",
                "loop_iteration": 1,
                "actor_id": actor,
                "actor_version": "0.0.0",
                "actor_kind": "external" if actor != "unknown" else "meta",
                "policy_version": params.get("policyVersion")
                or self.ACP_DEFAULT_POLICY_VERSION,
                "action_type": "session_end",
                "vendor": "acp",
                "observation_confidence": "direct",
                "external_session_id": params["sessionId"],
            },
            detail,
        )
        return {"recorded": True}

    def _handle_acp_permission_decision(
        self, params: bus_types.AcpPermissionDecisionParams
    ) -> bus_types.AcpSessionRecordResult:
        # The governance trail is durable before and independently of the
        # human answer. denied_by_policy lands as decision 'rejected' with
        # the citation in rework_reason — the exact records SEC-28
        # re-request checks look up by actor.
        outcome = params["outcome"]
        decision = (
            "approved"
            if outcome == "selected"
            else "rejected"
            if outcome == "denied_by_policy"
            else None
        )
        detail = {
            key: params.get(key)
            for key in ("sessionId", "adapterId", "toolCallId", "toolKind", "path", "optionId", "reason")
            if params.get(key) is not None
        }
        entry: dict[str, Any] = {
            "ts_utc": params.get("decidedAt") or ledger_core.utc_now(),
            "story_id": f"acp:{params['sessionId']}",
            "phase": "build",
            "loop_id": "acp-host",
            "loop_iteration": 1,
            "actor_id": params.get("adapterId") or "acp-host",
            "actor_version": "0.0.0",
            "actor_kind": "external" if params.get("adapterId") else "meta",
            "policy_version": params.get("policyVersion")
            or self.ACP_DEFAULT_POLICY_VERSION,
            "action_type": "permission_decision",
            "vendor": "acp",
            "observation_confidence": "direct",
            "external_session_id": params["sessionId"],
        }
        if decision is not None:
            entry["decision"] = decision
        if params.get("reason"):
            entry["rework_reason"] = params["reason"]
        self._append_acp_entry(entry, detail)
        return {"recorded": True}

    # -- steer & clarify over hosted sessions (FR-M25-01..04/06; F1 D t17) ----

    #: The steering records are governed-work records of their own, not
    #: acp-permissions policy decisions.
    STEER_POLICY_VERSION = "governor-steer/v1"

    def _steer_hosted_begin(self, session_id: str) -> dict[str, Any] | None:
        """The newest session_begin row for a session the extension host
        reported as hosted. None when Meridian never hosted it — an
        observed (or unknown) session. Only the host reports session_begin,
        so the row's existence IS the hosted fact (F1 Workstream D task 18).
        """
        ledger = self._ensure_ledger()
        begins = ledger.query(action_type="session_begin", limit=10_000)
        for row in reversed(begins):
            if row.get("external_session_id") == session_id:
                return row
        return None

    def _steer_require_hosted(self, session_id: str, method: str) -> dict[str, Any]:
        """Fail-closed hosted check: every mutating steer RPC refuses an
        observed session with the structured NOT_HOSTED error — an honest
        refusal naming the situation, never a silent no-op."""
        row = self._steer_hosted_begin(session_id)
        if row is not None:
            return row
        raise _RpcError(
            protocol.ERROR_NOT_HOSTED,
            f"session '{session_id}' is observed, not hosted — Meridian did "
            f"not launch this agent and cannot steer, clarify, or halt its "
            f"session. Observation and merge gating continue; steer/accept "
            f"apply only to sessions Meridian hosts.",
            {
                "method": method,
                "sessionId": session_id,
                "hosted": False,
                "observedOnly": True,
                "remediation": (
                    "Steering requires a hosted ACP session (one Meridian "
                    "launched). For an observed agent, use gate.halt with "
                    "scope observe-only to block its merge path."
                ),
            },
        )

    def _append_steer_entry(
        self,
        *,
        session_id: str,
        action_type: str,
        detail: dict[str, Any],
        actor_id: str | None = None,
        human_actor: str | None = None,
        decision: str | None = None,
    ) -> int:
        """FR-M10-08: the steering act is durable BEFORE the RPC returns.
        The encrypted input blob carries the full wire detail; who steered
        (FR-M20-01) rides the human_actor column, never a free-text param.
        """
        ledger = self._ensure_ledger()
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": f"acp:{session_id}",
            "phase": "build",
            "loop_id": "acp-host",
            "loop_iteration": 1,
            "actor_id": actor_id or "acp-host",
            "actor_version": "0.0.0",
            "actor_kind": "external" if actor_id else "meta",
            "policy_version": self.STEER_POLICY_VERSION,
            "action_type": action_type,
            "vendor": "acp",
            "observation_confidence": "direct",
            "external_session_id": session_id,
            "input": json.dumps(detail, ensure_ascii=False),
        }
        if human_actor:
            entry["human_actor"] = human_actor
        if decision:
            entry["decision"] = decision
        result = ledger.append(entry)
        self._trust_cache.invalidate()
        return result.sequence

    @staticmethod
    def _steer_session_id(params: dict[str, Any], method: str) -> str:
        session_id = params.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, f"{method} needs a sessionId"
            )
        return session_id

    def _handle_steer_send(
        self, params: bus_types.SteerSendParams
    ) -> bus_types.SteerSendResult:
        # FR-M25-01: the steering act is recorded (who steered — the
        # resolved human identity — what, when) BEFORE the host injects
        # the guidance into the running session over the wire.
        session_id = self._steer_session_id(params or {}, "steer.send")
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "steer.send needs a message")
        begin = self._steer_require_hosted(session_id, "steer.send")
        who = self._human_identity()
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="steer",
            detail={"message": message},
            actor_id=str(begin["actor_id"]),
            human_actor=who.display(),
        )
        return {"accepted": True, "sequence": sequence}

    def _handle_steer_question(
        self, params: bus_types.SteerQuestionParams
    ) -> bus_types.SteerQuestionResult:
        # FR-M25-02: the question is durable BEFORE the human sees it, so
        # the answer can always be bound to the question it answers.
        session_id = self._steer_session_id(params or {}, "steer/question")
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            raise _RpcError(
                protocol.INVALID_PARAMS, "steer/question needs a question"
            )
        begin = self._steer_require_hosted(session_id, "steer/question")
        detail: dict[str, Any] = {"question": question}
        options = params.get("options")
        if isinstance(options, list):
            detail["options"] = options
        if params.get("toolCallId"):
            detail["toolCallId"] = params["toolCallId"]
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="clarifying_question",
            detail=detail,
            actor_id=str(begin["actor_id"]),
        )
        return {"accepted": True, "sequence": sequence}

    def _handle_steer_answer(
        self, params: bus_types.SteerAnswerParams
    ) -> bus_types.SteerAnswerResult:
        # FR-M25-02: the recorded answer is what resumes the loop; a
        # dismissal is recorded honestly as cancelled, never dropped.
        session_id = self._steer_session_id(params or {}, "steer/answer")
        question_sequence = params.get("questionSequence")
        if not isinstance(question_sequence, int):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "steer/answer needs the questionSequence it answers",
            )
        self._steer_require_hosted(session_id, "steer/answer")
        ledger = self._ensure_ledger()
        question_row = ledger.get_entry(question_sequence)
        if (
            question_row is None
            or question_row.get("action_type") != "clarifying_question"
            or question_row.get("external_session_id") != session_id
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"no recorded clarifying question at sequence {question_sequence} "
                f"for session '{session_id}' — answers bind to a durable question",
            )
        who = self._human_identity()
        detail: dict[str, Any] = {
            "questionSequence": question_sequence,
            "cancelled": bool(params.get("cancelled")),
        }
        if params.get("selectedOptionId"):
            detail["selectedOptionId"] = params["selectedOptionId"]
        if params.get("text"):
            detail["text"] = params["text"]
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="clarifying_answer",
            detail=detail,
            human_actor=who.display(),
            decision="cancelled" if params.get("cancelled") else "answered",
        )
        return {"accepted": True, "sequence": sequence, "resumed": True}

    def _handle_steer_escalate(
        self, params: bus_types.SteerEscalateParams
    ) -> bus_types.SteerEscalateResult:
        # FR-M25-03: stated confidence below the per-class threshold — the
        # escalation is a durable event surfaced to the human; the policy
        # gate asks rather than acting until a human decides.
        session_id = self._steer_session_id(params or {}, "steer/escalate")
        action_class = params.get("actionClass")
        confidence = params.get("confidence")
        threshold = params.get("threshold")
        if (
            not isinstance(action_class, str)
            or not action_class.strip()
            or not isinstance(confidence, (int, float))
            or not isinstance(threshold, (int, float))
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "steer/escalate needs actionClass, confidence and threshold",
            )
        begin = self._steer_require_hosted(session_id, "steer/escalate")
        detail: dict[str, Any] = {
            "actionClass": action_class,
            "confidence": confidence,
            "threshold": threshold,
        }
        if params.get("toolCallId"):
            detail["toolCallId"] = params["toolCallId"]
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="escalation",
            detail=detail,
            actor_id=str(begin["actor_id"]),
        )
        return {"accepted": True, "sequence": sequence, "escalated": True}

    def _handle_steer_accept(
        self, params: bus_types.SteerAcceptParams
    ) -> bus_types.SteerAcceptResult:
        # FR-M25-04: one action carries both halves — accepted and
        # reworked — per file and hunk, recorded before the response.
        session_id = self._steer_session_id(params or {}, "steer/accept")
        accepted = params.get("accepted")
        rejected = params.get("rejected")
        if not isinstance(accepted, list) or not isinstance(rejected, list):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "steer/accept needs accepted and rejected file lists",
            )
        self._steer_require_hosted(session_id, "steer/accept")
        who = self._human_identity()
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="partial_acceptance",
            detail={"accepted": accepted, "rejected": rejected},
            human_actor=who.display(),
        )
        return {"accepted": True, "sequence": sequence}

    def _steer_acceptance_entries(
        self, session_id: str
    ) -> list[dict[str, Any]]:
        """The decrypted partial_acceptance details, ascending — the
        fold order for the latest-state answer."""
        ledger = self._ensure_ledger()
        rows = ledger.query(
            story_id=f"acp:{session_id}",
            action_type="partial_acceptance",
            limit=1000,
        )
        entries: list[dict[str, Any]] = []
        for row in rows:
            detail_row = ledger.get_entry(row["seq"])
            if detail_row is None:
                continue
            detail = ledger_wire.row_to_detail(detail_row, ledger.read_blob)
            if not detail.get("inputAvailable") or not detail.get("input"):
                continue
            try:
                entries.append(json.loads(detail["input"]))
            except (TypeError, ValueError):
                continue  # never a crash on a foreign blob
        return entries

    def _handle_steer_acceptance_status(
        self, params: bus_types.SteerAcceptanceStatusParams
    ) -> bus_types.SteerAcceptanceStatusResult:
        session_id = self._steer_session_id(params or {}, "steer/acceptanceStatus")
        begin = self._steer_hosted_begin(session_id)
        if begin is None:
            # Observed (or unknown) session: nothing accepted, nothing
            # rejectable — the honest empty answer (task 18).
            return {"sessionId": session_id, "hosted": False, "files": []}
        # Fold every recorded acceptance in order; the newest record for a
        # file wins, the ledger keeps the full history.
        latest: dict[str, dict[str, Any]] = {}
        rows = self._ensure_ledger().query(
            story_id=f"acp:{session_id}", action_type="partial_acceptance", limit=1000
        )
        for index, entry in enumerate(self._steer_acceptance_entries(session_id)):
            row = rows[index] if index < len(rows) else {}
            decided_by = row.get("human_actor") or "unknown"
            sequence = row.get("seq", 0)
            # FR-M25-04: one action accepts some hunks and reworks others,
            # so both halves of THIS entry merge per file before folding
            # over any earlier record.
            per_file: dict[str, list[dict[str, Any]]] = {}
            for side, state in (("accepted", "accepted"), ("rejected", "rejected")):
                for file_entry in entry.get(side) or []:
                    if not isinstance(file_entry, dict):
                        continue
                    name = file_entry.get("file")
                    if not isinstance(name, str):
                        continue
                    per_file.setdefault(name, []).extend(
                        {"index": int(h["index"]), "state": state}
                        for h in file_entry.get("hunks") or []
                        if isinstance(h, dict) and isinstance(h.get("index"), int)
                    )
            for name, hunks in per_file.items():
                latest[name] = {
                    "file": name,
                    "hunks": hunks,
                    "decidedBy": str(decided_by),
                    "sequence": int(sequence),
                }
        return {
            "sessionId": session_id,
            "hosted": True,
            "files": [latest[name] for name in sorted(latest)],
        }

    def _handle_steer_status(
        self, params: bus_types.SteerStatusParams
    ) -> bus_types.SteerStatusResult:
        # Task 18: the capability payload every session control renders
        # from. hosted comes from the hosted session_begin record — an
        # observe-only session answers hosted: false and carries no mode,
        # so the UI cannot construct a dead steer control for it.
        session_id = self._steer_session_id(params or {}, "steer/status")
        begin = self._steer_hosted_begin(session_id)
        if begin is None:
            return {"sessionId": session_id, "hosted": False}
        status: dict[str, Any] = {
            "sessionId": session_id,
            "hosted": True,
            "beginSequence": begin["seq"],
            "beganAt": begin["ts_utc"],
            "adapterId": str(begin["actor_id"]),
        }
        detail_row = self._ensure_ledger().get_entry(begin["seq"])
        ledger = self._ensure_ledger()
        if detail_row is not None:
            detail = ledger_wire.row_to_detail(detail_row, ledger.read_blob)
            if detail.get("inputAvailable") and detail.get("input"):
                try:
                    mode = json.loads(detail["input"]).get("mode", "normal")
                except (TypeError, ValueError):
                    mode = "normal"
                status["mode"] = mode if mode in ("normal", "dry-run") else "normal"
        ends = ledger.query(action_type="session_end", limit=10_000)
        for row in reversed(ends):
            if row.get("external_session_id") == session_id:
                status["endedAt"] = row["ts_utc"]
                status["endSequence"] = row["seq"]
                break
        return status

    def _handle_steer_plan(
        self, params: bus_types.SteerPlanParams
    ) -> bus_types.SteerPlanResult:
        # FR-M25-06: the dry run's planner output is durable before the
        # RPC returns — a dry run produces a provable packet graph and
        # cost estimate, and nothing else.
        session_id = self._steer_session_id(params or {}, "steer/plan")
        entries = params.get("entries")
        if not isinstance(entries, list):
            raise _RpcError(
                protocol.INVALID_PARAMS, "steer/plan needs the plan entries"
            )
        begin = self._steer_require_hosted(session_id, "steer/plan")
        detail: dict[str, Any] = {"entries": entries}
        if isinstance(params.get("costEstimate"), dict):
            detail["costEstimate"] = params["costEstimate"]
        sequence = self._append_steer_entry(
            session_id=session_id,
            action_type="plan_output",
            detail=detail,
            actor_id=str(begin["actor_id"]),
        )
        return {"accepted": True, "sequence": sequence}

    # -- worktree isolation (FR-M18-01..08; F1 Workstream A task 5) -----------

    def _worktree_manager(self, params: dict[str, Any]) -> worktree_mod.WorktreeManager:
        repo = (params or {}).get("repoPath") or self._workspace_dir
        if not repo:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "worktree methods need repoPath (or a workspaceDir handshake)",
            )
        try:
            return worktree_mod.WorktreeManager(Path(repo))
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    @staticmethod
    def _worktree_error(error: worktree_mod.WorktreeError) -> _RpcError:
        return _RpcError(protocol.INVALID_PARAMS, str(error))

    @staticmethod
    def _worktree_info_to_wire(info: worktree_mod.WorktreeInfo) -> bus_types.WorktreeInfo:
        return {
            "storyId": info.story_id,
            "branch": info.branch,
            "path": str(info.path),
            "worktreeRef": info.worktree_ref,
            "baseBranch": info.base_branch,
            "baseCommit": info.base_commit,
            "headCommit": info.head_commit,
            "adapterId": info.adapter_id,
            "dirty": info.dirty,
            "unpushedCommits": info.unpushed_commits,
        }

    def _append_worktree_entry(
        self,
        action_type: str,
        story_id: str,
        worktree_ref: str,
        actor_id: str,
        detail: dict[str, Any],
    ) -> None:
        """Task 5f: every create/remove/abort lands in the ledger with
        worktree_ref set, so the worktree's lifecycle is provenance too."""
        ledger = self._ensure_ledger()
        ledger.append(
            {
                "ts_utc": ledger_core.utc_now(),
                "story_id": story_id,
                "phase": "build",
                "loop_id": "worktree",
                "loop_iteration": 1,
                "actor_id": actor_id,
                "actor_version": "0",
                "actor_kind": "meta",
                "policy_version": "f1-worktrees",
                "action_type": action_type,
                "vendor": "meridian",
                "observation_confidence": "direct",
                "worktree_ref": worktree_ref,
                "input": json.dumps(detail, ensure_ascii=False),
            }
        )
        self._trust_cache.invalidate()

    def _handle_worktree_create(
        self, params: bus_types.WorktreeCreateParams
    ) -> bus_types.WorktreeCreateResult:
        params = params or {}
        manager = self._worktree_manager(params)
        try:
            info = manager.create(
                params["storyId"],
                params["adapterId"],
                base_branch=params.get("baseBranch")
                or worktree_mod.DEFAULT_BASE_BRANCH,
            )
        except worktree_mod.WorktreeError as error:
            raise self._worktree_error(error) from error
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        self._append_worktree_entry(
            "worktree_create",
            info.story_id,
            info.worktree_ref,
            params["adapterId"],
            {
                "branch": info.branch,
                "path": str(info.path),
                "baseBranch": info.base_branch,
                "baseCommit": info.base_commit,
                "identity": list(worktree_mod.agent_identity(params["adapterId"])),
                "trailer": worktree_mod.TRAILER_KEY,
            },
        )
        return {"worktree": self._worktree_info_to_wire(info)}

    def _handle_worktree_list(
        self, params: bus_types.WorktreeListParams
    ) -> bus_types.WorktreeListResult:
        manager = self._worktree_manager(params)
        try:
            return {
                "worktrees": [
                    self._worktree_info_to_wire(info) for info in manager.list()
                ]
            }
        except worktree_mod.WorktreeError as error:
            raise self._worktree_error(error) from error
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

    def _handle_worktree_remove(
        self, params: bus_types.WorktreeRemoveParams
    ) -> bus_types.WorktreeRemoveResult:
        params = params or {}
        manager = self._worktree_manager(params)
        try:
            info = manager.remove(params["storyId"], force=bool(params.get("force")))
        except worktree_mod.WorktreeError as error:
            raise self._worktree_error(error) from error
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        self._append_worktree_entry(
            "worktree_remove",
            info.story_id,
            info.worktree_ref,
            "worktree-manager",
            {
                "branch": info.branch,
                "force": bool(params.get("force")),
                "reason": params.get("reason"),
                "headCommit": info.head_commit,
            },
        )
        return {
            "removed": True,
            "storyId": info.story_id,
            "branch": info.branch,
            "worktreeRef": info.worktree_ref,
        }

    def _handle_worktree_abort_story(
        self, params: bus_types.WorktreeAbortStoryParams
    ) -> bus_types.WorktreeAbortStoryResult:
        params = params or {}
        manager = self._worktree_manager(params)
        try:
            info, branch_deleted, kept_reason = manager.abort(params["storyId"])
        except worktree_mod.WorktreeError as error:
            raise self._worktree_error(error) from error
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        # FR-M18-04: the abort itself is ledger-recorded; actor 'human'
        # (D9's identity source lands later and upgrades this attribution).
        self._append_worktree_entry(
            "story_abort",
            info.story_id,
            info.worktree_ref,
            "human",
            {
                "branch": info.branch,
                "branchDeleted": branch_deleted,
                "branchKeptReason": kept_reason,
                "headCommit": info.head_commit,
                "dirtyAtAbort": info.dirty,
            },
        )
        return {
            "removed": True,
            "storyId": info.story_id,
            "branch": info.branch,
            "branchDeleted": branch_deleted,
            **({"branchKeptReason": kept_reason} if kept_reason else {}),
            "worktreeRef": info.worktree_ref,
        }

    def _handle_worktree_conflicts(
        self, params: bus_types.WorktreeConflictsParams
    ) -> bus_types.WorktreeConflictsResult:
        params = params or {}
        manager = self._worktree_manager(params)
        try:
            report = manager.conflicts(
                story_id=params.get("storyId"),
                base_branch=params.get("baseBranch")
                or worktree_mod.DEFAULT_BASE_BRANCH,
                target_paths=params.get("targetPaths"),
            )
        except worktree_mod.WorktreeError as error:
            raise self._worktree_error(error) from error
        except AttributionError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        return {
            "repoPath": str(report.repo),
            "baseBranch": report.base_branch,
            "blocked": report.blocked,
            "conflicts": [
                {"kind": c.kind, "path": c.path, "detail": c.detail}
                for c in report.conflicts
            ],
        }

    # -- MCP server gateway (FR-M34-06; F1 Workstream A task 6) ---------------

    #: MCP tool name -> the existing read-only bus method it forwards to.
    #: The MCP server process (extension/src/mcp/) advertises exactly these
    #: names in its tools/list; the sidecar remains the authority for what
    #: exists and what each call did.
    MCP_TOOLS: dict[str, str] = {
        "ledger_query": "ledger.query",
        "ledger_export_bundle": "ledger.exportBundle",
        "ledger_verify": "ledger.verify",
        "trust_rejection_rate": "trust/rejectionRate",
    }

    def _handle_mcp_invoke(
        self, params: bus_types.McpInvokeParams
    ) -> bus_types.McpInvokeResult:
        params = params or {}
        tool = params.get("tool")
        if not isinstance(tool, str) or tool not in self.MCP_TOOLS:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"unknown MCP tool: {tool!r}",
                {"tool": tool, "availableTools": sorted(self.MCP_TOOLS)},
            )
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise _RpcError(
                protocol.INVALID_PARAMS, "arguments must be an object", {"tool": tool}
            )
        # The governance trail is durable before and independently of the
        # outcome: an external MCP client invoked this tool, and the ledger
        # says so even if the underlying read then fails.
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": f"mcp:{tool}",
            "phase": "intake",
            "loop_id": "mcp-server",
            "loop_iteration": 1,
            "actor_id": params.get("client") or "mcp-client",
            "actor_version": "0",
            "actor_kind": "external",
            "policy_version": "mcp-server/v1",
            "action_type": "tool_call",
            "vendor": "mcp",
            "observation_confidence": "direct",
            "input": json.dumps(
                {"tool": tool, "arguments": arguments}, ensure_ascii=False
            ),
        }
        if params.get("sessionId"):
            entry["external_session_id"] = params["sessionId"]
        ledger = self._ensure_ledger()
        ledger.append(entry)
        self._trust_cache.invalidate()
        # Reuse the existing handler — the MCP surface adds protocol and
        # governance, not a second implementation of the reads.
        handler = self._handlers[self.MCP_TOOLS[tool]]
        outcome = handler(self, arguments)
        return {"tool": tool, "result": outcome}


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
