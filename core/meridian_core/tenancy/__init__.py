"""C5 — tenant isolation (SEC-23, D13), story queue (FR-M21-01…03),
multi-repo story spanning (FR-M22-01), documentation gate (FR-M29-01/02).

SEC-23 / D13: Meridian OWNS tenant isolation for IT-services
deployments. A tenant's repositories, memory, ledger, and learned state
are namespaced under one tenant root, and the registry refuses
cross-tenant resolution — there is no code path by which one tenant's
fabric hands another tenant's agent its memory or learned/ state
(R19: cross-tenant leakage is a named critical risk). Model routing is
tenant-scoped: a tenant's calls never inherit another tenant's provider
configuration.

FR-M21-01/02/03: the story queue orders by priority with dependency
ordering and a WIP limit; concurrent stories are isolated by worktree
and never share in-flight agent instances; resource contention
(sandbox slots, budget) is arbitrated by priority with aging-based
starvation prevention — a waiting story's effective priority rises
with wait time, and a starved story is surfaced, never silently stuck.

FR-M22-01: a story may span multiple declared repositories, each with
its own worktree/branch/PR identity.

FR-M29-01/02: the documentation gate — a packet whose blast-radius
class includes a public API change must carry updated documentation;
Review blocks otherwise.

Zero model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from meridian_core.memory.fabric import MemoryFabric


class TenantError(ValueError):
    """A tenancy rule violation. Carries SEC-23."""


@dataclass(frozen=True)
class Tenant:
    """One client tenant: every piece of state lives under its root."""

    tenant_id: str
    root: Path

    def ledger_dir(self) -> Path:
        return self.root / "ledger"

    def memory_fabric(self) -> MemoryFabric:
        return MemoryFabric(self.root / "workspace")

    def adapters_dir(self) -> Path:
        return self.root / "adapters"

    def models_config(self) -> Path:
        return self.root / "models.yaml"


class TenantRegistry:
    """SEC-23 enforcement point. Tenants are registered explicitly;
    resolution is by exact id and nothing else — no path fallback, no
    shared default."""

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def register(self, tenant: Tenant) -> None:
        if tenant.tenant_id in self._tenants:
            raise TenantError(f"duplicate tenant {tenant.tenant_id!r}")
        tenant.root.mkdir(parents=True, exist_ok=True)
        self._tenants[tenant.tenant_id] = tenant

    def resolve(self, tenant_id: str) -> Tenant:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise TenantError(
                f"SEC-23: unknown tenant {tenant_id!r} — no fallback tenant"
                " exists, and one tenant's state is never another's"
            )
        return tenant

    def assert_same_tenant(self, tenant_id: str, path: Path) -> None:
        """A path claimed by a tenant must live under that tenant's
        root. This is the canonical-boundary check (not an OS sandbox —
        SEC-32 honesty): it catches wiring errors, not adversaries with
        shell access."""
        tenant = self.resolve(tenant_id)
        try:
            path.resolve().relative_to(tenant.root.resolve())
        except ValueError:
            raise TenantError(
                f"SEC-23: {path} is outside tenant {tenant_id!r}'s root"
            )


@dataclass(frozen=True)
class RepoTarget:
    """FR-M22-01: one repository target of a multi-repo story."""

    repo_id: str
    worktree: str
    branch: str
    pr_subject: str


@dataclass
class Story:
    story_id: str
    priority: int  # lower = more urgent
    tenant_id: str
    dependencies: tuple[str, ...] = ()
    repos: tuple[RepoTarget, ...] = ()
    enqueued_seq: int = 0
    waited_ticks: int = 0


class StoryQueue:
    """FR-M21-01/02/03: priority + dependency ordering, WIP limit,
    starvation prevention, per-story agent instances."""

    def __init__(
        self,
        *,
        wip_limit: int = 3,
        aging_every: int = 5,
        starvation_threshold: int = 20,
    ) -> None:
        self._wip_limit = wip_limit
        self._aging_every = aging_every
        self._starvation_threshold = starvation_threshold
        self._waiting: list[Story] = []
        self._in_flight: dict[str, Story] = {}
        self._done: set[str] = set()
        self._counter = 0
        self._agent_bindings: dict[str, str] = {}

    def enqueue(self, story: Story) -> None:
        self._counter += 1
        story.enqueued_seq = self._counter
        self._waiting.append(story)

    def _dependencies_met(self, story: Story) -> bool:
        return all(dep in self._done for dep in story.dependencies)

    def _effective_priority(self, story: Story) -> tuple[int, int]:
        """Priority with aging: every ``aging_every`` ticks of waiting
        lowers the effective priority value by one (more urgent)."""
        age_bonus = story.waited_ticks // self._aging_every
        return (story.priority - age_bonus, story.enqueued_seq)

    def tick(self) -> list[Story]:
        """One scheduling tick: admit what fits, age the rest. Returns
        newly admitted stories. Starved stories raise — surfacing is the
        starvation prevention, not silent priority fiddling."""
        admitted: list[Story] = []
        ready = [s for s in self._waiting if self._dependencies_met(s)]
        ready.sort(key=self._effective_priority)
        for story in ready:
            if len(self._in_flight) >= self._wip_limit:
                break
            if story.story_id in self._in_flight:
                continue
            self._waiting.remove(story)
            self._in_flight[story.story_id] = story
            admitted.append(story)
        for story in self._waiting:
            story.waited_ticks += 1
            if story.waited_ticks >= self._starvation_threshold:
                raise TenantError(
                    f"FR-M21-03: story {story.story_id!r} has waited"
                    f" {story.waited_ticks} ticks — starved; surface it,"
                    " do not let it rot"
                )
        return admitted

    def complete(self, story_id: str) -> None:
        del self._in_flight[story_id]
        self._done.add(story_id)

    def bind_agent(self, story_id: str, agent_instance: str) -> None:
        """FR-M21-02: in-flight agent instances are never shared across
        concurrent stories."""
        if agent_instance in self._agent_bindings.values():
            holder = next(
                s for s, a in self._agent_bindings.items() if a == agent_instance
            )
            raise TenantError(
                f"FR-M21-02: agent instance {agent_instance!r} is already"
                f" bound to story {holder!r}; concurrent stories do not"
                " share in-flight agents"
            )
        self._agent_bindings[story_id] = agent_instance

    def release_agent(self, story_id: str) -> None:
        self._agent_bindings.pop(story_id, None)


PUBLIC_API_CLASSES = ("public_api_contract_change",)


def documentation_gate(*, change_class: str, docs_updated: bool) -> Mapping[str, Any]:
    """FR-M29-02: public API changes without updated documentation
    BLOCK Review. Other classes pass with documentation recorded as
    unchanged."""
    if change_class in PUBLIC_API_CLASSES and not docs_updated:
        return {
            "gate": "review",
            "passed": False,
            "reason": (
                "FR-M29-02: public API change without updated documentation"
                " — API docs, README, changelog, and runbooks must reflect"
                " the change before Review"
            ),
        }
    return {"gate": "review", "passed": True, "reason": "documentation satisfied"}
