"""CLD-B01 reproduction: halts and revocations past the 1,000-row page."""
import json, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, r"F:\code\meridianloom\meridianloom\core")
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.governance import merge_gate, revocations


def base(action, decision, detail, extra=None):
    e = {
        "story_id": "gate:probe", "phase": "review", "loop_id": "governance",
        "loop_iteration": 1, "actor_id": "governor", "actor_version": "0",
        "actor_kind": "meta", "policy_version": "governance/v2",
        "action_type": action, "decision": decision, "vendor": "meridian",
        "observation_confidence": "direct", "input": json.dumps(detail),
    }
    if extra:
        e.update(extra)
    return e


with tempfile.TemporaryDirectory() as d:
    led = Ledger(Path(d) / "ledger", EphemeralSigningKeyProvider())
    # Control: a halt on a small ledger is seen.
    led.append(base("gate", "halted", {"method": "gate.halt", "scope": "merge", "subject": "feature/x", "reason": "control"}, {"rework_reason": "control"}))
    print("control halts seen:", merge_gate.active_halts(led, "feature/x"))
    # Clear it with a session-scope noise: 1,000 non-blocking gate rows.
    t = time.time()
    for i in range(1000):
        led.append(base("gate", "passed", {"method": "gate.evaluate", "i": i}))
    led.append(base("gate", "halted", {"method": "gate.halt", "scope": "merge", "subject": "feature/y", "reason": "late halt"}, {"rework_reason": "late halt"}))
    print("appended 1001 gate rows in %.1fs" % (time.time() - t))
    print("halt on feature/y (the 1,002nd gate row) seen:", merge_gate.active_halts(led, "feature/y"))

with tempfile.TemporaryDirectory() as d:
    led = Ledger(Path(d) / "ledger", EphemeralSigningKeyProvider())
    for i in range(1000):
        revocations.record_revocation(led, email=f"user{i}@example.com", reason="noise")
    revocations.record_revocation(led, email="mallory@example.com", reason="compromised")
    print("mallory revoked (1,001st revocation) seen:", revocations.revoked_at(led, "mallory@example.com"))
    print("user0 revoked seen:", bool(revocations.revoked_at(led, "user0@example.com")))
