"""CLD-C01 probe: does a stand-in loop.start export traces when LangSmith env vars are set?"""
import http.server, json, os, sys, tempfile, threading, time
from pathlib import Path

hits = []


class H(http.server.BaseHTTPRequestHandler):
    def _any(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        hits.append((self.command, self.path, len(body)))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")
    do_POST = do_GET = do_PATCH = do_PUT = _any

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ.update({
    "LANGSMITH_TRACING": "true", "LANGCHAIN_TRACING_V2": "true",
    "LANGSMITH_ENDPOINT": f"http://127.0.0.1:{port}", "LANGCHAIN_ENDPOINT": f"http://127.0.0.1:{port}",
    "LANGSMITH_API_KEY": "lsv2_probe_key", "LANGCHAIN_API_KEY": "lsv2_probe_key",
    "LANGSMITH_PROJECT": "probe",
})

sys.path.insert(0, r"F:\code\meridianloom\meridianloom\core")
import langgraph, langsmith  # noqa: E402
print("langgraph", getattr(langgraph, "__version__", "?"), "langsmith", langsmith.__version__)

from langgraph.graph import StateGraph, START, END  # noqa: E402
from typing import TypedDict  # noqa: E402


class S(TypedDict):
    progress: list


def n1(s):
    return {"progress": s["progress"] + ["n1"]}


g = StateGraph(S)
g.add_node("n1", n1)
g.add_edge(START, "n1")
g.add_edge("n1", END)
print("result:", g.compile().invoke({"progress": ["repo secret: src/payroll.py"]}))

# Also the product path, if the runner is importable.
try:
    from meridian_core.runtime import loop as rloop  # noqa: F401
    print("runtime.loop importable")
except Exception as e:  # pragma: no cover
    print("runtime import:", type(e).__name__, e)

try:
    from langsmith import Client
    Client().flush() if hasattr(Client(), "flush") else None
except Exception as e:
    print("flush:", type(e).__name__, e)
time.sleep(4)
print("requests reaching fake LangSmith endpoint:", len(hits))
for h in hits[:10]:
    print("  ", h)
