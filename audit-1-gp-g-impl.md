# Meridian Loom — production readiness remediation and verification plan

**Prepared:** 18–19 September 2026. **Requirements:** [Goal-based audit](audit-1-gp-g-req.md). **Initial baseline:** `b3e868bfe37d143f0132908282bbed3f29d1f355`. **Delta reviewed:** through `b999821a5ab0c691f775bf38bb5f63c852d7f642`, plus the explicitly identified in-progress GUI changes in the companion audit. This is a development handoff, not a statement that these tasks have been implemented.

## 1. Execution contract

The goal is a working, governed engineering product with verified delivery, portable agents, useful built-in roles/skills, inactive-agent learning, an editor-area GUI, durable evidence and supported installation. A passing unit suite, registered RPC, visible panel or signed agent card is not by itself acceptance of that goal.

1. Re-read the working tree, active changes and the two audit files before implementing. Preserve concurrent work. Reproduce findings at the implementation commit; mark a finding superseded only with code and acceptance evidence. Do not restore old defects to reproduce them in the working tree.
2. Keep the present architecture where it works. Connect existing ACP hosting, ledger, worktree, identity, policy and UI services; avoid another parallel registry or runtime.
3. Fix security and contract defects before exposing more privileged actions. The authorization needed for product actions is part of the product; an AI developer's permission to edit the repo does not remove end-user approval gates.
4. Use failing behavioral regression tests for confirmed defects. Then implement, run focused tests and required integration checks, and retain results. Do not make failures green by weakening schemas, suppressing errors, allowlisting every method, disabling security or accepting fabricated outputs.
5. Record code SHA, environment, commands, exit codes, artifacts and requirement disposition. Separate code-complete, tested, packaged, installed-verified and externally accepted states. Existing historical DONE labels do not close these tasks.
6. Finish all independently executable engineering work before handing off genuine external prerequisites. Do not invent live credentials, customer configuration, paid-feature decisions, elapsed soak time or human-study results.

All `GP-Tnnn` tasks map to `GP-nnn` in the requirements audit. **Initial status for every task: OPEN unless a narrower corrected subfinding is explicitly recorded.** In particular, the host-service addition closes the original missing-method-string detection, not the complete GUI or production workflow. The later `persist()` calls close some missing-write sites, not restart correctness. Keep these distinctions in subsequent updates.

## 2. Dependency order and release gates

| Wave | Tasks and deliverables | Exit condition |
|---|---|---|
| A — reconcile and reproduce | T001; capture T003–006, T008–010, T015, T018, T021 reproductions; establish T025 evidence format | Stable clause IDs and failing regressions; no inflated prior completion claims |
| B — security and authoritative contracts | T003–006, T020, trust/permission portions of T012/T013 | Tampered imports, traversal, forged authority and invalid wire data fail before side effects |
| C — executable and recoverable core | T007–014, T017–019, T021, T039; targeted T040 service boundaries | One real governed story and agent lifecycle survive errors/restart and produce correct artifacts |
| D — useful product workflows | T002/T022, T015/T016, accepted T034, T031 | User journeys reach functioning services with honest states and packaged resources |
| E — assurance and distribution | T023–030, T032/T037, T041; remaining T040 | Frozen candidate passes complete suites, installed-host checks and required nonfunctional gates |
| F — scope-dependent completion | T033/T035/T036/T038/T042 | Every accepted full-product obligation has evidence; external work has explicit owner/results |

Dependencies below express prerequisites for acceptance, not a ban on preparing independent tests or UI designs. For mutually integrated tasks, build the foundation first: define contracts/state versions; implement supervision, permissions and registry; demonstrate one executable fixture story; add recovery/queue and learning; then close the integrated acceptance criteria. Do not wait for learning to finish before implementing the registry it requires, or for all migration tests before defining the state schema they test. Long-running soak and human studies should be scheduled early after their code prerequisites stabilize, then restarted/requalified when material candidate changes invalidate them. A narrow release requires an explicit scope decision, not silent deletion of full-vision requirements.

## 3. Detailed task register

### GP-T001 — Build the authoritative requirement and acceptance register

**Priority:** P1. **Depends on:** none. **Files:** all sources listed in the audit inventory; `Requirements_Final.md`, `mvp-req-final.md`, `post-mvp-plan.md`, `DECISIONS.md`, `status.md`, `BUILD_STATE.md`, `docs/claims.md`; proposed machine-readable register under `docs/`.

- Extract source-qualified clauses: document, heading, original ID, exact obligation, release/milestone, amendments and explicit supersession. Identical copies point to a canonical row; overlapping IDs in JIT/futures remain distinct until mapped to canonical M47–M52.
- Give each row a production entry point, responsible component, acceptance scenario, current evidence, disposition and owner. Record unsupported configurations and D7 plans-only deployment separately from omissions.
- Replace unqualified percentages with counts against the accepted denominator. A task with code but no exercised product path is partial; a test not rerun at the candidate is historical evidence.

**Verification/acceptance:** inventory reconciliation detects missing clauses and duplicate identities; every module M1–M52, phase P1–P9 and NFR/SEC/AC/ECO family has traceability. An AI developer can resolve a row to source, implementation and executable acceptance without interpreting a narrative “done.” Do not automatically mark all clauses covered merely because this audit groups them into 42 findings.

### GP-T002 — Complete actual interface consumption and repair CI evidence

**Priority:** P1. **Depends on:** T006 and relevant backend task; T022 for UI acceptance. **Files:** `extension/src/orchestra/services.ts`, host/webview RPC services, `webview/src/workbench/`, `shared/schema/tiers.json`, `shared/schema/unsurfaced.json`, `scripts/check-surface-coverage.mjs`, `.github/workflows/verify.yml`.

- Retain the newly added host wrappers. Reconcile their handwritten inputs/results with generated schema types; wrappers returning `Promise<unknown>` are not runtime result validation.
- Wire the endpoint families in §4 into owning screens and real user journeys. Validate tier absence and host authority; clean obsolete allowlist entries after proving consumers.
- Extend the surface register to distinguish wrapper existence, reachable UI action and exercised backend workflow. Do not use the string-search gate as proof of all three.
- Run CI at the final commit and examine downstream jobs. The baseline failure is real history; the current local 109/112 surface pass supersedes its static failure only.

**Verification/acceptance:** UI action → host → real sidecar → durable result → UI, including failure and reconnect, for every accepted family; current full CI runs instead of skipping jobs. Developer-only exceptions have rationale, owner and scope.

### GP-T003 — Authenticate all portable-agent payload bytes

**Priority:** P0. **Depends on:** T006 for wire changes; coordinate T004. **Files:** `core/meridian_core/portability/__init__.py`, `core/meridian_core/adapters/__init__.py`, portability schemas, host import/export implementation, `core/tests/test_portability_m16.py`.

- Define a versioned canonical package manifest: normalized relative member path, byte size, digest, adapter identity/version, required capabilities and declared exclusions. Sign the manifest or a precisely specified root that covers it.
- On import, verify signer trust and every included member against the authenticated manifest before any destination write. A removable digest in an unsigned `adapter.yaml` cannot establish integrity.
- Decide how older package versions are rejected or explicitly migrated. Bind identity and runtime entry point; do not infer trust from a package's self-presented public key alone.

**Regression:** export a valid fixture; preserve card/signature; replace `agent.py` with harmless comment bytes and remove its optional manifest digest. Current baseline accepted this. Add tampered manifest, extra/missing file, wrong ID/version, revoked signer and legitimate exclusion cases. **Acceptance:** all unauthorized substitutions fail without installing or executing anything; valid cross-workspace trusted imports round-trip with identical verified payloads.

### GP-T004 — Make archive import contained and transactional

**Priority:** P0. **Depends on:** T003. **Files:** Python portability importer; host importer for shared policy; portable-package tests.

- Preflight all member names and adapter IDs. Reject absolute/drive/UNC paths, parent traversal, links, duplicate normalized names, case collisions on applicable filesystems and reserved/invalid names. Use path-component containment, including resolved existing parents, never string-prefix containment.
- Set compressed/expanded size, member-count and per-member budgets before extraction. Stage in a validated temporary location under the approved installation root; validate contents and admission there.
- Publish atomically with recoverable backup/rollback. Ensure failure, interruption, revoked consent or disk-full leaves the existing active version and sibling directories unchanged.

**Regression:** package member `../developer-extra/audit-proof.txt` must not be created beside `developer`; test platform-specific path variants, preexisting links and failure after the first staged member. **Acceptance:** no pre-validation write escapes staging, no partial active installation, and a legitimate upgrade has an auditable atomic version transition.

### GP-T005 — Derive privileged authority from authenticated host context

**Priority:** P1. **Depends on:** T006; coordinates T033. **Files:** `orchestra_handlers.py`, `server.py`, existing identity/roles/governance services, `extension/src/webview/webview-rpc-proxy.ts`, host confirmation flows.

- Enumerate trust, promotion, pinned memory, model overrides, gates, imports and replay overrides as protected actions. Classify permitted actor/role and required evidence per action.
- Replace caller booleans and self-declared authors/approval arrays as authorization with a host-authenticated principal and evidence-bound approval. Bind subject, digest/revision, action, policy version, expiry and revocation state.
- Reject stale/replayed approvals and persist the actual approver identity. Keep tier availability separate from authority. Do not accept an arbitrary JSON replay override as approval of live work.

**Verification/acceptance:** direct untrusted webview/RPC calls setting `humanApproved`, `actorIsHuman`, fabricated scores or approvals cannot mutate protected state; valid human flow succeeds exactly once and emits evidence; revoked/wrong-role actors fail. Preserve the local stdio threat boundary rather than claiming an Internet exploit.

### GP-T006 — Enforce authoritative request and response contracts

**Priority:** P1. **Depends on:** none. **Files:** `shared/schema/methods.json`, generated bus types, `shared/ts/workbench.ts`, `server.py`, `orchestra_handlers.py`, host wrappers and transport tests.

- Resolve loop start/stop/resume/replay/status wire shapes, ratio extra fields and nested adapter/memory shapes before generating types. Give one schema ownership of each result instead of independently typing actual-but-nonconforming responses in the workbench map.
- Validate all requests and responses at the boundary with bounded sizes and strict semantics; normalize expected validation failures to documented JSON-RPC errors. Check finite/ranged numbers, object shape, enums, identifiers and path scope.
- Version protocol changes deliberately and test host/webview/sidecar mixed-version diagnosis. Validate notifications as well as request/response methods.

**Verification/acceptance:** parameterized tests exercise every registered method through the real server against its schema. Deliberately mutate nested keys, result types, unknown properties and invalid params to prove the validator fails. Generated-file freshness remains necessary but cannot substitute for wire validity.

### GP-T007 — Replace production progress markers with real delivery execution

**Priority:** P0. **Depends on:** foundations from T005/006/008/011–014; integrate T009/010 for recovered/queued work and T018/T039 where the story needs them. **Files:** `orchestra_handlers.py`, `runtime/`, ACP host/runtime bindings, phase policy, work-packet schemas, built-in adapter entry points.

- Define versioned packet inputs, artifacts, phase exit evidence and rework transitions. Bind each node to an admitted agent or deterministic capability with an explicit runtime identity.
- Connect intake, design, planning, isolated implementation, tests, security and review to actual outputs. Consume existing ACP sessions and tool services; remove `_stand_in_nodes` from the production completion path.
- Keep simulation a separately identified transport/state space. Missing bindings, tests, approvals or runtime dependencies leave the run blocked/failed with reasons.

**Verification/acceptance:** a deterministic executable fixture first makes a real repository change and executes verification through the full product path; then T041 repeats with a live runtime. Inject failing tests, rejected review and missing credentials: none may return completed. Outputs reference the exact change, tests, roles, context and policy.

### GP-T008 — Implement responsive run supervision, cancellation and budgets

**Priority:** P1. **Depends on:** T006, T020. **Files:** `server.py` dispatch/control loop, `runtime/runner.py`, Orchestra handlers, sidecar client and status UI.

- Separate responsive control-plane requests from long-running work. Own nodes, schemas, cancellation and usage in per-run contexts, not one mutable thread-local map.
- Specify legal states and idempotent stop behavior. Unknown run is an error; known terminal states have explicit responses. Propagate cancellation through ACP/model/tool calls and terminate descendants where required.
- Enforce global concurrency and budgets, including usage reservations/actual reconciliation and in-call deadlines. Populate health from actual supervised runs.

**Verification/acceptance:** stop an executing subprocess/model fixture while ping/status remains responsive; test repeated stop, unknown ID, budget breach, concurrent runs and no context crossover. Prove no new delivery action starts after cancellation is acknowledged.

### GP-T009 — Recover executable continuations across restart

**Priority:** P1. **Depends on:** T007/008 execution foundations; coordinate state-version design with T030 before its upgrade tests. **Files:** `OrchestraState._restore/persist`, `runtime/runner.py`, checkpoint storage, `core/tests/test_orchestrator_state.py`.

- Persist run ID, definition version, trusted binding descriptors, state-schema version, gate/continuation cursor, budgets and completed side-effect keys. Rebuild callables from trusted registrations, not serialized executable input.
- Make checkpoint and visible run state consistent. Report corrupt/unknown snapshots as actionable recovery failures instead of silently replacing them with empty state.
- Refuse resume of unknown/terminal/incompatible runs; carry authenticated gate approvals into the exact continuation.

**Verification/acceptance:** start → suspend at real gate → abruptly kill process → new process → approve/resume, with exact output and no repeated effect. Also test cross-worker resume, sequential runs, invalid schema and missing runtime. The baseline metadata-only reconstruction causing `_local.schemas` errors must have a regression; completed-run resume must fail deliberately, not with internal error.

### GP-T010 — Make queue acknowledgement, admission and completion durable

**Priority:** P1. **Depends on:** T008/009/019. **Files:** Orchestra state/handlers, queue implementation, scheduler integration, queue recovery tests.

- Keep the new enqueue/tenant `persist()` calls, but replace incomplete snapshot semantics with a durable transition model covering waiting, in-flight, done/failed, order, dependencies, WIP reservations, leases and bindings.
- Acknowledge only committed changes. Add idempotent enqueue and completion; integrate admission with actual execution and release capacity on terminal outcomes.
- Validate tenant, dependencies, cycles and duplicate IDs. Recover abandoned leases without duplicate side effects.

**Verification/acceptance:** crash after every response/transition and reconcile acknowledged state; dependency/WIP invariants survive; admitted work does not disappear; completed work releases slots. Test two schedulers or enforce and verify a single-writer lease.

### GP-T011 — Unify launch paths and repository isolation

**Priority:** P1. **Depends on:** T005/008. **Files:** `extension/src/workbench/service.ts`, run-initiation/preflight/worktree services, Orchestra/ACP launch path, workspace ownership storage.

- Route workbench delivery, palette start, independent agent execution and queued stories through one validated launch service.
- Resolve approved repository roots, story branch/worktree, dirty-tree policy, permitted scope and agent version before process launch. Preserve explicit plans-only deploy boundaries.
- Handle cancellation, merge conflicts, orphan worktrees and two-window contention consistently; do not delete a user worktree based only on a naming convention.

**Verification/acceptance:** every entry point edits only its assigned worktree; the main checkout stays unchanged until the authorized integration step. Dirty workspace, conflict, denied path and concurrent-window cases have meaningful integration tests and user-facing recovery.

### GP-T012 — Connect native tools to admitted permissions

**Priority:** P1. **Depends on:** T005/006/011/020. **Files:** `tools/surface.py`, Orchestra tool construction, agent admission and permission services, tool schema registry.

- Build the tool surface from admitted capabilities plus current policy, packet, working directory and session identity. Populate permits through a protected service; do not expose an unrestricted permit RPC.
- Preserve read/edit/execute distinctions, argument validation, revocation and evidence correlation. Connect deterministic intelligence/build/test tools needed by real nodes.

**Verification/acceptance:** real approved read, edit and build/test operations succeed through the bus with actual output/exit status; unapproved tools, arguments, revoked sessions and wrong paths fail. An always-denied endpoint does not close this task.

### GP-T013 — Unify portable-agent lifecycle and admission

**Priority:** P1. **Depends on:** T003–005/008/011; T016 for learning. **Files:** host agent library/registry and workbench service, Python `adapters/`, Orchestra state, agent/adapter schemas and GUI.

- Define a durable identity/version mapping between the 22 profiles and 14 Python adapters; distinguish role/profile, executable runtime, skill set, participation, autonomy and learning-job state.
- Implement add/update/remove/activate/deactivate/import/export through one service. Freeze acting versions, protect referenced versions from removal, drain or explicitly cancel work before deactivation/unplug.
- Require real upgrade regression/scorecard evidence and authenticated admission/promotion. Persist version history/checkpoints; failed upgrade restores the previous admitted version.

**Verification/acceptance:** independent agent execution works outside a delivery team; active agents participate only when eligible; inactive agents receive no delivery work and display truthful learning/waiting states. All lifecycle actions survive restart, including unplug/replug and failed upgrade. Investigate the fresh failing `test_upgrade_regression_runs_adapter_tests` using its subprocess output; do not assume a root cause or merely raise its timeout.

### GP-T014 — Assemble governed instructions, skills and memory at invocation

**Priority:** P1. **Depends on:** T005/013/021. **Files:** host briefing builder, `core/meridian_core/memory/instructions.py`, library profiles/skills, invocation/context schemas.

- Define precedence for trusted organization/user instructions, repository conventions, role, skills, reviewed memory and task data. Explicitly distinguish untrusted retrieved text from instructions.
- Use one budgeted assembly contract across native and ACP execution. Record included/excluded source digests, versions and truncation reasons; invalidate changed or revoked inputs.
- Connect useful stack skills to real tool/test constraints: Java/Spring Boot, Python and cloud infrastructure examples must exercise their advertised behavior, not merely include Markdown.

**Verification/acceptance:** capture actual dispatched context; precedence/budget/injection/revocation cases behave as specified. Stack fixture changes build/test correctly and retain invocation provenance. An accepted learned change affects the next applicable invocation.

### GP-T015 — Make cost levers preserve semantics and measure real savings

**Priority:** P1. **Depends on:** T007/014/021. **Files:** `levers.py`, `router/routing.py`, provider/ACP invocation boundary, policy/config and spend UI.

- Remove local-prefix-cache behavior that sends only a suffix without a provider cache reference. Use supported provider caching semantics or retain the complete prompt.
- Apply shaped context to actual dispatched requests, including all required instructions/tool content; enforce complete budgets for Unicode and non-tool text.
- Record estimates separately from provider-reported cached tokens, actual usage, billing and unknowns. Configuration must change the live path.

**Verification/acceptance:** repeated short prompt never dispatches empty context; changed model/prefix/TTL behaves correctly; captured request bytes preserve required meaning; ledger/UI totals reconcile with observed calls. Do not accept reduced synthetic token counts as proof of billed savings.

### GP-T016 — Implement real inactive-agent learning jobs

**Priority:** P1. **Depends on:** T005/009/013/014/021. **Files:** trainer services, active-run registry, learning scheduler/storage, Training Queue UI.

- Derive delivery exclusion from real runtime state. Turn harvest into a durable job producing declarative candidates with source provenance, not an unconditional `ran=True`.
- Evaluate incumbent and candidate on pinned tasks with safety and quality regressions. Derive scores from retained results; caller-supplied numbers are proposals at most.
- Provide waiting/running/review/failed/completed states, cancellation, authenticated promotion and rollback. Label unavailable signals/resources truthfully.

**Verification/acceptance:** deactivation leads to a recorded job when eligible, a reproducible candidate evaluation and reviewed change that affects later execution; active delivery pauses/excludes training as specified; failures cannot self-promote. No claim of model-weight training without such a separately implemented product.

### GP-T017 — Persist decisions and implement reproducible explanation workflows

**Priority:** P2. **Depends on:** T005/009/014/021. **Files:** decision/XAI services, Orchestra handlers/persistence, decision schemas and GUI.

- Allocate stable decision IDs and return them; persist immutable inputs, context/model versions, outputs, confidence and replay recipe references.
- Support restart-safe lookup and scoped ablation. Distinguish deterministic executable replay from unavailable/narrative replay; avoid implying causal proof from arbitrary output differences.
- Bind calibration to observed outcomes and evidence populations; gate decisions consume verified test/scan/approval records.

**Verification/acceptance:** record → restart → lookup → ablate works on pinned inputs with a negative control; missing recipe/model is explicit; decision IDs never collide after restart; calibration distinguishes missing outcomes.

### GP-T018 — Enforce meaningful interface and documentation contracts

**Priority:** P1. **Depends on:** T006/007/019. **Files:** `interface_contracts.py`, multi-repository planning/review services, schema validators and contract-test fixtures.

- Replace generic repository-name GET skeletons as gate evidence with actual accepted API/message definitions, versions and digests derived from design or imported source.
- Validate syntax and semantic compatibility, generate/run provider-consumer contract checks, and wire the gate into dependent implementation/review transitions.
- Connect required documentation artifacts to their own validity/freshness rules; file presence alone is insufficient.

**Verification/acceptance:** text `not an API contract`, empty/stale schemas and incompatible provider/consumer changes block the real flow; compatible two-repository delivery produces meaningful executable contract evidence and linked artifacts.

### GP-T019 — Implement tenant/repository context or narrow the boundary

**Priority:** P1. **Depends on:** T001/005; coordinates T010/011. **Files:** tenant registry, Orchestra service factories, queue, memory/tools/ledger/cache/export resolution.

- Decide and document single trusted workspace per sidecar versus a genuinely shared service. A registry of roots is not isolation.
- For shared service scope, carry validated tenant context through every operation and storage/signer/cache boundary; authorize roots and reject unknown tenants before enqueue.
- Persist repository targets/bindings and prevent caller paths from changing the active trust domain.

**Verification/acceptance:** two-tenant adversarial tests cover queue, memory, adapters, logs, approvals, exports and recovery; no cross-resolution occurs. If shipping the narrower mode, enforce it and leave full multi-tenant obligations explicitly open.

### GP-T020 — Bound and contain external execution honestly

**Priority:** P1. **Depends on:** T001 supported-platform decision. **Files:** `tools/surface.py`, plain-Python bridge, ACP process launcher, environment/egress policy.

- Stream stdout/stderr with total byte/memory bounds and explicit truncation; do not buffer an unbounded process then truncate its display.
- Own subprocess trees, deadlines, cancellation, inherited handles and scrubbed environment on each supported OS.
- Implement actual OS/network/filesystem isolation where claimed, or clearly describe direct executable trust and limitations. A helper a Python agent may bypass is not containment.

**Verification/acceptance:** output flood is bounded, descendant processes terminate after stop/revoke/timeout, allowed commands still work, and claimed denied paths/egress are verified at the actual enforcement boundary.

### GP-T021 — Repair identity, coverage and usage accounting semantics

**Priority:** P2. **Depends on:** T006; coordinates T015/016/017.

**Files:** memory entry conversion/retrieval, trainer harvesting, trusted-signer iteration, router and ledger analytics.

- Retain the new deterministic ID improvement, but replace the truncated 32-bit subject/author hash with a versioned collision-resistant identity policy. Define entry identity versus content revision; include tenant/tier where required. Concatenating fields with `|` is ambiguous unless encoded canonically.
- Return actual content hashes; changed content must not masquerade as unchanged digest. Migrate existing references deliberately.
- Iterate full history with ordering/cursors and coverage envelopes. Separate requested, authorized, dispatched, completed and billed events.

**Verification/acceptance:** IDs survive process restart, unambiguous field tuples remain distinct, revisions change content hashes, >1,000 signals and >100,000 trust events preserve revocation/coverage, and ratios exclude never-dispatched calls. No silent “complete” aggregate over a capped population.

### GP-T022 — Complete specified GUI workflows in the editor area

**Priority:** P1. **Depends on:** relevant T002/T006–021/T039 services. **Files:** `webview/src/workbench/`, screen registry, shared workbench action map, host service and UI integration tests.

- Use the audit's VIGUIX screen matrix to map every accepted interaction to a real action/read model. Keep editor-area default and existing usable components.
- Replace standalone JSON panels/manual notes where a product workflow is required: real loop state/control, semantic CodeMap, evidence-backed comprehension, authorized hunk actions/rework, actual replay, learning jobs and durable portfolio operations.
- Verify tier gating at both visibility and host dispatch. A busy start must not disable the user's only stop control. Remove stale notices only when the corresponding behavior actually works.
- Supply loading/empty/error/stale/reconnect states, optimistic concurrency and accessible keyboard flows. Preserve simulation labeling and data separation.

**Verification/acceptance:** installed-product journeys cover success, denial, backend failure and reconnect for every required screen; no simulated completed status leaks into real delivery. DOM tests alone cannot certify installed-editor behavior.

### GP-T023 — Make production/simulation parity semantic and comprehensive

**Priority:** P1. **Depends on:** T006/022. **Files:** `scripts/check_scenario_parity.py`, scenario fixtures, simulation transport and rendered-component tests.

- Run mutation/read/error/notification steps against disposable real workspaces and simulation. Validate complete nested schemas and compare canonical results/state modulo explicitly documented nondeterminism.
- Replay both transports through actual screen components, including time controls and missing/error states; track screen/requirement coverage.

**Verification/acceptance:** deliberate nested-field drift, dropped notification, wrong status and no-op mutation fail. Preserve all ten existing scenarios but do not treat 20 shallow checks as the full AC-28 acceptance set.

### GP-T024 — Expand the golden corpus to meaningful product behaviors

**Priority:** P2. **Depends on:** T007–018/T023 as applicable. **Files:** `golden/`, replay/admission tools, CI golden checks.

- Add provenance-pinned greenfield/brownfield, rework, cancellation, crash resume, migrations, tampered import, multi-agent/story and supported-stack cases.
- Each cassette states requirements, inputs, expected actual artifacts/evidence and exactly which production behavior is re-executed versus verified from stored bytes.

**Verification/acceptance:** model/network prohibition is enforced in deterministic replay; an intentional behavior regression fails the relevant story; fixtures include negative controls and documented admission. Never fabricate ledger events and call that a successful live delivery.

### GP-T025 — Establish complete candidate-bound correctness validation

**Priority:** P1. **Depends on:** preceding functional fixes; prepare harness immediately. **Files:** tests, test runner/lock, `.github/workflows/verify.yml`, baseline evidence records.

- Run full core, extension, webview, generated-contract, Rust verifier, security/retention and package checks at a frozen candidate. Honor the existing cross-language suite lock; do not run competing full suites.
- Capture subprocess diagnostics for the failing portable-upgrade test and fix the cause. Distinguish host/resource failures, lock blocking and assertion failures; do not treat any as a pass.
- Strengthen tests that assert booleans/file presence/metadata instead of effects, especially stop, recovery, migration, signatures, authority and gates. Use targeted mutation controls to establish their sensitivity.

**Verification/acceptance:** no required suite skipped; failures/skips are explained and dispositioned; exact command, SHA/tree status, environment, counts, durations and logs retained. A dirty, changing checkout cannot be certified by combining separate green runs.

### GP-T026 — Validate the installed extension in a real editor host

**Priority:** P1. **Depends on:** T006/031/032. **Files:** installed-package/extension-host harness, interpreter/bootstrap/Doctor, package baselines.

- Install final VSIX into a clean profile; launch actual supported VS Code with an isolated workspace and external Python environment. Do not alias `vscode` to a mock for this gate.
- Exercise first activation, missing dependencies/provisioning, editor panel, real RPC, protocol mismatch/reload, untrusted workspace, process crash and uninstall. Verify offline/managed-machine behavior only where supported.

**Verification/acceptance:** works without the source checkout or warm developer site-packages; actionable failure remediation is tested; logs identify exact editor/runtime and VSIX digest. Keep the current validator as a lower-level check, labeled accurately.

### GP-T027 — Qualify every supported platform/runtime configuration

**Priority:** P1. **Depends on:** T001/026. **Files:** workflow matrices, compatibility contract and baselines, support docs.

- List exact OS/editor/Python/Node/native/remote combinations. Execute minimum supported editor and Python versions rather than inspecting manifests; include macOS core if macOS is supported.
- Rehearse claimed SSH/WSL/container/Codespaces modes, filesystem semantics, process cancellation and credential isolation. Run the required full matrix on release candidates even if PR smoke is narrower.

**Verification/acceptance:** every support row has real environment evidence or explicit unsupported status. An existing test filename is not platform qualification.

### GP-T028 — Complete soak, performance and fault recovery gates

**Priority:** P1. **Depends on:** stable T008–010/020/025/026 candidate. **Files:** soak/performance/resilience harnesses and `docs/baselines/`.

- Execute the specified 168-hour workload with representative observation, execution, queue, learning and large-ledger activity; include configured fault injections and recovery cases.
- Record cold/warm startup, p95 query/event/UI latency, RSS/handles/disk growth, queue throughput, lost/duplicate evidence and recovery objectives on named hardware.
- Connect aggregate release readiness to these required results; development smoke may remain shorter but must not satisfy release thresholds.

**Verification/acceptance:** complete raw samples, thresholds and verdict tied to the artifact; no acknowledged data/work lost; no truncated or restarted measurement labeled seven-day completion. The existing 0.05-hour record remains a harness smoke.

### GP-T029 — Verify accessibility and GUI quality on the candidate

**Priority:** P2. **Depends on:** T022/026. **Files:** webview components/styles, accessibility suites and assistive/visual protocols.

- Cover keyboard operation, focus/restoration, live announcements, errors, contrast, zoom, reduced motion, themes/densities and large datasets in the editor panel.
- Give graphs/timelines equivalent navigable data and ensure stop/review/import controls remain usable under loading/errors. Format complex UI handlers enough to review state transitions.

**Verification/acceptance:** fresh automated reports plus real assistive and visual records for critical journeys; no essential pointer-only/color-only action or focus trap. Historical axe results remain historical.

### GP-T030 — Prove upgrades, backups and recovery of all persistent state

**Priority:** P1. **Depends on:** T009/010/013/017 state design. **Files:** ledger migrations, backup/export/restore, all persistent state schemas, `core/tests/test_upgrade_path.py`, deployment/support docs.

- Create immutable fixtures using actual older released schemas/code and keys. Do not simulate an old database solely by changing unused `PRAGMA user_version` on a latest-schema database.
- Cover ledger/checkpoints/blobs/keys, queue, decisions, agent versions and workbench state; test consistent backup, migration interruption, unsupported downgrade and documented rollback/export.
- Define key loss/rotation and erasure-restoration boundaries; keep support instructions consistent with actual behavior.

**Verification/acceptance:** old evidence verifies after migration; acknowledged work persists; corrupt/unsupported versions fail with recovery instructions; backup/restore round-trip works using shipped tooling and no source checkout.

### GP-T031 — Package and resolve all intended runtime resources

**Priority:** P1. **Depends on:** T013 roster decision; T032. **Files:** `scripts/package-extension.mjs`, resource resolver, Orchestra defaults, adapter/library/policy staging and package validation.

- Establish one explicit resource root for source and installed layouts. Resolve phase policy, schemas and intended built-ins without accidental `core/adapters` or `sidecar/policy` fallbacks.
- Include the chosen executable/profile roster and required manifests, skills/instructions, notices and runtime resources. Avoid packaging competing rosters without lifecycle semantics.
- Rebuild and validate the final artifact, then calculate checksum/BOM/provenance and bind the validation record to that digest.

**Verification/acceptance:** clean extracted VSIX discovers expected agents, loads policy and runs supported behavior with no repository fallback. Test behavior as well as archive member names. Earlier validation of digest `57244792eacf04ab…` does not certify `675247ea7babb35d…`.

### GP-T032 — Reproduce and attest the supply chain and build environment

**Priority:** P1. **Depends on:** T001 support scope. **Files:** dependency manifests/locks, BOM/notices tools, CI workflow and release metadata.

- Lock transitive runtime dependencies with verifiable inputs; account separately for bundled and externally installed runtimes. Fail release checks on unresolved inventory rather than silently skipping it.
- Include applicable attribution/license texts and review redistribution inventory. Add Python/JavaScript vulnerability, secret and verifier gates with documented exceptions/expiry.
- Explicitly install Python/core dependencies in contracts/golden/parity jobs and test dependencies in performance jobs. Add mandatory verifier build/tests and candidate provenance; remove reliance on ambient runner packages.

**Verification/acceptance:** clean runners build/test/scan repeatably; BOM matches the distributed closure; provenance names source/toolchain/digest; all advisory exceptions have owners. The fresh `npm audit --omit=dev` zero-vulnerability result covers that dependency subset only.

### GP-T033 — Enforce enterprise governance at the real merge boundary

**Priority:** P1 for enforcement claims. **Depends on:** T005/034; external SCM/identity configuration. **Files:** identity provider seam, governance/SCM integration, evidence verification and enforcement declarations.

- Implement trusted identity and freshness/revocation where claimed. Bind approval and required-check evidence to actual repository/head/content, not only local UI state.
- Rehearse required SCM checks, separation of duties and bypass controls outside the editor. Report advisory mode where installation/configuration cannot enforce.

**Verification/acceptance:** failing/stale evidence or revoked identity blocks merge through an independent client; permitted approved merge succeeds. Retain customer configuration evidence; mocks alone cannot close the external boundary.

### GP-T034 — Finish accepted SDLC connectors and phase outputs

**Priority:** P1/P2 by clause scope. **Depends on:** T001/007/011/018. **Files:** connector adapters, CI/PR services, documentation/runbook generators, maintenance and model-comparison services.

- Split each outstanding connector/phase clause into an executable scenario: issue write-back, CI failure-to-rework, review response, linked repository PRs, generated documentation/runbooks, scheduled maintenance and comparison experiments.
- Implement pagination, credential scope, retry/rate limiting, idempotency and ledger correlation. Do not treat a successful read-only connectivity probe as workflow completion.
- Preserve D7 plans-only Release/Operate behavior unless an explicit product decision changes it; no implicit deployment execution.

**Verification/acceptance:** controlled repositories demonstrate issue → packet → isolated changes → tests/scans → reviewed PR → CI/rework → authorized integration/report, including denied/expired credentials, rate limits and duplicate callbacks.

### GP-T035 — Deliver the accepted JIT artifact/retrieval baseline

**Priority:** P2/future scope. **Depends on:** T001/014/024. **Files:** canonical M47 requirements, harness registry/storage/retrieval, packet-start binding and benchmarks.

- Implement J1/J2 artifact records, provenance, eligibility/matching, bounded retrieval, pinned validation and honest misses. Integrate accepted harness selection into the real packet path.
- Keep J3/J4 synthesis behind their explicit evidence decision; D44 is not a blanket prohibition on the allowed earlier artifact/retrieval work.

**Verification/acceptance:** reproducible retrieval/hit-rate and budget results; stale/untrusted harnesses cannot execute; synthesis cannot self-enable because a plan checkbox changed.

### GP-T036 — Close accepted competitive-assurance modules individually

**Priority:** P2/future or claim-dependent. **Depends on:** T001/020/021/032/033. **Files:** M48–M52 implementations, attestation/interoperability/gateway/outcomes code and post-MVP plan.

- Preserve separate acceptance for enforced tool-call lineage/gateway, attested workload identity, standard-tool-verifiable envelopes/witnesses and longitudinal outcomes. Generic seams do not fulfill each one.
- Preserve source confidence and reconciliation semantics in provenance imports. Add full-history 30/60/90-day outcome windows with censoring/missingness.

**Verification/acceptance:** each accepted control works at its declared boundary with an external verifier where required; unavailable infrastructure/outcomes remain explicit. Do not create more speculative features instead of closing the existing obligations.

### GP-T037 — Reconcile claims, documentation and operational runbooks

**Priority:** P2. **Depends on:** T001 and final implementation evidence. **Files:** `status.md`, `BUILD_STATE.md`, previous audits, `docs/claims.md`, SECURITY/SUPPORT/DEPLOYMENT/DEMO and duplicated spec sources.

- Date and supersede contradictory historical claims, including “core done,” absent roster/handler, persistence complete and purported contract integrity. Keep valuable history without presenting it as current status.
- Correct repository/security/support links and backup/rollback procedures. Distinguish a test reference that resolves from a current passing result.
- Make first install, diagnosis, backup, upgrade, restore and vulnerability reporting executable from shipped docs.

**Verification/acceptance:** source/claim/evidence register agrees with the actual artifact; links and runbook commands are checked; no untested promise of completion, enforcement, learning or savings remains.

### GP-T038 — Define the open-core and paid-feature boundary

**Priority:** P2/owner decision. **Depends on:** T001. **Files:** licensing/product decisions, distribution design, tier/capability and proposed entitlement interfaces.

- Prepare a concrete feature/artifact/support split for the owner's stated open-core direction. Retain current license truth; do not infer that root `private` prevents VSIX distribution.
- Once approved, implement only the necessary entitlement lifecycle, key management, expiry/trial/offline behavior and data portability for that offering. Capability settings are not payment enforcement.

**Verification/acceptance:** shipped artifacts, terms and capability behavior match an approved product decision; local tier editing cannot defeat claimed entitlement enforcement. Pricing, license changes and customer contracts need owner decisions; do not invent them to mark engineering done.

### GP-T039 — Make brownfield gates depend on actual tested evidence

**Priority:** P1. **Depends on:** T006/007/011. **Files:** comprehension engine, test discovery/coverage adapters, edit preflight and Comprehension/CodeMap UI.

- Resolve source paths inside the authorized repo and distinguish inferred filename adjacency from discovered/executed test coverage.
- Bind risk and characterization/mutation/contract checks to current code/test revisions and actual outcomes. Invalidate stale records and expose missingness.
- Enforce the required brownfield gate before the production edit path, not only through an optional viewer.

**Verification/acceptance:** a target filename in a test comment cannot count as coverage; unrun/failed/stale tests cannot pass; risky uncovered work is blocked until required evidence exists; risk factors have traceable sources.

### GP-T040 — Clarify state ownership and remove concurrency hazards

**Priority:** P2. **Depends on:** prioritize T008–013 correctness first. **Files:** large server/workbench services, application-service boundaries, persistent-store schemas and lifecycle cleanup.

- Document which service owns run, queue, agent, learning, document and evidence state and the transaction between them. Replace direct private-member coupling incrementally behind stable contracts.
- Add versions/migrations and cross-window concurrency control. Atomic file replacement alone does not prevent lost updates.
- Format complex UI/state handlers and extract cohesive units where it enables meaningful behavioral tests, without a broad rewrite.

**Verification/acceptance:** simultaneous windows cannot silently overwrite acknowledged updates; shutdown/reload releases processes/DB handles; refactor preserves behavior and reduces duplicate ownership.

### GP-T041 — Demonstrate the actual installed product

**Priority:** P1. **Depends on:** T007/011–014/025/026/031; live runtime/account. **Files:** `DEMO.md`, isolated demonstration repository, candidate evidence pack.

- Prepare a bounded representative story, expected changes and failure case. First prove deterministic execution, then repeat with an admitted live ACP runtime in the installed VSIX.
- Retain runtime identity, context digests, permissions, actual diff/build/tests, approvals, usage/unknown cost, cancellation and independently verified export.

**Verification/acceptance:** an unfamiliar user can follow the runbook to a verified deliverable; deliberately failing tests leave a failed/rework state. Credentials alone are not the remaining work until the engineering dependencies pass. No narrated or fixture-only live-demo claim.

### GP-T042 — Execute human and customer acceptance studies honestly

**Priority:** P2/claim-specific. **Depends on:** T026/027/033/041 and participants/customer access. **Files:** preregistered study protocols, data/analysis tools and acceptance records.

- Assign owners and prerequisites for first-value/assistive testing, twenty-story effectiveness study and two-editor/two-SCM evidence. Build any missing claimed editor integration before scheduling its success test.
- Collect consented, preregistered measurements including adverse and missing outcomes; preserve raw evidence and analysis criteria.

**Verification/acceptance:** real participant/customer results and explicit human disposition; no unsupported ROI/productivity/quality claim. These obligations remain open when prerequisites are external and cannot be replaced by generated study templates.

## 4. Endpoint-to-workflow register

These are the 32 originally orphaned methods, plus the loop controls previously allowlisted. The later host service file now supplies detected consumers; the work remaining is actual schema-correct, authorized, functioning user journeys. Re-enumerate from the registry before editing because concurrent GUI work may have landed.

| Owner surface | Methods | Required observable result |
|---|---|---|
| Runtime / phase board | `loop.start`, `loop.status`, `loop.stop`, `loop.resume`, `loop.replay` | Real run/control/gate continuation; cancellation remains available during execution; replay is labeled and isolated |
| Routing / economics | `router/requestModelCall`, `router/dependencyRatio` | Policy decision tied to actual invocation and honest usage/unknowns |
| Memory / instructions | `memory/retrieve`, `memory/write`, `memory/layered` | Authorized source-scoped content with correct hashes, precedence and budgets |
| CodeMap / comprehension | `comprehension/record`, `comprehension/gate` | Evidence-backed current file risk/coverage and an enforced edit gate |
| Registry / agent studio | `adapters/discover`, `adapters/plug`, `adapters/unplug`, `adapters/promote` | Durable lifecycle with actual runtime eligibility and admission |
| Agent portability dialogs | `portability/export`, `portability/import`, `portability/diff`, `portability/trust` | Verified payload, preview/diff, authenticated trust and atomic installation |
| Training Queue | `trainer/train`, `trainer/promote`, `trainer/rollback` | Real evaluated job, reviewed candidate promotion and effective rollback |
| Delivery operations | `tenancy/register`, `queue/enqueue`, `queue/tick` | Validated durable tenant/story admission linked to actual execution/completion |
| Evidence / explanation | `decisions/record`, `decisions/ablate`, `decisions/gate`, `annotations/add`, `issues/record` | Stable evidence IDs, restart-safe lookup and verified gate inputs |
| Governed tool execution | `tools/invoke` | Approved useful operation or explicit denial, bounded output and revocation |
| Preview / replay lab | `simulation/serve`, `simulation/timeControl`, `golden/run` | Isolated simulation and meaningful deterministic replay, never counted as live production work |

## 5. Validation procedure and evidence format

Run the repository's canonical scripts sequentially where they share the suite lock. Confirm script names at the candidate before execution. This audit did not run the complete release procedure below and does not represent it as passed.

```powershell
git status --short
git rev-parse HEAD
npm ci
python -m pip install -e ./core[dev]
node scripts/generate-bus-types.mjs --check
node scripts/check-surface-coverage.mjs
node scripts/check-mvp-traceability.mjs
node scripts/check-claims.mjs
node scripts/check-compatibility.mjs
node scripts/check-no-telemetry.mjs
npm run test --workspace=extension
npm run test --workspace=webview
npm run test:core:serial
npm run test:budgets
npm run check:golden
npm run check:parity
npm run build
npm run package
npm run check:bom
npm run check:notices
```

Additionally run the verifier's Cargo tests, installed-package validation, real editor-host journeys, vulnerability/security tests, platform/remote matrix, assistive validation, fault recovery, live demo and required soak using their checked-in harnesses. Review destructive fixture paths before cleanup and keep validation repositories isolated. Do not mechanically run unsupported commands against customer data.

Each acceptance result should record:

```json
{
  "finding": "GP-009",
  "task": "GP-T009",
  "requirementIds": ["FR-M4-05", "FR-M4-06"],
  "sourceCommit": "<full-sha>",
  "dirtyTree": false,
  "artifactSha256": "<exact-vsix-digest-or-null-for-source-test>",
  "environment": {"os": "<version>", "editor": "<version>", "python": "<version>"},
  "command": "<exact-command>",
  "startedAt": "<UTC timestamp>",
  "durationSeconds": 0,
  "exitCode": 0,
  "result": "pass|fail|blocked|not-run",
  "counts": {"passed": 0, "failed": 0, "skipped": 0},
  "evidencePaths": ["<logs-and-artifacts>"],
  "limitations": ["<what-this-test-does-not-prove>"]
}
```

Do not check in secrets, private source or raw sensitive prompts. Store sanitized reproducible evidence with hashes and controlled access where necessary. An evidence record must contain observed values; the template above is not evidence.

## 6. Definition of completion and resumption

A task closes only when its specified production behavior works, the regression can detect its failure, relevant consumers are connected, required package/installed checks pass, and the clause/claim register links the final evidence. “Code written” is an intermediate state. A future/owner-dependent obligation can be explicitly scoped out of a narrower release, but is still not implemented against the original full-product goal.

Before declaring production readiness, evaluate all R1–R8 gates in the requirements audit against one identified candidate. Retain known limitations and support boundaries. The original baseline, later local fixes and in-progress UI edits must not be combined into a fictional single green release.

On resumption, inspect git changes and this task register, rerun the smallest relevant reproduction, complete the earliest unmet dependency, then update the execution log below. Preserve existing work and move to independent tasks if an external dependency is unavailable. Request only the concrete external information/decision that is actually needed; do not repeatedly ask to perform already-authorized repository work.

## 7. Execution log for future implementation

| Task | State | Implementation commit | Acceptance evidence | Remaining dependency |
|---|---|---|---|---|
| GP-T001–GP-T042 | OPEN — handoff prepared | None attributed to this audit | See companion audit for baseline checks, confirmed probes and later delta review | Execute tasks and retain candidate-bound evidence |

The audit itself changes only the two requested GP documents. Concurrent source changes and commits belong to their existing authors/sessions and are not credited as remediation performed by this audit.
