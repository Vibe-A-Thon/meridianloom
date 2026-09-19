"""The §6.10 prebuilt roster as ACP-conformant adapters (FR-M31, v2.1:
"the roster names roles; adapters fill them").

Every prebuilt agent is an adapter folder — manifest, agent.py,
skills/, instructions/, learned/, tests/ — with NO private path into the
runtime: the same discovery, validation, probation and hot-plug rules as
any imported adapter (FR-M31: the framework is done when every prebuilt
adapter survives unplug and re-plug).

The agent.py bodies are deterministic stand-ins (they read a JSON args
file and print a JSON result; zero model calls). A prebuilt profile is
not a bundled model: real reasoning requires an ACP runtime bound at
launch, which the manifest makes explicit (``acp: true`` declares the
protocol expectation; the host-side binding supplies the runtime).

``materialize_roster`` writes the folders; the shipped ``adapters/``
directory at the repository root is its output, committed as real
artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import AdapterManifest, folder_digest, parse_manifest

MANIFEST_TEMPLATE = """\
# {title} — prebuilt Meridian adapter (§6.10 roster, M31).
# Governance facet of the adapter manifest (§7.9). ACP transport is
# host-side; this folder carries policy, skills, instructions, learning.
id: {adapter_id}
version: "{version}"
role: {role}
acp: true
bridge: null
permittedTools: [{tools}]
trainable:
  policy: false
  rules: true
  memory: true
  skills: false
  calibration: true
actionClasses:
{action_classes}
dependencies: [{dependencies}]
digest: "{digest}"
"""

AGENT_PY = '''"""Deterministic stand-in body for the {title} adapter.

Reads a JSON args file (path in argv[1]) and prints a JSON result. A
prebuilt profile is not a bundled model: bind an ACP runtime at launch
for real reasoning; this body makes the adapter loadable, testable and
governable end to end with zero model calls.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        args = json.load(handle)
    result = {{
        "adapter": "{adapter_id}",
        "echo": args,
        "note": "deterministic stand-in; bind an ACP runtime for reasoning",
    }}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

SKILL_MD = """\
# {title} — skill pack

Bound to this adapter by default (FR-M6-10). Skills are declarative
playbook content, reviewed on install (FR-M6-06); nothing executable
lives here.
"""

INSTRUCTIONS_MD = """\
# {title} — instructions

Adapter-tier instruction file (FR-M7-14 precedence: adapter first).
Human-editable, versioned, digest-recorded per invocation (FR-M7-15).
"""

LEARNED_README = """\
# learned/

The complete record of what this agent has acquired (FR-M31-12).
Declarative, schema-validated data only — the engine refuses executable
content here (SEC-26). Committed to the repository under
.meridian/adapters/<id>/learned/ per D18.
"""

TEST_SMOKE = '''"""Smoke: the stand-in body round-trips JSON."""

import json
import subprocess
import sys
from pathlib import Path


def test_stand_in_round_trip(tmp_path):
    args = tmp_path / "args.json"
    args.write_text(json.dumps({{"task": "demo"}}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "agent.py"), str(args)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["adapter"] == "{adapter_id}"
    assert payload["echo"] == {{"task": "demo"}}


if __name__ == "__main__":
    test_stand_in_round_trip(Path.cwd())
    print("smoke ok")
'''


def _action_classes(role: str) -> dict[str, str]:
    base = {
        "plan": "assisted",
        "review": "assisted",
        "diff": "assisted",
        "test_run": "deterministic",
        "note": "deterministic",
    }
    if role in ("developer", "front_end_engineer"):
        base["parse"] = "deterministic"
        base["resolve_symbol"] = "deterministic"
    if role == "security":
        base["scan"] = "deterministic"
    if role == "reviewer":
        base["approval"] = "assisted"
    return base


#: The MUST-v1 core of the §6.10 roster (Release/SRE/Trainer/Onboarding
#: are v1.x and land with their phases; Refactoring/Legacy Comprehension
#: are SHOULD v1.x and land with M38 consumption).
ROSTER: tuple[dict[str, Any], ...] = (
    {"id": "chief-orchestrator", "role": "chief_orchestrator",
     "tools": ("build", "test", "repo_read"),
     "dependencies": ()},
    {"id": "phase-orchestrator", "role": "phase_orchestrator",
     "tools": ("build", "test"),
     "dependencies": ("chief-orchestrator",)},
    {"id": "analyst", "role": "analyst",
     "tools": ("repo_read",),
     "dependencies": ()},
    {"id": "architect", "role": "architect",
     "tools": ("repo_read", "static_analysis"),
     "dependencies": ("analyst",)},
    {"id": "tech-lead", "role": "tech_lead",
     "tools": ("repo_read", "static_analysis", "build"),
     "dependencies": ("architect",)},
    {"id": "scrum-master", "role": "scrum_master",
     "tools": ("repo_read",),
     "dependencies": ()},
    {"id": "developer", "role": "developer",
     "tools": ("repo_read", "build", "test", "apply_patch"),
     "dependencies": ("tech-lead",)},
    {"id": "front-end-engineer", "role": "front_end_engineer",
     "tools": ("repo_read", "build", "test", "apply_patch"),
     "dependencies": ("developer",)},
    {"id": "qa-engineer", "role": "qa_engineer",
     "tools": ("repo_read", "test"),
     "dependencies": ("developer",)},
    {"id": "qa-lead", "role": "qa_lead",
     "tools": ("repo_read", "test", "static_analysis"),
     "dependencies": ("qa-engineer",)},
    {"id": "security", "role": "security",
     "tools": ("repo_read", "scan", "static_analysis"),
     "dependencies": ("architect",)},
    {"id": "reviewer", "role": "reviewer",
     "tools": ("repo_read",),
     "dependencies": ("qa-lead",)},
    {"id": "xai", "role": "xai_overlay",
     "tools": ("repo_read",),
     "dependencies": ()},
    {"id": "governance", "role": "governance",
     "tools": ("repo_read",),
     "dependencies": ("chief-orchestrator",)},
)


def materialize_roster(destination: Path, *, version: str = "1.0.0") -> list[Path]:
    """Write every roster adapter folder. Idempotent: identical inputs
    produce identical folders (the digest is content-derived)."""
    written: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    for spec in ROSTER:
        root = destination / spec["id"]
        (root / "skills").mkdir(parents=True, exist_ok=True)
        (root / "instructions").mkdir(exist_ok=True)
        (root / "learned").mkdir(exist_ok=True)
        (root / "tests").mkdir(exist_ok=True)
        title = spec["id"].replace("-", " ").title()
        (root / "agent.py").write_text(
            AGENT_PY.format(adapter_id=spec["id"], title=title), encoding="utf-8"
        )
        (root / "skills" / "SKILL.md").write_text(
            SKILL_MD.format(title=title), encoding="utf-8"
        )
        (root / "instructions" / "AGENTS.md").write_text(
            INSTRUCTIONS_MD.format(title=title), encoding="utf-8"
        )
        (root / "learned" / "README.md").write_text(LEARNED_README, encoding="utf-8")
        (root / "tests" / "test_smoke.py").write_text(
            TEST_SMOKE.format(adapter_id=spec["id"]), encoding="utf-8"
        )
        classes = _action_classes(spec["role"])
        action_lines = "\n".join(f'  {k}: "{v}"' for k, v in classes.items())
        tools = ", ".join(f'"{t}"' for t in spec["tools"])
        deps = ", ".join(f'"{d}"' for d in spec["dependencies"])
        # Digest over the content files, then the manifest embeds it.
        digest = folder_digest(root)
        manifest = MANIFEST_TEMPLATE.format(
            title=title,
            adapter_id=spec["id"],
            version=version,
            role=spec["role"],
            tools=tools,
            action_classes=action_lines,
            dependencies=deps,
            digest=digest,
        )
        (root / "adapter.yaml").write_text(manifest, encoding="utf-8")
        # Re-verify: the embedded digest must match the folder.
        parsed = parse_manifest(manifest, str(root))
        if parsed.digest != folder_digest(root):
            raise RuntimeError(f"digest drift materializing {spec['id']}")
        written.append(root)
    return written
