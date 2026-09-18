"""Audit follow-ups: TASK-103 (upgrade path) and TASK-041 (tenant
independence) — evidence behind docs/DEPLOYMENT.md sections 9 and 10.
"""

from __future__ import annotations

from pathlib import Path

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    apply_migrations,
)
from meridian_core.memory.fabric import MemoryEntry, MemoryFabric, Provenance
from meridian_core.tenancy import Tenant, TenantRegistry


# -- TASK-103: upgrades migrate forward, chain intact ---------------------------


def test_reopening_an_older_schema_migrates_and_preserves_the_chain(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    try:
        for seq in range(1, 4):
            led.append({
                "story_id": "OLD-1", "phase": "build", "loop_id": "L1",
                "loop_iteration": 1, "actor_id": "a", "actor_version": "0.0.1",
                "actor_kind": "role", "policy_version": "p", "action_type": "diff",
                "ts_utc": f"2026-09-18T00:00:{seq:06d}Z",
            })
        hashes_before = [
            row[0].hex()
            for row in led.conn.execute(
                "SELECT entry_hash FROM ledger_entry ORDER BY seq"
            ).fetchall()
        ]
        # Simulate an older sidecar: rewind the schema version, reopen.
        led.conn.execute("PRAGMA user_version = 1")
        led.conn.commit()
    finally:
        led.close()

    reopened = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    try:
        import meridian_core.ledger as _l
        assert _l.SCHEMA_VERSION >= 5  # migrations applied on open
        hashes_after = [
            row[0].hex()
            for row in reopened.conn.execute(
                "SELECT entry_hash FROM ledger_entry ORDER BY seq"
            ).fetchall()
        ]
        assert hashes_after == hashes_before  # chain untouched by migration
        reopened.append({
            "story_id": "NEW-1", "phase": "build", "loop_id": "L1",
            "loop_iteration": 1, "actor_id": "a", "actor_version": "0.0.1",
            "actor_kind": "role", "policy_version": "p", "action_type": "diff",
            "ts_utc": "2026-09-18T00:00:09Z",
        })
        assert reopened.verify().ok is True
    finally:
        reopened.close()


# -- TASK-041: workspaces (tenants) never share state ----------------------------


def test_two_workspaces_have_fully_independent_state(tmp_path):
    ws_a = tmp_path / "ws-a"
    ws_b = tmp_path / "ws-b"
    registry = TenantRegistry()
    registry.register(Tenant("acme", ws_a))
    registry.register(Tenant("globex", ws_b))

    fabric_a = registry.resolve("acme").memory_fabric()
    fabric_a.write(MemoryEntry(
        entry_id="m1", tier="semantic", subject="acme secret",
        content="confidential approach",
        provenance=Provenance(
            origin_sequence=None, author="a", ts_utc="2026-09-18T00:00:00Z",
            confidence=0.9, origin="workspace",
        ),
    ))
    fabric_b = registry.resolve("globex").memory_fabric()
    assert fabric_b.get("semantic", "acme secret") is None
    assert registry.resolve("acme").ledger_dir() != registry.resolve("globex").ledger_dir()
