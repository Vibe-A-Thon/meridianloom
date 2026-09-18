# Meridian Loom build optimization report

Recorded: 2026-09-18  
Branch: `dev_local`  
Recovered commit: `f3f5080` (`build changes`)  
Failed GitHub Actions run investigated: <https://github.com/Vibe-A-Thon/meridianloom/actions/runs/35259022891>

## Result

The failing CI path has been repaired and revalidated locally against the same job shapes used by `.github/workflows/verify.yml`.

The production package was rebuilt as:

- `dist/meridian-loom-0.1.0.vsix`
- SHA-256: `57244792eacf04ab9fb56e66b3fcb510e893e635e9208af47ddd00797d3b9a77`
- Package baseline: `docs/baselines/package/2026-09-18-windows.json`

The extension host and webview now build with protocol `v4`, matching the user-facing fix for:

> Webview protocol mismatch: host speaks v3, the webview requires v4.

## GitHub failure evidence

The GitHub CLI was installed but unauthenticated, so the complete log ZIP returned `403`. The public API still exposed the run metadata, job conclusions, and check annotations.

Run `35259022891` failed on commit `c9166ff` in workflow `verify`:

- `contracts, documents and types`: passed.
- `extension and webview (ubuntu-latest)`: failed in the `extension` step; later webview/support checks were skipped.
- `python core (ubuntu-latest)`: failed in the `core suite` step.
- `performance budgets`: skipped on `dev_local`, as expected.
- `build and package`: skipped because the required jobs failed.

The public annotations only reported generic exit-code failures plus Node 20 action deprecation warnings. The concrete failures were reproduced locally.

## Root causes fixed

1. Several extension tests had valid asynchronous work that could exceed Vitest's default 5-second timeout under load. The tests now use explicit 10-second budgets where the behavior under test depends on async persistence or subprocess-style workbench cleanup.

2. Cassette replay/recording joined blob references onto a root path before normalizing the reference. This left a path traversal/vector policy gap and failed the blob reference guard. Blob references are now normalized before all record/replay path joins.

3. The MCP stdio client spawned child processes without the sidecar child-environment policy. It now passes `child_environment()`, preventing Meridian secrets and unrelated process state from leaking to child tools.

4. Tool-runner tests invoked nested pytest processes while the parent suite held the Meridian global suite lock. Fixture-input pytest runs are now recognized as test data, not independent Meridian suites, and tool-runner children also strip `PYTEST_*` variables for deterministic nested behavior.

5. Direct git subprocess calls bypassed the central git execution policy. Collector and comprehension git calls now go through `run_git_command()`, so git runs with timeout, closed stdin, prompting disabled, deterministic output, and sanitized environment. Collector identity probing also treats `GitTimeout` as a best-effort fallback to a directory digest.

## Files changed in recovered commit

- `core/meridian_core/collector.py`
- `core/meridian_core/comprehension/__init__.py`
- `core/meridian_core/engine/runners.py`
- `core/meridian_core/replay/__init__.py`
- `core/meridian_core/tools/mcp_client.py`
- `core/tests/conftest.py`
- `extension/test/workbench.test.ts`
- `extension/test/workbench-integrations.test.ts`
- `docs/baselines/package/2026-09-18-windows.json`

## Validation performed

| Check | Result |
| --- | --- |
| `npm ci` | Passed. Runtime audit clean; dev audit still reports toolchain-only findings. |
| `npm run check:contracts` | Passed. |
| `npm run check:surface` | Passed: 74/80 registry methods have interface consumers; 16 declared unsurfaced. |
| `node scripts/check-mvp-traceability.mjs` | Passed. |
| `node scripts/check-claims.mjs` | Passed: 118 claims, 95 backed by tests, 21 limitations, 2 withdrawn. |
| `node scripts/check-licences.mjs` | Passed: 14 runtime dependencies resolved, none copyleft. |
| `node scripts/check-compatibility.mjs` | Passed: 7 rows backed by tests and deployment docs current. |
| `npx tsc --noEmit -p extension` | Passed. |
| `npx tsc --noEmit -p webview` | Passed. |
| Full extension tests | Passed: 55 files, 613 passed, 1 skipped, about 50 seconds. |
| Full webview tests | Passed: 37 files, 358 passed, about 46 seconds. |
| Full CI-shaped core suite | Passed: 2,185 tests in 1:00:14 with `MERIDIAN_ALLOW_CONCURRENT_SUITE=1` and `MERIDIAN_PERF_REPORT_ONLY=1`. |
| `npm run build` | Passed; host and webview both report protocol `v4`. |
| `npm run package` | Passed; VSIX, checksum, notices, and BOM generated. |
| `npm run check:demo` | Passed: 18 `DEMO.md` steps backed by package contents. |
| `npm run check:bom` | Passed: 54 components, all digests match the VSIX. |
| `npm run check:notices` | Passed. |
| `node scripts/validate-package.mjs --record` | Passed: all 12 package checks; baseline recorded. |
| `npm audit --omit=dev` | Passed: 0 production/runtime npm vulnerabilities. |

## Remaining risks and follow-up

1. Dev dependency audit findings remain in the local test/build toolchain: `vitest`, `vite`, and `esbuild`. `npm audit fix --force` would install breaking versions, so this should be handled as a planned toolchain migration with full test coverage rather than as an automatic CI hotfix.

2. GitHub Actions emitted Node 20 action deprecation warnings for official setup/checkout/upload actions. This is not the failing condition, but the workflow should be reviewed when newer action majors are available.

3. Local validation used Windows Node `26.8.2` / npm `11.19.1` and Python `3.11.9`; CI uses Node `22` and Python `3.12`. The repo now passes the workflow-shaped tests locally, but the repaired branch should still be allowed to run on GitHub's Ubuntu runners for final platform confirmation.

4. Webview tests still emit React `act(...)` warnings and one DOM nesting warning in normal unsuppressed output. They are not current blockers, but they should be cleaned up before a polished public marketplace launch.

5. The demo package check verifies that the VSIX carries the assets required by `DEMO.md`; it does not replace a human walk-through on a clean VS Code machine.

6. At the time this report was written, `core/meridian_core/ledger/schema.py` had an unrelated uncommitted schema migration draft in the working tree. It was not part of the recovered CI commit and was left untouched.
