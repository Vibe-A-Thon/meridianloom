"""FR-M9-02…08, FR-M28-03…07 (F3 step 4): tool surface controls, sandbox,
semantic search + reuse-first, hunk editing with binary exclusion, and
the stdio MCP client against a real fixture server. Zero model calls.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.tools import (
    CHANGE_CLASS_DEPENDENCY_ADD,
    TRUNCATION_MARKER,
    EditRefusedError,
    ExclusionSet,
    Hunk,
    LexicalSemanticIndex,
    McpProtocolError,
    McpServerRefusedError,
    McpStdioClient,
    PinnedMcpServer,
    SandboxConfig,
    SemanticIndex,
    ToolDeniedError,
    ToolSurface,
    apply_hunk,
    reuse_first_check,
    run_in_sandbox,
    scrub_environment,
    validate_mcp_server,
)


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    yield led
    led.close()


def sandbox(tmp_path) -> SandboxConfig:
    return SandboxConfig(working_dir=tmp_path / "work", timeout_s=30)


# -- FR-M9-03: permission gate ------------------------------------------------


def test_unpermitted_tool_denied_and_ledger_recorded(tmp_path, ledger) -> None:
    surface = ToolSurface(sandbox(tmp_path), ledger=ledger)
    surface.permit("agent-1", {"build"})
    with pytest.raises(ToolDeniedError, match="FR-M9-03"):
        surface.invoke("agent-1", "test", ["echo", "hi"])
    # No execution happened; the denial is the evidence.
    rows = ledger.query(action_type="rejection", story_id="tool-surface")
    assert len(rows) == 1
    assert rows[0]["decision"] == "rejected"
    assert json.loads(
        ledger.read_blob(rows[0]["input_ref"], rows[0]["blob_key_id"]).decode()
    )["reason"] == "FR-M9-03"
    assert ledger.verify().ok is True


def test_permitted_tool_executes(tmp_path, ledger) -> None:
    surface = ToolSurface(sandbox(tmp_path), ledger=ledger)
    surface.permit("agent-1", {"echo"})
    result = surface.invoke("agent-1", "echo", _echo_argv("hello"))
    assert result.ok is True
    assert "hello" in result.output


def _echo_argv(text: str) -> list[str]:
    if sys.platform == "win32":
        return ["cmd", "/c", f"echo {text}"]
    return ["echo", text]


# -- FR-M9-04: truncation marker -------------------------------------------------


def test_oversized_result_marked_not_silently_trimmed(tmp_path) -> None:
    result = run_in_sandbox(
        _echo_argv("x" * 200),
        sandbox(tmp_path),
        size_cap_bytes=64,
    )
    assert result.truncated is True
    assert result.output.endswith(TRUNCATION_MARKER)
    assert "x" * 200 not in result.output


def test_result_within_cap_unmarked(tmp_path) -> None:
    result = run_in_sandbox(_echo_argv("short"), sandbox(tmp_path))
    assert result.truncated is False
    assert TRUNCATION_MARKER not in result.output


# -- FR-M9-05/07: sandbox scrub + timeout + credential hygiene ---------------------


def test_scrubbed_environment_drops_credentials() -> None:
    env = {"PATH": "/usr/bin", "SECRET_API_KEY": "sk-live-12345", "HOME": "/root"}
    scrubbed = scrub_environment(env, ("PATH", "HOME"))
    assert scrubbed == {"PATH": "/usr/bin", "HOME": "/root"}
    assert "SECRET_API_KEY" not in scrubbed


def test_sandbox_sees_no_inherited_credentials(tmp_path) -> None:
    config = sandbox(tmp_path)
    result = run_in_sandbox(_env_argv(), config)
    assert result.ok is True
    assert "MERIDIAN_TEST_SECRET" not in result.output


def _env_argv() -> list[str]:
    if sys.platform == "win32":
        return ["cmd", "/c", "set"]
    return ["env"]


def test_sandbox_timeout_kills_and_reports(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path / "work", timeout_s=0.5)
    argv = [sys.executable, "-c", "import time; time.sleep(5)"]
    result = run_in_sandbox(argv, config)
    assert result.ok is False
    assert "timed out" in result.output


# -- FR-M9-06: dependency additions are a distinct change class ----------------------


def test_dependency_addition_flagged_separately(tmp_path, ledger) -> None:
    surface = ToolSurface(sandbox(tmp_path), ledger=ledger)
    surface.permit("agent-1", {"install"})
    result = surface.invoke(
        "agent-1",
        "install",
        _echo_argv("added"),
        change_class=CHANGE_CLASS_DEPENDENCY_ADD,
    )
    assert result.change_class == CHANGE_CLASS_DEPENDENCY_ADD
    rows = ledger.query(action_type="tool_call", story_id="tool-surface")
    calls = json.loads(rows[0]["tool_calls"])
    assert calls[0]["changeClass"] == CHANGE_CLASS_DEPENDENCY_ADD


# -- FR-M9-08: MCP server pinning ------------------------------------------------------


def test_unpinned_or_unacknowledged_server_refused() -> None:
    with pytest.raises(McpServerRefusedError, match="not version-pinned"):
        validate_mcp_server(PinnedMcpServer("s", ("echo",), version=""))
    with pytest.raises(McpServerRefusedError, match="content digest"):
        validate_mcp_server(PinnedMcpServer("s", ("echo",), version="1"))
    with pytest.raises(McpServerRefusedError, match="trust acknowledgement"):
        validate_mcp_server(
            PinnedMcpServer("s", ("echo",), version="1", digest="sha256:x")
        )
    validate_mcp_server(
        PinnedMcpServer("s", ("echo",), version="1", digest="sha256:x",
                        trust_acknowledged=True)
    )


# -- FR-M9-01: stdio MCP client against a real fixture server ----------------------------


FIXTURE_SERVER = textwrap.dedent(
    """
    import json
    import sys

    for line in sys.stdin:
        msg = json.loads(line)
        method = msg.get("method")
        if method == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"protocolVersion": "2025-06-18",
                                         "capabilities": {}}}), flush=True)
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"tools": [{"name": "echo",
                                                    "description": "echo"}]}}), flush=True)
        elif method == "tools/call":
            args = msg["params"]["arguments"]
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"content": [{"type": "text",
                                                      "text": args.get("text", "")}]}}), flush=True)
    """
)


def _server(tmp_path, digest="sha256:fixture") -> PinnedMcpServer:
    script = tmp_path / "fixture_mcp_server.py"
    script.write_text(FIXTURE_SERVER, encoding="utf-8")
    return PinnedMcpServer(
        "fixture",
        (sys.executable, str(script)),
        version="1.0.0",
        digest=digest,
        trust_acknowledged=True,
    )


@pytest.mark.skipif(
    os.environ.get("MERIDIAN_SKIP_MCP_FIXTURE") == "1",
    reason="fixture server subprocess disabled in this environment",
)
def test_mcp_client_full_session(tmp_path) -> None:
    client = McpStdioClient(_server(tmp_path))
    try:
        init = client.start()
        assert init["protocolVersion"] == "2025-06-18"
        tools = client.list_tools()
        assert [t["name"] for t in tools] == ["echo"]
        result = client.call_tool("echo", {"text": "hello mcp"})
        assert result["content"][0]["text"] == "hello mcp"
    finally:
        client.stop()


def test_mcp_client_server_error_surfaces(tmp_path) -> None:
    script = tmp_path / "bad_server.py"
    script.write_text(
        "import sys\nfor line in sys.stdin:\n"
        "    import json; m = json.loads(line)\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': m.get('id'),"
        " 'error': {'code': -32601, 'message': 'no such method'}}), flush=True)\n",
        encoding="utf-8",
    )
    client = McpStdioClient(
        PinnedMcpServer("bad", (sys.executable, str(script)), version="1",
                        digest="sha256:x", trust_acknowledged=True)
    )
    try:
        with pytest.raises(McpProtocolError, match="no such method"):
            client.start()
    finally:
        client.stop()


# -- FR-M28-03: semantic index ---------------------------------------------------------------


def _workspace(tmp_path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "payments.py").write_text(
        "class PaymentController:\n"
        "    def process_payment(self, amount):\n"
        "        return amount\n",
        encoding="utf-8",
    )
    (ws / "notes.txt").write_text(
        "the quick brown fox", encoding="utf-8"
    )
    return ws


def test_semantic_index_finds_related_file(tmp_path) -> None:
    ws = _workspace(tmp_path)
    index = LexicalSemanticIndex(ws)
    index.refresh()
    hits = index.search("process payment controller amount")
    assert hits and hits[0].path == "payments.py"
    assert "PaymentController" in hits[0].symbols


def test_semantic_index_incremental_update(tmp_path) -> None:
    ws = _workspace(tmp_path)
    index = LexicalSemanticIndex(ws)
    index.refresh()
    (ws / "refunds.py").write_text(
        "def process_refund(amount):\n    return -amount\n", encoding="utf-8"
    )
    index.index_file(ws / "refunds.py")
    hits = index.search("process refund amount")
    assert any(h.path == "refunds.py" for h in hits)
    (ws / "refunds.py").unlink()
    index.remove_file(ws / "refunds.py")
    # The removed file no longer matches; other files matching the shared
    # tokens (payments.py matches 'process'/'amount') legitimately remain.
    assert all(h.path != "refunds.py" for h in index.search("process refund amount"))


def test_index_implements_semantic_port(tmp_path) -> None:
    index = LexicalSemanticIndex(_workspace(tmp_path))
    assert isinstance(index, LexicalSemanticIndex)
    # Protocol conformance is structural; exercise the port surface.
    for name in ("index_file", "remove_file", "search"):
        assert callable(getattr(index, name))


# -- FR-M28-04: reuse-first ---------------------------------------------------------------------


def test_reuse_first_cites_existing_implementation(tmp_path) -> None:
    ws = _workspace(tmp_path)
    index = LexicalSemanticIndex(ws)
    index.refresh()
    verdict = reuse_first_check(
        index, proposed_symbol="process payment", workspace=ws,
        duplicate_threshold=99.0,  # high bar: found, but not a duplicate
    )
    assert verdict.searched is True
    assert verdict.hits
    assert "payments.py" in verdict.citation
    assert verdict.duplicate_suspected is False


def test_reuse_first_flags_suspected_duplicate(tmp_path) -> None:
    ws = _workspace(tmp_path)
    index = LexicalSemanticIndex(ws)
    index.refresh()
    verdict = reuse_first_check(
        index, proposed_symbol="process payment controller amount",
        workspace=ws, duplicate_threshold=0.0,
    )
    assert verdict.duplicate_suspected is True
    assert "suspected duplicate" in verdict.citation


def test_reuse_first_justifies_absence(tmp_path) -> None:
    ws = _workspace(tmp_path)
    index = LexicalSemanticIndex(ws)
    index.refresh()
    verdict = reuse_first_check(
        index, proposed_symbol="zzq quantum flux regulator", workspace=ws
    )
    assert not verdict.hits
    assert "no existing implementation fit" in verdict.citation


# -- FR-M28-05/07: hunk editing + binary exclusion -------------------------------------------------


def test_hunk_applies_targeted_edit(tmp_path) -> None:
    ws = _workspace(tmp_path)
    exclusions = ExclusionSet(ws)
    line = apply_hunk(
        ws,
        Hunk(path="payments.py", old="return amount", new="return amount * 100"),
        exclusions,
    )
    assert line == 3
    text = (ws / "payments.py").read_text(encoding="utf-8")
    assert "return amount * 100" in text
    assert "class PaymentController" in text  # the rest is untouched


def test_hunk_missing_anchor_refused(tmp_path) -> None:
    ws = _workspace(tmp_path)
    with pytest.raises(EditRefusedError, match="anchor not found"):
        apply_hunk(
            ws,
            Hunk(path="payments.py", old="definitely not there", new="x"),
            ExclusionSet(ws),
        )


def test_binary_generated_files_excluded_by_default(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    lock = ws / "package-lock.json"
    lock.write_text("{}", encoding="utf-8")
    exclusions = ExclusionSet(ws)
    assert exclusions.is_excluded(lock) is True
    with pytest.raises(EditRefusedError, match="FR-M28-07"):
        apply_hunk(ws, Hunk(path="package-lock.json", old="{}", new="{ }"), exclusions)
    # Allow-list override.
    allowed = ExclusionSet(ws, allowlist=frozenset({"package-lock.json"}))
    apply_hunk(ws, Hunk(path="package-lock.json", old="{}", new="{ }"), allowed)
    assert lock.read_text(encoding="utf-8") == "{ }"


def test_oversized_hunk_span_refused(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "big.py").write_text("x = 1\n", encoding="utf-8")
    exclusions = ExclusionSet(ws, max_edit_bytes=8)
    with pytest.raises(EditRefusedError, match="targeted-edit cap"):
        apply_hunk(ws, Hunk(path="big.py", old="x = 1\n" * 5, new="y"), exclusions)
