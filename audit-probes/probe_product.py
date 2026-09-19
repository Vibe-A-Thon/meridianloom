"""CLD-C01 via the product RPC path, and CLD-B01 revocation cap."""
import http.server, os, subprocess, sys, tempfile, threading, time
from pathlib import Path

hits = []


class H(http.server.BaseHTTPRequestHandler):
    def _any(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        hits.append((self.command, self.path, len(body), b"L-probe" in body, b"payroll" in body))
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(b"{}")
    do_POST = do_GET = do_PATCH = do_PUT = _any

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update({
    "LANGSMITH_TRACING": "true", "LANGSMITH_ENDPOINT": f"http://127.0.0.1:{port}",
    "LANGSMITH_API_KEY": "lsv2_probe_key", "LANGSMITH_PROJECT": "probe",
})

sys.path.insert(0, r"F:\code\meridianloom\meridianloom\core")
from meridian_core import protocol  # noqa: E402
from meridian_core.server import SidecarServer  # noqa: E402
from meridian_core.ledger.core import Ledger  # noqa: E402
from meridian_core.ledger.keys import EphemeralSigningKeyProvider  # noqa: E402
from meridian_core.governance import revocations  # noqa: E402

tmp = Path(tempfile.mkdtemp())
ws = tmp / "ws"; ws.mkdir()
for a in (["init", "-q", "-b", "main"], ["config", "user.name", "U"], ["config", "user.email", "u@e.t"]):
    subprocess.run(["git", *a], cwd=ws, check=True, capture_output=True)
(ws / "payroll.py").write_text("x=1\n")
subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
subprocess.run(["git", "commit", "-q", "-m", "b"], cwd=ws, check=True, capture_output=True)

led = Ledger(tmp / "ledger", EphemeralSigningKeyProvider())
s = SidecarServer(ledger=led)
s.handle_message({"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": {
    "protocolVersion": protocol.PROTOCOL_VERSION, "client": "probe", "workspaceDir": str(ws),
    "tiers": ["flight-recorder", "governor", "orchestra"]}})
r = s.handle_message({"jsonrpc": "2.0", "id": 2, "method": "loop.start",
                      "params": {"loopId": "L-probe", "storyId": "S-payroll", "kind": "L2-task"}})
print("loop.start:", r.get("result") or r.get("error"))
time.sleep(5)
print("product-path requests to fake LangSmith:", len(hits))
for h in hits[:10]:
    print("   method,path,bytes,contains loopId,contains 'payroll':", h)

# Revocation cap
led2 = Ledger(tmp / "ledger2", EphemeralSigningKeyProvider())
for i in range(1000):
    revocations.record_revocation(led2, email=f"user{i}@example.com", reason="noise")
revocations.record_revocation(led2, email="mallory@example.com", reason="compromised")
print("mallory (1,001st revocation) revoked_at:", revocations.revoked_at(led2, "mallory@example.com"))
print("user0 (1st) revoked:", bool(revocations.revoked_at(led2, "user0@example.com")))
led.close(); led2.close()
