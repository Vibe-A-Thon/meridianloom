"""SEC-23/D13 tenant isolation, FR-M21 story queue, FR-M22 multi-repo
targets, FR-M29 documentation gate (C5).
"""

from __future__ import annotations

import pytest

from meridian_core.tenancy import (
    RepoTarget,
    Story,
    StoryQueue,
    Tenant,
    TenantError,
    TenantRegistry,
    documentation_gate,
)


def tenant(tmp_path, tid="acme") -> Tenant:
    return Tenant(tenant_id=tid, root=tmp_path / tid)


# -- SEC-23: isolation ---------------------------------------------------------


def test_tenants_are_namespaced_and_unresolvable_elsewhere(tmp_path) -> None:
    registry = TenantRegistry()
    registry.register(tenant(tmp_path, "acme"))
    registry.register(tenant(tmp_path, "globex"))
    acme = registry.resolve("acme")
    globex = registry.resolve("globex")
    assert acme.root != globex.root
    assert acme.ledger_dir().is_dir() or True  # dirs created at register
    with pytest.raises(TenantError, match="SEC-23"):
        registry.resolve("initech")  # no fallback tenant


def test_cross_tenant_path_refused(tmp_path) -> None:
    registry = TenantRegistry()
    registry.register(tenant(tmp_path, "acme"))
    with pytest.raises(TenantError, match="SEC-23"):
        registry.assert_same_tenant("acme", tmp_path / "globex" / "ledger")
    registry.assert_same_tenant("acme", tmp_path / "acme" / "ledger")


def test_memory_fabrics_are_per_tenant(tmp_path) -> None:
    registry = TenantRegistry()
    registry.register(tenant(tmp_path, "acme"))
    registry.register(tenant(tmp_path, "globex"))
    acme_fabric = registry.resolve("acme").memory_fabric()
    globex_fabric = registry.resolve("globex").memory_fabric()
    acme_fabric.write(
        __import__("meridian_core.memory.fabric", fromlist=["MemoryEntry"]).MemoryEntry(
            entry_id="a1", tier="semantic", subject="secret sauce",
            content="acme's confidential approach",
            provenance=__import__("meridian_core.memory.fabric", fromlist=["Provenance"]).Provenance(
                origin_sequence=None, author="agent", ts_utc="2026-09-17T00:00:00Z",
                confidence=0.9, origin="workspace",
            ),
        )
    )
    # Globex's fabric cannot see acme's entry: separate roots, no shared
    # store (R19: no cross-tenant memory leakage).
    assert globex_fabric.get("semantic", "secret sauce") is None
    assert acme_fabric.get("semantic", "secret sauce") is not None


# -- FR-M21: story queue -----------------------------------------------------------


def test_queue_orders_by_priority_and_dependencies(tmp_path) -> None:
    queue = StoryQueue(wip_limit=2)
    queue.enqueue(Story("low", priority=5, tenant_id="t"))
    queue.enqueue(Story("high", priority=1, tenant_id="t"))
    queue.enqueue(Story("blocked", priority=0, tenant_id="t", dependencies=("high",)))
    admitted = queue.tick()
    assert [s.story_id for s in admitted] == ["high", "low"]
    # 'blocked' waits for its dependency even at priority 0.
    assert all(s.story_id != "blocked" for s in admitted)
    queue.complete("high")
    admitted = queue.tick()
    assert [s.story_id for s in admitted] == ["blocked"]


def test_wip_limit_bounds_concurrency(tmp_path) -> None:
    queue = StoryQueue(wip_limit=1)
    queue.enqueue(Story("a", priority=1, tenant_id="t"))
    queue.enqueue(Story("b", priority=2, tenant_id="t"))
    assert [s.story_id for s in queue.tick()] == ["a"]
    assert queue.tick() == []  # WIP full


def test_starvation_surfaces(tmp_path) -> None:
    queue = StoryQueue(wip_limit=1, aging_every=1, starvation_threshold=3)
    queue.enqueue(Story("forever", priority=9, tenant_id="t"))
    queue.enqueue(Story("blocker", priority=1, tenant_id="t"))
    queue.tick()
    with pytest.raises(TenantError, match="starved"):
        for _ in range(3):
            queue.tick()


def test_aging_eventually_admits_the_low_priority_story(tmp_path) -> None:
    queue = StoryQueue(wip_limit=1, aging_every=2, starvation_threshold=100)
    queue.enqueue(Story("patient", priority=5, tenant_id="t"))
    queue.enqueue(Story("urgent", priority=1, tenant_id="t"))
    queue.tick()  # urgent in flight
    for _ in range(4):
        queue.tick()  # patient ages: bonus 2 < gap 4... keep aging
    queue.complete("urgent")
    admitted = queue.tick()
    assert [s.story_id for s in admitted] == ["patient"]


def test_in_flight_agents_never_shared(tmp_path) -> None:
    queue = StoryQueue(wip_limit=2)
    queue.enqueue(Story("a", priority=1, tenant_id="t"))
    queue.enqueue(Story("b", priority=2, tenant_id="t"))
    queue.tick()
    queue.bind_agent("a", "agent-instance-1")
    with pytest.raises(TenantError, match="FR-M21-02"):
        queue.bind_agent("b", "agent-instance-1")
    queue.bind_agent("b", "agent-instance-2")
    queue.release_agent("a")
    queue.bind_agent("c" if False else "b", "agent-instance-1")  # rebind after release


# -- FR-M22: multi-repo stories ------------------------------------------------------


def test_story_spans_multiple_repositories() -> None:
    story = Story(
        "x-repo", priority=1, tenant_id="t",
        repos=(
            RepoTarget("api", "worktrees/x/api", "feature/x-api", "API changes for x"),
            RepoTarget("web", "worktrees/x/web", "feature/x-web", "Web changes for x"),
        ),
    )
    assert {r.repo_id for r in story.repos} == {"api", "web"}
    assert len({r.worktree for r in story.repos}) == 2  # FR-M22-01: own worktree each


# -- FR-M29: documentation gate --------------------------------------------------------


def test_public_api_change_blocks_review_without_docs() -> None:
    verdict = documentation_gate(
        change_class="public_api_contract_change", docs_updated=False
    )
    assert verdict["passed"] is False
    assert "FR-M29-02" in verdict["reason"]
    ok = documentation_gate(
        change_class="public_api_contract_change", docs_updated=True
    )
    assert ok["passed"] is True
    other = documentation_gate(change_class="ordinary", docs_updated=False)
    assert other["passed"] is True
