"""The E-GR-03 rework reason taxonomy (FR-M37-02; F1 Workstream B task 14).

DECISION RATIONALE (recorded in the module docstring as the brief
requires): FR-M37-02 — and gaps task 14 — mandate that every rejection
carry a reason from the canonical taxonomy referenced as ``E-GR-03``.
No document in ``docs/spec/`` defines that taxonomy's member list (a full
text search finds only the FR-M37-02 reference itself), so the taxonomy
is **defined, not merely adopted**: ``policy/rework-reasons.yaml`` — a
real, versioned, git-backed file reviewed like ``governance.yaml`` —
carries the eight core classes, and this module is the single classifier
every rejection and conflict record passes through. The classes:

wrong-requirement · incorrect-implementation · style-convention ·
missing-tests · security-concern · agent-conflict (the FR-M35-07
multi-agent conflict class, distinct from human rejection) ·
obsolete-superseded · other.

Classification is **fail-closed**: an absent, blank or unrecognised
reason never produces an unclassified record. It stamps the default
class (``other``) and carries the caller's raw input — or an explanatory
note — in ``note``. Detection-derived rejections cannot know WHY a human
rejected a change, so their default note says exactly that; review-sourced
rejections should always supply an explicit class.

Zero model calls (FR-M36-07): parsing and classification are string
normalisation over the policy file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

__all__ = [
    "DEFAULT_TAXONOMY_PATHS",
    "ReasonClass",
    "ReasonStamp",
    "Taxonomy",
    "TaxonomyError",
    "classify_reason",
    "load_taxonomy",
    "repo_taxonomy_path",
]

#: The embedded canonical copy of policy/rework-reasons.yaml. Loading falls
#: back to this when the policy file is unreadable or malformed, so a
#: missing file degrades to the shipped taxonomy — never to no taxonomy.
#: Kept in sync with the policy file (a test asserts the classes match).
_CANONICAL_YAML = """
version: 1
default: other
classes:
  - id: wrong-requirement
    label: Wrong requirement
    description: The change implements the wrong requirement or a misread one.
  - id: incorrect-implementation
    label: Incorrect implementation
    description: The requirement was right but the code is wrong.
  - id: style-convention
    label: Style / convention
    aliases: [style/convention]
    description: Violates the team's coding standards, naming or conventions.
  - id: missing-tests
    label: Missing tests
    description: Rejected for absent or inadequate test coverage.
  - id: security-concern
    label: Security concern
    description: Raises a security issue.
  - id: agent-conflict
    label: Agent conflict
    description: Two agents' changes conflict on the same story (FR-M35-07).
  - id: obsolete-superseded
    label: Obsolete / superseded
    aliases: [obsolete/superseded]
    description: Overtaken by events — superseded or re-scoped.
  - id: other
    label: Other
    description: Catch-all; requires a free-text note.
    requiresNote: true
"""


class TaxonomyError(ValueError):
    """The taxonomy policy file is unusable (not YAML, wrong shape)."""


@dataclass(frozen=True)
class ReasonClass:
    """One taxonomy class."""

    id: str
    label: str
    description: str
    aliases: tuple[str, ...] = ()
    requires_note: bool = False


@dataclass(frozen=True)
class Taxonomy:
    """The parsed taxonomy: versioned classes plus the fail-closed default."""

    version: int
    default: ReasonClass
    classes: tuple[ReasonClass, ...]
    source: str

    def __post_init__(self) -> None:
        lookup: dict[str, ReasonClass] = {}
        for cls in self.classes:
            lookup[cls.id] = cls
            for alias in cls.aliases:
                lookup[alias] = cls
        object.__setattr__(self, "_lookup", lookup)

    def lookup(self, value: str) -> ReasonClass | None:
        """Resolve a class id or alias (normalised) to its class."""
        normalised = value.strip().lower()
        return self._lookup.get(normalised)  # type: ignore[attr-defined]

    def is_valid(self, value: Any) -> bool:
        return isinstance(value, str) and self.lookup(value) is not None


@dataclass(frozen=True)
class ReasonStamp:
    """The classified reason every rejection/conflict record carries:
    a canonical class id plus a free-text note (required for ``other``)."""

    reason: str
    note: str | None = None


def repo_taxonomy_path() -> Path:
    """The repository's taxonomy file (core/meridian_core/ -> repo root)."""
    return Path(__file__).resolve().parents[3] / "policy" / "rework-reasons.yaml"


def default_taxonomy_paths() -> list[Path]:
    """Resolution order: workspace override, repository policy, embedded
    canonical copy (the fallback, not a file)."""
    paths = [repo_taxonomy_path()]
    return paths


DEFAULT_TAXONOMY_PATHS = default_taxonomy_paths()


def _parse_class(raw: Any, where: str) -> ReasonClass:
    if not isinstance(raw, Mapping):
        raise TaxonomyError(f"{where}: expected a mapping")
    class_id = raw.get("id")
    if not isinstance(class_id, str) or not class_id.strip():
        raise TaxonomyError(f"{where}.id: expected a non-empty string")
    label = raw.get("label")
    description = raw.get("description")
    aliases_raw = raw.get("aliases") or []
    if not isinstance(aliases_raw, list) or any(not isinstance(a, str) for a in aliases_raw):
        raise TaxonomyError(f"{where}.aliases: expected a list of strings")
    return ReasonClass(
        id=class_id.strip(),
        label=label.strip() if isinstance(label, str) else class_id.strip(),
        description=description.strip() if isinstance(description, str) else "",
        aliases=tuple(a.strip() for a in aliases_raw if a.strip()),
        requires_note=bool(raw.get("requiresNote", False)),
    )


def parse_taxonomy(text: str, source: str) -> Taxonomy:
    """Parse and validate a taxonomy document. Raises :class:`TaxonomyError`
    on any violation — a malformed taxonomy is fixed, never half-loaded."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise TaxonomyError(f"{source}: taxonomy is not valid YAML: {error}") from error
    if not isinstance(raw, Mapping):
        raise TaxonomyError(f"{source}: taxonomy must be a mapping")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise TaxonomyError(f"{source}: version must be an integer >= 1")
    raw_classes = raw.get("classes")
    if not isinstance(raw_classes, list) or not raw_classes:
        raise TaxonomyError(f"{source}: classes must be a non-empty list")
    classes = tuple(
        _parse_class(item, f"{source}: classes[{index}]")
        for index, item in enumerate(raw_classes)
    )
    ids = [cls.id for cls in classes]
    if len(set(ids)) != len(ids):
        raise TaxonomyError(f"{source}: duplicate class ids in {ids}")
    default_id = raw.get("default")
    default = next((cls for cls in classes if cls.id == default_id), None)
    if default is None:
        raise TaxonomyError(
            f"{source}: default '{default_id}' is not one of the class ids"
        )
    return Taxonomy(version=version, default=default, classes=classes, source=source)


def load_taxonomy(paths: Sequence[str | Path] | None = None) -> Taxonomy:
    """The active taxonomy: the first readable policy file, else the
    embedded canonical copy. Never raises on a missing file."""
    for path in paths if paths is not None else DEFAULT_TAXONOMY_PATHS:
        candidate = Path(path)
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            return parse_taxonomy(text, str(candidate))
        except TaxonomyError:
            continue  # malformed override: fall through to the next source
    return parse_taxonomy(_CANONICAL_YAML, "embedded-canonical")


def classify_reason(
    value: Any, note: str | None = None, taxonomy: Taxonomy | None = None
) -> ReasonStamp:
    """Classify one raw reason into a canonical stamp. Fail-closed:

    * a known id or alias stamps that class (with the caller's note);
    * anything else — absent, blank, unrecognised — stamps the default
      class ``other`` and preserves the raw input (or the given note, or
      an explanatory note) as the free-text note.
    """
    taxonomy = taxonomy or load_taxonomy()
    cleaned = note.strip() if isinstance(note, str) and note.strip() else None
    cls: ReasonClass | None = None
    if isinstance(value, str) and value.strip():
        cls = taxonomy.lookup(value)
    if cls is None:
        if isinstance(value, str) and value.strip():
            fallback = cleaned or f"unrecognised reason {value.strip()!r}"
        else:
            fallback = cleaned or "no reason supplied"
        cls = taxonomy.default
        cleaned = fallback
    if cls.requires_note and not cleaned:
        cleaned = "no free-text note supplied for the 'other' class"
    return ReasonStamp(reason=cls.id, note=cleaned)
