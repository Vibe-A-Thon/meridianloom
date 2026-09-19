"""Policy pack bootstrap (D43; N0-T09b–T09e; AC-53).

THE UNIFORM FRESH-WORKSPACE CONTRACT — stated once, for every sidecar-loaded
policy pack (D43's uniformity rule):

Every pack resolves workspace-relative — ``<ws>/.meridian/policy/<file>.yaml``
first, then ``<ws>/policy/<file>.yaml`` — with the shipped default at
``<install>/policy/<file>.yaml`` as the floor. Two behaviours exist, and no
third:

* **Absent everywhere** → the sidecar copies the shipped default into
  ``<ws>/.meridian/policy/`` when the workspace handshake arrives, reports
  every scaffold as a structured warning in server state
  (``health.policyScaffolds``), and the team owns the copy from then on
  (FR-M12-01/FR-M12-12: workspace policy is git-backed and PR-reviewable).
* **Present but invalid** → the pack's loader fails closed, naming the file,
  the schema violation, and the remedy (see :data:`FAIL_CLOSED_REMEDY`).

The scaffold NEVER overwrites: a pack the team created or edited anywhere in
the resolution chain always wins over the shipped default. Loaders keep
their defensive last resorts (the roles built-in default, the taxonomy
embedded canonical, an empty pricing/story pack) for a loader invoked
outside a bootstrapped workspace — they exist only for the case where no
shipped default was packaged, never as a third workspace behaviour.

Zero model calls (FR-M36-07): filesystem copies only.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import meridian_core

__all__ = [
    "FAIL_CLOSED_REMEDY",
    "POLICY_PACKS",
    "PolicyPackSpec",
    "ScaffoldEvent",
    "bootstrap_policy_packs",
    "scaffold_warnings",
    "shipped_policy_dir",
    "workspace_candidates",
]

#: The remedy every fail-closed pack error names (NFR-10; N0-T09e) — the
#: operator is told how to get back to a working state, not only what failed.
FAIL_CLOSED_REMEDY = (
    "Remedy: fix the file, or delete it and restart to re-scaffold "
    "the shipped default."
)


@dataclass(frozen=True)
class PolicyPackSpec:
    """One sidecar-loaded policy pack: its registry key and file name."""

    key: str
    filename: str
    description: str


#: The seven sidecar-loaded packs, in scaffold order. ``acp-permissions.yaml``
#: is deliberately absent: the extension host reads it from the extension
#: directory itself (it ships in the VSIX), it is not sidecar-loaded.
POLICY_PACKS: tuple[PolicyPackSpec, ...] = (
    PolicyPackSpec("governance", "governance.yaml", "the FR-M12-08 general policy pack"),
    PolicyPackSpec("action-classes", "action-classes.yaml", "the D16 action-class catalogue"),
    PolicyPackSpec("roles", "roles.yaml", "the FR-M20-02 role pack"),
    PolicyPackSpec("pricing", "pricing.yaml", "the FR-M39-04 pricing pack"),
    PolicyPackSpec("stories", "stories.yaml", "the FR-M26-03 story-metadata pack"),
    PolicyPackSpec("rework-reasons", "rework-reasons.yaml", "the E-GR-03 rework-reason taxonomy"),
    PolicyPackSpec("licenses", "licenses.yaml", "the FR-M33-02 SPDX license map"),
)


@dataclass(frozen=True)
class ScaffoldEvent:
    """The structured per-pack outcome of one bootstrap run.

    ``action`` is ``"present"`` (a workspace pack won — no copy),
    ``"scaffolded"`` (the shipped default was copied into
    ``<ws>/.meridian/policy/``) or ``"missing-default"`` (no workspace pack
    and no shipped default — a broken install; the warning names it).
    """

    pack: str
    filename: str
    action: str  # "present" | "scaffolded" | "missing-default"
    path: str | None
    message: str

    def as_warning(self) -> str | None:
        """The visible notice for a scaffold (D43), or None when nothing
        happened (the pack was already present)."""
        if self.action == "scaffolded":
            return self.message
        if self.action == "missing-default":
            return self.message
        return None


def shipped_policy_dir() -> Path:
    """The directory holding the shipped default packs: ``policy/`` next to
    the installed ``meridian_core`` (the repository root in development,
    ``extension/policy/`` inside the packaged VSIX — see
    scripts/package-extension.mjs)."""
    return Path(meridian_core.__file__).resolve().parent.parent.parent / "policy"


def workspace_candidates(workspace: str | Path, spec: PolicyPackSpec) -> list[Path]:
    """The workspace-relative resolution chain for one pack: the
    ``.meridian/policy/`` override first, then the workspace ``policy/``
    directory — first readable file wins."""
    root = Path(workspace)
    return [
        root / ".meridian" / "policy" / spec.filename,
        root / "policy" / spec.filename,
    ]


def _readable(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def bootstrap_policy_packs(workspace: str | Path) -> list[ScaffoldEvent]:
    """Run the D43 scaffold for every pack against one workspace.

    For each pack: if a readable file exists anywhere in the workspace
    chain, do nothing (workspace packs always win). Otherwise copy the
    shipped default into ``<ws>/.meridian/policy/`` — creating the directory
    if needed, never overwriting a file that appeared since the check —
    and record a ``"scaffolded"`` event. A pack with neither a workspace
    file nor a shipped default records ``"missing-default"`` so a broken
    install degrades to a visible warning, never a silent hole.
    """
    root = Path(workspace)
    shipped = shipped_policy_dir()
    events: list[ScaffoldEvent] = []
    for spec in POLICY_PACKS:
        for candidate in workspace_candidates(root, spec):
            if _readable(candidate):
                events.append(
                    ScaffoldEvent(
                        pack=spec.key,
                        filename=spec.filename,
                        action="present",
                        path=str(candidate),
                        message=f"{spec.key}: using workspace pack at {candidate}",
                    )
                )
                break
        else:
            default = shipped / spec.filename
            if not _readable(default):
                events.append(
                    ScaffoldEvent(
                        pack=spec.key,
                        filename=spec.filename,
                        action="missing-default",
                        path=None,
                        message=(
                            f"{spec.key}: no workspace pack and no shipped default "
                            f"at {default} — the pack stays unloaded until one "
                            f"appears. {FAIL_CLOSED_REMEDY}"
                        ),
                    )
                )
                continue
            destination = root / ".meridian" / "policy" / spec.filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                # The pack appeared between the chain check and the copy
                # (a concurrent editor or a racing second bootstrap): the
                # workspace file wins, exactly as if it had been there first.
                events.append(
                    ScaffoldEvent(
                        pack=spec.key,
                        filename=spec.filename,
                        action="present",
                        path=str(destination),
                        message=f"{spec.key}: using workspace pack at {destination}",
                    )
                )
                continue
            shutil.copyfile(default, destination)
            events.append(
                ScaffoldEvent(
                    pack=spec.key,
                    filename=spec.filename,
                    action="scaffolded",
                    path=str(destination),
                    message=(
                        f"{spec.key}: scaffolded the shipped default "
                        f"{spec.filename} into {destination} — review and "
                        f"commit it like any team policy (FR-M12-12); delete "
                        f"the file and restart to restore the default."
                    ),
                )
            )
    return events


def scaffold_warnings(events: Sequence[ScaffoldEvent]) -> list[str]:
    """The visible notices (D43) from one bootstrap run — the scaffolded
    and broken-install events, in pack order; ``present`` packs are silent."""
    return [warning for event in events if (warning := event.as_warning())]
