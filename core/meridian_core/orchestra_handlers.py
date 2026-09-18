"""TASK-011: RPC handlers for the Orchestra/F4+ surfaces (audit GAP-001).

One module, one handler per contracted method, merged into the sidecar's
dispatch table at boot. Handlers are plain ``(server, params)`` functions —
the same call shape as the built-in table — and delegate to the real
modules built in F3/C3–C6. Workspace-scoped state (router, runner, fabric,
registries) is constructed lazily against the handshake workspace, the
same discipline as ``_ensure_ledger``.

Ledger-first: every handler whose module records evidence does so through
the module itself (the modules were built that way); handlers that own no
ledger write say so in their docstring.

Tier posture comes from shared/schema/tiers.json (registrar: simulation/*
and golden/* are flight-recorder — zero tiers, zero credentials per
FR-M32; delivery surfaces are orchestra; governance surfaces governor).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from langgraph.checkpoint.sqlite import SqliteSaver

from meridian_core.adapters import AdapterRegistry
from meridian_core.comprehension import ComprehensionEngine
from meridian_core.decisions import (
    AblationRunner,
    CalibrationTracker,
    DecisionRecord,
    GateInputs,
    Rationale,
    evaluate_gate,
)
from meridian_core.differentiation import (
    Annotation,
    AnnotationStore,
    record_detected_issue,
)
from meridian_core.engine.capabilities import CapabilityRegistry
from meridian_core.engine.catalogue import load_catalogue
from meridian_core.engine.dispatch import Dispatcher
from meridian_core.engine.structural import StructuralParseCapability
from meridian_core.memory.fabric import MemoryEntry, MemoryFabric, Provenance
from meridian_core.portability import (
    diff_against_workspace,
    export_package,
    import_package,
)
from meridian_core.router import Router
from meridian_core.runtime import (
    FieldSpec,
    LangGraphLoopRunner,
    LoopState,
    RunHandle,
    UNBOUNDED,
    append_unique,
    canonical_loops,
)
from meridian_core.simulation import SimulationCore, SimulationClock
from meridian_core.tenancy import Story, StoryQueue, Tenant, TenantRegistry
from meridian_core.tools.surface import SandboxConfig, ToolDeniedError, ToolSurface
from meridian_core.trainer import LearnedDelta, Trainer, harvest_signals

class OrchestraError(ValueError):
    """A handler input/scope violation; the server maps this to the
    protocol INVALID_PARAMS error at the merge boundary."""


PROGRESS_SCHEMA = {
    # reducer declared: several body nodes write progress in one pass —
    # FR-M4-04 merges them, it never last-write-wins.
    "progress": FieldSpec("progress", list, reducer=append_unique, default=[]),
    "approved": FieldSpec("approved", bool, default=False),
}

KIND_TO_LOOP = {
    "L1-micro": "L1",
    "L2-task": "L2",
    "L3-phase": "L3",
    "L4-delivery": "L4",
    "L5-learning": "L5",
    "L6-organisation": "L6",
}
_KIND_OF_LOOP = {v: k for k, v in KIND_TO_LOOP.items()}


def _stand_in_nodes(definition) -> dict[str, Callable]:
    """Deterministic node callables for a canonical loop: each node marks
    progress. Real agent work binds at launch (roster stand-ins are not
    models — see the adapter manifests); the runtime machinery exercised
    here is the real M4 path."""
    def make(node_id):
        def node(ctx):
            progress = list(ctx.state.get("progress") or [])
            if node_id not in progress:
                return {"progress": (node_id, [node_id])}
            return {}
        return node
    return {n: make(n) for n in definition.body_graph}


def _all_visited(definition) -> Callable[[LoopState], bool]:
    def check(state: LoopState) -> bool:
        progress = set(state.get("progress") or [])
        return all(n in progress for n in definition.body_graph)
    return check


class OrchestraState:
    """Lazily-built, workspace-scoped module instances.

    TASK-320: the run registry, story queue and tenant registry persist
    under ``.meridian/orchestrator/state.json`` (atomic write) so a
    sidecar restart resumes rather than forgets. Module instances stay
    lazy; only the small state snapshots persist."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._router: Router | None = None
        self._runner: LangGraphLoopRunner | None = None
        self._surface: ToolSurface | None = None
        self._fabric: MemoryFabric | None = None
        self._adapters: AdapterRegistry | None = None
        self._queue = StoryQueue()
        self._tenants = TenantRegistry()
        self._trainer: Trainer | None = None
        self._annotations: AnnotationStore | None = None
        self._comprehension: ComprehensionEngine | None = None
        self._simulation: SimulationCore | None = None
        self._calibration = CalibrationTracker()
        self._decisions: dict[str, DecisionRecord] = {}
        self._decision_replays: dict[str, dict[str, Any]] = {}
        self._handles: dict[str, RunHandle] = {}
        self._cp_conn: sqlite3.Connection | None = None
        self._restore()

    # -- lazy builders -----------------------------------------------------

    @property
    def workspace(self) -> Path:
        workspace = self._server._workspace_dir
        if not workspace:
            raise RuntimeError("no workspace configured")
        return Path(workspace)

    @property
    def ledger(self) -> Any:
        return self._server._ensure_ledger()

    @property
    def router(self) -> Router:
        if self._router is None:
            catalogue = load_catalogue([
                self.workspace / ".meridian" / "policy" / "action-classes.yaml",
                Path(__file__).resolve().parents[2] / "policy" / "action-classes.yaml",
            ])
            registry = CapabilityRegistry(catalogue)
            registry.register("parse", StructuralParseCapability())
            dispatcher = Dispatcher(catalogue=catalogue, registry=registry)
            self._router = Router(dispatcher, self.ledger)
        return self._router

    @property
    def runner(self) -> LangGraphLoopRunner:
        if self._runner is None:
            state_dir = self.workspace / ".meridian" / "checkpoints"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._cp_conn = sqlite3.connect(
                str(state_dir / "loops.db"), check_same_thread=False
            )
            self._runner = LangGraphLoopRunner(
                SqliteSaver(self._cp_conn), ledger=self.ledger
            )
        return self._runner

    @property
    def surface(self) -> ToolSurface:
        if self._surface is None:
            self._surface = ToolSurface(
                SandboxConfig(working_dir=self.workspace / ".meridian" / "sandbox"),
                ledger=self.ledger,
            )
        return self._surface

    @property
    def fabric(self) -> MemoryFabric:
        if self._fabric is None:
            self._fabric = MemoryFabric(self.workspace, ledger=self.ledger)
        return self._fabric

    @property
    def adapters(self) -> AdapterRegistry:
        if self._adapters is None:
            # The governed tool allow-list for adapter manifests. A
            # workspace policy may narrow this further at validation time.
            self._adapters = AdapterRegistry(
                tool_allowlist=frozenset(
                    {"repo_read", "build", "test", "apply_patch",
                     "static_analysis", "scan"}
                )
            )
        return self._adapters

    @property
    def trainer(self) -> Trainer:
        if self._trainer is None:
            self._trainer = Trainer(
                self.workspace / ".meridian" / "learned",
                ledger=self.ledger,
            )
        return self._trainer

    @property
    def annotations(self) -> AnnotationStore:
        if self._annotations is None:
            self._annotations = AnnotationStore(self.ledger)
        return self._annotations

    @property
    def comprehension(self) -> ComprehensionEngine:
        if self._comprehension is None:
            self._comprehension = ComprehensionEngine(self.workspace)
        return self._comprehension

    @property
    def simulation(self) -> SimulationCore:
        if self._simulation is None:
            self._simulation = SimulationCore(ledger=self.ledger)
        return self._simulation

    def find_adapter_root(self, adapter_id: str) -> Path:
        for root in self.adapter_roots():
            candidate = root / adapter_id
            if (candidate / "adapter.yaml").is_file():
                return candidate
        raise OrchestraError(f"unknown adapter {adapter_id!r}")

    # -- TASK-320 persistence ------------------------------------------------

    @property
    def _state_path(self) -> Path:
        return self.workspace / ".meridian" / "orchestrator" / "state.json"

    def _restore(self) -> None:
        path = self._state_path
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for handle_raw in raw.get("runs", []):
            definition = canonical_loops().get(handle_raw["loopKey"])
            if definition is not None:
                handle = RunHandle(
                    run_id=handle_raw["runId"],
                    thread_id=handle_raw["threadId"],
                    definition=definition,
                    result=dict(handle_raw["result"]),
                    state_snapshot=dict(handle_raw.get("stateSnapshot") or {}),
                    initial_state=dict(handle_raw.get("initialState") or {}),
                )
                self._handles[handle_raw["loopId"]] = handle
        for story_raw in raw.get("queue", []):
            self._queue.enqueue(Story(
                story_id=story_raw["storyId"],
                priority=int(story_raw["priority"]),
                tenant_id=story_raw["tenantId"],
                dependencies=tuple(story_raw.get("dependencies") or ()),
                waited_ticks=int(story_raw.get("waitedTicks") or 0),
            ))
        for tenant_raw in raw.get("tenants", []):
            try:
                self._tenants.register(
                    Tenant(tenant_raw["tenantId"], Path(tenant_raw["root"]))
                )
            except ValueError:
                continue  # duplicate from a prior snapshot: keep first

    def persist(self) -> None:
        """Atomic snapshot: tmp file + replace, never a half-written state."""
        payload = {
            "version": 1,
            "runs": [
                {
                    "loopId": loop_id,
                    "loopKey": handle.definition.loop_id,
                    "runId": handle.run_id,
                    "threadId": handle.thread_id,
                    "result": dict(handle.result),
                    "stateSnapshot": dict(handle.state_snapshot),
                    "initialState": dict(handle.initial_state),
                }
                for loop_id, handle in self._handles.items()
            ],
            "queue": [
                {
                    "storyId": story.story_id,
                    "priority": story.priority,
                    "tenantId": story.tenant_id,
                    "dependencies": list(story.dependencies),
                    "waitedTicks": story.waited_ticks,
                }
                for story in self._queue._waiting
            ],
            "tenants": [
                {"tenantId": t.tenant_id, "root": str(t.root)}
                for t in self._tenants._tenants.values()
            ],
        }
        path = self._state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        tmp.replace(path)

    def adapter_roots(self) -> list[Path]:
        return [
            self.workspace / ".meridian" / "adapters",
            Path.home() / ".meridian" / "adapters",
            Path(__file__).resolve().parents[2] / "adapters",
        ]

    def shutdown(self) -> None:
        try:
            self.persist()
        except OSError:
            pass
        if self._cp_conn is not None:
            self._cp_conn.close()
            self._cp_conn = None


# ---------------------------------------------------------------------------
# Handlers: (server, params) -> result
# ---------------------------------------------------------------------------


def _state(server: Any) -> OrchestraState:
    orch = getattr(server, "_orchestra", None)
    if orch is None:
        orch = OrchestraState(server)
        server._orchestra = orch
    return orch


def _require(params: Mapping[str, Any], *fields: str) -> None:
    missing = [f for f in fields if params.get(f) in (None, "")]
    if missing:
        raise OrchestraError(f"missing required params: {missing}")


# -- loops -------------------------------------------------------------------


def loop_start(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "loopId", "storyId", "kind")
    key = KIND_TO_LOOP.get(str(params["kind"]))
    if key is None:
        raise OrchestraError(f"unknown loop kind {params['kind']!r}")
    definition = canonical_loops()[key]
    runner = orch.runner
    runner.with_exit_check(definition, _all_visited(definition))
    handle = runner.start(
        definition,
        _stand_in_nodes(definition),
        PROGRESS_SCHEMA,
        story_id=str(params["storyId"]),
    )
    orch._handles[str(params["loopId"])] = handle
    orch.persist()
    return {
        "runId": handle.run_id,
        "status": handle.result["status"],
        "iterations": handle.result["iterations"],
        "checkpointed": True,
    }


def loop_stop(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "loopId")
    handle = orch._handles.get(str(params["loopId"]))
    orch.ledger.append(
        {
            "story_id": "loop-control",
            "phase": "build",
            "loop_id": str(params["loopId"]),
            "loop_iteration": 1,
            "actor_id": "loop-runtime",
            "actor_version": "m4/v1",
            "actor_kind": "meta",
            "policy_version": "loops/v1",
            "action_type": "loop_event",
            "input": json.dumps(
                {"event": "loop_stopped", "reason": params.get("reason", "operator")},
                ensure_ascii=False,
            ),
        }
    )
    orch.persist()
    return {"stopped": True, "was": handle.result["status"] if handle else "unknown"}


def loop_status(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "loopId")
    handle = orch._handles.get(str(params["loopId"]))
    if handle is None:
        raise OrchestraError(
            f"unknown loop {params['loopId']!r} — 'pending' would be a"
            " fabricated state; unknown is unknown"
        )
    return {
        "loopId": params["loopId"],
        "kind": _KIND_OF_LOOP.get(handle.definition.loop_id, handle.definition.loop_id),
        "state": handle.result["status"],
        "iteration": handle.result["iterations"],
    }


def loop_resume(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "loopId")
    handle = orch._handles[str(params["loopId"])]
    finished = orch.runner.resume(handle)
    orch._handles[str(params["loopId"])] = finished
    orch.persist()
    return {"status": finished.result["status"], "iteration": finished.result["iterations"]}


def loop_replay(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "loopId", "stateOverrides")
    handle = orch._handles[str(params["loopId"])]
    fork = orch.runner.replay(handle, state_overrides=params["stateOverrides"])
    orch.persist()
    return {"forkRunId": fork.run_id, "status": fork.result["status"]}


# -- router --------------------------------------------------------------------


def router_request(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "actionClass", "agentId", "storyId", "phase")
    decision = orch.router.request_model_call(
        action_class=str(params["actionClass"]),
        agent_id=str(params["agentId"]),
        story_id=str(params["storyId"]),
        phase=str(params["phase"]),
        payload=params.get("payload"),
        human_override=bool(params.get("humanOverride")),
    )
    return {
        "permitted": decision.permitted,
        "actionClass": decision.action_class,
        "whyLlm": decision.why_llm,
        "refusalReason": decision.refusal_reason,
        "recordedSequence": decision.recorded_sequence,
    }


def router_ratio(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    ratio = orch.router.dependency_ratio(
        agent_id=params.get("agentId"),
        phase=params.get("phase"),
        story_id=params.get("storyId"),
        action_class=params.get("actionClass"),
        ceiling=params.get("ceiling"),
    )
    return ratio.to_dict() if hasattr(ratio, "to_dict") else {
        "modelCalls": ratio.model_calls,
        "engineExecutions": ratio.engine_executions,
        "ratio": ratio.ratio,
        "ceiling": ratio.ceiling,
        "breached": ratio.breached,
    }


# -- tools ---------------------------------------------------------------------


def tools_invoke(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "agentId", "tool", "argv")
    try:
        result = orch.surface.invoke(
            str(params["agentId"]),
            str(params["tool"]),
            [str(a) for a in params["argv"]],
            change_class=str(params.get("changeClass", "ordinary")),
        )
    except ToolDeniedError as exc:
        raise OrchestraError(str(exc))
    return result.to_dict()


# -- memory ---------------------------------------------------------------------


def _entry_from_wire(raw: Mapping[str, Any]) -> MemoryEntry:
    return MemoryEntry(
        entry_id=f"mem-{int.from_bytes(hashlib.sha256((str(raw['subject']) + '|' + str(raw['author'])).encode()).digest()[:4])}",
        # Deterministic id: the same entry content identifies the same
        # entry across processes (hash() is randomised per interpreter —
        # never used for anything persisted).
        tier=str(raw["tier"]),
        subject=str(raw["subject"]),
        content=str(raw["content"]),
        source=raw.get("source"),
        trusted=str(raw.get("origin", "workspace")) not in ("story", "repository", "third_party"),
        provenance=Provenance(
            origin_sequence=None,
            author=str(raw["author"]),
            ts_utc=__import__("meridian_core.memory.fabric", fromlist=["utc_now"]).utc_now(),
            confidence=float(raw["confidence"]),
            origin=str(raw.get("origin", "workspace")),
            pinned=bool(raw.get("pinned", False)),
        ),
    )


def memory_retrieve(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "agentId", "queryTerms", "budgetChars")
    result = orch.fabric.retrieve(
        [str(t) for t in params["queryTerms"]],
        agent_id=str(params["agentId"]),
        budget_chars=int(params["budgetChars"]),
        tiers=tuple(params.get("tiers") or ("procedural", "semantic", "episodic")),
    )
    return {
        "included": [
            {"entryId": e.entry_id, "subject": e.subject, "digest": e.entry_id}
            for e in result.included
        ],
        "cut": list(result.cut),
    }


def memory_write(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "entry")
    entry = _entry_from_wire(params["entry"])
    try:
        orch.fabric.write(entry, actor_is_human=bool(params.get("actorIsHuman")))
    except ValueError as exc:
        return {"written": False, "reason": str(exc)}
    return {"written": True, "reason": None}


def memory_layered(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "layers")
    layers = [(str(l["tier"]), Path(str(l["dir"]))) for l in params["layers"]]
    return {"effective": orch.fabric.layered_procedural(layers)}


# -- comprehension ---------------------------------------------------------------


def comprehension_record(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "path")
    return {"record": orch.comprehension.record(str(params["path"])).to_dict()}


def comprehension_gate(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "path")
    verdict = orch.comprehension.gate(str(params["path"]))
    return {
        "allowed": verdict.allowed,
        "path": verdict.path,
        "reason": verdict.reason,
        "record": verdict.record,
    }


# -- adapters ---------------------------------------------------------------------


def adapters_discover(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    roots = [Path(str(r)) for r in params.get("roots") or orch.adapter_roots()]
    found = orch.adapters.discover(roots)
    return {
        "adapters": [
            {"id": a.manifest.adapter_id, "version": a.manifest.version,
             "valid": a.valid, "errors": list(a.errors)}
            for a in found
        ],
        "states": dict(orch.adapters.states),
    }


def adapters_plug(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "folder")
    adapter = orch.adapters.plug(Path(str(params["folder"])))
    return {"id": adapter.manifest.adapter_id, "valid": adapter.valid,
            "state": orch.adapters.states[adapter.manifest.adapter_id]}


def adapters_unplug(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "id")
    orch.adapters.unplug(str(params["id"]), inflight=params.get("inflight"))
    return {"retired": True, "checkpointed": bool(params.get("inflight"))}


def adapters_promote(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "id")
    from meridian_core.adapters import AgentRegistryM5

    m5 = AgentRegistryM5(orch.adapters, prebuilt_roots=orch.adapter_roots(),
                         ledger=orch.ledger)
    m5.promote(str(params["id"]))
    return {"state": orch.adapters.states[str(params["id"])]}


# -- decisions ---------------------------------------------------------------------


def decisions_record(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "agentId", "inputs", "output", "confidence")
    record = DecisionRecord(
        decision_id=f"dec-{len(orch._decisions) + 1}",
        agent_id=str(params["agentId"]),
        inputs=params["inputs"],
        retrieved_memory=tuple(params.get("retrievedMemory") or ()),
        tool_calls=tuple(params.get("toolCalls") or ()),
        output=params["output"],
        confidence=float(params["confidence"]),
        rationale=Rationale(str(params["rationale"])) if params.get("rationale") else None,
    )
    orch._calibration.capture(record)
    orch._decisions[record.decision_id] = record
    if params.get("replay"):
        orch._decision_replays[record.decision_id] = dict(params["replay"])
    sequence = orch.ledger.append(
        {
            "story_id": "decisions",
            "phase": "build",
            "loop_id": "decisions",
            "loop_iteration": 1,
            "actor_id": record.agent_id,
            "actor_version": "m13/v1",
            "actor_kind": "role",
            "policy_version": "decisions/v1",
            "action_type": "decision_record",
            "input": json.dumps(record.to_dict(), ensure_ascii=False, default=str),
        }
    ).sequence
    return {"sequence": sequence}


def decisions_ablate(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "decisionId", "withoutFactor", "inputs")
    record = orch._decisions.get(str(params["decisionId"]))
    if record is None:
        raise OrchestraError(f"unknown decision {params['decisionId']!r}")
    # TASK-331: the replay recipe may be supplied now or was stored with
    # the decision at record time (hosted decisions record it). The engine
    # is the replayable decision function in both cases.
    action_class = params.get("actionClass")
    recipe = orch._decision_replays.get(str(params["decisionId"]))
    if not action_class and recipe:
        action_class = recipe.get("actionClass")
    if not action_class:
        raise OrchestraError(
            "decisions/ablate requires actionClass (or a decision recorded"
            " with a replay recipe): the engine is the replayable decision"
            " function; narrative decisions without a recipe are not"
        )
    runner = AblationRunner(
        lambda inputs: orch.router._dispatcher.dispatch(str(action_class), inputs).kind
    )
    result = runner.ablate(record, str(params["withoutFactor"]))
    return {
        "changedFactor": result.removed_factor,
        "outputChanged": result.output_changed,
        "labelled": result.labelled(),
    }


def decisions_gate(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    _require(params, "testsPassed", "scansPassed", "approvals", "changeClass")
    gate = GateInputs(
        tests_passed=bool(params["testsPassed"]),
        scans_passed=bool(params["scansPassed"]),
        approvals=tuple(params["approvals"]),
        change_class=str(params["changeClass"]),
        ablations=tuple(params.get("ablations") or ()),
    )
    return {"passed": evaluate_gate(gate)}


# -- portability ---------------------------------------------------------------------


def portability_export(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "adapterId", "destination")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    signing = orch.ledger._signing_key.private_key()
    result = export_package(
        orch.find_adapter_root(str(params["adapterId"])),
        Path(str(params["destination"])),
        signing_key=signing,
    )
    return {"package": str(result.package), "scannedFiles": result.scanned_files}


def portability_diff(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "package")
    diff = diff_against_workspace(Path(str(params["package"])),
                                  _state(server).workspace / ".meridian" / "adapters")
    return {"added": diff["added"], "overwritten": diff["overwritten"]}


def portability_trust(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "fingerprint", "humanApproved")
    from meridian_core.portability import trust_signer

    trust_signer(
        orch.ledger,
        fingerprint=str(params["fingerprint"]),
        human_approved=bool(params["humanApproved"]),
    )
    return {"trusted": True}


def portability_import(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "package", "confirm", "availableTools")
    from meridian_core.portability import (
        import_package,
        package_signature,
        signer_fingerprint,
        trusted_signers,
        verify_package_trust,
    )
    from meridian_core.ledger.keys import public_key_bytes

    # TASK-330: the package must verify against its own embedded key AND
    # its signer fingerprint must be trusted — either this workspace's
    # own key or one explicitly trusted via portability/trust.
    package = Path(str(params["package"]))
    _, public_key_hex = package_signature(package)
    fingerprints = trusted_signers(orch.ledger)
    fingerprints.add(
        signer_fingerprint(
            public_key_bytes(
                orch.ledger._signing_key.private_key()
            ).hex()
        )
    )
    verify_package_trust(package, trusted_fingerprints=fingerprints)
    adapter = import_package(
        package,
        orch.workspace / ".meridian" / "adapters",
        trusted_key=__import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["Ed25519PublicKey"]
        ).Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)),
        available_tools=frozenset(params["availableTools"]),
        registry=orch.adapters,
        confirm=bool(params["confirm"]),
    )
    return {"adapterId": adapter.manifest.adapter_id,
            "state": orch.adapters.states[adapter.manifest.adapter_id]}


# -- trainer ---------------------------------------------------------------------------


def trainer_train(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    try:
        orch.trainer.assert_not_mid_story([str(p) for p in params.get("openPhases") or ()])
    except ValueError as exc:
        return {"ran": False, "refusedReason": str(exc)}
    harvest_signals(orch.ledger)
    return {"ran": True, "refusedReason": None}


def trainer_promote(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "kind", "subject", "content", "incumbentScore",
             "candidateScore", "humanApproved")
    candidate = LearnedDelta(
        kind=str(params["kind"]),
        subject=str(params["subject"]),
        content=str(params["content"]),
    )
    verdict = orch.trainer.evaluate(
        candidate,
        incumbent_score=float(params["incumbentScore"]),
        candidate_score=float(params["candidateScore"]),
    )
    if not verdict.promoted or not params["humanApproved"]:
        return {"promoted": False, "reason": verdict.reason, "path": None}
    path = orch.trainer.promote(
        candidate, verdict,
        human_approved=bool(params["humanApproved"]),
        evidence=dict(params.get("evidence") or {}),
    )
    return {"promoted": True, "reason": verdict.reason, "path": str(path)}


def trainer_rollback(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "kind", "subject")
    path = orch.trainer.rollback(str(params["kind"]), str(params["subject"]))
    return {"path": str(path)}


# -- tenancy / queue ---------------------------------------------------------------------


def tenancy_register(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "tenantId", "root")
    orch._tenants.register(Tenant(str(params["tenantId"]), Path(str(params["root"]))))
    orch.persist()
    return {"registered": True}


def queue_enqueue(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "story")
    raw = params["story"]
    orch._queue.enqueue(
        Story(
            story_id=str(raw["storyId"]),
            priority=int(raw["priority"]),
            tenant_id=str(raw["tenantId"]),
            dependencies=tuple(raw.get("dependencies") or ()),
        )
    )
    orch.persist()
    return {"enqueued": True}


def queue_tick(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    admitted = orch._queue.tick()
    return {"admitted": [s.story_id for s in admitted]}


# -- annotations / issues -------------------------------------------------------------------


def annotations_add(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "targetSeq", "author", "text")
    sequence = orch.annotations.add(
        Annotation(
            target_seq=int(params["targetSeq"]),
            author=str(params["author"]),
            text=str(params["text"]),
            bookmark=bool(params.get("bookmark")),
        )
    )
    return {"sequence": sequence}


def issues_record(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "agentId", "severity", "description", "storyId")
    sequence = record_detected_issue(
        orch.ledger,
        agent_id=str(params["agentId"]),
        severity=str(params["severity"]),
        description=str(params["description"]),
        story_id=str(params["storyId"]),
    )
    return {"sequence": sequence}


# -- simulation / golden ---------------------------------------------------------------------


def simulation_serve(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "method", "params")
    if params.get("scenario"):
        from meridian_core.simulation.scenarios import load_scenario

        scenario = load_scenario(str(params["scenario"]))
        orch.simulation._scenario = scenario
        orch.simulation.clock = __import__(
            "meridian_core.simulation", fromlist=["SimulationClock"]
        ).SimulationClock(scenario.sequences())
    response = orch.simulation.serve(str(params["method"]), params["params"] or {})
    return {"response": response, "backend": orch.simulation.backend}


def simulation_time_control(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "action")
    clock: SimulationClock = orch.simulation.clock
    action = str(params["action"])
    if action == "pause":
        position = clock.pause()
    elif action == "step":
        position = clock.step()
    elif action == "play":
        position = clock.play(rate=float(params.get("rate", 1.0)))
    elif action == "jump":
        position = clock.jump(int(params["sequence"]))
    else:
        raise OrchestraError(f"unknown time-control action {action!r}")
    return {"position": position, "paused": clock.paused}


def golden_run(server: Any, params: Mapping[str, Any]) -> Mapping[str, Any]:
    orch = _state(server)
    _require(params, "folder")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = orch.simulation.run_golden(Path(str(params["folder"])), Path(tmp))
    return dict(result)


HANDLERS: dict[str, Callable[[Any, Mapping[str, Any]], Mapping[str, Any]]] = {
    "loop.start": loop_start,
    "loop.stop": loop_stop,
    "loop.status": loop_status,
    "loop.resume": loop_resume,
    "loop.replay": loop_replay,
    "router/requestModelCall": router_request,
    "router/dependencyRatio": router_ratio,
    "tools/invoke": tools_invoke,
    "memory/retrieve": memory_retrieve,
    "memory/write": memory_write,
    "memory/layered": memory_layered,
    "comprehension/record": comprehension_record,
    "comprehension/gate": comprehension_gate,
    "adapters/discover": adapters_discover,
    "adapters/plug": adapters_plug,
    "adapters/unplug": adapters_unplug,
    "adapters/promote": adapters_promote,
    "decisions/record": decisions_record,
    "decisions/ablate": decisions_ablate,
    "decisions/gate": decisions_gate,
    "portability/export": portability_export,
    "portability/trust": portability_trust,
    "portability/import": portability_import,
    "portability/diff": portability_diff,
    "trainer/train": trainer_train,
    "trainer/promote": trainer_promote,
    "trainer/rollback": trainer_rollback,
    "tenancy/register": tenancy_register,
    "queue/enqueue": queue_enqueue,
    "queue/tick": queue_tick,
    "annotations/add": annotations_add,
    "issues/record": issues_record,
    "simulation/serve": simulation_serve,
    "simulation/timeControl": simulation_time_control,
    "golden/run": golden_run,
}
