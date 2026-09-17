"""Smoke: the stand-in body round-trips JSON."""

import json
import subprocess
import sys
from pathlib import Path


def test_stand_in_round_trip(tmp_path):
    args = tmp_path / "args.json"
    args.write_text(json.dumps({"task": "demo"}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "agent.py"), str(args)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["adapter"] == "security"
    assert payload["echo"] == {"task": "demo"}


if __name__ == "__main__":
    test_stand_in_round_trip(Path.cwd())
    print("smoke ok")
