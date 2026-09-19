"""Golden corpus CI runner (audit TASK-022; FR-M27-03, AC-16, D10).

Runs every ``golden/<story-id>/`` entry through the cassette replay and
the expected-root comparison. Admission is by adding a folder; a tampered
or drifted entry fails the run. Zero model calls by construction.

Usage:  python scripts/check_golden.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from meridian_core.replay import Cassette, replay_cassette  # noqa: E402


def run_entry(folder: Path) -> dict:
    cassette = Cassette.load(folder / "cassette.json")
    expected = (folder / "expected_root.txt").read_text(encoding="utf-8").strip()
    if not (folder / "story.txt").is_file():
        return {"storyId": cassette.story_id, "ok": False,
                "reason": "missing story.txt"}
    with tempfile.TemporaryDirectory() as tmp:
        ledger = replay_cassette(cassette, Path(tmp))
        try:
            root = ledger._frontier.root().hex()
        finally:
            ledger.close()
    return {
        "storyId": cassette.story_id,
        "ok": root == expected,
        "ledgerRoot": root,
        "expectedRoot": expected,
        "entries": len(cassette.rows),
    }


def main() -> int:
    golden = ROOT / "golden"
    folders = sorted(p for p in golden.iterdir() if p.is_dir()) if golden.is_dir() else []
    if not folders:
        print("check-golden: no corpus entries under golden/ — nothing to run")
        return 1
    failures = 0
    for folder in folders:
        result = run_entry(folder)
        status = "ok" if result["ok"] else "FAIL"
        print(f"  {status}  {result['storyId']}  entries={result['entries']}")
        if not result["ok"]:
            failures += 1
            print(f"        ledger root {result.get('ledgerRoot')} != "
                  f"expected {result.get('expectedRoot')} ({result.get('reason', 'root mismatch')})")
    print(f"check-golden: {len(folders) - failures}/{len(folders)} entries passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
