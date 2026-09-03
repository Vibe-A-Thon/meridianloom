"""JSON-RPC method dispatch for the Meridian Core sidecar.

The server is a plain object so tests can drive it without real stdio:
``handle_message`` maps one decoded frame to zero or one response frame.
``serve`` is the production loop over stdin/stdout.

FR-M32-09: handler signatures are typed with the generated bus types
(shared/py/bus_types.py, from shared/schema/). Lifecycle methods are real;
ledger and loop methods are registered placeholders that answer with the
contracted NOT_IMPLEMENTED error until Workstreams D/E fill them in.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import logging
import os
import platform
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import bus_types

from . import doctor, protocol, tiers
from .ledger import core as ledger_core
from .ledger import keys as ledger_keys
from .ledger import wire as ledger_wire
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
        self._handlers: dict[str, Handler] = {
            "handshake": SidecarServer._handle_handshake,
            "ping": SidecarServer._handle_ping,
            "shutdown": SidecarServer._handle_shutdown,
            "health": SidecarServer._handle_health,
            "doctor/run": SidecarServer._handle_doctor_run,
            "ledger.append": SidecarServer._handle_ledger_append,
            "ledger.query": SidecarServer._handle_ledger_query,
            "ledger.getEntry": SidecarServer._handle_ledger_get_entry,
            "ledger.verify": SidecarServer._handle_ledger_verify,
            "ledger.proof": SidecarServer._handle_ledger_proof,
            "ledger.exportBundle": SidecarServer._handle_ledger_export_bundle,
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
        # FR-M10-01: the workspace path locates the ledger.
        workspace_dir = (params or {}).get("workspaceDir")
        if isinstance(workspace_dir, str) and workspace_dir:
            self._workspace_dir = workspace_dir
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
        # not-yet-built ones (observers) take the registry's not-installed
        # path with remediation instead of failing.
        context = doctor.DoctorContext(started_at=self._started_at)
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
        import base64 as b64

        ledger = self._ensure_ledger()
        from_seq = (params or {}).get("fromSequence") or 1
        to_seq = min(
            (params or {}).get("toSequence") or ledger.last_sequence,
            ledger.last_sequence,
        )
        rows = []
        if to_seq >= from_seq and to_seq > 0:
            rows = ledger.query(
                story_id=(params or {}).get("storyId"),
                actor_id=(params or {}).get("agentId"),
                from_sequence=from_seq,
                to_sequence=to_seq,
                limit=1000,
            )
        # A signed head must cover the range end; emit one at the tip if
        # the cadence has not produced one yet (FR-M10-04).
        head_row = ledger.latest_tree_head()
        head_wire = None
        if ledger.last_sequence and (head_row is None or head_row["seq"] < to_seq):
            head_wire = ledger.emit_tree_head_now()  # already wire shape
        elif head_row is not None:
            head_wire = ledger_wire.tree_head_to_wire(head_row)
        return {
            "formatVersion": 1,
            "generatedAt": ledger_core.utc_now(),
            "signer": {
                "algorithm": "Ed25519",
                "publicKey": b64.b64encode(ledger.signing_public_key).decode(),
            },
            **({"treeHead": head_wire} if head_wire is not None else {}),
            "range": {"fromSequence": from_seq, "toSequence": to_seq},
            "filter": {
                key: value
                for key, value in (
                    ("storyId", (params or {}).get("storyId")),
                    ("agentId", (params or {}).get("agentId")),
                )
                if value is not None
            },
            "entries": [ledger_wire.row_to_bundle_entry(row) for row in rows],
        }


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
