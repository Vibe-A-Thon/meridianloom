"""Action-class catalogue (FR-M33-01; §7.10; D16).

The catalogue classifies every agent action as ``deterministic``,
``assisted`` or ``generative`` and is the D16 artefact: a policy YAML file
(``policy/action-classes.yaml`` in the repository; a workspace overrides it
at ``.meridian/policy/action-classes.yaml`` — first readable file wins, the
same convention as the governance and pricing packs). Reclassification
(FR-M33-10) is a reviewed change to that file, never a runtime decision.

Parsing is fail-closed exactly like the other policy packs: YAML syntax
errors and schema violations come back as ``errors`` and a catalogue with
any error refuses every lookup — a malformed catalogue never silently
classifies an action as generative. This module never raises on policy
content.

Zero model calls: this is table lookups and validation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

__all__ = [
    "ActionClass",
    "Catalogue",
    "MODES",
    "load_catalogue",
    "parse_catalogue",
    "repo_default_paths",
]

#: The §7.10 classification modes.
MODES = ("deterministic", "assisted", "generative")

#: Field names a class entry understands, per mode.
_COMMON_KEYS = ("mode", "engine", "schema", "rationale", "escalateIf")
_MODE_KEYS = {
    "deterministic": ("capability",),
    "assisted": ("deterministicFirst", "gap"),
    "generative": ("validate",),
}
_CLASS_KEYS = frozenset(
    _COMMON_KEYS + tuple(key for keys in _MODE_KEYS.values() for key in keys)
)

_TOP_LEVEL_KEYS = ("version", "actionClasses", "ceilings")


@dataclass(frozen=True)
class ActionClass:
    """One §7.10 action class.

    ``capability`` names the FR-M33-02 capability that owns a deterministic
    class (None for assisted/generative — the engine cannot execute them
    end to end). ``deterministic_first`` names the capability an assisted
    class runs before declaring its gap. ``escalate_if`` names the single
    condition under which a deterministic class may escalate (absent =
    escalation structurally impossible, FR-M8-15).
    """

    id: str
    mode: str
    engine: str
    rationale: str
    capability: str | None = None
    deterministic_first: str | None = None
    gap: str | None = None
    schema: str | None = None
    validate: tuple[str, ...] = ()
    escalate_if: str | None = None

    @property
    def router_eligible(self) -> bool:
        """Whether the mode ever permits the router to be invoked
        (FR-M33-03). Escalation out of a deterministic class additionally
        requires ``escalate_if`` to be named."""
        return self.mode in ("assisted", "generative")


@dataclass
class Catalogue:
    """The parsed catalogue. ``errors`` non-empty means fail-closed: every
    lookup returns None (unknown class refused) — a malformed catalogue
    never opens a path to the router."""

    version: int
    source: str
    classes: dict[str, ActionClass] = field(default_factory=dict)
    ceilings: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    def lookup(self, action_class: str) -> ActionClass | None:
        """The class entry, or None when unknown or the catalogue is
        fail-closed — an unknown class is always refused."""
        if self.errors:
            return None
        return self.classes.get(action_class)


def parse_catalogue(text: str, source: str) -> Catalogue:
    """Parse and validate a catalogue document. Never raises on content:
    every violation lands in ``errors`` and the catalogue refuses all
    lookups."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return Catalogue(version=0, source=source, errors=[f"{source}: not valid YAML: {error}"])
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return Catalogue(
            version=0, source=source, errors=[f"{source}: must be a mapping at the top level"]
        )

    errors: list[str] = []
    version = raw.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        errors.append(f"version: expected an integer >= 1, got {version!r}")
        version = 0
    unknown_sections = set(raw) - set(_TOP_LEVEL_KEYS)
    for name in sorted(unknown_sections):
        errors.append(f"{name}: unknown top-level section")

    classes: dict[str, ActionClass] = {}
    raw_classes = raw.get("actionClasses", {})
    if not isinstance(raw_classes, Mapping):
        errors.append("actionClasses: expected a mapping of class id to spec")
    else:
        for class_id, spec in raw_classes.items():
            where = f"actionClasses.{class_id}"
            if not isinstance(class_id, str) or not class_id.strip():
                errors.append("actionClasses: class ids must be non-empty strings")
                continue
            entry = _parse_class(class_id.strip(), spec, where, errors)
            if entry is not None:
                classes[entry.id] = entry

    ceilings = raw.get("ceilings", {})
    if not isinstance(ceilings, Mapping):
        errors.append("ceilings: expected a mapping")
        ceilings = {}
    else:
        ratio = ceilings.get("llm_dependency_ratio_max")
        if ratio is not None and (
            not isinstance(ratio, (int, float))
            or isinstance(ratio, bool)
            or not 0 <= ratio <= 1
        ):
            errors.append(
                f"ceilings.llm_dependency_ratio_max: expected a number in [0, 1], got {ratio!r}"
            )
        unknown_ceilings = set(ceilings) - {"llm_dependency_ratio_max"}
        for name in sorted(unknown_ceilings):
            errors.append(f"ceilings.{name}: unknown ceiling")

    if errors:
        return Catalogue(
            version=version, source=source, errors=[f"{source}: {e}" for e in errors]
        )
    return Catalogue(version=version, source=source, classes=classes, ceilings=dict(ceilings))


def _parse_class(
    class_id: str, spec: Any, where: str, errors: list[str]
) -> ActionClass | None:
    if not isinstance(spec, Mapping):
        errors.append(f"{where}: expected a mapping")
        return None
    unknown = set(spec) - _CLASS_KEYS
    for key in sorted(unknown):
        errors.append(f"{where}: unknown key '{key}'")

    mode = spec.get("mode")
    if mode not in MODES:
        errors.append(f"{where}.mode: '{mode}' is not a mode ({', '.join(MODES)})")
        return None

    engine = spec.get("engine")
    if not isinstance(engine, str) or not engine.strip():
        errors.append(f"{where}.engine: expected a non-empty string (owning engine, FR-M33-01)")
        engine = ""

    rationale = spec.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append(f"{where}.rationale: expected a non-empty string (FR-M33-01)")
        rationale = ""

    schema = spec.get("schema")
    if schema is not None and (not isinstance(schema, str) or not schema.strip()):
        errors.append(f"{where}.schema: expected a non-empty string when present")
        schema = None

    escalate_if = spec.get("escalateIf")
    if escalate_if is not None and (not isinstance(escalate_if, str) or not escalate_if.strip()):
        errors.append(f"{where}.escalateIf: expected a non-empty string when present")
        escalate_if = None

    capability = None
    deterministic_first = None
    gap = None
    validate: tuple[str, ...] = ()

    if mode == "deterministic":
        capability = spec.get("capability")
        if not isinstance(capability, str) or not capability.strip():
            errors.append(
                f"{where}.capability: a deterministic class must name its "
                f"FR-M33-02 capability"
            )
            capability = None
    elif mode == "assisted":
        deterministic_first = spec.get("deterministicFirst")
        if not isinstance(deterministic_first, str) or not deterministic_first.strip():
            errors.append(
                f"{where}.deterministicFirst: an assisted class must name the "
                f"capability that runs before the gap (FR-M33-04)"
            )
            deterministic_first = None
        gap = spec.get("gap")
        if not isinstance(gap, str) or not gap.strip():
            errors.append(f"{where}.gap: an assisted class must name its bounded gap (FR-M33-04)")
            gap = None
        if schema is None:
            errors.append(f"{where}.schema: an assisted class must name its gap schema (FR-M33-04)")
    else:  # generative
        if spec.get("capability") is not None:
            errors.append(
                f"{where}.capability: a generative class must not claim a "
                f"deterministic capability (the engine cannot help, FR-M33-03)"
            )
        raw_validate = spec.get("validate")
        if (
            not isinstance(raw_validate, list)
            or not raw_validate
            or any(not isinstance(v, str) or not v.strip() for v in raw_validate)
        ):
            errors.append(
                f"{where}.validate: a generative class needs a non-empty list of "
                f"validator names (FR-M33-05)"
            )
        else:
            validate = tuple(v.strip() for v in raw_validate)
        if schema is None:
            errors.append(f"{where}.schema: a generative class must name its output schema (FR-M8-14)")

    return ActionClass(
        id=class_id,
        mode=mode,
        engine=engine.strip(),
        rationale=rationale.strip(),
        capability=capability.strip() if isinstance(capability, str) else None,
        deterministic_first=(
            deterministic_first.strip() if isinstance(deterministic_first, str) else None
        ),
        gap=gap.strip() if isinstance(gap, str) else None,
        schema=schema.strip() if isinstance(schema, str) else None,
        validate=validate,
        escalate_if=escalate_if.strip() if isinstance(escalate_if, str) else None,
    )


def repo_default_paths(workspace: str | Path | None = None) -> list[Path]:
    """The catalogue search path: workspace override first, then the
    repository default. First readable file wins."""
    repo_root = Path(__file__).resolve().parents[3]
    paths: list[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / ".meridian" / "policy" / "action-classes.yaml")
    paths.append(repo_root / "policy" / "action-classes.yaml")
    return paths


def load_catalogue(paths: Sequence[str | Path]) -> Catalogue:
    """First readable file wins. No readable file is a fail-closed
    catalogue, never an exception."""
    tried: list[str] = []
    for path in paths:
        candidate = Path(path)
        tried.append(str(candidate))
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        return parse_catalogue(text, str(candidate))
    return Catalogue(
        version=0,
        source="action-class-catalogue",
        errors=["no catalogue file found (tried: " + ", ".join(tried) + ")"],
    )
