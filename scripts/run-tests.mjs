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
