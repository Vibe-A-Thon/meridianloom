# Audit 1 — Kimi Requirements & Gap Analysis

**Date:** 17 September 2026 · **Auditor:** lead implementation session (Kimi) · **Evidence basis:** repository source of truth at HEAD, not status files. Every status below cites code or test evidence; a register claim was never taken as proof.

---

## 1. Executive Summary

**Overall state.** Meridian Loom is a working VS Code extension + React webview + Python sidecar with a real evidence spine: an append-only hash-chained Merkle-signed encrypted ledger, policy engine and merge gate, observer/capture machinery for external agents, a deterministic engine with an action-class catalogue, and a substantial workbench GUI built by the parallel session (catalogue, governance, operations studios plus ten screens). A later core-build phase (this session) added the full Orchestra modules — M8 router, M4 loop runtime, M9/M28 tools, M7 memory, M38 comprehension, M31 adapters + roster, phases, M5 deltas, M13 decisions, M27 cassettes, M32 simulation core, M16 portability, M14 trainer, C5 tenancy, C6 differentiation — each with dedicated tests (362 core tests + 9 verifier cargo tests green at 17 Sep).

**The major finding (P1).** The entire Orchestra/F4+ core layer is **implemented but unreachable**: none of it is registered in the sidecar's RPC handler table (`core/meridian_core/server.py`, 78 handlers) and none of it is invoked by the extension host. The modules are correct as libraries — and their invariants (ledger-first recording, router refusal, gate suspension, adapter hot-plug) are proven — but no runtime path from the product touches them. Until the wiring layer lands, the product's behaviour is unchanged by them.

**Other majors.** M32's AC-28 parity (every screen's scenario on both backends) is core-side only; the GUI session must run scenarios against `SimulationCore`. Golden-corpus CI runner exists core-side (`SimulationCore.run_golden`) but has no CI job wired. JIT harness intelligence (M47) is absent **by design** (POST-MVP, D44/J2 gated) — not a defect. F2's evidence study and several assurance criteria are human- or customer-gated and correctly dispositioned rather than faked.

**Security.** Strong honest posture: append-only enforcement by triggers (UPDATE/DELETE), 16+ credential-shape redaction corpus-verified, consent-forgery escape found and fixed (SEC-37), bearer/JWT/etc escapes found and fixed (SEC-07), MCP identity honestly at `asserted`. Known residual: raw forged SQL INSERT bypasses write-time refusal (detected by chain verify — recorded in DECISIONS); the sandbox egress allow-list is declared, not kernel-enforced (honest, per SEC-32).

**Tests.** ~1,900 test functions in `core/tests/`, an adversarial corpus (103 fixtures) with hosted/passive split, host-side vitest suites. Gaps: no end-to-end run (live ACP agent), no multi-platform rehearsal evidence, no soak run, several post-MVP suites absent by design.

**Production readiness.** Not production-ready: the live-agent demo path (B) is untested, release/operate is plans-only by decision (D7), SCM enforcement (AC-45) needs a pilot customer's platform team (D37). The extension packages and activates (per earlier phases' evidence); that evidence was not re-run in this audit pass.

---

## 2. Sources Audited

**Documents (24):** Requirements-implementation.md, Requirements_Final.md, viguix-implementation.md, VIGUIX_Final.md, vision.md, sample-meridian-loom-gui.html, jit-impl.md, jit-requirements.md, mvp-req-final.md, mvp-impl-plan.md, post-mvp-plan.md, SECURITY.md, status.md, gaps-requirements.md, gaps_initiation.md, gaps_implementation.md, gaps_guix.md, gaps_guix_implementation.md, futures.md, futures-implementation.md, futures_requirements.md, DEMO.md, DECISIONS.md, BUILD_STATE.md.

**Code areas:** `core/meridian_core/` (ledger, engine, router, runtime, tools, memory, comprehension, adapters, phases, decisions, replay, simulation, portability, trainer, tenancy, differentiation, governance, observers, metrics, server, interop, collector, attestation, contract_versions, identity, worktree, ingest), `core/tests/` (incl. `tests/adversarial/`), `extension/` (host, ACP/MCP, adapters), `webview/` (screens + workbench studios), `shared/schema/` + generated bus types, `verifier/` (Rust), `policy/`, `adapters/` (14 prebuilt), `scripts/`, `docs/`.

---

## 3. Requirements Inventory (normalized)

The canonical register lives in `status.md`/`mvp-req-final.md` (already maintained by the project); this catalog normalizes by module family rather than renumbering. Counts below are **canonical requirement families**, with collided IDs preserved via the M47 mapping (mvp-req-final §0.3/§14).

| Canonical family | Source IDs | Classification |
|---|---|---|
| Evidence ledger (append-only, hash chain, merkle, signed, encrypted blobs) | FR-M10-01…16 | MVP-adjacent core (F0) |
| Worktree isolation | FR-M18-01…09 | MVP core (F0/F1) |
| Sidecar host contract, lifecycle, RPC | FR-M3-01…, protocol | MVP (F0) |
| Observers (vendor capture, retention, fallback chains) | FR-M35/M44 (futures) | F1 + N1 |
| Policy engine, roles, merge gate, approvals, bundles, revocations | FR-M12/M20/M42 | F1 + N2 |
| Evidence metrics (trust, spend, DORA, coverage envelopes) | FR-M41 (futures), FR-M39 | F1 + N1 |
| Deterministic engine + action-class catalogue + learned rules | FR-M33 | F3 |
| Model router behind engine | FR-M8-15…18 | F3 |
| Loop runtime (six loops, bounds, checkpoints, gates, replay) | FR-M4 | F3 |
| Tool layer + sandbox + MCP client + LSP/tree-sitter | FR-M9, FR-M28 | F3 |
| Memory fabric + instruction library | FR-M7 | F3 |
| Brownfield comprehension + characterisation gate | FR-M38 | F3 |
| Adapter framework + roster + bridges + portability | FR-M31, FR-M34-02, FR-M16 | F3/C3 |
| Phase set provider + registry deltas | D8, FR-M5 | F3 |
| Decision records, calibration, ablation | FR-M13 | F3 |
| Cassettes + simulation core + golden corpus | FR-M27, FR-M32 | F3 |
| Trainer + autonomy promotion | FR-M14, FR-M15-03/04, D6 | C4 |
| Tenancy, story queue, multi-repo, docs gate | SEC-23, FR-M21/22/29 | C5 |
| Differentiation items | FR-M10-16, M13-08, M14-11, M16-10, M19-07, M24-05, M30-05, P5-09, P8-02 | C6 |
| GUI workbench (VIGUIX screens/studios) | VIGUIX_Final + gaps_guix | G-phases |
| Futures assurance (N0–N2: bypass detection, receipts/verifier, trailer spec, attestation, collector, contract versions, economics) | FR-M42/43/44/45/46 (rest) | N-track |
| JIT harness intelligence | M47 (was JIT M41) | POST-MVP, D44/J2-gated |
| Release/Operate execution | D7 | plans-only by decision |

---

## 4. Requirements Traceability Matrix (condensed)

Legend: **C** COMPLETE · **P** PARTIAL · **M** MISSING · **U** UNREACHABLE (implemented, no runtime path) · **D** DOCUMENTATION/DEFERRED · **conf** = confidence.

| Family | Evidence (code) | Tests | Status | conf |
|---|---|---|---|---|
| Ledger M10 | `core/meridian_core/ledger/` (schema triggers, canonical hash, merkle, Ed25519, blob AES-GCM, keystore) | test_ledger_*, receipts, privacy, archive, verdicts | **C** (core) | HIGH |
| Raw-INSERT escape detection | corpus `CHAIN-INSERT_FORGED` | adversarial | **P** (verify-layer only; no BEFORE-INSERT trigger) | HIGH |
| Redaction SEC-07 | `ledger/redaction.py` (16+ shapes) | corpus REDACT-×21 | **C** | HIGH |
| Privacy lifecycle SEC-37 | `ledger/privacy.py` (incl. privacy/v1 issuer filter) | privacy + corpus | **C** | HIGH |
| Governance engine/roles/merge gate | `governance/` (policy, engine, roles, merge_gate, bundles, revocations, bypass, enforcement_points) | extensive | **C** (core); SCM enforcement **P/BLOCKED D37** | HIGH |
| Engine M33 | `engine/` (catalogue, dispatch, capabilities, rules, assisted/generative, reporting) | test_engine_* | **C** core; **U** (not RPC-wired) | HIGH |
| Router M8 | `router/routing.py` (refusal, why_llm, ratio, ceilings) | 14 tests | **U** (no runtime caller) | HIGH |
| Loops M4 | `runtime/` (LangGraph+SqliteSaver, bounds, gates, replay tags) | 14 tests | **U** | HIGH |
| Tools M9/M28 | `tools/` (surface, sandbox, search, editing, mcp_client) | 21 tests | **U** (mcp/invoke wired separately) | HIGH |
| Memory M7 | `memory/` (fabric, instructions) | 15 tests | **U** | HIGH |
| Comprehension M38 | `comprehension/` (records, risk, AC-35 gate, memory deposit) | 9 tests | **U** | HIGH |
| Adapters M31 + roster | `adapters/` framework + 14 folders; unplug/re-plug proven | 13+13 | **U** core; host pinning/identity exists (MV3) | HIGH |
| Phases/M5 | `phases/` + AgentRegistryM5 | 11 tests | **U** | HIGH |
| Decisions M13 | `decisions/` | 7 tests | **U** | HIGH |
| Cassettes M27 | `replay/` (byte-identical + tamper fail) | 10 (in m32 suite) | **U** (golden CI unwired) | HIGH |
| Simulation Core M32 | `simulation/` (contract serve, time control, golden runner) | incl. drift test | **P** (AC-28 parity host-side open) | HIGH |
| Portability M16 | `portability/` (signed export/import, scan blocks) | 10 tests | **U** | HIGH |
| Trainer M14 / D6 | `trainer/` | 12 tests | **U** | HIGH |
| Tenancy C5 | `tenancy/` (registry, queue, docs gate) | 10 tests | **U** | HIGH |
| Differentiation C6 | `differentiation/` | 9 tests | **U** | HIGH |
| GUI workbench | `webview/src/workbench/**` + screens (catalogue/governance/operations + 10 screens) | vitest suites | **P** (VIGUIX screens ~partially covered; many VIGUIX surfaces absent) | MEDIUM |
| Futures N0–N2 | receipts/verifier/trailer/attestation/collector/contract_versions/economics | suites green | **C** core | HIGH |
| JIT M47 | none (by design) | n/a | **D** (D44/J2) | HIGH |
| MVP F0/F1 (sidecar, ledger, observers, run initiation, gates) | server.py + workbench | suites green | **C** for MVP register items as evidenced in mvp-impl-plan | HIGH |

---

## 5. Fully Missing Requirements

### GAP-001 — RPC wiring of the Orchestra layer
- **Requirement:** FR-M4/M8/M9/M28/M7/M38/M31/M13/M16/M14 + C5/C6 surfaces must be reachable through the product.
- **Current implementation:** modules exist under `core/meridian_core/` with tests; `server.py` `_handlers` registers none of them (grep-verified).
- **Missing components:** RPC methods in `shared/schema/methods.json`, handlers in `server.py`, host callers, GUI surfaces.
- **Impact:** the largest body of built functionality is invisible to users.
- **Severity:** P1 (BLOCKER-adjacent for the "working product" claim, though Flight Recorder/Governor tiers unaffected).
- **Remediation:** see impl plan TASK-001/002.
- **Acceptance:** each module's head method appears in the contract, handler invokes the module, integration test proves the path.
- **Confidence:** HIGH.

### GAP-002 — AC-28 screen scenario parity
- **Requirement:** AC-28 (webview runs unchanged against production sidecar; every screen's scenario runs on both).
- **Current:** SimulationCore contract-serving exists; scenario parity harness not wired to the webview.
- **Severity:** P1. **Confidence:** HIGH.

### GAP-003 — Golden corpus in CI
- **Requirement:** FR-M27-03 / AC-16 (corpus in CI, zero model calls).
- **Current:** `SimulationCore.run_golden` exists; no `scripts/` job or CI step invokes it on a corpus.
- **Severity:** P2. **Confidence:** HIGH.

### GAP-004 — Live-agent end-to-end demo (demo path B)
- **Requirement:** AC-01…AC-04, AC-24 measured shape; §10.2 quality bar (F2-baseline).
- **Current:** no ACP runtime binding exercised end-to-end; `MERIDIAN_MODEL_*` never required for builds — correct — but live path untested.
- **Severity:** P1 (external: runtime + credentials). **Confidence:** HIGH.

### GAP-005 — M32 ten scripted scenarios with per-screen data
- **Requirement:** FR-M32-04 named scenarios.
- **Current:** `SCENARIO_NAMES` constant exists; per-screen scenario payloads not materialized.
- **Severity:** P2. **Confidence:** HIGH.

### GAP-006 — Hosts of v1.x module remains
- **Requirement:** M17 full, M19 connectors (Jira/Confluence), M23 CI loop, M24 QA analytics, M25 human review tooling, M26 estimation (partially via economics), M30 observability, M21 phase orchestrators (queue exists; orchestration loop open), M22-02 interface contracts (targets exist; contract generation open).
- **Current:** absent or seeds only.
- **Severity:** P2 (each SHOULD/MUST v1.x per register). **Confidence:** HIGH.

---

## 6. Partially Implemented Requirements

### PART-001 — MCP egress governance
- Exists: sandbox env scrub + declared egress allow-list (`tools/surface.py`), honest label.
- Missing: kernel/firewall enforcement and the AC-29 pause action (host runtime). **Confidence:** HIGH.

### PART-002 — FR-M8-17 ceiling escalation into policy
- Exists: ratio + ceiling breach ledger entry (`router/routing.py`).
- Missing: escalation feeding a policy decision path (no consumer wired). **Confidence:** HIGH.

### PART-003 — Loop runtime resume via host
- Exists: GateSuspend + checkpoint resume (`runtime/runner.py`).
- Missing: host-side gate UI driving resume; runner is library-only. **Confidence:** HIGH.

### PART-004 — Instruction Library into agent briefings
- Exists: discovery/precedence/digest recording (`memory/instructions.py`).
- Missing: the one briefing path consuming it per invocation at runtime (binding recorded; no live consumer). **Confidence:** HIGH.

### PART-005 — Traceability from story to commit to ledger range in UI
- Exists: trailers + AC-49 verification core-side; ledger viewer host-side.
- Missing: the joined flow in the GUI (blame → trailer → range). **Confidence:** MEDIUM.

### PART-006 — Adapter onboarding wizard (FR-M15-01/02)
- Exists: manifest + registry validation, hot plug core-side.
- Missing: wizard UI and schema-driven manifest authoring. **Confidence:** HIGH.

---

## 7. Stub / Placeholder Implementations

- `deploy_execution` (FR-P8-02): intentionally raises with requirement id — **deliberate D7 seam**, not a defect. Classified STUB-INTENTIONAL.
- `meridian_core.replay`: cassette runner real; `simulation/` scenario payloads are the seam awaiting per-screen data (GAP-005).
- Roster `agent.py` bodies: deterministic stand-ins by design ("a prebuilt profile is not a bundled model" — stated in each manifest); real reasoning needs ACP runtime binding. Classified STUB-INTENTIONAL.
- `core/meridian_core/memory` semantic tier's embedding index: port exists (`SemanticIndex`), deterministic lexical implementation shipped; embeddings are POST-MVP. Not a defect.

---

## 8. Disconnected / Unreachable Features

- **Every Orchestra/F4+ core module** (GAP-001): zero references in `server.py` handler table; no host callers.
- `economics.py` gate-bound cost: library + ledger derivation; no RPC/surface consumer yet (recorded in BUILD_STATE as an integration decision).
- `contract_versions.stamp_external_contract`: wired into `interop/notarise` only; other derived-entry producers (observers) don't call it.
- `SimulationCore.serve`: no host/webview consumer; the workbench talks to the production sidecar only.
- `AnnotationStore`, `StoryQueue`, `QualityDiversityArchive`, `ScheduleRegistry`: no consumers.

---

## 9. UI / VIGUIX Gaps

The workbench (catalogue/governance/operations studios + FirstRun, FlightRecorder, Ledger, ExternalAgents, WeavePanel, AnyLinePanel, PullRequestCard, InteropPanel, LaunchScreen, ProvenanceReconciliation + studio screens) is real and test-covered, with enforcement-point badges, coverage envelopes, and the simulation band. Gaps against VIGUIX_Final (visual scale, every screen): the remaining VIGUIX surfaces (Dojo, Loop Graph 2.5D, Routing Observatory full, Dojo/canvas DOM parallels for several, Focus Mode with the X-26 band in every state, full 27-banned-pattern sweep validation beyond the existing banned-patterns test, density/keyboard-complete journeys) are partially present or absent; the sample HTML is a visual reference only and was not ported. GUI parity assessment belongs to the GUI session's own register; this audit did not re-verify screen-by-screen beyond file/test presence. **Confidence:** MEDIUM (evidence: file inventory + test suites; no rendered-pixel inspection).

---

## 10. JIT Gaps

M47 (renamed JIT module) is absent from code **by design**: POST-MVP, gated on D44 (adopt-or-not) and J2 hit-rate evidence. The artifact half (FR-M47-01…05) is the first candidate. No partial JIT implementation contaminates the build. **Confidence:** HIGH.

---

## 11. Security Gaps

- **SEC-GAP-01 (P2):** append-only triggers cover UPDATE/DELETE only; a raw forged INSERT is detected at verify-time, not refused at write time. Documented in DECISIONS; BEFORE-INSERT gapless trigger is the follow-up. Evidence: corpus `CHAIN-INSERT_FORGED`.
- **SEC-GAP-02 (P2):** sandbox egress allow-list is declared and recorded, not kernel-enforced (AC-29's pause is host-side). Honest per SEC-32; enforcement owner: host runtime.
- **SEC-GAP-03 (P3):** MCP gateway identity is caller-declared (`asserted` with reason); no executable digest binding for MCP clients (host has it for ACP launch).
- **SEC-GAP-04 (P3):** sidecar authorization: local-bus trust boundary is documented; interop notarisation and collector paths trust the workspace — acceptable for local extension, but multi-user/multi-tenant deployments need the tenant registry wired into the sidecar (C5 module exists, unwired).
- **SEC-07 hardening verified:** 16 corpus-found shapes closed; over-redaction bias documented.
- **Secrets in logs/exports:** export pre-scan blocks on detection (M16); collector export retains redaction labels.

---

## 12. Testing Gaps

- No live-agent E2E (demo path B) — external-blocked.
- No multi-platform rehearsal evidence (T31) and no 7-day soak (T32) — harnesses exist; runs are environment/time-blocked.
- No RPC-level tests for unwired modules (they're unreachable — GAP-001 subsumes).
- Simulation-core scenario parity tests absent (GAP-002/005).
- Golden-corpus CI job absent (GAP-003).
- Vitest coverage of several VIGUIX screens partial (per GUI register; not re-verified).

---

## 13. Architecture Gaps

- **ARCH-GAP-01 (P1):** two-lane architecture — a product lane (server/workbench) and a module lane (core libraries) — with no integration bus between them. The wiring seam is the missing layer, not any single module.
- **ARCH-GAP-02 (P2):** sidecar handler table is one 78-entry dict in a 5.4k-line `server.py`; new surfaces will continue to concentrate there. A handler registry per module is warranted.
- **ARCH-GAP-03 (P3):** `LangGraphLoopRunner` holds per-run node/schema maps as instance state (one-run-at-a-time documented); a runner pool is needed for concurrent stories (M21) once wired.
- **ARCH-GAP-04 (P3):** runtime owns one exit-check map keyed by `id(definition)`; definitions are shared constants — register by loop key instead.

---

## 14. Integration Gaps

The story of this build: **integration is the phase that has not started.** Every vertical slice (ledger, governance, engine, router, loops, tools, memory, adapters, portability, trainer, tenancy) is test-proven in isolation; the horizontal seam (RPC registration → host service → GUI surface) is missing for all of them. MVP/F0/F1/GUI lanes are wired; F3+ lanes are not.

---

## 15. Non-Functional Requirement Gaps

- NFR-38 storage growth/restore: measured core-side (test_ledger_archive prints figures) — published numbers belong to release evidence.
- NFR-42/43: resilience rehearsal + soak harnesses exist; evidence runs not recorded for all platforms.
- Performance budgets: `test:budgets` exists per register; not re-run in this audit.
- Accessibility: assistive-journeys tests exist (`webview/src/screens/assistive-journeys.test.tsx`); screen-reader validation per VIGUIX beyond tests not audited (not executable here).

---

## 16. Documentation vs Code Mismatches

- BUILD_STATE header "ALL PHASES ENGINEERING-COMPLETE" is accurate for **core modules**, but overstates the *product* claim — the unreachability finding (GAP-001) is recorded in the F3 exit register as host-integration, so the register is honest; the headline could mislead a skimmer.
- mvp-impl-plan's MV3/MV5 claims are consistent with code found (pinning, identity, evidence gate classes present).
- status.md was not fully re-validated item-by-item (see §17).

---

## 17. Existing Gap-Document Validation

- **gaps-requirements.md / gaps_implementation.md:** the F0→F1→F2→F3→F4+ resequencing matches reality (G-0); the FR-M46-16 engine growth gate, D14 security-phase amendment, D35 F2 human gate, D37 SCM refusal, D43 policy scaffold — all corroborated in code/DECISIONS. **Fully resolved** as documents; their build phases map as reported.
- **gaps_initiation.md (M40):** run initiation (preflight/cancel ledger record) present host-side per MV2; verified by test names. **Resolved (host), pending core verification** for RPC claim shape.
- **gaps_guix.md / gaps_guix_implementation.md:** workbench/studio inventory exists; full VIGUIX coverage unverified in this audit. **Partially resolved / unable to verify fully.**
- **futures-*:** N0/N1/N2 tasks land as recorded (BUILD_STATE exit assessments corroborated by test suites); N3=F2 human-gated correctly dispositioned. **Fully resolved for N0–N2.**

---

## 18. MVP Completion Analysis

Against mvp-req-final.md's frozen 0.1.x register: the MVP modules (sidecar contract, ledger, observers, governance, run initiation, gates, evidence surfaces, demo package) are implemented and test-covered per the MVP suite evidence recorded in mvp-impl-plan.md; this audit verified the code presence of the key seams (ledger schema, sidecar registry, workbench screens, evidence-gate classes) but did not re-run the packaged VSIX install/activate flow or the demo script. MV5 (the human evidence study) is outstanding by definition (D35). **No post-MVP items were counted toward MVP completion.**

---

## 19. Post-MVP / Future Analysis

- post-mvp-plan.md CP1–CP4: CP1 interop notarisation/conflicts/export present (interop.py + suites); CP2 attested identity = futures N2-B done; CP3 adapter pinning/identity done (MV3 + host); CP4 spans Orchestra-era items, partially covered by F3 modules.
- futures-implementation N-track: N0–N2 done (assessed); N3 human; N4 open.
- JIT M47: intentional backlog, gated on D44/J2 — **not a defect.**
- No accidental future contamination found in the code (no J3/J4 synthesis seams; harness selection absent as required until D44 closes).

---

## 20. Hidden / Newly Discovered Gaps

1. **NEW-GAP-A (P1):** Orchestra unreachability is the project's structural risk — an entire phase of work is invisible to the product (detailed in GAP-001).
2. **NEW-GAP-B (P2):** `contract_versions` stamping reaches interop notarisation only; other derived-entry paths (observer ingest) don't record contract version (FR-M44-06 partial).
3. **NEW-GAP-C (P2):** server.py's handler concentration (ARCH-GAP-02) is a maintainability trap that will worsen with every new surface.
4. **NEW-GAP-D (P3):** LangGraph runner single-run state (ARCH-GAP-03).
5. **NEW-GAP-E (P3):** collector's headless seed (`MERIDIAN_LEDGER_SIGNING_SEED`/seed file) and the extension host's provisioned seed are two paths to the same ledger keyspace; no documented precedence between them (a workspace could end with two signers for one chain).

---

## 21. Gap Dependency Graph

```
GAP-001 (RPC wiring) ─→ GAP-002 (scenario parity) ─→ GAP-005 (scenario data)
GAP-001 ─→ PART-002/003/004/005/006 (each becomes reachable via its RPC)
GAP-003 (golden CI) ─→ GAP-005
SEC-GAP-01 (INSERT trigger) ── independent
GAP-004 (live demo) ── external (runtime+credentials)
NEW-GAP-E (seed precedence) ── precedes collector/production co-use
```

---

## 22. Prioritized Gap Register

| Gap | Requirement | Type | Severity | Depends | Effort | Risk | Order |
|---|---|---|---|---|---|---|---|
| GAP-001 | FR-M4/M8/… C6 | integration | P1 | — | L | H | 1 |
| GAP-005 | FR-M32-04 | content | P2 | GAP-001 | M | M | 2 |
| GAP-002 | AC-28 | integration | P1 | GAP-001 | M | M | 3 |
| GAP-003 | AC-16 | CI | P2 | GAP-005 | S | L | 4 |
| NEW-GAP-E | seeds | config | P3 | — | S | M | 5 |
| SEC-GAP-01 | FR-M10-01 | security | P2 | — | S | M | 6 |
| PART-002/003/004/005/006 | various | partial | P2 | GAP-001 | S-M each | M | 7-11 |
| GAP-006 | v1.x modules | missing | P2 | GAP-001 | L | M | 12 |
| GAP-004 | AC-01..04 | external | P1 | D-creds | M | H | gated |

---

## 23. Definition of Done for Gap Closure

A gap moves to COMPLETE only when: (1) the behaviour is reachable through the product's real entry point (not a library call); (2) an integration test exercises the real path end to end; (3) the requirement's acceptance evidence is recorded with test name and commit; (4) any ledger/security invariant it touches is re-proven; (5) the register row cites all four. A gap with a named external owner stays BLOCKED-with-owner until that owner's evidence exists.

---

## 24. Goal-Based Production-Readiness & Marketability Audit (added per owner goal: "production ready, fully functional, thoroughly tested, marketable to other companies")

This section re-grades every finding against the commercial goal, not the build order. Severity changes are explicit; deferred-by-decision items the goal promotes to blockers are marked accordingly.

### 24.1 What the goal demands that the build-order audit did not

1. **Fully functional** — every built layer reachable and working in the shipped product.
2. **Production ready** — installable, upgradable, recoverable, secure by default, documented for operators.
3. **Thoroughly tested** — unit + integration + E2E + multi-platform + soak + failure paths, with evidence a customer's platform team can audit.
4. **Marketable** — a license customers can accept, truthful claims, support and deployment documentation, a demo that works on a clean machine, and disclosed limitations.

### 24.2 Re-graded findings under the goal

| Prior ID | Prior severity | Goal severity | Reason |
|---|---|---|---|
| GAP-001 (Orchestra unwired) | P1 | **P0** | "Fully functional" fails: a whole layer invisible to the product. |
| GAP-004 (live-agent E2E, demo B) | P1 | **P0 (external)** | No marketable product demo exists; §10.2 quality bar unmeasured. |
| F2 evidence gate / MV5 | human-gated | **P0 (external)** | The goal's "marketed" claim cannot outrun the preregistered evidence study; shipping marketing claims without it risks the claims doc's honesty guarantees. |
| D19 residue (`private: true`, no manifest license field) | deferred | **P1** | LICENSE (MIT) now exists at repo root (verified 18 Sep); manifest does not declare it and `private: true` blocks any distribution channel. The goal overrides the deferral. |
| GAP-002 (AC-28 parity) | P1 | P1 | unchanged |
| SEC-GAP-01 (raw INSERT) | P2 | **P1** | External customers raise the adversary model; write-time refusal is expected of a marketed evidence product. |
| GAP-003 (golden CI) | P2 | P2 | unchanged |
| T31/T32 (rehearsal, soak) | blocked | **P1 (external)** | Customers will ask for the resilience evidence the matrix already advertises. |
| D37 (SCM enforcement) | blocked | P1 (external) | unchanged |
| SEC-GAP-04 (tenant-scoped sidecar) | P3 | **P2** | IT-services marketing makes multi-tenant posture a sales question. |
| NEW-GAP-E (seed precedence) | P3 | P2 | Two-signer ambiguity is a support incident waiting for a paying customer. |

### 24.3 Newly identified marketability gaps (this pass)

**MKT-001 (P1) — Manifest/license mismatch.** `LICENSE` (MIT, 2026 Meridian Loom contributors) exists; `package.json` and `extension/package.json` carry no `license` field and `private: true`. A customer reading the manifest cannot discover the license; `vsce package` works but any registry/channel refuses or mislabels. Evidence: `grep license package.json extension/package.json` → empty. **Confidence: HIGH.**

**MKT-002 (P1) — Open-core split undecided.** The goal names "open core with paid features" (standing direction, D19). No module boundary marks core vs paid; no entitlement seam exists (correctly — none was authorized). Marketing to companies requires the split statement before pricing conversations. **Confidence: HIGH.**

**MKT-003 (P2) — No upgrade path for external users.** Versioning exists internally (0.1.0); no migration/upgrade story ships for a customer's `.meridian/` state across versions (ledger migrations exist via `apply_migrations` — good — but no documented upgrade procedure in DEPLOYMENT for state + policies + adapters). **Confidence: MEDIUM.**

**MKT-004 (P2) — Third-party attributions incomplete for redistribution.** OFL-1.1 fonts (Archivo, JetBrains Mono) ship in the VSIX; attribution obligations per OFL §2 must ship with the font files. Verify inside the built VSIX; add `extension/NOTICE` or equivalent. **Confidence: MEDIUM** (file presence not inspected inside the artifact this pass).

**MKT-005 (P2) — Telemetry/privacy posture for customer deployments.** `docs/SECURITY-AND-DATA.md` covers data handling; a marketed product needs an explicit "what leaves the machine" statement (default: nothing — verify no telemetry exists; if any exists, disclose). **Confidence: MEDIUM.**

**MKT-006 (P3) — Support surface unpriced.** `docs/SUPPORT.md` exists (90 lines); no SLA/support-tier content — fine pre-launch, listed for completeness.

### 24.4 What already satisfies the goal (verified this pass)

- LICENSE (MIT) present; checksum + AI-BOM (`meridian-loom-0.1.0.cdx.json`) ship beside the VSIX — supply-chain posture better than most pre-launch products. **HIGH.**
- `docs/claims.md` (164 lines) + `docs/SUPPORT.md` + `docs/DEPLOYMENT.md` (186 lines) exist and the claims doc is designed for honesty checking. **HIGH.**
- D41: compatibility matrix travels with the artifact. **HIGH.**
- Adversarial corpus (103 fixtures) + privacy lifecycle + consent-forgery fix — strong security story. **HIGH.**

### 24.5 Marketability verdict

**Not marketable today, for three independent reasons:** (1) the built Orchestra layer is unreachable (P0); (2) no live, truthful demo + evidence study (P0 external); (3) the license/manifest/open-core residue blocks any lawful distribution channel (P1). None requires new architecture — all are wiring, evidence, and packaging work already planned in `audit-1-k-g-impl.md` plus the marketability tasks added there.

---

## 25. Goal Re-Audit — "production ready, fully functional, thoroughly tested" (post-execution, 18 September 2026)

This section supersedes §24's verdict. It reflects the code as it exists NOW (after the execution rounds recorded in audit-1-k-g-impl.md §4), verified against artifacts, not registers.

### 25.1 What is now PROVEN (with evidence)

- **The Orchestra layer is reachable** (TASK-011): 31 surfaces dispatch through the real `SidecarServer` handler table; 12 integration tests drive the real JSON-RPC path; tier gating verified (orchestra surfaces refuse without the tier; simulation/golden are zero-tier per FR-M32). Evidence: `core/tests/test_orchestra_rpc.py` (12 passed), commit 9060686.
- **Contract integrity**: 115 methods, all in the sidecar registry, drift check green, both generated consumers in lockstep. Simulation canned data aligned to production wire shapes (the AC-28 harness caught and fixed `rows`→`entries` drift). Evidence: `scripts/check_scenario_parity.py` 20/20 (6e24b86).
- **Golden corpus runs in CI**: `golden/EDB-12345/` replays byte-identical; `npm run check:golden` in verify.yml (bfd00d0).
- **Security hardening landed**: write-time gapless-insert refusal (1d3712e), signer-marker precedence (9447882), egress refusal at the tool gate (b578c2e), 103-fixture adversarial corpus, 16 redaction shapes.
- **Distribution residue clearing**: MIT in the manifest, private flag dropped (7549d43); notices verified; no-telemetry guard green (7a95532); upgrade + tenant docs with tests.

### 25.2 Goal verdict

**Still not production-ready.** Four independent blockers remain, three of which are engineering tasks and one of which is a missing requirement:

1. **GAP-101 (P0): the shipped artifact is stale — the P0 fix is not in the package.** Verified 18 Sep: `dist/meridian-loom-0.1.0.vsix` (built 06:27) contains the new modules but NOT `orchestra_handlers.py` (no match in the archive), and its `bus_types.py` predates the 115-method contract (file dated 17 Sep 16:54). An evaluator installing the VSIX gets the pre-wiring product. **Fix: rebuild (`npm run package`), re-validate (`validate-package`), refresh checksum + AI-BOM.**
2. **GAP-102 (P1): zero host/GUI consumers of the 31 RPCs.** Verified: the only match for any new method name in `extension/src`/`webview/src` is a docstring sentence in `steer.ts`. The workbench cannot start a loop, route a call, query memory, run the trainer, or open a portability dialog. "Fully functional" fails at the UI boundary even though the bus is live.
3. **GAP-103 (P1): FR-M26-04 is unimplemented** — prompt caching, context compaction, and tool-result summarisation as configurable cost levers with reported savings are a MUST v1 requirement with no code (verified: zero matches in `core/`). Omitted requirement, not deferred by any decision.
4. **GAP-104 (P1, external): no live end-to-end run** — an installed ACP runtime with credentials has never driven a story through the product; the §10.2 quality bar and F2/MV5 remain human/customer-gated.

### 25.3 Tech-debt register (detailed)

Each item: what exists, what is incomplete and why, severity, fix pointer. "Intentional" items are documented design boundaries, not defects; they are listed so the fix work does not mistake them for gaps.

| ID | Item | State | Detail | Severity | Fix |
|---|---|---|---|---|---|
| TD-001 | Loop node bodies | Intentional stand-in | `orchestra_handlers._stand_in_nodes` runs deterministic progress markers; real reasoning requires the ACP runtime binding (roster manifests state this). The M4 machinery exercised is real. | P3 (until demo B) | runtime binding at launch |
| TD-002 | `portability/import` trust scope | Partial | Only packages signed by THIS workspace's ledger key import; cross-origin trust establishment (the FR-M16-04 general case) refuses honestly. | P2 | TASK-330 |
| TD-003 | `decisions/ablate` scope | Partial | Only engine-dispatchable decisions replay; narrative decisions refuse with the reason named. | P3 | TASK-331 |
| TD-004 | Simulation parity breadth | Partial | The parity harness probes read methods live; mutating steps are simulation-only by design (they must not mutate a probe workspace). | P3 | document; extend with disposable-workspace probing |
| TD-005 | Golden corpus size | Partial | One entry (EDB-12345). Admission path proven; corpus breadth is content work. | P3 | add stories as they complete |
| TD-006 | Orchestrator state is process-local | Real gap | `OrchestraState` holds run handles, story queue, tenants in memory. A sidecar restart loses the run registry (checkpoints survive; `loop.resume` needs the handle). Queue/tenants do not survive restart. | P2 | TASK-320 |
| TD-007 | Checkpointer connection lifetime | Minor | `_cp_conn` closes at process exit; `OrchestraState.shutdown` exists but is not called from the server's shutdown path. | P4 | TASK-321 |
| TD-008 | FR-M26-04 cost levers | **Omitted** | No prompt-cache/compaction/summarisation levers; no savings reporting. MUST v1. | P1 | TASK-310 |
| TD-009 | FR-M22-02 interface contracts | Partial | Multi-repo targets exist; Architect-generated OpenAPI/protobuf contract artefacts are not produced. MUST v1.x. | P2 | TASK-340 |
| TD-010 | FR-M26-05 model comparison harness | Missing | SHOULD v1.x; golden story × N model configs on yield/cost/latency. | P3 | post-MVP |
| TD-011 | FR-M13-06 contribution attribution | Missing | SHOULD v1.x; story-level agent contribution marked as estimate. | P3 | post-MVP |
| TD-012 | Full core suite in one run | Process debt | Targeted suites green (140+12+61+187+35…); the serial full suite (~1h+) was not re-run end-to-end in this pass. CI runs it. | P3 | CI evidence |
| TD-013 | `server.py` concentration | Improved, residual | Orchestra handlers live in their own module (good); server.py is still ~5.5k lines for the pre-existing surface. | P4 | incremental extraction |
| TD-014 | Host webview parity for new surfaces | Real gap (GAP-102) | No workbench UI calls the new RPCs. | P1 | TASK-300 series |
| TD-015 | Live-demo path | External | Runtime + credentials + bounded task never exercised. | P1 ext | demo B runbook |
| TD-016 | Rate limiting / multi-user sidecar | Documented assumption | Local single-user trust boundary; multi-user deployments need listener hardening. Disclosed. | P3 | deployment guide |
| TD-017 | VIGUIX sweep automation | Partial | assistive-journeys + banned-patterns tests exist; full §18 banned-pattern and screen-by-screen automated sweep incomplete. | P3 | GUI session |
| TD-018 | npm/webview full suites this pass | Not re-run | Host suites were green in earlier evidence; not re-executed in this audit pass. | P3 | CI |

### 25.4 Severity roll-up for the goal

- **P0:** 1 (GAP-101 stale artifact — half-day fix).
- **P1:** 3 engineering (GAP-102 host consumers, GAP-103/TD-008 M26-04, plus rebuild validation) + external gates unchanged (F2/MV5, D37, AC-50, soak, demo).
- **P2:** TD-002, TD-006, TD-009, SEC residuals from §11.
- **P3/P4:** the balance of the tech-debt register.

The path to "production ready, fully functional, thoroughly tested" is now: rebuild the artifact (hours) → host consumers (the largest remaining engineering block) → M26-04 levers → TD-002/006/009 → then the external evidence gates. Everything on that path has an implementation task in audit-1-k-g-impl.md §5.
