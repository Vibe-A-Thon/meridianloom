import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extensionDir = path.join(root, 'extension');
const outDir = path.join(root, 'dist');
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';

// Ship the sidecar Python sources inside the VSIX at extension/sidecar/
// (see extension/src/layout.ts). FR-M3-05a / D4: we do NOT bundle a Python
// runtime — the interpreter comes from the workspace via the FR-M3-05
// resolution chain — so the package is intentionally platform-neutral: no
// --target flag, one universal VSIX. Platform-specific VSIX targets become
// mandatory only if a bundled runtime is ever shipped.
const sidecarDir = path.join(extensionDir, 'sidecar');
rmSync(sidecarDir, { recursive: true, force: true });
cpSync(path.join(root, 'core', 'meridian_core'), path.join(sidecarDir, 'meridian_core'), {
  recursive: true,
  filter: (source) => !source.includes('__pycache__'),
});
cpSync(path.join(root, 'core', 'pyproject.toml'), path.join(sidecarDir, 'pyproject.toml'));

try {
  // --no-dependencies: every dependency is a devDependency (the bundle is
  // self-contained), and without it vsce's dependency walk leaks npm
  // workspace-root files into the VSIX and fails.
  const result = spawnSync(npx, ['vsce', 'package', '--no-dependencies'], {
    cwd: extensionDir,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.error) {
    console.error(result.error);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
} finally {
  rmSync(sidecarDir, { recursive: true, force: true });
}

const vsix = readdirSync(extensionDir).filter((name) => name.endsWith('.vsix'));
if (vsix.length !== 1) {
  console.error(`expected exactly one .vsix in extension/, found: ${vsix.join(', ') || 'none'}`);
  process.exit(1);
}

if (!existsSync(outDir)) {
  mkdirSync(outDir, { recursive: true });
}
const target = path.join(outDir, vsix[0]);
renameSync(path.join(extensionDir, vsix[0]), target);
console.log(`VSIX written to ${target}`);
