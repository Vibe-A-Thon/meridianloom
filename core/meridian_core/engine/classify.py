"""Dependency, license and migration-reversibility classifier (FR-M33-02).

Parses dependency manifests — Gradle ``build.gradle`` (groovy), npm
``package.json`` and Python ``requirements.txt`` (the ecosystems the
samples use) — into dependency records (name, version, ecosystem).
License classification looks each dependency up in the PINNED
SPDX-identifier map, a policy YAML resolved by the same override chain
as the other packs (D43; stated once in ``governance/bootstrap.py``):
``<ws>/.meridian/policy/licenses.yaml`` overrides, then
``<ws>/policy/licenses.yaml``, then the shipped default at
``<install>/policy/licenses.yaml`` — first readable file wins. An
explicit ``license_map_path`` on the payload still wins outright over
the whole chain (config, never hard-coded here); a ``workspaceDir``
payload param scopes the workspace-relative candidates. A dependency
with no map entry reports license ``unknown`` — never guessed, and a
malformed map fails closed naming the file, the violation and the
remedy (fix the file, or delete it and restart to re-scaffold the
shipped default).

Migration-reversibility is a heuristic classification over dependency +
file evidence: a known data-migration tool (flyway, liquibase, alembic,
…) or migration-layout files (``migrations/``, ``db/changelog``, …) in
the manifest's tree mark the change as ``data_migration``; otherwise it
is ``code_only``. Every classification is confidence-labelled
(``high``/``medium``/``low``) and carries the evidence that fired.

Zero model calls: line-oriented parsing, JSON, and table lookups.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..governance.bootstrap import FAIL_CLOSED_REMEDY, shipped_policy_dir
from .capabilities import CapabilityOutcome

__all__ = ["MigrationClassifierCapability"]

_CAPABILITY_NAME = "migration_classifier"

#: Ecosystems this capability parses (the samples' ecosystems).
_ECOSYSTEMS = ("gradle", "npm", "python")

#: Dependencies that are data-migration tooling by name (lowercased match
#: on the dependency name or its last coordinate segment).
_MIGRATION_TOOLS = (
    "flyway",
    "liquibase",
    "alembic",
    "prisma",
    "knex",
    "typeorm",
    "sequelize-cli",
    "migrate",
)

#: File/directory layout evidence of data migration (lowercased substring
#: match on path parts relative to the manifest).
_MIGRATION_LAYOUT = (
    "migration",
    "migrations",
    "changelog",
    "db/migrate",
)


@dataclass(frozen=True)
class DependencyRecord:
    """One parsed dependency."""

    name: str
    version: str | None
    ecosystem: str
    license: str  # SPDX id, or "unknown" — never guessed
    license_source: str  # "policy-map:<path>" or "unmapped"


@dataclass
class LicenseMap:
    """The pinned SPDX map, fail-closed like the other policy packs."""

    source: str
    licenses: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    def lookup(self, name: str) -> str | None:
        if self.errors:
            return None
        return self.licenses.get(name) or self.licenses.get(name.lower())


def repo_default_license_map() -> Path:
    """The shipped default license map (repo ``policy/`` in development,
    ``extension/policy/`` inside the packaged VSIX)."""
    return shipped_policy_dir() / "licenses.yaml"


def default_license_map_paths(workspace: str | Path | None = None) -> list[Path]:
    """The license-map override chain, the same convention as the other
    policy packs: the workspace ``.meridian/policy/`` override, then the
    workspace ``policy/`` directory, then the shipped default. First
    readable file wins. ``workspace`` None (no handshake context) leaves
    just the shipped default."""
    paths: list[Path] = []
    if workspace is not None:
        root = Path(workspace)
        paths.append(root / ".meridian" / "policy" / "licenses.yaml")
        paths.append(root / "policy" / "licenses.yaml")
    paths.append(repo_default_license_map())
    return paths


def parse_license_map(text: str, source: str) -> LicenseMap:
    """Parse one license-map document. Never raises on content: a broken
    document fails closed naming the violation and the remedy (every
    lookup unknown, never a guess)."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return LicenseMap(
            source=source, errors=[f"{source}: not valid YAML: {error}", FAIL_CLOSED_REMEDY]
        )
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return LicenseMap(
            source=source, errors=[f"{source}: must be a mapping", FAIL_CLOSED_REMEDY]
        )
    version = raw.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        return LicenseMap(
            source=source,
            errors=[f"{source}: version must be an integer >= 1", FAIL_CLOSED_REMEDY],
        )
    licenses = raw.get("licenses")
    if not isinstance(licenses, Mapping):
        return LicenseMap(
            source=source, errors=[f"{source}: 'licenses' must be a mapping", FAIL_CLOSED_REMEDY]
        )
    clean: dict[str, str] = {}
    for name, spdx in licenses.items():
        if not isinstance(name, str) or not isinstance(spdx, str) or not name.strip() or not spdx.strip():
            return LicenseMap(
                source=source,
                errors=[
                    f"{source}: license entries must be non-empty name → SPDX string pairs",
                    FAIL_CLOSED_REMEDY,
                ],
            )
        clean[name.strip()] = spdx.strip()
        clean.setdefault(name.strip().lower(), spdx.strip())
    return LicenseMap(source=source, licenses=clean)


def load_license_map(path: str | Path | Sequence[str | Path] | None) -> LicenseMap:
    """Load the license map. A single path loads exactly that file; a
    sequence is the override chain — the first readable file wins. A
    missing/unreadable file (or chain with no readable candidate) fails
    closed naming what was tried and the remedy, never an exception."""
    if path is None:
        candidates: list[Path] = default_license_map_paths()
    elif isinstance(path, (str, Path)):
        candidates = [Path(path)]
    else:
        candidates = [Path(candidate) for candidate in path]
    tried: list[str] = []
    for candidate in candidates:
        tried.append(str(candidate))
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError as error:
            if len(candidates) == 1:
                return LicenseMap(
                    source=str(candidate),
                    errors=[f"{candidate}: unreadable: {error}", FAIL_CLOSED_REMEDY],
                )
            continue
        return parse_license_map(text, str(candidate))
    return LicenseMap(
        source="licenses.yaml",
        errors=[
            "no license map found (tried: " + ", ".join(tried) + ")",
            FAIL_CLOSED_REMEDY,
        ],
    )


def detect_ecosystem(path: Path) -> str | None:
    """The ecosystem of a manifest file, by its name."""
    name = path.name.lower()
    if name in ("build.gradle", "build.gradle.kts"):
        return "gradle"
    if name == "package.json":
        return "npm"
    if name.endswith("requirements.txt") or name == "requirements.txt":
        return "python"
    return None


#: Gradle dependency coordinates: implementation 'group:name:version'.
_GRADLE_COORD = re.compile(
    r"""^\s*(?:testImplementation|implementation|api|compileOnly|runtimeOnly|
    annotationProcessor|classpath)\s*[\s(]*['"]([^'":\s]+):([^'":\s]+)(?::([^'"\s)]+))?['"]""",
    re.VERBOSE,
)

#: requirements.txt lines: name, name==version, name>=version, name~=x.y.
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:==|>=|<=|~=|>|<)?\s*([A-Za-z0-9.*+!._-]+)?\s*(?:#.*)?$")


def parse_gradle(text: str) -> list[tuple[str, str | None]]:
    records: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        match = _GRADLE_COORD.match(line)
        if match:
            records.append((f"{match.group(1)}:{match.group(2)}", match.group(3)))
    return records


def parse_package_json(text: str) -> "list[tuple[str, str | None]] | str":
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        return f"not valid JSON: {error}"
    if not isinstance(raw, Mapping):
        return "must be a JSON object"
    records: list[tuple[str, str | None]] = []
    for section in ("dependencies", "devDependencies"):
        deps = raw.get(section, {})
        if not isinstance(deps, Mapping):
            return f"'{section}' must be an object"
        for name, spec in deps.items():
            records.append((str(name), str(spec) if isinstance(spec, str) else None))
    return records


def parse_requirements(text: str) -> list[tuple[str, str | None]]:
    records: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = _REQUIREMENT.match(line)
        if match and match.group(1):
            records.append((match.group(1), match.group(2)))
    return records


def _migration_evidence(manifest: Path, dependencies: Sequence[DependencyRecord]) -> list[str]:
    """Dependency + file evidence that a change touching this manifest is
    a data migration rather than code-only."""
    evidence: list[str] = []
    for record in dependencies:
        lowered = record.name.lower()
        last_segment = lowered.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
        if any(tool in lowered or tool == last_segment for tool in _MIGRATION_TOOLS):
            evidence.append(f"dependency '{record.name}' is data-migration tooling")
    root = manifest.parent
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root)).lower().replace("\\", "/")
            if any(marker in relative for marker in _MIGRATION_LAYOUT):
                evidence.append(f"file layout '{path.relative_to(root)}' is migration-shaped")
    return evidence


class MigrationClassifierCapability:
    """The ``migration_classifier`` capability, owned by the
    ``classify_migration`` action class (FR-M33-01).

    Payload: ``{path}`` — a manifest file or a directory to scan for
    manifests; optional ``license_map_path`` overrides the whole override
    chain; optional ``workspaceDir`` scopes the workspace-relative chain
    (``.meridian/policy/licenses.yaml``, ``policy/licenses.yaml``, shipped
    default) used when no explicit map path is given.
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        raw_path = action.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return CapabilityOutcome(handled=False, reason="missing 'path'")
        target = Path(raw_path)
        if not target.exists():
            return CapabilityOutcome(handled=False, reason=f"manifest path does not exist: {target}")

        map_path = action.get("license_map_path")
        workspace = action.get("workspaceDir") or action.get("workspace")
        license_map = (
            load_license_map(map_path)
            if isinstance(map_path, str) and map_path
            else load_license_map(default_license_map_paths(workspace))
        )
        if license_map.fail_closed:
            return CapabilityOutcome(
                handled=False,
                reason=f"license map fail-closed: {'; '.join(license_map.errors)}",
            )

        manifests = (
            [target]
            if target.is_file() and detect_ecosystem(target) is not None
            else sorted(
                p for p in target.rglob("*") if p.is_file() and detect_ecosystem(p) is not None
            )
            if target.is_dir()
            else []
        )
        if not manifests:
            return CapabilityOutcome(
                handled=False, reason=f"no supported manifest (gradle/package.json/requirements.txt) under {target}"
            )

        parsed: list[dict[str, Any]] = []
        all_records: list[DependencyRecord] = []
        for manifest in manifests:
            ecosystem = detect_ecosystem(manifest)
            assert ecosystem is not None  # filtered above
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                return CapabilityOutcome(handled=False, reason=f"cannot read {manifest}: {error}")
            raw_records: "list[tuple[str, str | None]] | str"
            if ecosystem == "gradle":
                raw_records = parse_gradle(text)
            elif ecosystem == "npm":
                raw_records = parse_package_json(text)
            else:
                raw_records = parse_requirements(text)
            if isinstance(raw_records, str):
                return CapabilityOutcome(
                    handled=False, reason=f"{manifest.name}: {raw_records}"
                )
            records: list[DependencyRecord] = []
            for name, version in raw_records:
                spdx = license_map.lookup(name)
                records.append(
                    DependencyRecord(
                        name=name,
                        version=version,
                        ecosystem=ecosystem,
                        license=spdx or "unknown",
                        license_source=(
                            f"policy-map:{license_map.source}" if spdx is not None else "unmapped"
                        ),
                    )
                )
            all_records.extend(records)
            parsed.append(
                {
                    "manifest": str(manifest),
                    "ecosystem": ecosystem,
                    "dependencies": [record.__dict__ for record in records],
                }
            )

        evidence = [e for m in manifests for e in _migration_evidence(m, all_records)]
        if evidence:
            classification = "data_migration"
            confidence = "high" if any(e.startswith("dependency") for e in evidence) else "medium"
        else:
            classification = "code_only"
            confidence = "medium"  # a heuristic absence, not proof

        return CapabilityOutcome(
            handled=True,
            result={
                "manifests": parsed,
                "reversibility": {
                    "classification": classification,
                    "confidence": confidence,
                    "evidence": evidence,
                },
            },
            reason=f"classified {len(all_records)} dependencies across {len(manifests)} manifest(s) "
            f"(FR-M33-02)",
        )
