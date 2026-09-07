"""Governance can halt (FR-M12-06; F1 Workstream B task 11).

gate.halt records a halt (reason, scope) in the ledger — before the RPC
returns (FR-M10-08) — and takes the enforceable action available at that
scope:

* hosted-session: the halt is dispatched to the extension host's ACP
  session registry as a `gate/halt` bus notification; killing the real
  session process is the registry's job (the sidecar owns the record and
  the dispatch, never host processes).
* merge: the merge gate enters the halted state — merge attempts for the
  subject (or every subject when none is named) are refused.
* observe-only (external agents): FR-M35-06 — observation never
  intercepts, so an external agent cannot be force-stopped. The halt
  records, blocks merges, warns, and the RPC response says exactly that
  (enforceable: false).

G5: governor disabled -> TIER_DISABLED, recorder untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import merge_gate, policy
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles: {}
"""


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "Fixture")
    env.setdefault("GIT_AUTHOR_EMAIL", "fixture@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Fixture")
    env.setdefault("GIT_COMMITTER_EMAIL", "fixture@example.com")
    result = subprocess.run(
        [
            "git",
            "-c", "core.autocrlf=false",
            "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main",
            "-c", "user.name=Ada Lovelace",
            "-c", "user.email=ada@example.com",
            *args,
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init")
    (target / ".meridian" / "policy").mkdir(parents=True)
    (target / ".meridian" / "policy" / "governance.yaml").write_text(
        PACK_TEXT, encoding="utf-8"
    )
    (target / "app.txt").write_text("one\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "initial")
    return target


class NotificationSink:
    """The framed writer's notification slot, captured for assertions."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    def __call__(self, message: dict) -> None:
        self.messages.append(message)


def make_server(tmp_path: Path, repo: Path, sink: NotificationSink) -> SidecarServer:
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger, notification_sink=sink)
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(repo),
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    return server


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def halt_row(server: SidecarServer) -> dict:
    rows = server.ledger.query(action_type="gate")
    assert len(rows) == 1
    return rows[0]


# -- hosted-session -----------------------------------------------------------


class TestHostedSessionHalt:
    def test_halt_records_then_dispatches_to_session_registry(
        self, tmp_path, repo
    ):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        response = call(
            server,
            "gate.halt",
            {
                "reason": "credential leak in prompt",
                "scope": "hosted-session",
                "sessionId": "acp-session-7",
            },
        )
        result = response["result"]
        assert result["recorded"] is True
        assert result["enforceable"] is True
        # FR-M10-08: the halt row exists before the response was assembled.
        row = halt_row(server)
        assert row["decision"] == "halted"
        assert row["rework_reason"] == "credential leak in prompt"
        assert row["human_actor"]  # the halting human is named (FR-M12-07)
        detail = json.loads(
            server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["scope"] == "hosted-session"
        assert detail["sessionId"] == "acp-session-7"
        # The dispatch crosses the bus as a gate/halt notification; killing
        # the process is the extension registry's job, not the sidecar's.
        assert len(sink.messages) == 1
        notice = sink.messages[0]
        assert notice["method"] == "gate/halt"
        assert notice["params"]["sessionId"] == "acp-session-7"
        assert notice["params"]["reason"] == "credential leak in prompt"
        assert notice["params"]["sequence"] == row["seq"]
        (action,) = result["actions"]
        assert action["scope"] == "hosted-session"
        assert action["action"] == "terminated"
        assert "registry" in action["detail"]

    def test_session_id_is_required_for_hosted_session(self, tmp_path, repo):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        response = call(
            server,
            "gate.halt",
            {"reason": "stop", "scope": "hosted-session"},
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert server.ledger.query(action_type="gate") == []
        assert sink.messages == []


# -- merge --------------------------------------------------------------------


class TestMergeHalt:
    def test_merge_halt_blocks_merge_attempts(self, tmp_path, repo):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        response = call(
            server,
            "gate.halt",
            {"reason": "incident: freeze the queue", "scope": "merge", "subject": "main"},
        )
        result = response["result"]
        assert result["enforceable"] is True
        (action,) = result["actions"]
        assert action["action"] == "blocked"
        assert "main" in action["detail"]
        # No session dispatch for a merge halt.
        assert sink.messages == []
        # The merge gate now refuses — even with an approval in hand the
        # halt wins (policy outranks delivery).
        status = call(server, "gate.status", {"subject": "main", "commit": "a" * 40})[
            "result"
        ]
        assert status["status"] == "blocked"
        assert status["halted"] is True
        assert any("freeze the queue" in m for m in status["missing"])
        pack = policy.parse_policy_pack(PACK_TEXT, "t")
        verdict = merge_gate.check_merge(
            server.ledger, pack, subject="main", head_commit="a" * 40
        )
        assert verdict.allowed is False
        assert verdict.halted is True

    def test_global_merge_halt_blocks_every_subject(self, tmp_path, repo):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        call(server, "gate.halt", {"reason": "freeze all", "scope": "merge"})
        status = call(
            server, "gate.status", {"subject": "feature/x", "commit": "b" * 40}
        )["result"]
        # Unprotected branch, but the global halt still wins.
        assert status["status"] == "blocked"
        assert status["halted"] is True


# -- observe-only (FR-M35-06) ---------------------------------------------------


class TestObserveOnlyHalt:
    def test_cannot_force_stop_but_records_blocks_and_warns(self, tmp_path, repo):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        response = call(
            server,
            "gate.halt",
            {
                "reason": "untrusted output detected",
                "scope": "observe-only",
                "subject": "main",
            },
        )
        result = response["result"]
        # The response says exactly what enforcement is and is not possible.
        assert result["enforceable"] is False
        assert result["warning"]
        assert "FR-M35-06" in result["warning"]
        assert "cannot" in result["warning"] and "force-stop" in result["warning"]
        actions = {(a["scope"], a["action"]) for a in result["actions"]}
        assert ("observe-only", "warned") in actions
        assert ("merge", "blocked") in actions
        # Nothing was dispatched — observation never intercepts.
        assert sink.messages == []
        # ...but the merge IS blocked and the halt is recorded.
        status = call(server, "gate.status", {"subject": "main", "commit": "a" * 40})[
            "result"
        ]
        assert status["status"] == "blocked"
        assert status["halted"] is True
        row = halt_row(server)
        assert row["decision"] == "halted"
        detail = json.loads(
            server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["scope"] == "observe-only"


# -- validation + G5 ------------------------------------------------------------


class TestHaltValidation:
    @pytest.mark.parametrize(
        "params",
        [
            {"scope": "merge"},  # no reason
            {"reason": "x"},  # no scope
            {"reason": "x", "scope": "sideways"},  # unknown scope
            {"reason": "", "scope": "merge"},  # blank reason
        ],
    )
    def test_bad_params_are_refused_and_record_nothing(self, tmp_path, repo, params):
        sink = NotificationSink()
        server = make_server(tmp_path, repo, sink)
        response = call(server, "gate.halt", params)
        assert response["error"]["code"] == protocol.INVALID_PARAMS, params
        assert server.ledger.query(action_type="gate") == []
        assert sink.messages == []

    def test_governor_disabled_refuses_and_touches_nothing(self, tmp_path, repo):
        server = SidecarServer()
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "workspaceDir": str(repo),
                },
            }
        )
        response = call(
            server, "gate.halt", {"reason": "r", "scope": "merge", "subject": "main"}
        )
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert not (repo / ".meridian" / "ledger").exists()
