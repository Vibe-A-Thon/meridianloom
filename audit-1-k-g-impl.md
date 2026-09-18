# Audit 1 — Kimi Gap Implementation Plan

**Companion to `audit-1-k-g-req.md`.** Every task cites its gap(s), requirement IDs, files, and acceptance evidence. Sequencing is dependency-first; nothing rewrites working code.

---

## 1. Implementation Strategy

**Dependency-first sequencing.** The single P1 structural gap — the Orchestra/F4+ layer is unreachable — gates everything downstream (scenario parity, golden CI, every "partial" consumer). Fix the seam first, per-module after.

**Stabilization, not rewrites.** The pattern is already proven: a module enters the contract in `shared/schema/methods.json`, both generated consumers regenerate, a handler lands in `server.py` (or a per-module handler file per ARCH-GAP-02), the host service calls it, the webview surfaces it, and an integration test proves the full path. Repeat that pattern per module.

**Security-first.** The two security improvements (BEFORE-INSERT trigger; seed precedence) are small, isolated, and precede new wiring so the new surfaces start on the hardened baseline.

**Feature completion via wiring, not re-implementation.** PART-* items need consumers, not rewrites. The roster's deterministic stand-ins stay until demo path B binds a runtime — per their manifests' own honest statement.

**Testing strategy.** Each task lands with unit tests plus one integration test over the real path; the adversarial corpus gains fixtures for any new security-relevant seam; contract drift check covers every new method.

---

## 2. Implementation Phases

### Phase 0 — Stabilization (SEC-GAP-01, NEW-GAP-E)

#### TASK-001 — Gapless-insert trigger for the ledger
**Gap:** SEC-GAP-01. **Requirement:** FR-M10-01. **Priority:** P2. **Files:** `core/meridian_core/ledger/schema.py`, `core/tests/adversarial/corpus_batch1.py`, `core/tests/test_ledger_*.py`.

**Current state:** UPDATE/DELETE triggers ABORT; a raw forged INSERT is detected only by verify (corpus fixture CHAIN-INSERT_FORGED asserts detection).
**Required state:** the write path refuses a forged raw INSERT (seq must equal MAX(seq)+1 and prev_hash must equal the current tip); verify remains as the second layer.
**Implementation steps:** add a BEFORE INSERT trigger that RAISEs when `NEW.seq != (SELECT COALESCE(MAX(seq),0)+1 FROM ledger_entry)` or `NEW.prev_hash != current tip hash`; migration version bump; the corpus fixture flips its expectation from KIND_DETECTED to KIND_BLOCKED.
**Security:** closes the last write-path gap without weakening the chain. **Error handling:** IntegrityError with FR-M10-01 message. **Testing:** updated corpus fixture + a positive-path append test (facade inserts unaffected).
**Acceptance:** corpus fixture asserts the write-time refusal; full ledger suites green. **Completion evidence:** test name + commit hash.

#### TASK-002 — Ledger signing seed precedence
**Gap:** NEW-GAP-E. **Requirement:** FR-M10-04/key hygiene. **Priority:** P3. **Files:** `core/meridian_core/collector.py`, `core/meridian_core/server.py`, `DECISIONS.md`.

**Current state:** host handshake seed (authoritative) and collector seed file are independent.
**Required state:** one documented order — provisioned handshake seed wins; the collector seed is used only headlessly and only when the workspace ledger has never been signed by another key; a second signer for an existing chain is refused.
**Steps:** on ledger open, compare stored signer public key with the resolved provider's; refuse on mismatch with a named error; collector documents the rule. **Testing:** mismatch/refusal and agree/accept tests. **Acceptance:** refusal test green; decision recorded.

---

### Phase 1 — Integration seam (GAP-001)

#### TASK-010 — Contract registration for Orchestra surfaces
**Gap:** GAP-001 (contract half). **Requirements:** FR-M4/8/9/28/7/38/31/13/16/14, SEC-23. **Priority:** P1. **Files:** `shared/schema/methods.json`, regenerate `shared/ts/bus-types.ts`, `shared/py/bus_types.py`; `npm run check:contracts`.

**Current state:** 78 registered methods; no Orchestra surfaces. **Required state:** the contract gains, per module, the minimal honest entry points: `loop/start`, `loop/resume`, `loop/status`, `loop/replay` (M4); `router/requestModelCall`, `router/dependencyRatio` (M8); `tools/invoke` (M9, already permissioned); `memory/retrieve`, `memory/write`, `memory/layered` (M7); `comprehension/record`, `comprehension/gate` (M38); `adapters/discover`, `adapters/plug`, `adapters/unplug`, `adapters/promote` (M31); `decisions/record`, `decisions/ablate`, `decisions/gate` (M13); `portability/export`, `portability/import`, `portability/diff` (M16); `trainer/train`, `trainer/promote`, `trainer/rollback` (M14); `tenancy/register`, `queue/enqueue`, `queue/tick` (C5); `annotations/add`, `issues/record` (C6); `simulation/serve`, `simulation/timeControl`, `golden/run` (M32/M27).
**Steps:** author each method def with $defs hoisted (generator rule); regenerate; green drift check. **Testing:** contract shape unit tests (params/result), drift check. **Acceptance:** `check:contracts` green; every method has a $defs entry with required/optional fields.

#### TASK-011 — Handlers + host integration per module
**Gap:** GAP-001 (handler half). **Priority:** P1. **Depends:** TASK-010. **Files:** new `core/meridian_core/handlers_<module>.py` per module (per ARCH-GAP-02, do NOT grow server.py); `server.py` registry imports; `extension/src/services` callers as applicable.

**Current state:** handler table is one dict in server.py. **Required state:** per-module handler files export a `{method: handler}` map; `server.py` merges them at boot; each handler delegates to the module (engine/router/runtime/tools/memory/comprehension/adapters/decisions/portability/trainer/tenancy/differentiation/simulation). Ledger-first discipline: handlers that change state record before returning (FR-M10-08 pattern).
**Steps:** (1) extract handler registration into per-module modules with a `register(server) -> dict` convention; (2) implement each module's handlers with typed params; (3) host service methods for the calls the workbench needs; (4) integration tests per module driving the real RPC over the real JSON-RPC framing. **Error handling:** protocol error codes (INVALID_PARAMS, TIER_DISABLED, LEDGER_UNAVAILABLE) reused; unknown method → -32601 as today. **Observability:** handlers log method + seq. **Testing:** per-module integration suite + one end-to-end test per module through `SidecarServer.handle_message`. **Acceptance:** each module's methods callable over the bus; tests named; `check:contracts` green. **Completion evidence:** integration test names + commit.

#### TASK-012 — Wire the existing consumers
**Gap:** PART-002/003/004/005 (consumers). **Priority:** P2. **Depends:** TASK-011. **Files:** `core/meridian_core/router/routing.py` consumers (engine dispatch call sites), `core/meridian_core/runtime/runner.py` host resume path, briefing assembly (host `launch.ts` → memory/instructions), ledger viewer join (blame → trailer → range).
**Acceptance:** each partial item has its consumer wired + test. **Evidence:** per-item test name.

---

### Phase 2 — Simulation parity + golden CI (GAP-002, GAP-005, GAP-003)

#### TASK-020 — Materialize the ten scenarios
**Gap:** GAP-005. **Requirement:** FR-M32-04. **Priority:** P2. **Depends:** TASK-010. **Files:** `core/meridian_core/simulation/__init__.py`, new `simulation/scenarios/*.py` (or the repo's `simulation/scenarios/` dir per layout).
**Current state:** `SCENARIO_NAMES` constant; no payloads. **Required state:** each named scenario is a `Scenario` with real `ScenarioStep`s whose canned responses carry the data each screen needs (the ten FR-M32-04 families). **Testing:** each scenario replays and produces its ledger entries with `replay_of` tags; a screen-data coverage test asserts every workbench query a scenario names is answerable by its canned responses. **Acceptance:** 10 scenarios replay; per-screen queries answered.

#### TASK-021 — AC-28 parity harness
**Gap:** GAP-002. **Priority:** P1. **Depends:** TASK-020 + GUI session (screens). **Files:** `scripts/check-scenario-parity.mjs`, `core/tests/test_scenario_parity.py`, `scripts/check-demo-package.mjs` (parallel).
**Current state:** contract-drift check passes; scenarios unrun. **Required state:** every screen's queries are run against `SimulationCore` and against the production sidecar with identical cassettes, byte-identical answers modulo timestamps. **Testing:** the parity runner is the test; CI job runs it. **Acceptance:** parity job green for the ten scenarios on both backends. **Evidence:** CI run id + test names.

#### TASK-022 — Golden corpus admission + CI
**Gap:** GAP-003. **Requirement:** FR-M27-03, AC-16, D10. **Priority:** P2. **Depends:** TASK-020. **Files:** `golden/EDB-12345/` (story, cassette, expected_root), `scripts/check-golden.mjs`, CI workflow entry.
**Current state:** `run_golden` exists; no corpus folders; no CI. **Required state:** `golden/EDB-12345/` admits by folder with a real recorded cassette and expected root; the CI job runs `run_golden` for every folder; refresh is `meridian corpus refresh` semantics via the CLI (collector). **Testing:** golden test fails on tampered cassette (already proven at unit level — extend to the corpus). **Acceptance:** CI step green with one real corpus entry. **Evidence:** CI run + corpus folder contents.

---

### Phase 3 — Partial completion (PART-*)

#### TASK-030 — Router escalation into policy (PART-002)
Wire `DependencyRatio.breached` escalation to the governance engine's decision path: a breached ceiling produces a `policy_update` proposal awaiting human approval, never an auto-policy change. Files: `core/meridian_core/router/routing.py`, `core/meridian_core/governance/engine.py`, handler per TASK-011. **Acceptance:** breach → proposal recorded with pending state; approval flips it; tests cover both.

#### TASK-031 — Host gate resume (PART-003)
Workbench approval surface calls `loop/resume` with the approved snapshot. Files: handler (TASK-011), `webview/src/workbench/governance/Gates.tsx` (parallel session owns — coordinate). **Acceptance:** suspend→approve→resume→complete over the real bus; integration test in core; host test where present.

#### TASK-032 — Briefing consumes Instruction Library (PART-004)
Host launch path assembles briefing via `InstructionLibrary.assemble` (budgeted, digest-recorded). Files: `extension/src/adapters/launch.ts` (parallel session owns — coordinate), `core/meridian_core/memory/instructions.py` (already digests). **Acceptance:** a run's ledger entry carries the instruction digests (FR-M7-15 already recorded per assembly; now per launch). **Evidence:** integration test.

#### TASK-033 — Blame → trailer → range join (PART-005)
Ledger viewer surfaces the trailer's `seq`+root and links to the entry range; `attrib/blame` output joins the trailer. Files: workbench ledger screen (parallel session), `core/meridian_core/server.py` handler join. **Acceptance:** an agent-authored line resolves blame → trailer → verified range in one flow; test at core + host.

#### TASK-034 — Adapter onboarding wizard (PART-006)
Manifest-driven wizard writing a validated adapter folder, admitted via `adapters/plug` (probation). Files: `extension/src/workbench/**` (parallel session), `core/meridian_core/adapters/__init__.py` (validator exists). **Acceptance:** wizard output passes registry validation and enters probation; round-trip test.

#### TASK-035 — MCP egress enforcement declaration (PART-001)
Keep the allow-list declared-and-recorded; the pause action becomes a real ledger `policy_update` + tool-surface refusal; host-side kernel/firewall enforcement is recorded as out-of-scope-with-reason (SEC-32 honesty). Files: `core/meridian_core/tools/surface.py`, server handler. **Acceptance:** an out-of-list egress attempt is refused at the tool gate and ledger-recorded with the AC-29 label; the residual limitation is documented.

---

### Phase 4 — Security hardening

#### TASK-040 — MCP client identity digest (SEC-GAP-03)
Where the host can digest the MCP client binary (it spawned it), the digest rides the `mcp/invoke` identity block; otherwise the `asserted` reason stands. Files: `extension/src/mcp/server.ts` (parallel session), `shared/schema/methods.json` (identity block extension), `core/meridian_core/server.py`. **Acceptance:** digest present when derivable; absent states reason; corpus fixture added.

#### TASK-041 — Tenant-scoped sidecar (SEC-GAP-04)
The TenantRegistry drives sidecar state root selection per workspace; no shared defaults. Files: `core/meridian_core/server.py`, `core/meridian_core/tenancy/__init__.py`. **Acceptance:** two tenants, two roots, no cross-resolution; tests.

---

### Phase 5 — GUI/VIGUIX completion
Owned by the GUI session (parallel). This audit flags the workbench inventory is partial against VIGUIX_Final; the GUI session's register is the authority. No core task here beyond surfaces the GUI consumes (TASK-011 + TASK-020 feeds).

### Phase 6 — JIT completion
**Intentionally none until D44/J2.** The artifact half (FR-M47-01…05) is the first candidate after the MVP evidence gate; do not build synthesis before its evidence gate closes.

### Phase 7 — Reliability/observability
#### TASK-070 — Runner concurrency pool (ARCH-GAP-03)
`LangGraphLoopRunner` instance state becomes per-run context keyed by run_id; pool with the M21 concurrency cap. Files: `core/meridian_core/runtime/runner.py`. **Acceptance:** two concurrent runs, both checkpoint correctly; tests.

#### TASK-071 — Exit-check registration by loop key (ARCH-GAP-04)
Replace `id(definition)` keying with `loop_id`. **Acceptance:** two definitions sharing an id-never collides; tests.

### Phase 8 — Testing/regression
- E2E live-agent (demo path B) — external-gated; recorded, not fabricated.
- Multi-platform rehearsal + soak evidence runs — release process; harnesses exist.
- Corpus grows with every new security-relevant seam (TASK-040's identity block).

### Phase 9 — Production readiness
Gated on F2/MV5 (human study), D37 (pilot SCM), AC-50 (customer), T31/T32 (release process). Nothing in this plan manufactures those.

---

## Cross-check mapping

Every gap maps: GAP-001→TASK-010/011/012 · GAP-002→TASK-021 · GAP-003→TASK-022 · GAP-004→external (demo B) · GAP-005→TASK-020 · SEC-GAP-01→TASK-001 · NEW-GAP-E→TASK-002 · PART-001→TASK-035 · PART-002→TASK-030 · PART-003→TASK-031 · PART-004→TASK-032 · PART-005→TASK-033 · PART-006→TASK-034 · SEC-GAP-03→TASK-040 · SEC-GAP-04→TASK-041 · ARCH-GAP-02→TASK-011 convention · ARCH-GAP-03→TASK-070 · ARCH-GAP-04→TASK-071 · GAP-006 (v1.x modules)→POST-MVP plan, not this audit's scope. No orphan gaps; every P0/P1 has a path; every task has acceptance criteria.

---

## 3. Marketability Phase (added per owner goal)

These tasks close the gap between "engineering complete" and "sellable to other companies". They depend on Phase 1 (integration seam) where noted.

### TASK-100 — License manifest alignment (MKT-001)
**Gap:** MKT-001. **Priority:** P1. **Depends:** owner sign-off implicit in goal; no code dependency.
**Files:** `package.json`, `extension/package.json`, `extension/CHANGELOG.md`.
**Current state:** MIT LICENSE at root; manifests declare neither license nor public availability.
**Required state:** both manifests carry `"license": "MIT"`; `private: true` removed (or replaced with publish-config gating) once the distribution channel decision lands; CHANGELOG entry records the licensing state.
**Steps:** add fields; `npm run package` re-verified; validate-package script re-run.
**Security/legal:** MIT chosen consistent with the dependency tree (all permissive, verified in DECISIONS D22 analysis); OFL font obligations handled in TASK-101.
**Acceptance:** manifest license field present; package validation green; legal review note in DECISIONS.
**Completion evidence:** commit + validate-package output.

### TASK-101 — Third-party notices for redistribution (MKT-004)
**Gap:** MKT-004. **Priority:** P2. **Files:** `extension/NOTICE` (or ` ThirdPartyNotices`), package script inclusion, `scripts/validate-package.mjs` check.
**Required state:** OFL-1.1 attribution for Archivo + JetBrains Mono ships inside the VSIX next to the font files; validator fails the build if NOTICE is missing.
**Acceptance:** built VSIX contains NOTICE; validator test added.

### TASK-102 — Open-core boundary statement (MKT-002)
**Gap:** MKT-002. **Priority:** P1. **Files:** `DECISIONS.md`, `README.md`, `docs/claims.md`.
**Current state:** open-core direction recorded (D19) with no module split.
**Required state:** a written split proposal: core (extension host, ledger, Flight Recorder, Governor, webview shell) vs paid tier candidates (Orchestra runtime at scale, tenant registry, OIDC identity, policy simulator at team scale) — proposal only; implementation gated on owner approval. No entitlement/billing code is created.
**Acceptance:** DECISIONS records the proposal with rationale; claims doc unchanged (no capability claims added).
**Completion evidence:** DECISIONS entry.

### TASK-103 — Upgrade & migration procedure for external users (MKT-003)
**Gap:** MKT-003. **Priority:** P2. **Depends:** TASK-011 (so state shapes are final).
**Files:** `docs/DEPLOYMENT.md`, `core/meridian_core/ledger/schema.py` (migrations exist), an upgrade integration test.
**Required state:** documented upgrade path: what migrates (ledger via `apply_migrations`, policy packs preserved, adapters preserved, learned/ preserved), what a customer does (reinstall VSIX; sidecar auto-migrates), rollback limits stated.
**Acceptance:** an upgrade test opens a v-N ledger with v-N+1 code and verifies; DEPLOYMENT section exists.
**Completion evidence:** test name + doc section.

### TASK-104 — Telemetry/privacy attestation (MKT-005)
**Gap:** MKT-005. **Priority:** P2. **Files:** `docs/SECURITY-AND-DATA.md`, a no-telemetry guard test.
**Required state:** verified statement: the extension makes no network calls except the configured model provider and configured sinks (collector `--sink` is opt-in); a test fails the build if an unexpected network client appears in the extension host bundle (mirrors the core zero-model-call guard).
**Acceptance:** doc statement + guard test green.
**Completion evidence:** test + doc diff.

### TASK-105 — Marketability evidence pack (depends on external gates)
**Gap:** GAP-004/F2/T31/T32/D37 packaging. **Priority:** P1 (external). **Files:** `docs/baselines/`, `DEMO.md`, release runbook.
**Required state:** for each external gate, the moment its evidence exists (study readout, pilot SCM config, CI matrix runs, soak log), the evidence lands in `docs/baselines/` and the compatibility matrix / claims doc / DEMO are updated in the same change — no claim precedes its evidence (existing house rule).
**Acceptance:** n/a until externals land; the procedure is written now.
**Completion evidence:** procedure section in release runbook.

### Re-sequenced top order under the goal
TASK-001 (INSERT trigger, now P1) → TASK-002 → TASK-100 (license manifest) → TASK-010/011/012 (P0 wiring) → TASK-020/021/022 → TASK-101/102/103/104 → PART/SEC tasks → TASK-105 packaging as externals land.

---

## 4. Execution Record (updated 18 September 2026)

**Core-side tasks COMPLETE:** TASK-001 (gapless INSERT trigger), TASK-002 (signer marker), TASK-100 (license manifest), TASK-010 (contract, 31 methods + 68 defs), TASK-011 (**GAP-001 closed** — 31 handlers, 12 integration tests), TASK-020 (ten scenarios), TASK-021 (AC-28 parity harness, 20/20; canned shapes aligned to production), TASK-022 (golden EDB-12345 + `check:golden` in CI), TASK-035 (network-binary egress refusal at the tool gate, ledger-recorded), TASK-070 (thread-local run context), TASK-071 (loop-id exit-check keying), TASK-101 (verified: THIRD-PARTY-NOTICES.md with OFL fonts section ships in the VSIX, enforced by package-extension), TASK-103 (upgrade doc §9 + migration test), TASK-104 (no-telemetry guard `check:telemetry` + data-goes statement), TASK-041 (tenant independence doc §10 + test).

**Remaining (owner: host/GUI session or external):** TASK-012's host consumers (briefing assembly, gate-resume UI, blame→trailer join, onboarding wizard — `extension/src/**` and `webview/src/**` are the parallel session's files), TASK-030 (escalation→policy approval UI), TASK-040 (MCP client digest — host-side), and the external gates (F2/MV5, D37, AC-50, soak, live demo). Core-side prerequisites for all host tasks are now reachable over the bus.

---

## 5. Remaining Work — executable tasks (goal: production ready / fully functional / thoroughly tested)

Sequencing: TASK-200 first (it makes everything else shippable), then the host consumers (largest block), then M26-04, then the P2 debt. Every task lists acceptance criteria; §4's execution record tracks completion.

## TASK-200 — Rebuild and re-validate the artifact (GAP-101, P0)
**Gap:** GAP-101. **Priority:** P0. **Depends:** nothing.
**Current state:** `dist/meridian-loom-0.1.0.vsix` (18 Sep 06:27) predates the contract registration and handler wiring: it contains the new modules but not `orchestra_handlers.py`, and its `bus_types.py` is the 84-method version.
**Required state:** a fresh package containing the 115-method contract, `orchestra_handlers.py`, `simulation/scenarios.py`, the v5 ledger schema, and the license manifest; `validate-package` 12/12; checksum + AI-BOM regenerated; `check:golden` and `check:parity` pass against the packaged sidecar.
**Implementation steps:** `npm run build && npm run package`; run `node scripts/validate-package.mjs`; run `python scripts/check_golden.py` and `python scripts/check_scenario_parity.py` against the packaged sidecar (parity probe already spawns `python -m meridian_core` from the repo — point it at the packaged copy or accept repo equivalence after validate-package passes); commit `dist/` + refreshed `.sha256`/`.cdx.json` + BUILD_STATE.
**Files:** `dist/`, `extension/package.json` (version bump if warranted), BUILD_STATE.md.
**Acceptance:** `unzip -l` shows `orchestra_handlers.py` and a `bus_types.py` containing `RouterRequestParams`; validate-package green; checksum matches.
**Completion evidence:** validate-package output + archive listing + commit.

## TASK-300 series — Host/GUI consumers of the Orchestra RPCs (GAP-102, P1)
**Gap:** GAP-102. **Priority:** P1. **Depends:** TASK-200 (to test against the artifact). **Owner note:** `extension/src/**` and `webview/src/**` are the parallel session's files; these tasks are specified here so either session can execute. Each task: add the host service method, the workbench surface, and a vitest.

- **TASK-301 Runtime Studio → loops.** Call `loop.start`/`loop.status`/`loop.stop`/`loop.resume` from `webview/src/workbench/RuntimeStudio.tsx`; show run state, iteration, gate; render the FR-M4-06 gate-approve→resume flow. Acceptance: a vitest drives the service with a mocked transport asserting the exact RPC names/params.
- **TASK-302 Routing Observatory → router.** Surface `router/dependencyRatio` (per-scope) and a policy-ceiling display fed by the ratio's `breached` flag; render `router/requestModelCall` refusals from the ledger (`rejection` entries). Acceptance: vitest + one integration test over the real sidecar.
- **TASK-303 Memory panel → memory.** `memory/retrieve`/`memory/write`/`memory/layered` in the organisation studio; show included-vs-cut from the retrieval result (FR-M7-13's cut visibility). Acceptance: vitest.
- **TASK-304 Brownfield → comprehension.** "Comprehend module" action on a file → `comprehension/record`; render the record; blocked packets show the AC-35 reason. Acceptance: vitest with mocked transport + core integration test already present.
- **TASK-305 Agents catalogue → adapters.** `adapters/discover`/`plug`/`unplug`/`promote` wired to the existing RegistryBay; probation→active promotion gated by the promote button calling `adapters/promote`. Acceptance: vitest.
- **TASK-306 Portability dialogs → portability.** Export/import/diff buttons calling the three portability RPCs; import flow presents the diff result before confirm. Acceptance: vitest.
- **TASK-307 Trainer → trainer.** Training Queue surface calling `trainer/train`/`promote`/`rollback`; promote disabled without human approval. Acceptance: vitest.
- **TASK-308 Delivery Ops → queue/tenancy/issues.** Story queue view over `queue/enqueue`/`tick`; Problems panel reading `detected_issue` entries (already ledger-visible); tenant switcher over `tenancy/register`. Acceptance: vitest.
- **TASK-309 Simulation mode.** A workbench toggle pointing the transport at `simulation/serve` (scenario param) so every screen can run against canned scenarios; the X-26 band already exists. Acceptance: vitest switching transports.

## TASK-310 — FR-M26-04 cost levers (TD-008/GAP-103, P1)
**Requirement:** FR-M26-04 (MUST v1). **Priority:** P1.
**Current state:** no levers exist.
**Required state:** three configurable levers on the model-call path: (a) **prompt caching** — identical prompt prefixes hashed and reused within a TTL, cache hits recorded; (b) **context compaction** — over-budget contexts compacted by deterministic summarisation (drop oldest tool results first, marked); (c) **tool-result summarisation** — oversized results replaced by a capped extract with the truncation marker (reuse `TRUNCATION_MARKER`). Each lever's savings (tokens, cost) reported per story and in aggregate via a `spend/levers` read (or an extension of `router/dependencyRatio` result).
**Implementation steps:** new `core/meridian_core/levers.py` with a `CostLeverSet` consumed by `Router.request_model_call` (pre-call) and by a post-call recorder; config from the governance pack (`budget_ceilings`-adjacent key) with safe defaults (all levers on, TTL 15 min); ledger entries for cache hits and compactions (action_type `model_call` with `lever` field in detail).
**Files:** `core/meridian_core/levers.py` (new), `core/meridian_core/router/routing.py`, `core/meridian_core/orchestra_handlers.py` (ratio extension or new `spend/levers` read), `shared/schema/methods.json` if a new read method is added, policy schema.
**Testing:** unit per lever (cache hit/miss, compaction order, marker preservation); integration via the bus; savings arithmetic proven against synthetic call logs. **Acceptance:** all three levers demonstrably reduce recorded token spend in a test scenario; savings figures reconcile to the ledger.

## TASK-320 — Persist orchestrator state (TD-006, P2)
Run registry (loop handles), story queue, and tenant registry survive sidecar restart: store under `<workspace>/.meridian/orchestrator/state.json` (atomic write), rebuilt at `_state()` first touch; `loop.resume` accepts a persisted handle. **Acceptance:** start→suspend→kill→restart→resume completes; queue state survives.

## TASK-321 — Close the checkpointer on shutdown (TD-007, P4)
Call `server._orchestra.shutdown()` from the shutdown path. **Acceptance:** no leaked connection warning in a start/stop test.

## TASK-330 — Cross-origin import trust (TD-002, P2)
`portability/import` accepts a package signed by any key whose fingerprint the workspace has explicitly trusted (trust record in the ledger, human-approved). **Acceptance:** untrusted signature still refuses; trusted imports succeed; tests.

## TASK-331 — Narrative ablation (TD-003, P3)
Store the decision function's replay recipe at record time for hosted decisions (engine class + payload template), enabling ablate without `actionClass`. **Acceptance:** narrative decisions ablate; tests.

## TASK-340 — Interface contract artefacts (TD-009/FR-M22-02, P2)
For multi-repo stories, generate an interface contract file (OpenAPI skeleton) from declared repo targets before implementation; Review gate requires it when `repos.length > 1`. **Acceptance:** two-repo story produces a contract artefact; gate blocks without it; tests.

## Execution record (§4) continues
Mark each task DONE here with commit + evidence as it lands.
