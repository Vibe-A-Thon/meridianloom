import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function run(args) {
  const result = spawnSync(npm, args, {
    cwd: root,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.error) {
    console.error(result.error);
  }
  return result.status ?? 1;
}

// FR-M32-09 (schema half): generated bus types must be fresh vs the schema
// before any test runs — a stale contract fails the suite, not CI later.
const contracts = spawnSync(process.execPath, ['scripts/generate-bus-types.mjs', '--check'], {
  cwd: root,
  stdio: 'inherit',
});
if (contracts.status !== 0) {
  process.exit(contracts.status ?? 1);
}

// FR-M46-01/02 + AC-43 (status.md G-02): the surface-coverage orphan gate.
// Enumerates the method registry (shared/schema/tiers.json), greps the
// webview + extension consumers for callers, and fails on an undeclared
// orphan or a `mustSurface: true` allowlist entry that still has no
// consumer (shared/schema/unsurfaced.json) — that second class is the
// blocking gate for the parallel GUI session surfacing the G-02 trust and
// spend instruments. The JSON report at .meridian/surface-coverage.json is
// the machine-readable surface the GUI session iterates on.
const surface = spawnSync(
  process.execPath,
  ['scripts/check-surface-coverage.mjs', '--json', '.meridian/surface-coverage.json'],
  { cwd: root, stdio: 'inherit' },
);
if (surface.status !== 0) {
  console.error(
    'surface-coverage gate failed (FR-M46-02, AC-43): undeclared orphan methods or ' +
      'pending mustSurface instruments. See shared/schema/unsurfaced.json and ' +
      '.meridian/surface-coverage.json.',
  );
  process.exit(surface.status ?? 1);
}

// MV0 gates. All three are cheap, all three guard a document rather than the
// code, and all three exist because a document drifted from the tree without
// anything noticing: a requirements file asserting a suite that was red, a
// README listing directories that were not there, and a security document
// asserting a dependency licence set nobody re-checked. They run before the
// suites so a drifted claim fails in seconds rather than after half an hour.
const documentGates = [
  ['scripts/check-mvp-traceability.mjs', 'MV0-T04: mvp-req-final.md and mvp-impl-plan.md disagree.'],
  ['scripts/check-claims.mjs', 'MV0-T03: a claim in docs/claims.md names a test that does not exist.'],
  ['scripts/check-licences.mjs', 'MV0-T05: a runtime dependency contradicts docs/SECURITY-AND-DATA.md §7.'],
  ['scripts/check-compatibility.mjs', 'MV1-T05/T06: the support matrix names a test that does not exist, or its published table has drifted.'],
  // MV4-T09/AC-70. The BOM's drift check needs a built VSIX and so lives in
  // the package job; this one only needs the licence sweep, so it runs every
  // time and catches a dependency added without regenerating the notices.
  ['scripts/generate-notices.mjs', 'MV4-T09: THIRD-PARTY-NOTICES.md no longer matches the runtime dependencies.', '--check'],
  // MV4-T05. Release notes are written last and read first, which is exactly
  // why they drift into marketing. This holds them against the limitations,
  // the disclaimed claims, the tier set and the decision record.
  ['scripts/check-release-notes.mjs', 'MV4-T05: the release notes disagree with the limitations, the decision record, or what the MVP does not claim.'],
];
for (const [script, message, ...extra] of documentGates) {
  const gate = spawnSync(process.execPath, [script, ...extra], { cwd: root, stdio: 'inherit' });
  if (gate.status !== 0) {
    console.error(message);
    process.exit(gate.status ?? 1);
  }
}

let status = run(['test', '--workspace=extension']);
if (status !== 0) {
  process.exit(status);
}

// Python sidecar tests (core/). Python is a hard dependency of the product
// (FR-M3-05); if no interpreter is on PATH we warn rather than fail so an
// extension-only edit loop still works.
const python = process.platform === 'win32' ? 'python' : 'python3';
// -n auto: a serial run of this suite is about an hour and three quarters,
// because most of it spawns real git and sidecar subprocesses. A suite nobody
// waits for is a suite nobody runs, which is how every stale claim in this
// repository happened. Workers are separate processes with separate tmp dirs,
// so the parallelism is isolated by construction. Budgets are excluded here
// and measured serially by `npm run test:budgets` — a timing taken under
// parallel load is the noise that made NFR-33 read PASS while failing.
const pytest = spawnSync(
  python,
  ['-m', 'pytest', 'tests', '-q', '-m', 'not perf', '-n', 'auto'],
  {
    cwd: path.join(root, 'core'),
    stdio: 'inherit',
    env: { ...process.env, MERIDIAN_PERF_REPORT_ONLY: '1' },
  },
);
if (pytest.error && pytest.error.code === 'ENOENT') {
  console.warn(`WARNING: '${python}' not found; skipping core/ pytest suite.`);
} else if (pytest.status !== 0) {
  process.exit(pytest.status ?? 1);
}

if (existsSync(path.join(root, 'webview', 'package.json'))) {
  status = run(['test', '--workspace=webview']);
  if (status !== 0) {
    process.exit(status);
  }
} else {
  console.log('webview workspace not present yet; skipping webview tests.');
}
