"""Child process for test_egress.py: run something that *would* upload traces
to LangSmith if tracing were on, and report what the environment looked like.

    egress_probe.py early|late|control <fake-endpoint-port> <workspace>

early    tracing variables were set by the parent before this process started
         (the editor's environment); ``import meridian_core`` must remove them.
late     variables are set *after* import, simulating something enabling them
         later; the runner's explicit no-tracing context must still hold.
control  same as late, but a bare LangGraph graph is run without Meridian's
         protection — proving the listener really does see uploads, so the
         zero in the other modes means something.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import meridian_core  # noqa: E402,F401  (scrubs the environment on import)

mode, port, workspace = sys.argv[1], sys.argv[2], sys.argv[3]

if mode in ("late", "control"):
    os.environ.update(
        {
            # Every spelling, overriding the "false" pins the import-time
            # scrub left behind: this simulates something enabling tracing
            # *after* import, which only the runner's explicit context stops.
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_TRACING_V2": "true",
            # (Not the legacy LANGCHAIN_TRACING: langchain-core raises on it,
            # which the import-time scrub also prevents in real use.)
            "LANGCHAIN_TRACING_V2": "true",
            "LANGSMITH_ENDPOINT": f"http://127.0.0.1:{port}",
            "LANGCHAIN_ENDPOINT": f"http://127.0.0.1:{port}",
            "LANGSMITH_API_KEY": "lsv2_probe_key",
        }
    )

report: dict = {
    "env": {k: v for k, v in os.environ.items() if k.upper().startswith(("LANGSMITH", "LANGCHAIN", "LANGGRAPH", "OTEL"))}
}

if mode == "control":
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        progress: list

    graph = StateGraph(State)
    graph.add_node("n1", lambda s: {"progress": s["progress"] + ["n1"]})
    graph.add_edge(START, "n1")
    graph.add_edge("n1", END)
    graph.compile().invoke({"progress": ["repo secret: src/payroll.py"]})
    report["ran"] = "bare-langgraph"
else:
    from meridian_core import protocol
    from meridian_core.licensing import runtime as licence_runtime
    from meridian_core.server import SidecarServer

    server = SidecarServer(licence=licence_runtime.LicenceManager(fixed_status=licence_runtime.premium_test_status()))
    server.handle_message(
        {
            "jsonrpc": "2.0", "id": 1, "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION, "client": "egress-probe",
                "workspaceDir": workspace, "tiers": ["flight-recorder", "governor", "orchestra"],
            },
        }
    )
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "loop.start",
         "params": {"loopId": "L-egress", "storyId": "S-payroll", "kind": "L2-task"}}
    )
    report["ran"] = "loop.start"
    report["response"] = response.get("result") or response.get("error")

# LangSmith uploads from a background thread. Give it every chance to send
# (flush what langchain knows about, then wait) before the process exits, or a
# zero-request result could just mean the process ended first.
try:
    from langchain_core.tracers.langchain import wait_for_all_tracers

    wait_for_all_tracers()
except Exception:  # noqa: BLE001 - best effort; the sleep below is the backstop
    pass
time.sleep(5)

print("REPORT:" + json.dumps(report))
