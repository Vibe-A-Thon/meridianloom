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

let status = run(['test', '--workspace=extension']);
if (status !== 0) {
  process.exit(status);
}

// Python sidecar tests (core/). Python is a hard dependency of the product
// (FR-M3-05); if no interpreter is on PATH we warn rather than fail so an
// extension-only edit loop still works.
const python = process.platform === 'win32' ? 'python' : 'python3';
const pytest = spawnSync(python, ['-m', 'pytest', 'tests', '-q'], {
  cwd: path.join(root, 'core'),
  stdio: 'inherit',
});
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
