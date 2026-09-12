import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extensionDir = path.join(root, 'extension');
const outDir = path.join(root, 'dist');
const vsceCli = path.join(root, 'node_modules', '@vscode', 'vsce', 'vsce');
const licensePath = path.join(root, 'LICENSE');

// Only generated directories immediately inside this extension may be cleaned.
function cleanGeneratedDirectory(target) {
  const resolved = path.resolve(target);
  if (path.dirname(resolved) !== extensionDir || !['sidecar', 'webview-dist', 'policy', 'docs'].includes(path.basename(resolved))) {
    throw new Error(`Refusing to clean a non-generated directory: ${resolved}`);
  }
  rmSync(resolved, { recursive: true, force: true });
}

// A library-generation script was once run from the wrong working directory
// and wrote a second copy of the whole library to extension/extension/, which
// then got committed and shipped inside every VSIX unnoticed — it caused no
// runtime symptom, only silent bloat. vsce packages whatever it finds under
// extensionDir, so the one place that reliably catches a stray top-level
// directory before it ships is here, right before packaging runs.
const unexpectedTopLevel = readdirSync(extensionDir).filter(
  (name) => name === 'extension',
);
if (unexpectedTopLevel.length) {
  throw new Error(
    `extension/ contains a nested directory that should not exist: ${unexpectedTopLevel.join(', ')}. ` +
      'This has happened before from a generation script run with the wrong cwd; delete it rather than packaging it.',
  );
}

// Deleting the directory is not enough, and we know that because deleting it
// was not enough: the files stayed at HEAD and came back with the next
// checkout. A path that must never ship has to be absent from the index too,
// or the next clone re-creates it and the check above passes on a machine
// where the problem is already fixed.
const FORBIDDEN_PATHS = ['extension/extension'];
for (const forbidden of FORBIDDEN_PATHS) {
  const trackedUnder = execFileSync('git', ['ls-files', '--', forbidden], {
    cwd: root,
    encoding: 'utf8',
  })
    .split('\n')
    .filter((line) => line.trim().length > 0);
  if (trackedUnder.length) {
    throw new Error(
      `git tracks ${trackedUnder.length} file(s) under ${forbidden}, which must never ship. ` +
        `Deleting the working copy is not enough — the path is still in the index and will return on the next checkout. ` +
        `Run: git rm -r ${forbidden}`,
    );
  }
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

// FR-M36-06 / NFR-31 / SEC-29: the open reference verifier ships WITH the
// extension. The product's central claim is that an exported audit bundle
// verifies without Meridian installed, and that claim is only true for a user
// who actually has the verifier — shipping it in the repository and not in the
// package made the promise true for us and false for them. It is one file,
// Python standard library only (Ed25519 is a pure-Python RFC 8032
// implementation), so it costs 12 KB and adds no dependency: a user can hand
// verify.py and their bundle to an auditor who has never heard of this tool.
cpSync(
  path.join(root, 'verifier', 'verify.py'),
  path.join(sidecarDir, 'verify.py'),
);
// FR-M43-11: the reference parser for the `Meridian-Ledger:` trailer, and the
// specification it implements. The trailer is the pointer from a commit into
// the ledger, and the published claim (NFR-39, AC-49) is that a third party
// can go from `git log` to verified evidence with no Meridian installed. That
// is only true if the tool and the document they are told to use are actually
// in the package — the same way the verifier was true of the repository and
// false of the VSIX until someone checked.
cpSync(
  path.join(root, 'verifier', 'meridian_trailer.py'),
  path.join(sidecarDir, 'meridian_trailer.py'),
);
cpSync(
  path.join(root, 'docs', 'spec', 'meridian-ledger-trailer.md'),
  path.join(sidecarDir, 'meridian-ledger-trailer.md'),
);
// The documents an organisation's security review and platform team actually
// ask for. They ship inside the package because the package is what gets
// handed around: a VSIX sideloaded into an enterprise arrives without the
// repository, and "see the docs in our repo" is not an answer when the
// repository is private.
const evaluatorDocs = path.join(extensionDir, 'docs');
cleanGeneratedDirectory(evaluatorDocs);
mkdirSync(evaluatorDocs, { recursive: true });
for (const name of ['SECURITY-AND-DATA.md', 'DEPLOYMENT.md']) {
  cpSync(path.join(root, 'docs', name), path.join(evaluatorDocs, name));
}
cpSync(
  path.join(root, 'docs', 'spec', 'evidence-portability.md'),
  path.join(evaluatorDocs, 'evidence-portability.md'),
);
cpSync(
  path.join(root, 'docs', 'spec', 'meridian-ledger-trailer.md'),
  path.join(evaluatorDocs, 'meridian-ledger-trailer.md'),
);
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
  const result = spawnSync(process.execPath, [vsceCli, 'package', '--no-dependencies'], {
    cwd: extensionDir,
    stdio: 'inherit',
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
  cleanGeneratedDirectory(evaluatorDocs);
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

// A sideloaded VSIX is unsigned — VS Code does not sign them — so the only
// integrity check available to whoever receives it is a digest they can
// compare. docs/SECURITY-AND-DATA.md tells evaluators to do exactly that, so
// the build has to actually produce one: a document that instructs a reader
// to check something that was never published is worse than saying nothing.
const digest = createHash('sha256').update(readFileSync(target)).digest('hex');
const checksumFile = `${target}.sha256`;
writeFileSync(checksumFile, `${digest}  ${path.basename(target)}
`, 'utf8');

console.log(`VSIX written to ${target}`);
console.log(`SHA-256 ${digest}`);
console.log(`checksum written to ${checksumFile}`);
