"""TASK-010: register the Orchestra/F4+ surfaces in shared/schema/methods.json.

Inserts new $defs and x-methods entries into the existing file with
surgical text splicing (no full-file reformat). Nested object schemas
are auto-hoisted into $defs to satisfy generate-bus-types.mjs.
Run:  python scripts/_register_orchestra_contract.py
Then: node scripts/generate-bus-types.mjs && npm run check:contracts
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = ROOT / "shared" / "schema" / "methods.json"

OBJ = "object"


def s(type_, **extra):
    schema = {"type": type_}
    schema.update(extra)
    return schema


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


# --------------------------------------------------------------------------
# Schema builders. `_hoist` lifts inline object schemas out of `properties`.
# --------------------------------------------------------------------------

DEFS: dict[str, dict] = {}
METHODS_NEW: dict[str, dict] = {}


def _hoist(owner: str, schema: dict) -> dict:
    """Recursively extract inline object property schemas into DEFS."""
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            props = {}
            for pname, pschema in value.items():
                if (
                    isinstance(pschema, dict)
                    and pschema.get("type") == OBJ
                    and "properties" in pschema
                ):
                    child_name = f"{owner}{pname[0].upper()}{pname[1:]}"
                    lifted = dict(pschema)
                    lifted["properties"] = _hoist(child_name, pschema)["properties"]
                    DEFS[child_name] = lifted
                    props[pname] = ref(child_name)
                else:
                    props[pname] = _hoist(f"{owner}{pname[0].upper()}{pname[1:]}", pschema)
            out[key] = props
        elif isinstance(value, dict):
            out[key] = _hoist(owner, value)
        elif isinstance(value, list):
            out[key] = [_hoist(owner, item) for item in value]
        else:
            out[key] = value
    return out


def define(name: str, desc: str, required: list[str], **properties):
    DEFS[name] = {
        "description": desc,
        "type": OBJ,
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


def method(name: str, description: str, params: str, result: str):
    METHODS_NEW[name] = {
        "description": description,
        "params": ref(params),
        "result": ref(result),
    }


# -- M4 loops ---------------------------------------------------------------

define(
    "LoopDefinitionWire",
    "The eight FR-M4-02 bound fields of a loop definition, as wire data.",
    ["loopId", "entryCondition", "bodyGraph", "exitCriteria",
     "maxIterations", "tokenBudget", "wallClockBudgetS", "costCeilingUsd",
     "escalationTarget"],
    loopId=s("string"),
    entryCondition=s("string"),
    bodyGraph=s("object", additionalProperties={"type": "array", "items": s("string")}),
    exitCriteria=s("string"),
    maxIterations={"type": ["integer", "string"]},
    tokenBudget={"type": ["integer", "string"]},
    wallClockBudgetS={"type": ["integer", "string"]},
    costCeilingUsd={"type": ["number", "string"]},
    escalationTarget=s("string"),
)
# loop.start/stop/status already exist in the contract (contracted stubs
# whose handlers return NOT_IMPLEMENTED until F3 wiring); TASK-011 replaces
# those stubs against the existing LoopStartParams shape (loopId/storyId/
# kind). Only the new surfaces are registered here.
define("LoopResumeParams", "Resume a suspended loop at its gate (FR-M4-06).",
       ["loopId"], loopId=s("string"))
define("LoopResumeResult", "Resumed run state.", ["status"],
       status=s("string"), iteration=s("integer"))
define("LoopReplayParams", "Fork-replay a run with state overrides (FR-M4-07).",
       ["loopId", "stateOverrides"],
       loopId=s("string"), stateOverrides=s("object", additionalProperties=True))
define("LoopReplayResult", "The forked run.", ["forkRunId", "status"],
       forkRunId=s("string"), status=s("string"))

method("loop.resume", "FR-M4-06: resume at a human gate.", "LoopResumeParams", "LoopResumeResult")
method("loop.replay", "FR-M4-07: modified-state fork replay.", "LoopReplayParams", "LoopReplayResult")

# -- M8 router ---------------------------------------------------------------

define("RouterRequestParams",
       "Request a model call through the engine-first router (FR-M8-15/16).",
       ["actionClass", "agentId", "storyId", "phase"],
       actionClass=s("string"), agentId=s("string"), storyId=s("string"),
       phase=s("string"), humanOverride=s("boolean"),
       payload=s("object", additionalProperties=True))
define("RouterRequestResult", "The router decision (recorded).",
       ["permitted", "actionClass"],
       permitted=s("boolean"), actionClass=s("string"),
       whyLlm={"type": ["string", "null"]},
       refusalReason={"type": ["string", "null"]},
       recordedSequence={"type": ["integer", "null"]})
define("RouterRatioParams", "LLM dependency ratio scope (FR-M8-17).", [],
       agentId={"type": ["string", "null"]}, phase={"type": ["string", "null"]},
       storyId={"type": ["string", "null"]}, actionClass={"type": ["string", "null"]},
       ceiling={"type": ["number", "null"]})
define("RouterRatioResult", "Ratio with breakdown-relevant counts.",
       ["modelCalls", "engineExecutions"],
       modelCalls=s("integer"), engineExecutions=s("integer"),
       ratio={"type": ["number", "null"]}, ceiling={"type": ["number", "null"]},
       breached={"type": ["boolean", "null"]})

method("router/requestModelCall", "FR-M8-15/16: engine-first model-call boundary.",
       "RouterRequestParams", "RouterRequestResult")
method("router/dependencyRatio", "FR-M8-17: per-scope LLM dependency ratio.",
       "RouterRatioParams", "RouterRatioResult")

# -- M9 tools ----------------------------------------------------------------

define("ToolsInvokeParams", "Invoke a native tool through the permission gate.",
       ["agentId", "tool", "argv"],
       agentId=s("string"), tool=s("string"),
       argv=s("array", items=s("string")), changeClass=s("string"))
define("ToolsInvokeResult", "Capped, marked tool result.",
       ["ok", "output", "truncated", "changeClass"],
       ok=s("boolean"), output=s("string"), truncated=s("boolean"),
       changeClass=s("string"), exitCode={"type": ["integer", "null"]})

method("tools/invoke", "FR-M9-02/03: permissioned native tool invocation.",
       "ToolsInvokeParams", "ToolsInvokeResult")

# -- M7 memory ---------------------------------------------------------------

define("MemoryEntryWire", "A declarative memory entry (FR-M7-04 provenance).",
       ["tier", "subject", "content", "author", "confidence", "origin"],
       tier={"type": "string", "enum": ["procedural", "semantic", "episodic"]},
       subject=s("string"), content=s("string"), author=s("string"),
       confidence=s("number"),
       origin={"type": "string", "enum": ["workspace", "user", "organisation", "story", "repository", "third_party"]},
       pinned=s("boolean"), source={"type": ["string", "null"]})
define("MemoryRetrieveParams", "Budgeted, ranked retrieval (FR-M7-13).",
       ["agentId", "queryTerms", "budgetChars"],
       agentId=s("string"), queryTerms=s("array", items=s("string")),
       budgetChars=s("integer"),
       tiers=s("array", items=s("string")))
define("MemoryRetrieveResult", "Included and cut entries, both logged.",
       ["included", "cut"],
       included=s("array", items=ref("MemoryHitWire")),
       cut=s("array", items=s("string")))
DEFS["MemoryHitWire"] = _hoist("MemoryHitWire", {
    "type": OBJ, "required": ["entryId", "subject", "digest"],
    "properties": {"entryId": s("string"), "subject": s("string"), "digest": s("string")},
    "additionalProperties": False,
})
define("MemoryWriteParams", "Gated memory writeback (FR-M7-05/07/11).",
       ["entry"],
       entry=ref("MemoryEntryWire"), actorIsHuman=s("boolean"))
define("MemoryWriteResult", "Write outcome.", ["written"],
       written=s("boolean"), reason={"type": ["string", "null"]})
define("MemoryLayeredParams", "Layered procedural merge (FR-M7-09).",
       ["layers"],
       layers=s("array", items=ref("MemoryLayerWire")))
DEFS["MemoryLayerWire"] = {
    "type": OBJ, "required": ["tier", "dir"],
    "properties": {"tier": s("string"), "dir": s("string")},
    "additionalProperties": False,
}
define("MemoryLayeredResult", "Effective playbook.", ["effective"],
       effective=s("object", additionalProperties=s("string")))

method("memory/retrieve", "FR-M7-08/13: budgeted ranked retrieval.", "MemoryRetrieveParams", "MemoryRetrieveResult")
method("memory/write", "FR-M7-05: gated writeback.", "MemoryWriteParams", "MemoryWriteResult")
method("memory/layered", "FR-M7-09: layered procedural memory.", "MemoryLayeredParams", "MemoryLayeredResult")

# -- M38 comprehension ---------------------------------------------------------

define("ComprehensionRecordParams", "Produce a module comprehension record (FR-M38-01).",
       ["path"], path=s("string"))
define("ComprehensionRecordResult", "The deterministic record.", ["record"],
       record=s("object", additionalProperties=True))
define("ComprehensionGateParams", "Evaluate the AC-35 characterisation gate.",
       ["path"], path=s("string"))
define("ComprehensionGateResult", "Gate verdict citing the record.",
       ["allowed", "path", "reason"],
       allowed=s("boolean"), path=s("string"), reason=s("string"),
       record=s("object", additionalProperties=True))

method("comprehension/record", "FR-M38-01: comprehension record.", "ComprehensionRecordParams", "ComprehensionRecordResult")
method("comprehension/gate", "AC-35/FR-M38-04: characterisation gate.", "ComprehensionGateParams", "ComprehensionGateResult")

# -- M31 adapters --------------------------------------------------------------

define("AdaptersDiscoverParams", "Discover adapter roots (FR-M31-02).",
       ["roots"], roots=s("array", items=s("string")))
define("AdaptersDiscoverResult", "Discovered adapters with validation state.",
       ["adapters", "states"],
       adapters=s("array", items=ref("AdapterWire")),
       states=s("object", additionalProperties=s("string")))
DEFS["AdapterWire"] = {
    "type": OBJ, "required": ["id", "version", "valid"],
    "properties": {"id": s("string"), "version": s("string"), "valid": s("boolean"),
                   "errors": s("array", items=s("string"))},
    "additionalProperties": False,
}
define("AdaptersPlugParams", "Hot-plug an adapter folder (FR-M31-04).",
       ["folder"], folder=s("string"))
define("AdaptersPlugResult", "Admission outcome.", ["id", "valid", "state"],
       id=s("string"), valid=s("boolean"), state=s("string"))
define("AdaptersUnplugParams", "Retire an adapter; in-flight work checkpointed (FR-M31-04).",
       ["id"], id=s("string"), inflight=s("object", additionalProperties=True))
define("AdaptersUnplugResult", "Retirement outcome.", ["retired"],
       retired=s("boolean"), checkpointed=s("boolean"))
define("AdaptersPromoteParams", "Promote probation -> active (FR-M5-05).",
       ["id"], id=s("string"))
define("AdaptersPromoteResult", "New state.", ["state"], state=s("string"))

method("adapters/discover", "FR-M31-02: discovery with precedence.", "AdaptersDiscoverParams", "AdaptersDiscoverResult")
method("adapters/plug", "FR-M31-04: hot plug to probation.", "AdaptersPlugParams", "AdaptersPlugResult")
method("adapters/unplug", "FR-M31-04: retire with checkpoint+escalation.", "AdaptersUnplugParams", "AdaptersUnplugResult")
method("adapters/promote", "FR-M5-05: probation promotion gate.", "AdaptersPromoteParams", "AdaptersPromoteResult")

# -- M13 decisions -------------------------------------------------------------

define("DecisionsRecordParams", "Record a consequential decision (FR-M13-01).",
       ["agentId", "inputs", "output", "confidence"],
       agentId=s("string"), inputs=s("object", additionalProperties=True),
       output={"type": ["object", "string", "number", "boolean", "null"]},
       confidence=s("number"), rationale={"type": ["string", "null"]},
       retrievedMemory=s("array", items=s("string")),
       toolCalls=s("array", items=s("string")))
define("DecisionsRecordResult", "Ledger sequence of the record.", ["sequence"],
       sequence=s("integer"))
define("DecisionsAblateParams", "Counterfactual replay with a factor removed (FR-M13-04/08).",
       ["decisionId", "withoutFactor", "inputs"],
       decisionId=s("string"), withoutFactor=s("string"),
       inputs=s("object", additionalProperties=True))
define("DecisionsAblateResult", "Marked-as-evidence ablation outcome.",
       ["changedFactor", "outputChanged", "labelled"],
       changedFactor=s("string"), outputChanged=s("boolean"), labelled=s("string"))
define("DecisionsGateParams", "Gate on tests/scans/approvals only (FR-M13-07).",
       ["testsPassed", "scansPassed", "approvals", "changeClass"],
       testsPassed=s("boolean"), scansPassed=s("boolean"),
       approvals=s("array", items=s("string")), changeClass=s("string"),
       ablations=s("array", items=s("integer")))
define("DecisionsGateResult", "Gate verdict.", ["passed"], passed=s("boolean"))

method("decisions/record", "FR-M13-01/02: decision record with labelled rationale.", "DecisionsRecordParams", "DecisionsRecordResult")
method("decisions/ablate", "FR-M13-04/08: counterfactual replay.", "DecisionsAblateParams", "DecisionsAblateResult")
method("decisions/gate", "FR-M13-05/07: explanation-free gate.", "DecisionsGateParams", "DecisionsGateResult")

# -- M16 portability ------------------------------------------------------------

define("PortabilityExportParams", "Export a signed adapter package (FR-M16-01/02/03).",
       ["adapterId", "destination"],
       adapterId=s("string"), destination=s("string"))
define("PortabilityExportResult", "Package path and card.", ["package"],
       package=s("string"), scannedFiles=s("integer"))
define("PortabilityImportParams", "Verify + confirm + import (FR-M16-04/05/06).",
       ["package", "confirm", "availableTools"],
       package=s("string"), confirm=s("boolean"),
       availableTools=s("array", items=s("string")))
define("PortabilityImportResult", "Admission outcome.", ["adapterId", "state"],
       adapterId=s("string"), state=s("string"))
define("PortabilityDiffParams", "Diff a package against the workspace (FR-M16-04).",
       ["package"], package=s("string"))
define("PortabilityDiffResult", "The full diff.", ["added", "overwritten"],
       added=s("array", items=s("string")),
       overwritten=s("array", items=s("string")))

method("portability/export", "FR-M16-01..03: signed, scanned export.", "PortabilityExportParams", "PortabilityExportResult")
method("portability/import", "FR-M16-04..06: verified, confirmed, probated import.", "PortabilityImportParams", "PortabilityImportResult")
method("portability/diff", "FR-M16-04: pre-import diff.", "PortabilityDiffParams", "PortabilityDiffResult")

# -- M14 trainer ------------------------------------------------------------------

define("TrainerTrainParams", "Run the Trainer (never mid-story, FR-M14-09).",
       ["openPhases"], openPhases=s("array", items=s("string")))
define("TrainerTrainResult", "Train outcome.", ["ran"], ran=s("boolean"),
       refusedReason={"type": ["string", "null"]})
define("TrainerPromoteParams", "Human-approved promotion (FR-M14-04..06).",
       ["kind", "subject", "content", "incumbentScore", "candidateScore",
        "humanApproved"],
       kind={"type": "string", "enum": ["prompt", "playbook", "checklist", "rule"]},
       subject=s("string"), content=s("string"),
       incumbentScore=s("number"), candidateScore=s("number"),
       humanApproved=s("boolean"), actorIsHuman=s("boolean"))
define("TrainerPromoteResult", "Promotion verdict.", ["promoted", "reason"],
       promoted=s("boolean"), reason=s("string"), path={"type": ["string", "null"]})
define("TrainerRollbackParams", "Single-action rollback (FR-M14-07).",
       ["kind", "subject"],
       kind=s("string"), subject=s("string"))
define("TrainerRollbackResult", "Restored version path.", ["path"], path=s("string"))

method("trainer/train", "FR-M14-09: scheduled/explicit training only.", "TrainerTrainParams", "TrainerTrainResult")
method("trainer/promote", "FR-M14-04..06: margin + invariant + human approval.", "TrainerPromoteParams", "TrainerPromoteResult")
method("trainer/rollback", "FR-M14-07/08: one-action rollback.", "TrainerRollbackParams", "TrainerRollbackResult")

# -- C5 tenancy / queue -------------------------------------------------------------

define("TenancyRegisterParams", "Register a tenant root (SEC-23).",
       ["tenantId", "root"], tenantId=s("string"), root=s("string"))
define("TenancyRegisterResult", "Registration outcome.", ["registered"],
       registered=s("boolean"))
define("QueueEnqueueParams", "Enqueue a story (FR-M21-01).", ["story"],
       story=ref("StoryWire"))
DEFS["StoryWire"] = _hoist("StoryWire", {
    "type": OBJ,
    "required": ["storyId", "priority", "tenantId"],
    "properties": {
        "storyId": s("string"), "priority": s("integer"), "tenantId": s("string"),
        "dependencies": s("array", items=s("string")),
    },
    "additionalProperties": False,
})
define("QueueEnqueueResult", "Enqueue outcome.", ["enqueued"], enqueued=s("boolean"))
define("QueueTickParams", "One scheduling tick (FR-M21-03).", [])
define("QueueTickResult", "Newly admitted stories.", ["admitted"],
       admitted=s("array", items=s("string")))

method("tenancy/register", "SEC-23/D13: tenant registration.", "TenancyRegisterParams", "TenancyRegisterResult")
method("queue/enqueue", "FR-M21-01: story enqueue.", "QueueEnqueueParams", "QueueEnqueueResult")
method("queue/tick", "FR-M21-03: scheduling tick with starvation surfacing.", "QueueTickParams", "QueueTickResult")

# -- C6 surfaces ----------------------------------------------------------------------

define("AnnotationsAddParams", "Annotate/bookmark a ledger entry (FR-M10-16).",
       ["targetSeq", "author", "text"],
       targetSeq=s("integer"), author=s("string"), text=s("string"),
       bookmark=s("boolean"))
define("AnnotationsAddResult", "Annotation sequence.", ["sequence"], sequence=s("integer"))
define("IssuesRecordParams", "Record an agent-detected issue (FR-M24-05).",
       ["agentId", "severity", "description", "storyId"],
       agentId=s("string"),
       severity={"type": "string", "enum": ["info", "warning", "critical"]},
       description=s("string"), storyId=s("string"))
define("IssuesRecordResult", "Issue sequence.", ["sequence"], sequence=s("integer"))

method("annotations/add", "FR-M10-16: ledger annotations/bookmarks.", "AnnotationsAddParams", "AnnotationsAddResult")
method("issues/record", "FR-M24-05: agent-detected issues.", "IssuesRecordParams", "IssuesRecordResult")

# -- M32/M27 simulation + golden ---------------------------------------------------------

define("SimulationServeParams", "Serve one bus request against a scripted scenario (FR-M32-01).",
       ["method", "params"],
       method=s("string"), params=s("object", additionalProperties=True))
define("SimulationServeResult", "Canned scenario response.", ["response", "backend"],
       response=s("object", additionalProperties=True), backend=s("string"))
define("SimulationTimeControlParams", "Time control (FR-M32-06).",
       ["action"],
       action={"type": "string", "enum": ["pause", "step", "play", "jump"]},
       rate=s("number"), sequence=s("integer"))
define("SimulationTimeControlResult", "Clock state.", ["position", "paused"],
       position=s("integer"), paused=s("boolean"))
define("GoldenRunParams", "Run one golden corpus entry (FR-M27-03/AC-16).",
       ["folder"], folder=s("string"))
define("GoldenRunResult", "Golden validation verdict.",
       ["storyId", "ok", "ledgerRoot", "expectedRoot", "entries"],
       storyId=s("string"), ok=s("boolean"), ledgerRoot=s("string"),
       expectedRoot=s("string"), entries=s("integer"))

method("simulation/serve", "FR-M32-01/04: scripted scenario serving.", "SimulationServeParams", "SimulationServeResult")
method("simulation/timeControl", "FR-M32-06: pause/step/play/jump.", "SimulationTimeControlParams", "SimulationTimeControlResult")
method("golden/run", "FR-M27-03/AC-16: golden corpus validation.", "GoldenRunParams", "GoldenRunResult")


# --------------------------------------------------------------------------
# Splice into methods.json preserving formatting.
# --------------------------------------------------------------------------

def render_block(name: str, schema: dict, indent: int) -> str:
    text = json.dumps(schema, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    # `{"a": 1}` dumped becomes "{\n  \"a\": 1\n}"; turn it into a named
    # object member: "\"name\": {\n  ..."
    lines[0] = json.dumps(name, ensure_ascii=False) + ": " + lines[0]
    pad = " " * indent
    return "\n".join(pad + line if line.strip() else line for line in lines)


def main() -> None:
    raw = METHODS.read_text(encoding="utf-8")
    document = json.loads(raw)
    existing_defs = set(document.get("$defs", {}))
    existing_methods = set(document.get("x-methods", {}))
    clashes = (set(DEFS) & existing_defs) | (set(METHODS_NEW) & existing_methods)
    if clashes:
        raise SystemExit(f"refusing to overwrite existing entries: {sorted(clashes)}")

    defs_lines = []
    for name, schema in DEFS.items():
        defs_lines.append(render_block(name, schema, 4))
    methods_lines = []
    for name, entry in METHODS_NEW.items():
        methods_lines.append(render_block(name, entry, 4 // 2))

    defs_text = ",\n".join(defs_lines)
    methods_text = ",\n".join(methods_lines)

    # Insert methods INSIDE the x-methods object: the boundary is the
    # object's closing `  },` immediately before `  "$defs": {`.
    marker = '\n  },\n  "$defs": {'
    assert marker in raw, "x-methods close/$defs boundary not found"
    raw = raw.replace(
        marker, ",\n" + methods_text + "\n  },\n  " + '"$defs": {', 1
    )

    # Insert defs before the file's final `  }\n}` ($defs is the last
    # top-level key; the last def currently ends without a trailing comma).
    tail = raw.rstrip()
    assert tail.endswith("}\n}") or tail.endswith("}}"), f"unexpected tail: {tail[-20:]!r}"
    closing = raw.rfind("  }\n}")
    assert closing != -1, "final $defs close not found"
    raw = raw[:closing] + ",\n" + defs_text + "\n" + raw[closing:]

    json.loads(raw)  # validity
    METHODS.write_text(raw, encoding="utf-8", newline="\n")
    print(f"inserted {len(METHODS_NEW)} methods, {len(DEFS)} defs")


if __name__ == "__main__":
    main()
