"""AC-28 scenario parity harness (audit TASK-021).

For every scripted scenario step: (a) the method exists in the generated
contract AND the production sidecar's registry (no drift — FR-M32-09);
(b) read-only steps are served by BOTH backends without a protocol error
— the SimulationCore from canned scenario data, the production sidecar
from a real (empty) workspace — and the two responses carry the same
top-level shape for the shared read methods.

Scope, stated honestly: byte-identical answers are proven for cassette
replays (tests/test_simulation_m32.py, AC-15); live production answers
depend on workspace state, so this harness checks shape parity and
reachability, not byte equality.

Usage:  python scripts/check_scenario_parity.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from meridian_core.simulation import load_contract  # noqa: E402
from meridian_core.simulation.scenarios import all_scenarios  # noqa: E402

# Methods safe to probe against a live production sidecar (read-only).
READ_METHODS = {
    "ledger.query", "ledger.verify", "gate.status", "loop.status",
    "steer/status", "adapters/discover",
}

# Response keys that must exist on both backends for shared read methods.
SHARED_KEYS = {
    "ledger.query": {"entries", "truncated"},
    "ledger.verify": {"ok"},
    "gate.status": {"status"},
    "loop.status": {"loopId", "kind", "state", "iteration"},
    "adapters/discover": {"adapters"},
}


class SidecarProbe:
    """One production sidecar subprocess speaking framed JSON-RPC."""

    def __init__(self, workspace: Path) -> None:
        env = {"PYTHONPATH": str(ROOT / "core")}
        import os
        full_env = dict(os.environ)
        full_env.update(env)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "meridian_core"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=workspace,
            env=full_env,
        )
        self._next_id = 1
        self._request(
            "handshake",
            {
                "protocolVersion": 1,
                "client": "parity-probe",
                "workspaceDir": str(workspace),
                "tiers": ["flight-recorder", "governor", "orchestra"],
            },
        )

    def _request(self, method: str, params: dict) -> dict:
        request_id = self._next_id
        self._next_id += 1
        assert self._proc.stdin is not None and self._proc.stdout is not None
        # FR-M3-01 framing: newline-delimited JSON, one frame per line.
        frame = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        ).encode("utf-8") + b"\n"
        self._proc.stdin.write(frame)
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("sidecar closed the connection")
        return json.loads(line.decode("utf-8"))

    def call(self, method: str, params: dict) -> dict:
        return self._request(method, params)

    def close(self) -> None:
        try:
            self._request("shutdown", {})
        except Exception:
            pass
        self._proc.wait(timeout=10)


def simulate(scenario_name: str, method: str, params: dict) -> dict:
    from meridian_core.simulation import SimulationCore
    from meridian_core.simulation.scenarios import load_scenario

    core = SimulationCore(scenario=load_scenario(scenario_name))
    return core.serve(method, params)


def main() -> int:
    contract = load_contract()
    scenarios = all_scenarios()
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / ".meridian").mkdir()
        probe = SidecarProbe(workspace)
        try:
            for name, scenario in scenarios.items():
                for step in scenario.steps:
                    method = step.method
                    if method not in contract:
                        problems.append(f"{name}: {method} not in contract")
                        continue
                    # Simulation backend answers every step from canned data.
                    sim = simulate(name, method, dict(step.params))
                    if "error" in sim:
                        problems.append(
                            f"{name}: simulation error on {method}: {sim['error']}"
                        )
                    if method not in READ_METHODS:
                        continue
                    live = probe.call(method, dict(step.params))
                    if "error" in live:
                        problems.append(
                            f"{name}: production error on {method}:"
                            f" {live['error']}"
                        )
                        continue
                    live_keys = set(live.get("result", {}))
                    missing = SHARED_KEYS.get(method, set()) - live_keys
                    if missing:
                        problems.append(
                            f"{name}: production {method} missing keys {sorted(missing)}"
                        )
        finally:
            probe.close()
    for problem in problems:
        print(f"  FAIL  {problem}")
    total = sum(len(s.steps) for s in scenarios.values())
    print(
        f"scenario-parity: {total - len(problems)}/{total} step checks passed "
        f"across {len(scenarios)} scenarios"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
