# Meridian Loom — Goal Audit 1 (Claude): Implementation Plan to Close the Gaps

| | |
|---|---|
| **Findings register** | [`audit-1-cld-g-req.md`](audit-1-cld-g-req.md). Every task cites the `CLD-*` IDs it closes. Read the finding before starting the task. |
| **Baseline commit** | `a00e4cd` on `dev_local` |
| **Audience** | The coding agent (or engineer) that implements the fixes, plus the owner for the decisions in §3 |
| **Status of other registers** | This file is proposed as the **single living gap register**. `audit-1-gp-g-*.md` and `audit-1-k-g-*.md` become history, and every GP/Kimi item they raise is mapped in §6 |

---

## 0. Rules for the implementing agent

These rules exist because the history on `dev_local` shows how completion was claimed before it was true (CLD-H01, CLD-L01). They are not optional.

1. **Work one package at a time, in the order in §2.** A work package is done only when every one of its "Done when" criteria has evidence recorded in §7.
2. **Failing test first (MP2).** For every behavioural fix, first write the test that reproduces the defect and show it failing on the baseline. Paste the failing output into the PR description. Then fix. A test that would pass on the unfixed code is not evidence.
3. **Negative controls for every guard.** Every security, integrity or authority check needs a test that proves the guard *refuses* something, and a mutation check: temporarily remove the guard, confirm the test fails, restore it, and confirm by hash that the restore is exact.
4. **No stand-in may report success.** Any path that does not do real work must return a distinct state (`simulated`, `not_bound`, `unavailable`) and never `completed`, `ran`, `promoted` or `retired`.
5. **Full suite before claiming done.** Run `npm test` (after WP-00 makes it run every phase) on the final commit of the package. Record the SHA, the per-phase counts and the duration. Targeted runs are for iteration only.
6. **Do not edit status documents by hand.** `BUILD_STATE.md` status, `docs/claims.md` status and the disposition columns change only through the generators added in WP-11. No sentence may say "complete", "production-ready" or "all phases" without a linked green run.
7. **No new code in `server.py`.** New handlers go into domain modules (WP-10.4).
8. **Keep the security constraints.** Credentials never appear in agent arguments. Integration credentials live only in the OS keychain, and a missing keychain refuses the save. `redact()` runs on every error. All integration operations are reads. No `MERIDIAN_*` variable is inherited by a child process (SEC-27). Imported agents enter Learning with only `read`, `search` and `think` permissions.
9. **Do not publish anything publicly** (Marketplace, public repository, public release) until decision **OD-1** (licence) is recorded (CLD-K01).
10. **Commits.** One work-package task per commit where practical, with a message stating the finding IDs, e.g. `fix(governance): paginate gate/approval reads — CLD-B01`. End commit messages with the project's attribution line.

### 0.1 Verification commands used throughout

```bash
# Whole suite, every phase (after WP-00.3)
npm test

# Phases individually
cd extension && npx tsc --noEmit && npx vitest run
cd core && python -m pytest tests -q -m "not perf" -n auto
cd webview && npx tsc --noEmit && npx vitest run

# Gates
npm run check:surface && npm run check:claims && npm run check:mvp-traceability \
  && npm run check:release-notes && npm run check:licences && npm run check:notices

# Package
npm run package && node scripts/validate-package.mjs
```

---

## 1. Release gates

The goal clauses are defined measurably in `audit-1-cld-g-req.md` §0.3. These gates operationalise them. **A release is production-ready only when G1–G8 are all green on one frozen commit. It is marketable only when G9–G11 are also met.**

| Gate | Passes when | Work packages |
|---|---|---|
| **G1 Green, stable suite** | The full suite passes 5 consecutive times on the frozen commit on Windows, macOS and Linux in CI, and the runner executes every phase | WP-00, WP-09 |
| **G2 No open P0 or P1 integrity or security finding** | CLD-B01, B02, B04, B05, C01 and C03 are closed with negative-control evidence | WP-01, WP-02, WP-03, WP-06, WP-07 |
| **G3 Installed-artefact truth** | The VSIX installs into a clean VS Code profile on each OS, provisions its runtime without manual steps, loads the roster and policy, and passes the real-editor smoke test | WP-04, WP-08, WP-09 |
| **G4 Every claim executes** | Every sentence in the README, listing and docs maps to a test that **passed** in the release run. Every unfinished surface is hidden or labelled | WP-11, WP-12 |
| **G5 Measured quality** | Coverage is reported and at or above its floors. Lint and type gates pass. SAST, secret scanning and dependency audits pass or carry dated exceptions | WP-09 |
| **G6 Operational evidence** | 168-hour soak, 20 resilience rehearsals across 3 OSes plus one remote, a compatibility row per claimed platform, and cold start ≤ 2 s at p95 | WP-14, WP-06 |
| **G7 Supply chain** | Hash-locked full closure, a complete SBOM and notices, a signed VSIX with provenance, and no build artefacts in git | WP-10 |
| **G8 Operable** | One consistent upgrade and rollback procedure, proven by a test using the previous release's data. Support bundle available. Docs consistent | WP-08, WP-11 |
| **G9 Legal and commercial** | OD-1 (licence) and OD-2 (entitlements) decided and implemented. EULA, privacy policy and DPA published. Legal entity and trademark settled | WP-16 |
| **G10 Evidence behind marketing** | Assistive runs, cold-start and first-value sessions, plus a design-partner pilot or MV5 study recorded. Marketing copy is limited to what is recorded | WP-15, WP-16, §5 |
| **G11 "Automates development" claim** *(only if that is to be marketed)* | The Orchestra executes a real task end to end through governed ACP agents in isolated worktrees (WP-05), and evidence exists for its effect | WP-05, §5 |

**Recommended launch sequence** (see req §7):
- **Launch A** — governance and verifiable evidence (Flight Recorder plus Governor), to design partners: G1–G10.
- **Launch B** — Orchestra and automation: add G11.

---

## 2. Work packages and order

```
WP-00 Stabilise suite & CI  ──┬─> WP-01 Ledger read correctness (P0)
                              ├─> WP-02 Authority & RPC validation
                              ├─> WP-03 Sidecar egress & env hygiene
                              ├─> WP-04 Packaged resources (roster/policy)
                              └─> WP-09 Quality tooling ─> WP-10 Supply chain & release
WP-01..04 ─> WP-06 Runtime control & durability ─> WP-05 Real Orchestra execution
WP-08 Provisioning ─> WP-14 Performance/soak/resilience
WP-11 Docs & status truth (start in parallel; finish last)
WP-12 GUI completeness ─ WP-13 Missing modules ─ WP-15 A11y & l10n
WP-16 Commercial pack (owner-led; starts now)
```

| WP | Title | Priority | Closes |
|---|---|---|---|
| WP-00 | Stabilise the suite and repair CI | P0 | CLD-D01, D02, D03, E01 (partly) |
| WP-01 | Ledger read correctness (row cap) | P0 | CLD-B01, C02, E05, A03 (ratio read) |
| WP-02 | Authority and RPC boundary validation | P1 | CLD-B04, B05, B02 (unknown ids) |
| WP-03 | Sidecar egress and environment hygiene | **P0** (reproduced leak) | CLD-C01 |
| WP-04 | Packaged runtime resources | P1 | CLD-A06 |
| WP-05 | Real Orchestra execution through governed ACP | P0 for Launch B | CLD-A01, A02, A03, A04, D07, G02 |
| WP-06 | Runtime control, concurrency and durability | P1 | CLD-B02, B03, E02, B06 |
| WP-07 | Containment or honest labelling | P1 | CLD-C03 |
| WP-08 | Provisioning, upgrade and operability | P0 for marketability | CLD-F01, F03, F05, E01 |
| WP-09 | Quality tooling and test architecture | P1 | CLD-D04, D05, D06, D09, D10, D11, C06 |
| WP-10 | Supply chain, versioning, signing, release | P1 | CLD-J01–J04, F04, E04, L02 |
| WP-11 | Documentation and status truth | P1 | CLD-H01–H04, A05, C05, F03, L03 |
| WP-12 | GUI completeness and onboarding | P1 | CLD-G01, G03 |
| WP-13 | Missing competitive modules | P2 | CLD-A07, I02 |
| WP-14 | Performance, soak, resilience, platform matrix | P1 | CLD-E03, D08, F02 |
| WP-15 | Accessibility and localisation | P1/P2 | CLD-G04, G05 |
| WP-16 | Commercial, legal and go-to-market pack | P0 (decision) | CLD-K01–K09, L01 |

---

## WP-00 — Stabilise the suite and repair CI (P0)

**Why.** Nothing downstream can be certified while the suite is red and flaky and CI fails before tests run (CLD-D01, D02, D03).

### WP-00.1 — Make CI install Python wherever Python runs
- **Files:** `.github/workflows/verify.yml`.
- **Steps:**
  1. In the `contracts` job, add `actions/setup-python@v5` (Python 3.12, pip cache) and `pip install -e core[dev]` from the lock file (after WP-10.1; until then, use the pinned requirements) before `check:golden` / `check:parity`.
  2. Audit every other job for Python use, and add the same step wherever it is missing.
  3. Add a Python 3.11 leg (the documented minimum) to the core job matrix.
- **Test:** push the branch and confirm the `contracts` job passes. Then temporarily remove the pip step and confirm it fails with the import error (negative control).
- **Done when:** a CI run on the branch is green in every job, and its URL is recorded in §7.

### WP-00.2 — Remove the extension-suite flakiness at its cause
- **Files:** `extension/test/**` (especially `acp-client`, `acp-conformance`, `adapters-launch`, `bus-types`, `evidence-chain-e2e`, `steer`, `tiers-e2e`, `workbench`), `extension/src/stdio-client.ts`, and test helpers.
- **Steps:**
  1. **Readiness, not time.** Replace fixed timeouts with explicit readiness signals: wait for the sidecar `initialize` response and for the fake agent's ready line. Keep a single generous outer timeout (60 s) purely as a hang detector.
  2. **Shared warm sidecar.** Add a per-file (or per-worker) fixture that starts one sidecar and shares it across tests that do not need a fresh process. Only crash/restart tests spawn their own.
  3. **Windows cleanup.** Create a `rmWithRetry(dir)` helper: wait for the child's `exit` event, then retry `EBUSY`/`EPERM` with backoff (up to about 2 s). Use it in every `afterEach`.
  4. **EPIPE.** Guard writes to a child's stdin after exit, both in the product code (`stdio-client.ts`) and in tests. A write after exit must surface as a named `SidecarGone` error, not an unhandled `EPIPE`.
  5. **Assertion race.** `expected 'running' to be 'completed'`: wait on the state-change event, not a snapshot.
  6. Set `poolOptions` / `maxWorkers` for real-subprocess files so they do not oversubscribe the CPU. Tag them `@e2e` so WP-09.5 can tier them.
- **Test:** run the extension suite 10 times in a loop on Windows and in CI on all three OSes. Record the failure count; the target is 0/10.
- **Done when:** 10/10 local passes on Windows, and 5/5 green CI runs on each OS.

### WP-00.3 — The runner executes every phase and reports honestly
- **Files:** `scripts/run-tests.mjs`.
- **Steps:**
  1. Run all phases even after a failure.
  2. Print a table (phase, passed, failed, skipped, duration).
  3. Write `test-results/summary.json` plus JUnit XML per phase (vitest `--reporter=junit`, pytest `--junitxml`).
  4. Exit non-zero if any phase failed.
  5. Keep a `--fail-fast` flag.
- **Test:** make one webview test fail deliberately, and confirm the core phase still runs and the exit code is 1. Then revert.
- **Done when:** `summary.json` is produced and consumed by WP-11.2.

### WP-00.3a — Hung tests must fail, not stall
- **Why:** the core suite hung at ~98% for over an hour on the audited commit (req §3.4.6).
- **Steps:**
  1. Add `pytest-timeout` to `[dev]` and set `timeout = 300` plus `timeout_method = "thread"` in `core/pyproject.toml`.
  2. Mark known-long tests explicitly.
  3. In vitest, set `testTimeout` per project (webview 15 s, extension unit 10 s, `@e2e` 60 s) and fix the 4 webview timeouts in `ledger-screen.test.tsx` and `screen-invariants.test.tsx` by awaiting the rendered state (`findBy*`/`waitFor`), not by raising the limit.
  4. Fix the slow and hanging tests named in req §3.4.6:
     - move `test_event_ingestion.py::test_clean_full_100k_fixture_reconciles_exactly` and `test_full_history_metrics.py::test_equals_full_scan_recomputation` to the `perf`/nightly tier (add a 5k-row variant to the default tier);
     - make every test that starts a session observer stop it in teardown, and add an autouse fixture that fails a test when it leaks threads (`threading.enumerate()` before/after);
     - update `test_bus_types.py::test_placeholder_methods_answer_not_implemented` and `extension/test/bus-types.test.ts` to the implemented loop.* contract (only `trust.summary` remains a stub).
  4b. Profile `merkle.append` / `node_hash` during 100k ingestion. If ingest throughput is below the NFR budget, batch the Merkle updates per transaction (WP-14).
  5. Add `faulthandler_timeout = 600` so any future hang prints a stack.
- **Done when:** the core suite completes (pass or fail) within 30 min with `-n auto` on the CI runner, and no test exceeds its ceiling.

### WP-00.4 — Fast start for the sidecar (first slice of CLD-E01)
- **Files:** `core/meridian_core/server.py`, and its imports.
- **Steps:**
  1. Measure: `python -X importtime -m meridian_core.server < /dev/null 2> importtime.txt`. Record the top 20.
  2. Move subsystem imports (observers, tree-sitter, metrics, governance, orchestra, langgraph) into the handler registration so they load on first use (a lazy registry keyed by method prefix).
  3. `initialize` / `ping` must not import optional subsystems.
- **Test:** a new perf test measures spawn-to-`initialize`-response latency. It is report-only in WP-00; WP-14 makes it a gate at ≤ 2 s p95.
- **Done when:** the cold-start time is recorded before and after in §7.

---

## WP-01 — Ledger read correctness (P0)

**Why.** Halts and revocations fail open, and erasures stop replaying, once more than 1,000 rows of a type exist (CLD-B01, C02).

### WP-01.1 — Provide correct read primitives in the ledger
- **File:** `core/meridian_core/ledger/core.py`.
- **Add:**
  1. `iter_query(action_type=None, subject=None, after_sequence=0, page=1000)`: a generator that pages by `after_sequence` until exhausted. It is the **only** sanctioned way to read full history.
  2. `latest(action_type, *, subject=None, where=None)`: `ORDER BY seq DESC LIMIT 1`, with an index covering `(action_type, subject, seq)`.
  3. `query_desc(action_type, limit)`: newest-first, for UI lists.
  4. A schema migration adding the index if missing (idempotent; recorded in the migration ledger).
- **Tests (write first):**
  - 2,500 rows → `iter_query` yields 2,500 in sequence order.
  - `latest` returns the 2,500th.
  - The migration is idempotent and has an upgrade test from a pre-index database fixture.

### WP-01.2 — Fix every caller
For each site, replace the single `query(limit=1000)` with the correct primitive:

| Site | Correct primitive |
|---|---|
| `governance/merge_gate.py` `_iter_gate_rows`, `_iter_approval_rows`, `active_halts` | Per-subject latest-state query (halt set/cleared) or full `iter_query`; newest-first semantics, done properly |
| `governance/revocations.py` `active_revocations` | Full `iter_query` (a revocation set is small but unbounded in time), or `latest` per identity |
| `ledger/privacy.py` consents (L253), `erasures()` (L408), `coverage_gaps` (L445) | `iter_query` |
| `governance/roles.py` L439, 550, 557, 568 | `iter_query`, or `latest` per delegation |
| `ledger/receipts.py` L468 | `iter_query` |
| `metrics/economics.py` L322, 359 | `iter_query`, with a coverage envelope when window-scoped |
| `router/routing.py` L338 | `iter_query` over **dispatched** calls (see WP-05.6) |
| `engine/reporting.py` L168 | `iter_query` |
| `server.py` L1078, 2600, 2766, 2890 | `iter_query` or `latest` according to use |

Find the complete list with `grep -rnE "\.query\(" core/meridian_core --include=*.py` and review each hit. The 25 sites above are the known minimum.

- **Tests (each fails on the baseline first):**
  1. `test_merge_gate_halt_after_1000_rows`: write 1,001 approve-gate rows, then a halt. `check` must refuse the merge.
  2. `test_approval_after_1000_rows_visible`: the merge is allowed when the approval is the 1,001st.
  3. `test_revocation_after_1000_rows`: 1,000 unrelated revocations, then revoke X. Approval by X must be refused.
  4. `test_erasure_after_1000_rows_replays_on_restore`: 1,001 erasures, back up, restore. The 1,001st subject stays erased.
  5. `test_consent_after_1000_rows`.
  6. `test_dependency_ratio_full_history`.
- **Guard:** `core/tests/test_no_unpaginated_ledger_reads.py`. This AST test fails if any non-test module calls `ledger.query(` outside the allow-listed UI helpers, or passes `limit` ≥ 1,000 without iterating. The allow-list lives in the test with a justification per entry.

### WP-01.3 — Performance at scale
- Add perf tests over a 50,000-row ledger for `check` (merge gate), `active_revocations`, and backup-restore erasure replay. Budgets:
  - merge check ≤ 50 ms p95;
  - revocation lookup ≤ 10 ms p95;
  - replay ≤ 5 s for 50,000 rows.
- **Done when:** tests 1–6 pass, the guard test passes with its mutation check (re-introduce one capped read and see the guard fail), and the perf numbers are recorded.

---

## WP-02 — Authority and RPC boundary validation (P1)

### WP-02.1 — Derive authority from the host, never from request data (CLD-B04)
- **Files:** `core/meridian_core/orchestra_handlers.py` (L517, L616, L761–765, L799–805, L866–884), `extension/src/**` host wrappers, `governance/roles.py`, `governance/approvals*`.
- **Design:**
  1. The extension host already knows the authenticated editor user (the host identity used by gates and approvals). Every privileged request carries a **host-signed request context** `{principal, role, nonce, ts}`, signed with the per-session key established at `initialize`. Only the host holds the key, and the webview never sees it.
  2. The sidecar verifies the context, then resolves the role from `roles.py` policy.
  3. Remove the request fields `humanOverride`, `actorIsHuman`, `humanApproved`, `approvals`, `testsPassed`, `scansPassed`, `incumbentScore` and `candidateScore` as authority inputs:
     - approvals are looked up in the ledger (bound to action, subject, digest, expiry and principal);
     - test and scan results come from recorded run evidence;
     - scores come from recorded evaluation runs (WP-05.7).
- **Tests (negative first):** for each of the 8 fields, send a forged value from a non-privileged context and assert no state change and a named refusal. Replay a signed context with an old nonce and assert it is refused.
- **Done when:** a grep for these field names in handler parameter reads returns only the legitimate evidence lookups.

### WP-02.2 — Validate every request and response against `methods.json` (CLD-B05)
- **Files:** `core/meridian_core/server.py` dispatch, `shared/schema/methods.json`, and the generated types.
- **Steps:**
  1. Compile all 116 request and result schemas once at startup, lazily per method (jsonschema `Draft202012Validator`, or `fastjsonschema` if performance requires).
  2. Validate the request before the handler: failure → `-32602` with the path of the first error, redacted.
  3. Validate the result after the handler in debug/test mode, and **always in CI**: failure → a test failure. In production, log the failure and return `-32603`.
  4. Reject NaN/Infinity; negative budgets are rejected by schema (`minimum: 0`).
- **Tests:**
  - A parametrised test over all 116 methods sends a minimal valid request and asserts the result validates.
  - Per method, one mutated request (wrong type) must be refused.
- **Done when:** the parametrised test covers 116/116 methods (assert the count).

### WP-02.3 — Named refusals for unknown ids (CLD-B02, partial)
- `loop_stop`, `loop_resume`, `loop_replay` and `loop_status` with an unknown id → `OrchestraError("unknown loop")`. **No ledger write.**
- **Test:** unknown-id `stop` leaves the ledger length unchanged.

---

## WP-03 — Sidecar egress and environment hygiene (P0 — do this first; it is two days of work)

**Why:** CLD-C01.

### WP-03.1 — Scrub and pin the sidecar environment
- **File:** `extension/src/stdio-client.ts` (L125–126, the spawn), plus the Python sidecar entry point.
- **Steps:**
  1. Build the child environment from an allow-list (`PATH`, `SYSTEMROOT`, `TEMP`/`TMP`, `HOME`/`USERPROFILE`, `LANG`/`LC_*`, proxy variables only if the user opted in, `PYTHON*` only as needed) instead of spreading `process.env`.
  2. Set explicitly:
     ```
     LANGCHAIN_TRACING_V2=false
     LANGSMITH_TRACING=false
     LANGCHAIN_TRACING=false
     LANGCHAIN_API_KEY=
     LANGSMITH_API_KEY=
     LANGSMITH_ENDPOINT=
     LANGCHAIN_ENDPOINT=
     ```
  3. In Python, at the top of `meridian_core/__main__`/`server`, before importing langgraph, repeat the defensive settings in `os.environ`, so the headless CLI is covered too.
- **Tests:**
  1. Unit: the spawn environment contains no `LANGSMITH_*`/`LANGCHAIN_*`/`LANGGRAPH_*` key other than the forced-off values.
  2. Egress (Python): start a local HTTP listener. Set `LANGSMITH_TRACING=true`, `LANGSMITH_ENDPOINT=http://127.0.0.1:<port>` and `LANGSMITH_API_KEY=x`. Run `loop.start` over the headless path. Assert **zero** requests reached the listener. Negative control: remove the scrub and see ≥ 1 request, *if* the installed langgraph traces. Record the result either way; the test must be meaningful, not vacuous.

### WP-03.2 — Extend the no-telemetry guard to Python
- **Files:** `scripts/check-telemetry*.mjs`, plus a new `core/tests/test_no_egress.py`.
- **Steps:**
  1. Add a runtime egress test: monkeypatch `socket.socket.connect` / `socket.create_connection` during a representative RPC session covering every method family. Fail on any non-loopback connection that is not an explicitly configured export or witness.
  2. Add an import scan listing every third-party module the sidecar imports at runtime. Any module on a network/telemetry deny-list (`langsmith`, `sentry_sdk`, `posthog`, …) must be justified in an allow-list with a reason.
- **Done when:** the egress test passes, and `SECURITY-AND-DATA.md` "what leaves the machine" cites it.

---

## WP-04 — Packaged runtime resources (P1)

**Why:** CLD-A06.

- **Files:** `scripts/package*.mjs`, `extension/.vscodeignore`, `core/meridian_core/orchestra_handlers.py` (`adapter_roots`), the policy loaders, and `scripts/validate-package.mjs`.
- **Steps:**
  1. Create one `resources.py` with `resource_root()`. It resolves a source checkout (`<repo>/adapters`, `<repo>/policy`) or a packaged layout (`extension/sidecar/adapters`, `extension/policy`) using a marker file written at package time (`sidecar/RESOURCES.json` listing the roots and a digest).
  2. The packaging step copies `adapters/*/adapter.yaml`, the `agent.py` stand-ins (until WP-05) and the learned folders into the VSIX. Exclude runtime state.
  3. Every loader uses `resource_root()`.
  4. `validate-package.mjs` extracts the VSIX into a temporary directory, starts the packaged sidecar with **that** directory as the only source, and calls:
     - `adapter.list` (must return 14);
     - a policy-dependent method (for example `gate.evaluate` with a policy that denies);
     - `loop.start` (must return `simulated`/`not_bound` until WP-05).
- **Test (negative):** delete the roster from the extracted package → the validator fails naming the missing resource.
- **Done when:** `validate-package` passes on all three OSes in CI.

---

## WP-05 — Real Orchestra execution through governed ACP (P0 for Launch B)

**Why:** CLD-A01, A02, A03, A04, D07, G02. This is the largest package. Do not start it before WP-01, WP-02 and WP-06.1 are done.

### WP-05.1 — Truthful states first (can land immediately)
- `loop.start` with the stand-in path returns `status: "simulated"` plus `simulation: true`, never `completed`.
- `trainer.train` returns `status: "not_implemented"` until WP-05.7.
- `adapter.unplug` for a live session returns `retired: false, reason: "session active"` until WP-05.5.
- Update `core/tests/test_orchestra_rpc.py` and the other stand-in assertions (CLD-D07) to assert the new truthful states.
- The GUI shows a "Simulation" badge on these runs.

### WP-05.2 — One execution service (host side)
- **Files:** a new `extension/src/execution/service.ts`. Refactor `workbench/service.ts` and `adapters/launch.ts` to use it.
- **Interface:**
  ```ts
  dispatch(job: {
    runId, nodeId, agentRef, prompt, worktree, permissions, budget, timeoutMs
  }): Promise<{
    status: 'succeeded' | 'failed' | 'refused' | 'cancelled' | 'timeout',
    diffRef?, transcriptRef, usage, evidenceRefs[]
  }>
  ```
- **Responsibilities:** admit the agent (identity, tier, permission policy) and bind an ACP session through the existing host. Mediate permissions, stream updates to the ledger, enforce budget and timeout, and cancel cleanly (kill the process tree).
- **Tests:** a fake ACP agent covers succeed, fail, permission-denied, over-budget, timeout and cancel. Each ends in the matching state with ledger evidence.

### WP-05.3 — Per-run worktree isolation (FR-M40)
- **Files:** `core/meridian_core/worktree/*`, and the host execution service.
- **Behaviour:**
  1. Each run gets `git worktree add` on a run branch under a managed directory.
  2. The agent's cwd and all file permissions are scoped to it.
  3. On success, produce a diff. On failure or cancel, remove the worktree.
  4. Merge only through the gate (WP-05.4).
- **Tests:** two concurrent runs never see each other's files. A crash leaves no orphaned worktree after the next start (cleanup sweep). A path outside the worktree is refused.

### WP-05.4 — Loop nodes call the execution service
- **Files:** `core/meridian_core/runtime/*`, `orchestra_handlers.py`, and the JSON-RPC notification path from sidecar to host.
- **Design:**
  1. Real nodes are `dispatch` requests the sidecar sends **to the host** (reverse RPC `host.dispatch`), awaited asynchronously (depends on WP-06.1).
  2. Node types: `plan`, `implement`, `test` (runs the project's test command in the worktree via the tool bus — WP-06.4), `review`, and `gate`.
  3. A loop is `completed` only if every node succeeded **and** the gate passed. `failed` otherwise, with the reason.
  4. The stand-in path remains available only as `mode: "simulation"`.
- **End-to-end test (the acceptance for CLD-A01):** a fixture repository with a failing test and a scripted fake ACP agent that writes a fix. Run the loop from the RPC entry point. Assert:
  - the worktree diff exists;
  - tests pass in the worktree;
  - the gate evaluated;
  - a signed bundle is produced;
  - `status` is `completed`.
- **Negative tests:**
  - the agent writes a wrong fix → tests fail → `failed`;
  - a halt is set → gate refuses → not merged;
  - budget of 0 → refused before dispatch;
  - no agent bound → `not_bound`.
- **Real-agent test (manual/nightly):** the same task with a real ACP agent (for example Claude Code via ACP) on a nightly runner with credentials from CI secrets. It is recorded, never run in the PR tier.

### WP-05.5 — Unify the registries (GP-013)
- There must be one roster: the 14 Python adapter manifests and the 22 host Markdown profiles are reconciled into one schema, with the host as the execution authority and the sidecar as metadata and lifecycle.
- `unplug` stops the live session through the execution service.

### WP-05.6 — Router dispatch states (CLD-A03)
- Separate the `model_call_authorised`, `model_call_dispatched` and `model_call_completed` actions (a migration aliases the old `model_call` rows as `authorised`).
- The dependency ratio counts dispatched/completed only, via `iter_query`.

### WP-05.7 — Real learning jobs (CLD-A04)
- `trainer.train`: collect signals (existing), generate candidate prompt/skill variants, evaluate them on a pinned task set through WP-05.4 in simulation-free mode, and persist the scores as ledger evidence.
- `trainer.promote` reads those recorded scores and a WP-02.1 human approval. It accepts no scores from the request.
- **Tests:**
  - promotion without evaluation evidence → refused;
  - forged scores → ignored;
  - the evaluation run is recorded and reproducible.

### WP-05.8 — Done when
The CLD-A01 acceptance test passes. Every stand-in success assertion is gone (grep `"completed"` in `test_orchestra*`, each hit justified). The GUI runs a real loop visibly (WP-12.2). The nightly real-agent run is green 3 nights in a row.

---

## WP-06 — Runtime control, concurrency and durability (P1)

### WP-06.1 — Asynchronous dispatch with cancellation (CLD-E02, B02)
- **File:** `core/meridian_core/server.py` `serve()`.
- **Design:**
  1. A reader thread parses frames. Control methods (`ping`, `health`, `$/cancel`, `loop.stop`, `loop.status`) run inline.
  2. Long methods run on a bounded worker pool, and each gets a cancellation token.
  3. `$/cancel` sets the token, and handlers check it at safe points.
  4. Subprocess work registers its process tree so it can be killed.
- **Tests:**
  - `loop.stop` during a 30-s node returns within 500 ms, and the node's child process tree is gone.
  - `ping` stays under 100 ms while a long export runs.
  - A second `stop` is idempotent.
  - `health.activeLoops` is accurate.

### WP-06.2 — Durable continuation (CLD-B03)
- Persist a run descriptor with every checkpoint: node bindings (agent reference, worktree path, permissions), gate position, usage-to-date and cursor.
- On restart, `loop.resume` rebuilds real nodes from the descriptor, not from stand-ins.
- **Test:** kill the sidecar (SIGKILL / `taskkill /F`) mid-`implement`, restart and resume. The node re-dispatches exactly once (an idempotency key checked in the ledger), and there are no duplicate diffs or ledger entries.

### WP-06.3 — Queue durability (GP-010)
- Persist every queue transition (`waiting → admitted → running → done|failed|cancelled`) in a single SQLite transaction.
- **Test:** crash at each transition point and recover exactly-once.

### WP-06.4 — Usable, bounded tool bus (CLD-B06)
- **Files:** `core/meridian_core/tools/surface.py` and the permission population from policy.
- **Steps:**
  1. Populate permitted tools from the run's policy and role.
  2. Stream output with a hard memory cap: keep the head and tail buffers, count the dropped bytes, and record the truncation in evidence.
  3. On timeout, kill the process group (POSIX `killpg`; Windows Job Object or `taskkill /T /F`).
- **Tests:**
  - A permitted `read → edit → test` sequence succeeds.
  - A 1 GB output flood stays under 64 MB RSS growth.
  - A grandchild process is gone after the timeout, on all three OSes.

---

## WP-07 — Containment or honest labelling (P1)

**Why:** CLD-C03.

- **Minimum (required for Launch A):**
  1. A permission prompt and a `SECURITY-AND-DATA.md` section titled "What Meridian does not contain". Agents run with your user's privileges. Meridian records and gates; it does not sandbox.
  2. The same sentence goes in the Marketplace listing.
  3. A test asserts the sentence exists in all three places (the claims gate).
- **Target (Launch B):** platform containment for Orchestra-dispatched processes.
  - **Windows:** Job Object with a kill-on-close and process limit; optional AppContainer is out of scope.
  - **Linux:** `bwrap` (if present) with the worktree bind-mounted read-write and the network namespace off unless the policy allows it.
  - **macOS:** a `sandbox-exec` profile (deprecated but functional) or documented "uncontained".
  - Detect capability at runtime and record the containment level in the evidence bundle per run.
- **Tests:**
  - A contained run cannot write outside the worktree, or open a network socket when the policy denies it (Linux/macOS where available).
  - The recorded level is truthful.

---

## WP-08 — Provisioning, upgrade and operability (P0 for marketability)

### WP-08.1 — Private, managed runtime environment (CLD-F01)
- **Files:** `extension/src/interpreter.ts`, a new `extension/src/provision/*`, `core/requirements.lock` (from WP-10.1), and the docs.
- **Design (recommended; owner confirms as OD-4):**
  1. The extension owns a private environment under `context.globalStorageUri/runtime/<version>/`.
  2. **Preferred path:** `uv` bundled per platform (single static binary, about 15 MB) → `uv python install 3.12` (managed CPython) → `uv pip sync requirements.lock --require-hashes`.
  3. **Fallback:** if the user sets `meridian.python.path`, create a `venv` from that interpreter and `pip install --require-hashes -r requirements.lock` into it. Never install into the base interpreter.
  4. **Offline:** support `meridian.provision.wheelhouse` (a folder or zip of wheels per platform, which the release pipeline produces in WP-10), plus the proxy and index-URL settings.
  5. Show progress and a cancel button. Failures show the exact step and a copyable log.
  6. The runtime digest is recorded, and `doctor` verifies it.
  7. Remove the "run this pip command" instruction from the product.
- **Tests:**
  - Unit: plan generation per OS; a hash mismatch refuses.
  - CI integration on a clean runner image **without Python on PATH** on each OS: install the VSIX → provision → `initialize`.
  - Offline: with no network plus a wheelhouse → provisioning succeeds.
- **Done when:** a clean machine with no Python reaches a working sidecar in one action, in under 3 minutes on a broadband connection (recorded).

### WP-08.2 — One upgrade and rollback story (CLD-F03)
- Decide the semantics as OD-5. Recommended: **forward-only migrations, with an automatic pre-migration backup, and rollback = restore that backup with the older version**.
- Implement the automatic backup (existing backup feature) before any migration, and record it.
- Rewrite `DEPLOYMENT.md` §9 (and fix the duplicate §9/§10 numbering) and `SUPPORT.md` to say exactly that.
- **Tests:**
  - A fixture ledger created by release N-1 (commit the fixture produced by the previous tag) → open with N → migrated, verified, and the backup exists.
  - Restore the backup with N-1 (in CI, install the N-1 sidecar from the tag) → it opens.
  - Replace `test_upgrade_path.py`'s constant assertion (CLD-D07).

### WP-08.3 — Support bundle and log levels (CLD-F05)
- Add `Meridian: Create support bundle` and `meridian support-bundle`. The bundle contains:
  - versions of the extension, sidecar, VS Code and OS;
  - the `doctor` output;
  - the last N MB of logs;
  - settings (redacted);
  - environment variable **names only**;
  - ledger stats (counts, not content).
  It is written as a zip the user chooses where to save.
- Add a `meridian.log.level` setting passed to the sidecar.
- **Test:** the bundle is redacted against the full adversarial secret corpus (reuse the existing fixtures). The test fails if any fixture secret appears.

### WP-08.4 — Workspace trust and remote
- `untrustedWorkspaces: false` stays. Verify behaviour in the real-editor tests (WP-09.3).
- For SSH, WSL and containers, declare `extensionKind: ["workspace"]` (confirm) and test in WP-14.

---

## WP-09 — Quality tooling and test architecture (P1)

### WP-09.1 — Static analysis (CLD-D06)
- **Python:**
  - Add `ruff` (lint and format) with a rule set including `E,F,W,I,B,UP,S,SIM,RUF` and the `S` security rules.
  - Add `mypy`: strict for new modules and a baseline for existing ones. Store the baseline in `core/mypy-baseline.txt`; CI fails if it grows.
- **TypeScript:** ESLint flat config with `typescript-eslint` type-aware rules (`no-floating-promises`, `no-misused-promises`, `no-unused-vars`, `import/no-cycle`), plus Prettier.
- CI job `lint` gates PRs.
- **Done when:** the baseline counts are recorded and the CI job is green.

### WP-09.2 — Coverage (CLD-D04)
- `pytest-cov` (branch) plus vitest `coverage.provider: v8` for the extension and webview.
- Publish the reports as CI artefacts. Set floors at the first measured value minus 1 %, and ratchet them upward in each release.
- Security and integrity modules (`ledger/`, `governance/`, `portability/`, `redact`) get a floor of ≥ 90 % branch coverage.

### WP-09.3 — Real-editor tests (CLD-D05)
- Add `@vscode/test-cli` plus `@vscode/test-electron`, with a `extension/test-e2e/` suite that runs against the **built VSIX** installed into a fresh `--user-data-dir` and `--extensions-dir`.
- **Scenarios:**
  1. activate;
  2. provisioning (WP-08.1) or a pre-provisioned runtime in the PR tier;
  3. one RPC per tier;
  4. open the workbench webview and assert CSP no-violation (listen for `securitypolicyviolation`);
  5. commands registered;
  6. untrusted workspace → restricted;
  7. uninstall leaves no processes.
- **Matrix:** minimum supported VS Code (from `engines.vscode`) and stable, on Windows, macOS and Linux (xvfb).

### WP-09.4 — The claims gate consumes results (CLD-D04, H04)
- `check-claims.mjs` reads `test-results/*.xml` (WP-00.3) and fails any `shipped` claim whose bound test is missing from the results **or did not pass**.

### WP-09.5 — Test tiers and speed (CLD-D09)
- Tiers:
  - **PR** (under 10 min): unit tests plus fast integration.
  - **Merge/nightly:** full suite plus `@e2e` plus real-editor.
  - **Weekly:** perf, soak slice and real-agent nightly (WP-05.4).
- Speed-ups: session-scoped git-fixture templates copied per test, and the shared warm sidecar (WP-00.2).
- Target: core under 15 min with `-n auto` on CI runners (record it).

### WP-09.6 — Golden corpus and parity (CLD-D10)
- Add ≥ 10 golden stories: greenfield, brownfield, rework, cancellation, crash-resume, halt, revocation-after-1000, erasure-restore, multi-agent attribution, and export-verify.
- Parity sends write methods in simulation and compares full payloads, not just top-level keys, with a normaliser for timestamps and ids.

### WP-09.7 — Rust verifier (CLD-D11)
- Decide as OD-6: ship or drop.
- If shipped, add a CI job (`cargo test`, `cargo clippy -D warnings`) plus a cross-verifier test: bundles produced by Python verify under Rust and under the stdlib verifier.

### WP-09.8 — Security testing in CI (CLD-C06)
- CodeQL (Python, JS/TS) or Semgrep.
- Secret scanning: gitleaks on the full history once, then on PRs.
- `npm audit --omit=dev --audit-level=high` and `pip-audit -r requirements.lock`, with exceptions in `security/exceptions.yml` (owner, expiry).
- Dependabot/Renovate configured for both ecosystems.

---

## WP-10 — Supply chain, versioning, signing, release (P1)

### WP-10.1 — Hash-locked closure (CLD-J02)
- Generate `core/requirements.lock` with `uv pip compile --generate-hashes --python-version 3.11` and a per-platform-marker-aware lock. CI verifies it is up to date.
- The provisioning (WP-08.1) and CI use it exclusively.

### WP-10.2 — Complete SBOM and notices (CLD-J01)
- Generate a CycloneDX SBOM (Python via `cyclonedx-py` from the lock; Node via `@cyclonedx/cyclonedx-npm --omit dev`) and merge it with the existing AI-BOM.
- Generate `THIRD-PARTY-NOTICES.md` from the SBOM, including licence texts. Correct its "every component that ships" sentence to "every component shipped or installed by Meridian's provisioning".
- A licence policy check fails on unknown or strong-copyleft licences, and requires recorded review for weak-copyleft (MPL-2.0: `certifi`, `orjson`).

### WP-10.3 — One version everywhere (CLD-F04)
- `scripts/release/version.mjs` stamps the version into `extension/package.json`, `core/pyproject.toml`, `webview/package.json` and the `BUILD_STATE` header.
- A CI check fails on mismatch.

### WP-10.4 — Split the monoliths (CLD-E04)
- Move `server.py` handlers by domain into `meridian_core/handlers/<domain>.py`, registered through a table. Do this mechanically, one domain per commit, with the suite green after each.
- Split `methods.json` per domain, with generated aggregation (the generated output stays byte-identical, and a test asserts it).
- Split `workbench/service.ts` by responsibility (dispatch → WP-05.2; package import; UI state).

### WP-10.5 — Signing, provenance and artefact hygiene (CLD-J03, J04)
- Remove `dist/*.vsix` from git (`git rm --cached`), keep the `.gitignore` entry, and add a CI check that no `*.vsix` is tracked.
- Release workflow on tag:
  1. Build on clean runners.
  2. Produce the VSIX, SBOM, notices, checksums, wheelhouses per platform (WP-08.1) and the `uv` binaries.
  3. `actions/attest-build-provenance` (SLSA).
  4. Sigstore `cosign sign-blob` for the VSIX and SBOM.
  5. Upload as release assets.
- Marketplace: a verified publisher (after OD-3 and OD-7).

### WP-10.6 — Release process executed (CLD-L02)
- Introduce a `release/*` branch model:
  - `main` is protected: PRs only, required checks = all CI jobs, required review ≥ 1.
  - Work continues on feature branches off `main`.
  - `dev_local` merges once via PR after WP-00.
- Execute `mvp-impl-plan.md` §13 for `v0.2.0-rc.1`, and record each step in §7.

---

## WP-11 — Documentation and status truth (P1)

### WP-11.1 — Generated status (CLD-H01)
- Replace the hand-written status in `BUILD_STATE.md` with a generated block from `scripts/status.mjs`, containing:
  - the last full-suite `summary.json` (SHA, date, per-phase counts);
  - open findings by severity (parsed from this file's §7 table);
  - gate states G1–G11.
- Remove "ALL PHASES ENGINEERING-COMPLETE" and similar sentences.
- A CI check fails if the committed block differs from the generated one.

### WP-11.2 — One requirements tree and one register (CLD-H02, H03, L03)
- Keep `docs/spec/` as the canonical requirements.
- Delete the 10 root duplicates (leave redirects in the README index). Move `md files/` to an `archive/` branch or a tag, not `main`.
- Move `status.md` (966 KB) and `KIMI_MASTER_PROMPT.md` out of the product tree into an archive tag or an internal-notes repository.
- `BUILD-OPTIMIZATION-REPORT.md` → `docs/internal/`.
- Deduplicate `adapters/*/learned/README.md` into one template generated at runtime (or leave a single root README).
- Update `mvp-req-final.md` §3.1 / §5, `post-mvp-plan.md` §2 and `docs/claims.md` from evidence, with each status line linking to a test or a baseline.
- Freeze `audit-1-gp-*` and `audit-1-k-*`: add a header "Superseded by audit-1-cld-g-impl.md §6 mapping", with no further edits.

### WP-11.3 — Customer-facing documentation (CLD-A05, K06)
- The root `README.md` becomes a short project README for the repository. The customer page is `extension/README.md` (the Marketplace listing).
- Remove "self-improving" and any claim not in the §7-truthful list of the req file.
- Create a docs site (static, generated from `docs/`) with Getting started, Concepts (ledger, attribution, gates), Security and data, Administration (deployment, upgrade, backup), Troubleshooting (support bundle), and a Compliance mapping.
- Fix the `DEPLOYMENT.md` duplicate §9/§10 and the rollback contradiction (WP-08.2).

### WP-11.4 — Identity consistency (CLD-C05)
- One canonical organisation and repository in `SECURITY.md`, the manifest (`repository`, `bugs`, `homepage`), README badges and the docs.
- A link-check CI job covers all Markdown.

---

## WP-12 — GUI completeness and onboarding (P1)

### WP-12.1 — Shell surfaces (CLD-G01)
For each shell below, either implement the specified workflow against the production RPC or hide it behind a `preview` flag that shows a "Preview — not yet functional" banner. The catalogue test asserts every visible surface either is flagged or has ≥ 1 workflow test that exercises a real RPC round-trip (against the sidecar test harness, not a mock).

| Surface | File | Specified workflow (spec reference) |
|---|---|---|
| Modeling studio | `modeling/ModelingStudio.tsx` (20 lines) | M39 modelling entry: choose model → open diagram/code map/diff |
| Repositories | `governance/Repositories.tsx` (24) | M22 multi-repository registry: list, add, per-repository policy |
| Replay studio | `modeling/ReplayStudio.tsx` (29) | FR-M24 replay: pick run → step through ledger with diffs |
| Comprehension | `modeling/ComprehensionStudio.tsx` (34) | M38: architecture summary, entry points, risk hotspots |
| Delivery evidence | `governance/DeliveryEvidence.tsx` (38) | Bundle browser: list, verify, export |
| Diff studio | `modeling/DiffStudio.tsx` (43) | Attributed diff with the three-state marks |
| Code map | `modeling/CodeMapStudio.tsx` (45) | Tree-sitter map with ownership overlay |
| Diagram studio | `modeling/DiagramStudio.tsx` (62) | Loop and diagram editing. **Remove the stale L51 "not implemented" notice now** |

- Add a test that cross-checks every "not implemented"/"unavailable" string in the webview against the method registry, and fails if the method exists.

### WP-12.2 — Orchestra run view (with WP-05)
- A live view of a real loop: nodes, current agent, worktree diff, test results, gate decision and cost. The stop button calls WP-06.1 cancellation. The "Simulation" badge shows for simulated runs.

### WP-12.3 — Onboarding walkthrough (CLD-G03)
- `contributes.walkthroughs`:
  1. provision the runtime (WP-08.1);
  2. choose tiers;
  3. bind an agent (detect installed ACP agents);
  4. make a first agent change and see its provenance;
  5. export and verify a bundle with the standalone verifier.
- Each step has a completion event.
- A sample repository (`meridian-loom-sample`) supports the demo.

---

## WP-13 — Missing competitive modules (P2; order by OD-8)

Implement in accordance with `post-mvp-plan.md` CP2–CP4 and `jit-impl.md` J1–J2. Each module must prove its function at its **real control boundary**:

| Module | Minimum viable scope | Acceptance test at the boundary |
|---|---|---|
| **M47 harness provenance** | Record harness (agent CLI, version, config digest, model id as reported) per session in the ledger and bundle | A bundle's harness fields match the actual launched agent; a tampered config digest fails verification |
| **M48 tool-call governance** | Observer path: record each tool call from ACP permission requests with lineage. The gateway half waits on D48 | Every permission request in an ACP session appears with its decision; a denied call leaves no side effect |
| **M49 attested identity** | Bind approver identity to an OS or SSO credential (for example Git commit signing key, or SSH/GPG, or OIDC via VS Code auth provider), not git config name | An approval from an unattested identity is labelled as such; policy can require attested identities; forged name refused |
| **M50 standards envelopes** | Complete DSSE/in-toto output | Verified by the upstream `in-toto` / `cosign verify-blob` tool in CI (AC-68) |
| **M51 longitudinal outcomes** | 30/60/90-day follow-up records (reverts, incident links, churn) bound to the merge decision | A reverted change's outcome record links to its original gate decision |

---

## WP-14 — Performance, soak, resilience, platform matrix (P1)

**Why:** CLD-E01, E03, D08, F02.

1. **Cold start:** the WP-00.4 test becomes a gate at ≤ 2 s p95 (reference runner defined in `docs/baselines/`).
2. **Perf gates in CI:** remove report-only mode from the CI perf job. The budgets come from NFR-01…27, plus WP-01.3.
3. **Soak (R6.4):** 168 h on a dedicated machine with the existing harness, driving a synthetic workload (ingest, attribution, gate checks, exports) at recorded rates. Pass criteria: no crash, RSS growth under 10 %, ledger verifies at the end, and no handle leak. Record under `docs/baselines/soak/`.
4. **Resilience (R1.7):** the 20 rehearsals (kill -9 mid-write, disk full, power loss simulation via VM snapshot, corrupted WAL, clock skew, network loss during export) on Windows, macOS, Linux and one remote (WSL or SSH). Record each.
5. **Compatibility (R1.6):** for each published row (OS × VS Code version × Python version × remote), a real run of the real-editor suite (WP-09.3). Remove unverified rows from the published matrix.

- **Done when:** baselines are committed, each bound to the release SHA and VSIX digest.

---

## WP-15 — Accessibility and localisation

### WP-15.1 — Accessibility (CLD-G05, P1)
- Add automated `axe-core` checks per surface in the webview tests (WCAG 2.1 AA rules) and keyboard-trap tests.
- Run the 6 recorded human sessions in `docs/baselines/assistive/PROTOCOL.md` (NVDA on Windows, VoiceOver on macOS; launch, review, export).
- Produce an ACR (VPAT 2.5 INT edition) for the shipped surfaces.

### WP-15.2 — Localisation readiness (CLD-G04, P2)
- Externalise extension strings (`package.nls.json` plus `vscode.l10n.t`) and webview strings (a small i18n module with message catalogues).
- A pseudo-locale test (`[!! Ŧęşŧ !!]`) proves no string is hard-coded on the covered surfaces.
- Translations follow OD-9.

---

## WP-16 — Commercial, legal and go-to-market pack (P0 decisions; owner-led)

Engineering work in this package waits on the owner decisions in §3. The agent prepares drafts and mechanisms but must not publish.

| Task | Closes | Deliverable |
|---|---|---|
| 16.1 Licence decision implemented | CLD-K01 | After OD-1: `LICENSE`, file headers where required, manifest `license`, notices, README section. Keep the repository private until done |
| 16.2 Entitlements | CLD-K02 | After OD-2: a signed offline licence file (Ed25519, reusing the existing crypto), verified at activation and on tier change, with a grace period, no phone-home, and paid tiers absent without entitlement (G5). Tests: tampered, expired and wrong-product licences are all refused |
| 16.3 Legal documents | CLD-K03 | Drafts for legal review: EULA/ToS, privacy policy ("no collection" stated precisely, with the WP-03.2 test as evidence), DPA template, sub-processor statement, export-control note (Ed25519/AES-GCM; likely EAR 5D992 / mass-market — counsel to confirm), AI acceptable-use policy |
| 16.4 Trust pack | CLD-K07 | `trust/` generated per release: SBOM, notices, data-flow diagram, security architecture, control mapping (ISO/IEC 24970, EU AI Act Art. 12/26, SSDF, ISO 42001 — supporting evidence, not certification), pen-test summary, ACR, vulnerability SLA, pre-filled CAIQ-Lite/SIG-Lite answers |
| 16.5 Listing and demo | CLD-K06 | Marketplace README with screenshots (from `docs/gui/`, retaken on the release build), a 2–3 min video, pricing/trial, links, a Q&A decision, and category review |
| 16.6 Positioning | CLD-K08, A05 | A positioning one-pager built only from req §7 claimable items: "Verifiable governance for AI-written code — know which agent wrote what, prove who approved it, verify it without us." Competitive notes against Ink, DX/Atlassian and agent gateways |
| 16.7 Commercial operations | CLD-K09 | Pricing model, trial terms, support tiers and SLA, design-partner agreement template, an opt-in feedback command (no telemetry) |
| 16.8 Engineering process | CLD-L01 | Branch protection, CODEOWNERS, PR template requiring finding IDs plus failing-first evidence, and a single integrator per WP |
| 16.9 External pen test | CLD-C06 | Scope: the extension host, sidecar RPC, webview, package import, bundle verification and provisioning. Findings tracked in this register |

---

## 3. Owner decisions required

| ID | Decision | Options | Recommendation | Blocks |
|---|---|---|---|---|
| **OD-1** | Licence | Proprietary EULA · open core (Apache-2.0 core plus commercial modules) · source-available (BSL/FSL) · AGPL plus commercial | **Open core or source-available**, with legal advice. The ledger format and verifier stay open (it strengthens the "verify without us" claim); Governor enforcement and Orchestra are commercial. **Do not publish under MIT until decided**, because MIT publication is irreversible for that code | WP-16.1, any publication |
| **OD-2** | Tier and entitlement model | Per-seat · per-repository · per-organisation; offline licence file | Per-seat with an offline signed licence; Flight Recorder free | WP-16.2 |
| **OD-3** | Legal entity and brand | — | Name the contracting entity; run a trademark search for "Meridian Loom" in target markets | WP-10.5, WP-16 |
| **OD-4** | Runtime provisioning | Managed `uv` runtime · bundled CPython per platform · user interpreter (current) | Managed `uv` runtime plus an offline wheelhouse (WP-08.1) | WP-08.1 |
| **OD-5** | Upgrade semantics | Forward-only plus automatic backup · bidirectional | Forward-only plus automatic backup; rollback = restore | WP-08.2 |
| **OD-6** | Rust verifier | Ship (CI-tested) · drop | Keep the stdlib Python verifier as the canonical one; ship Rust only if CI-tested | WP-09.7 |
| **OD-7** | Canonical repository and organisation | `Vibe-A-Thon/meridianloom` · `meridianloom/meridian-loom` | One org owned by the entity (OD-3) | WP-11.4 |
| **OD-8** | Post-launch module order | M49 · M48 · M47 · M51 | M49 (identity) first — the weakest point against competitors for regulated buyers; then M48 observer path | WP-13 |
| **OD-9** | Languages | English only · plus target markets | English at launch with l10n-ready strings | WP-15.2 |
| **OD-10** | Launch scope | Launch A only · A then B | **Launch A** (governance and evidence) to design partners first; Launch B after WP-05 and pilot evidence | Marketing copy |

---

## 4. Definitions of done

- **"Production ready" (Launch A)**
  - G1–G8 green on one frozen, tagged commit.
  - Every finding at P0/P1 in dimensions B, C, D, E, F, H and J is closed in §7 with evidence.
  - Dimension A items are closed **or** the Orchestra is hidden or labelled "Simulation / preview" in the product and all copy.
- **"Fully functional"**
  - Every surface is either working end to end (a test round-trips a real RPC) or labelled as preview.
  - No endpoint reports success for work it did not do (grep-audited).
- **"Thoroughly tested"**
  - G1 plus G5.
  - Every security/integrity guard has a negative control.
  - Real-editor, packaged-artefact, perf, soak, resilience and assistive evidence are recorded.
- **"Marketable"**
  - G9 and G10 are met.
  - Copy is limited to req §7 claimable rows.
  - The trust pack is published with the release.
  - At least one design-partner pilot is running with the evidence protocol.
- **"Automates development" (Launch B)**
  - G11.
  - The pilot or MV5 study has reported, and copy states the measured result, whatever it is.

---

## 5. External evidence plan (people, time, infrastructure)

| Evidence | Who | Duration | Produces | Blocks |
|---|---|---|---|---|
| 168-hour soak | Dedicated machine (can be a cloud VM) | 7 days plus analysis | `docs/baselines/soak/` | G6 |
| Resilience ×20 | Engineer plus VMs on 3 OSes plus WSL/SSH | 1–2 weeks | `docs/baselines/resilience/` | G6 |
| Cold-start / first-value | 5 people new to the product | 1 week | `docs/baselines/cold-start/`, `first-value/` | G10, NFR-28 |
| Assistive runs | A screen-reader user (NVDA and VoiceOver) | 2–3 days | `docs/baselines/assistive/`, ACR | G10 |
| Pen test | External firm | 2–3 weeks | Report, with fixes tracked here | G10, trust pack |
| Design-partner pilot / MV5 | 1–3 IT-services companies, one team each | 8 weeks | `docs/baselines/evidence-gate/` | G10, any outcome claim |
| SCM-side enforcement (D37) | A pilot's platform team | During pilot | A GitHub/GitLab required-check integration using the verifier | "cannot be bypassed" claim |
| Legal review | Counsel | 2–4 weeks | OD-1, EULA, DPA, export note | G9 |

---

## 6. Mapping of the earlier audits' items

### 6.1 GPT (`audit-1-gp-g-*.md`)

| GP | → WP | | GP | → WP |
|---|---|---|---|---|
| 001 | WP-11.2 | | 022 | WP-12.1 |
| 002 | WP-00.1 | | 023 | WP-09.6 |
| 003–004 | Verify in §7 (tests from `7d20faa`); extend to the host `packages.ts` path (WP-02 tests) | | 024 | WP-09.6 |
| 005 | WP-02.1 | | 025 | WP-00, WP-09 |
| 006 | WP-02.2 | | 026 | WP-09.3 |
| 007 | WP-05.1, 05.4 | | 027 | WP-14.5 |
| 008 | WP-06.1, WP-02.3 | | 028 | WP-14 |
| 009 | WP-06.2 | | 029 | WP-15.1 |
| 010 | WP-06.3 | | 030 | WP-08.2 |
| 011 | WP-05.2 | | 031 | WP-04 |
| 012 | WP-06.4 | | 032 | WP-10.1, 10.2 |
| 013 | WP-05.5 | | 033 | §5 (D37) |
| 014 | WP-05.4 (context assembly through governed memory, GP-T014) | | 034 | Post-launch connectors; reads only (security constraint) |
| 015 | WP-05.4 (levers shape real dispatch, GP-T015) | | 035 | WP-13 (M47) |
| 016 | WP-05.7 | | 036 | WP-13 |
| 017 | WP-05.4 (persist decisions as ledger events, GP-T017) | | 037 | WP-11 |
| 018 | WP-02.2 (interface contracts validated) | | 038 | OD-1, OD-2, WP-16 |
| 019 | Post-Launch-A: tenant routing end to end (GP-T019) | | 039–041 | Covered by the GP plan's own tasks; re-verify after WP-00 |
| 020 | WP-06.4, WP-07 | | | |
| 021 | WP-01, WP-05.6 | | | |

### 6.2 Kimi (`audit-1-k-g-*.md`)

| Kimi | → WP |
|---|---|
| GAP-001 / TD-001 Orchestra stand-ins | WP-05 (severity raised to P0 for Launch B) |
| GAP-101 artefact | WP-04, WP-10.5 |
| GAP-102 host consumers | WP-05.2, WP-12.2 |
| GAP-103 / FR-M26-04 cost levers | WP-05.4 |
| TD-010 model-comparison harness (FR-M26-05) | WP-05.7 (evaluation harness) |
| TD-011 contribution attribution (FR-M13-06) | WP-05.4 follow-on |
| TD-012, TD-018 full suite not run | WP-00.3, WP-09.5 |
| MKT-001…006 | WP-16, OD-1, OD-2 |

---

## 7. Progress and evidence log (the living register)

Update **only** by appending evidence: commit SHA, test names, CI run URL and the date. A row's status changes to `closed` only with evidence in the same row.

| Finding | Sev | WP | Status | Evidence (SHA · test · CI run · date) |
|---|---|---|---|---|
| CLD-A01 | P0 | 05 | open | |
| CLD-A02 | P0 | 05.2 | open | |
| CLD-A03 | P1 | 05.6, 01 | open | |
| CLD-A04 | P1 | 05.7 | open | |
| CLD-A05 | P1 | 11.3 | open | |
| CLD-A06 | P1 | 04 | open | |
| CLD-A07 | P2 | 13 | open | |
| CLD-B01 | P0 | 01 | open | |
| CLD-B02 | P1 | 02.3, 06.1 | open | |
| CLD-B03 | P1 | 06.2, 06.3 | open | |
| CLD-B04 | P1 | 02.1 | open | |
| CLD-B05 | P1 | 02.2 | open | |
| CLD-B06 | P1 | 06.4 | open | |
| CLD-C01 | P0 | 03 | open | |
| CLD-C02 | P0 | 01 | open | |
| CLD-C03 | P1 | 07 | open | |
| CLD-C04 | P2 | 02 tests | open | |
| CLD-C05 | P2 | 11.4 | open | |
| CLD-C06 | P2 | 09.8, 16.9 | open | |
| CLD-D01 | P0 | 00.2 | open | |
| CLD-D02 | P0 | 00.1 | open | |
| CLD-D03 | P1 | 00.3 | open | |
| CLD-D04 | P1 | 09.2, 09.4 | open | |
| CLD-D05 | P1 | 09.3 | open | |
| CLD-D06 | P1 | 09.1 | open | |
| CLD-D07 | P1 | 05.1, 08.2 | open | |
| CLD-D08 | P1 | 14 | open | |
| CLD-D09 | P2 | 09.5 | open | |
| CLD-D10 | P2 | 09.6 | open | |
| CLD-D11 | P2 | 09.7 | open | |
| CLD-D12 | P1 | §5 | open | |
| CLD-E01 | P1 | 00.4, 14 | open | |
| CLD-E02 | P1 | 06.1 | open | |
| CLD-E03 | P1 | 14 | open | |
| CLD-E04 | P2 | 10.4 | open | |
| CLD-E05 | P2 | 01.1, 01.3 | open | |
| CLD-F01 | P0 | 08.1 | open | |
| CLD-F02 | P1 | 14.5 | open | |
| CLD-F03 | P1 | 08.2, 11.3 | open | |
| CLD-F04 | P2 | 10.3, 10.5 | open | |
| CLD-F05 | P2 | 08.3 | open | |
| CLD-G01 | P1 | 12.1 | open | |
| CLD-G02 | P1 | 05, 12.2 | open | |
| CLD-G03 | P2 | 12.3 | open | |
| CLD-G04 | P2 | 15.2 | open | |
| CLD-G05 | P1 | 15.1 | open | |
| CLD-H01 | P1 | 11.1 | open | |
| CLD-H02 | P2 | 11.2 | open | |
| CLD-H03 | P2 | 11.2 | open | |
| CLD-H04 | P2 | 09.4 | open | |
| CLD-I01 | P1 | 14, §5 | open | |
| CLD-I02 | P1 | 05, 06, 13 | open | |
| CLD-I03 | P1 | §5 | open | |
| CLD-J01 | P1 | 10.2 | open | |
| CLD-J02 | P1 | 10.1 | open | |
| CLD-J03 | P2 | 10.5 | open | |
| CLD-J04 | P2 | 10.5 | open | |
| CLD-K01 | P0 | OD-1, 16.1 | open — decision | |
| CLD-K02 | P0 | OD-2, 16.2 | open — decision | |
| CLD-K03 | P1 | 16.3 | open | |
| CLD-K04 | P1 | §5 | open — external | |
| CLD-K05 | P1 | OD-3 | open — decision | |
| CLD-K06 | P1 | 16.5 | open | |
| CLD-K07 | P1 | 16.4 | open | |
| CLD-K08 | P1 | 16.6, OD-10 | open | |
| CLD-K09 | P2 | 16.7 | open | |
| CLD-L01 | P1 | 16.8, 10.6 | open | |
| CLD-L02 | P2 | 10.6 | open | |
| CLD-L03 | P2 | 11.2 | open | |

**Estimated effort** (one experienced engineer-equivalent, excluding external waits). The ranges are wide because WP-05 depends on the ACP agents' behaviour.

| Work package | Effort |
|---|---|
| WP-00 | 1–2 weeks |
| WP-01 | 1 week |
| WP-02 | 1–2 weeks |
| WP-03 | 2–3 days |
| WP-04 | 3–4 days |
| WP-06 | 2–3 weeks |
| WP-08 | 2–3 weeks |
| WP-09 | 2 weeks |
| WP-10 | 1–2 weeks |
| WP-11 | 1 week |
| WP-12 | 2–4 weeks |
| WP-15 | 1–2 weeks |
| WP-16 engineering | 1–2 weeks |
| **Launch A total** | **roughly 4–6 months** of focused engineering, running in parallel with the 8-week pilot |
| WP-05 (Launch B) | 6–10 weeks additional |
| WP-13 | 2–3 months additional |
