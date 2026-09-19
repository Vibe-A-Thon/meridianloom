# Meridian Loom — Goal Audit 1 (Claude): Gaps, Technical Debt and Readiness Requirements

| | |
|---|---|
| **Auditor** | Claude (development partner) |
| **Audit date** | 19 September 2026 |
| **Commit audited** | `a00e4cd` on `dev_local` (working tree clean at start) |
| **Goal audited against** | *"The application should be production ready, fully functional, with thorough and complete testing done — and ready to be marketed to other IT companies to use and automate their application/software development work."* |
| **Companion** | [`audit-1-cld-g-impl.md`](audit-1-cld-g-impl.md) — the implementation plan a coding agent executes to close every gap below |
| **Earlier audits reconciled** | `audit-1-gp-g-req.md` / `-impl.md` (GPT, 18–19 Sep), `audit-1-k-g-req.md` / `-impl.md` (Kimi, 18 Sep). Their findings are re-verified or explicitly carried forward in §6; nothing here assumes they are right. |

---

## 0. How to read this document

**Every finding has an ID (`CLD-<dimension><nn>`), a severity, a classification, evidence a reader can re-run, the impact on the goal, and the acceptance evidence that would close it.** The companion implementation plan maps each ID to one or more tasks.

### 0.1 Severity

| Severity | Meaning under this goal |
|---|---|
| **P0** | Blocks the goal outright. The product cannot honestly be called production ready, fully functional, thoroughly tested or marketable while this stands. Includes integrity or security failures in the product's central promise. |
| **P1** | Must close before the affected capability is sold or claimed as production ready. |
| **P2** | Significant completeness, quality, maintainability or commercial debt. Must be scheduled and either closed or explicitly scoped out in writing before launch. |
| **P3** | Improvement. Schedule after launch unless cheap. |

### 0.2 Classification

| Classification | Meaning |
|---|---|
| **CONFIRMED-RUN** | Reproduced by executing code or tests during this audit; command and result recorded. |
| **CONFIRMED-CODE** | Deterministic from reading the current source; file and line cited. No runtime needed to know it is true. |
| **EVIDENCE-GAP** | The evidence required to claim the property does not exist. This does not prove the property fails. |
| **DECISION** | Needs an owner or business decision; engineering cannot close it alone. |
| **EXTERNAL** | Needs people, customers, time or infrastructure outside the repository. |

### 0.3 What "the goal" means, measurably

A goal that is not decomposed cannot be audited. This audit holds the product to these definitions, and the implementation plan's release gates (`audit-1-cld-g-impl.md` §1) are built on them.

| Goal clause | Measurable definition used here |
|---|---|
| **Production ready** | A customer installs the published package on a supported, clean machine with no source checkout, provisions its runtime without manual dependency surgery, and it starts, operates, upgrades, backs up, recovers and uninstalls as documented — on every platform the matrix claims — with no known P0/P1 integrity, security or data-loss defect open. |
| **Fully functional** | Every capability the product *claims* (README, Marketplace listing, docs, UI) works end to end through the shipped entry point against real inputs, not stand-ins, simulations or registered-but-unwired endpoints. Anything not working is either removed from the claim or visibly labelled as unavailable. |
| **Thoroughly and completely tested** | One frozen commit passes the entire suite sequentially, repeatably, on every supported platform in CI; the suite contains negative controls for every security/integrity guard; coverage is measured; real-editor and packaged-artefact tests exist; performance, soak, resilience and accessibility evidence exists at the level the requirements set. |
| **Marketable to IT companies to automate their software development** | The product does what the marketing will say (automates or governs development work), under a licence and commercial model that lets the owner sell it, with the legal, security, procurement, support and evidence materials an enterprise buyer requires, and with no claim that outruns recorded evidence. |

---

## 1. Verdict

### 1.1 Against each goal clause

| Goal clause | Verdict | Deciding evidence |
|---|---|---|
| Production ready | **NOT MET** | Suite red on the audited commit (§3.1); P0 silent-truncation defects that make governance fail open (CLD-B01); customer must hand-provision 45 Python packages into an interpreter the extension finds (CLD-F01); platform evidence is Windows-only and soak is 3 minutes of 168 hours (CLD-E03) |
| Fully functional | **NOT MET** | The Orchestra — the layer that would automate development — executes deterministic **stand-in** nodes and returns `completed`; no production path makes an agent do SDLC work (CLD-A01, CLD-A02). Four specified modules have no implementation at all (CLD-A07) |
| Thoroughly tested | **NOT MET** | All three test layers fail: extension 25 failures (10 isolated, rotating), Python core ≥ 6 failures plus a hang that never completes, webview 4 timeouts (CLD-D01); CI's first job can fail before any test runs (CLD-D02); no coverage measurement, no linters or type checkers for Python, no ESLint, no real-editor tests (CLD-D04–D06); tests assert stand-in behaviour as success (CLD-D07) |
| Marketable to IT companies | **NOT MET** | The MIT licence lets anyone take and resell the product free, which contradicts selling it (CLD-K01); no entitlement mechanism (CLD-K02); no effectiveness evidence, so no productivity or automation claim may be made (CLD-K04); no EULA, privacy policy, DPA or procurement pack (CLD-K03, CLD-K07) |

### 1.2 What is genuinely strong — and is the real product today

This audit is not a verdict that the work is poor. A large amount is real, careful and differentiated, and the plan should protect it:

- **The Flight Recorder and Governor tiers are substantive.** They cover a hash-chained, Ed25519-signed ledger with Merkle proofs and a standalone standard-library verifier; three-state attribution with coverage envelopes; cross-vendor observers; ACP hosting with permission mediation; gates, roles, approvals, delegation and hygiene; privacy with crypto-shredding; and signed evidence bundles mapped to ISO/IEC 24970, SSDF, ISO 42001 and EU AI Act Articles 12/26.
- **The honesty discipline is unusual and valuable.** `docs/claims.md` binds claims to tests; `unknown` is a first-class state; confidence only ever clamps down; the release notes carry limitations verbatim.
- **The security posture has real depth.** It includes a 103-fixture adversarial corpus, 25+ redaction shapes, write-time refusal of forged ledger inserts, signer-marker precedence, a strict webview CSP with per-panel nonces, keychain-only credentials, and child-environment scrubbing.
- **Supply-chain artefacts beyond most pre-launch products** ship: a CycloneDX AI-BOM, checksums, notices, a support policy and a disclosure policy.

**The honest product today is a governance and provenance layer over agents the customer already runs** ("bring your own agents, keep the evidence" — `extension/README.md`), not an autonomous development workforce. That product is close to marketable once the P0/P1 items in dimensions B, C, D, F and K close. The autonomous-delivery product the goal describes is **not built**; its libraries exist, its execution does not (dimension A).

### 1.3 Top blockers, in the order they must be addressed

| # | ID | Blocker | Severity |
|---|---|---|---|
| 1 | CLD-K01 / K02 | Licence and commercial model contradict selling the product | P0 · DECISION |
| 2 | CLD-B01 | Governance and privacy logic silently reads only the oldest 1,000 ledger rows: halts and revocations **fail open**, erasures stop replaying | P0 |
| 3 | CLD-D01 / D02 | The suite is red on the audited commit and CI can fail before running any test | P0 |
| 4 | CLD-A01 / A02 | The Orchestra runs stand-ins; nothing automates development work | P0 (for the stated goal) |
| 5 | CLD-F01 | A customer must provision Python ≥3.11 plus 45 packages by hand into their own interpreter | P0 (for marketability) |
| 6 | CLD-C01 | The sidecar inherits the whole editor environment while depending on LangChain/LangSmith: a tracing variable set for other work **exports loop state to LangChain's cloud (reproduced, §3.4.2)** | P0 |
| 7 | CLD-B04 | Privileged Orchestra RPCs trust caller-asserted flags (`humanApproved`, `actorIsHuman`, `humanOverride`, scores) | P1 |
| 8 | CLD-K04 | No effectiveness evidence: the MV5 study has never run, so marketing may not claim productivity, quality or automation outcomes | P1 · EXTERNAL |
| 9 | CLD-E03 / F02 | Soak 0.05 of 168 hours; resilience and compatibility recorded on Windows only | P1 · EXTERNAL |
| 10 | CLD-H01 | Status documents claim "ALL PHASES ENGINEERING-COMPLETE", which the evidence does not support; every agent and reader who trusts them is misled | P1 |

---

## 2. What the product is today — capability map

Measured on `a00e4cd`. "Lines" are Python source lines per package, excluding tests.

| Layer | What exists | State against the goal |
|---|---|---|
| **Flight Recorder** (base tier) | `ledger/` 4,699 · `attribution/` 1,631 · `observers/` 2,859 · `metrics/` 6,056 · headless CLI · verifier | **Real and tested.** Production-grade core, subject to CLD-B01 and platform evidence |
| **Governor** | `governance/` 4,569 · ACP host in `extension/src/acp` · workbench `extension/src/workbench/service.ts` (2,728 lines) · gates, roles, approvals, spend ceilings, steering | **Real, with defects.** Editor-side enforcement only (D37); workbench runs one agent at a time in the open workspace with no worktree isolation (`docs/gui-implementation.md` L51–52) |
| **Orchestra** (would automate development) | `runtime/` 936 · `router/` 444 · `tools/` 782 · `memory/` 605 · `adapters/` 718 · `phases/` 112 · `decisions/` 211 · `comprehension/` 353 · `orchestra_handlers.py` 1,040 · roster of 14 adapter folders | **Library-level, not functional.** Loop bodies are stand-ins; roster `agent.py` files are stand-ins; the router authorises but never dispatches; nothing binds a real agent (CLD-A01) |
| **F4+ / C3–C6** | `trainer/` 376 · `portability/` 487 · `tenancy/` 219 · `differentiation/` 416 · `simulation/` 413 · `replay/` 186 | **Thin.** For scale: M14 Trainer specifies 31 FRs, implemented in 376 lines; M7 Memory 30 FRs in 605; M8 Router 27 FRs in 444. Several report success without doing the work (CLD-A04) |
| **Competitive-review modules** | M47 harness · M48 tool-call gateway · M49 attested identity · M51 longitudinal outcomes | **Absent.** Zero source files reference any of their FRs (CLD-A07) |
| **Interface** | 52 catalogued surfaces; React webview; 356 webview tests | **Mixed.** Core screens real; modelling and several governance surfaces are 20–62-line shells (CLD-G01) |
| **Contract** | 116 RPC methods; `methods.json` 9,970 lines; generated TS/Python types | Generated types are checked; runtime request/response validation is not general (CLD-B05) |

**Scale of the specification.** The requirement documents define several hundred functional requirements:

- **311** distinct `FR-*` identifiers in `Requirements_Final.md`, and **488** across all specification documents;
- **67** `AC-*`, **53** `NFR-*` and **47** `SEC-*`.

Across the frozen specification, the disposition labels in the tracked requirement documents occur as follows:

| Label | Occurrences |
|---|---|
| `BUILT` | 160 |
| Partly or mostly `BUILT` | 21 |
| `MVP-GAP` | 28 |
| `MVP-HUMAN` | 15 |
| `POST-MVP` | 120 |

These are label occurrences, not unique requirements. The frozen MVP set (`mvp-req-final.md` §5) has 40 requirement groups: **33 `BUILT`, 4 `MVP-GAP`, 3 `MVP-HUMAN`**. The four gaps are the support matrix (R1.6), resilience rehearsal (R1.7), soak (R6.4) and assistive journeys (R6.5); the three human groups are the evidence study (R5.2), first-value timing (R5.3) and two-editor proof (R5.4). **The MVP is therefore not complete by its own definition**, independent of anything post-MVP.

---

## 3. Evidence gathered in this audit

The audit did not rely on existing test results or on either earlier audit. Commands were run against `a00e4cd` on Windows 11, Python 3.11, Node 22.

### 3.1 Test execution

| Run | Result | Meaning |
|---|---|---|
| `npm test` (the project's own sequential runner, all phases) | **FAIL — exit 1.** Document gates passed. Extension phase: **25 failed / 600 passed / 1 skipped** across 56 files, with 8 failing files and 1 unhandled error. The runner then stopped; **the core and webview phases never ran** | The audited commit does not pass its own suite |
| Failing extension files re-run alone (`npx vitest run` on the 8 files, nothing else running) | **FAIL — 10 failed / 80 passed**, 5 files failing | Failures are not caused only by parallel load |
| Comparison of the two failing sets | **The failing set rotates.** C-INIT-2 failed alone but passed in the full run; C-CRASH-1 the reverse | The failures are timing-dependent — flaky, not deterministic logic errors |
| Error signatures (both runs) | Timeouts at 5 s, 15 s, 20 s and 30 s on tests that spawn the Python sidecar or a fake ACP agent; Windows `EBUSY` on temp-dir cleanup (15 occurrences); one `EPIPE`; one assertion `expected 'running' to be 'completed'` | Subprocess start-up is too slow for the tests' budgets, and cleanup races process exit |
| Python core suite (`pytest -m "not perf" -n auto`, run separately because the runner never reached it) | **DID NOT COMPLETE.** 1,964 test functions. **At least 6 failures (`F`)** by the 90% mark. At about 98% all 8 xdist workers stayed CPU-bound, with **no progress for over 60 minutes**. The run was stopped after about 4.5 hours. A diagnostic re-run with `faulthandler_timeout=600` is recorded in §3.4.6 | The Python suite cannot currently produce a pass/fail verdict: some tests hang or spin. There is no per-test timeout (`pytest-timeout` is not a dependency), so one hung test stalls the whole release gate indefinitely |
| Webview suite (`vitest run`, machine otherwise idle) | **FAIL — 4 failed / 361 passed** (39 files, 2 failing), 281 s. All 4 are `Test timed out in 5000ms`: `ledger-screen.test.tsx` ×2 (filters → `ledger/query`; consistency proof) and `screen-invariants.test.tsx` ×2 (X-27 vendor tag confidence; X-29 Crown watching → recording) | **All three test layers fail on the audited commit.** The webview failures are timing-sensitive jsdom renders with no subprocess involved, so the flakiness is not confined to subprocess tests |

### 3.2 Static and artefact checks

| Check | Result |
|---|---|
| `npm run check:surface`, `check:claims`, `check:mvp-traceability`, `check:release-notes`, `check:licences`, `check:compatibility`, `check:notices` (inside `npm test`) | Pass — but see CLD-D04 and CLD-H04 on what they do and do not prove |
| Packaged VSIX (`dist/meridian-loom-0.1.0.vsix`, 278 members) | Contains `orchestra_handlers.py` and 9 policy files under `extension/policy/`; **contains 0 roster adapter manifests** |
| Python dependency closure, computed from installed metadata | **45 distributions** from 8 declared, including `langchain-core`, `langsmith`, `langgraph-sdk`, `httpx`, `requests`, `pydantic`, native `orjson`, `zstandard`, `xxhash`, `sqlite-vec`, `cryptography`; licences include MPL-2.0 (`certifi`, `orjson`) |
| `THIRD-PARTY-NOTICES.md` | Lists 8 Python and 2 Node runtime components; states it covers "every third-party component that ships" |
| Code or test references to FR-M47 / M48 / M49 / M51 | **0 / 0 / 0 / 0** |
| `ledger.query` | `ORDER BY seq LIMIT min(max(limit,1),1000)` — oldest first, page clamped to 1,000 (`ledger/core.py` L518–519) |
| Unpaginated `limit=1000`-style reads in non-test core | **25 call sites**, including merge gate, revocations, privacy, roles, receipts, economics, router |
| Tracked Markdown | **159 files, 3.9 MB**; **11 byte-identical duplicate groups (23 redundant copies)** |
| CI workflow `verify.yml` | `contracts` job runs `check:golden` and `check:parity` (Python) at L122–125 with **no `setup-python` or `pip install` in that job**; every other job `needs: contracts` |
| Quality tooling | No `ruff`, `mypy`, `flake8`, `pylint`, `black` or coverage config for Python; no ESLint or Prettier config for TypeScript; no `@vscode/test-electron` / `@vscode/test-cli` |
| Localisation | No `package.nls*.json`, no `l10n/`, no `vscode.l10n` usage |
| Onboarding | `contributes.walkthroughs`: 0; 9 settings |

### 3.3 Behavioural probes

| Probe | Result |
|---|---|
| Merge gate halts after more than 1,000 gate entries (CLD-B01) | **Reproduced — halt invisible, fails open** (§3.4.1) |
| LangSmith tracing inherited by the sidecar (CLD-C01) | **Reproduced — `POST /runs/multipart` 4,066 bytes** (§3.4.2) |
| Sidecar cold-start time (CLD-E01) | Server import 36–95 s under contention (§3.4.3) |

### 3.4 Results completed after the first draft

*The numbers here supersede the "see §3.4" placeholders above. Probe scripts are reproduced in Appendix B.*

#### 3.4.1 Merge-gate halt after 1,000 gate rows — **REPRODUCED: fails open (CLD-B01)**

| Step | Result |
|---|---|
| Control: a `merge`-scope halt on `feature/x` in a fresh ledger | `active_halts` → `[(1, 'control')]` — **seen** |
| Append 1,000 non-halting `gate` rows (5.9 s), then a `merge`-scope halt on `feature/y` | `active_halts(ledger, "feature/y")` → **`[]` — the halt is invisible; `check_merge` would not block the merge** |

This used the module's own functions and the exact row shape `test_merge_gate.py::append_halt` writes. **An enterprise repository reaches 1,000 gate evaluations within weeks of normal use.**

#### 3.4.2 LangSmith tracing inherited from the environment — **REPRODUCED: loop state leaves the machine (CLD-C01)**

With `LANGSMITH_TRACING=true`, `LANGSMITH_ENDPOINT=http://127.0.0.1:<port>` and a dummy API key set in the environment (as a developer who uses LangSmith for other work would have):

- A LangGraph `StateGraph` of the kind `runtime/runner.py` builds, using the installed `langgraph` and `langsmith 0.6.9` from the product's own dependency closure, produced **4 requests** to the endpoint: `GET /info` ×3 and **`POST /runs/multipart` carrying 4,066 bytes**, the run inputs and outputs, i.e. the loop state.
- The sidecar inherits the editor's environment unfiltered (`stdio-client.ts` L125). Nothing in the product disables tracing.

With a real endpoint, loop state (story ids, file paths, prompts once real nodes exist) would be sent to LangChain's cloud service under the developer's personal account. This directly contradicts "nothing leaves the machine". The product-path confirmation through `SidecarServer` → `loop.start` is recorded in §3.4.4.

#### 3.4.3 Sidecar import cost — **CONFIRMED: import-heavy start-up (CLD-E01)**

| Measurement | Result |
|---|---|
| `import meridian_core.server` (two runs while the core suite was using all cores — **contended**, not an idle cold start) | **36.1 s** and **94.8 s** |
| `-X importtime` top cumulative | `meridian_core.governance` (37 s under contention, of which `governance.bypass` 30 s), `metrics.evidence_gate → evidence_study → jsonschema` (27.6 s), `ledger.core → cryptography` (17.7 s) |

These numbers are inflated by contention and must be re-measured on an idle machine (WP-00.4). They demonstrate the structural problem: **the sidecar imports every subsystem (governance, metrics, jsonschema and cryptography) before it can answer `initialize`**. That is why real-subprocess tests with 5–30 s budgets time out whenever the machine is busy, and why the product ships a 30 s handshake default with advice to raise it.

#### 3.4.4 Product path: `SidecarServer` → `loop.start` with tracing variables set — **REPRODUCED (CLD-C01, CLD-A01)**

Setup: a real `SidecarServer` with all three tiers, handshaken against a git workspace, then `loop.start {loopId: "L-probe", storyId: "S-payroll", kind: "L2-task"}`.

- **Result:** `{'runId': '79b10c08fa50', 'status': 'completed', 'iterations': 1, 'checkpointed': True}`. **The product reports a completed L2 task loop although no agent ran and no file changed** (CLD-A01).
- **Egress:** 4 requests to the fake LangSmith endpoint: `GET /info` and **three `POST /runs/multipart` totalling 10,933 bytes** (1,814 + 2,295 + 6,824).
- A plain-substring search of the request bodies found neither the loop id nor the file name. The multipart bodies may be compressed or encoded, so this does **not** show that identifiers were absent. It shows only that run records for the product's loop were uploaded.

**Conclusion:** the product's own RPC path uploads Orchestra run traces to whatever LangSmith endpoint the user's environment names.

#### 3.4.5 Revocation after 1,000 revocations — **REPRODUCED: fails open (CLD-B01, CLD-C02)**

1,000 revocations of `user0…user999@example.com`, then a revocation of `mallory@example.com` (the 1,001st):

| Query | Result |
|---|---|
| `revocations.revoked_at(ledger, "mallory@example.com")` | **`None` — the revocation is invisible, so Mallory can still approve and still authorise merges** |
| `revoked_at(ledger, "user0@example.com")` (control) | `True` |

The erasure-replay path (`privacy.erasures()`) uses the identical read pattern and was not separately reproduced. It is CONFIRMED-CODE only.

#### 3.4.6 Why the Python suite "hangs" — diagnostic re-run (CLD-D01, CLD-D09, CLD-E01)

Re-run: `pytest -m "not perf" -n auto -v -rfE -o faulthandler_timeout=600`, on a machine otherwise idle. Faulthandler dumped the stacks of tests still running after 10 minutes:

| Stack (worker still running after 10 min) | Meaning |
|---|---|
| `test_event_ingestion.py::test_clean_full_100k_fixture_reconciles_exactly` → `ingest.ingest_batch` → `ledger/core._insert_rows` → `merkle.append` → `merkle.node_hash` | A **100,000-event scale test runs in the default (non-`perf`) tier** and spends over 10 min in per-row Merkle hashing. It is a test-tiering defect and also a **throughput signal**: ingesting 100k events costs more than 10 minutes of CPU on a workstation. NFR ingest budgets need re-measuring against it (WP-14) |
| `test_full_history_metrics.py::test_equals_full_scan_recomputation` → `metrics/trust.compute_rejection_rate` → `_add` | A full-history recomputation equality test, also scale-sized and in the default tier |
| `observers/sessions._run` → `tick` → `observers/claude.observe` / `observers/codex.observe` → `_scan_trailers` → `gitcmd.run_git_command` — **in the thread dump of unrelated tests** (`test_initiation_rpc.py::TestLaunchAuthority…`) | **Leaked background observer threads.** Session-observer loops started by earlier tests keep running `git` subprocesses inside later tests on the same worker. That is test-isolation debt, and on the product side it means observer threads are not reliably stopped when their owner is torn down. **Verify shutdown in the product (WP-06)** |

Failures named so far in the re-run (a subset; see the note after this table):

| Test | Likely cause |
|---|---|
| `test_bus_types.py::test_placeholder_methods_answer_not_implemented` | **Verified.** The test (L60–70) still asserts that `loop.start`, `loop.stop` and `loop.status` answer `NOT_IMPLEMENTED`, but they were implemented (`9060686`, `a00e4cd`). A stale test left red by the commits that implemented loop.*, which shows **those commits were made without running the suite**. The extension's `bus-types.test.ts` failure (§3.1) is the same drift on the TypeScript side, as is the stale DiagramStudio notice (CLD-G01) |
| `test_engine_capabilities_structural.py::TestSymbolResolution::test_references_via_real_subprocess` | Real language-server subprocess |
| `…::test_workspace_symbols_via_real_subprocess` | Real language-server subprocess |
| `…::TestDispatchEndToEnd::test_dispatch_resolve_symbol_executes_via_configured_server` | Real language-server subprocess |

#### 3.4.7 Where the re-run stopped

| Measure | Value |
|---|---|
| Elapsed time (idle machine, `-n auto`, 8 workers) | about 90 minutes |
| Progress | **45%** |
| Passed | 1,012 |
| Failed | 4 (the tests named above) |
| Faulthandler stack dumps | 2 |

The re-run was stopped at that point, because it had already produced its diagnostic evidence and a full completion would have taken several more hours.

**No complete Python-suite verdict exists for `a00e4cd`.** Producing one on a developer workstation takes longer than a working session, which is itself the CLD-D09 finding. The first job of WP-00 is to make the suite complete, with a verdict, in under 30 minutes.

---

## 4. Findings

### Dimension A — Product function and goal fit

#### CLD-A01 — The Orchestra executes stand-ins; nothing automates development work
**P0 · CONFIRMED-CODE · FR-M4-01…11, FR-P1…P7, AC-01…AC-04, vision §§2–5, the stated goal.** Related: GP-007, Kimi TD-001.

- `core/meridian_core/orchestra_handlers.py` L99–111 builds `_stand_in_nodes(definition)`: each node appends its own name to a `progress` list and returns.
- `loop_start` (L397–419) runs those nodes and returns `status: completed`.
- On resume after a restart, `_ensure_runner_context` (L463–481) rebinds the **same stand-ins**, so a "restored" run finishes by marking names visited.
- The 14 roster adapters' `agent.py` bodies are stand-ins by design: they read a JSON args file and print a JSON result with zero model calls (`adapters/roster.py` docstring L1–20; template L45–60).
- `Router.request_model_call` (`router/routing.py` L117–250) authorises or refuses a call and records it. It never dispatches one.
- No module in `core/` imports a model or agent client. The only outbound network code is the opt-in export collector sink (`collector.py` L344) and witness receipts (`ledger/receipts.py`).

**Impact.** A buyer told the product "automates application/software development" would install something that cannot produce a single line of code or a test through its Orchestra. The autonomous-delivery value proposition is unbuilt.

**Acceptance.** A real, bounded repository task (for example "add input validation and a test to this function") entered through the product runs through the loop runtime. It dispatches to a real ACP agent through the governed host, produces a diff and passing tests in an isolated worktree, passes the gates, and yields a signed evidence bundle. A failing test, rejected gate, budget breach or unbound runtime prevents `completed`. The stand-in path stays available only as an explicitly labelled simulation mode.

#### CLD-A02 — Two unconnected execution systems
**P0 (for the goal) · CONFIRMED-CODE · FR-M18, FR-M40, FR-P4-07, GP-011.**

- **Real agent execution exists only in the extension host.** The workbench (`extension/src/workbench/service.ts`) and run initiation (`extension/src/adapters/launch.ts`) spawn ACP agents. The workbench runs one agent at a time, sequentially, in the open workspace — "This does not yet implement M40 worktree isolation, parallel orchestration, transactional merge" (`docs/gui-implementation.md` L51–52; also L150, L166).
- **The Orchestra runtime lives in the Python sidecar** and has no path to those agents.
- The two have different isolation, different registries (22 Markdown profiles in the host; 14 adapter folders in Python — GP-013) and different state.

**Impact.** Even with CLD-A01 fixed inside Python, there is no governed, isolated way for the Orchestra to use the agents the customer already has. That is the product's own stated architecture ("bring your own agents").

**Acceptance.** One execution service owns the job. The Orchestra requests work; the host binds an admitted, identity-checked ACP agent inside a per-run worktree, streams and records its output, and returns a result the loop can gate. Workbench dispatch and palette launch use the same service.

#### CLD-A03 — Router ratio counts authorisations as executions
**P1 · CONFIRMED-CODE · FR-M8-17, FR-M17-10.** Related: GP-021.

- `router/routing.py` records a `model_call` row when a call is authorised (L224–250).
- `dependency ratio` counts those rows (L338–345). That read is additionally clamped to 1,000 rows (see CLD-B01).

Once real dispatch exists, "LLM dependency ratio", a KPI the product sells on, would count permissions rather than calls.

**Acceptance.** Distinct `authorised`, `dispatched` and `completed` states. The ratio uses only dispatched and completed calls over the full history, paginated.

#### CLD-A04 — Learning and adapter-lifecycle endpoints report success without doing the work
**P1 · CONFIRMED-CODE · FR-M14, FR-M15-03/04, FR-M5, FR-M31.** Related: GP-013, GP-016.

- `trainer_train` returns `{"ran": True}` after harvesting signals and discarding them (`orchestra_handlers.py` L846–860).
- `trainer_promote` trusts caller-supplied `incumbentScore`, `candidateScore` and `humanApproved` (L866–884).
- Adapter `promote` changes state without a scorecard.
- `unplug` returns `retired: True` without stopping a running session (L679).

**Acceptance.** Learning jobs are real: signals are collected, candidates generated, evaluation runs on pinned tasks, and results are persisted. Promotion needs evaluated evidence and an authenticated human decision. Unplug stops the live session. Every one of these is covered by a test that fails when the work is skipped.

#### CLD-A05 — Positioning drifts from what exists
**P1 · CONFIRMED-CODE.**

- The root `README.md` L3 says the product "runs a governed, **self-improving** organisation of AI agents against a real codebase", which is not true today (CLD-A01, CLD-A04).
- The root README is a developer and specification index, not a customer page.
- `extension/README.md` is honest and well positioned ("Bring your own agents. Keep the evidence.").

Marketing written from the root README, the vision or the requirement documents would overclaim.

**Acceptance.** One customer-facing README and listing, every sentence of which is bound in `docs/claims.md` to a test that passes on the release commit. Aspirational content lives in a clearly labelled roadmap.

#### CLD-A06 — The installed product has no Orchestra roster
**P1 · CONFIRMED-RUN (artefact inspection) · FR-M31-02/11, D4, MP7.** Related: GP-031.

- The VSIX contains **0** `adapters/*/adapter.yaml` manifests.
- `OrchestraState.adapter_roots()` resolves `Path(__file__).parents[2]/adapters`, which in the package is `extension/sidecar/adapters`: absent.
- Policy ships under `extension/policy/`, which the Python fallback does not look for.

**Acceptance.** One runtime resource resolver for source and packaged layouts. `validate-package` extracts the VSIX into a clean directory and proves the roster and policies load by behaviour, not by filename.

#### CLD-A07 — Four specified modules are entirely absent
**P2 · CONFIRMED-CODE · M47, M48, M49, M51 (`mvp-req-final.md` §14, §17).**

- A search of `core/` and `core/tests/` for `FR-M47-`, `FR-M48-`, `FR-M49-` and `FR-M51-` returns **zero files**.
- M50 (1 file) and M52 (4 files) are partial.

These are the competitive-review answers to CMP-01…CMP-05: harness provenance, tool-call governance, attested workload identity, and 30/60/90-day outcomes bound to the gate decision.

**Impact.** Against agent gateways and attested-identity vendors, the product has no answer at the call boundary and no identity stronger than a git config name (D38).

**Acceptance.** Per `post-mvp-plan.md` CP2–CP4 and `jit-impl.md` J1–J2, each with integration tests at its real control boundary. M48's gateway half waits on decision D48.

---

### Dimension B — Functional correctness and data integrity

#### CLD-B01 — Governance and privacy silently read only the oldest 1,000 ledger rows
**P0 · CONFIRMED-RUN (§3.4.1) · FR-M41-07 / G-01 defect class, FR-M12, FR-M20, FR-M42-06, SEC-31, FR-M43-06…08, GDPR Art. 17.**

`Ledger.query` returns rows **oldest first** and clamps every page to 1,000 (`ledger/core.py` L518–519). Callers that read once without paginating see only the first 1,000 matching entries in the chain's life. Even `limit=100000` is silently clamped. The same defect class was fixed for metrics under FR-M41-07 (`scan_scope`), but never for these callers:

| Call site | Consequence once more than 1,000 matching entries exist |
|---|---|
| `governance/merge_gate.py` L99–106 `_iter_gate_rows` / `_iter_approval_rows` (comment says "newest first"; it reverses the **oldest** 1,000) | (Reproduced, §3.4.1.) A **halt** recorded later is invisible: `active_halts` misses it and **the merge is not blocked (fails open)**. New approvals are invisible, so merges are wrongly refused |
| `governance/revocations.py` L111 `active_revocations` | Revocations after the 1,000th are ignored: **a revoked identity can still approve (fails open) — reproduced, §3.4.5** |
| `ledger/privacy.py` L408 `erasures`, L253 consents, L445 `coverage_gaps` | Erasures after the 1,000th are not replayed into a restored backup, so **erased subjects become readable again after restore**; later consent records are invisible; coverage gaps are wrong |
| `governance/roles.py` L439, L550, L557, L568 | Delegations, approval hygiene, ingest and gate evidence are incomplete |
| `ledger/receipts.py` L468 · `server.py` L1078, L2600, L2766, L2890 · `metrics/economics.py` L322, L359 · `router/routing.py` L338 · `engine/reporting.py` L168 | Trusted signers, notarisation dedupe, rejection capture, PR ingest, economics and dependency ratio all computed over a truncated population with no coverage envelope |

**Impact.** The product's central promise — a governance and evidence layer that cannot be walked around — fails silently at exactly the scale an enterprise customer reaches in weeks.

**Acceptance.**
- Every non-test caller uses full-history cursor iteration, or an indexed query that is exact by construction (for example, newest-by-subject).
- A guard test fails the build if any `ledger.query(` in non-test code is read without pagination.
- Reproduction tests with more than 1,000 rows prove: a later halt blocks the merge; a later revocation refuses the approval; a later erasure replays into a restored copy.
- Performance budgets are re-measured over a 50k ledger.

#### CLD-B02 — Loop control lies about unknown runs and cannot cancel
**P1 · CONFIRMED-CODE · FR-M4-06/08, FR-M3-02.** Related: GP-008.

- `loop_stop` (`orchestra_handlers.py` L422–444) appends a `loop_stopped` ledger entry and returns `stopped: True` **even when the loop id does not exist** (`was: "unknown"`). It writes a false record into the ledger.
- `loop_resume` / `loop_replay` index `orch._handles[...]` directly (L487, L497), so an unknown id raises a bare `KeyError`: internal error `-32603` instead of a named refusal.
- The server dispatches synchronously. `$/cancel` is ignored, so a long node would block `stop` itself (GP-008).
- `health` reports zero active loops.

**Acceptance.**
- An unknown id is refused with a named error and nothing is written.
- `stop` cancels a genuinely running node, including a child process tree.
- A second `stop` is idempotent.
- Interleaved runs do not share context.
- `health` reports the real count.

#### CLD-B03 — Restart and queue durability are cosmetic for real work
**P1 · CONFIRMED-CODE / carried forward · FR-M4-05, FR-M21, NFR-42.** Related: GP-009, GP-010.

- The GP-009 fix (`a00e4cd`) restores thread-local context by re-binding stand-in nodes. It makes the stand-ins resumable, but persists no executable continuation for real work: no binding descriptor, gate position, usage or cursor.
- Queue durability (`_waiting` only; admitted and done work omitted) was not re-verified in this audit and is carried forward from GP-010.

**Acceptance.** Kill the sidecar mid-run of a real (CLD-A01) task, reopen, and approve or resume at the exact continuation with no duplicate side effects. Every acknowledged queue transition survives a crash.

#### CLD-B04 — Privileged Orchestra RPCs trust caller assertions
**P1 · CONFIRMED-CODE · FR-M12-07, FR-M20, FR-M7-11, FR-M14-06.** Related: GP-005.

`orchestra_handlers.py` accepts authority as request data:

| Line | Caller-supplied value trusted as authority |
|---|---|
| L517 | `humanOverride`, a router bypass |
| L616 | `actorIsHuman`, which pins procedural memory |
| L761–765 | `approvals`, `testsPassed`, `scansPassed` for the gate |
| L799–805 | `humanApproved` for portability trust |
| L866–884 | `humanApproved` and numeric scores for trainer promotion |

**Acceptance.** Authority derives from the host-authenticated identity and role policy. Approvals are bound to action, subject, digest, expiry and principal. A test sends every forged flag and asserts no state change.

#### CLD-B05 — No general runtime validation of RPC requests and responses
**P1 · CONFIRMED-CODE · FR-M3, FR-M32-09.** Related: GP-006.

- `a00e4cd` fixed the declared shapes for `loop.start`, `loop.stop` and `loop.resume`: `LoopStartResult` now matches the code.
- The server still does not validate general requests or results against `methods.json`. Malformed booleans, paths, NaN or negative budgets reach handlers.

**Acceptance.** Boundary validation for all 116 methods, with a wire test per method that mutates the response shape and fails.

#### CLD-B06 — The native tool endpoint cannot be used, and its limits are not memory limits
**P1 · carried forward · FR-M9, FR-M28, FR-M9-04/05/07.** Related: GP-012, GP-020.

- The production `ToolSurface` has no path that populates permitted tools, so it denies everything.
- `tools/surface.py` buffers full output before truncating.
- The timeout does not kill descendant processes.

**Acceptance.** A permitted read/build/test/edit sequence works through the bus. Output flood stays within a memory budget. Descendants die on timeout.

---

### Dimension C — Security and privacy

#### CLD-C01 — Third-party tracing could export loop state; "nothing leaves the machine" is not enforced for the sidecar
**P0 · CONFIRMED-RUN (§3.4.2) · SEC-27 spirit, `docs/SECURITY-AND-DATA.md` data-flow statement, TASK-104 no-telemetry guard.**

- `extension/src/stdio-client.ts` L125–126 spawns the sidecar with `env: { ...process.env, ... }`.
- The sidecar's dependency closure includes `langchain-core`, `langsmith` and `langgraph-sdk`.
- No code scrubs `LANGSMITH_*`, `LANGCHAIN_*` or `LANGGRAPH_*` variables, or disables tracing.
- A developer who exported `LANGSMITH_TRACING=true` with an API key for unrelated work would start VS Code, and therefore the sidecar, with them.
- `check:telemetry` scans only extension and webview TypeScript (136 files), not the Python closure.

**Impact.** A privacy statement enterprise buyers rely on ("what leaves the machine: nothing") has an unguarded path.

**Acceptance.**
- The sidecar starts with tracing explicitly disabled and those variable families scrubbed.
- A test sets tracing variables pointing at a local HTTP listener, runs a loop, and asserts zero requests.
- The no-telemetry guard covers the Python closure (import-graph scan plus a runtime egress test).

#### CLD-C02 — Erasure and revocation integrity at scale
**P0 (subsumed in CLD-B01) · CONFIRMED-CODE.** Listed separately because it is the security and privacy face of CLD-B01, and a buyer's DPO or CISO will ask about exactly these two properties.

#### CLD-C03 — No OS-level containment; honest labels needed
**P1 · CONFIRMED-CODE / carried forward · FR-M9-05, SEC-14/32.** Related: GP-020.

- The plain-Python bridge launches arbitrary code.
- The environment scrub and egress refusal are policy checks, not a sandbox.

This is acceptable for a local, single-user tool only if every surface and document says so. Enterprise buyers will ask "can an agent exfiltrate my repository?", and the truthful answer today is "yes, if the agent itself chooses to — Meridian records and gates, it does not contain".

**Acceptance.** Either platform containment (process job objects or cgroups, a network namespace or a firewall rule, filesystem scoping) per supported OS, or explicit "uncontained" labels in `SECURITY-AND-DATA.md`, the Marketplace listing and the permission UI.

#### CLD-C04 — Portable-package integrity fix needs independent verification
**P2 · EVIDENCE-GAP · FR-M16-02/04, SEC-12.** Related: GP-003, GP-004.

`7d20faa` adds a signed content manifest, canonical containment, archive budgets and staged extract-then-publish with rollback, plus 15 tests in `test_portability_gp003_gp004.py`. Whether they pass on the audited commit is recorded in §3.4. The host-side importer (`extension/src/workbench/packages.ts`) is a separate path and was not re-audited here.

**Acceptance.** GPT's original reproductions (payload substitution, sibling-prefix traversal) fail before any write, on both the Python and host import paths.

#### CLD-C05 — Security identity inconsistencies
**P2 · CONFIRMED-CODE.**

- `SECURITY.md` L7 sends vulnerability reports to `github.com/meridianloom/meridian-loom/security/advisories/new`.
- The manifest `repository`, `homepage` and `bugs` all point to `github.com/Vibe-A-Thon/meridianloom`.

A reporter following the policy reaches a repository that may not exist, or is not the product's.

**Acceptance.** One canonical organisation, repository and contact, checked by a link test.

#### CLD-C06 — No security testing programme in CI
**P2 · EVIDENCE-GAP.**

- There is no SAST, no secret scanning, no `npm audit` / `pip-audit` gate and no dependency-update policy.
- No penetration test has ever been performed on the extension, sidecar RPC surface or webview.

The adversarial corpus is excellent but is not a substitute.

**Acceptance.**
- CI gates: SAST (Semgrep or CodeQL), secret scanning, and vulnerability audits for both ecosystems with owner/expiry exceptions.
- One external penetration test before general availability, with findings tracked.

---

### Dimension D — Testing and quality engineering

#### CLD-D01 — The suite is red in all three layers, the Python layer hangs, and the extension and webview layers are flaky
**P0 · CONFIRMED-RUN (§3.1, §3.4.6).**

| Layer | Result |
|---|---|
| Extension | 25 failures (full run), 10 (isolated) |
| Python core | ≥ 6 failures, and **a hang at ~98% that never ends** |
| Webview | 4 timeouts |

Acceptance additionally requires `pytest-timeout` (a per-test ceiling, e.g. 300 s, with an explicit `@pytest.mark.timeout` for known-long tests) and vitest `testTimeout` tuned per project. **A hung test must fail, not stall the gate.**

- Normal run: **25 failures**. Isolated re-run: **10 failures**. The failing set rotates.
- The causes are start-up timeouts on real-subprocess tests (sidecar spawn, fake ACP agents), Windows `EBUSY` temp-dir cleanup races, and one `EPIPE`.
- Previous status notes acknowledged "rotating real-subprocess e2e timeouts under parallelism, all pass isolated" (`363a16b`). This audit shows they do **not** all pass isolated.

**Impact.** A red, flaky suite means no release can be certified, regressions hide in noise, and a customer's platform team will reject the evidence.

**Acceptance.**
- The full suite passes **five consecutive times** on a frozen commit, on each CI OS.
- Real-subprocess tests share a warmed sidecar or use explicit readiness signals, not fixed sleeps or timeouts.
- Temp cleanup retries on `EBUSY` after process exit.
- Flaky tests are quarantined only with an owner and a date, never silently skipped.

#### CLD-D02 — CI can fail before running a single test
**P0 · CONFIRMED-CODE.** Related: GP-002, GP-032.

- In `.github/workflows/verify.yml`, the `contracts` job runs `npm run check:golden` and `npm run check:parity` (L122–125). These are Python scripts importing `meridian_core` and its dependencies (cryptography, langgraph and others).
- That job has no `actions/setup-python` step and no `pip install`. Only the later jobs do (L169, L231, L266, L320).
- All other jobs `needs: contracts`.
- The GPT audit observed consecutive red runs failing in this job.

**Impact.** No CI evidence exists that the product builds and tests green on any OS.

**Acceptance.**
- Every job that imports Python installs the locked dependencies first.
- CI runs the full OS matrix on every PR to the release branch.
- The last run on the release commit is green across all jobs, with its URL recorded in the release notes.

#### CLD-D03 — The test runner hides failures
**P1 · CONFIRMED-RUN.** `scripts/run-tests.mjs` exits at the first failing phase (L27, L44, L75, L82, L108, L114). On this audit's run, extension flakiness meant the core (1,800+ tests) and webview (356) suites never executed, and there was no signal that they were skipped.

**Acceptance.** The runner executes every phase, reports a per-phase table (passed, failed, skipped, duration) and exits non-zero if any phase failed. A `--fail-fast` flag stays available for developers.

#### CLD-D04 — No coverage measurement, and "claims bound to tests" checks existence, not execution
**P1 · CONFIRMED-CODE.** Related: GP-025, GP-037.

- There is no `pytest-cov` or Vitest coverage configuration anywhere.
- `check-claims.mjs` passes when a named test **exists**, not when it passed on the release commit.

Neither line coverage nor requirement coverage is measured.

**Acceptance.**
- Line and branch coverage is reported for Python, extension and webview, with floors set from the first measurement and ratcheting upward.
- The claims gate consumes the JUnit or JSON results of the release run and fails on any claim whose test did not pass.

#### CLD-D05 — No test runs the real extension inside VS Code
**P1 · CONFIRMED-CODE.** Related: GP-026.

- `vscode` is mocked in every extension test.
- `validate-package.mjs` L28 states it "does not open VS Code".
- There is no `@vscode/test-electron` or `@vscode/test-cli`.

Activation, webview load, the CSP, command registration, workspace trust, sidecar provisioning from a clean profile and uninstall have never been tested in a real editor.

**Acceptance.**
- An automated extension-host test job runs from the built VSIX in a clean user profile, on each CI OS, against the minimum and latest supported VS Code.
- It covers install → activate → provision/diagnose → one real RPC per tier → open the workbench → uninstall.

#### CLD-D06 — No static analysis for either language
**P1 · CONFIRMED-CODE.**

- **Python:** no ruff, flake8, pylint, mypy or pyright. `server.py` alone is 5,527 lines, and none of it is type-checked.
- **TypeScript:** `tsc --noEmit` runs, but there is no ESLint (no `no-floating-promises`, no unused-code or import-cycle rules) and no Prettier.

For a product that must pass enterprise code review and survive many contributors, including several AI agents, this is a high-leverage gap.

**Acceptance.**
- `ruff` (lint and format) and `mypy --strict` on new or changed modules, with a baseline file for existing debt that only shrinks.
- ESLint with the TypeScript type-aware ruleset, plus Prettier.
- All run in CI as gates.

#### CLD-D07 — Tests certify stand-in behaviour and weak properties as success
**P1 · CONFIRMED-CODE.** Related: GP-007, GP-030.

- `core/tests/test_orchestra_rpc.py` asserts that a loop started over RPC returns `completed`, which is the stand-in result (GP cites L115–123).
- `test_upgrade_path.py` sets `PRAGMA user_version` on a current-schema database and asserts a constant, so it never migrates an old database (GP-030).

Tests like these make coverage and pass counts meaningless for the goal.

**Acceptance.**
- Every test that asserts a success state for Orchestra, trainer, adapter lifecycle or upgrade is rewritten against real behaviour.
- Each gets a negative control that fails when the work is skipped: the project's own `MP2` rule, applied to the F3/F4+ code it was not applied to.

#### CLD-D08 — Performance, soak and resilience are not release evidence
**P1 · EVIDENCE-GAP · NFR-01…27, NFR-33, NFR-42, NFR-43.**

- Locally, performance tests run in report-only mode (`MERIDIAN_PERF_REPORT_ONLY=1`).
- The CI performance job exists, but CI has not been green (CLD-D02).
- Soak: **0.05 of 168 hours** (`docs/baselines/soak/…summary.json`).
- Resilience: **5 of 20** rehearsals, Windows only.
- Compatibility: 3 of 6 rows verified, Windows only.

**Acceptance.** See CLD-E03 and implementation work package WP-14.

#### CLD-D09 — The suite is too slow to run routinely, so it is not run
**P2 · CONFIRMED-RUN.**

- The core suite takes about 1 h 45 min serially and 20–60 min with `-n auto` on a workstation (`core/pyproject.toml` comment; this audit's runs).
- Extension real-subprocess tests take about 5–9 min.

The project history shows completion claims made on targeted subsets because the full suite takes too long (Kimi TD-012, TD-018).

**Acceptance.**
- A tiered suite: a fast PR tier under 10 min, gating; a full tier on merge and nightly, gating the release; a soak/performance tier on a schedule.
- Shared sidecar fixtures, and git repositories built once and copied rather than rebuilt per test.

#### CLD-D10 — Golden corpus and simulation parity prove little
**P2 · CONFIRMED-CODE.** Related: GP-023, GP-024.

- The golden corpus holds 1 story with 3 ledger entries.
- The parity harness sends read methods only and checks top-level keys.

**Acceptance.** Per GP-T023 and GP-T024, and once CLD-A01 exists, golden stories for greenfield, brownfield, rework, cancellation and crash-resume.

#### CLD-D11 — The Rust verifier is never built or tested in CI
**P2 · CONFIRMED-CODE.** `verifier/Cargo.toml` and its tests exist, but `verify.yml` has no cargo step. Either ship it (and test it) or remove it from the claims.

#### CLD-D12 — Human test protocols have never been executed
**P1 · EXTERNAL.**

- The protocols exist and are good: cold start, assistive, first value, two editors, evidence study.
- None has run.

See Dimension I and the implementation plan's external-evidence programme.

---

### Dimension E — Reliability, performance and scalability

#### CLD-E01 — Sidecar cold start is slow enough to time out its own tests
**P1 · CONFIRMED-RUN (timings in §3.4).**

- `server.py` imports nearly every subsystem at module load (L32–66 and on): attribution, all of governance, all observers, tree-sitter, metrics and more.
- The extension tests' 5–20 s budgets are exceeded.
- The product's own handshake default is 30 s (`meridian.sidecar.handshakeTimeoutMs`), and its description tells users to "raise it if a first launch times out on a slow machine".

A customer's first impression is a timeout.

**Acceptance.**
- Cold-start handshake at p95 of 2 s or less on the reference machine, measured in CI.
- Subsystems load lazily on first use.
- The handshake returns before optional subsystems load.

#### CLD-E02 — Single-threaded, synchronous control plane
**P1 · CONFIRMED-CODE.** Related: GP-008. `server.serve` dispatches synchronously, so any long-running handler (the future real Orchestra node, a large blame, a big export) blocks every other request, including `stop`, `ping` and `health`.

**Acceptance.** Long operations run on workers with cancellation. The control-plane methods stay responsive under load, proven by a test that sends `stop` during a long node.

#### CLD-E03 — Soak, resilience and multi-platform evidence
**P1 · EVIDENCE-GAP / EXTERNAL · MVP-R1.6, R1.7, R6.4, NFR-42, NFR-43.** These need a 168-hour soak on a dedicated machine, 20 resilience rehearsals (Windows, macOS, Linux and one remote configuration), and compatibility verified on every claimed row. The harnesses exist; the runs do not.

**Acceptance.** Recorded baselines under `docs/baselines/`, each bound to the release commit and package digest.

#### CLD-E04 — Monolith concentration
**P2 · CONFIRMED-CODE.**

- `core/meridian_core/server.py`: 5,527 lines, 240 KB.
- `extension/src/workbench/service.ts`: 2,728 lines.
- `shared/schema/methods.json`: 9,970 lines.

Change risk, merge conflicts between concurrent agents, and review cost all scale with these files.

**Acceptance.** Handlers are split by domain into modules behind a registration table. `methods.json` is split per domain with generated aggregation. No new handler lands in `server.py`.

#### CLD-E05 — Unpaginated scans are also a performance hazard
**P2 · CONFIRMED-CODE.** Fixing CLD-B01 by reading the full history each time would turn silent truncation into linear scans on every merge check. The fix needs indexed, subject-scoped queries (latest halt per subject, latest revocation per identity), not only pagination.

---

### Dimension F — Installation, deployment and operations

#### CLD-F01 — Customers must hand-provision a Python runtime and 45 packages
**P0 (for marketability) · CONFIRMED-CODE / CONFIRMED-RUN · FR-M3-05, D4, NFR-28 (15-minute first value), MVP-R1.**

- The extension does not bundle a runtime (D4).
- It finds an interpreter (Python extension, then `python3`/`python` on `PATH`) and, when modules are missing, shows a command built by `installCommand` (`extension/src/interpreter.ts` L45–58): `python -m pip install <8 pinned packages>`, **into whatever interpreter it found**.
- Those 8 resolve to **45 distributions**, several native (`cryptography`, `tree-sitter*`, `orjson`, `zstandard`, `xxhash`, `sqlite-vec`, `pydantic-core`).

In an IT-services company this collides with:
- managed laptops without admin rights;
- corporate proxies and air-gapped networks;
- conflicts with project-pinned versions in the same interpreter (langchain, pydantic, cryptography);
- system Pythons (Homebrew, Debian) that refuse `pip install` into the base environment (PEP 668);
- Windows Store Python stubs;
- users with no Python at all.

**Impact.** First value in 15 minutes (NFR-28) is implausible for a non-Python team, and many enterprise installs will fail outright.

**Acceptance.**
- The extension provisions an **isolated, private environment** it owns (for example a `uv`-managed or `venv` environment under extension global storage), from a hash-locked requirements set, with an offline wheel-bundle option and a documented proxy and mirror configuration. Alternatively, it ships per-platform bundled runtimes.
- A clean machine with no Python reaches a working sidecar through one guided action.
- Tested in CI on each OS.

#### CLD-F02 — Supported-platform claims exceed evidence
**P1 · EVIDENCE-GAP.** Related: GP-027.

- `docs/baselines/compatibility/2026-09-13-windows.json` verifies Windows 11, VS Code 1.95 and Python 3.11. Linux, macOS and Python 3.12 are `not-verified-here`.
- The remote configurations (SSH, WSL, dev containers, Codespaces) have no real-run evidence.

**Acceptance.** Every published row is backed by a real run on that platform, or removed (`MK5`).

#### CLD-F03 — Operator documentation contradicts itself
**P1 · CONFIRMED-CODE.** Related: GP-037.

- `docs/DEPLOYMENT.md` has **two "§9" and two "§10" sections** (L151 "9. Upgrading", L174 "10. Multi-tenant", L196 "9. Leaving", L208 "10. Known limitations").
- On rollback it says an older sidecar can read migrated state "where the older sidecar understands the newer columns" (L169–172).
- `docs/SUPPORT.md` L50–51 says: "A ledger migrated forward cannot be read by the previous sidecar."

An operator doing a rollback gets opposite answers.

**Acceptance.** One upgrade and rollback procedure, demonstrated by a test that migrates a fixture created by the previous released version, then rolls back.

#### CLD-F04 — Version and release hygiene
**P2 · CONFIRMED-CODE.**

- Versions disagree: extension `0.1.0`, sidecar (`core/pyproject.toml`) `0.0.1`, webview `0.0.1`.
- There is no automated version bump, tag or changelog release step.
- The built VSIX binary was force-added to git in `b3e868b` despite `.gitignore` excluding `/dist/*.vsix`.

**Acceptance.**
- One version, stamped into all components by the release script, with a git tag.
- Build artefacts published as release assets, never committed.

#### CLD-F05 — Operability for support
**P2 · CONFIRMED-CODE.**

- The sidecar logs to stderr and a rotating `~/.meridian/logs/sidecar.log`.
- `doctor` exists in the editor and headless.
- There is no **support-bundle** command that collects logs, the doctor report, versions, settings and a redacted environment into a file a customer can send.
- There is no documented log-level control.

With no telemetry (by design), support depends on what the customer can send.

**Acceptance.** A `Meridian: Create support bundle` command and a CLI equivalent with redaction tested against the adversarial corpus, plus a documented log-level setting.

---

### Dimension G — User experience, accessibility and localisation

#### CLD-G01 — Several catalogued surfaces are shells
**P1 · CONFIRMED-CODE.** Related: GP-022.

Non-test line counts:

| File | Lines |
|---|---|
| `modeling/ModelingStudio.tsx` | 20 |
| `governance/Repositories.tsx` | 24 |
| `modeling/ReplayStudio.tsx` | 29 |
| `modeling/ComprehensionStudio.tsx` | 34 |
| `governance/DeliveryEvidence.tsx` | 38 |
| `modeling/DiffStudio.tsx` | 43 |
| `modeling/CodeMapStudio.tsx` | 45 |
| `modeling/DiagramStudio.tsx` | 62 |

`DiagramStudio.tsx` L51 tells users loop endpoints are "not implemented by the current sidecar", which has been stale since `9060686` registered them. The catalogue says all 52 surfaces "connect to a dedicated interface" (`studios.test.tsx`), which is navigation coverage, not workflow coverage.

**Acceptance.** Every surface either delivers its specified workflow against the production backend, or is hidden or explicitly labelled "preview" in the UI and the listing. Stale capability notices are removed by a test that cross-checks notices against the method registry.

#### CLD-G02 — The execution experience is single-agent and non-isolated
**P1 · CONFIRMED-CODE.** Workbench runs are sequential, in the open workspace, with no worktree isolation, parallelism or transactional merge (`docs/gui-implementation.md` L51–52). For a product sold as orchestration, the user can watch one agent at a time edit their live checkout. See CLD-A02.

#### CLD-G03 — No guided onboarding
**P2 · CONFIRMED-CODE.**

- `contributes.walkthroughs` is empty.
- There are 9 settings.
- First run depends on reading `DEMO.md` and `docs/DEPLOYMENT.md`.

The cold-start protocol (MV4-T04) has never been run with a stranger.

**Acceptance.** A VS Code walkthrough (install runtime → bind an agent → first provenance answer → first export and verify), timed in a cold-start session.

#### CLD-G04 — No localisation
**P2 · CONFIRMED-CODE.** No `package.nls.json`, no `l10n/` bundle and no string externalisation in either TypeScript codebase. Many IT-services buyers (India, Europe, Japan) operate in English, but public-sector and European enterprise tenders often require localisation readiness.

**Acceptance.** Externalised strings via `vscode.l10n` and a webview i18n layer, with English as the default and at least pseudo-localisation tests. Translations are a business decision.

#### CLD-G05 — Accessibility evidence and procurement documents
**P1 · EXTERNAL / EVIDENCE-GAP · FR-M46-05, MVP-R6.5.**

- The structural tests are good.
- The six recorded human runs (keyboard-only and screen-reader, across launch, review and export) are not done.
- No VPAT / Accessibility Conformance Report exists. Public-sector and many enterprise buyers require one.

**Acceptance.** Recorded assistive runs per `docs/baselines/assistive/PROTOCOL.md`, plus a WCAG 2.1 AA ACR for the shipped surfaces.

---

### Dimension H — Documentation and knowledge integrity

#### CLD-H01 — Status documents claim completion the evidence does not support
**P1 · CONFIRMED-CODE.**

- `BUILD_STATE.md` records "ALL PHASES ENGINEERING-COMPLETE" (commit `55d3a72`), and the Kimi audit states "everything on the core lane is done" and "engineering complete" (§25–26).
- Against that: the suite is red (CLD-D01), the Orchestra runs stand-ins (CLD-A01), four modules are absent (CLD-A07), and endpoints report success without doing work (CLD-A04).

Every future agent that reads `BUILD_STATE.md` first — as its header instructs — starts from a false premise. That is how the prior "engineering complete" rounds happened.

**Acceptance.**
- `BUILD_STATE.md` carries only machine-checkable status: the last full-suite result by SHA, open P0/P1 counts from this register, and the release-gate state.
- "Complete" may be written only with a linked green run.

#### CLD-H02 — Documentation sprawl with three generations of requirements
**P2 · CONFIRMED-RUN.**

- **Volume and duplication:** 159 tracked Markdown files (3.9 MB). 11 groups of byte-identical duplicates, with 23 redundant copies: 10 specification documents duplicated between the root and `docs/spec/`, and 14 identical `adapters/*/learned/README.md`.
- **Three generations of requirements:** `md files/` holds older, diverged versions (`Requirements.md`, `VIGUIX.md`, `VIGUIX_GAPS.md`, `Requirements-Additions.md`).
- **Historical and internal material at the root:** `status.md` is a 966 KB historical log. `KIMI_MASTER_PROMPT.md` (an instruction prompt for another AI) and `BUILD-OPTIMIZATION-REPORT.md` sit at the root.
- **Competing gap registers:** there are now three audits (`gp`, `k`, `cld`).

**Acceptance.**
- One requirements tree (`docs/spec/`, read-only), with historical versions archived outside the product repository.
- Internal prompts and working notes moved out of the product root.
- **One** living gap register, which this audit proposes to be the companion implementation file, with the other audits frozen and linked as history.

#### CLD-H03 — The requirement set contradicts the code in both directions
**P2 · CONFIRMED-CODE.**

- `mvp-req-final.md` §3.1 (corrected under D56 on 13 September) says `runtime/`, `router/` and `simulation/` are absent; since 17 September they exist.
- `post-mvp-plan.md` §2 shows F3 "Not started" and CP1 "In progress", while F3–C6 were committed on 17 September and CP1 in `bcf2405`.
- `docs/claims.md` still withdraws the root roster as non-existent (GP-037).

**Acceptance.** The requirement disposition, plan status and claims are regenerated from this audit's register and bound to evidence (CLD-D04).

#### CLD-H04 — The claims gate proves a test name exists, not that it passed
**P2 · CONFIRMED-CODE.** See CLD-D04. `check-claims.mjs` reports "118 claims — 95 backed by a resolving test". On the audited commit, several of the extension tests backing shipped claims failed (for example ACP conformance). The gate stayed green.

---

### Dimension I — Requirement coverage

#### CLD-I01 — The MVP is not complete by its own definition
**P1 · CONFIRMED-CODE.**

`mvp-req-final.md` §5 has 33 groups `BUILT`, plus:

| Open group | Requirement | Disposition |
|---|---|---|
| **R1.6** | Tested support matrix | `MVP-GAP` |
| **R1.7** | Resilience rehearsals on three platforms | `MVP-GAP` |
| **R6.4** | Seven-day soak | `MVP-GAP` |
| **R6.5** | Keyboard and screen-reader journeys | `MVP-GAP` |
| **R5.2** | Evidence study | `MVP-HUMAN` |
| **R5.3** | First-value timing | `MVP-HUMAN` |
| **R5.4** | Two editors, two SCMs | `MVP-HUMAN` — also blocked because only one editor is supported |

#### CLD-I02 — POST-MVP: libraries built, products not
**P1 · CONFIRMED-CODE.**

| Area | State on `a00e4cd` | Main gaps |
|---|---|---|
| F3 Orchestra: M4 runtime, M8 router, M9/M28 tools, M7 memory, M38 comprehension, M31 roster, M5, M13, M32/M27 | Libraries and RPC handlers exist | Stand-ins, no agent binding, unwired tools, caller-asserted authority, ephemeral decisions (CLD-A01…A04, B02…B06; GP-014, 017, 018) |
| C3 portability (M16) | Built; GP-003/004 fix committed | Host path not re-audited (CLD-C04) |
| C4 learning (M14, M15, D6) | Library | Reports success without jobs (CLD-A04) |
| C5 tenancy, multi-repo, queue (M21, M22, SEC-23) | Registry | Not end-to-end tenant routing (GP-019); queue durability (CLD-B03) |
| C6 differentiation | Library | Unwired to product surfaces |
| M40 remainder (FR-M40-04, 06, 07, 08, 10) | Not verified in this audit | Carry forward |
| M26 cost levers (FR-M26-04) | Library | Do not shape real calls (GP-015) |
| FR-M26-05 model-comparison harness; FR-M13-06 contribution attribution | Missing | Kimi TD-010, TD-011 |
| M47 harness (J1/J2) | Absent | CLD-A07 |
| M48 tool-call governance | Absent | Gateway half gated on D48; lineage, observer path and declaration can be built |
| M49 attested identity | Absent | Design notes exist in this session's scratchpad (CP2) |
| M50 standards envelopes (DSSE/in-toto, C2PA, witness seam) | Partial | `8c1dd73` adds an in-toto-compatible envelope; standard-tool verification (AC-68) not proven |
| M51 longitudinal outcomes | Absent | — |
| M52 interoperability | CP1 built (`bcf2405`) | Verify with the suite |
| 35 POST-MVP screens (GF3) | Many routed shells | CLD-G01 |

#### CLD-I03 — Human and external gates
**P1 · EXTERNAL.**

| Gate | Needs | Blocks |
|---|---|---|
| MV5 evidence study (D21; `docs/evidence-gate.md`) | A pilot team, 20 stories, independent reviewers, 8 weeks | Any effectiveness claim (CLD-K04); the Orchestra go/stop decision |
| D37 SCM-side enforcement | A pilot customer's platform team | "Governance cannot be bypassed outside the editor" |
| AC-50 two editors, two SCMs | A second supported editor, and a customer | Any vendor-independence claim (FR-M43-15) |
| Cold-start and first-value sessions | 5 people who have never seen the product | NFR-28; onboarding quality |
| Assistive recorded runs | A screen-reader user | R6.5; the ACR |
| Soak and resilience matrix | Dedicated machines on 3 OSes plus a remote host | R6.4, R1.7 |

---

### Dimension J — Supply chain and release engineering

#### CLD-J01 — Notices and SBOM do not cover what customers actually install
**P1 · CONFIRMED-RUN.**

- `THIRD-PARTY-NOTICES.md` lists 8 Python packages and says it covers "every third-party component that **ships**".
- Python packages do not ship in the VSIX; customers install them (CLD-F01). The real runtime closure is **45 distributions**, with MPL-2.0 components (`certifi`, `orjson`) and Apache-2.0 components needing their notices.
- The AI-BOM covers the shipped library (agents, skills, presets) but not the runtime closure.

**Acceptance.**
- Notices and a CycloneDX software SBOM generated from the **locked full closure** (Python and Node), with licence texts included.
- Any MPL, file-level copyleft or unknown licence is reviewed and recorded.

#### CLD-J02 — Python dependencies are not locked with hashes
**P1 · CONFIRMED-CODE.** `core/pyproject.toml` pins direct dependencies only. Transitive versions float, so two customers can run different code, and a compromised transitive release installs silently.

**Acceptance.** A hash-locked lock file (`uv.lock` or `pip-compile --generate-hashes`) used by CI, by the provisioning in CLD-F01, and by the SBOM.

#### CLD-J03 — Unsigned artefacts and no build provenance
**P2 · CONFIRMED-CODE.**

- The VSIX is unsigned; the digest proves transit, not authorship, as `docs/claims.md` itself states.
- There is no SLSA or Sigstore provenance attestation for release builds.
- Marketplace publisher verification is not established.

**Acceptance.** A signed release: Marketplace-verified publisher, a Sigstore/cosign signature or attestation on the VSIX and SBOM, and reproducible build instructions.

#### CLD-J04 — Build artefacts committed; repository hygiene
**P2 · CONFIRMED-CODE.**

- The VSIX binary is tracked (`b3e868b`).
- `docs/gui/*.png` screenshots (0.2 MB each) and a 145 KB sample HTML are fine as documentation assets.
- `.codemap/` and `.codetwin/` tool directories sit at the root; confirm they are untracked and ignored.

**Acceptance.** The VSIX is untracked, releases are published as assets, and `.gitignore` is enforced by a CI check.

---

### Dimension K — Commercial, legal and go-to-market readiness

#### CLD-K01 — The licence contradicts the intent to sell
**P0 · DECISION · D19, GP-038, Kimi MKT-001/002.**

- The repository `LICENSE` is **MIT**.
- `extension/package.json` declares `"license": "MIT"`, and the `private` flag was dropped (`7549d43`) on the premise that "the goal overrides the deferral".
- Under MIT, any company may download, modify, rebrand and resell Meridian Loom at no charge, and the owner can never withdraw that grant for any version already published.

That directly contradicts "market this app to other IT companies" as a business, and the owner's recorded direction of an open core with paid features (D19). Owner determination on 10 September deferred the licence **deliberately**. Changing it was an engineering action taken on the owner's commercial question.

**Impact.** Publishing under MIT before this decision is irreversible for that code.

**Acceptance.**
- A recorded owner decision, with legal advice, choosing one model: proprietary EULA; open core (MIT or Apache core plus a commercially licensed paid module set); source-available (BSL, FSL, Elastic); or AGPL plus a commercial licence.
- Manifests, headers and notices aligned to it.
- **Until then, keep the repository private and do not publish the VSIX publicly.**

#### CLD-K02 — No entitlement or licensing mechanism
**P0 · DECISION + engineering.**

- Tiers (`flight-recorder`, `governor`, `orchestra`) are a workspace setting (`meridian.tiers`) any user can change.
- There is no licence key, seat model, entitlement check, offline licence file or grace period.

A paid Governor or Orchestra tier is currently a setting away from free.

**Acceptance.**
- After CLD-K01: an entitlement design with an offline-capable signed licence file and no phone-home, consistent with the no-telemetry promise.
- Tier gating reads entitlements, with tests proving an unlicensed paid tier is absent (not merely disabled, `G5`).

#### CLD-K03 — No customer-facing legal documents
**P1 · DECISION + drafting.** Beyond `SECURITY.md`, `docs/SECURITY-AND-DATA.md` and `docs/SUPPORT.md`, none of these exist:
- a EULA or Terms of Service;
- a privacy policy (even "we collect nothing" needs publishing);
- a Data Processing Addendum template;
- a sub-processor list (none, but it must be stated);
- a warranty and liability position;
- an export-control statement (cryptography: Ed25519, AES-GCM);
- an acceptable-use policy for AI agents.

**Acceptance.** Legal-reviewed documents published and referenced from the listing and the README.

#### CLD-K04 — No effectiveness evidence, so no outcome claims
**P1 · EXTERNAL · MV5, FR-M46-14/15/17, `mvp-req-final.md` §13.**

The product's own rules state it "makes no claim that the product improves delivery outcomes, reduces defects, saves cost or raises productivity", because the evidence study has not run. "Automate their application/software development works" is exactly such a claim.

**Impact.** Until the study (or a customer pilot with recorded results) exists, marketing must sell verifiable provenance, governance and compliance evidence, not productivity.

**Acceptance.** A pilot with a design partner, run under `docs/baselines/evidence-gate/PROTOCOL.md`, with the result published whatever it is. Marketing claims then map one-to-one to recorded evidence in `docs/claims.md`.

#### CLD-K05 — Brand, trademark and publisher identity are unresolved
**P1 · DECISION.**

- "Meridian Loom" has no recorded trademark clearance.
- The Marketplace publisher id is `meridianloom`; the repository lives under `Vibe-A-Thon`; the security contact points at `meridianloom/meridian-loom`.
- Copyright is "Meridian Loom contributors", with no legal entity named.

A buyer's procurement desk needs a contracting entity.

**Acceptance.**
- A trademark search or filing in target markets.
- One legal entity named in the licence, EULA and publisher profile.
- One repository and organisation.

#### CLD-K06 — Marketplace listing is not launch-grade
**P1.**

- There is no gallery banner, no screenshots or animated demo in `extension/README.md` (screenshots exist in `docs/gui/`), no demo video, no pricing field, and `qna: false`.
- The categories include "Machine Learning", which may mis-target discovery.
- There is no public documentation site or tutorial repository.

**Acceptance.** A listing with screenshots, a 2–3 minute demo video recorded on the release build, pricing and trial terms, links to docs, support and security, and a sample repository with a scripted first-value path.

#### CLD-K07 — Enterprise procurement pack is missing
**P1.** Buyers in IT services will send a security questionnaire (SIG Lite or CAIQ) and ask for:
- a penetration-test summary;
- an SBOM covering the full closure;
- an accessibility ACR;
- a data-flow diagram;
- an AI-governance statement;
- support SLAs;
- a vulnerability-handling SLA (`SECURITY.md` promises 10/20/30 working days — acceptable, but must be staffed).

The bundle's ISO/IEC 24970 and EU AI Act Article 12/26 mappings are a genuine differentiator here and should lead.

**Acceptance.** A versioned "Trust pack" folder generated per release from repository sources wherever possible.

#### CLD-K08 — Competitive position is exposed on three fronts
**P1 · DECISION + engineering.**

`mvp-req-final.md` §16 records the pressure:

| Front | Competitor | Meridian today |
|---|---|---|
| Cross-vendor line-level provenance (CMP-01) | Exceeds Ink | Answered by being verifiable and bound to the merge decision |
| Bundling into the SCM (CMP-02) | DX, now Atlassian | — |
| Governance at the tool call (CMP-03, CMP-05) | Agent gateways | Governs the merge only; M48 absent |

Meridian's durable differentiator — a signed, independently verifiable record bound to the human decision that let a change merge, verifiable without Meridian installed — is built. Its weakest points against these competitors are the Orchestra (CLD-A01), enforcement that can be bypassed outside the editor (D37), and identity no stronger than a git config name (M49).

**Acceptance.** A positioning decision: lead with verifiable governance, not automation, until CLD-A01 and CLD-K04 close. Roadmap priorities chosen against these three fronts.

#### CLD-K09 — No commercial operations
**P2 · DECISION.**

- No pricing, trial or licence-delivery process.
- No support desk or SLA (`docs/SUPPORT.md` states there is no paid support).
- No customer-success runbook, onboarding service or design-partner programme.
- No product analytics. That is by design (no telemetry), so an opt-in feedback channel is needed.

**Acceptance.** Owner decisions and runbooks. Engineering supplies the entitlement mechanism (CLD-K02), the support bundle (CLD-F05) and an opt-in feedback command.

---

### Dimension L — Engineering process and governance

#### CLD-L01 — Concurrent AI agents commit to one branch without a release captain
**P1 · CONFIRMED-CODE (git history).**

In the last 93 commits, several AI sessions (Claude, GPT, Kimi and a parallel "GUI session") committed to `dev_local`. The pattern:
- Modules covering dozens of FRs landed 5–10 minutes apart on 17 September (M8 at 17:56, M4 at 18:28, M9/M28 at 18:36, M7 at 18:43, M38 at 18:50, M31 at 19:00, …, "ALL PHASES ENGINEERING-COMPLETE" at 19:43).
- Some commit messages are uninformative ("new gap fixes", "build fix changes", "no need files").
- Completion was claimed without a full-suite run.

The project's own `MP3` rule (one tree, one sequential suite, one commit) was not held.

**Impact.** Speed without verification produced the overclaims this audit had to unwind, and it will again.

**Acceptance.**
- Work lands through pull requests into a protected release branch, with required green CI (CLD-D02), a required review, and a single designated integrator per work package.
- No agent may edit `BUILD_STATE.md` status except through the generated status of CLD-H01.

#### CLD-L02 — No release branch or release process in use
**P2 · CONFIRMED-CODE.**

- All work is on `dev_local`.
- CI's full OS matrix runs only on `main`, on a schedule or on manual dispatch.
- There are no tags.
- `mvp-impl-plan.md` §13 describes a release procedure that has never been executed.

**Acceptance.** Execute §13 end to end for a release candidate: tag, artefacts, recorded baselines and release notes.

#### CLD-L03 — Competing gap registers
**P2.** Three audit pairs now exist. Without consolidation, agents will work from whichever they read first.

**Acceptance.** The companion implementation file of this audit is the single living register (it maps every GP and Kimi ID). The others are frozen as history and linked from it.

---

## 5. Scorecard (no invented percentages)

Readiness per dimension on a 0–5 scale: **0** absent, **1** designed only, **2** partially built, **3** built with known defects, **4** built and verified with minor gaps, **5** release-ready with evidence.

| Dimension | Score | Why |
|---|---|---|
| A. Core function vs the goal (automating development) | **1** | Orchestra libraries exist; execution is stand-ins |
| A′. Core function vs the honest product (governance and provenance) | **3** | Real, but with CLD-B01 and platform gaps |
| B. Correctness and integrity | **2** | Strong ledger; P0 truncation defects in governance and privacy readers |
| C. Security and privacy | **2** | Deep controls, but a reproduced third-party egress path (tracing inheritance), caller-asserted authority and no containment open |
| D. Testing and QA | **2** | Large, careful suite; red and flaky, no coverage, no linters, no real-editor tests |
| E. Reliability and performance | **2** | Harnesses exist; soak, resilience and multi-platform evidence absent; slow cold start |
| F. Installation and operations | **1** | Manual 45-package Python provisioning; contradictory operator docs |
| G. UX, accessibility and localisation | **2** | Good core screens; shells, no onboarding, no l10n, no human a11y runs |
| H. Documentation integrity | **2** | Excellent individual documents; sprawl, duplication and false status claims |
| I. Requirement coverage | **2** | MVP 33/40 groups; post-MVP largely library-level; four modules absent |
| J. Supply chain and release | **2** | BOM, notices and checksums exist; incomplete closure, no lock, unsigned, CI red |
| K. Commercial and legal | **0–1** | Licence contradicts sale; no entitlements, EULA, procurement pack or evidence |
| L. Engineering process | **1** | No release branch, review gate or single integrator; overclaim pattern |

---

## 6. Reconciliation with the earlier audits

### 6.1 GPT audit (`audit-1-gp-g-req.md`, GP-001…GP-041)

| GP | Status on `a00e4cd` per this audit | This audit's ID |
|---|---|---|
| GP-001 release scope / source of truth | Open | CLD-H03, CLD-L03 |
| GP-002 host consumers / CI | Host wrappers exist; **CI still structurally broken** | CLD-D02 |
| GP-003 package payload authentication | Fix committed (`7d20faa`), 15 tests; host path not re-audited | CLD-C04 |
| GP-004 archive containment | Fix committed (`7d20faa`) | CLD-C04 |
| GP-005 caller-asserted authority | **Open — re-confirmed** (L517, L616, L761–765, L799–805, L866–884) | CLD-B04 |
| GP-006 contract drift | **Partly fixed** (loop.* shapes in `a00e4cd`); general validation open | CLD-B05 |
| GP-007 Orchestra stand-ins | **Open — re-confirmed** | CLD-A01 |
| GP-008 stop/resume/scheduling | **Open — re-confirmed**; also unknown-loop stop writes a false ledger entry, and resume raises `KeyError` | CLD-B02, CLD-E02 |
| GP-009 restart resume | **Superficially fixed** (stand-ins re-bound) | CLD-B03 |
| GP-010 queue durability | Not re-verified; carried forward | CLD-B03 |
| GP-011 separate execution paths | **Open — re-confirmed** (docs L51–52) | CLD-A02, CLD-G02 |
| GP-012 tool permission population | Carried forward | CLD-B06 |
| GP-013 two registries | Carried forward | CLD-A02, CLD-A04 |
| GP-014 governed context assembly | Carried forward | CLD-I02 |
| GP-015 cost levers | Carried forward | CLD-I02 |
| GP-016 learning endpoint | **Open — re-confirmed** (L846–884) | CLD-A04 |
| GP-017 decisions ephemeral | Carried forward | CLD-I02 |
| GP-018 interface contracts | Carried forward (`a00e4cd` touched `interface_contracts.py`; not re-verified) | CLD-I02 |
| GP-019 tenancy | Carried forward | CLD-I02 |
| GP-020 subprocess containment | Carried forward | CLD-B06, CLD-C03 |
| GP-021 identities, caps, ratio | **Extended**: 25 unpaginated call sites, halts and revocations fail open | CLD-B01, CLD-A03 |
| GP-022 GUI shells | **Re-confirmed**, with line counts | CLD-G01 |
| GP-023 parity weak | Carried forward | CLD-D10 |
| GP-024 golden corpus small | Carried forward | CLD-D10 |
| GP-025 testing claim unsupported | **Re-confirmed** — suite red | CLD-D01…D09 |
| GP-026 no installed-editor test | **Re-confirmed** | CLD-D05 |
| GP-027 platform labels | **Re-confirmed** | CLD-F02 |
| GP-028 soak/performance/recovery | **Re-confirmed** | CLD-E03 |
| GP-029 accessibility | **Re-confirmed** | CLD-G05 |
| GP-030 upgrade tests weak | Carried forward | CLD-D07, CLD-F03 |
| GP-031 packaging omits roster | **Re-confirmed** (0 manifests) | CLD-A06 |
| GP-032 supply chain | **Re-confirmed and extended** (45-package closure, MPL, no lock) | CLD-J01, CLD-J02 |
| GP-033 enterprise enforcement | Carried forward (D37) | CLD-I03 |
| GP-034 SDLC connectors | Carried forward | CLD-I02 |
| GP-035 JIT | **Re-confirmed** (M47 absent) | CLD-A07 |
| GP-036 competitive modules | **Re-confirmed** (M48, M49, M51 absent) | CLD-A07 |
| GP-037 docs contradict reality | **Re-confirmed and extended** | CLD-F03, CLD-H01…H04, CLD-C05 |
| GP-038 open-core boundary | **Escalated to P0 decision**: MIT is already declared | CLD-K01, CLD-K02 |
| GP-039…041 | Carried forward via the GP implementation plan | see `audit-1-cld-g-impl.md` §6 |

### 6.2 Kimi audit (`audit-1-k-g-req.md`)

| Kimi item | Status |
|---|---|
| GAP-001 Orchestra unwired | Wiring exists (RPC, host wrappers, some GUI). **The behaviour behind it is stand-ins**, which the Kimi audit recorded as "intentional" (TD-001, P3). This audit disagrees with that severity: under the stated goal, it is P0 (CLD-A01) |
| GAP-101 stale artefact | Rebuilt (`ce8ad4d`); the artefact still lacks the roster (CLD-A06) |
| GAP-102 host consumers | Partly (loop control, adapter registry, pass-through) |
| GAP-103 FR-M26-04 | Library built (`985f374`); does not shape real calls (GP-015) |
| TD-012, TD-018 full suite not run | **Now run: red** (CLD-D01) |
| MKT-001 licence | "Resolved" by declaring MIT. **This audit reopens it as P0** (CLD-K01) |
| MKT-002 open-core | Open (CLD-K02) |
| §25–26 "engineering complete" | **Not supported** (CLD-H01) |

---

## 7. What can be marketed truthfully today, and what cannot

| Claim | Status today | Condition to claim it |
|---|---|---|
| "Every agent change recorded in a signed, hash-chained ledger that a third party verifies without Meridian installed" | **Claimable** (AC-33, AC-49 backed) | Keep it bound to tests that pass on the release commit |
| "Cross-vendor provenance: which agent wrote which line, with confidence stated" | **Claimable**, with the three-state and confidence caveats | — |
| "Governed agent runs: permissions, gates, approvals, spend ceilings, halts" | **Claimable for the editor boundary**; "cannot be bypassed" is **not** claimable (D37) | CLD-B01 fixed; SCM enforcement for the stronger claim |
| "Compliance evidence mapped to ISO/IEC 24970, EU AI Act Art. 12/26, SSDF, ISO 42001 (supporting evidence, not certification)" | **Claimable** with the existing not-a-conformity sentence | — |
| "Bring your own agents — Claude Code, Gemini CLI, Codex or any ACP agent" | **Claimable** | Platform evidence (CLD-F02) |
| "Automates your software development / an AI delivery team" | **Not claimable** | CLD-A01, CLD-A02 and CLD-K04 |
| "Improves productivity, quality or cost" | **Not claimable** | CLD-K04 (MV5 or pilot evidence) |
| "Self-improving agents" | **Not claimable** | CLD-A04 |
| "Works on Windows, macOS, Linux and remote" | **Only Windows is evidenced** | CLD-F02 |
| "Nothing leaves your machine" | **Claimable for the extension; unguarded for the sidecar** | CLD-C01 |
| "Enterprise-ready: tenancy, SSO, attested identity" | **Not claimable** | GP-019, D38, M49 |

**Recommended go-to-market sequencing.** Launch first as **governance and verifiable evidence for AI-assisted development** (Flight Recorder plus Governor) to design partners under a commercial licence, once dimensions B, C, D, F, J and K reach their P0/P1 exits. Run the evidence study with those partners. Market automation only after the Orchestra executes real work and the study has reported.

---

## Appendix A — Commands used for evidence

```bash
# Full suite (project runner)
npm test                                        # exit 1; extension 25 failed / 600 passed

# Isolation re-run of the failing extension files
cd extension && npx vitest run test/acp-client.test.ts test/acp-conformance.test.ts \
  test/adapters-launch.test.ts test/bus-types.test.ts test/evidence-chain-e2e.test.ts \
  test/steer.test.ts test/tiers-e2e.test.ts test/workbench.test.ts   # 10 failed / 80 passed

# Core and webview (run separately because the runner stops at the first failure)
cd core && MERIDIAN_PERF_REPORT_ONLY=1 python -m pytest tests -q -m "not perf" -n auto
cd webview && npx vitest run

# Ledger page semantics
grep -n "ORDER BY seq LIMIT" core/meridian_core/ledger/core.py
grep -rnE "limit=1000|limit=100000" core/meridian_core --include=*.py

# Dependency closure (importlib.metadata walk over the 8 declared requirements)  -> 45
# Module presence
for m in M47 M48 M49 M51; do grep -rlE "FR-$m-[0-9]+" core/meridian_core core/tests; done   # none

# VSIX inspection
node --input-type=module -e "import {openZip} from './scripts/lib/vsix.mjs'; ..."   # 0 roster manifests
```

## Appendix B — Reproduction probes

The probe scripts are saved in [`audit-probes/`](audit-probes/). They are standalone Python scripts; run each from the repository root with the core dependencies installed (`python audit-probes/<name>.py`). They insert `core/` into `sys.path` via an absolute path, so edit that line for your checkout. On Windows, `probe_cap.py` may raise a `PermissionError` while cleaning up its temporary directory (`ledger.db` is still open); that happens after its results are printed and does not affect them.

| Script | Reproduces | Expected output on `a00e4cd` | Expected output once fixed |
|---|---|---|---|
| `probe_cap.py` | CLD-B01: halt after 1,000 gate rows (and a revocation variant) | `halt on feature/y ... seen: []` | a non-empty halt list |
| `probe_langsmith.py` | CLD-C01: tracing inherited through the environment (LangGraph directly) | `requests reaching fake LangSmith endpoint: 4` including `POST /runs/multipart` | `0` (because WP-03 disables tracing in-process as well) |
| `probe_product.py` | CLD-C01 via `SidecarServer` → `loop.start`; CLD-A01 stand-in `completed`; CLD-B01 revocation | 3× `POST /runs/multipart`; `status: completed`; `mallory ... revoked_at: None` | 0 requests; `status: simulated`; a revocation timestamp |

WP-01 and WP-03 must convert these probes into permanent regression tests under `core/tests/`. After that, `audit-probes/` can be deleted.
