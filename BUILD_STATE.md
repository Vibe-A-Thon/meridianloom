# MERIDIAN LOOM — Build State

> Resumption state. Updated after every completed task. If the session is interrupted, read this file and DECISIONS.md first, then continue from the recorded task.

**GOVERNING ORDER (changed mid-build — see DECISIONS.md G-0):** the repo owner committed `gaps-requirements.md` + `gaps_implementation.md` (+ `gaps_guix.md`, `gaps_guix_implementation.md`), which supersede the S0 → GUI → C1…C6 sequencing. New order: **F−1 (legal gate, human-gated — see DECISIONS.md) → F0 Flight Recorder → F1 Governor → F2 Evidence Gate (human-run) → F3 Orchestra → F4+ (old C3–C6).** All six original spec files remain requirement sources; copies of all ten docs are in `docs/spec/`.

- **Current phase:** N2 — Unassailable (N0 quiesce COMPLETE, N1 COMPLETE)
- **Current workstream:** N2 — Unassailable; WORKSTREAM G COMPLETE (T29 verified built; T30/31/32 dispositioned; T33 corpus at 103 ≥ 100). NEXT: N2 exit assessment — walk every exit criterion in futures-implementation.md §N2, map each to test/commit evidence, mark pass/blocked-with-owner, then decide N3 (=F2 evidence gate, human) and F3 resumption.
- **N2-E closure:** T23 verified green (40 tests: adapters-pinning + adapters-identity, host-side by parallel session MV3-T01/T01b). T25 dispositioned in DECISIONS.md — matrix + honesty check + platform-matched smoke runner all exist; product/version-dimension rows and evidence-channel qualification blocked on real smoke evidence (MK5 forbids unbacked rows), matrix file coordinator-owned.
- **Last commit:** a22c23d — N2-T33 batch 3 DONE: 44 fixtures (103 total, ≥100 floor asserted in driver). NEW FINDINGS FIXED: (1) consent forgery — privacy replay now honours only policy_version privacy/v1 entries (SEC-37); (2) nine more SEC-07 token shapes: AGE, sq0atp, sq0csp, pypi-, hf_, xapp-, shpat_, SG., dop_v1_. Families: canonical malleability ×6, merkle proofs ×5, retention windows ×5, observer confidence ceiling ×3 (overclaim downgraded not raised), privacy consent ×5 (forgery/wildcard/revoke), ingestion ×4 (dup/excluded/vendor/disk), policy bundles ×3 (tamper→invalid, expiry, sanity), economics binding ×3, redaction ×9. Full local regression: 160 passed (corpus+privacy+receipts+economics+contracts).
- **Last commit:** 3739fc9 — N2-T33 batch 2 DONE: 28 fixtures (policy refusals ×6 incl fail-closed/unknown-profile/anonymous-approval; worktree boundary ×6 incl traversal/absolute/unicode/branch-dotdot + canonical-boundary-holds; identity ×4 incl spoof-stays-asserted, unavailable, bot-never-human, OIDC-deferred-raises; economics injection ×4 incl detail-JSON provenance claim cannot upgrade; redaction ×6 — FOUND+FIXED 5 real SEC-07 escapes: JWT, sk-ant-, npm_, AIza, URL creds; attribution spoof ×2). 59/100 fixtures, all green; privacy/receipts/trailer suites re-run (36) no regression.
- **Last commit:** 6ba8b94 — N2-T33 batch 1 DONE: adversarial corpus harness (`tests/adversarial/`, hosted_execution and passive_observation run as SEPARATE tests per FR-M46-10) + 31 fixtures (chain tamper ×7, redaction ×10 incl Bearer, privacy erasure, schema refusal, encoding ×2, signatures ×3, trailers ×3, notarisation ×3, sanity). Corpus found a REAL escape: SEC-07 missed `Authorization: Bearer` tokens → pattern added, fixture green. Raw forged INSERT is detected-by-verify not refused-at-write — documented honestly in fixture + DECISIONS (BEFORE-INSERT trigger = coordinator follow-up). Coverage limits stated in harness docstring: no general-resistance claim.
- **Last commit:** 6d48b59 — N2-T28 DONE (Workstream F COMPLETE): closed cost-category vocabulary (tokens/provider_charge/subscription/compute/storage/failed_attempt/human_review/rework/follow_up_fix) enforced on CostLine+BillLine; by_category breakdown rides every Aggregation; `reconcile_bill` — detailed billing reconciles ≤1% with residue reported, undetailed billing returns reconciled:False (not run, never passed), exclusions documented by category+reason; `check_budget` — hosted stops before ceiling (reaching = refused, enforced), unhosted returns allowed=True enforced=False with 'unenforced' label. 20 economics tests green. NOTE: economics.py is a library with ledger-derivation entry points; RPC/UI surfacing is a later integration decision (record if N2-G or F3 surfaces need it).
- **Last commit:** c20e2fd — N2-T26/T27 DONE: `metrics/economics.py` — CostLine bound to gate_sequence + merged_commit; closed provenance vocabulary (invoice_reconciled/vendor_api/locally_inferred/unknown) enforced in the type; Aggregation carries by_provenance+by_measurement beside every total (FR-M45-04 structural); merged/abandoned split per change; AC-51 reconcile_sample(20 changes, tolerance 0.5%) with residue reported never absorbed (incl. within-tolerance residue still named); lines_from_ledger defaults honestly to locally_inferred, refuses to mint vendor_api; bind_gate_and_commit attaches latest approved gate + headCommit. 11 tests green.
- **Last commit:** 815c4fd — N2-T21/T22 MCP-gateway leg DONE: `mcp/invoke` binds the session to the caller-declared client identity at assurance `asserted` (D38 vocabulary) with reason stated ("no executable digest or resolved version at this boundary"), recorded in the ledger entry blob AND returned in the result; contract updated properly — methods.json source edited preserving formatting, `$defs/McpClientIdentity` hoisted, generate-bus-types.mjs rerun, `npm run check:contracts` green (an earlier json.dump reformat was caught and amended out, 815c4fd). 14 mcp tests green. Earlier: b9f6cc4 — N2-T24 core leg DONE: `contract_versions.py` resolves derived-evidence sources to pinned versions from `shared/schema/external-contracts.json`; `interop/notarise` entries now record `externalContractVersion` in the encrypted detail (rides chain + bundles), unpinned tools (aider, continue, …) degrade visibly as `"unpinned"` + named in RPC `unpinnedContracts` (NFR-40); 8 new tests green, interop+drift suites (30) no regression. T21/T22/T23 host-side already built by parallel session as MV3-T01/T01b (identity.ts, pinning.ts + tests — verified present, not re-done).
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
