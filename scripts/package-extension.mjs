import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extensionDir = path.join(root, 'extension');
const outDir = path.join(root, 'dist');
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';

// Only generated directories immediately inside this extension may be cleaned.
function cleanGeneratedDirectory(target) {
  const resolved = path.resolve(target);
  if (path.dirname(resolved) !== extensionDir || !['sidecar', 'webview-dist', 'policy'].includes(path.basename(resolved))) {
    throw new Error(`Refusing to clean a non-generated directory: ${resolved}`);
  }
  rmSync(resolved, { recursive: true, force: true });
}

// Ship the sidecar Python sources inside the VSIX at extension/sidecar/
// (see extension/src/layout.ts). FR-M3-05a / D4: we do NOT bundle a Python
// runtime — the interpreter comes from the workspace via the FR-M3-05
// resolution chain — so the package is intentionally platform-neutral: no
// --target flag, one universal VSIX. Platform-specific VSIX targets become
// mandatory only if a bundled runtime is ever shipped.
const sidecarDir = path.join(extensionDir, 'sidecar');
cleanGeneratedDirectory(sidecarDir);
cpSync(path.join(root, 'core', 'meridian_core'), path.join(sidecarDir, 'meridian_core'), {
  recursive: true,
  filter: (source) => !source.includes('__pycache__'),
});
cpSync(path.join(root, 'core', 'pyproject.toml'), path.join(sidecarDir, 'pyproject.toml'));
// The generated bus types ship beside the sidecar sources; meridian_core's
// sys.path shim finds them at <sidecar>/shared/py (FR-M32-09).
cpSync(path.join(root, 'shared', 'py'), path.join(sidecarDir, 'shared', 'py'), {
  recursive: true,
  filter: (source) => !source.includes('__pycache__'),
});

// The recorder dashboard webview ships as its built bundle at
// <extension>/webview-dist (VIGUIX_Final §17: the panel serves every
// resource from this directory through asWebviewUri). Building here keeps
// the VSIX self-contained; development checkouts read ../webview/dist
// directly (see extension/src/recorder-panel.ts).
const webviewDist = path.join(extensionDir, 'webview-dist');
cleanGeneratedDirectory(webviewDist);
const webviewBuild = spawnSync(
  process.platform === 'win32' ? 'npm.cmd' : 'npm',
  ['run', 'build', '--workspace=webview'],
  { cwd: root, stdio: 'inherit', shell: process.platform === 'win32' },
);
if (webviewBuild.status !== 0) {
  process.exit(webviewBuild.status ?? 1);
}
cpSync(path.join(root, 'webview', 'dist'), webviewDist, { recursive: true });

// The ACP host loads this conservative floor unless the workspace overrides it.
// D43/AC-53 (N0-T09b): the sidecar bootstrap also treats <extension>/policy as
// the shipped-default source for ALL seven sidecar-loaded packs (governance,
// action-classes, roles, pricing, stories, rework-reasons, licenses) — every
// *.yaml in the repository policy/ directory ships, so a fresh workspace gets
// the full uniform scaffold, not a half-inert Governor.
const policyDir = path.join(extensionDir, 'policy');
cleanGeneratedDirectory(policyDir);
mkdirSync(policyDir);
for (const name of readdirSync(path.join(root, 'policy')).filter((n) => n.endsWith('.yaml'))) {
  cpSync(path.join(root, 'policy', name), path.join(policyDir, name));
}

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
  cleanGeneratedDirectory(sidecarDir);
  cleanGeneratedDirectory(policyDir);
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
