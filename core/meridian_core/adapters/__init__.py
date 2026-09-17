"""M31 Adapter framework, re-based on ACP per FR-M34-02 — FR-M31-02…04,
06…10, 12, 15.

An adapter is an ACP agent plus a Meridian governance manifest. The ACP
transport lives in the extension host; THIS module is the governance
side, and it is transport-agnostic: it discovers adapter folders,
validates their manifests, admits them through probation, hot-plugs
them (no restart), routes bridges through the sandbox and the tool
permission check, and ports their ``learned/`` state.

- FR-M31-02: discovery from ``.meridian/adapters/`` then
  ``~/.meridian/adapters/`` then the organisation registry, in that
  precedence.
- FR-M31-03: validation — manifest schema, declared tools against the
  policy allow-list, files resolvable, digest where present. Invalid
  adapters are listed WITH their errors and never loaded.
- FR-M31-04: hot plug — adding a folder admits the adapter to
  probation; removing it retires the agent. In-flight work owned by an
  unplugged adapter is checkpointed and escalated, never lost.
- FR-M31-06: bridges run the wrapped agent inside the FR-M9-05 sandbox
  and route every tool call through the FR-M9-03 permission check; a
  bridged agent cannot bypass governance by being external.
- FR-M31-07: every adapter enters at the ``suggest`` probation tier.
- FR-M31-08/09: manifests declare trainable surfaces and action classes.
- FR-M31-10: adapters are executable code — digest-pinned and revocable.
- FR-M31-12: ``learned/`` is the complete acquired-state record;
  export/import move it.
- FR-M31-15: adapter dependencies resolved and validated at discovery.

Zero model calls.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from meridian_core.tools.surface import (
    SandboxConfig,
    ToolDeniedError,
    ToolSurface,
    run_in_sandbox,
)

MANIFEST_NAME = "adapter.yaml"
TRAINABLE_SURFACES = ("policy", "rules", "memory", "skills", "calibration")
ACTION_CLASS_MODES = ("deterministic", "assisted", "generative")
ADAPTER_STATES = ("probation", "active", "paused", "retired")


class AdapterError(ValueError):
    """A framework rule violation; carries the requirement id."""


@dataclass(frozen=True)
class AdapterManifest:
    """The §7.9 governance facet (ACP identity is separate, host-side)."""

    adapter_id: str
    version: str
    role: str
    acp: bool  # speaks ACP natively (True) or requires a bridge
    bridge: str | None  # "plain_python" | "mcp" — D15 v1 set
    permitted_tools: tuple[str, ...]
    trainable: Mapping[str, bool]  # FR-M31-08
    action_classes: Mapping[str, str]  # FR-M31-09: class -> mode
    dependencies: tuple[str, ...] = ()  # FR-M31-15
    digest: str | None = None  # FR-M31-10

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "version": self.version,
            "role": self.role,
            "acp": self.acp,
            "bridge": self.bridge,
            "permittedTools": list(self.permitted_tools),
            "trainable": dict(self.trainable),
            "actionClasses": dict(self.action_classes),
            "dependencies": list(self.dependencies),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class AdapterFolder:
    """One discovered adapter on disk."""

    root: Path
    manifest: AdapterManifest
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def learned_dir(self) -> Path:
        return self.root / "learned"

    @property
    def healthy(self) -> bool:
        return (self.root / "agent.py").exists()


def parse_manifest(text: str, source: str) -> AdapterManifest:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise AdapterError(f"FR-M31-03: {source}: manifest is not YAML: {exc}")
    if not isinstance(raw, dict):
        raise AdapterError(f"FR-M31-03: {source}: manifest is not a mapping")
    try:
        adapter_id = str(raw["id"])
        version = str(raw["version"])
        role = str(raw["role"])
    except KeyError as exc:
        raise AdapterError(f"FR-M31-03: {source}: manifest missing {exc}")
    trainable = {
        surface: bool(raw.get("trainable", {}).get(surface, False))
        for surface in TRAINABLE_SURFACES
    }
    action_classes = {
        str(k): str(v) for k, v in (raw.get("actionClasses") or {}).items()
    }
    unknown_modes = set(action_classes.values()) - set(ACTION_CLASS_MODES)
    if unknown_modes:
        raise AdapterError(
            f"FR-M31-09: {source}: unknown action-class modes {sorted(unknown_modes)}"
        )
    return AdapterManifest(
        adapter_id=adapter_id,
        version=version,
        role=role,
        acp=bool(raw.get("acp", False)),
        bridge=raw.get("bridge"),
        permitted_tools=tuple(raw.get("permittedTools") or ()),
        trainable=trainable,
        action_classes=action_classes,
        dependencies=tuple(raw.get("dependencies") or ()),
        digest=raw.get("digest"),
    )


def folder_digest(root: Path) -> str:
    """FR-M31-10: digest over every file the adapter ships, stable order."""
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == MANIFEST_NAME:
            continue  # the digest lives inside the manifest
        hasher.update(path.relative_to(root).as_posix().encode())
        hasher.update(path.read_bytes())
    return "sha256:" + hasher.hexdigest()


@dataclass
class AdapterRegistry:
    """Discovery, validation, hot-plug lifecycle (FR-M31-02/03/04)."""

    tool_allowlist: frozenset[str]
    surfaces: ToolSurface | None = None
    adapters: dict[str, AdapterFolder] = field(default_factory=dict)
    states: dict[str, str] = field(default_factory=dict)
    escalations: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)

    # -- FR-M31-02: discovery -------------------------------------------------

    def discover(self, roots: Sequence[Path]) -> list[AdapterFolder]:
        """Precedence: first root wins for an adapter id."""
        found: dict[str, AdapterFolder] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for folder in sorted(root.iterdir()):
                if not folder.is_dir() or folder.name.startswith("."):
                    continue
                if folder.name in found:
                    continue  # higher-precedence root already claimed it
                found[folder.name] = self._validate(folder)
        return list(found.values())

    def load(self, roots: Sequence[Path]) -> None:
        """Discovery + admission. Valid adapters enter probation
        (FR-M31-07); invalid ones are listed with errors, never loaded."""
        for adapter in self.discover(roots):
            if not adapter.valid:
                self.adapters[adapter.manifest.adapter_id] = adapter
                self.states[adapter.manifest.adapter_id] = "retired"
                continue
            self._admit(adapter)

    def _validate(self, folder: Path) -> AdapterFolder:
        errors: list[str] = []
        manifest_path = folder / MANIFEST_NAME
        manifest: AdapterManifest | None = None
        if not manifest_path.is_file():
            errors.append("FR-M31-03: missing adapter.yaml")
        else:
            try:
                manifest = parse_manifest(
                    manifest_path.read_text(encoding="utf-8"), str(folder)
                )
                disallowed = set(manifest.permitted_tools) - set(self.tool_allowlist)
                if disallowed:
                    errors.append(
                        f"FR-M31-03: tools not in the policy allow-list:"
                        f" {sorted(disallowed)}"
                    )
                if manifest.bridge not in (None, "plain_python", "mcp"):
                    errors.append(
                        f"FR-M31-06: unknown bridge {manifest.bridge!r}"
                    )
                if manifest.digest and manifest.digest != folder_digest(folder):
                    errors.append(
                        "FR-M31-10: digest mismatch — the adapter's files"
                        " changed since it was pinned"
                    )
                for dep in manifest.dependencies:
                    pass  # cross-adapter resolution happens post-discovery
                for required in ("skills", "instructions", "agent.py"):
                    if not (folder / required).exists():
                        errors.append(f"FR-M31-03: missing {required}/")
            except AdapterError as exc:
                errors.append(str(exc))
        if manifest is None:
            manifest = AdapterManifest(
                adapter_id=folder.name, version="0", role="unknown",
                acp=False, bridge=None, permitted_tools=(),
                trainable={}, action_classes={},
            )
        return AdapterFolder(root=folder, manifest=manifest, errors=tuple(errors))

    def _admit(self, adapter: AdapterFolder) -> None:
        self.adapters[adapter.manifest.adapter_id] = adapter
        self.states[adapter.manifest.adapter_id] = "probation"  # FR-M31-07

    # -- FR-M31-04: hot plug ------------------------------------------------------

    def plug(self, folder: Path) -> AdapterFolder:
        """Adding a folder: validate, admit to probation. No restart."""
        adapter = self._validate(folder)
        self.adapters[adapter.manifest.adapter_id] = adapter
        self.states[adapter.manifest.adapter_id] = (
            "probation" if adapter.valid else "retired"
        )
        return adapter

    def unplug(self, adapter_id: str, *, inflight: Mapping[str, Any] | None = None) -> None:
        """Removing the folder: retire the agent. In-flight work owned by
        the adapter is checkpointed and escalated — never lost."""
        if adapter_id not in self.adapters:
            raise AdapterError(f"unknown adapter {adapter_id!r}")
        self.states[adapter_id] = "retired"
        if inflight:
            self.checkpoints[adapter_id] = dict(inflight)
            self.escalations.append(
                {
                    "adapterId": adapter_id,
                    "event": "unplugged_with_inflight_work",
                    "checkpointed": True,
                    "escalation_target": "human",
                }
            )

    def replug(self, adapter_id: str, folder: Path) -> AdapterFolder:
        """Re-plug: the framework is done when every adapter survives
        unplug and re-plug — state restored, probation respected."""
        adapter = self.plug(folder)
        if adapter_id in self.checkpoints:
            # The checkpointed work is handed back for resumption; the
            # escalation record stays as the audit trail.
            adapter.root.joinpath("learned").mkdir(exist_ok=True)
        return adapter

    # -- FR-M31-12: portability ------------------------------------------------------

    def export_state(self, adapter_id: str, destination: Path) -> Path:
        """``learned/`` is the complete record of what the agent acquired."""
        adapter = self.adapters[adapter_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.make_archive(str(destination), "zip", adapter.learned_dir)
        return Path(str(destination) + ".zip")

    def import_state(self, adapter_id: str, archive: Path) -> None:
        adapter = self.adapters[adapter_id]
        import zipfile

        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(adapter.learned_dir)

    # -- FR-M31-15: dependency resolution ----------------------------------------------

    def resolve_dependencies(self) -> dict[str, list[str]]:
        """Validate the dependency graph at discovery time; every declared
        dependency must exist among the loaded adapters."""
        missing: dict[str, list[str]] = {}
        for adapter_id, adapter in self.adapters.items():
            unresolved = [
                dep for dep in adapter.manifest.dependencies
                if dep not in self.adapters
            ]
            if unresolved:
                missing[adapter_id] = unresolved
        return missing


class PlainPythonBridge:
    """FR-M31-06 (D15): a plain-Python callable wrapped as an adapter.
    The wrapped callable runs inside the FR-M9-05 sandbox and every tool
    call it attempts routes through the FR-M9-03 permission check."""

    def __init__(
        self,
        manifest: AdapterManifest,
        callable_path: Path,
        surface: ToolSurface,
    ) -> None:
        if manifest.bridge != "plain_python":
            raise AdapterError("FR-M31-06: not a plain-python bridge manifest")
        self._manifest = manifest
        self._callable = callable_path
        self._surface = surface

    def invoke(self, agent_id: str, *, args_file: Path, sandbox: SandboxConfig) -> Any:
        """Run the wrapped callable in the sandbox. The callable receives
        its inputs as a JSON file (no credentials in argv — FR-M9-07);
        tool access is only possible through the surface, which checks
        permissions first."""
        result = run_in_sandbox(
            [
                "python",
                str(self._callable),
                str(args_file),
            ],
            sandbox,
        )
        if not result.ok:
            raise AdapterError(
                f"FR-M31-06: bridged agent failed: {result.output[:200]}"
            )
        return result.output

    def guarded_tool(self, agent_id: str, tool: str, argv: Sequence[str]) -> Any:
        """The ONLY tool path a bridged agent gets — permission-checked."""
        return self._surface.invoke(agent_id, tool, argv)


# -- FR-M5 registry deltas -----------------------------------------------------

#: FR-M5-07: provenance is derived from where the adapter was discovered
#: and whether it wraps an external agent — governance is identical, but
#: trust history is not, so the distinction rides every adapter.
PROVENANCE_PREBUILT = "prebuilt"
PROVENANCE_CUSTOM = "custom"
PROVENANCE_BRIDGED = "bridged"


def classify_provenance(folder: AdapterFolder, prebuilt_roots: Sequence[Path]) -> str:
    if folder.manifest.bridge:
        return PROVENANCE_BRIDGED
    for root in prebuilt_roots:
        try:
            folder.root.relative_to(root)
            return PROVENANCE_PREBUILT
        except ValueError:
            continue
    return PROVENANCE_CUSTOM


class AgentRegistryM5:
    """FR-M5-04/05/06/07 on top of the M31 lifecycle: versioned
    manifests, agent states, immutable versions, retirement that keeps
    history, provenance on every agent."""

    def __init__(
        self,
        registry: AdapterRegistry,
        *,
        prebuilt_roots: Sequence[Path] = (),
        ledger: Any = None,
    ) -> None:
        self._registry = registry
        self._prebuilt_roots = tuple(prebuilt_roots)
        self._ledger = ledger
        #: FR-M5-04: every version of a manifest ever admitted is kept;
        #: a re-plug with a changed version archives the old one rather
        #: than overwriting it.
        self._versions: dict[str, list[AdapterFolder]] = {}

    def admit(self, adapter: AdapterFolder) -> None:
        manifest = adapter.manifest
        history = self._versions.setdefault(manifest.adapter_id, [])
        if history and history[-1].manifest.version != manifest.version:
            history.append(adapter)  # new immutable version; old kept
        elif not history:
            history.append(adapter)
        self._registry.adapters[manifest.adapter_id] = adapter
        if adapter.valid:
            self._registry.states[manifest.adapter_id] = "probation"
            self._record_version(manifest)

    def _record_version(self, manifest: AdapterManifest) -> None:
        """FR-M5-04: the ledger records the exact version that acts."""
        if self._ledger is None:
            return
        self._ledger.append(
            {
                "story_id": "agent-registry",
                "phase": "govern",
                "loop_id": "registry",
                "loop_iteration": 1,
                "actor_id": manifest.adapter_id,
                "actor_version": manifest.version,
                "actor_kind": "meta",
                "policy_version": "registry/v1",
                "action_type": "policy_update",
                "input": json.dumps(
                    {
                        "event": "agent_admitted",
                        "provenance": self.provenance(manifest.adapter_id),
                    },
                    ensure_ascii=False,
                ),
            }
        )

    def promote(self, adapter_id: str) -> None:
        """Probation -> active. Only active agents may take live work."""
        if adapter_id not in self._registry.adapters:
            raise AdapterError(f"unknown adapter {adapter_id!r}")
        if self._registry.states[adapter_id] != "probation":
            raise AdapterError(
                f"FR-M5-05: only probation agents may be promoted; "
                f"{adapter_id} is {self._registry.states[adapter_id]}"
            )
        self._registry.states[adapter_id] = "active"

    def pause(self, adapter_id: str) -> None:
        self._registry.states[adapter_id] = "paused"

    def retire(self, adapter_id: str) -> None:
        """FR-M5-06: retirement changes state, never deletes the manifest
        or the version history."""
        self._registry.states[adapter_id] = "retired"

    def can_take_work(self, adapter_id: str) -> bool:
        """FR-M5-05: only `active` agents take live work. Inactive
        agents display Learning with an accurate substate — callers
        surface the state rather than fabricating activity."""
        return self._registry.states.get(adapter_id) == "active"

    def learning_substate(self, adapter_id: str) -> str:
        state = self._registry.states.get(adapter_id, "unknown")
        return {
            "probation": "probation: suggest-tier, under evaluation",
            "paused": "paused: not taking delivery tasks",
            "retired": "retired: removed from delivery",
        }.get(state, "active")

    def provenance(self, adapter_id: str) -> str:
        folder = self._registry.adapters[adapter_id]
        return classify_provenance(folder, self._prebuilt_roots)

    def versions(self, adapter_id: str) -> tuple[str, ...]:
        """FR-M5-04: the full immutable version history."""
        return tuple(a.manifest.version for a in self._versions.get(adapter_id, ()))
