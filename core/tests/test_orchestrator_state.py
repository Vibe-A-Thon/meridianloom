"""TASK-320: orchestrator state survives a sidecar restart."""

from __future__ import annotations

from meridian_core.orchestra_handlers import PROGRESS_SCHEMA, OrchestraState


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


def test_resume_after_restart_completes(tmp_path):
    """GP-009: the audit's reproduction — start, persist, NEW state (fresh
    runner), resume — must complete, not die on an uninitialised schema."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from meridian_core.runtime import (
        GateSuspend,
        LangGraphLoopRunner,
        canonical_loops,
    )

    ws = tmp_path / "ws"
    ws.mkdir()
    server = _FakeServer(ws)
    orch = OrchestraState(server)
    ledger = server._ensure_ledger()
    definition = canonical_loops()["L2"]

    def build(ctx):
        if not ctx.state.get("progress"):
            return {"progress": ("build", ["built"])}
        return {}

    def review(ctx):
        if not ctx.state.get("approved"):
            raise GateSuspend(gate="human-approval", awaiting="decision")
        return {}

    def verify(ctx):
        return {}

    conn = sqlite3.connect(ws / "cp.db", check_same_thread=False)
    runner = LangGraphLoopRunner(SqliteSaver(conn), ledger=ledger)
    runner.with_exit_check(definition, lambda state: state.get("approved") is True)
    orch._runner = runner
    handle = runner.start(
        definition, {"build": build, "review": review, "verify": verify},
        PROGRESS_SCHEMA, story_id="RES-1",
    )
    assert handle.result["status"] == "suspended"
    orch._handles["L2"] = handle
    orch.persist()

    # Fresh process: new state, runner rebuilt — handles restored from disk.
    fresh = OrchestraState(_FakeServer(ws))
    assert "L2" in fresh._handles
    restored = fresh._handles["L2"]
    fresh._runner = LangGraphLoopRunner(SqliteSaver(conn), ledger=ledger)
    fresh._runner.with_exit_check(definition, lambda state: state.get("approved") is True)

    def review_pass(ctx):
        return {"approved": ("review", True)}

    fresh._runner._local.nodes = {"build": build, "review": review_pass, "verify": verify}
    fresh._runner._local.schemas = dict(PROGRESS_SCHEMA)
    snapshot = dict(restored.state_snapshot)
    snapshot["approved"] = True
    restored.state_snapshot = snapshot
    finished = fresh._runner.resume(restored)
    assert finished.result["status"] == "completed"
    conn.close()
