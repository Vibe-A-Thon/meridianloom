# MERIDIAN LOOM — Build State

> Resumption state. Updated after every completed task. If the session is interrupted, read this file and DECISIONS.md first, then continue from the recorded task.

**GOVERNING ORDER (changed mid-build — see DECISIONS.md G-0):** the repo owner committed `gaps-requirements.md` + `gaps_implementation.md` (+ `gaps_guix.md`, `gaps_guix_implementation.md`), which supersede the S0 → GUI → C1…C6 sequencing. New order: **F−1 (legal gate, human-gated — see DECISIONS.md) → F0 Flight Recorder → F1 Governor → F2 Evidence Gate (human-run) → F3 Orchestra → F4+ (old C3–C6).** All six original spec files remain requirement sources; copies of all ten docs are in `docs/spec/`.

- **Current phase:** F3 — Orchestra (N2 Unassailable ENGINEERING COMPLETE — exit assessment 84154a6; N3=F2 is the human evidence gate)
- **Current workstream:** N2 — Unassailable; WORKSTREAM G COMPLETE (T29 verified built; T30/31/32 dispositioned; T33 corpus at 103 ≥ 100). NEXT: N2 exit assessment — walk every exit criterion in futures-implementation.md §N2, map each to test/commit evidence, mark pass/blocked-with-owner, then decide N3 (=F2 evidence gate, human) and F3 resumption.
- **N2-E closure:** T23 verified green (40 tests: adapters-pinning + adapters-identity, host-side by parallel session MV3-T01/T01b). T25 dispositioned in DECISIONS.md — matrix + honesty check + platform-matched smoke runner all exist; product/version-dimension rows and evidence-channel qualification blocked on real smoke evidence (MK5 forbids unbacked rows), matrix file coordinator-owned.
- **Last commit:** 0631837 — C6 DONE: `differentiation/` — annotations/bookmarks as chain entries (FR-M10-16); counterfactual replay labelled evidence (FR-M13-08 — test corrected: removing a load-bearing TRUE factor flips the decision); quality-diversity archive keeping novel-or-better candidates (FR-M14-11); retirement handover with ledger-recorded transfer (FR-M16-10); batch epic ingestion splitting ## headings into stories with - bullets as acceptance (FR-M19-07); agent-detected issues as queryable ledger evidence with severity vocabulary (FR-M24-05); scheduled tasks with 60s floor and due/mark_run (FR-M30-05); deterministic fuzz cases from schema boundaries (FR-P5-09); deployment execution as a D7-honest raising seam (FR-P8-02). ECO-06/ECO-08 recorded as ecosystem integrations on shipped seams (MCP client, import path). 9 tests green.
- **Last commit:** 90ad90e — C5 tenancy DONE: `tenancy/` — TenantRegistry with per-tenant roots (ledger/memory/adapters/models config) and NO fallback resolution (unknown tenant refused, never rerouted — R19 critical risk); assert_same_tenant canonical-boundary check (declared as wiring-error detection, not an OS sandbox, SEC-32 honesty); per-tenant MemoryFabric proven non-sharing. StoryQueue: priority + dependency ordering, WIP limit, aging-based starvation prevention that SURFACES starved stories as an error (not silent priority fiddling), FR-M21-02 per-story agent instance binding refused on sharing. FR-M22-01 multi-repo targets with own worktree/branch/PR each. FR-M29-02 documentation gate: public API changes block Review without updated docs. 10 tests green.
- **Last commit:** 40da05d — C4 DONE: `trainer/` — LearnedDelta kinds closed to prompt/playbook/checklist/rule at the type level (D5; skill packs/code can never be constructed); executable-looking content refused pre-write (SEC-26); harvest_signals reads all six FR-M14-01 sources; assert_not_mid_story refuses training during build/verify (FR-M14-09); evaluate = margin over incumbent AND safety-invariant check FIRST — 'skip security scan…' rejects at 0.99 vs 0.10 (FR-M14-05 monotonic); promote requires human_approved=True (FR-M14-06), versions monotonic-max numbering with retention bound 3 (FR-M14-08, caught count-after-prune bug), rollback in one action restoring prior content as a new version (FR-M14-07), promotion ledger-recorded with evidence; autonomy_decision implements D6 exactly (≥0.85 yield over ≥20 AND ≤0.12 calibration; hold on partial; demote at 10 consecutive below); FR-M15-03/04 probation scoring gate. 12 tests green.
- **Last commit:** 8b1c9cf — C3 portability DONE: `portability/` — export_package ships the adapter folder as a signed zip w/ agent card (FR-M16-01/02); pre-export scan BLOCKS on SEC-07-detected secrets and untrusted-tagged content, no override (FR-M16-03 — corpus-tested); exclusions recorded on the card and never zipped; verify_package refuses bad signatures before anything touches disk (FR-M16-04); diff_against_workspace shows added/overwritten; import requires explicit confirm, refuses missing tools naming them, zip-slip guarded, admits to PROBATION not trust (FR-M16-04/05/06); run_upgrade_regression runs the agent's own tests/ in the sandbox as the upgrade admission ticket (FR-M16-09). Sandbox env allowlist extended with APPDATA/USERPROFILE/PYTHONUSERBASE (user-site plumbing, not credentials — pytest now runs in-sandbox). 10 tests green (31 with M9/M28).
- **Last commit:** 9ee82c9 — F3 FINAL CORE SLICE M32+M27 DONE: `replay/` cassettes (record rows+blob ciphertext+wrapped keys with pinned seed; replay restores and Ledger.verify() proves the chain; tamper → hard fail; AC-15) + `simulation/` Simulation Core (serves the generated x-methods contract — divergence test vs sidecar registry = FR-M32-09/AC-28 core; scripted scenario families FR-M32-04; ledger writes real + replay_of-tagged FR-M32-02; time control pause/step/play-Nx/jump FR-M32-06; golden runner AC-16; zero model calls enforced by AST guard FR-M32-05). 10 tests green. F3 CORE COMPLETE — all modules built; remaining AC items are host-integration, F2-human, or release-process owned (see F3 exit assessment).
- **Last commit:** 7ef91ac — F3-M13 DONE: `decisions/` — DecisionRecord with inputs/retrieved-memory/tool-calls/output/confidence (FR-M13-01); Rationale renders ONLY with the 'unverified narrative' label, no unlabelled path (FR-M13-02); CalibrationTracker records outcomes and derives mean |claimed−observed| beside any claim, insufficient-evidence (<5 samples) reported as None (FR-M13-03); AblationRunner replays with a factor removed, results labelled as evidence and change-detected (FR-M13-04); evaluate_gate consumes tests/scans/approvals ONLY — a rationale argument raises ExplanationGateError (FR-M13-07), and high blast-radius classes (schema migration, public API contract, security-relevant, cross-service) require ablation results before the gate (FR-M13-05). 7 tests; F3 core suite regression 46 green.
- **Last commit:** 6da3e4f — F3 remaining slice 1 DONE: `phases/` PhaseSet provider (D8) — nine §6 phases shipped as policy/phases.yaml, workspace override first-wins, malformed/duplicate packs fail-closed with NO fallback constants (banned pattern 24); M5 deltas on the adapter registry — probation→active promotion gate (only active takes live work, inactive agents surface accurate Learning substate), immutable versions with old manifests kept on upgrade + exact acting version ledger-recorded, retirement keeps manifest+history, provenance prebuilt/custom/bridged derived from discovery root + bridge declaration. 11 tests green (24 with M31).
- **Last commit:** ff782ca — F3 step 7 M31 DONE: `adapters/` framework (discovery with root precedence FR-M31-02; validation incl. allow-list + digest-tamper + missing files, invalid listed-with-errors never loaded FR-M31-03; hot plug/unplug/re-plug with in-flight checkpoint+escalation, EVERY roster adapter proven to survive unplug+re-plug FR-M31-04; probation admission FR-M31-07; plain-python bridge sandboxed w/ guarded permission-routed tool path FR-M31-06; learned/ export/import FR-M31-12; dependency graph validation FR-M31-15) + roster.py materializer. Shipped `adapters/` at repo root: 14 real §6.10 MUST-v1 adapter folders (chief-orchestrator, phase-orchestrator, analyst, architect, tech-lead, scrum-master, developer, front-end-engineer, qa-engineer, qa-lead, security, reviewer, xai, governance) — manifest w/ embedded content digest, deterministic stand-in agent.py (JSON in/out, zero model calls, real ACP runtime bound at launch), skills/, instructions/, learned/, tests/. 13 framework tests green; shipped smoke test passes from its folder. Roster expansion (Release/SRE/Trainer/Onboarding v1.x, Refactoring/Legacy SHOULD) lands with their phases.
- **Last commit:** ae15d1f — F3 step 6 M38 DONE: `comprehension/` — deterministic module records (imports/imported-by/test adjacency incl. characterisation markers/git history with backdated age/incidents/conventions, no model calls, whole-day age rounding for determinism); risk score = age+coupling+coverage+change-failure with blast-radius + gate-strictness escalation (FR-M38-03); AC-35 gate blocks uncovered high-risk modules and cites the comprehension record in the reason; records deposit as procedural comprehension memory (FR-M38-05). Two corrections en route: gate aligned to AC-35's exact wording (uncovered-only — coverage by ordinary tests admits), Windows path separators normalized. 9 tests green.
- **Last commit:** 2fb93e8 — F3 step 5 M7 DONE: `memory/` package. fabric.py: three tiers under .meridian/memory/ (procedural markdown-committable, semantic always naming its source, episodic); every entry carries provenance (FR-M7-04); gated writeback — contradicting candidates quarantined for humans, never merged (FR-M7-05); untrusted origins can never reach procedural memory + tagged in other tiers (FR-M7-07, poisoning defence); pinned entries writable only by human actors (FR-M7-11); retrieval ranked (trusted>confidence>recency), budgeted, included AND cut both ledger-logged with the consuming agent (FR-M7-08/13); episodic retention consolidates past-horizon entries into summaries and archives raw traces, never deletes (FR-M7-06); layered procedural org→team→repo with lower overriding (FR-M7-09); stable-order Markdown export bundle, diffable (FR-M7-10). instructions.py: AGENTS.md/CONVENTIONS.md/.meridian/instructions/**/adapter instructions/ discovered only from trusted tiers (repository/story text NEVER — FR-M7-16), precedence adapter→workspace→user→organisation (FR-M7-14), per-invocation digest recording so behaviour changes trace to instruction changes (FR-M7-15), digest-diff across versions. 15 tests green.
- **Last commit:** 873af57 — F3 step 4 M9/M28 DONE: `tools/` package. surface.py: ToolSurface single dispatch — per-agent permitted sets checked BEFORE execution, denials ledger-recorded as rejections (FR-M9-03); sandbox with env scrubbed from scratch (no inherited credentials), wall-clock timeout that kills and reports (FR-M9-05/07); results capped with explicit TRUNCATION_MARKER never silent (FR-M9-04); dependency additions carried as distinct change class into the ledger (FR-M9-06); MCP servers pinned version+digest+trust-ack with no bypass path (FR-M9-08). mcp_client.py: minimal stdio JSON-RPC MCP client (initialize/tools-list/tools-call) proven against a real fixture server + server-error surfacing (FR-M9-01). search.py: SemanticIndex port + deterministic lexical-semantic TF index, incremental (FR-M28-03, embeddings slot behind the port when a model tier exists); reuse_first_check returns a mandatory citation + duplicate-suspect flag (FR-M28-04). editing.py: anchored hunk application with span cap refused before anchor work, binary/generated exclusion by default with allow-list override (FR-M28-05/07). LSP (FR-M28-01) and tree-sitter (FR-M28-02) consumed via existing engine bridges. 21 tests green.
- **Last commit:** 31c9eef — F3 step 3 M4 DONE: `runtime/` package. loops.py: LoopDefinition with 8 bound fields validated at load (FR-M4-02, UNBOUNDED is an explicit declaration only L4/L6 may make), fan-out path-overlap refusal (FR-M4-09), six canonical loops with §6.1 bounds incl. L4 'merged AND CI green' amendment. state.py: typed fields + declared reducers, reducer-less concurrent write = error (FR-M4-04). runner.py: LangGraph 1.0.8 StateGraph + SqliteSaver behind the LoopRunner Protocol port (D1, deps pinned in pyproject); one super-step = one DAG pass over the body (back-edges incl. self-loops dropped, cycles realised ACROSS iterations); per-node checkpoints (FR-M4-05); GateSuspend persists completed writes and resume continues from the gate's state (FR-M4-06); replay forks from the run's INITIAL state + overrides, entries tagged replay_of (FR-M4-07 — recorded: checkpoint-precise forks need a checkpointer state copy); exit-before-bounds ordering so finished loops never breach; bound breach halts with escalation-target ledger entry (FR-M4-08); fan-out width cap default 4 (FR-M4-10); per-iteration ledger entry (FR-M4-11). 14 tests green (28 with M8).
- **Last commit:** 12d4b46 — F3 step 2 M8 DONE: `router/` package — Router.request_model_call dispatches to the M33 engine first; non-router-eligible outcomes refuse (FR-M8-15) with ledger-recorded rejection naming the engine outcome kind; explicit human_override is the only bypass, recorded with why_llm=human_override (FR-M8-16, router-assigned); invalid/missing engine why fails closed. dependency_ratio per agent/phase/story/class from ledger evidence (model_call vs engine_executed), None when denominator 0; policy ceilings (specific-key > default) breach → policy_update escalation entry. AC-26 shape test: 1/6 ratio under 0.35 ceiling. 14 tests + engine dispatch 17, all green.
- **Last commit:** a22c23d — N2-T33 batch 3 DONE: 44 fixtures (103 total, ≥100 floor asserted in driver). NEW FINDINGS FIXED: (1) consent forgery — privacy replay now honours only policy_version privacy/v1 entries (SEC-37); (2) nine more SEC-07 token shapes: AGE, sq0atp, sq0csp, pypi-, hf_, xapp-, shpat_, SG., dop_v1_. Families: canonical malleability ×6, merkle proofs ×5, retention windows ×5, observer confidence ceiling ×3 (overclaim downgraded not raised), privacy consent ×5 (forgery/wildcard/revoke), ingestion ×4 (dup/excluded/vendor/disk), policy bundles ×3 (tamper→invalid, expiry, sanity), economics binding ×3, redaction ×9. Full local regression: 160 passed (corpus+privacy+receipts+economics+contracts).
- **Last commit:** 3739fc9 — N2-T33 batch 2 DONE: 28 fixtures (policy refusals ×6 incl fail-closed/unknown-profile/anonymous-approval; worktree boundary ×6 incl traversal/absolute/unicode/branch-dotdot + canonical-boundary-holds; identity ×4 incl spoof-stays-asserted, unavailable, bot-never-human, OIDC-deferred-raises; economics injection ×4 incl detail-JSON provenance claim cannot upgrade; redaction ×6 — FOUND+FIXED 5 real SEC-07 escapes: JWT, sk-ant-, npm_, AIza, URL creds; attribution spoof ×2). 59/100 fixtures, all green; privacy/receipts/trailer suites re-run (36) no regression.
- **Last commit:** 6ba8b94 — N2-T33 batch 1 DONE: adversarial corpus harness (`tests/adversarial/`, hosted_execution and passive_observation run as SEPARATE tests per FR-M46-10) + 31 fixtures (chain tamper ×7, redaction ×10 incl Bearer, privacy erasure, schema refusal, encoding ×2, signatures ×3, trailers ×3, notarisation ×3, sanity). Corpus found a REAL escape: SEC-07 missed `Authorization: Bearer` tokens → pattern added, fixture green. Raw forged INSERT is detected-by-verify not refused-at-write — documented honestly in fixture + DECISIONS (BEFORE-INSERT trigger = coordinator follow-up). Coverage limits stated in harness docstring: no general-resistance claim.
- **Last commit:** 6d48b59 — N2-T28 DONE (Workstream F COMPLETE): closed cost-category vocabulary (tokens/provider_charge/subscription/compute/storage/failed_attempt/human_review/rework/follow_up_fix) enforced on CostLine+BillLine; by_category breakdown rides every Aggregation; `reconcile_bill` — detailed billing reconciles ≤1% with residue reported, undetailed billing returns reconciled:False (not run, never passed), exclusions documented by category+reason; `check_budget` — hosted stops before ceiling (reaching = refused, enforced), unhosted returns allowed=True enforced=False with 'unenforced' label. 20 economics tests green. NOTE: economics.py is a library with ledger-derivation entry points; RPC/UI surfacing is a later integration decision (record if N2-G or F3 surfaces need it).
- **Last commit:** c20e2fd — N2-T26/T27 DONE: `metrics/economics.py` — CostLine bound to gate_sequence + merged_commit; closed provenance vocabulary (invoice_reconciled/vendor_api/locally_inferred/unknown) enforced in the type; Aggregation carries by_provenance+by_measurement beside every total (FR-M45-04 structural); merged/abandoned split per change; AC-51 reconcile_sample(20 changes, tolerance 0.5%) with residue reported never absorbed (incl. within-tolerance residue still named); lines_from_ledger defaults honestly to locally_inferred, refuses to mint vendor_api; bind_gate_and_commit attaches latest approved gate + headCommit. 11 tests green.
- **Last commit:** 815c4fd — N2-T21/T22 MCP-gateway leg DONE: `mcp/invoke` binds the session to the caller-declared client identity at assurance `asserted` (D38 vocabulary) with reason stated ("no executable digest or resolved version at this boundary"), recorded in the ledger entry blob AND returned in the result; contract updated properly — methods.json source edited preserving formatting, `$defs/McpClientIdentity` hoisted, generate-bus-types.mjs rerun, `npm run check:contracts` green (an earlier json.dump reformat was caught and amended out, 815c4fd). 14 mcp tests green. Earlier: b9f6cc4 — N2-T24 core leg DONE: `contract_versions.py` resolves derived-evidence sources to pinned versions from `shared/schema/external-contracts.json`; `interop/notarise` entries now record `externalContractVersion` in the encrypted detail (rides chain + bundles), unpinned tools (aider, continue, …) degrade visibly as `"unpinned"` + named in RPC `unpinnedContracts` (NFR-40); 8 new tests green, interop+drift suites (30) no regression. T21/T22/T23 host-side already built by parallel session as MV3-T01/T01b (identity.ts, pinning.ts + tests — verified present, not re-done).
## AUDIT EXECUTION PROGRESS (18 September 2026)

Executing `audit-1-k-g-impl.md`. DONE this session: TASK-001 (ledger v5 gapless BEFORE INSERT trigger, 1d3712e — corpus fixture now expects write-time refusal, 187 tests green), TASK-002 (one-chain-one-signer marker; host records fingerprint, collector refuses mismatch/unmarked-signed ledgers, 9447882), TASK-100 (extension manifest declares MIT + private flag dropped, validate-package 12/12, 7549d43), TASK-010 (31 Orchestra/F4+ methods + 68 defs registered in methods.json via scripts/_register_orchestra_contract.py; tiers.json gained 11 capabilities — simulation/golden are flight-recorder, e6970f6+f056167), TASK-011 (**GAP-001 CLOSED — the P0**: orchestra_handlers.py wires all 31 surfaces into SidecarServer dispatch with lazy workspace-scoped module instances; loop.* stubs replaced; tier gating enforced (orchestra surfaces refused without the tier, simulation open); 12 integration tests drive the real JSON-RPC path, 9060686; regression 61 green incl. drift/interop/mcp/collector). Found en route: loop.* contracted stubs pre-existed (NOT_IMPLEMENTED) — replaced, not duplicated. ROUND 2 DONE (18 Sep): TASK-020 (0e1b841), TASK-022 (bfd00d0), TASK-021 (6e24b86 — 20/20 parity, canned shapes aligned to production wire shapes), TASK-035+071 (b578c2e), TASK-104+103+041 (7a95532), TASK-070 (6a51f81). ROUND 3 DONE (18 Sep): TASK-200 (rebuild+validate, GAP-101 closed), TASK-310/GAP-103 (FR-M26-04 levers, 985f374), TASK-320/321 (orchestrator persistence + shutdown, 6153a90), TASK-330/331/340 (cross-origin trust + narrative ablation + interface contracts, d162340). ALL CORE-SIDE PLAN TASKS COMPLETE. ROUND 4 (18 Sep): host service layer landed (extension/src/orchestra/services.ts, 10 vitest green, tsc clean) — every Orchestra RPC callable from the host with contract-exact shapes. CROSS-SESSION NOTE for the GUI session: TASK-301..309 remaining work is SCREEN WIRING ONLY — import the matching functions from '../../orchestra/services' (or '../orchestra/services' relative to src) into your studio/screen components; the transport matches SidecarClient.request. ROUND 5 (19 Sep): GUI wiring begun — Loop Control panel (TASK-301, 699afc8, 4 vitest), Adapter Registry panel (TASK-305, ae29769, 3 vitest); generic sidecar pass-through for all 15 Orchestra prefixes + typed action-map entries for the remaining families; webview+extension tsc clean; GUI wiring round done: Loop Control panel (4 vitest) + Adapter Registry panel (3 vitest) + generic pass-through for all 15 Orchestra families + typed action-map entries; webview suite 364/365 green solo (1 timeout-under-load, passes isolated); extension suite: lazy orchestra import landed (server construct no longer pulls LangGraph); maxWorkers 4→2 per measured starvation. REMAINING FLAKE (recorded honestly): a rotating set of ~3-5 real-subprocess e2e tests (adapters-launch, registry-bay, interpreter, steer, bus-types, tiers, doctor, evidence-chain) trip 30s spawn timeouts under suite parallelism on this machine — the failing SET rotates run-to-run and every one passes in isolation; pre-existing suite characteristic (the run-lock and the config comment document it), needs CI hardware or serial execution for a 100% run. Artifact: rebuilding VSIX with the GUI wiring (validate-package re-run). External gates unchanged: F2/MV5, D37, AC-50, soak, live demo.

## GOAL SHIFT (18 September 2026) — production-ready / marketable goal

Owner's stated goal: the product "should be by now production ready, fully functional with thorough testing, and marketable to other companies." A goal-based audit pass was appended to `audit-1-k-g-req.md` (section 24) and `audit-1-k-g-impl.md` (Marketability Phase, TASK-100…105). Re-graded under the goal: GAP-001 (Orchestra unwired) P0; live demo + F2/MV5 P0-external; SEC-GAP-01 P1; license-manifest residue P1 (LICENSE/MIT exists at root — manifests don't declare it, `private: true` remains); new marketability gaps MKT-001…006 (manifest/license mismatch, open-core split statement, upgrade procedure, OFL notices, telemetry attestation, support surface). Not marketable today for three independent reasons (wiring, evidence, distribution residue) — all have implementation paths; none needs new architecture. This section supersedes the "ALL PHASES ENGINEERING-COMPLETE" headline for product-readiness claims: engineering-complete ≠ marketable, and the register now says so.

## F3 exit assessment (17 September 2026, this session — core-side)

Every AC mapped to evidence or a named owner. Core-side = this session's modules; host-side = parallel session (MV1–MV3). Verdict: **F3 core engineering complete; end-to-end acceptance needs the live ACP runtime (demo path B) and M32 cassettes.**

| AC | Disposition | Evidence / owner |
|---|---|---|
| AC-01 clarified spec + ambiguity register | CORE MECHANISM PASS, e2e needs runtime | engine ambiguity + assisted gap; live chain = demo path B |
| AC-02 seven-phase chain unprompted | CORE PASS (phase set + L4 graph + loops), e2e needs runtime | phases 6da3e4f, L4 chain 31c9eef incl. Security per D14 |
| AC-03 tests authored, AC traceably covered | CORE MECHANISM PASS, e2e needs runtime | engine validate + tool test_run; traceability via ledger story_id |
| AC-04 PR with story ref, agents, gates, ledger range, cost | HOST PARTIAL (MV2/MV3 PR card) + economics c20e2fd | end-to-end = demo B |
| AC-05 ledger answers per-line provenance | PASS (core) | ledger+attribution suites; viewer = host |
| AC-06 rework re-enters loop with reason | CORE PASS | runtime rework edges + rejection taxonomy (F1) |
| AC-07 kill sidecar mid-loop, resume ≤1 node | CORE PASS | per-node checkpoints 31c9eef; window reload = host |
| AC-08 no orphan processes, 3 platforms | SINGLE-PASS, MATRIX BLOCKED | orphan monitor + run lock; CI matrix owner: release |
| AC-09 skill-pack swap changes conventions | HOST RUNTIME | adapter skills/ + instruction precedence 2fb93e8; demo B |
| AC-10 yield/cost dashboard, 20 real stories | BLOCKED — F2 human study | spend/trust instruments (N1) ready to display it |
| AC-11 injection → no out-of-set tools, ledgered | CORE PASS | tool permission gate + adversarial corpus (103) + SEC-07 |
| AC-12 no protected-branch change w/o recorded human approval | PASS (editor-side) / SCM BLOCKED D37 | merge gate + approvals; SCM = pilot platform team |
| AC-13 human edit conflict surfaced, never lost | PASS | worktree manager conflict detection (F1/M18 tests) |
| AC-14 abort leaves primary tree byte-identical | PASS | worktree isolation AC-13/14 tests (F1) |
| AC-15 cassette replay byte-identical ledger | PASS | replay/ 9ee82c9: rows+blob ciphertext+wrapped keys recorded; replay restores and verify() proves; tamper test fails verification |
| AC-16 golden corpus CI, no model calls | PASS (runner core) | SimulationCore.run_golden validates story+cassette+expected_root; zero-model-call AST guard; CI wiring = scripts |
| AC-17 steer visible next iteration + ledger | HOST (one-steer N1 closed) | steer/* RPCs + HostedSteerController |
| AC-18 below-confidence → structured clarifying question | CORE PASS | engine ambiguity/assist (M33 slices) + loop suspension 31c9eef |
| AC-19 VS Code Remote-SSH | SINGLE-PASS / MATRIX BLOCKED | remote.test.ts; CI matrix owner: release |
| AC-20 dry-run packet graph + cost, zero writes | HOST PASS (MV2 preflight) | run/preflight + cancel record |
| AC-21 blame shows agent identity + trailer → ledger range | PASS | trailers + Co-Authored-By + AC-49 trailer spec d0b93e8 |
| AC-22 synthetic credential redacted + logged | PASS | SEC-07 redaction (16 shapes) + corpus redaction fixtures |
| AC-23 custom adapter probated ≤5s, no restart; removal retires, history remains | CORE PASS (semantics); watch+UI = host | plug/unplug/re-plug 13 tests ff782ca + M5 deltas 6da3e4f |
| AC-24 plain-Python bridge governed, wrapped code unmodified | CORE PASS (bridge); full packet = demo B | sandboxed + permission-routed ff782ca |
| AC-25 export→import applies learned/rules, no model call | CORE PASS | learned/ export/import ff782ca + engine rules loader (M33) |
| AC-26 zero model calls on deterministic classes; ratio ≤0.35 | CORE PASS (shape) | M33 zero-call structural tests + router ratio AC-26 test 12d4b46; measured on reference story = demo B |
| AC-27 deterministic-path model call refused + ledgered | PASS | test_router_m8 (12d4b46) |
| AC-28 webview unchanged against production sidecar | CORE PASS; GUI scenario parity = GUI session | contract-drift test compares sidecar registry vs generated methods.json (9ee82c9); screens run against SimulationCore — host integration |
| AC-29 egress outside allow-list → paused + ledgered | PARTIAL — allow-list declared + sandbox honest (SEC-32); pause = host enforcement | enforcement owner: host runtime |
| AC-35 brownfield gate | PASS | comprehension gate ae15d1f |

**F3 exit verdict:** core module spine PASS (M33, M8, M4, M9/M28, M7, M38, M31, phases, M5, M13). NOT met as numbered: AC-15/16/28 (M32 Simulation Core + cassettes — the one remaining core build slice), AC-10 + §10.2 quality bar (F2 human evidence — D35), 3-platform/remote matrix + live agent demo (release process / demo path B / pilot).

## N2 exit assessment (17 September 2026, this session)

Every §N2 exit criterion mapped to evidence. Verdict: **N2 engineering complete; evidence-gated items blocked with named owners** — no criterion is silently dropped.

| Criterion | Verdict | Evidence |
|---|---|---|
| AC-45 SCM block | BLOCKED — D37 (pilot customer) | enforcement-point vocabulary + honest editor-side declaration (N2-T05, `governance/enforcement_points.py`); owner: platform team |
| AC-46 revocation 5 min + in-flight stop | PASS | `test_identity_assurance.py`, `test_policy_bundles.py`, merge_gate revocation path (FR-M42-06/SEC-31) |
| AC-48 bypass detection + coverage downgrade | PASS | N2-C (dd71929): five detectors, durable entries, same-session downgrade |
| AC-49 archive/compact/restore verifies; third-party trailer parse | PASS | T18 (d0b93e8, `test_trailer_ac49.py` 7 tests) + T16 (`test_ledger_archive.py`) + standalone verifier cargo 9 |
| AC-50 two editors/two SCMs | BLOCKED — human/customer | owner: pilot |
| AC-51 20-change reconciliation, residue reported, no provenance blend | PASS | T26/27 (c20e2fd, `test_economics.py` 20 tests) |
| AC-52 binary swap visible | PASS | MV3-T01b `identity.ts` + `adapters-identity.test.ts` |
| NFR-35 backfill determinism | BLOCKED — POST-MVP | FR-M41-16/17 backfill is F3+ scope per mvp-req-final §M41 |
| NFR-36 revocation propagation | PASS | identity_assurance + policy_bundles suites |
| NFR-37 capture margin reported | PASS | `observers/retention.py` record_capture (achieved_margin), suite green |
| NFR-38 archive restore budget + growth published | PASS | `test_ledger_archive.py` prints per-10k growth + 3-year restore |
| NFR-39 portable verification | PASS | trailer spec v1 + reference parser + verifier crate |
| NFR-40 contract drift visible | PASS | dbe6950 + contract_versions (b9f6cc4) |
| NFR-41 1% bill reconciliation + exclusions | PASS | reconcile_bill (6d48b59) |
| NFR-42 zero-loss recovery | PASS (single-platform) / matrix BLOCKED | `test_resilience.py` + `record-resilience.mjs`; 3-platform+remote like T31 |
| NFR-43 7-day soak | BLOCKED — elapsed time | soak.mjs ready; owner: release process |
| SEC-32 enforcement-point honesty | PASS | N2-T05 + EnforcementBadge; audit record per decision |
| SEC-33 digest pinning refusal naming both digests | PASS | `pinning.ts` + tests (MV3-T01) |
| SEC-34 adversarial corpus, no elevation above inferred | PASS | 103 fixtures (a22c23d), hosted/passive split |
| SEC-35 bundle signature fail-closed | PASS | evaluate_bundle + corpus BUNDLE fixtures |
| SEC-36 receipts verifiable without servers | PASS | test_ledger_receipts.py (public-keys-only) |
| SEC-37 erasure across storage/exports/backups | PASS | privacy module + restore replay + corpus + consent-forgery fix |
| SEC-38 dispute correction append-only | PARTIAL — mechanism PASS, flow N/A | append-only triggers + corpus CHAIN fixtures prove no deletion/alteration; no dispute-correction flow exists because FUT-018 trusted-team scope has no dispute mechanism — recorded in DECISIONS |
| Independent-reviewer statement | PASS | `enforcementPoint` rides every gate decision detail (FR-M42-12 wiring) |

**Next:** N3 is the F2 evidence gate (human study, not a build phase). F3 resumption: M8 router behind engine, then M4 loops, M9/M28, M7, M38, M31 roster, M5/M6/M13/M26 — interlock: FR-M46-16 growth gate binds engine growth until per-class value measured.

- **Orchestrator note:** parallel session works in this tree — never stage or overwrite files outside your task; stage by explicit pathspec. FR-M18-06/09 out of F1 scope per gaps plan (SHOULD v1.x).

## N1 status + CROSS-SESSION TASK LIST for the GUI session (owner's second session — read this)

**N1 engineering (this session) is COMPLETE** across workstreams A–E host halves. The GUI session owns the following, tracked by the blocking gate:

1. **Surface the 10 mustSurface instruments** (flips `shared/schema/unsurfaced.json` entries to `resolvedMustSurface`): trust/score, trust/scoreDecomposition, trust/reasonDistribution, trust/compareAgents, trust/jcurve, trust/tokenmaxxing, trust/doraExport, spend/series, spend/forecast, spend/pricing. N1-T24: every chart carries a written finding (A-10/H7). N1-T25: Cross-Vendor Spend panel moves onto spend/series + spend/pricing + spend/forecast and gains team + cost-centre dimensions. Machine-readable work list: `node scripts/check-surface-coverage.mjs --json .meridian/surface-coverage.json`.
2. **Consume the coverage envelope** (N1-T06): replace the local `entries.length === 1000` detection in `webview/src/workbench/governance/Analytics.tsx` with the envelope's `truncated`; a truncated figure states it in text and disables derived projections. Envelope: `result.coverage` (`result.coverageEnvelope` on trust/score).
3. **Retire the duplicate steer path (AMD-M25/G-03)**: delete `run/steer` from `extension/src/workbench/service.ts` (~line 1059) and its consumers `webview/src/workbench/catalogue/RunsTab.tsx:124`, `webview/src/workbench/operations/WorkspaceOperations.tsx:1122` (+ their tests); move the UI onto the canonical `steer/*` RPCs; instantiate `HostedSteerController` in the launch path. Then flip `extension/test/steer-protocol-surface.test.ts` to `toNotContain` (marked in the test). Exit criterion "exactly one steering implementation" stays FAIL until this lands.
4. `observe/captureEvidence` is the tested capture surface for observer evidence capture UI (N1-T21 GUI affordance).

**N1 exit criteria status:** AC-41 full-scan equality at 50k PASS (45928f1) · AC-42 three-state attribution PASS (963b1b3, corpus precision 1.0000, floor 0.95) · AC-43 gate live and blocking (61d4788) — FAIL until items 1–2 · AC-44 PASS (ba55d22, four cases) · AC-47 evidence_expired PASS (ba55d22) · **NFR-33 re-measured in full on 9 September 2026** (budget 5s at 50k, all inside it): rejectionRate 3.90s, score 1.21s, reasonDistribution 1.26s, jcurve 3.77s, doraExport 3.74s, compareAgents 0.43s, spend/series 0.82s, spend/forecast 0.74s. **These had gone stale and the criterion was recorded PASS while failing.** AMD-M37 (per-bucket computation) and FR-M41-06 (attribution floor) landed after the `45928f1` measurement and nobody re-ran it: rejectionRate had reached 5.81s and doraExport 7.34s, both over budget, for two commits. Fixed by dropping a redundant full ledger scan from `compute_rejection_rate` (the diff population is a subset of a scope already read, and its COUNT was discarded) and by replacing the DORA time-to-restore linear tail scan with a bisect over already-sorted stamps. `core/tests/test_nfr33_budgets_are_current.py` now fails if a budgeted metric is missing from this line, and CI runs the benchmark on every push. · NFR-34 same-operation disclosure PASS (envelope) · one steering implementation PENDING GUI item 3.


## N1 GUI items — CLOSED (9 September 2026, GUI session)

All four cross-session items above are done. Evidence:

1. **Ten mustSurface instruments surfaced** — `webview/src/workbench/governance/Observatory.tsx`
   consumes trust/score, trust/scoreDecomposition, trust/reasonDistribution,
   trust/compareAgents, trust/jcurve, trust/tokenmaxxing, trust/doraExport,
   spend/series, spend/forecast and spend/pricing. Every figure renders `null`
   as "Insufficient evidence" (or "Not measurable" under the FR-M41-06 floor)
   and never as zero; every chart carries a written finding (N1-T24, A-10/H7);
   `observatory.test.tsx` (11 tests) asserts those refusals rather than the
   happy path. **The surface-coverage gate now passes: 62/70, exit 0.**
2. **Coverage envelope consumed** (N1-T06) — the Cross-Vendor Spend panel is
   routed to `SpendObservatory`, which reads `coverage.truncated` from the
   envelope and disables the forecast on it. The legacy `Analytics.tsx` Spend
   component, which guessed truncation from `entries.length === 1000`, is
   marked SUPERSEDED and routed nowhere (N1-T25).
3. **`identity.revoke` surfaced** — a confirmed operator control in the
   Approvals view (`Gates.tsx`), stating both consequences: the revocation
   binds immediately, and approvals the identity already gave stop counting at
   the next gate execution. The undeclared orphan is gone.
4. **AMD-M25 / G-03 closed — exactly one steering implementation.**
   `HostedSteerController` is now the only caller of any `steer/*` RPC.
   Its session dependency was narrowed from `AcpClient` to a structural
   `SteerableSession` so the workbench (which runs through `AdapterSession`
   and injects fakes in tests) can share it; `adoptSession`/`release` let the
   workbench keep owning its own lifecycle while the controller owns the
   protocol. `run/steer` survives as a workbench action that delegates.
   Delivery is an explicit policy on the one implementation — `now` for a
   hosted session, `nextTurn` for the workbench, which is what its interface
   promises and what a one-turn-at-a-time adapter can accept.
   `steer-protocol-surface.test.ts` now guards the substance: service.ts makes
   no steer RPC call of its own.

**Also closed in the same session — a defect this session introduced and then
found in review.** Skills, instruction files, SDLC phase tags and tool
connections were catalogued, bound, displayed and exported, and none of them
reached the running agent, while the interface claimed they did. The agent
received only `${title}

${brief}

Your role: ${role}`. Fixed by
`extension/src/workbench/briefing.ts`: `composeBriefing` assembles the whole
document (brief, role, phase and its purpose, instruction files in precedence
order, enabled skills, connected systems without credentials, accepted memory)
and `convene` selects agents phase by phase in SDLC order, falling back to
every active agent when nobody is tagged. The launch path's second prompt
composer was deleted — the briefing is composed once, recorded on the run, and
sent verbatim, so what the history shows is what the agent got.
`briefing.test.ts` (19 tests) asserts each binding arrives.

## Phase N0 — Quiesce (COMPLETE)

| Task | Disposition |
|---|---|
| T01 tree quiet / J9 | organisational (owner's second session) — recorded, not enforceable by this session |
| T02 sequential suite runs | extension 368✓ 1 skip; webview 177✓; core 1109✓/1 — the 1 (X-29 cursor disappearance) was load-timing, fixed by T06 retry (ec36bd2); sequential run at a1b9b36+ window, machine quiet, vitest legs 21s/35s |
| T03 verify perf floor | **kept** — meets target on a quiet machine (TestVerifyPerformance 2/2 in 11.7s; F0 measured ~31k entries/s); full-suite breach occurred only under 71-min parallel load. Disposition recorded; AMD-M10 satisfied (not silently red) |
| T04 observer handicap test | load-sensitive, no defect — green solo and in quiet runs (9/9) |
| T05 workbench + webview operations reds | both fixed (parallel session repaired their committed test; extension 24/24, webview 7/7) |
| T06 e2e contention | X-29 disappearance tests got one-retry tolerance, 2s budget unchanged (ec36bd2); extension real-sidecar e2e green in quiet sequential run |
| T07 BUILD_STATE reconcile | done — F1 workstream table C–H corrected (8cede03) |
| T08 dependency findings | vite 5.4.21 patch bump; vitest/vite majors = dated accepted-risk note (dev toolchain only, owner: repo owner) (a1cea9f) |
| T09 fresh-workspace policy | D43 closed (ship-and-copy, 33e2cc3); uniform bootstrap + license override chain + fresh-workspace tests (a1b9b36, 26+212+92+34 green); AC-53 satisfied |

N0 exit: sequential runs green or dispositioned; BUILD_STATE matches log; every dependency finding upgraded or accepted-risk-noted; AC-53 pass. **N0 exit criteria are met** (J9 recorded as organisational).

## Phase F2 — Evidence Gate (pending-human-evidence, D35)

Per gaps_implementation.md §F2 this is a decision phase, not a build phase: 20 real stories through F0+F1 over weeks, measured not judged. Exit criterion: a written human decision (go/stop/pivot/kill) with the raw ledger slice attached. **Cannot be executed by the build agent; not faked.** Every measure is already computable from shipped surfaces, so no engineering work is blocked on it:

| F2 measure | Computable from |
|---|---|
| Rejection rate before vs after gating, greenfield/brownfield | `trust/rejectionRate`, `trust/reasonDistribution` (FR-M37-01/02), reconciliation oracle |
| Defects caught by gates the agent missed | gate outcome entries vs PR ingest range (`test_pr_ingest.py` shape) |
| Change failure rate vs baseline | `trust/doraExport` change_failure_rate (D27 proxies) |
| Approval hygiene | roles/approver entries, FR-M20-06 rubber-stamp inputs |
| Time cost per gated PR | ledger timings in the ingest range |
| Provenance queries actually run | ledger query RPC telemetry |
| First-value retention (week 8) | human observation |

F3 proceeds per D35 under the user's standing continue instruction.

## Phase F1 exit criteria (from gaps_implementation.md §F1)

| # | Criterion | Status | Proof |
|---|---|---|---|
| 1 | AC-31 ACP Registry agent installs via Adapter Bay → probation → packet, permission requests policy-checked before human sees them | pass (engineering) / human-gated (real registry install) | `acp-registry-source.test.ts`, `adapters-probation.test.ts`, `adapters-launch.test.ts`, `acp-permission-gate.test.ts` (FR-M34-04 policy check wraps the approver); a live install from the real ACP Registry is human/CI |
| 2 | AC-32 external-agent PR ingested, gated (Security+Review), merged only after recorded human approval — one ledger range | pass (engineering) / human-gated (real Copilot-from-Jira PR) | `core/tests/test_pr_ingest.py` — ingest records origin pass + gates in one contiguous range, entries before response (FR-M10-08), merge requires recorded approver identity, changed head invalidates approval; real Copilot/Jira PR is human-gated |
| 3 | AC-34 rejection rate + reason distribution per agent, greenfield/brownfield, reconciles to ledger (≥20 stories) | pass (engineering) / human-gated (20 real stories) | reconciliation oracle in `test_trust_metrics.py` (recomputes from raw ledger rows, asserts RPC equality); 20-story half is F2's evidence gate |
| 4 | AC-36 Orchestra disabled → Flight Recorder + Governor fully functional | pass | tiers e2e (4059975) + `tiers-e2e.test.ts`; route-table/command-registry tier gating (H3) |
| 5 | AC-37 hosted + observed agent's spend by vendor/model, reconciling to ledger | pass (engineering) | `test_spend_series.py` — six dimensions, vendor/model/agent splits, recorded vs estimated cost never blended silently (D32), reconciles to ledger rows |
| 6 | NFR-30 ACP conformance suite green in CI | pass (local suite) / CI-provisioning remainder documented | `extension/test/acp-conformance.test.ts` — real-subprocess fake wire agent, spec sections: init/version negotiation, session lifecycle, streaming shapes, permission flows, cancellation, fs/terminal methods; upstream-harness-in-CI remainder documented in the test header, not faked |
| 7 | X-31 Adapter Bay parity with Devin Desktop Agent Command Center, measured | human-gated | five-engineer timed study (GF1 task 32) — cannot be run by the build agent |
| 8 | No path to merge an external agent's PR without a recorded approver identity | pass | `test_merge_requires_recorded_approval`, `test_status_blocked_without_approval`, `test_changed_head_invalidates_approval` in `test_pr_ingest.py` |
| 9 | Full `npm test` + `pytest` green | **pass** (with one documented load artifact) | core: 900 passed / 1 failed in the 71-min full run — the failure is `test_verify_100k_under_budget`, a perf-floor assertion (10,033 entries/s vs 12,000 floor) failing only under parallel-session CPU load; the file passes 10/10 in isolation (18.9s, unchanged since 60858d5). Extension: 365 passed / 40 files / 1 skipped in the combined run. Webview: see row below. |
| 10 | Webview vitest green | **fail — cross-session red, not F1 scope** | webview solo run: 176 passed / 1 failed. The failure is `src/workbench/operations/operations.test.tsx` ("keeps inactive profiles in the Learning room…") — a heading "Learning dojo" the component stopped rendering. File last touched by the parallel GUI session's commit 7f26bff; persistent (re-run solo, not flaky). `webview/**` is the GUI session's active territory — recorded here as theirs to close before GF1 exit; engineering F1 surfaces (extension 365+, core 910) are green. |

Note: the ten GF1 **screens** (10.1, 10.6, 10.27, 10.28, 10.32, 10.43, 10.47, 10.49, 10.16, 10.50) are the parallel GUI session's workstream (gaps_guix_implementation.md GF1), built against real gated external PRs; all their sidecar RPC surfaces (`trust/*`, `spend/*`, gates, steer/clarify, roles) are done and tested on this side. GF1 exit criteria (H7 written findings, snapshots, axe-core, colour-blind) are the GUI session's to close.

## Mapping of completed S0 work onto the new plan

| Old (S0) | New (F0) | Status | Proof |
|---|---|---|---|
| A1 scaffold (FR-M1-01..03) | F0-A1 | done — fuller superset (5 views, 12 commands) retained, see DECISIONS.md G-0 | `manifest.test.ts`, commit 4e52a8a |
| A2 thread discipline (FR-M1-04) | — (baseline) | done | `thread-discipline.test.ts`, 2a7a1f6 |
| A3 SecretStorage adapter (FR-M1-06/07) | F0-A4 | done | `secrets.test.ts`, 558d779 |
| A4 progress/cancellation (FR-M1-09) | — (baseline) | done | `progress.test.ts`, 6779a7b |
| A5 bundling (FR-M1-10) | — (baseline) | done — dist/meridian-loom-0.0.1.vsix | c0df98d |
| B6 spawn + framed JSON-RPC (FR-M3-01/09) | F0-A2 | done | e2e stdio test, 43a907e |
| B7 dual teardown (FR-M3-02/03) | F0-A2 | done — orphan-guard test | a64eee4 |
| B8 spawn errors + interpreter chain (FR-M3-04/05/05a) | F0-A3 | done | ac274dc |
| B9 remote support (FR-M3-11) | F0-A3 | done | bde3e95 |
| B10 health/restart/versioned RPC/no-listener (FR-M3-06/08/10) | F0-A5 | done | ecf7de9 |
| B11 generated bus types + staleness check (FR-M32-09 foundation) | F0-A5 | done — `npm run check:contracts` blocks divergence | 1527530 |

## Phase F0 exit criteria (from gaps_implementation.md §F0)

| # | Criterion | Status | Proof |
|---|---|---|---|
| 1 | AC-30 first value < 15 min, no model credential, Weave shows external session with vendor tags, any-line provenance | pass (engineering) / human-gated (measurement) | 10.45/10.46/10.40 screens on real sidecar data (40d8e30, c3aa115, 73922f7); real claude.exe session detected live on the dev machine (X-29 e2e); the 5-person 15-minute measurement is human-gated — NFR-28 |
| 2 | AC-33 provenance survives uninstall; bundle verifies with open verifier on clean machine | pass (engineering) / human-gated (uninstall act) | open verifier tests verify exported bundles using only bundled material, no Meridian installed (4dfbdb1 — verify.py + Rust meridian-verify); trailer persistence in git is filesystem-verified by hook e2e tests (86aec58); the physical VSIX uninstall is a human/CI-matrix act |
| 3 | AC-34 (partial) rejection rate per agent split greenfield/brownfield reconciles to ledger over ≥10 sessions | partially — engineering half proven: `test_reconciliation` recomputes the rate independently from raw ledger rows and asserts equality with the trust/rejectionRate RPC result (df7bf0a); ≥10-sessions human half remains pending-human-evidence |
| 4 | NFR-28 first value < 15 min (5-person measurement — human-gated; engineering proxies automated) | human-gated | 10.40 First-Run four steps on real data (73922f7); the 5-person measurement cannot be run by the build agent |
| 5 | NFR-29 observation ≤5% latency, never blocks | **pass** | measured: hook burst ~0.0ms, RPC reads ~0.0ms during 500ms in-flight observation (9e190c0); budget 100ms |
| 6 | FR-M36-07 zero model calls — CI test fails on any model-client import in F0 paths | **pass** | `test_no_model_calls.py` (13) + `no-model-calls.test.ts` (12), ed66495 |
| 7 | Chain verification passes; corrupted entry detected and sequence named | **pass** | `test_ledger_verify.py` (10) — 3.2s/100k, payload/prev-hash/gap divergence naming (60858d5) |
| 8 | Broken observer telemetry degrades to `inferred` with visible warning within one session, never silence | **pass** | observer framework NFR-32 downgrade tests (522d07b); visible warning surfaced in 10.46 observer health (c3aa115) |
| 9 | No orphaned sidecar after window close/reload/disable (all platforms, Remote SSH) | pass (mechanism) / matrix human-gated | dual-teardown orphan-guard tests both halves (a64eee4); Windows/macOS/Linux/Remote-SSH matrix is CI/human |
| 10 | G5 tier isolation: disabling Governor/Orchestra leaves Flight Recorder fully functional | **pass** | tiers e2e on real sidecar: upper-tier RPCs refused with structured error, FR fully functional, config-only re-enable (4059975) |

## F0 workstream progress

| Workstream | Tasks | Status |
|---|---|---|
| A — Shell and sidecar, minimum viable | 1–7 | **done** (4059975; doctor 5730d66; tiers e2e prove G5) |
| B — Ledger core | 8–12 | **done** (e25a530; 631f86f run_id/origin v2 migration per gaps_initiation §5) |
| C — Deterministic attribution (no model calls) | 13–16 | **done** (ed66495; FR-M36-07 exit criterion 6 proven by test) |
| D — Observers | 17–22 | **done** (c60874b; X-29 + NFR-29 measured within budget; SEC-27 pass) |
| E — Portable provenance | 23–27 | **done** (481f5fa hook UI command; 90b5e6c agent identity trailers; abfc94c full signed bundle — proofs/signature/compliance; 4dfbdb1 open verifier verify.py + meridian-verify; 1ea71c8 spec docs) |
| F — Rejection measurement, minimum | 28–30 | **done** (5b54279 rejection capture + ledger v4 rejection entries; 820f59a greenfield/brownfield classification; df7bf0a ledger-derived rejection rate, cached, split, reconciling) |
| G — The three screens (interlock GF0) | 31–36 | **done** (82b84b9 export plumbing; 40d8e30 10.45 Flight Recorder; c3aa115 10.46 External Agents; 5f082f6 10.7 Ledger; 73922f7 10.40 First-Run; c0a1243 X-27…X-30 invariants; b3732aa theme close-out) |

## Later phases (per gaps_implementation.md)

- F1 Governor — ACP host (M34), gates over external PRs, roles, trust analytics, spend, 10 screens — **in progress (workstream A)**
- F2 Evidence Gate — human-run, 20 real stories; recorded as pending-human-evidence (DECISIONS.md)
- F3 Orchestra — old C1+C2 re-based on ACP; Simulation Core built here as regression harness
- F4+ — old C3–C6

## F1 workstream progress

| Workstream | Tasks | Status |
|---|---|---|
| A — ACP host | 1–8 | tasks 1–5, 8 done (c4a4805 client; df4b267 adapter re-base; f22ef6a registry; 289d33a permission gate SEC-28; 8ed0bcf conformance; task 5 worktree isolation below); 6–7 done (eeec15a MCP server FR-M34-06; 88a2b32 upstream tracking FR-M34-05) |
| B — Gates over other people's work | 9–14 | **done** (47e809b policy engine; 0791ec9 merge gate; 3abb236 halt; 7f68ec5 pr/ingest + pr/status FR-M35-04/05 with AC-32 one-range reconciliation; 4ae3cc7 pr/conflicts FR-M35-07; 910aad8 E-GR-03 taxonomy in policy/) |
| C — Human identity and roles | 15–16 | **done** (identity D9 closed; roles FR-M20-02..08) |
| D — Steer and clarify | 17–18 | **done** (d3521ce + 61298aa, FR-M25-01/02/03/04/06 + NOT_HOSTED honest controls) |
| E — Trust analytics | 19–25 | **done** (1e2f94b tasks 19–21; 85b555c/104fbf1/ea9ac2e/f3cafd3 tasks 22–25; FR-M37-01..05/07/08; D24–D27) |
| F — Cross-vendor spend | 26–29 | **done** (8e23fc3/3608ecd, FR-M39-01..04; D28–D33) |
| G — Remaining observers | 30 | **done** (2289a36 cursor/codex/devin, D34) |
| H — Screens (interlock GF1) | 31–32 | host half **done** (539e564 D33 wiring); screens are the GUI session's GF1 workstream; X-31 human-gated |

## Decisions closed

- D4, D10, D18 — pre-decided (kickoff)
- D20 — Claude Code + Copilot observers first (DECISIONS.md)
- D23 — commit-msg hook default, git notes fallback (DECISIONS.md)
- D22 — OPEN, human-gated (DECISIONS.md → Deferred)

## Phase log

- F1 Workstream B tasks 12–14 done — external PR gating + multi-agent conflicts + rework taxonomy. New sidecar module `core/meridian_core/pr/` (ingest: gh-api payload → Meridian story — origin record actionType pr_ingest origin connector, per-agent attributed hunks via trailers > author markers > inferred fallback, agent pass as proposed-change entries, routing through verify/security/review gate profiles; conflicts: per-commit hunk attribution over a git range, agent-vs-agent overlaps as the distinct class agent-conflict). New RPCs `pr/ingest`, `pr/status`, `pr/conflicts` in governor-tier capability `governor.pr-gates` (single ownership holds; G5 refusal tested). Merge gate `check_merge` gains an explicit `requires_approval` override so a PR subject targeting a protected base branch needs a recorded human approval bound to the head digest; AC-32 test proves the agent's pass, the gates and the approver in one contiguous ledger range. E-GR-03: no spec defines the taxonomy, so it is DEFINED in `policy/rework-reasons.yaml` (versioned, 8 classes) with the rationale in `core/meridian_core/rejection/taxonomy.py`'s docstring; `trust/detectRejections` gains reason/reasonNote params, and both the F0 rejection detector and the conflict detector stamp fail-closed (unknown → other + note; the mechanical shape moves to tool_calls, idempotency keys on it). Suite: pytest 639 green at the full root run (test_pr_ingest 22, test_pr_conflicts 10, test_rework_taxonomy 13 among them), extension vitest 317 passed, `check:contracts` green, no-model-calls green.

- F1 Workstream A task 6 (MCP server exposure, FR-M34-06) done: new sidecar RPC `mcp/invoke` in capability `governor.mcp-server` (single-ownership registry holds; bus types regenerated) — the governor tier gate is the permission gate (disabled ⇒ TIER_DISABLED, G5), every call is ledger-recorded as a `tool_call` entry (vendor `mcp`, direct confidence, story `mcp:<tool>`) BEFORE it executes, and the tool maps onto the existing read-only handler (ledger_query/export_bundle/verify, trust_rejection_rate). Extension: `extension/src/mcp/server.ts` implements MCP 2025-03-26 directly (initialize/ping/tools/list/tools/call/resources/list/resources/read; NDJSON stdio; no protocol deps); structured sidecar errors mirrored verbatim (TIER_DISABLED shape included); resources `meridian://open-ledger-spec` + live `meridian://doctor-report`. `extension/src/mcp/main.ts` is the standalone vscode-free entrypoint (same framed sidecar spawn, FR-M3-01/11; stdout MCP-only per FR-M3-09); bundled via `npm run build` to `dist/mcp/mcp-server.js` and smoke-tested as a real spawned process. Suite: pytest 500→512 (test_mcp_invoke 12), extension vitest 282→296 (mcp-server 13 unit + 1 real-sidecar e2e), `tsc --noEmit` clean, `check:contracts` green, no-model-calls green.
- F1 Workstream A task 7 (upstream contribution, FR-M34-05) done: `extension/src/acp/UPSTREAM.md` (host-generic vs Meridian-specific inventory; Apache-2.0 publication plan — LICENSE stays with the human owner per D22; layering strategy on native ACP; supported-SDK declaration `<!-- supported-acp-sdk: 0.4.5 -->`), `docs/upstream/vscode-acp-issue.md` (tracks microsoft/vscode#265496, signal order, review cadence), `extension/test/acp-upstream-version.test.ts` (4 tests; warns never fails on SDK drift). Deferred: wiring the MCP server into VS Code via `vscode.lm.registerMcpServerDefinitionProvider` (needs a newer `@types/vscode` than 1.95 pinned in the repo) — the server is spawnable and tested standalone today.

- F1 Workstream A task 5 (worktree isolation, M18) done: new `core/meridian_core/worktree/` (manager: create/list/remove/abort/conflicts — dedicated branch `meridian/<story>` under `.meridian/worktrees/<story-id>/`, worktree-local agent identity + `Meridian-Hosted-Agent` trailer hook via per-worktree `core.hooksPath`, abort deletes never-pushed branch and leaves the primary tree byte-identical). Sidecar RPCs `worktree/create|list|remove|abortStory|conflicts` in a new governor-tier capability `governor.worktrees` (single-ownership assertion holds); create/remove/abort ledger-recorded with `worktree_ref`. Extension: `meridian.abortStory` wired to the abort RPC (confirm-first), new `meridian.openWorktree` command (worktree/list → `vscode.openFolder` new window, FR-M18-08). AC-13/AC-14-shaped tests by name; conflict report consumed later by the M40 RunRequest/preflight flow. Suite: pytest 457→500 (test_worktree 43), extension vitest 268→282 (worktree-commands 13, manifest 1), `tsc --noEmit` clean, `check:contracts` green. FR-M18-06 (signed agent commits, SecretStorage key) and FR-M18-09 (GC retention) remain v1.x per spec — not built here.

- Workstream E (tasks 23–27) done: pytest 360→406, extension vitest 128→137, `tsc --noEmit` clean, `check:contracts` green throughout. Proof commits 481f5fa, 90b5e6c, abfc94c, 4dfbdb1, 1ea71c8. Cargo-based verifier tests skip-and-notice when cargo is off PATH.
- Workstream F (tasks 28–30) done: pytest 406→448 collected (test_rejection 20, test_greenfield 14, test_trust_metrics 9, schema tests updated for v4; cargo-based verifier tests skip-and-notice when cargo is off PATH), extension vitest unchanged at 137, `tsc --noEmit` clean, `check:contracts` green throughout. Proof commits 5b54279, 820f59a, df7bf0a. New surface: `trust/detectRejections`, `trust/classify`, `trust/rejectionRate` (capability `recorder.trust-metrics`, flight-recorder tier); ledger schema v4 (rejected_sequence/rejected_commit/rejecting_commit); workspace settings `meridian.rejectionWindowDays` (7), `meridian.greenfieldNewFileRatio` (0.5), `meridian.greenfieldMaxMedianAgeDays` (30).
- GF0 foundation (G0a–G0d) done: new `webview/` workspace (Vite+React+TS, vitest+RTL) — six themes + follow-vscode default, Iron Gall forced on high contrast; comfortable density default; Archivo + JetBrains Mono via @fontsource (latin subset; Commit Mono deferred, see `webview/FONTS.md`); invariant components (X-27 ConfidenceBar, RationaleBlock, AgentToken, ActionClassChip, VendorTag with geometric SVG glyphs — V10 glyph pass deferred); `shared/ts/webview-messages.ts` (hand-written, not generated — `check:contracts` green); extension host `RecorderPanel` (CSP nonce, asWebviewUri, serializer, no web storage), pure tier-gated `dispatchWebviewMessage` proxy, rename `meridian.openDashboard`→`meridian.openRecorder` (gaps §F0 names it; DECISIONS.md G-0), packaging copies `webview/dist`→`extension/webview-dist`. Suite: pytest 448, extension vitest 137→158 (recorder-panel 12, webview-rpc-proxy 8, webview-e2e 1 real sidecar round-trip), webview vitest 70, both `tsc --noEmit` clean, `npm run build` green (webview bundle 154.79 kB). Proof commits 2c563a7, 6999b8c, afbaf98.
