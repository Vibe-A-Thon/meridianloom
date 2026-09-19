"""Third-party telemetry must not leave the machine (audit CLD-C01).

Reproduced before the fix: with ``LANGSMITH_TRACING=true`` and an endpoint in
the environment, one ``loop.start`` made three ``POST /runs/multipart``
requests. These tests hold the line at both layers — the environment scrub at
import and the explicit no-tracing context around graph execution — and the
*control* proves the listener sees uploads when the protection is bypassed.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from meridian_core import egress

CORE = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().parent / "egress_probe.py"


class Listener:
    """A stand-in for LangSmith's ingestion endpoint that records requests."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, int]] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _any(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append((self.command, self.path, len(body)))
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            do_GET = do_POST = do_PATCH = do_PUT = _any

            def log_message(self, *args) -> None:  # noqa: D401
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def uploads(self) -> list[tuple[str, str, int]]:
        # GET /info is a capability probe with no payload; uploads are POST/PATCH.
        return [r for r in self.requests if r[0] in ("POST", "PATCH", "PUT")]


@pytest.fixture()
def listener():
    instance = Listener()
    yield instance
    instance.close()


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.test",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.test"}
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)
    return root


def run_probe(mode: str, listener: Listener, workspace: Path, extra_env: dict[str, str] | None = None) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("MERIDIAN_LICENCE")}
    env.update(extra_env or {})
    completed = subprocess.run(
        [sys.executable, str(PROBE), mode, str(listener.port), str(workspace)],
        cwd=CORE, env=env, capture_output=True, text=True, timeout=600, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    line = next(l for l in completed.stdout.splitlines() if l.startswith("REPORT:"))
    return json.loads(line[len("REPORT:"):])


# -- the helper --------------------------------------------------------------


class TestScrub:
    def test_families_are_removed_and_tracing_is_pinned_off(self):
        env = {
            "LANGSMITH_API_KEY": "k", "LANGCHAIN_ENDPOINT": "http://x", "LANGGRAPH_API_URL": "y",
            "langsmith_project": "lowercase-too", "PATH": "/bin", "MERIDIAN_X": "1",
        }
        removed = egress.disable_third_party_telemetry(env)
        assert sorted(removed) == ["LANGCHAIN_ENDPOINT", "LANGGRAPH_API_URL", "LANGSMITH_API_KEY", "langsmith_project"]
        assert env["LANGSMITH_TRACING"] == "false" and env["LANGCHAIN_TRACING_V2"] == "false"
        assert env["PATH"] == "/bin" and env["MERIDIAN_X"] == "1"  # unrelated variables untouched
        assert not [k for k in env if "API_KEY" in k]

    def test_idempotent(self):
        env = {"LANGSMITH_TRACING": "true"}
        egress.disable_third_party_telemetry(env)
        first = dict(env)
        egress.disable_third_party_telemetry(env)
        assert env == first
        assert env["LANGSMITH_TRACING"] == "false"

    def test_this_process_was_scrubbed_at_import(self):
        assert os.environ.get("LANGSMITH_TRACING") == "false"
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"


# -- the behaviour -----------------------------------------------------------


class TestNothingIsUploaded:
    def test_control_a_bare_graph_does_upload_when_tracing_is_on(self, listener, workspace):
        # If this fails the probe can no longer see uploads (for example the
        # library stopped tracing on env vars) and the zeros below are vacuous.
        report = run_probe("control", listener, workspace)
        assert report["ran"] == "bare-langgraph"
        assert listener.uploads, (
            "control saw no upload: the listener cannot observe LangSmith traffic, "
            "so this suite is not proving anything"
        )

    def test_environment_from_the_editor_is_scrubbed_at_import(self, listener, workspace):
        report = run_probe(
            "early", listener, workspace,
            extra_env={
                "LANGSMITH_TRACING": "true", "LANGCHAIN_TRACING_V2": "true",
                "LANGSMITH_ENDPOINT": f"http://127.0.0.1:{listener.port}",
                "LANGSMITH_API_KEY": "lsv2_should_not_survive",
            },
        )
        assert "LANGSMITH_API_KEY" not in report["env"]
        assert "LANGSMITH_ENDPOINT" not in report["env"]
        assert report["env"]["LANGSMITH_TRACING"] == "false"
        assert report["response"]["status"] in {"completed", "simulated"}
        assert listener.requests == [], listener.requests

    def test_variables_set_after_import_still_upload_nothing_from_a_loop(self, listener, workspace):
        report = run_probe("late", listener, workspace)
        assert report["env"]["LANGSMITH_TRACING"] == "true"  # the variable really was on
        assert report["ran"] == "loop.start"
        assert report["response"]["status"] in {"completed", "simulated"}
        assert listener.uploads == [], (
            "loop.start uploaded run data to a third-party endpoint: " + repr(listener.uploads)
        )
