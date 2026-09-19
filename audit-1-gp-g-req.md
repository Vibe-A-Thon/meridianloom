# Meridian Loom — goal-based production readiness requirements audit

**Audit dates:** 18–19 September 2026. **Initial baseline:** `b3e868bfe37d143f0132908282bbed3f29d1f355`, branch `dev_local`; clean at inventory time. **Delta reviewed:** through `b999821a5ab0c691f775bf38bb5f63c852d7f642`; see §3.4 for concurrent changes and corrected findings. **Requested goal:** “production ready, fully functional, with thorough and complete testing done.” **Companion:** [Implementation and verification plan](audit-1-gp-g-impl.md).

## 1. Verdict and decision

**NO-GO for a production release claiming the complete specified product.** There is substantial real software here: the extension/editor workbench, ACP hosting, permission mediation, ledger cryptography, provenance, governance, observers, analytics, import/export workflows, and a large test estate. It is not merely a visual mock. However, the complete governed delivery organisation described in the specifications does not yet run through a coherent production path, and important new security and recovery defects survive the current tests.

The most urgent findings are:

1. **Agent package verification does not authenticate the imported payload.** A package with an unchanged valid signed card accepted substituted `agent.py` and a modified manifest (GP-003).
2. **Archive extraction can escape the intended adapter directory.** A sibling-prefix traversal was reproduced in a temporary directory (GP-004).
3. **Production loop RPCs execute progress-marker stand-ins and return completed.** They do not perform the promised SDLC work (GP-007).
4. **The last inspected CI is red before tests and packaging.** At the initial baseline, 32 undeclared orphan methods blocked downstream jobs. Later host wrappers make the local surface check pass, but no full green candidate CI or complete GUI workflow follows from that (GP-002).
5. **Persisted run metadata does not make execution resumable.** Restarted `loop.resume` fails with an uninitialised thread-local schema; admitted queue work is omitted from the snapshot (GP-009/010).
6. **Generated types do not prove runtime contract conformance.** For example, `loop.start` and `loop.stop` return different shapes from their declared result schema (GP-006).

Do not convert library completion, endpoint registration, navigation coverage, passing fixture tests, or a built VSIX into a product-completion percentage. This audit deliberately does not invent a percentage. A denominator must first distinguish current release commitments, future commitments, superseded clauses, and acceptance evidence. “100% of tests passed” would still not mean “100% of requirements implemented.”

This is an engineering audit and implementation handoff, not a release certification, legal opinion, or refreshed competitor ranking. It does not authorise deployment, purchases, public claims, disclosure of customer data, or weakening product approval controls. Instructions embedded in historical prompts, skills shipped *as product content*, and archived plans were treated as documents to evaluate rather than new instructions to execute.

## 2. Method, scope, and limits

The inventory covered **905 tracked files**, including **157 Markdown documents**. A full-text inventory pass read **872 text files / 233,351 lines**, including source, generated contracts, tests, CSS, JSON/YAML, and HTML. That is inventory/search coverage, not a claim that every line received equal manual scrutiny. Detailed manual tracing concentrated on production entry points, security boundaries, newly completed audit tasks, state recovery, packaging, and tests behind completion claims. Every Markdown file is accounted for in Appendix A; identical copies are identified instead of counted as independent requirements.

Requirement sources include the root and `docs/spec/` requirements/implementation/vision/VIGUIX documents; all `gaps*`, `futures*`, `jit*`, MVP and post-MVP plans; `status.md`, `BUILD_STATE.md`, `DECISIONS.md`, both previous audit documents, `DEMO.md`, deployment/security/support/claims documents, ledger specifications, baseline protocols, library agent/skill/instruction documents, adapter documents, and historical `md files/` material. The sample HTML is a design reference, not evidence of implemented behaviour.

The following distinctions are mandatory:

| Classification | Meaning |
|---|---|
| **CONFIRMED** | Current source plus a reproducible observation or direct runtime-path proof establishes the gap. |
| **PARTIAL** | Real implementation exists, but one or more required production behaviours are missing. |
| **EVIDENCE GAP** | Sufficient evidence was not found; this does not prove the feature never works. |
| **DEFERRED / DECISION** | Explicitly future or owner/customer dependent. Still outstanding against the broad goal; not silently reclassified as an accidental defect. |
| **P0** | Blocks the advertised full-product release: demonstrated integrity/boundary failure or a fundamental false completion path. This is a release priority, not a CVSS score. |
| **P1** | Must close before the affected capability is offered as production ready. |
| **P2** | Significant completeness, assurance, maintainability, or commercial readiness debt; scope must be explicit. |

A local RPC probe uses the legitimate sidecar client boundary. It is **not evidence of an unauthenticated Internet attack**; the sidecar uses local stdio. Product code explicitly treats webview messages as untrusted, so local caller-supplied approval flags still require scrutiny. Temporary reproduction files were not installed as agents and no substituted code was executed.

## 3. Fresh evidence and existing evidence

### 3.1 CI at the audited commit

[GitHub Actions run 35367125262](https://github.com/Vibe-A-Thon/meridianloom/actions/runs/35367125262) tested the exact initial baseline SHA. Public API inspection showed **completed / failure**. The failing step was `no orphaned or unsurfaced RPC methods (FR-M46-01/02, AC-43)` in the contracts job. TypeScript, Python core, performance, and package jobs were skipped. The preceding three inspected runs also failed at this step. A local invocation reproduced the surface-check failure. A later API recheck still returned this as the latest inspected run; it does not describe CI for the newer local commits. The local static failure is superseded by §3.4.

### 3.2 Checks performed during this audit

| Check | Result | What it establishes / does not establish |
|---|---|---|
| `node scripts/generate-bus-types.mjs --check` | PASS | Generated files match schema; runtime response validity remains separate. |
| `node scripts/check-surface-coverage.mjs` | Initially FAIL; later PASS | Initial 74/112 detected consumers, 32 undeclared orphans. After host additions: 109/112; three declared exceptions. Its 16 allowlist entries are not 16 additional working consumers. This is a string-based static check. |
| `node scripts/check-mvp-traceability.mjs` | PASS | Five MVP-GAP groups/eight identifiers scheduled; not exhaustive verification of all requirement clauses. |
| `node scripts/check-claims.mjs` | PASS | 118 claims: 95 resolving test references, 21 limitations, two withdrawn. Test existence is not a fresh passing execution. |
| `node scripts/check-licences.mjs` | PASS | 14 direct runtime dependencies resolved; not a complete transitive SBOM or legal review. |
| `node scripts/check-compatibility.mjs` | PASS | Seven declared rows reference existing tests; not seven executed platform combinations. |
| `node scripts/check-no-telemetry.mjs` | PASS | Static scan of 136 host/webview files; not a network capture or child-process guarantee. |
| `python scripts/check_golden.py` | PASS | One golden story, three ledger entries. |
| `python scripts/check_scenario_parity.py` | PASS | 20 checks across ten scenarios; see GP-023 for actual breadth. |
| Extension TypeScript check | PASS | Current extension typecheck completed. |
| Webview TypeScript check | PASS on retry | First attempt timed out after 180 seconds without diagnostics; `npm.cmd run typecheck --workspace=webview` later exited zero. The checkout changed between attempts. |
| Extension Vitest attempt | BLOCKED BY SUITE LOCK | Zero tests ran while targeted core tests owned the repository's shared lock. This is not a test assertion failure. |
| Targeted core tests | FAIL: 33 passed / 1 failed | Portable-agent upgrade regression returned `ok=False`; 551.31 seconds. Root cause is not established by that assertion. Full command in Appendix B. |
| Host Orchestra wrapper tests | PASS: 10 tests | Fresh `extension/test/orchestra-services.test.ts`; fake transport request-shape tests, not live sidecar response or GUI acceptance. |
| `npm.cmd audit --omit=dev --json` | PASS: zero known vulnerabilities | Report covers the selected JavaScript dependency subset, not Python, native code or complete supply-chain assurance. |
| Audit-specific behaviour probes | Reproductions recorded below | Exposes gaps not asserted by existing happy-path tests. |

The older full core run resumed from the preceding task ended with **2,185 passed / one failed**, `test_portability_m16.py::test_upgrade_regression_runs_adapter_tests`, in 7,535.43 seconds. It belongs to an earlier checkout and is historical evidence only. It must not be attributed to the current SHA. Earlier extension/webview success counts also remain historical until rerun against a frozen current tree.

### 3.3 Artifact and assurance evidence

The inspected `dist/meridian-loom-0.1.0.vsix` has SHA-256 **`675247ea7babb35dc2853206f7313a31349f4d7d951101d62875dc33ed426775`**, 278 archive members, and an `orchestra_handlers.py` byte-identical to current source. Therefore the old audit's “handler absent from VSIX” finding is superseded for this local artifact. However, it contains **zero `adapter.yaml` roster manifests** and has the packaging-root issues in GP-031.

`docs/baselines/package/2026-09-18-windows.json` records checksum prefix **`57244792eacf04ab`**, not the inspected package's digest. It cannot prove validation of this package. The stored soak record reports **0.05 hours of 168 required**, explicitly `incomplete`. Stored compatibility/resilience records are Windows-only; the compatibility record itself labels Linux, macOS, and Python 3.12 `not-verified-here`. The installed-package validator explicitly does not open VS Code.

### 3.4 Changes arriving during the audit

The audit continued after the user's “continue” message on 19 September. Other work advanced HEAD through `af82c01` (typed host wrappers), `d4391f6` (handoff documentation), `5d5b2c5` (targeted handler fixes), and `b999821` (previous audit updates). Those changes were read and preserved. At delta review, uncommitted edits also existed in `extension/src/workbench/service.ts`, `shared/ts/workbench.ts`, and `webview/src/workbench/RuntimeStudio.tsx`, adding loop pass-through/actions and controls. These are in-progress inputs, not this audit's implementation or a frozen release candidate.

| Earlier observation | Corrected disposition after delta review |
|---|---|
| 32 methods have no detected host/UI consumer | Host wrappers now exist and the static surface check passes 109/112. Real screen journeys and response validation remain open. |
| Unknown `loop.status` returns fabricated pending | Fixed: now raises a named error; loop-kind lookup now uses an inverse mapping. Unknown `loop.stop` still reports stopped, and actual cancellation remains absent. |
| Queue enqueue / tenant registration do not call persist | Those calls were added, as were stop/replay calls. `queue_tick` still omits persistence; snapshot still excludes admitted/done work and executable continuation context. |
| Memory IDs use randomized Python `hash()` | Fixed to a SHA-256-derived deterministic 32-bit value of delimiter-joined subject/author. Collision/ambiguous encoding, revision identity and fake content digest remain unresolved. |
| No loop GUI controls | In-progress Runtime Studio controls are present. This does not replace stand-in nodes, cancellation or recovery. The handwritten workbench result types also preserve the separate schema disagreement. |
| Previous audit says “Everything on the core lane is done” / “Engineering complete” | Not supported: GP-003/004/006–021 remain substantive core work. Its GAP-105 explanation is also inaccurate: the static gate did detect the initial orphans and now recognizes host wrappers; adding allowlist entries is not the cure for missing GUI journeys. |

Source line references below generally refer to the initial baseline; later insertions may shift them. Symbol/file references remain authoritative. Fresh checks from different moments are explicitly separated; no combined whole-tree green test result is claimed. Appendix A preserves the initial inventory, while this section records the later changed documents/source.

## 4. Findings and required outcomes

Each GP identifier maps one-to-one to an implementation task of the same numeric suffix. “Acceptance” below is required future evidence, not a claim that the evidence exists.

### GP-001 — Release scope and source-of-truth conflict

**P1 · PARTIAL / DECISION · Requirements_Final §§0, 5–10; MVP §§0, 3, 9; post-mvp-plan; user goal.** `mvp-req-final.md` still describes runtime/router/simulation/comprehension as absent while these packages exist. Post-MVP rows say not started despite implementation commits. JIT and futures both originally used M41, and their NFR/SEC/AC namespaces collide. `status.md` contains historical estimates, not a current acceptance ledger.

Define a release contract with every source clause assigned to accepted release scope, future scope, superseded-by-specific-clause, or explicit decision. Preserve canonical M47 mapping for JIT. Broader owner intent must not disappear behind an old MVP deferral; equally, a future experiment must not become a fabricated release blocker without its scope recorded. **Acceptance:** a machine-readable clause register with stable source file/heading/ID, production path, acceptance test, evidence SHA, and disposition; no orphan clauses or unqualified “complete” rows.

### GP-002 — Host consumers added; product consumption and current CI proof remain incomplete

**P1 · PARTIAL / EVIDENCE GAP · FR-M46-01/02, AC-43.** Initial surface coverage and exact-baseline CI failed for 32 new methods. The later `extension/src/orchestra/services.ts` adds host callers and now passes static coverage; its ten mock-transport tests pass. The wrappers return unknown responses and do not establish real screen journeys, runtime schema conformance or a current all-jobs-green CI run. In-progress loop controls are acknowledged in §3.4. See the endpoint register in the implementation plan.

Wire user-needed capabilities through typed host services, stateful screens, and real integration tests. Explicit developer-only methods may have justified exclusions with owners and release scope. Do not add blanket allowlist entries or inert string references to get a green check. **Acceptance:** no undeclared orphan; actual UI action reaches the handler, produces/reads durable evidence, renders errors, and survives reconnect; full CI executes downstream jobs.

### GP-003 — Signed agent card does not authenticate package contents

**P0 · CONFIRMED by reproduction · FR-M16-02/04, FR-M31-10, SEC-12/33.** `portability/__init__.py:230–242` verifies only the signed card. Import at 285–329 never compares the archive payload with the card's `contentDigest`. `adapters/__init__.py:219` accepts a manifest without a digest. The audit retained original card/signature bytes, replaced `agent.py`, removed the manifest digest, and imported the modified package with `valid=True` and no errors.

Authenticate a canonical member manifest covering paths, bytes, sizes, and relevant metadata; bind the adapter manifest, identity, version, and exclusions. Verify all bytes before any destination write. **Acceptance:** tampering, adding/removing a member, manifest substitution, and identity substitution fail before write; legitimate exports, including exclusions, round-trip. Do not execute package code during validation. Existing signature tests must cover payload integrity rather than only signature-field corruption.

### GP-004 — Archive containment and transactional import are unsafe

**P0 · CONFIRMED by reproduction · SEC-12, FR-M16-04/05, FR-M31-03.** `portability/__init__.py:320–327` uses string `startswith` for containment. `../developer-extra/audit-proof.txt` resolves outside `developer` but shares its prefix, so the audit successfully wrote it beside the adapter. Extraction writes before validating all members, has no visible member/expanded-size budget, and can overwrite an existing installation before `registry.plug` validates it.

Use canonical path-component containment, reject traversal/absolute/drive/UNC paths, links, duplicate normalised names and unsafe identifiers, preflight archive size/count/compression limits, and stage imports outside the active adapter directory. Atomically publish only a fully verified and admitted package. **Acceptance:** adversarial archives and simulated failures leave both the destination and siblings unchanged; valid upgrade rollback preserves the prior working adapter. Reuse protections from the more defensive host importer where appropriate; do not assume the Python and host import paths share them.

### GP-005 — Privileged RPCs accept caller assertions as authority

**P1 · CONFIRMED boundary weakness · FR-M12-07, FR-M20, FR-M14-06, FR-M7-11.** `orchestra_handlers.py` consumes `humanOverride`, `actorIsHuman`, `humanApproved`, caller-supplied scores and approval lists. `memory/write` accepted pinned procedural content with `actorIsHuman=True` and an unverified author in the audit probe. `portability/trust` records generic `operator`; it does not resolve the established human principal/role. The generic webview proxy forwards enabled RPCs after tier checking.

Derive authority from host-authenticated context and existing role/revocation policy. Bind approvals to action, subject, revision/digest, expiry, principal and policy version. Tier enablement is availability, not authority. **Acceptance:** forged flags, replayed/stale approvals, revoked principals, wrong roles and machine actors fail without changing state; the normal human flow succeeds and names its evidence. Local stdio limits exposure; no remote-exploit claim is made.

### GP-006 — Contract drift is hidden by weak runtime validation

**P1 · CONFIRMED · FR-M3, FR-M32-09, AC-28.** `loop.start` declares `LoopStatusResult` (`loopId`, `kind`, `state`, `iteration`) but returns `runId`, `status`, `iterations`, `checkpointed`; `loop.stop` returns `stopped`/`was`. `RouterRatioResult` prohibits additional properties while `DependencyRatio.to_dict()` supplies `scope` and `escalationSequence`. `server.py:490–504` does not validate general requests/results against JSON Schema. `_require` mainly checks absence, and only `OrchestraError` is mapped to invalid params.

Make request/result shapes authoritative and enforce boundary validation with bounded payloads, strict types, ranges, enums, identifiers, and consistent errors. **Acceptance:** every registered method has schema-validated real success and invalid-input responses; generated type checks plus wire tests catch deliberate shape mutations; malformed booleans/paths/NaN/negative budgets cannot become privileged input.

### GP-007 — Orchestra completes stand-ins rather than delivery work

**P0 · CONFIRMED · FR-M4, FR-P1…P7, AC-01…04, vision §§2–5.** `orchestra_handlers.py:90–109,361–383` builds `_stand_in_nodes`, visits node names, and returns completed after one pass. `test_orchestra_rpc.py:115–123` asserts this outcome. Bundled `adapters/*/agent.py` are labelled deterministic stand-ins. ACP workbench runs exist separately; no traced production composition connects these loops to those runs and real SDLC outputs.

Implement versioned work packets and real handlers for intake, design, planning, implementation, verification, security and review. Bind eligible independent ACP agents, deterministic tools, worktrees, policy and evidence to each transition. Keep a separately labelled simulation mode. **Acceptance:** a real bounded repository task produces a reviewed change and test evidence through the production entry point; a failed test, missing dependency, rejected gate or unbound runtime prevents completion. Model credentials alone will not fix missing execution wiring.

### GP-008 — Stop/resume and scheduling do not provide real runtime control

**P1 · CONFIRMED / PARTIAL · FR-M4-05/06/08/10, FR-M3-02, FR-M25.** `loop.stop` records an event and returns true even for an unknown run, reproduced by the audit. `server.serve` dispatches synchronously; a future long-running node would block subsequent stop/ping requests. `$/cancel` is ignored. One runner's thread-local node/schema maps are replaced on each `start`, rather than keyed by run. Fan-out width validation is not a global active-run limit. Usage/wall-clock checks occur between graph invocations, with no demonstrated provider/tool cancellation propagation.

Add a run supervisor with per-run context, a responsive control plane, explicit legal transitions, global concurrency and usage accounting, cancellation tokens and process-tree termination. **Acceptance:** stop a genuinely running task, stop twice, stop unknown, cancel during a tool/model call, breach each budget, and resume two interleaved runs without context crossover. Health must report real active-loop state (`server.py:641` currently returns zero).

### GP-009 — Restart restores metadata but not resumable execution

**P1 · CONFIRMED by reproduction · FR-M4-05/06, NFR-42.** `OrchestraState._restore` reconstructs handles; `runner.resume` immediately accesses `self._local.schemas`, which a fresh runner has never initialised. After start → persist → new server → resume, the probe returned JSON-RPC `-32603` with underlying `AttributeError`. The restored status could still say completed. `test_orchestrator_state.py` only saves/restores waiting queue and tenant objects; it never resumes a run.

Persist versioned executable binding descriptors, state schema, gate position, usage and continuation cursor; rebuild callables from trusted registrations. Reject illegal resumes explicitly. **Acceptance:** suspend a real run, kill the sidecar, reopen and approve/resume at the exact continuation without duplicate side effects. Also cover sequential runs on one thread, resume on another worker, unknown schema versions, corrupted snapshots and missing bindings.

### GP-010 — Queue acknowledgements and admitted work are not durable

**P1 · CONFIRMED by reproduction/source · FR-M21, SEC-23, NFR-42.** Initially `queue_enqueue`, `queue_tick`, and `tenancy_register` acknowledged without persisting. The delta adds persistence to enqueue/registration, but not tick. `persist()` still saves only `_waiting`, omitting `_in_flight`, `_done`, agent bindings, repository targets and ordering metadata. After admission and an explicit persist, a new state object had no admitted story. An unregistered tenant was admitted. No queue completion RPC bridges real run completion, so WIP slots/dependencies can remain stuck. More calls to the same incomplete snapshot do not fix this.

Persist transactions before success responses; make enqueue idempotent, validate tenant/dependency identity, record admissions/completions/failures and recover leases after crashes. **Acceptance:** crash after every acknowledgement; maintain exactly the acknowledged state and dependency/WIP rules, release completed slots, reject cycles/duplicate IDs, and never lose or double-run a story.

### GP-011 — Product has separate execution paths with different isolation

**P1 · PARTIAL · FR-M18, FR-M40, FR-P4-07.** Workbench delivery runs through `extension/src/workbench/service.ts`; launch/preflight/worktree functionality lives in a separate run-initiation path. `docs/gui-implementation.md:51–53` explicitly says workbench agents run sequentially in the open workspace, without M40 worktree isolation or cross-window locking. Existing worktree unit tests do not prove this entry point uses worktrees.

Unify draft delivery, palette launch, independent-agent runs and Orchestra scheduling behind one execution service. Resolve approved repository, branch, target scope, worktree and gate policy before spawning. **Acceptance:** each UI/palette entry point operates in its assigned worktree, leaves the main checkout intact, denies out-of-scope edits at the supported enforcement boundary, and handles abort/conflicts/dirty workspaces consistently. Document direct-executable containment limits.

### GP-012 — Native tool endpoint has no working permission population path

**P1 · PARTIAL · FR-M9-01…08, FR-M28.** `OrchestraState.surface` constructs an empty `ToolSurface`; `tools_invoke` invokes it, but the traced production path does not populate permitted tools from an admitted agent and policy. The RPC test proves denial only. `ToolSurface.permit` exists as a library API. A secure always-deny endpoint is not a functional build/test tool layer.

Bind tool schemas and immutable agent/session/packet context, policy-approved grants, working directory and request approval to the invocation service. Keep read/edit/execute distinctions. **Acceptance:** one genuinely permitted read/build/test/edit workflow and each denial case execute through the bus, with truthful exit codes, truncation and audit records; revocation prevents the next action.

### GP-013 — Two agent registries and incomplete probation/hot-plug lifecycle

**P1 · PARTIAL · FR-M5, FR-M15, FR-M31.** The host's 22 Markdown profiles and the Python 14-folder roster use different representations and state. Python `AgentRegistryM5.promote` changes probation to active without a scorecard or human-authority check; handlers instantiate a new M5 wrapper per promotion. Adapter states, version history and in-flight checkpoints are not in the orchestrator snapshot. `unplug` copies caller-supplied metadata; it does not itself stop a running ACP session. `replug` creates a learned directory rather than restoring execution.

Define one durable lifecycle with mappings between portable profile configuration, executable identity, participation, probation, permission autonomy and actual learning job state. Enforce dependency validity and immutable acting versions. **Acceptance:** add/update/remove/activate/deactivate/import/export and unplug/replug run through GUI and runtime; inactive agents get no delivery work; promotion requires real evidence; restart preserves states; failed upgrades retain the previous version.

### GP-014 — Memory, instructions and skills are not one governed execution context

**P1 · PARTIAL · FR-M6, FR-M7-08/13…16, FR-M31-08/09.** Host briefing code binds library content and accepted notes, while `memory/instructions.py` supplies a separate precedence/budget/digest implementation with no located production assembly consumer. Python memory RPCs are unsurfaced. Skill Markdown includes useful stack guidance, but its presence is not proof that required tests, constraints and migrations execute for that stack.

Create a shared context contract for role, skill, repository conventions, trusted instructions, reviewed memory, packet and tool capabilities. Record included and omitted content digests at invocation; prevent untrusted repository/story text from acquiring instruction authority. **Acceptance:** Java/Spring, Python and cloud examples receive the exact intended context; precedence, budget exclusions, changed digests, revoked skills and injected instructions are exercised through a live host session.

### GP-015 — Cost levers neither shape production calls nor safely cache prompts

**P1 · CONFIRMED / PARTIAL · FR-M26-04, FR-M8-15…18.** `OrchestraState.router` constructs `Router` without levers. Even when injected in a library test, `routing.py:206` discards the shaped prompt and records savings. `CostLeverSet._apply_cache` returns only the suffix on a local prefix hit; the audit repeated a short prompt and received an empty prompt plus seven “cached tokens,” with no provider cache handle or reconstructed context. Compaction can leave oversized non-tool text and does not guarantee a complete budgeted request.

Implement request shaping on the actual provider/ACP boundary only where supported. Never remove required context merely because a local hash was seen. Separate estimated token savings, observed provider cache usage, billed savings and unknowns. **Acceptance:** capture actual dispatched bytes for repeated/different prompts, models and Unicode; preserve semantics; enforce full prompt budgets; reconcile savings with observed usage; settings control the real path.

### GP-016 — Learning endpoint reports training without producing a learning job

**P1 · PARTIAL · FR-M14, FR-M15-03/04, D5/D6.** `trainer_train` checks caller-supplied `openPhases`, calls `harvest_signals`, discards the result and returns `ran=True`. The audit obtained this response with empty params. `trainer_promote` trusts numeric scores supplied by the caller; the safety filter is a set of text patterns, not an evaluated safety regression suite. Existing learning UI records reviewed notes rather than running this backend.

Implement real scheduled/explicit learning jobs: collect eligible signals, generate declarative candidates, evaluate incumbent/candidate on pinned tasks, retain artifacts, request authenticated promotion, and support rollback. Derive active-story exclusion from runtime state. **Acceptance:** a deactivated agent visibly moves through waiting/running/review/failed states, produces a replayable evaluation, cannot self-promote, and its accepted delta changes a subsequent invocation. Do not promise model-weight training.

### GP-017 — Decision/calibration/replay evidence is ephemeral and incomplete

**P2 · PARTIAL · FR-M13-01…10.** Decisions and replay recipes live in `_decisions`/`_decision_replays` dictionaries, omitted from persistence; IDs restart at `dec-1`. The record RPC returns only a ledger sequence while ablation requires a decision ID. Calibration capture has no traced outcome-feedback product flow. The replay recipe dispatches an engine action; this does not establish reproducible ablation of a hosted model's decision. Some gate input booleans are caller assertions (GP-005).

Persist stable decision IDs and immutable input/model/context/evidence references; return the ID; derive outcome calibration from actual results. Replays must state precisely what was replayed and separate deterministic evidence from narrative. **Acceptance:** record → restart → lookup → ablate succeeds using pinned inputs, with negative controls and model/version labels; unavailable replay is explicit; high-blast-radius gate policy consumes verified evidence.

### GP-018 — Interface contract generation/gating is an unused skeleton

**P1 · PARTIAL / CONFIRMED false-positive gate · FR-M22-02, FR-M29-02.** `interface_contracts.py` has no located production callers. It writes generic GET paths from repository names. `interface_contract_gate` checks only `is_file`; the audit wrote “not an API contract” to the expected file and received `passed=True`. Unit tests do not demonstrate producer/consumer compatibility or a Review transition invoking the gate.

Generate or import actual versioned API/message schemas from design artifacts; validate schemas and both consumer/provider compatibility before allowing dependent work/review. Bind artifact digest to the story revision. **Acceptance:** invalid, stale, empty or incompatible contracts block the production multi-repository flow; compatible contracts produce executable contract tests; documentation-gate evidence is also connected.

### GP-019 — Named tenancy is a registry, not end-to-end tenant routing

**P1 · PARTIAL · SEC-23, FR-M21/22, ECO-04/05/07.** `tenancy_register` records a path; Orchestra builders continue to resolve the handshake workspace for ledger, memory, tools and adapters. Queue admission does not resolve the tenant. Existing tests demonstrate separate library roots, not a routed multi-tenant request. Single-workspace deployment is a narrower, legitimate boundary.

Either ship and accurately document one trusted workspace per sidecar, or carry validated tenant context across every service, artifact, cache, signer and export. **Acceptance:** two-tenant integration/adversarial tests prove no cross-resolution through queue, memory, adapter packages, logs, tool paths or approvals; unknown tenant fails before admission; restore retains isolation. Do not advertise shared-service tenant isolation from the registry test alone.

### GP-020 — Subprocess limits and containment claims need enforcement

**P1 · PARTIAL · FR-M9-04/05/07, SEC-14/32, NFR-42.** `tools/surface.py:120–163` buffers complete stdout/stderr with `capture_output=True` before truncation; the display cap is not a memory limit. `subprocess.run(timeout=...)` alone is not evidence of descendant termination. The plain-Python bridge launches arbitrary code and exposes a separate guarded-tool function; it cannot force arbitrary code to use that function. Environment scrubbing and declared egress checks are useful but are not an OS sandbox.

Stream bounded output, cancel process trees, define inherited-handle/env rules, and choose enforceable containment per supported platform where required. Keep honest boundary labels if full isolation is outside a release. **Acceptance:** output flood stays within memory budget; spawned descendants stop on timeout/revoke; denied network/path operations are either actually blocked or explicitly uncontained under the supported threat model, with no misleading sandbox claim.

### GP-021 — Memory identity and new analytics bypass evidence conventions

**P2 · CONFIRMED / PARTIAL · FR-M7, FR-M41-07…14, FR-M8-17.** Initial `_entry_from_wire` IDs used process-randomised `hash`; the delta fixes process determinism but keeps only 32 bits of a digest over delimiter-joined subject/author. Distinct field tuples can encode identically, and content/tier/tenant/revision semantics need definition. `memory_retrieve` still returns the entry ID as its digest rather than a content digest. `harvest_signals` queries at most 1,000 rows without a coverage envelope. `trusted_signers` scans at most 100,000 policy rows, which needs explicit ordering/full-history handling for revocation. Router “model_call” rows are written for permissions, before an actual call is demonstrated; ratio reporting can therefore count authorisations as executions.

Use stable collision-resistant identities/content hashes, full-history cursor iteration and the existing coverage vocabulary. Distinguish requested/authorised/dispatched/completed calls. **Acceptance:** restart-stable memory references; changed content changes digest; >1,000-signal and long trust/revocation histories reconcile; incomplete populations report gaps; ratios match actual executions and do not count denied/never-dispatched calls.

### GP-022 — Routed GUI surfaces still fall short of specified workflows

**P1 · PARTIAL · VIGUIX §10/11/15/16, gaps_guix, FR-M46-02.** Inspected notices explicitly identify gaps: `CodeMapStudio.tsx:34` is directory membership/attribution rather than semantic dependencies; `ComprehensionStudio.tsx:20` is authored notes; `DiffStudio.tsx:34` stores annotations without applying/staging/rework; `ReplayStudio.tsx:17` only browses a ledger timeline. `DiagramStudio.tsx:51` still says loop endpoints are unimplemented even though they are now registered. New Runtime Studio controls are in progress (§3.4); operation/learning/portfolio/configuration workflows still require end-to-end validation. In the inspected in-progress controls, `loopBusy` disables every control, including Stop while Start is awaiting a response; tier labels are not themselves visibility or authorization checks.

Use the screen matrix below to implement the actual workflow behind each advertised surface. Preserve usable existing components, explicit preview isolation, tier hiding, loading/empty/error/stale states and keyboard operation. **Acceptance:** each required screen has a user journey against the packaged production backend, including a failure/reconnect case; navigation or document-save-only shells cannot close runtime requirements.

### GP-023 — Scenario parity is weaker than AC-28

**P1 · CONFIRMED limitation · FR-M32-04/09, AC-28.** `scripts/check_scenario_parity.py:32–45,118–144` sends only selected read methods to production, skips mutating live steps, and checks selected top-level production keys. It does not render the webview, compare complete responses/semantics, validate every schema, or establish per-screen parity. It can pass despite GP-006.

Run each scenario against disposable production workspaces and the simulation transport, including mutations, errors, notifications and time controls. Compare canonical state/results modulo explicitly allowed nondeterminism and replay recorded responses through real components. **Acceptance:** wrong nested fields, lost notifications, contradictory statuses and broken mutation handlers all fail the harness; the claimed screen set is explicit and completely represented.

### GP-024 — Golden corpus proves admission but little product behaviour

**P2 · EVIDENCE GAP · FR-M27-03, AC-15/16, D10.** Fresh `check_golden` passed a single story containing three ledger entries. That is useful regression infrastructure, not evidence of all loops, rework, budgets, agents, stacks or error recovery. Replay of stored ledger bytes is also different from re-executing the delivery pipeline without models.

Admit meaningful recorded scenarios: greenfield and brownfield changes, rejected work, drift, cancellation, crash resume, migration, package tamper, multiple agents/stories and supported stacks. **Acceptance:** per-scenario requirements, input/cassette provenance, expected artifacts/evidence, network/model-call prohibition and intentional tamper negatives; CI fails when a meaningful production behaviour regresses, not only when a stored root changes.

### GP-025 — Full testing claim is not supported by current evidence

**P1 · EVIDENCE GAP · MP3/MP5/MP7, NFR-42, FR-M46.** The exact-commit CI skips the suites. Targeted tests and older green counts cannot replace one complete, identified run. Tests for stop, persistence and upgrade contain weak success assertions (GP-008/009/030); this audit's probes exposed failures outside those assertions. Rust verifier execution is optional in development, and there is no release-path cargo step in the inspected workflow.

Run sequential, reproducible whole-tree correctness validation on a frozen commit, plus meaningful new regression tests and package/host journeys. Retain failures and expected skips with reasons. **Acceptance:** SHA, environment, commands, counts, exit codes, durations and artifacts are recorded; no suite is silently skipped; security/control mutations demonstrate the relevant tests can fail. Coverage percentages alone do not establish requirement coverage.

### GP-026 — Clean installed-editor startup is not demonstrated

**P1 · EVIDENCE GAP / PARTIAL · FR-M1/M3, MVP-R1/R2, AC-69/71.** `validate-package.mjs:28` explicitly does not open VS Code. Tests alias `vscode` to a mock. The interpreter probe now checks eight required import modules, which is an improvement, but dependencies are installed into an external interpreter and the package validator uses a pre-provisioned Python environment. Base-tier startup imports Orchestra dependencies through server registration.

Automate an actual extension-host/editor smoke test from the final VSIX, with a clean profile and independently prepared runtime. Verify missing-dependency remediation, supported versions, untrusted workspaces, first run, editor-area panel, protocol mismatch recovery and reload. **Acceptance:** install → activate → provision/diagnose → real RPC → uninstall succeeds without the source checkout or warm development dependencies. Offline/managed-machine constraints must be documented and tested where claimed.

### GP-027 — Supported-platform labels exceed recorded rehearsal evidence

**P1 · EVIDENCE GAP · FR-M3-11, FR-M44-08…10, NFR-42, AC-50/54.** Stored results only prove selected Windows checks. Some matrix rows refer to manifest tests rather than an installed editor of that version. CI runs the full OS shape on main/schedule/manual, not every PR; the inspected current run never reached it. macOS core is excluded and only Python 3.12 is configured in CI despite a 3.11 support row.

Create a release matrix tied to exact editor/runtime/OS/remote combinations and evidence. Run native and supported remote rehearsals, or narrow support claims. **Acceptance:** Windows/Linux/macOS and SSH/WSL/container/Codespaces claims each have appropriate real-run evidence or explicit unsupported disposition; a minimum VS Code version is tested as an editor, not just read from a manifest.

### GP-028 — Soak, performance and recovery targets remain unproven at release

**P1 · EVIDENCE GAP · NFR-01…27, NFR-33/42/43, FR-M46-07/08.** The committed soak smoke is 0.05/168 hours; recovery evidence covers one of four configurations. Current CI performance job did not run. Timing from a loaded audit workstation is not a valid baseline. GUI large-history rendering, queue throughput and new Orchestra memory growth need measurement.

Run the specified 168-hour soak and fault-recovery matrix on a pinned candidate, with workloads representative of observation plus active execution/learning. Measure startup, p95 queries, event lag, RSS, handles, disk growth and UI responsiveness on named hardware. **Acceptance:** thresholds and complete samples are retained; no acknowledged evidence/work is lost, recovery meets the specified objective, and short harness tests are never labelled a completed soak.

### GP-029 — Accessibility and GUI assurance require current packaged evidence

**P2 · EVIDENCE GAP · VIGUIX §15/16, FR-M46-05, AC-54.** Existing DOM/assistive tests and historical axe results are useful; `docs/gui-implementation.md` explicitly limits them and does not claim installed-VSIX visual or screen-reader validation. Dense one-line TSX in modeling surfaces makes state/race/focus review difficult. New backend workflows will change UI states.

Validate keyboard-only workflows, focus restoration, screen-reader announcements, contrast, zoom, reduced motion, error recovery and large datasets in all supported themes/densities and the editor panel. **Acceptance:** current-SHA automated reports plus manual assistive records for the critical journeys; graphs have equivalent navigable data; no action requires colour, pointer-only interaction or inaccessible canvas content.

### GP-030 — Upgrade/rollback and backup guarantees exceed their tests

**P1 · PARTIAL / CONFIRMED test weakness · FR-M30-03, NFR-42, AC-71.** `test_upgrade_path.py:37–46` changes `PRAGMA user_version` on a current-schema ledger, while migrations use `schema_migrations`; it asserts the module constant is >=5. This does not create an old database or prove a migration. Deployment and support documents disagree about old-version readability after migration. No current package-level proof covers all new queue/decision/adapter/workbench state and key recovery.

Use immutable fixtures created by actual older released code and persistent keys. Test forward migration, interruption, refusal of unsupported downgrade, recovery/export, consistent SQLite/blob/key backup, and post-erasure restore. **Acceptance:** old rows/heads remain valid, no acknowledged work disappears, unsupported schemas fail clearly, and the documented rollback procedure is exactly what the tests demonstrate.

### GP-031 — Packaging and resource lookup omit the Python roster/defaults

**P1 · CONFIRMED / PARTIAL · FR-M31-02/11, FR-M32, D4, MP7.** The inspected VSIX contains the 22-profile library but no `adapters/*/adapter.yaml` from the 14-folder Python roster. `OrchestraState.adapter_roots()` and its router fallback use `Path(__file__).resolve().parents[2] / adapters|policy`; in a checkout that is `core/adapters|policy`, and in the VSIX it is `sidecar/adapters|policy`, whereas the packager stages policy under `extension/policy`. Existing bootstrap masks some fallback errors by copying defaults.

Define one runtime resource resolver for source and packaged layouts, including prebuilt adapters, phase policy, schemas and intended golden/scenario resources. Choose whether both rosters are needed and unify their lifecycle (GP-013). **Acceptance:** extract the final VSIX into a clean directory and discover the intended built-ins, load policies and start the supported runtime without repository-relative fallbacks; verify every required resource by behavior, not a filename substring alone.

### GP-032 — Supply-chain evidence is incomplete

**P1 · PARTIAL · ECO-03, FR-M44, FR-M50-04, AC-62/70.** `core/pyproject.toml` pins direct dependencies but not the full transitive environment. Licence/notices/BOM sweeps primarily enumerate declared dependencies and can skip unresolved Python metadata. The artifact contains only the top-level `LICENSE.txt` among licence-named members; full third-party/font attribution texts require review. CI has no explicit dependency vulnerability gate, Python audit, mandatory verifier build, or release provenance/attestation job. `contracts` invokes Python golden/parity checks before an explicit setup-python/install-core step.

Make clean builds reproducible with locked/hashes-verified transitive runtime inputs; inventory bundled versus externally installed components accurately; retain applicable notices/licence texts; add calibrated vulnerability, secret and build-provenance checks. Install declared dependencies in every CI job that imports them. **Acceptance:** clean runner builds/scans/tests without ambient packages; SBOM includes the full distributed closure and separates external runtimes; unresolved licences are not release passes; advisory exceptions have owners/expiry and evidence. This is an engineering completeness finding, not a legal conclusion.

### GP-033 — Enterprise governance has explicit unfinished enforcement boundaries

**P1 for enterprise claim · DEFERRED / PARTIAL · FR-M42-01…03, SEC-22/31, AC-45/46, D37/D38.** Editor governance and asserted git identity exist; SCM-required enforcement and enterprise identity-provider support are not established by them. `identity/__init__.py` has an explicit unsupported provider seam. A user outside Meridian can bypass an editor-only check. The current docs disclose this, which is good.

For an enforced enterprise offering, implement and rehearse repository-native required checks, head/digest-bound approvals, trusted identity, revocation/freshness and separation of duties at the actual merge boundary. **Acceptance:** merge outside the editor is blocked for failing/stale evidence; revoked identities cannot approve; unsupported installations explicitly say advisory. Customer branch-protection configuration remains an external acceptance step, not something a unit test can simulate into completion.

### GP-034 — SDLC connectors, CI feedback and delivery outputs are incomplete

**P1/P2 by accepted scope · PARTIAL / DEFERRED · FR-M19/M21…26/M29/M30, FR-P1…P9.** Read-only integration probes, PR intake/conflicts, manual documents and registry/queue primitives exist. They are not the complete work-item write-back, CI failure-to-rework loop, review-response loop, linked cross-repository PR delivery, generated docs/runbooks, scheduled maintenance or model-comparison harness described by the full specifications. `deploy_execution` explicitly raises under D7.

Retain a clause-level backlog for each phase and connector. Implement provider adapters with idempotency, pagination, credential scope, retries, rate limits and ledger correlation, then connect real phase outputs/gates. **Acceptance:** controlled integration repositories show issue → work packet → worktree → tests/scans → reviewed PR → CI/rework → authorised merge/report, with linked artifacts and failure paths. Release/Operate execution stays plans-only unless that product decision changes; do not count it as implemented execution.

### GP-035 — JIT harness track remains largely future work

**P2 · DEFERRED / MISSING PRODUCT PATH · canonical M47, jit requirements/implementation, D44.** No complete harness record/retrieval/benchmark/synthesis product path was located. Existing skills/templates are not equivalent to the proposed JIT harness lifecycle. The post-MVP plan explicitly allows J1/J2 while later synthesis remains evidence-gated; the earlier blanket “all JIT waits for D44” interpretation is too broad.

Implement the accepted artifact/retrieval baseline with canonical IDs, provenance, matching, bounded retrieval, evaluation and hit-rate evidence before optional synthesis. **Acceptance:** stable harness resolution at packet start, honest misses, pinned tests and budget limits; J3/J4 cannot self-authorise from a completion checkbox. Report this as remaining full-vision scope rather than a regression in the Recorder.

### GP-036 — Competitive assurance modules are not all delivered

**P2 · PARTIAL / DEFERRED · M48…M52, AC-64…68, NFR-49…53.** The repo has useful provenance interoperability, receipts, witness/attestation helpers and confidence labelling. These do not establish an enforced MCP gateway, workload attestation, standard-tool DSSE verification, or full-history 30/60/90-day outcome attribution. CP2–CP4 remain distinct obligations in `post-mvp-plan.md`; names in a module or a generic seam are insufficient.

Preserve separate tasks for tool-call lineage/enforcement declarations, attested workload identity, interoperable envelopes/witnesses and longitudinal outcomes. **Acceptance:** each accepted claim has a real integration/control-boundary test; censored/missing outcomes stay unknown; interop preserves source confidence; optional external infrastructure remains owner/customer dependent. Do not add unrelated speculative features to close the current release.

### GP-037 — Status, claims and operator documentation contradict current reality

**P2 · CONFIRMED · MP5, NFR-55, AC-69/71.** Old audit statements are both too negative (handler absent) and too positive (persistence complete). `docs/claims.md` still withdraws the root roster on the assertion that it does not exist; it now exists. The security contact points to `github.com/meridianloom/meridian-loom`, while the manifest repository is `Vibe-A-Thon/meridianloom`. Deployment backup text is misplaced under later sections with duplicate numbering; rollback statements conflict with SUPPORT. `check-claims` passes based on named test existence.

Update claims from the corrected release ledger; bind them to executed evidence and artifact digest. Repair contact/support links and operational instructions, retain historical entries as dated evidence, and remove false “complete” conclusions. **Acceptance:** reader can install, diagnose, back up, upgrade, report a vulnerability and understand limitations using only shipped docs; links and commands are checked; stale test references cannot imply a current pass.

### GP-038 — Open-core commercial boundary is unspecified

**P2 · DECISION / COMMERCIAL GAP · owner direction: open core with paid features; D19; ECO-01/02.** A MIT licence and extension manifest metadata now exist; this supersedes “no licence” claims. Root/workspace `private` flags are not themselves a blocker to VSIX packaging. Capability tiers are configuration flags, not paid entitlements. No reviewed core/paid boundary, separate distribution/licensing arrangement, entitlement lifecycle or commercial support offering is established.

Prepare a concrete open-core/paid packaging and capability proposal, then obtain the product owner's commercial decision where necessary. Specify offline behaviour, trial/expiry, data portability, key management and support commitments only for the chosen offering. **Acceptance:** distributable artifacts and customer-facing terms match the approved boundary; switching a local tier setting cannot grant a feature claimed as entitlement-protected. Do not retroactively change licences or invent prices/contracts as an engineering shortcut.

### GP-039 — Brownfield coverage gate can confuse references with tested behaviour

**P1 · PARTIAL · FR-M38-01…05, AC-35, AMD-M38.** `ComprehensionEngine.record` sets `covered=bool(test_files)`. `_references` treats a target filename substring inside a file whose path contains `test|spec` as a test relationship. This can mean a comment or unrelated name, not executed coverage; characterization is similarly based on marker text. The GUI does not consume the engine yet.

Label heuristic adjacency as inferred, then bind risk/coverage gates to real test discovery/results and the required characterization/mutation/contract evidence. Resolve source paths inside the authorised repository and index incrementally. **Acceptance:** an unrelated test comment cannot satisfy coverage; stale/failed/unrun tests do not become a pass; risky uncovered code blocks the production edit path; every risk factor carries evidence and missingness.

### GP-040 — State ownership and code concentration create change risk

**P2 · PARTIAL / EVIDENCE GAP · NFR reliability, FR-M3/M30, MP4.** `server.py` is 5,512 lines, `workbench/service.ts` 2,694, and new handlers directly access private ledger/queue/registry members. Thread-local execution context is not a durable run model; multiple stores independently own agents, learning, documents and runtime state. Workbench atomic replace protects against partial files but does not prove cross-window lost-update protection. Many modeling components compress complex handlers into single lines.

Extract cohesive application services behind existing contracts, document ownership and transaction boundaries, add schema versions/migrations and concurrency controls, and format complex UI code for review. **Acceptance:** two windows editing the same workspace cannot silently overwrite acknowledged changes; lifecycle cleanup is deterministic; refactors preserve behavioral tests and contain no parallel replacement architecture. Prioritise correctness fixes before cosmetic restructuring.

### GP-041 — Live product demonstration is still an unclosed acceptance gate

**P1 · EVIDENCE GAP plus engineering dependencies · AC-01…04/24, DEMO paths A/B.** Fixture ACP and real stdio subprocess tests are valuable, but no current artifact-bound live coding-agent story demonstration was found. A credentials-only explanation is incomplete because GP-007/011/012/014 must first connect the path. The Recorder demo and generated study templates are not proof of autonomous delivery.

After deterministic contract tests pass, run a bounded live provider task in an isolated demonstration repository using the installed VSIX. Retain runtime identity/version, prompts/context digests, permissions, costs/unknowns, actual diff, tests, approvals, cancellation and independently verified export. **Acceptance:** an unfamiliar user follows the runbook to a verified deliverable, and a deliberately failing task is reported failed. Runtime/account provisioning is an external prerequisite; do not invent a successful run.

### GP-042 — Human/customer measurements remain distinct from engineering completion

**P2 / claim-specific gate · EVIDENCE GAP / EXTERNAL · F2/MV5, NFR-28, AC-24/50, FR-M46-15…17.** First-value/assistive/two-editor/effectiveness protocols exist, but measured novice use, the preregistered twenty-story study and two-editor/two-SCM customer evidence are not replaced by unit tests. The repository itself says effectiveness is unmeasured. A second editor needs actual support before a two-editor exercise can succeed.

Assign accountable owners, prerequisites, recruitment/data agreements, collection scripts, analysis and publication criteria. **Acceptance:** preregistered real evidence including adverse/missing outcomes and a human decision; no unsupported productivity/quality/ROI claim. These do not automatically block an honestly scoped technical preview, but they do block claims that require those measurements and remain outstanding against the user's complete-product goal.

## 5. Coverage matrix — all module and phase families

This is an audit disposition, not an assertion that every clause in a family shares one completion level. GP-001 requires clause-level reconciliation before a percentage can be issued.

| Family | Existing substance and remaining goal gap | Findings |
|---|---|---|
| M1 Extension host | Real activation/commands/editor panel; installed-host and minimum-version evidence incomplete | 026,027 |
| M2 Dashboard | Real React workbench; workflow completeness and assurance remain | 002,022,029 |
| M3 Sidecar/IPC | Real stdio and supervision; contract/cancel/control-plane issues | 006,008,026 |
| M4 Loops | LangGraph substrate; production stand-ins and broken recovery | 007–010 |
| M5 Agent registry | Host/Python stores diverge; lifecycle/persistence incomplete | 013 |
| M6 Skills | Ten useful profiles; executable stack acceptance not established | 014,034 |
| M7 Memory | Real storage/retrieval library and reviewed notes; context/identity integration gaps | 005,014,021 |
| M8 Router | Permission/classification logic; no complete governed provider path | 005,015,021 |
| M9 Tools | Gates and subprocess helpers; grants/limits/containment incomplete | 012,020 |
| M10 Ledger | Substantial tested crypto/integrity substrate; release/security assurance still required | 025,030,032 |
| M11 Viewer | Real evidence rendering/verification; full correlated runtime journey incomplete | 017,022 |
| M12 Governance | Real policy/merge gate; new RPC authority and external enforcement gaps | 005,033 |
| M13 XAI | Decision/ablation/calibration primitives; persistent usable flow incomplete | 017 |
| M14 Trainer | Declarative learning library; no complete job/evaluation workflow | 016,021 |
| M15 Onboarding | Import/binding UI; scored durable admission incomplete | 013,016 |
| M16 Portability | Real host import/export and signed-card library; Python integrity/path defects | 003,004,013 |
| M17 KPIs | Substantial ledger-derived metrics; actual outcome integration/release evidence | 021,028,036 |
| M18 Isolation | Worktree library; inconsistent product entry-point use | 011 |
| M19 Connectors | Read-only integrations; write-back/full intake as scoped | 034 |
| M20 Identity/roles | Asserted identities/role logic; new privileged paths and enterprise identity | 005,033 |
| M21 Portfolio | Queue library; durable scheduler/completion missing | 010,019 |
| M22 Multi-repo | Target records/skeleton contracts; linked delivery and valid contracts incomplete | 018,019,034 |
| M23 CI/merge | PR intake and evidence; live CI/rework/SCM enforcement incomplete | 033,034 |
| M24 Editor/chat | Provenance editor integration exists; full chat/action clauses need register | 026,034 |
| M25 Human steering | Working ACP steering; hunk actions and loop control incomplete | 008,011,022 |
| M26 Economics | Spend/estimation plus lever library; dispatch/savings correctness incomplete | 015,021,034 |
| M27 Replay | Real cassette verifier; meaningful corpus and product replay incomplete | 017,023,024 |
| M28 Intelligence | Parsing/LSP/lexical primitives; production CodeMap/reuse integration incomplete | 012,022,039 |
| M29 Documentation | Manual documents/library gate; automated outputs/gate consumers incomplete | 018,034 |
| M30 Operations | Doctor/uninstall/repair helpers; recovery/scheduling/release evidence incomplete | 008–010,028,030,040 |
| M31 Adapters | ACP host plus native registry; security/lifecycle/resource consistency gaps | 003,004,013,031 |
| M32 Simulation | Scenarios/golden scripts now exist; semantic and UI parity incomplete | 023,024 |
| M33 Engine | Useful deterministic capabilities; routed investment/value and provider flow | 007,012,015,042 |
| M34 ACP host/registry | Real hosting/pinning/permissions; qualified live runtime evidence needed | 013,026,041 |
| M35 Observers | Five observer families; drift/platform/recovery validation needed per claim | 025,027,028 |
| M36 Recorder/tiering | Functional foundation; enabled tier does not equal paid authorisation | 005,038 |
| M37 Trust analytics | Real analytics; complete populations and outcome evidence needed | 021,028,042 |
| M38 Brownfield | Heuristic comprehension library; coverage gate and UI integration incomplete | 022,039 |
| M39 Spend | Real ledger series/pricing; distinguish estimates and billed/saved cost | 015,021 |
| M40 Initiation | Preflight/worktree path exists; workbench/Orchestra handoff incomplete | 007,011 |
| M41 Evidence coverage | Earlier pagination/coverage work exists; new features need same discipline | 021,025 |
| M42 Enforcement assurance | Honest declarations; SCM and identity completion needed for stronger claims | 005,033 |
| M43 Durability/portability | Receipts/archive/collector/verifier; current recovery/interoperability evidence | 025,030,036 |
| M44 Supply chain/vendors | Pins/identity/retention; payload auth, platform qualification, reproducibility | 003,027,032 |
| M45 Change economics | Library metrics; authoritative merge/outcome association incomplete | 021,034,036 |
| M46 Product assurance | Baseline CI red; local static gate now passes; full candidate acceptance still incomplete | 001,002,023–029,037,042 |
| M47 JIT (formerly JIT M41) | Artifact/retrieval and later synthesis track not complete | 035 |
| M48 Tool-call governance | Core permission mediation is narrower than an enforced gateway | 020,033,036 |
| M49 Workload identity | Executable identity is narrower than workload attestation | 036 |
| M50 Standards evidence | BOM/helpers present; transitive/standard-tool assurance incomplete | 032,036 |
| M51 Longitudinal outcomes | Complete 30/60/90-day evidence not established | 036,042 |
| M52 Provenance interoperability | Readers/export/reconciliation exist; preserve format/confidence limits | 025,036,037 |
| FR-P1…P3 | Real intake/design/planning artifacts need production agent transitions | 007,014,034 |
| FR-P4 | Work-packet-scoped code, migrations/dependencies and change controls | 007,011,012 |
| FR-P5…P7 | Actual tests/scans/review and failed-result rework, not supplied booleans | 005,007,018,034 |
| FR-P8/P9 | Plans/runbooks may proceed; deploy execution intentionally D7-gated | 034 |
| NFR/SEC/AC/ECO and amendments | Retained by source-qualified clause IDs; cross-cutting release matrix below | 001,025–042 |

## 6. GUI acceptance inventory

All specified surfaces remain in scope accounting even when multiple surfaces share one component. Grouping does not waive their distinct interactions.

| VIGUIX surface(s) | Remaining acceptance beyond an existing route/view |
|---|---|
| 10.1 Command Center; 10.2 Floor; 10.3 Weave; 10.4 Agents Watch | Actual runtime/phase/loop state, errors/paused agents, queue contention, live correlation and accessible spatial/list equivalents. |
| 10.5 Dojo; 10.14 Skill Forge; 10.15 Onboarding; 10.16 Inspector | Real evaluation jobs, binding validation, scored probation, authoritative lifecycle, versioned context/trace and safe promotion/rollback. |
| 10.6 Gates; 10.27 Decision Stream; 10.28 Steer | Authenticated revision-bound actions, real loop suspension/resumption, evidence details, durable clarify/rework history. |
| 10.7 Ledger; 10.29 Replay | Linked run/commit/artifact journeys; cassette/time-travel semantics distinct from timeline browsing; pagination and coverage. |
| 10.8 CodeMap; 10.9 Loop Graph | Actual dependency/risk/test relations and executable loop state, not directory membership or an editable planning graph. |
| 10.10 Architecture; 10.11 UML; 10.12 Flow | Claimed extraction/drift/source synchronisation and approval workflows, or explicitly scoped authored diagrams. |
| 10.13 Config; 10.31 Routing; 10.38 Runtime | Effective policy/config preview, actual routing/cost levers, health, cancellation/recovery and actionable diagnostics. |
| 10.17 Diff | Apply/stage/partial acceptance/rework with stale-head checks and actual file effects; annotations alone are partial. |
| 10.18 Spec; 10.19 Packet Board; 10.25 Story Hub; 10.26 Portfolio | Versioned artifacts consumed by the scheduler, acceptance traceability, dependencies, WIP and multi-repo ownership. |
| 10.20 Verification; 10.21 Security; 10.34 Pipeline | Real tool/CI/scanner results with tested SHA, failure gates and actionable rework; manual plans are not executions. |
| 10.22 KPI; 10.37 Calibration; 10.47 Trust; 10.48 Spend | Full-history evidence/coverage, observed versus inferred costs and outcomes, user-visible missingness. |
| 10.23 Exchange; 10.43 Adapter Bay | Signed payload verification, safe transactional import, trust/revocation, executable identity, cross-workspace portable behaviour. |
| 10.24 Focus; 10.39 Notifications; 10.40 First Run; 10.41 Keyboard; 10.42 Editor | Packaged-editor navigation, focus, keyboard, persistent notifications, remote readiness and assistive journeys. |
| 10.30 Memory; 10.44 Instructions | Real tiers, contradiction review, provenance, included/cut digests, precedence, retention and invocation linkage. |
| 10.32 Roles; 10.33 Connectors; 10.35 Repositories | Authority/revocation, configured provider scope, real worktrees and cross-repo consistency. |
| 10.36 Documentation/report | Evidence-derived report and publication controls, version/freshness, documentation gate linkage. |
| 10.45 Recorder; 10.46 External Agents | Existing useful paths need current packaged-platform proof and retention/drift/error trials. |
| 10.49 Comprehension; 10.50 Launch; 10.51 Preflight | Engine-backed evidence, truthful readiness and one consistent isolated execution handoff. |
| 10.52 Harness; 10.53 Tool-call lineage; 10.54 Reconciliation; 10.55 Outcomes | Explicit future/partial scope; implement only against actual M47–M52 services and evidence. Reconciliation already has real functionality. |
| Cross-cutting X/E/A/P systems | Map every source-qualified interaction clause to its screen; verify tier absence, vendor/confidence labels, sanitisation, responsive layout, themes, motion, shortcut conflicts, optimistic concurrency and error states. |

## 7. Release acceptance gates

| Gate | Required proof | Current disposition |
|---|---|---|
| R1 Scope/claims | Accepted clause inventory, no hidden omissions, supported configurations and commercial boundary | OPEN |
| R2 Security | GP-003/004 fixed; new authority/validation paths adversarially tested | FAIL |
| R3 Functionality | Real SDLC journey, independent and pluggable agents, inactive learning, real control flow | PARTIAL |
| R4 Recovery | Durable acknowledged state, exact continuation, migrations/backups and failure rehearsals | FAIL/PARTIAL |
| R5 Build/test | Exact-SHA CI with all mandatory jobs green, no unexplained skips, verified package digest | Baseline FAIL; newer full candidate UNPROVEN |
| R6 Deployment | Clean installed editor, real runtime provisioning, claimed platform/remote matrix | UNPROVEN |
| R7 Quality | Current performance, 168-hour soak, accessibility and support/runbooks | UNPROVEN/PARTIAL |
| R8 Claims requiring people | Live demo, novice timing, study, customer enforcement and multi-editor evidence as claimed | OPEN / EXTERNAL |

Engineering can fix code, build harnesses, prepare datasets/runbooks and execute local/CI validation. It cannot fabricate provider credentials, customer SCM administration, a seven-day elapsed run, user-study participants, commercial decisions or real outcome measurements. These must have owners and remain explicitly open. A scoped pilot can be considered separately; it must not be labelled the completed full product.

## Appendix A — Markdown source inventory

The inventory below records every tracked Markdown document at the baseline, its line count and normalized-text SHA-256 prefix. “Same as” denotes identical UTF-8 text after newline normalization; historical copies that differ remain separate. File indexing does not endorse a document's completion claims. The shipped `AGENTS.md`/`SKILL.md` files are product content, not root-repository operating instructions.

| Source | Lines | Text SHA-256 prefix | Duplicate disposition |
|---|---:|---|---|
| [BUILD-OPTIMIZATION-REPORT.md](<BUILD-OPTIMIZATION-REPORT.md>) | 96 | `0c437ab9c8ab` | Distinct source |
| [BUILD_STATE.md](<BUILD_STATE.md>) | 305 | `a5c7063cf19a` | Distinct source |
| [DECISIONS.md](<DECISIONS.md>) | 168 | `6c1444598a3c` | Distinct source |
| [DEMO.md](<DEMO.md>) | 367 | `f8e4018654d4` | Distinct source |
| [KIMI_MASTER_PROMPT.md](<KIMI_MASTER_PROMPT.md>) | 366 | `733a73dd56d5` | Distinct source |
| [README.md](<README.md>) | 105 | `be7d91cd7ebf` | Distinct source |
| [Requirements-implementation.md](<Requirements-implementation.md>) | 707 | `72ad4238b4f3` | Distinct source |
| [Requirements_Final.md](<Requirements_Final.md>) | 1565 | `8a24adecbdbc` | Distinct source |
| [SECURITY.md](<SECURITY.md>) | 89 | `9492b83e3e20` | Distinct source |
| [THIRD-PARTY-NOTICES.md](<THIRD-PARTY-NOTICES.md>) | 53 | `42f59533db40` | Distinct source |
| [VIGUIX_Final.md](<VIGUIX_Final.md>) | 1839 | `e873ffb4c200` | Distinct source |
| [adapters/analyst/instructions/AGENTS.md](<adapters/analyst/instructions/AGENTS.md>) | 4 | `2d3643ddffee` | Distinct source |
| [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) | 6 | `50ca939df614` | Distinct source |
| [adapters/analyst/skills/SKILL.md](<adapters/analyst/skills/SKILL.md>) | 5 | `d9f2a16325a3` | Distinct source |
| [adapters/architect/instructions/AGENTS.md](<adapters/architect/instructions/AGENTS.md>) | 4 | `4c628d59e0da` | Distinct source |
| [adapters/architect/learned/README.md](<adapters/architect/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/architect/skills/SKILL.md](<adapters/architect/skills/SKILL.md>) | 5 | `74eb0e45e5c9` | Distinct source |
| [adapters/chief-orchestrator/instructions/AGENTS.md](<adapters/chief-orchestrator/instructions/AGENTS.md>) | 4 | `7ec0661c21f8` | Distinct source |
| [adapters/chief-orchestrator/learned/README.md](<adapters/chief-orchestrator/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/chief-orchestrator/skills/SKILL.md](<adapters/chief-orchestrator/skills/SKILL.md>) | 5 | `cb77b832d837` | Distinct source |
| [adapters/developer/instructions/AGENTS.md](<adapters/developer/instructions/AGENTS.md>) | 4 | `e4a8e3ab4d9d` | Distinct source |
| [adapters/developer/learned/README.md](<adapters/developer/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/developer/skills/SKILL.md](<adapters/developer/skills/SKILL.md>) | 5 | `ad6a5d0841af` | Distinct source |
| [adapters/front-end-engineer/instructions/AGENTS.md](<adapters/front-end-engineer/instructions/AGENTS.md>) | 4 | `f5ef642450ae` | Distinct source |
| [adapters/front-end-engineer/learned/README.md](<adapters/front-end-engineer/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/front-end-engineer/skills/SKILL.md](<adapters/front-end-engineer/skills/SKILL.md>) | 5 | `7647162785a2` | Distinct source |
| [adapters/governance/instructions/AGENTS.md](<adapters/governance/instructions/AGENTS.md>) | 4 | `8ece57f0d426` | Distinct source |
| [adapters/governance/learned/README.md](<adapters/governance/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/governance/skills/SKILL.md](<adapters/governance/skills/SKILL.md>) | 5 | `5f47dc69c1a8` | Distinct source |
| [adapters/phase-orchestrator/instructions/AGENTS.md](<adapters/phase-orchestrator/instructions/AGENTS.md>) | 4 | `7d25ebbea76c` | Distinct source |
| [adapters/phase-orchestrator/learned/README.md](<adapters/phase-orchestrator/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/phase-orchestrator/skills/SKILL.md](<adapters/phase-orchestrator/skills/SKILL.md>) | 5 | `022a66229c1f` | Distinct source |
| [adapters/qa-engineer/instructions/AGENTS.md](<adapters/qa-engineer/instructions/AGENTS.md>) | 4 | `dd6799bdfae4` | Distinct source |
| [adapters/qa-engineer/learned/README.md](<adapters/qa-engineer/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/qa-engineer/skills/SKILL.md](<adapters/qa-engineer/skills/SKILL.md>) | 5 | `4daaf915de3e` | Distinct source |
| [adapters/qa-lead/instructions/AGENTS.md](<adapters/qa-lead/instructions/AGENTS.md>) | 4 | `d95ccbb100a2` | Distinct source |
| [adapters/qa-lead/learned/README.md](<adapters/qa-lead/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/qa-lead/skills/SKILL.md](<adapters/qa-lead/skills/SKILL.md>) | 5 | `eed782585107` | Distinct source |
| [adapters/reviewer/instructions/AGENTS.md](<adapters/reviewer/instructions/AGENTS.md>) | 4 | `c7ffeca28018` | Distinct source |
| [adapters/reviewer/learned/README.md](<adapters/reviewer/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/reviewer/skills/SKILL.md](<adapters/reviewer/skills/SKILL.md>) | 5 | `e2c4949c4652` | Distinct source |
| [adapters/scrum-master/instructions/AGENTS.md](<adapters/scrum-master/instructions/AGENTS.md>) | 4 | `a23154b43965` | Distinct source |
| [adapters/scrum-master/learned/README.md](<adapters/scrum-master/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/scrum-master/skills/SKILL.md](<adapters/scrum-master/skills/SKILL.md>) | 5 | `16dfd1f305ba` | Distinct source |
| [adapters/security/instructions/AGENTS.md](<adapters/security/instructions/AGENTS.md>) | 4 | `ba9ae58554b0` | Distinct source |
| [adapters/security/learned/README.md](<adapters/security/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/security/skills/SKILL.md](<adapters/security/skills/SKILL.md>) | 5 | `c02dbaa0531d` | Distinct source |
| [adapters/tech-lead/instructions/AGENTS.md](<adapters/tech-lead/instructions/AGENTS.md>) | 4 | `09c9be6b5b31` | Distinct source |
| [adapters/tech-lead/learned/README.md](<adapters/tech-lead/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/tech-lead/skills/SKILL.md](<adapters/tech-lead/skills/SKILL.md>) | 5 | `3de42969a597` | Distinct source |
| [adapters/xai/instructions/AGENTS.md](<adapters/xai/instructions/AGENTS.md>) | 4 | `4deeef58ef5d` | Distinct source |
| [adapters/xai/learned/README.md](<adapters/xai/learned/README.md>) | 6 | `50ca939df614` | Same as [adapters/analyst/learned/README.md](<adapters/analyst/learned/README.md>) |
| [adapters/xai/skills/SKILL.md](<adapters/xai/skills/SKILL.md>) | 5 | `9cfea6dba53b` | Distinct source |
| [audit-1-k-g-impl.md](<audit-1-k-g-impl.md>) | 259 | `e8b3db44aad6` | Distinct source |
| [audit-1-k-g-req.md](<audit-1-k-g-req.md>) | 424 | `8e3a290de7e0` | Distinct source |
| [core/tests/fixtures/analytical/template/skill-pack/README.md](<core/tests/fixtures/analytical/template/skill-pack/README.md>) | 3 | `e271525a5cb4` | Distinct source |
| [docs/DEPLOYMENT.md](<docs/DEPLOYMENT.md>) | 219 | `390fc3d68ad2` | Distinct source |
| [docs/SECURITY-AND-DATA.md](<docs/SECURITY-AND-DATA.md>) | 286 | `318aa2195ef1` | Distinct source |
| [docs/SUPPORT.md](<docs/SUPPORT.md>) | 90 | `792415d541bc` | Distinct source |
| [docs/baselines/assistive/PROTOCOL.md](<docs/baselines/assistive/PROTOCOL.md>) | 83 | `7a53523aeb5e` | Distinct source |
| [docs/baselines/cold-start/PROTOCOL.md](<docs/baselines/cold-start/PROTOCOL.md>) | 76 | `370261ad12ae` | Distinct source |
| [docs/baselines/evidence-gate/PROTOCOL.md](<docs/baselines/evidence-gate/PROTOCOL.md>) | 113 | `b5c301ba0991` | Distinct source |
| [docs/baselines/first-value/PROTOCOL.md](<docs/baselines/first-value/PROTOCOL.md>) | 85 | `66dbb107721d` | Distinct source |
| [docs/baselines/two-editors/PROTOCOL.md](<docs/baselines/two-editors/PROTOCOL.md>) | 82 | `c1976f71323f` | Distinct source |
| [docs/claims.md](<docs/claims.md>) | 164 | `b56ac61d4181` | Distinct source |
| [docs/evidence-gate.md](<docs/evidence-gate.md>) | 135 | `182019b9fdcc` | Distinct source |
| [docs/gui-implementation.md](<docs/gui-implementation.md>) | 331 | `3aee4a9c2609` | Distinct source |
| [docs/meridian-ledger-trailer.md](<docs/meridian-ledger-trailer.md>) | 113 | `077d850b8538` | Distinct source |
| [docs/open-ledger-spec/01-entry-schema.md](<docs/open-ledger-spec/01-entry-schema.md>) | 55 | `55485787d5af` | Distinct source |
| [docs/open-ledger-spec/02-canonical-json.md](<docs/open-ledger-spec/02-canonical-json.md>) | 91 | `d34020db77e5` | Distinct source |
| [docs/open-ledger-spec/03-hash-chain.md](<docs/open-ledger-spec/03-hash-chain.md>) | 45 | `b73f487c4b83` | Distinct source |
| [docs/open-ledger-spec/04-merkle-tree.md](<docs/open-ledger-spec/04-merkle-tree.md>) | 58 | `8f53dcd83d5b` | Distinct source |
| [docs/open-ledger-spec/05-signed-tree-head.md](<docs/open-ledger-spec/05-signed-tree-head.md>) | 43 | `3b0d6883a863` | Distinct source |
| [docs/open-ledger-spec/06-blob-envelope.md](<docs/open-ledger-spec/06-blob-envelope.md>) | 57 | `6690a372fcfe` | Distinct source |
| [docs/open-ledger-spec/07-bundle-format.md](<docs/open-ledger-spec/07-bundle-format.md>) | 135 | `8fcd797376ca` | Distinct source |
| [docs/open-ledger-spec/08-verification-algorithm.md](<docs/open-ledger-spec/08-verification-algorithm.md>) | 94 | `97345c342ed9` | Distinct source |
| [docs/open-ledger-spec/README.md](<docs/open-ledger-spec/README.md>) | 48 | `512ebd63bf3d` | Distinct source |
| [docs/open-ledger-spec/verify.md](<docs/open-ledger-spec/verify.md>) | 59 | `08a77c1ea231` | Distinct source |
| [docs/spec/Requirements-implementation.md](<docs/spec/Requirements-implementation.md>) | 707 | `72ad4238b4f3` | Same as [Requirements-implementation.md](<Requirements-implementation.md>) |
| [docs/spec/Requirements_Final.md](<docs/spec/Requirements_Final.md>) | 1565 | `8a24adecbdbc` | Same as [Requirements_Final.md](<Requirements_Final.md>) |
| [docs/spec/VIGUIX_Final.md](<docs/spec/VIGUIX_Final.md>) | 1839 | `e873ffb4c200` | Same as [VIGUIX_Final.md](<VIGUIX_Final.md>) |
| [docs/spec/evidence-portability.md](<docs/spec/evidence-portability.md>) | 202 | `3b125bfb49c2` | Distinct source |
| [docs/spec/futures.md](<docs/spec/futures.md>) | 99 | `00f6b9387b7e` | Distinct source |
| [docs/spec/gaps-requirements.md](<docs/spec/gaps-requirements.md>) | 244 | `11234034eb45` | Distinct source |
| [docs/spec/gaps_guix.md](<docs/spec/gaps_guix.md>) | 239 | `9770e047c070` | Distinct source |
| [docs/spec/gaps_guix_implementation.md](<docs/spec/gaps_guix_implementation.md>) | 530 | `1e168a550cfa` | Distinct source |
| [docs/spec/gaps_implementation.md](<docs/spec/gaps_implementation.md>) | 591 | `6b260a203467` | Distinct source |
| [docs/spec/gaps_initiation.md](<docs/spec/gaps_initiation.md>) | 259 | `af8cf1139854` | Distinct source |
| [docs/spec/meridian-ledger-trailer.md](<docs/spec/meridian-ledger-trailer.md>) | 186 | `4227c2874414` | Distinct source |
| [docs/spec/viguix-implementation.md](<docs/spec/viguix-implementation.md>) | 790 | `9262af453ce8` | Distinct source |
| [docs/spec/vision.md](<docs/spec/vision.md>) | 539 | `64e703b1f133` | Distinct source |
| [docs/upstream/vscode-acp-issue.md](<docs/upstream/vscode-acp-issue.md>) | 42 | `89bf69d6d23f` | Distinct source |
| [extension/CHANGELOG.md](<extension/CHANGELOG.md>) | 319 | `b1c1263b4cbe` | Distinct source |
| [extension/README.md](<extension/README.md>) | 253 | `96eaf615b9f1` | Distinct source |
| [extension/library/agents/analyst-agent.md](<extension/library/agents/analyst-agent.md>) | 53 | `9b0bd80baa7d` | Distinct source |
| [extension/library/agents/api-contract-agent.md](<extension/library/agents/api-contract-agent.md>) | 39 | `a6e913dedceb` | Distinct source |
| [extension/library/agents/architect-agent.md](<extension/library/agents/architect-agent.md>) | 48 | `dcda5d10c314` | Distinct source |
| [extension/library/agents/cloud-aws-agent.md](<extension/library/agents/cloud-aws-agent.md>) | 39 | `0460e6a8395d` | Distinct source |
| [extension/library/agents/database-migration-agent.md](<extension/library/agents/database-migration-agent.md>) | 39 | `4a8bca1010d5` | Distinct source |
| [extension/library/agents/developer-agent.md](<extension/library/agents/developer-agent.md>) | 51 | `1086638df743` | Distinct source |
| [extension/library/agents/dotnet-service-agent.md](<extension/library/agents/dotnet-service-agent.md>) | 39 | `62c082c2de51` | Distinct source |
| [extension/library/agents/frontend-agent.md](<extension/library/agents/frontend-agent.md>) | 51 | `fa3b9c0be15c` | Distinct source |
| [extension/library/agents/go-service-agent.md](<extension/library/agents/go-service-agent.md>) | 39 | `36308267b9c8` | Distinct source |
| [extension/library/agents/java-fullstack-agent.md](<extension/library/agents/java-fullstack-agent.md>) | 39 | `2d0eb026fab8` | Distinct source |
| [extension/library/agents/java-spring-boot-agent.md](<extension/library/agents/java-spring-boot-agent.md>) | 39 | `07a441e834df` | Distinct source |
| [extension/library/agents/node-service-agent.md](<extension/library/agents/node-service-agent.md>) | 39 | `3d4cf8751f42` | Distinct source |
| [extension/library/agents/python-service-agent.md](<extension/library/agents/python-service-agent.md>) | 39 | `809a4c17c08e` | Distinct source |
| [extension/library/agents/qa-engineer-agent.md](<extension/library/agents/qa-engineer-agent.md>) | 48 | `cdb42a89b1b2` | Distinct source |
| [extension/library/agents/qa-lead-agent.md](<extension/library/agents/qa-lead-agent.md>) | 50 | `287165b0b9c5` | Distinct source |
| [extension/library/agents/react-frontend-agent.md](<extension/library/agents/react-frontend-agent.md>) | 39 | `721b1ae29ccb` | Distinct source |
| [extension/library/agents/release-agent.md](<extension/library/agents/release-agent.md>) | 51 | `a54471ae8ee1` | Distinct source |
| [extension/library/agents/reviewer-agent.md](<extension/library/agents/reviewer-agent.md>) | 51 | `b889cc065d69` | Distinct source |
| [extension/library/agents/scrummaster-agent.md](<extension/library/agents/scrummaster-agent.md>) | 48 | `26c85d908c89` | Distinct source |
| [extension/library/agents/security-agent.md](<extension/library/agents/security-agent.md>) | 54 | `25bd1e8bbdd0` | Distinct source |
| [extension/library/agents/sre-agent.md](<extension/library/agents/sre-agent.md>) | 51 | `1ee4cc9fb177` | Distinct source |
| [extension/library/agents/techlead-agent.md](<extension/library/agents/techlead-agent.md>) | 48 | `aecc55591216` | Distinct source |
| [extension/library/instructions/definition-of-done.md](<extension/library/instructions/definition-of-done.md>) | 30 | `5f0ba7f13b6d` | Distinct source |
| [extension/library/instructions/engineering-standards.md](<extension/library/instructions/engineering-standards.md>) | 44 | `1c6d6dd39a2f` | Distinct source |
| [extension/library/instructions/review-checklist.md](<extension/library/instructions/review-checklist.md>) | 43 | `0b5993cd762b` | Distinct source |
| [extension/library/instructions/security-baseline.md](<extension/library/instructions/security-baseline.md>) | 45 | `b2ab18c7184d` | Distinct source |
| [extension/library/skills/api-contract-first.md](<extension/library/skills/api-contract-first.md>) | 44 | `583c3fcce579` | Distinct source |
| [extension/library/skills/aws-iac.md](<extension/library/skills/aws-iac.md>) | 45 | `e8bc301edc18` | Distinct source |
| [extension/library/skills/dotnet-service.md](<extension/library/skills/dotnet-service.md>) | 42 | `920ded87c35c` | Distinct source |
| [extension/library/skills/golang-service.md](<extension/library/skills/golang-service.md>) | 44 | `d61e81be80a7` | Distinct source |
| [extension/library/skills/java-fullstack.md](<extension/library/skills/java-fullstack.md>) | 42 | `793ae53348f7` | Distinct source |
| [extension/library/skills/java-spring-gradle.md](<extension/library/skills/java-spring-gradle.md>) | 44 | `c3834b760e8d` | Distinct source |
| [extension/library/skills/node-service.md](<extension/library/skills/node-service.md>) | 44 | `091b47c0e0b3` | Distinct source |
| [extension/library/skills/python-service.md](<extension/library/skills/python-service.md>) | 47 | `467d1075622d` | Distinct source |
| [extension/library/skills/react-frontend.md](<extension/library/skills/react-frontend.md>) | 43 | `bc9fd183ed7e` | Distinct source |
| [extension/library/skills/sql-migration.md](<extension/library/skills/sql-migration.md>) | 45 | `d74bbc6910bc` | Distinct source |
| [extension/src/acp/UPSTREAM.md](<extension/src/acp/UPSTREAM.md>) | 93 | `5561072e75a0` | Distinct source |
| [futures-implementation.md](<futures-implementation.md>) | 639 | `b4257c2fc386` | Distinct source |
| [futures.md](<futures.md>) | 193 | `85bbe292b2f9` | Distinct source |
| [futures_requirements.md](<futures_requirements.md>) | 374 | `89b04d035e20` | Distinct source |
| [gaps-requirements.md](<gaps-requirements.md>) | 244 | `11234034eb45` | Same as [docs/spec/gaps-requirements.md](<docs/spec/gaps-requirements.md>) |
| [gaps_guix.md](<gaps_guix.md>) | 239 | `9770e047c070` | Same as [docs/spec/gaps_guix.md](<docs/spec/gaps_guix.md>) |
| [gaps_guix_implementation.md](<gaps_guix_implementation.md>) | 530 | `1e168a550cfa` | Same as [docs/spec/gaps_guix_implementation.md](<docs/spec/gaps_guix_implementation.md>) |
| [gaps_implementation.md](<gaps_implementation.md>) | 591 | `6b260a203467` | Same as [docs/spec/gaps_implementation.md](<docs/spec/gaps_implementation.md>) |
| [gaps_initiation.md](<gaps_initiation.md>) | 259 | `af8cf1139854` | Same as [docs/spec/gaps_initiation.md](<docs/spec/gaps_initiation.md>) |
| [jit-impl.md](<jit-impl.md>) | 387 | `4eb0707a5c0f` | Distinct source |
| [jit-requirements.md](<jit-requirements.md>) | 305 | `aa7c2d6d8a9d` | Distinct source |
| [md files/Requirements-Additions.md](<md files/Requirements-Additions.md>) | 477 | `208cafc63618` | Distinct source |
| [md files/Requirements-implementation.md](<md files/Requirements-implementation.md>) | 758 | `941c4f383e36` | Distinct source |
| [md files/Requirements.md](<md files/Requirements.md>) | 681 | `fcb6851a468c` | Distinct source |
| [md files/Requirements_Final.md](<md files/Requirements_Final.md>) | 1325 | `cbbc20611b25` | Distinct source |
| [md files/VIGUIX.md](<md files/VIGUIX.md>) | 894 | `562d77a0eebe` | Distinct source |
| [md files/VIGUIX_Final.md](<md files/VIGUIX_Final.md>) | 1721 | `02eafeff60ee` | Distinct source |
| [md files/VIGUIX_GAPS.md](<md files/VIGUIX_GAPS.md>) | 632 | `32d467ef0cae` | Distinct source |
| [md files/viguix-implementation.md](<md files/viguix-implementation.md>) | 735 | `ad395fe73981` | Distinct source |
| [md files/vision.md](<md files/vision.md>) | 470 | `d1fc7a7a7d65` | Distinct source |
| [mvp-impl-plan.md](<mvp-impl-plan.md>) | 1047 | `c4ae1dc8e425` | Distinct source |
| [mvp-req-final.md](<mvp-req-final.md>) | 1021 | `c8224065654d` | Distinct source |
| [post-mvp-plan.md](<post-mvp-plan.md>) | 70 | `5dc4dddc12e8` | Distinct source |
| [status.md](<status.md>) | 2439 | `d077b8fa54df` | Distinct source |
| [viguix-implementation.md](<viguix-implementation.md>) | 790 | `9262af453ce8` | Same as [docs/spec/viguix-implementation.md](<docs/spec/viguix-implementation.md>) |
| [vision.md](<vision.md>) | 539 | `64e703b1f133` | Same as [docs/spec/vision.md](<docs/spec/vision.md>) |
| [webview/FONTS.md](<webview/FONTS.md>) | 20 | `d3da15d415e1` | Distinct source |

## Appendix B — Audit execution close-out

The audit performed read-only analysis and temporary-directory behavioral probes; it did not implement the remediation plan, rebuild a release candidate, publish, commit, or deploy. Other sessions' source changes were preserved. The current task's deliverables are this file and `audit-1-gp-g-impl.md`.

The focused core command was:

```powershell
python -m pytest core/tests/test_orchestra_rpc.py core/tests/test_orchestrator_state.py core/tests/test_levers_m26.py core/tests/test_interface_contracts.py core/tests/test_upgrade_path.py core/tests/test_portability_m16.py -q --tb=short
```

Observed result: **33 passed, one failed, 551.31 seconds, exit 1**. Failure: `core/tests/test_portability_m16.py::test_upgrade_regression_runs_adapter_tests`, line 155, expected `result["ok"] is True` but received false. The assertion output did not establish whether the nested Python/pytest process failed because of code, environment, timeout or another reason. Capture `output_tail`, exit status and interpreter details during remediation; do not silently count it as infrastructure-only or assume the fix.

Later focused host command, from `extension/`: `node ../node_modules/vitest/vitest.mjs run test/orchestra-services.test.ts` — **one file / ten tests passed**, 20.79 seconds, exit 0. `npm.cmd run typecheck --workspace=webview` also exited 0 on retry. These are later-working-tree checks; they are not a single frozen-commit product run. JavaScript production dependency audit: zero known vulnerabilities, 15 production dependencies reported, exit 0. Full extension/webview/core suites, fresh build/package, live editor and soak were **not** completed as part of this audit.

Reproduction observations retained in the findings:

| Probe | Observed behavior | Interpretation/limit |
|---|---|---|
| Signed package payload substitution | Original card/signature retained; replaced `agent.py`, removed optional manifest digest; importer returned valid with no errors | Confirmed unsigned payload acceptance; replacement code was never executed |
| Sibling-prefix archive traversal | `../developer-extra/audit-proof.txt` was written beside the intended `developer` directory | Confirmed containment failure, confined to an audit temporary directory |
| Loop start | Stand-in nodes returned completed after one iteration | Confirms execution path, not a real delivered software change |
| Stop unknown loop | Returned stopped true | False acknowledgement; not actual cancellation |
| Restart then resume | JSON-RPC internal error from missing thread-local schemas | Confirmed restoration defect; terminal-state rejection is also required |
| Queue admit then explicitly persist/reload | Admitted work absent after restore; unknown tenant admitted | Snapshot and validation gaps; later enqueue persistence does not address them |
| Pinned memory with caller human flag | Accepted with unverified supplied author | Local caller authority boundary issue, not an Internet exposure claim |
| Empty trainer request | Returned ran true | No retained learning/evaluation job demonstrated |
| Repeated short cached prompt | Empty shaped prompt and seven cached tokens | Unsafe local cache semantics without provider context handle |
| Invalid contract text in expected path | Gate returned passed | File presence substituted for contract validity |

The combined runtime probe produced these observations before its cleanup failed on Windows because the sidecar had changed the current directory and retained monitored resources. It is not reported as a wholly passing harness. The separate signed-package/traversal probe completed with exit 0. Implement permanent isolated regression tests with explicit shutdown/current-directory restoration; temporary audit helpers are not shipped acceptance tests.

The later source delta was reviewed for its actual changes, not assumed to inherit the initial results. The original 157-document inventory above remains tied to the initial baseline. Updated `BUILD_STATE.md`, `audit-1-k-g-req.md` and `audit-1-k-g-impl.md` were additionally read during delta review; their newer completion claims are assessed in §3.4 and GP-037.

**Final audit conclusion:** the full-product goal is not met. The 42 findings are grouped engineering/assurance obligations, not 42 equally sized work units or a completion percentage. The companion contains 42 matching implementation tasks, dependency waves, endpoint ownership and acceptance evidence rules. Production readiness must be reevaluated against a frozen implemented candidate after those obligations are resolved or explicitly scoped by the owner.
