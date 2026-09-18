"""TASK-320: orchestrator state survives a sidecar restart."""

from __future__ import annotations

from meridian_core.orchestra_handlers import OrchestraState


class _FakeServer:
    def __init__(self, workspace):
        self._workspace_dir = str(workspace)
        self._ledger = None

    def _ensure_ledger(self):
        from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
        if self._ledger is None:
            import pathlib
            self._ledger = Ledger(
                pathlib.Path(self._workspace_dir) / ".meridian" / "ledger",
                EphemeralSigningKeyProvider(),
            )
        return self._ledger


def test_state_persists_across_restart(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    first = OrchestraState(_FakeServer(workspace))
    first._tenants.register(__import__(
        "meridian_core.tenancy", fromlist=["Tenant"]).Tenant("acme", workspace / "t"))
    first._queue.enqueue(__import__(
        "meridian_core.tenancy", fromlist=["Story"]).Story("S1", 1, "acme"))
    first.persist()
    first.shutdown()

    second = OrchestraState(_FakeServer(workspace))  # restores on init
    tenants = second._tenants._tenants
    assert "acme" in tenants
    assert [s.story_id for s in second._queue._waiting] == ["S1"]
    assert second._state_path.is_file()
    second.shutdown()
