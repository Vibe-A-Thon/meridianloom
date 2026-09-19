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
from . import licensing
from .licensing import store as licence_store
from . import identity as authenticated_identity
from .attribution import blame, diff as attribution_diff, wire as attribution_wire
from .attribution import symbols as symbols_mod
from .attribution import heuristics
from .attribution import AttributionError
from .attribution._git import normalise_repo_path as attribution_normalise
from .governance import bootstrap as policy_bootstrap
from .governance import approval_class as governance_approval_class
from .governance import engine as governance_engine
from .governance import enforcement_points as governance_enforcement
from .governance import identity as governance_identity
from .governance import merge_gate as governance_merge_gate
from .governance import policy as governance_policy
from .governance import revocations as governance_revocations
from .governance import roles as governance_roles
from . import initiation
from . import interop
from . import contract_versions
from . import hooks as provenance_hooks
from . import metrics as metrics_mod
from .metrics import evidence_gate
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
from .observers import retention as observer_retention
from .observers import sessions as observer_sessions
from .rpc import (
    FramedReader,
    FramedWriter,
    make_error_response,
    make_notification,
    make_response,
)

logger = logging.getLogger("meridian_core.server")


def _signer_fingerprint(public_key: bytes) -> str:
    import hashlib

    return hashlib.sha256(public_key).hexdigest()


def _record_signer_marker(workspace: Path, public_key: bytes) -> None:
    """TASK-002 (audit NEW-GAP-E): the extension host's provisioned
    signing key is authoritative; record its fingerprint so headless
    consumers (the collector) can detect a two-signer ambiguity instead
    of silently signing one chain with two keys. A changed fingerprint
    (legitimate key rotation via the host) rewrites the marker and is
    logged — collector users must then be given the new seed."""
    marker = workspace / ".meridian" / "ledger-signer.fp"
    fingerprint = _signer_fingerprint(public_key)
    if marker.is_file() and marker.read_text(encoding="ascii").strip() != fingerprint:
        logger.warning(
            "ledger signing key changed for %s — collector/headless users "
            "must be given the new MERIDIAN_LEDGER_SIGNING_SEED",
            workspace,
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(fingerprint + "\n", encoding="ascii")


def _parse_iso(value: Any, field: str) -> datetime:
    """Parse an ISO 8601 timestamp param; an invalid value is an
    INVALID_PARAMS refusal, never a silent default."""
    if not isinstance(value, str) or not value.strip():
        raise _RpcError(protocol.INVALID_PARAMS, f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise _RpcError(
            protocol.INVALID_PARAMS, f"{field} must be an ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed

#: Every ledger sequence a caller can name. SQLite's ``seq`` is a positive
#: 64-bit rowid, so anything outside that range cannot address a row and is a
#: caller error rather than an empty result.
_MAX_SEQUENCE = 2**63 - 1


def _check_sequence_params(method: str, params: Any) -> None:
    """Refuse a malformed sequence filter instead of quietly answering wrong.

    Twenty RPCs take ``fromSequence`` / ``toSequence`` / ``afterSequence`` /
    ``sequence`` and none of them validated it. A string, a float or a negative
    number reached the SQL layer as a bound parameter, where SQLite compares
    across types rather than failing — so ``fromSequence: "abc"`` returned a
    figure computed over the wrong rows, silently.

    For a product whose whole claim is that its numbers can be trusted, a
    silently-wrong figure is a worse outcome than a crash. This runs once at
    the dispatch boundary rather than in twenty handlers, so a method added
    later inherits the check by naming its parameter the same way.

    Booleans are rejected explicitly: ``isinstance(True, int)`` is True in
    Python, and ``fromSequence: true`` is a caller error, not sequence 1.
    """
    if not isinstance(params, dict):
        return
    for field, value in params.items():
        if value is None or not field.endswith(("Sequence", "sequence")):
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"{field} must be a whole number; {method} was given "
                f"{type(value).__name__}. Refusing rather than computing a "
                "figure over the wrong rows.",
            )
        if value < 0 or value > _MAX_SEQUENCE:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"{field} must be between 0 and {_MAX_SEQUENCE}; {method} was "
                f"given {value}. No ledger row can carry that sequence.",
            )


# Method handlers take (server, params) and return a JSON-able result.
Handler = Callable[["SidecarServer", Any], Any]


class SidecarServer:
    """Dispatches framed JSON-RPC requests to method handlers."""

    def __init__(
        self,
        ledger: ledger_core.Ledger | None = None,
        identity_provider: Any | None = None,
        notification_sink: Callable[[dict[str, Any]], None] | None = None,
        licence: licensing.LicenceManager | None = None,
    ) -> None:
        self._started_at = time.monotonic()
        # Free Community edition by default; Premium features unlock only
        # when a licence that verifies for this machine/developer is found
        # (see meridian_core.licensing). Offline; nothing is ever sent.
        self._licence = licence or licensing.new_manager()
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
        # interface — v1 git user.name/email (assurance "asserted" per D38),
        # the handshake identityProvider selection, or a test injection. Never
        # a free-text param (FR-M20-01).
        self._identity_provider = identity_provider
        # FR-M12-06: sidecar -> host notifications (gate/halt dispatch) ride
        # the same framed writer as responses; serve() installs the writer
        # here, tests inject a capture callable.
        self._notification_sink = notification_sink
        self._workspace_dir: str | None = None
        self._signing_seed: bytes | None = None
        # D43/AC-53 (N0-T09b): the policy-bootstrap scaffold events from
        # the workspace handshake — surfaced in health.policyScaffolds so
        # the host can show the visible first-run notice; empty when no
        # workspace handshook yet or every pack was already present.
        self._policy_scaffolds: list[dict[str, Any]] = []
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
        # FR-M44-12/13 (N1-T21/22): session-lifetime volatile-evidence
        # tracker — captures recorded here feed the evidence_expired
        # markers on observer health/sessions surfaces and the named
        # coverage gaps on trust-metric envelopes.
        self._evidence_expiry = observer_retention.EvidenceExpiryTracker()
        self._handlers: dict[str, Handler] = {
            "handshake": SidecarServer._handle_handshake,
            "ping": SidecarServer._handle_ping,
            "shutdown": SidecarServer._handle_shutdown,
            "health": SidecarServer._handle_health,
            "licence/status": SidecarServer._handle_licence_status,
            "licence/install": SidecarServer._handle_licence_install,
            "licence/remove": SidecarServer._handle_licence_remove,
            "doctor/run": SidecarServer._handle_doctor_run,
            "observe/sessions": SidecarServer._handle_observe_sessions,
            "observe/health": SidecarServer._handle_observe_health,
            # FR-M44-12 (N1-T21): volatile-evidence capture against the
            # documented retention windows (FR-M44-11).
            "observe/captureEvidence": SidecarServer._handle_observe_capture_evidence,
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
            # F2 (gaps_implementation.md §F2): the evidence gate, computed.
            # Its measures were all computable and all in different places;
            # assembling the verdict by hand is exactly the manual step this
            # project has repeatedly got wrong.
            "evidence/gate": SidecarServer._handle_evidence_gate,
            # FR-M39-01/02/03/04 (F1 Workstream F tasks 26-29): cross-vendor
            # spend — the real feed onto the SpendSeries protocol, config-
            # driven ceilings (pause hosted / warn observed), the monthly
            # forecast + budget alert, and the predictable pricing table.
            "spend/series": SidecarServer._handle_spend_series,
            "spend/ceilingCheck": SidecarServer._handle_spend_ceiling_check,
            "spend/forecast": SidecarServer._handle_spend_forecast,
            "spend/pricing": SidecarServer._handle_spend_pricing,
            # FR-M42-11/12, SEC-32 (MV1-T01): the honest enforcement-point
            # declaration. The computation already existed and fed the audit
            # bundle; nothing exposed it to an interface, so a surface had no
            # way to render a control's real boundary and two screens carried
            # hand-written prose notices instead. Prose does not compose.
            # M52 (MV3-T06): another tool's provenance record, read
            # and made tamper-evident. Flight Recorder, because this
            # is observation and observation is the honesty floor.
            # P31: notarise, do not duplicate — the digest goes in
            # the ledger, the content stays where its owner put it.
            "interop/records": SidecarServer._handle_interop_records,
            "interop/notarise": SidecarServer._handle_interop_notarise,
            "interop/verify": SidecarServer._handle_interop_verify,
            "interop/conflicts": SidecarServer._handle_interop_conflicts,
            "interop/export": SidecarServer._handle_interop_export,
            "governance/enforcementPoints": SidecarServer._handle_enforcement_points,
            # M40 (MV2): one contract, many doors. The door is
            # `origin`; nothing else about a run differs by door
            # (FR-M40-01/02, AC-38). Governor tier — and ABSENT
            # below it rather than registered-and-refused, which
            # is the scar G5 forbids (FR-M40-11, AC-40).
            "run/preflight": SidecarServer._handle_run_preflight,
            "run/start": SidecarServer._handle_run_start,
            "run/cancel": SidecarServer._handle_run_cancel,
            "gate.evaluate": SidecarServer._handle_gate_evaluate,
            "gate.profiles": SidecarServer._handle_gate_profiles,
            "gate.approve": SidecarServer._handle_gate_approve,
            # FR-M42-06/SEC-31/AC-46 (N2-T08): the ledger-recorded
            # revocation list — immediate in-process effect, five-minute
            # outer envelope for other replicas (NFR-36).
            "identity.revoke": SidecarServer._handle_identity_revoke,
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
        # TASK-011 (audit GAP-001): the Orchestra/F4+ surfaces dispatch to
        # the real F3/C3-C6 modules via orchestra_handlers. The import is
        # LAZY — the module pulls the LangGraph/cryptography stack, and
        # doing that at construction slowed every sidecar spawn enough to
        # trip parallel e2e readiness windows (recorded in DECISIONS).
        # The names come from the generated contract (light import).
        def _make_orchestra_handler(name: str):
            def _orchestra_bound(server: Any, params: Any) -> Any:
                from . import orchestra_handlers

                fn = orchestra_handlers.HANDLERS[name]
                try:
                    return fn(server, params)
                except orchestra_handlers.OrchestraWorkspaceError as exc:
                    raise _RpcError(protocol.ERROR_LEDGER_UNAVAILABLE, str(exc))
                except orchestra_handlers.OrchestraError as exc:
                    raise _RpcError(protocol.INVALID_PARAMS, str(exc))

            return _orchestra_bound

        _prefixes = (
            "loop.", "adapters/", "router/", "tools/", "memory/",
            "comprehension/", "portability/", "trainer/", "tenancy/",
            "queue/", "annotations/", "issues/", "simulation/", "golden/",
            "decisions/",
        )
        for _name in sorted(bus_types.REQUEST_METHODS):
            if _name.startswith(_prefixes):
                self._handlers[_name] = _make_orchestra_handler(_name)
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
            _record_signer_marker(
                Path(self._workspace_dir), self._ledger.signing_public_key
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
        # Edition gate, after the tier gate: a Premium feature needs a valid
        # licence in addition to its tier being enabled. Community methods
        # (the whole Flight Recorder, and licence management itself) never
        # reach the licence check at all.
        denial = self._licence.check_method(method)
        if denial is not None:
            return make_error_response(
                request_id,
                protocol.ERROR_LICENCE_REQUIRED,
                denial["message"],
                denial["data"],
            )
        handler = self._handlers.get(method)
        if handler is None:
            return make_error_response(
                request_id, protocol.METHOD_NOT_FOUND, f"unknown method: {method}"
            )
        try:
            request_params = message.get("params") or {}
            # One boundary check for every sequence filter in the registry
            # (see _check_sequence_params). Inside the try so its refusal is
            # returned as a structured INVALID_PARAMS like any other.
            _check_sequence_params(method, request_params)
            result = handler(self, request_params)
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
            # The per-developer licence check reads this workspace's git
            # identity, so the licence is (re)evaluated once it is known.
            self._licence.reload(workspace_dir)
            self._ensure_session_monitor()
            self._run_policy_bootstrap(Path(workspace_dir))
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
        # TASK-321: release the loop checkpointer connection if the
        # orchestrator was used this session.
        orch = getattr(self, "_orchestra", None)
        if orch is not None:
            orch.shutdown()
        self._shutdown_requested.set()
        return {"ok": True}

    def _handle_health(self, params: bus_types.HealthParams) -> bus_types.HealthResult:
        return {
            "status": "shutting-down" if self._shutdown_requested.is_set() else "ok",
            "uptimeSeconds": round(time.monotonic() - self._started_at, 3),
            "pid": os.getpid(),
            "activeLoops": 0,  # loops land in Workstream E
            # D43/AC-53: the policy-bootstrap scaffold events from the
            # workspace handshake (empty when nothing was scaffolded).
            "policyScaffolds": list(self._policy_scaffolds),
        }

    # -- licence (always available; see licensing/editions.ALWAYS_AVAILABLE) --

    def _licence_result(self, status: licensing.LicenceStatus, fingerprint: bool) -> dict[str, Any]:
        wire = status.to_wire()
        if fingerprint:
            from .licensing import machine as licence_machine

            wire["machineFingerprint"] = licence_machine.machine_fingerprint()
        return wire

    def _handle_licence_status(self, params: Any) -> dict[str, Any]:
        params = params or {}
        status = self._licence.reload() if params.get("reload") else self._licence.status
        return self._licence_result(status, bool(params.get("includeFingerprint")))

    def _handle_licence_install(self, params: Any) -> dict[str, Any]:
        params = params or {}
        text = params.get("text")
        path = params.get("path")
        if (text is None) == (path is None):
            raise _RpcError(protocol.INVALID_PARAMS, "licence/install needs exactly one of 'path' or 'text'")
        if path is not None:
            try:
                text = Path(path).read_text(encoding="utf-8-sig")
            except OSError as error:
                raise _RpcError(
                    protocol.INVALID_PARAMS, f"cannot read licence file: {error.strerror or error}"
                ) from error
        scope = params.get("scope") or licence_store.SCOPE_USER
        try:
            status = self._licence.install(str(text), scope)
        except licensing.LicenceError as error:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"licence not installed: {error}",
                data={"state": error.state},
            ) from error
        except (PermissionError, ValueError) as error:
            raise _RpcError(protocol.INVALID_PARAMS, f"licence not installed: {error}") from error
        return self._licence_result(status, False)

    def _handle_licence_remove(self, params: Any) -> dict[str, Any]:
        scope = (params or {}).get("scope") or licence_store.SCOPE_USER
        try:
            removed = self._licence.remove(scope)
        except ValueError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        return {"removed": removed, "status": self._licence_result(self._licence.status, False)}

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

    def _run_policy_bootstrap(self, workspace: Path) -> None:
        """D43/AC-53: on the workspace handshake, scaffold the shipped
        policy packs into ``<ws>/.meridian/policy/`` when the workspace has
        none (never overwriting team files), and keep the structured
        scaffold events in server state for health. A re-handshake re-runs
        the bootstrap — it is a no-op for every pack the team now owns."""
        try:
            events = policy_bootstrap.bootstrap_policy_packs(workspace)
        except OSError as error:
            logger.warning("policy bootstrap failed for %s: %s", workspace, error)
            return
        self._policy_scaffolds = [dataclasses.asdict(event) for event in events]
        for warning in policy_bootstrap.scaffold_warnings(events):
            logger.warning("%s", warning)

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
        # FR-M44-13/AC-47: a closed evidence window rides the sessions
        # surface as a named marker in every branch, never as a silent
        # empty session list.
        expiry_warnings = self._evidence_expiry.warnings()
        if monitor is None or not monitor.running:
            return {
                "sessions": [],
                "warnings": [
                    "session observation not started — no workspaceDir handshake yet",
                    *expiry_warnings,
                ],
            }
        snapshot = monitor.snapshot()
        warnings = list(snapshot["warnings"]) + expiry_warnings
        return {"sessions": snapshot["sessions"], "warnings": warnings}

    def _handle_observe_health(
        self, params: bus_types.ObserveHealthParams
    ) -> bus_types.ObserveHealthResult:
        # FR-M35-08: pure in-memory health records; safe to compute inline.
        return {
            "observers": self._observers.health(),
            "monitorRunning": bool(
                self._session_monitor and self._session_monitor.running
            ),
            # FR-M44-13/AC-47: closed retention windows downgrade observer
            # health within one session — named, never silent.
            "evidenceExpired": [
                marker.to_dict() for marker in self._evidence_expiry.markers()
            ],
        }

    def _handle_observe_capture_evidence(
        self, params: bus_types.CaptureEvidenceParams
    ) -> bus_types.CaptureEvidenceResult:
        """FR-M44-12 / NFR-37 (N1-T21): record one volatile-evidence
        capture against the vendor's documented retention window, deriving
        latency and achieved margin in the same operation (NFR-34)."""
        params = params or {}
        vendor = params.get("vendor")
        if not isinstance(vendor, str) or not vendor.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "vendor must be a non-empty string")
        source = params.get("source")
        if not isinstance(source, str) or not source.strip():
            raise _RpcError(protocol.INVALID_PARAMS, "source must be a non-empty string")
        evidence_time = _parse_iso(params.get("evidenceTime"), "evidenceTime")
        captured_at = (
            _parse_iso(params.get("capturedAt"), "capturedAt")
            if params.get("capturedAt")
            else None
        )
        unavailable = params.get("unavailable") or []
        if not isinstance(unavailable, list) or any(
            not isinstance(item, str) for item in unavailable
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS, "unavailable must be a list of strings"
            )
        record = observer_retention.record_capture(
            vendor.strip(),
            source.strip(),
            evidence_time,
            captured_at=captured_at,
            unavailable=unavailable,
        )
        self._evidence_expiry.record(record)
        # The downgrade check runs in the same operation: a capture that
        # arrives after its window closed marks itself (AC-47).
        self._evidence_expiry.markers()
        window = observer_retention.window_for(vendor.strip(), source.strip())
        return {
            "recorded": True,
            "capture": record.to_dict(),
            "window": window.to_dict() if window is not None else None,
            "windowStatus": "documented" if record.window_days is not None else "unknown",
            "marginTarget": observer_retention.MARGIN_TARGET,
            "meetsMarginTarget": record.meets_margin_target,
            "expired": [
                marker.to_dict() for marker in self._evidence_expiry.markers()
            ],
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

    def _attribution_floor(self, params: dict[str, Any]) -> float | None:
        """FR-M41-06: the attribution-coverage floor configured in the
        active governance pack (``attributionCoverageFloor``). Unconfigured
        (or a fail-closed pack) means no suppression — the metric reports
        its coverage with ``floor: null`` instead."""
        return self._governance_pack(params).attribution_coverage_floor

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
        control: str | None = None,
        external_contract_version: str | None = None,
    ) -> int:
        """FR-M10-08: the gate decision is committed to the ledger BEFORE the
        RPC returns; the encrypted input blob carries the full detail.

        FR-M42-12/SEC-32: when ``control`` names a registered control, the
        detail records that control's effective enforcement point, so the
        decision in the ledger (and every bundle exporting it) states what
        could have bypassed it — a client-side control is never recorded
        as enforced at a boundary where it is not.
        """
        ledger = self._ensure_ledger()
        if control is not None:
            detail = {
                **detail,
                "enforcementPoint": governance_enforcement.audit_record(
                    governance_enforcement.effective_declaration(control)
                ),
            }
        if external_contract_version is not None:
            # FR-M44-06 (N2-T24): a derived entry states which version of
            # the external contract produced it. "unpinned" is recorded
            # explicitly by the resolver — never omitted, never invented.
            detail = {
                **detail,
                "externalContractVersion": external_contract_version,
            }
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
            control="policy_refusal",
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

    # -- other tools' provenance records (M52, SEC-42/43; MV3-T06) -----------

    def _interop_repo(self, params: dict[str, Any]) -> str:
        repo = (params or {}).get("repoPath") or self._workspace_dir
        if not repo:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "interop methods need repoPath (or a workspaceDir handshake)",
            )
        return str(repo)

    def _interop_read(self, params: dict[str, Any]) -> list[interop.ForeignRecord]:
        """Every foreign record in the repository, notes and trailers.

        Never raises for a repository that simply has none: a customer with
        no other provenance tool installed is the common case, and making
        that look like a fault would teach people to ignore the surface.
        """
        repo = self._interop_repo(params)
        records = list(interop.read_foreign_notes(repo))
        commit = (params or {}).get("commit")
        if isinstance(commit, str) and commit.strip():
            records.extend(interop.read_foreign_trailers(repo, commit.strip()))
        return records

    @staticmethod
    def _interop_wire(record: interop.ForeignRecord) -> dict[str, Any]:
        return {**record.as_wire(), "payload": interop.parsed_payload(record)}

    def _handle_interop_records(
        self, params: bus_types.InteropRecordsParams
    ) -> bus_types.InteropRecordsResult:
        """FR-M52-01: what other tools have written here. Reads nothing into
        the ledger — a surface can show what is present before anybody
        commits to recording it."""
        return {
            "records": [
                self._interop_wire(record) for record in self._interop_read(params or {})
            ]
        }

    def _notarisation_details(self) -> list[dict[str, Any] | None]:
        """What each notarisation entry recorded, read back out of its blob.

        `None` for an entry whose blob cannot be read — the per-subject key
        was crypto-shredded. That is reported rather than skipped: an entry
        that exists and cannot be checked is a different fact from an entry
        that checks out, and silently dropping it would make `interop/verify`
        report all-clear over records it never looked at.
        """
        ledger = self._ensure_ledger()
        details: list[dict[str, Any] | None] = []
        for row in ledger.query_all(action_type="foreign_record_notarised"):
            ref = row.get("input_ref")
            if not isinstance(ref, str) or not ref:
                details.append(None)
                continue
            try:
                raw = ledger.read_blob(ref, str(row.get("blob_key_id") or "default"))
                detail = json.loads(raw.decode("utf-8"))
            except Exception:
                details.append(None)
                continue
            details.append(detail if isinstance(detail, dict) else None)
        return details

    def _notarised_digests(self) -> set[str]:
        """Digests already notarised, so the same unchanged record is not
        recorded twice. Proving the same thing a second time adds a row and
        no evidence."""
        return {
            detail["digest"]
            for detail in self._notarisation_details()
            if detail and isinstance(detail.get("digest"), str)
        }

    def _handle_interop_notarise(
        self, params: bus_types.InteropNotariseParams
    ) -> bus_types.InteropNotariseResult:
        """FR-M52-03, SEC-43, AC-59: the digest into the signed ledger.

        The digest and not the content. Meridian is not the custodian of
        another tool's data, and copying it would make it one — with the
        retention, erasure and disclosure obligations that follow. What the
        entry buys is that a third party can prove the record has not been
        altered since Meridian saw it; it buys nothing about whether the
        record was true, and the entry says so.
        """
        params = params or {}
        records = self._interop_read(params)
        already = self._notarised_digests()
        pack = self._role_pack(params)

        notarised = 0
        unpinned_tools: list[str] = []
        for record in records:
            if record.digest in already:
                continue
            entry = interop.notarisation_entry(record)
            # FR-M44-06/07, NFR-40 (N2-T24): the derived entry records the
            # pinned version of the contract that produced it. An unpinned
            # tool degrades visibly — named here, recorded as "unpinned" —
            # never silently treated as current.
            detail, contract_version = contract_versions.stamp_external_contract(
                entry["detail"], entry["vendor"]
            )
            if contract_version == contract_versions.UNPINNED:
                unpinned_tools.append(entry["vendor"])
            self._append_gate_entry(
                story_id=entry["storyId"],
                pack=pack,
                decision="proposed",
                action_type=entry["actionType"],
                # No control enforced anything here. Meridian observed a file
                # and recorded a digest; naming a control would imply a gate
                # that did not run.
                control=None,
                phase=entry["phase"],
                actor_kind="external",
                vendor=entry["vendor"],
                observation_confidence=entry["observationConfidence"],
                detail=detail,
                external_contract_version=contract_version,
            )
            already.add(record.digest)
            notarised += 1

        return {
            "notarised": notarised,
            "alreadyNotarised": len(records) - notarised,
            "unpinnedContracts": sorted(set(unpinned_tools)),
            "records": [self._interop_wire(record) for record in records],
        }

    def _handle_interop_conflicts(
        self, params: bus_types.InteropConflictsParams
    ) -> bus_types.InteropConflictsResult:
        """FR-M52-05, AC-60, NFR-53 (CP1-T02): where provenance records disagree.

        Compares, commit by commit, every claim about which agent produced the
        work: Meridian's own ledger entries, reached through the commit's
        Meridian-Ledger trailer; a bot author identity; and each other tool's
        note or trailer. A disagreement is reported with every claim beside it
        and no winner, including when one of the claims is Meridian's own.

        Reading writes nothing. With `record`, each disagreement not already in
        the ledger is appended as digests, so the disagreement itself becomes
        evidence a third party can check.
        """
        params = params or {}
        repo = self._interop_repo(params)
        ledger = self._ensure_ledger()
        max_commits = params.get("maxCommits", 200)
        if (
            not isinstance(max_commits, int)
            or isinstance(max_commits, bool)
            or not 1 <= max_commits <= 5000
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS, "maxCommits must be an integer from 1 to 5000"
            )

        def rows(first: int, last: int) -> list[dict[str, Any]]:
            return ledger.query(
                from_sequence=first, to_sequence=last, limit=min(1000, last - first + 1)
            )

        try:
            result = interop.reconcile(
                repo,
                ref=str(params.get("ref") or "HEAD"),
                max_commits=max_commits,
                ledger_rows=rows,
            )
        except interop.InteropError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error

        recorded = 0
        if params.get("record"):
            known: set[str] = set()
            after: int | None = None
            while True:
                page = ledger.query(
                    action_type="provenance_disagreement", after_sequence=after, limit=1000
                )
                for row in page:
                    try:
                        detail = json.loads(
                            ledger.read_blob(
                                str(row.get("input_ref")), str(row.get("blob_key_id") or "default")
                            ).decode("utf-8")
                        )
                    except Exception:  # noqa: BLE001 - an unreadable entry matches nothing
                        continue
                    if isinstance(detail, dict) and isinstance(detail.get("digest"), str):
                        known.add(detail["digest"])
                if len(page) < 1000:
                    break
                after = page[-1]["seq"]

            pack = self._role_pack(params)
            for disagreement in result.disagreements:
                if disagreement.digest in known:
                    continue
                self._append_gate_entry(
                    story_id="interop/disagreement",
                    pack=pack,
                    decision="proposed",
                    action_type="provenance_disagreement",
                    control=None,
                    phase="operate",
                    actor_kind="meta",
                    vendor="meridian",
                    # Meridian directly observed that these records disagree.
                    # It observed nothing about which of them is right.
                    observation_confidence="direct",
                    detail=disagreement.as_wire(),
                )
                known.add(disagreement.digest)
                recorded += 1

        return {**result.as_wire(), "recorded": recorded}  # type: ignore[return-value]

    def _handle_interop_export(
        self, params: bus_types.InteropExportParams
    ) -> bus_types.InteropExportResult:
        """FR-M52-04 (CP1-T03): Meridian's attributions in formats other tools consume.

        `attribution-json` returns the line-level export and writes nothing.
        `git-notes` reports what would be written under
        `refs/notes/meridian-attribution`, and writes it only when `write` is
        exactly true, because notes change the repository's refs. Both carry,
        by digest, any disagreement another record raises about a commit.

        `installedAt` is Meridian's installation time, from the caller:
        commits older than it are attributed at `inferred`, never `observed`
        (FR-M41-16). Without it no such downgrade is applied.
        """
        from . import interop_export

        params = params or {}
        repo = self._interop_repo(params)
        ledger = self._ensure_ledger()

        def rows(first: int, last: int) -> list[dict[str, Any]]:
            return ledger.query(
                from_sequence=first, to_sequence=last, limit=min(1000, last - first + 1)
            )

        ref = str(params.get("ref") or "HEAD")
        installed_at = params.get("installedAt")
        export_format = params.get("format")
        try:
            if export_format == "attribution-json":
                paths = params.get("paths")
                if paths is not None and (
                    not isinstance(paths, list) or not all(isinstance(p, str) for p in paths)
                ):
                    raise _RpcError(protocol.INVALID_PARAMS, "paths must be a list of strings")
                document = interop_export.attribution_export(
                    repo, ref=ref, paths=paths, ledger_rows=rows, installed_at=installed_at
                )
                return {"format": export_format, "document": document}  # type: ignore[return-value]
            if export_format == "git-notes":
                max_commits = params.get("maxCommits", 200)
                if (
                    not isinstance(max_commits, int)
                    or isinstance(max_commits, bool)
                    or not 1 <= max_commits <= 5000
                ):
                    raise _RpcError(
                        protocol.INVALID_PARAMS, "maxCommits must be an integer from 1 to 5000"
                    )
                write = params.get("write", False)
                if not isinstance(write, bool):
                    # Writing into somebody's refs needs a yes, not a string
                    # that happens to spell one.
                    raise _RpcError(protocol.INVALID_PARAMS, "write must be true or false")
                notes = interop_export.export_notes(
                    repo,
                    ref=ref,
                    max_commits=max_commits,
                    write=write,
                    ledger_rows=rows,
                    installed_at=installed_at,
                )
                return {"format": export_format, "notes": notes}  # type: ignore[return-value]
        except interop_export.ExportError as error:
            raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
        raise _RpcError(
            protocol.INVALID_PARAMS, "format must be attribution-json or git-notes"
        )

    def _handle_interop_verify(
        self, params: bus_types.InteropVerifyParams
    ) -> bus_types.InteropVerifyResult:
        """AC-59's second half: does each notarised record still say what it
        said? Both digests are reported on a mismatch, because the operator's
        question is "did this change, and to what?"."""
        params = params or {}
        present = {
            (record.source, record.commit): record
            for record in self._interop_read(params)
        }
        verdicts: list[dict[str, Any]] = []
        altered = 0
        missing = 0
        unreadable = 0
        for detail in self._notarisation_details():
            if detail is None:
                unreadable += 1
                verdicts.append(
                    {
                        "ok": False,
                        "tool": "unknown-tool",
                        "source": "",
                        "commit": "",
                        "digestAtNotarisation": "",
                        "digestNow": None,
                        "detail": (
                            "A notarisation entry exists whose detail could not be "
                            "read, so what it recorded cannot be compared. Its "
                            "per-subject blob key was destroyed."
                        ),
                    }
                )
                continue
            key = (detail.get("source"), detail.get("commit"))
            recorded = detail.get("digest")
            if not isinstance(recorded, str):
                continue
            verdict = interop.verify_notarisation(recorded, present.get(key))
            if not verdict.ok:
                if verdict.digest_now is None:
                    missing += 1
                else:
                    altered += 1
            verdicts.append(
                {
                    "ok": verdict.ok,
                    "tool": detail.get("tool", "unknown-tool"),
                    "source": detail.get("source", ""),
                    "commit": detail.get("commit", ""),
                    "digestAtNotarisation": verdict.digest_at_notarisation,
                    "digestNow": verdict.digest_now,
                    "detail": verdict.detail,
                }
            )
        return {
            "verdicts": verdicts,
            "altered": altered,
            "missing": missing,
            "unreadable": unreadable,
        }

    # -- enforcement points (FR-M42-11/12, SEC-32; MV1-T01) ------------------

    def _handle_enforcement_points(
        self, params: bus_types.EnforcementPointsParams
    ) -> bus_types.EnforcementPointsResult:
        """Every control's effective enforcement point, or one control's.

        Effective, not aspirational: `effective_declaration` downgrades an
        scm-point control to `sidecar` when no SCM binding is configured
        (D37), and v1 never configures one — so in v1 nothing reported here
        claims SCM enforcement. That downgrade is the whole value of the
        method. A surface rendering the aspirational point would be exactly
        the overclaim SEC-32 forbids.

        An unknown control id raises rather than returning an empty set: a
        control nobody declared is a programming error, not an absence (P26).
        """
        params = params or {}
        scm_configured = bool(params.get("scmBindingConfigured", False))
        control = params.get("control")

        if control is None:
            return governance_enforcement.enforcement_section(
                scm_binding_configured=scm_configured
            )

        if control not in governance_enforcement.CONTROLS:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"unknown control {control!r}: it has no enforcement-point "
                f"declaration. Known controls: "
                f"{', '.join(sorted(governance_enforcement.CONTROLS))}.",
            )
        declaration = governance_enforcement.effective_declaration(
            control, scm_binding_configured=scm_configured
        )
        return {
            "vocabularyVersion": governance_enforcement.VOCABULARY_VERSION,
            "vocabulary": list(governance_enforcement.VOCABULARY),
            "scmBindingConfigured": scm_configured,
            "controls": {
                control: governance_enforcement.audit_record(declaration)
            },
        }

    # -- run initiation (M40, SEC-30, AC-38/39/40; MV2) ----------------------

    @staticmethod
    def _initiation_error(error: initiation.InitiationError) -> _RpcError:
        """An initiation refusal, rendered so the surface can show it.

        The code travels in `data` rather than being parsed out of the
        message: a dialog has to distinguish "you have not confirmed" from
        "your role may not do this", and matching on prose is how that
        distinction rots.
        """
        return _RpcError(
            protocol.INVALID_PARAMS,
            str(error),
            data={"code": error.code, **error.detail},
        )

    def _request_from_preflight(
        self, wire: Any, *, where: str
    ) -> initiation.RunRequest:
        """Rebuild the request from the preflight the human was shown.

        The branch and worktree on the wire are **not** trusted. They are
        derived from the run id, and re-deriving them here is the check
        that the human confirmed the target that will actually be created:
        a preflight showing one branch and a start creating another is the
        divergence the single contract exists to prevent. A mismatch is a
        refusal, not a correction — silently creating the right thing would
        mean the human confirmed something they never saw.
        """
        if not isinstance(wire, dict):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"{where} needs the preflight object returned by run/preflight",
            )
        try:
            request = initiation.build_run_request(
                origin=str(wire.get("origin") or ""),
                intent=str(wire.get("intent") or ""),
                repo=str(wire.get("repo") or ""),
                base_branch=str(wire.get("baseBranch") or "main"),
                adapters={
                    str(k): str(v)
                    for k, v in (wire.get("adapters") or {}).items()
                },
                mode=str(wire.get("mode") or "dry_run"),
                gates=tuple(str(g) for g in (wire.get("gates") or ())),
                cost_ceiling_usd=wire.get("costCeilingUsd"),
                estimate_usd=wire.get("estimateUsd"),
                run_id=str(wire.get("runId") or "") or None,
            )
        except initiation.InitiationError as error:
            raise self._initiation_error(error) from error

        for field, expected in (
            ("branch", request.branch),
            ("worktree", request.worktree),
        ):
            supplied = wire.get(field)
            if supplied is not None and str(supplied) != expected:
                raise _RpcError(
                    protocol.INVALID_PARAMS,
                    f"the preflight was confirmed for {field} {supplied!r} but "
                    f"run {request.run_id} would create {expected!r}. Both are "
                    "derived from the run id, so they cannot legitimately "
                    "differ; refusing rather than creating something the "
                    "human did not see (FR-M40-01).",
                    data={"code": "PREFLIGHT_TAMPERED", "field": field},
                )
        return request

    @staticmethod
    def _adapter_usable(adapter_id: str) -> bool:
        """Whether the worktree machinery will accept this adapter id.

        Asked at preflight rather than discovered at creation: an id the
        worktree manager rejects makes the run unstartable, and reporting
        `confirmable` for it means the human confirms and *then* learns
        about a constraint nobody showed them. The rule is the manager's
        own, called rather than copied — a second copy of the pattern is a
        second thing to keep in step.
        """
        try:
            worktree_mod.agent_identity(adapter_id)
        except (AttributionError, ValueError, worktree_mod.WorktreeError):
            return False
        return True

    def _handle_run_preflight(
        self, params: bus_types.RunPreflightParams
    ) -> bus_types.RunPreflightResult:
        """FR-M40-03: the six answers, and any that are missing.

        Missing answers come back as `confirmable: false` with `missing`
        naming them, rather than as an error. The surface has to *show*
        what is incomplete; an exception leaves a dialog that will not open
        and no way to see why.
        """
        params = params or {}
        try:
            request = initiation.build_run_request(
                origin=str(params.get("origin") or ""),
                intent=str(params.get("intent") or ""),
                repo=str(params.get("repo") or ""),
                base_branch=str(params.get("baseBranch") or "main"),
                adapters={
                    str(k): str(v)
                    for k, v in (params.get("adapters") or {}).items()
                },
                mode=str(params.get("mode") or "dry_run"),
                gates=tuple(str(g) for g in (params.get("gates") or ())),
                cost_ceiling_usd=params.get("costCeilingUsd"),
                estimate_usd=params.get("estimateUsd"),
                run_id=params.get("runId") or None,
            )
        except initiation.InitiationError as error:
            raise self._initiation_error(error) from error
        report = initiation.preflight(
            request, adapter_usable=self._adapter_usable
        )
        return {"preflight": report.as_wire()}

    def _handle_run_start(
        self, params: bus_types.RunStartParams
    ) -> bus_types.RunStartResult:
        """FR-M40-01/02/05, SEC-30, AC-38: the single entry point.

        Everything that could refuse does so before anything is created.
        The ordering is not an implementation detail — it is what makes
        FR-M40-09's guarantee (a cancelled run leaves no worktree and no
        branch) achievable at all. A worktree created optimistically and
        cleaned up on cancel is a weaker promise: it depends on the
        cleanup running.
        """
        params = params or {}
        request = self._request_from_preflight(
            params.get("preflight"), where="run/start"
        )
        identity = self._human_identity()
        # The role pack, not the governance pack: the policy that decides
        # whether this launch may happen is the role policy, so it is the
        # one whose version belongs on the entry. Recording a governance
        # policy version next to a role decision would name a document that
        # had no part in it.
        pack = self._role_pack(params)
        authority = governance_roles.launch_modes(pack, params.get("role"))
        try:
            request = initiation.authorise(
                request,
                identity_email=identity.email or identity.id,
                identity_assurance=identity.assurance,
                permitted_modes=authority.modes,
                requires_verified=bool(params.get("requiresVerifiedIdentity")),
            )
        except initiation.InitiationError as error:
            # FR-M40-05: the refusal is recorded. A refused launch that
            # leaves no trace is indistinguishable from one nobody tried,
            # and "who was turned away, and why" is exactly the question
            # an audit asks after an incident.
            self._append_gate_entry(
                story_id=request.run_id,
                pack=pack,
                decision="rejected",
                action_type="run_start_refused",
                control="permission_policy",
                phase="plan",
                human_actor=identity.display(),
                human_role=authority.role,
                run_id=request.run_id,
                origin=request.origin,
                detail={
                    "code": error.code,
                    "reason": str(error),
                    "mode": request.mode,
                    "permittedModes": list(authority.modes),
                    "roleReason": authority.reason,
                    "assurance": identity.assurance,
                },
            )
            raise self._initiation_error(error) from error

        manager = self._worktree_manager(params)
        adapter_id = self._run_adapter_id(request, params)

        def record_entry(entry: dict[str, Any]) -> int:
            return self._append_gate_entry(
                story_id=entry["storyId"],
                pack=pack,
                decision=entry["decision"],
                action_type=entry["actionType"],
                control="permission_policy",
                phase="plan",
                human_actor=identity.display(),
                human_role=authority.role,
                run_id=entry["runId"],
                origin=entry["origin"],
                detail={
                    **entry["detail"],
                    "assurance": identity.assurance,
                    "adapterId": adapter_id,
                    "branch": request.branch,
                    "worktree": request.worktree,
                },
            )

        def create_worktree(branch: str, base_branch: str, path: str) -> str:
            try:
                info = manager.create(
                    request.run_id,
                    adapter_id,
                    base_branch=base_branch,
                    branch=branch,
                )
            except worktree_mod.WorktreeError as error:
                raise self._worktree_error(error) from error
            except AttributionError as error:
                raise _RpcError(protocol.INVALID_PARAMS, str(error)) from error
            return str(info.path)

        try:
            started = initiation.start_run(
                request,
                confirmed=bool(params.get("confirmed")),
                record_entry=record_entry,
                create_worktree=create_worktree,
                adapter_usable=self._adapter_usable,
            )
        except initiation.InitiationError as error:
            raise self._initiation_error(error) from error

        return {
            "runId": started["runId"],
            "origin": started["origin"],
            "branch": started["branch"],
            "worktree": started["worktree"],
            "mode": started["mode"],
            "authorisedBy": started["authorisedBy"],
            "assurance": started["assurance"],
            "sequence": started["entry"],
        }

    @staticmethod
    def _run_adapter_id(
        request: initiation.RunRequest, params: dict[str, Any]
    ) -> str:
        """Which agent identity the run's worktree commits are attributed to.

        A run has a role-to-adapter map; a worktree has one git identity
        (FR-M18-07). An explicit `adapterId` wins. Otherwise the Developer
        role, because that is the role that writes code, and failing that
        the first role by name — deterministic, so the same request always
        produces the same attribution rather than one that depends on dict
        ordering.
        """
        explicit = params.get("adapterId")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        adapters = request.adapters
        ordered = sorted(adapters, key=lambda name: (name != "Developer", name))
        if ordered:
            return adapters[ordered[0]]
        raise _RpcError(
            protocol.INVALID_PARAMS,
            "the run names no adapter, so there is no agent identity to "
            "attribute its commits to (FR-M18-07). Preflight would have "
            "reported this as a missing answer.",
            data={"code": "PREFLIGHT_INCOMPLETE", "missing": ["adapters"]},
        )

    def _handle_run_cancel(
        self, params: bus_types.RunCancelParams
    ) -> bus_types.RunCancelResult:
        """FR-M40-09, AC-39: cancel at preflight.

        One record and nothing else. There is no cleanup here because
        run/start creates nothing until after confirmation and
        authorisation — which is what makes this a guarantee rather than a
        best effort.
        """
        params = params or {}
        request = self._request_from_preflight(
            params.get("preflight"), where="run/cancel"
        )
        pack = self._role_pack(params)
        try:
            identity = self._human_identity()
            actor: str | None = identity.display()
        except _RpcError:
            # A cancellation is not an action that needs authority: nothing
            # was created and nothing will be. Refusing to record it because
            # the identity provider is unavailable would lose the trace for
            # the one case where losing it is free.
            actor = None
        record = initiation.cancellation_record(
            request, reason=str(params.get("reason") or "")
        )
        sequence = self._append_gate_entry(
            story_id=record["storyId"],
            pack=pack,
            decision=record["decision"],
            action_type=record["actionType"],
            control=None,
            phase="plan",
            human_actor=actor,
            run_id=record["runId"],
            origin=record["origin"],
            detail=record["detail"],
        )
        return {
            "runId": request.run_id,
            "cancelled": True,
            "sequence": sequence,
            "note": record["detail"]["note"],
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
        still accepted and map onto asserted assurance (D38).
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
            assurance="asserted",
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
        # FR-M42-05 (N2-T07): where policy requires a verified approver, an
        # asserted (git) identity is refused at approval time — with the
        # level named, never silently downgraded or upgraded. Where the
        # requirement is unset, asserted is accepted and recorded as
        # asserted.
        if pack.requires_verified_identity(subject.strip()) and who.assurance != "verified":
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"FR-M42-05: this gate requires a verified approver, but the "
                f"acting identity resolves at assurance '{who.assurance}' — a "
                "git name/email never satisfies a policy requiring a verified "
                "approver",
                data={
                    "code": "IDENTITY_ASSURANCE_INSUFFICIENT",
                    "subject": subject.strip(),
                    "assurance": who.assurance,
                    "required": "verified",
                },
            )
        # FR-M42-06/SEC-31/AC-46 (N2-T08): a revoked identity cannot record
        # new approvals. The refusal names the recorded revokedAt and is
        # effective from the instant the revocation row committed — in
        # process there is no propagation delay (NFR-36's five minutes is
        # the outer envelope for other replicas only).
        revoked_at = governance_revocations.revoked_at(ledger, who.email)
        if revoked_at is not None:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                f"FR-M42-06/AC-46: identity {who.email} was revoked at "
                f"{revoked_at} — a revoked identity cannot record new "
                "approvals",
                data={
                    "code": "IDENTITY_REVOKED",
                    "email": who.email,
                    "revokedAt": revoked_at,
                },
            )
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
        delegated = False
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
            delegated = True
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
        # FR-M42-07 (D40): every approval carries its approvedBy class —
        # human_individual as themselves, or human_delegated when an
        # active delegation grant (FR-M20-05) carried the permission.
        # FR-M42-04/06 (D38): the identity assurance level (asserted |
        # verified) rides the same stamp, so the level is bound to the
        # decision and re-validated whenever the gate executes.
        approved_by = governance_approval_class.stamp(
            "human_delegated" if delegated else "human_individual",
            who.assurance,
        )
        sequence = self._append_gate_entry(
            story_id=(params.get("storyId") or f"gate:{subject.strip()}"),
            pack=pack,
            control="merge_gate",
            action_type="approval",
            decision="approved",
            human_actor=who.display(),
            human_role=role if isinstance(role, str) and role.strip() else None,
            detail={
                "method": "gate.approve",
                "subject": subject.strip(),
                "commit": commit.strip(),
                "role": role if isinstance(role, str) else None,
                "approvedBy": approved_by,
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
            "approvedBy": approved_by,
        }

    # -- identity revocation (FR-M42-06/SEC-31/AC-46; N2 Workstream B T08) ---

    def _handle_identity_revoke(
        self, params: bus_types.IdentityRevokeParams
    ) -> bus_types.IdentityRevokeResult:
        """Record an identity revocation (FR-M42-06, AC-46).

        The row commits BEFORE the response returns (FR-M10-08) and every
        governance check reads the ledger anew, so the revocation binds the
        very next gate evaluation in this process — new approvals by the
        identity are refused and in-flight merge authorisations stop, from
        the instant of the revocation entry. NFR-36's five minutes is the
        worst-case outer envelope for OTHER replicas (an SCM-side consumer
        that syncs the ledger), not the in-process latency.
        """
        params = params or {}
        email = params.get("email")
        if not isinstance(email, str) or not email.strip() or "@" not in email:
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "email must be the non-empty address of the identity to revoke",
            )
        revoked_at = params.get("revokedAt")
        if revoked_at is not None and (
            not isinstance(revoked_at, str) or not revoked_at.strip()
        ):
            raise _RpcError(
                protocol.INVALID_PARAMS,
                "revokedAt must be an ISO-8601 UTC timestamp when given",
            )
        reason = params.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise _RpcError(protocol.INVALID_PARAMS, "reason must be a string")
        # FR-M20-01: the revoking operator is attributed, never anonymous.
        who = self._human_identity()
        ledger = self._ensure_ledger()
        effective = revoked_at.strip() if isinstance(revoked_at, str) else ledger_core.utc_now()
        sequence = governance_revocations.record_revocation(
            ledger,
            email=email,
            revoked_by=who.display(),
            reason=reason.strip() if isinstance(reason, str) else None,
            revoked_at=effective,
            policy_version=self._governance_pack(params).policy_version,
        )
        return {
            "recorded": True,
            "sequence": sequence,
            "email": email.strip().lower(),
            "revokedAt": effective,
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
            # FR-M42-07: the bound approval's class rides the status
            # payload so no surface mistakes a stamped class for a human.
            result["approvedBy"] = {
                "class": verdict.approval.approved_by_class,
                "classifierVersion": verdict.approval.approved_by_class_version,
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
            control="halt_all",
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
                control="policy_refusal",
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
            for row in ledger.query_all(action_type="gate", story_id=story_id):
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
        for row in reversed(ledger.query_all(action_type="pr_ingest")):
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
        rows = ledger.query_all(action_type="rejection")
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
            # FR-M41-01/02: per-field provenance — source, capture method,
            # contract version, capture timestamp and the observed state.
            # Every blame field is read directly from git porcelain output;
            # nothing here is inferred, so signing has nothing to promote.
            "provenance": attribution_wire.blame_provenance(
                str(repo), params.get("ref") or "HEAD"
            ),
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
            # FR-M41-01/02: per-field provenance. path/line are the caller's
            # own observed arguments; language/symbol come from the symbols
            # engine — observed when resolved, honestly unknown when the
            # language is unregistered or no enclosing definition exists
            # (G3 degradation never overclaims).
            "provenance": attribution_wire.symbol_provenance(
                rel, line, result.language, result.symbol
            ),
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
                excluded_paths=params.get("excludedPaths"),
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
                    "unknownReason": file.unknown_reason,
                    "unknownReasonVersion": file.unknown_reason_version,
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
        taxonomy = rejection_taxonomy.load_taxonomy(
            rejection_taxonomy.default_taxonomy_paths(self._workspace_dir)
        )

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
        existing = ledger.query_all(action_type="rejection")
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

    def _handle_evidence_gate(
        self, params: bus_types.EvidenceGateParams
    ) -> bus_types.EvidenceGateResult:
        """F2's gate over this workspace's own ledger.

        Approval hygiene (FR-M20-06) is bound here rather than inside the
        metric, because it needs the workspace's role pack: `assess_hygiene`
        has existed since F1 and was never reachable over the bus, which is
        why the F2 measure it was written for could not be taken.
        """
        params = params or {}
        ledger = self._ensure_ledger()

        hygiene = None
        try:
            pack = self._role_pack(params)
        except Exception:  # noqa: BLE001 — an unreadable pack is not a crash
            pack = None
        # A fail-closed pack assesses nothing and returns no warnings, so passing
        # it on would report "assessed, no signals": a clean bill from no check.
        if pack is not None and not pack.fail_closed:

            def hygiene(subject: str) -> list[str]:  # type: ignore[misc]
                return governance_roles.assess_hygiene(ledger, pack, subject=subject)

        return evidence_gate.compute_evidence_gate(
            ledger,
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            baseline_change_failure_rate=params.get("baselineChangeFailureRate"),
            hygiene=hygiene,
        )  # type: ignore[return-value]

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
                "attributionFloor": self._attribution_floor(params),
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
            attribution_floor=self._attribution_floor(params),
            # FR-M44-13/AC-47: a closed vendor retention window is a named
            # coverage gap on the envelope — never an absence of activity.
            data_gaps=self._evidence_expiry.gaps(),
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
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

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
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "attributionFloor": self._attribution_floor(params),
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
        result = metrics_mod.compute_trust_score(
            ledger,
            actor_id=actor_id,
            repo_id=params.get("repoId"),
            task_class=params.get("taskClass"),
            task_class_by_story=task_class_by_story,
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            attribution_floor=self._attribution_floor(params),
            classify=classify_fn,
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
                "attributionFloor": self._attribution_floor(params),
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
            attribution_floor=self._attribution_floor(params),
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
        # feed uses), yield = 1 - rejected/proposed per bucket. Full
        # history over the after_sequence cursor (FR-M41-07, D36) — the
        # yield half of the detector was under the same 1,000-row cap as
        # the other analytics (G-01).
        rows, rows_available = metrics_mod.scan_scope(
            ledger,
            action_type="diff",
            from_sequence=from_sequence,
            to_sequence=to_sequence,
        )
        scoped_rows = rows
        if repo_id is not None:
            rows = [row for row in rows if row.get("repo_id") == repo_id]
        rejection_rows, rejection_available = metrics_mod.scan_scope(
            ledger, action_type="rejection"
        )
        rejection_scanned = rejection_rows
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
            # FR-M41-08 (NFR-34): the yield half's coverage disclosure.
            metrics_mod.ATTACH_KEY: metrics_mod.envelope_for(
                None,
                scoped_rows,
                rows_available,
                aux_scans=((rejection_scanned, rejection_available),),
            ).to_dict(),
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
        story_commits = params.get("storyCommits") or {}
        ratio_threshold = params.get("newFileRatioThreshold")
        max_age_days = params.get("maxMedianAgeDays")

        cache_key = json.dumps(
            {
                "scope": {
                    "repoId": params.get("repoId"),
                    "fromSequence": params.get("fromSequence"),
                    "toSequence": params.get("toSequence"),
                },
                "resourceAttributes": resource_attributes,
                "exportedAt": exported_at,
                "storyCommits": story_commits,
                "thresholds": [ratio_threshold, max_age_days],
                "attributionFloor": self._attribution_floor(params),
                "tip": ledger.last_sequence,  # append-invalidation backstop
            },
            sort_keys=True,
        )
        cached = self._trust_cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        classify_fn = self._trust_classifier(
            params, story_commits, ratio_threshold, max_age_days
        )
        computed = metrics_mod.compute_dora_metrics(
            ledger,
            repo_id=params.get("repoId"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
            attribution_floor=self._attribution_floor(params),
            classify=classify_fn,
        )
        export = metrics_mod.export_otlp(
            computed,
            exported_at=exported_at if isinstance(exported_at, str) else None,
            resource_attributes=resource_attributes,
        )
        result = {
            "status": computed["status"],
            "metrics": computed["metrics"],
            "split": computed["split"],
            "export": export,
            # FR-M41-08: the export's coverage disclosure rides the result.
            metrics_mod.ATTACH_KEY: computed[metrics_mod.ATTACH_KEY],
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
        rows, rows_available = self._spend_rows(ledger, params)
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
            # FR-M41-08: the coverage envelope rides the same result
            # (NFR-34). The population is every row in the declared
            # scope; the spend figures consider the token-bearing ones.
            metrics_mod.ATTACH_KEY: metrics_mod.envelope_for(
                aggregated["totals"]["costUsd"], rows, rows_available
            ).to_dict(),
            "cacheHit": False,
        }
        self._trust_cache.put(cache_key, result)
        return result  # type: ignore[return-value]

    def _spend_rows(
        self, ledger: Any, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        """Rows in scope + the scope's row count, full-history cursor
        paginated (FR-M41-07, D36) — the newest-1,000 cap is gone; the
        coverage envelope on every spend result reports what the figure
        saw (FR-M41-08, NFR-34)."""
        rows, rows_available = metrics_mod.scan_scope(
            ledger,
            actor_id=params.get("actorId"),
            story_id=params.get("storyId"),
            vendor=params.get("vendor"),
            from_sequence=params.get("fromSequence"),
            to_sequence=params.get("toSequence"),
        )
        repo_id = params.get("repoId")
        if repo_id is not None:
            rows = [row for row in rows if row.get("repo_id") == repo_id]
        return rows, rows_available

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

        scope_rows, scope_available = self._spend_rows(
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
            story_rows, _story_available = self._spend_rows(
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
            # FR-M41-08 (NFR-34): coverage envelope over the actor scope
            # the spend figure was checked against.
            metrics_mod.ATTACH_KEY: metrics_mod.envelope_for(
                spent_usd, scope_rows, scope_available
            ).to_dict(),
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

        scoped_rows, rows_available = self._spend_rows(ledger, params)
        rows = scoped_rows
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
        # FR-M41-08 (NFR-34): the envelope is built in this same operation
        # and handed to the projection (FR-M41-09): a truncated scope
        # disables the forecast at the module level rather than letting
        # the webview detect a row cap of its own. The team mapping
        # filter is a declared scope restriction, never truncation.
        envelope = metrics_mod.envelope_for(
            None, scoped_rows, rows_available
        )
        forecast = metrics_mod.forecast_monthly_spend(
            months,
            current_month,
            window_months=window or 3,
            coverage_envelope=envelope,
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
        # over budget; not projecting changes nothing). A truncated scope
        # outranks everything but an actual breach: the projection was
        # disabled (FR-M41-09), the result must say so, not read ok.
        if budget["status"] in ("actual_breach", "forecast_breach"):
            status = budget["status"]
        elif forecast["status"] == "truncated":
            status = "truncated"
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
            metrics_mod.ATTACH_KEY: metrics_mod.envelope_for(
                forecast["projectedUsd"], scoped_rows, rows_available
            ).to_dict(),
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
        filters = {
            "story_id": (params or {}).get("storyId"),
            "actor_id": (params or {}).get("actorId"),
            "vendor": (params or {}).get("vendor"),
            "action_type": (params or {}).get("actionType"),
            "from_sequence": (params or {}).get("fromSequence"),
            "to_sequence": (params or {}).get("toSequence"),
            "from_timestamp": (params or {}).get("fromTimestamp"),
            "to_timestamp": (params or {}).get("toTimestamp"),
        }
        limit = (params or {}).get("limit") or 100
        rows = ledger.query(
            after_sequence=(params or {}).get("afterSequence"),
            limit=limit,
            **filters,
        )
        # FR-M41-07: when the page is full, the clamp is reported —
        # never silent. A short page is by definition complete.
        truncated = False
        if len(rows) >= min(max(limit, 1), 1000):
            truncated = ledger.count(**filters) > len(rows)
        return {
            "entries": [ledger_wire.row_to_wire(row) for row in rows],
            "truncated": truncated,
            "nextAfterSequence": rows[-1]["seq"] if rows else None,
        }

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
        begins = ledger.query_all(action_type="session_begin")
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
        # FR-M42-07/08 (D40): every permission decision carries its
        # approvedBy class. A caller/vendor class hint maps onto the
        # closed set (unknown on failure, P26); otherwise the outcome
        # decides: a policy-gate refusal is a ruleset_actor decision (the
        # human never saw the prompt), a human selection/cancellation is
        # human_individual.
        declared = params.get("approvedByClass")
        if declared is not None:
            decision_class = governance_approval_class.classify(declared=str(declared))
        elif outcome == "denied_by_policy":
            decision_class = "ruleset_actor"
        else:
            decision_class = "human_individual"
        # FR-M42-04/06 (D38, N2-T08): a human decision binds the resolved
        # identity's assurance level into the stamp, so the level rides
        # the decision entry. When no identity can be resolved the level
        # is recorded honestly as "unrecorded" — never fabricated, never
        # a silent "verified". Non-human classes (the policy gate decided,
        # FR-M42-08) carry no human assurance.
        identity_assurance = None
        if governance_approval_class.is_human_class(decision_class):
            try:
                identity_assurance = self._human_identity().assurance
            except Exception:
                identity_assurance = "unrecorded"
        detail["approvedBy"] = governance_approval_class.stamp(
            decision_class, identity_assurance
        )
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
        begins = ledger.query_all(action_type="session_begin")
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
        rows = ledger.query_all(
            story_id=f"acp:{session_id}",
            action_type="partial_acceptance",
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
        rows = self._ensure_ledger().query_all(
            story_id=f"acp:{session_id}", action_type="partial_acceptance"
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
        ends = ledger.query_all(action_type="session_end")
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
        # FR-M44-01/02 (N2-T21/T22): the MCP client identity is whatever the
        # caller declared at this boundary. The gateway has no executable
        # evidence about the client — no digest, no resolved version — so
        # the recorded identity is bound to the declared name at assurance
        # "asserted" (D38 vocabulary) with the reason stated, and surfaced
        # in the result so host-side labelling never upgrades it to
        # verified.
        declared = params.get("client")
        client = (
            declared.strip()
            if isinstance(declared, str) and declared.strip()
            else "mcp-client"
        )
        identity = {
            "client": client,
            "assurance": "asserted",
            "reason": (
                "caller-declared MCP client name; no executable digest or"
                " resolved version is available at this boundary"
            ),
        }
        entry: dict[str, Any] = {
            "ts_utc": ledger_core.utc_now(),
            "story_id": f"mcp:{tool}",
            "phase": "intake",
            "loop_id": "mcp-server",
            "loop_iteration": 1,
            "actor_id": client,
            "actor_version": "0",
            "actor_kind": "external",
            "policy_version": "mcp-server/v1",
            "action_type": "tool_call",
            "vendor": "mcp",
            "observation_confidence": "direct",
            "input": json.dumps(
                {"tool": tool, "arguments": arguments, "identity": identity},
                ensure_ascii=False,
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
        return {"tool": tool, "result": outcome, "identity": identity}


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
