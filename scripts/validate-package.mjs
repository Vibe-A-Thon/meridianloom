/**
 * Validate the installed package, not the checkout — `MP7` (MV4-T03).
 *
 * A rehearsal in the development checkout proves the checkout works. What an
 * organisation installs is the VSIX, and the two have differed in this
 * repository before: a screen that never reached the bundle, an integrity
 * check tree-shaken away, a nested `extension/extension/` with 37 duplicate
 * files. So every check here runs **the shipped copy**: the sidecar, the CLI
 * and the verifier are extracted from the VSIX and executed from there.
 *
 * The plan's list, each as a step with a verdict:
 *
 *  - the checksum matches the published `.sha256`;
 *  - there is no nested `extension/extension/` in the package, and nothing
 *    is tracked under it in git;
 *  - the evaluator documents are staged inside the package;
 *  - the packaged `cli doctor` passes an intact workspace **and exits
 *    non-zero on an induced failure** — an altered ledger entry;
 *  - a bundle exported by the packaged CLI verifies with the packaged
 *    `verify.py`, and a tampered copy of it does not;
 *  - the packaged `cli evidence-gate` prints the digest a study registers,
 *    scores a study with that registration reported intact, and writes a
 *    ledger slice the packaged verifier accepts (MV5);
 *  - the packaged `cli compare-evidence` passes two bundles of one shape and
 *    fails an altered one (AC-50);
 *  - the shipped agent library is byte-identical to its source and not empty.
 *
 * What it does not do: open VS Code. Seeding the library into a workspace on
 * first open is an editor action, and the cold-start rehearsal (`MV4-T04`) is
 * where a person watches it happen.
 *
 * Usage: node scripts/validate-package.mjs [path/to.vsix] [--record]
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findVsix, openZip } from './lib/vsix.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASELINES = path.join(root, 'docs', 'baselines', 'package');
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';
const SEED_HEX = '22'.repeat(32);

const STAGED_DOCUMENTS = [
  'SECURITY-AND-DATA.md',
  'DEPLOYMENT.md',
  'SUPPORT.md',
  'SECURITY.md',
  'THIRD-PARTY-NOTICES.md',
  'evidence-portability.md',
  'meridian-ledger-trailer.md',
];

/**
 * The environment every packaged process runs under: its own sidecar on the
 * path, and no `MERIDIAN_*` variable inherited from whoever runs this. A check
 * that passes because the developer happened to export a signing key would be
 * checking the developer's shell, not the package (SEC-27's rule, applied to
 * the harness too).
 */
function packagedEnvironment(sidecarDir) {
  const environment = { PYTHONPATH: sidecarDir, PYTHONUTF8: '1' };
  for (const [key, value] of Object.entries(process.env)) {
    if (!key.startsWith('MERIDIAN_') && key !== 'PYTHONPATH') environment[key] = value;
  }
  return environment;
}

function runPython(sidecarDir, args, cwd) {
  return spawnSync(PYTHON, args, {
    cwd: cwd ?? sidecarDir,
    env: packagedEnvironment(sidecarDir),
    encoding: 'utf8',
    timeout: 180_000,
    windowsHide: true,
  });
}

function filesUnder(directory, base = directory) {
  const found = [];
  for (const name of readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, name.name);
    if (name.isDirectory()) found.push(...filesUnder(full, base));
    else found.push(path.relative(base, full).split(path.sep).join('/'));
  }
  return found;
}

const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');

export function validatePackage({ vsixPath } = {}) {
  const steps = [];
  const record = (step, ok, detail) => steps.push({ step, ok, detail });

  const vsix = findVsix(vsixPath);
  if (!vsix || !existsSync(vsix)) {
    record('package present', false, 'no VSIX in dist/. Run `npm run package` first.');
    return { ok: false, steps };
  }
  const archive = openZip(vsix);
  const names = archive.names;

  // -- the artefact itself --------------------------------------------------
  const checksumFile = `${vsix}.sha256`;
  if (!existsSync(checksumFile)) {
    record('checksum matches', false, `${path.basename(checksumFile)} is not published beside the package`);
  } else {
    const published = readFileSync(checksumFile, 'utf8').trim().split(/\s+/)[0];
    const actual = digest(readFileSync(vsix));
    record(
      'checksum matches',
      published === actual,
      published === actual ? `sha256 ${actual.slice(0, 16)}…` : `published ${published}, file is ${actual}`,
    );
  }

  const nested = names.filter((name) => name.startsWith('extension/extension/'));
  let tracked = '';
  try {
    tracked = execFileSync('git', ['ls-files', 'extension/extension'], {
      cwd: root,
      encoding: 'utf8',
    }).trim();
  } catch {
    tracked = '(git unavailable)';
  }
  record(
    'no nested extension/extension/',
    nested.length === 0 && tracked === '',
    nested.length
      ? `${nested.length} files under extension/extension/ in the package`
      : tracked
        ? `git tracks files under extension/extension/: ${tracked.split('\n').length}`
        : 'absent from the package and untracked in git',
  );

  const missingDocs = STAGED_DOCUMENTS.filter((name) => !names.includes(`extension/docs/${name}`));
  record(
    'evaluator documents staged',
    missingDocs.length === 0,
    missingDocs.length ? `missing: ${missingDocs.join(', ')}` : `${STAGED_DOCUMENTS.length} documents present`,
  );

  // -- the shipped sidecar, executed ---------------------------------------
  const scratch = mkdtempSync(path.join(os.tmpdir(), 'meridian-validate-'));
  const sidecarDir = path.join(scratch, 'sidecar');
  const extracted = archive.extract('extension/sidecar/', sidecarDir);
  if (extracted === 0 || !existsSync(path.join(sidecarDir, 'verify.py'))) {
    record('sidecar and verifier shipped', false, 'extension/sidecar/ or its verify.py is not in the package');
    return { ok: false, steps, vsix };
  }
  record('sidecar and verifier shipped', true, `${extracted} files extracted and run from the package copy`);

  const workspace = path.join(scratch, 'workspace');
  const keyFile = path.join(scratch, 'signing.key');
  writeFileSync(keyFile, SEED_HEX, 'utf8');

  // A ledger written by the packaged code, the way the sidecar writes one.
  const seed = runPython(sidecarDir, [
    '-c',
    [
      'import sys',
      'from pathlib import Path',
      'from meridian_core.ledger import Ledger',
      'from meridian_core.ledger import keys',
      `ws = Path(${JSON.stringify(workspace)})`,
      "(ws / '.meridian').mkdir(parents=True, exist_ok=True)",
      `ledger = Ledger(ws / '.meridian' / 'ledger', keys.ProvisionedSigningKeyProvider(bytes.fromhex('${SEED_HEX}')))`,
      'for i in range(1, 6):',
      "    ledger.append({'story_id': 'VALIDATE-1', 'phase': 'build', 'loop_id': 'L2-task', 'loop_iteration': 1, 'actor_id': 'developer-agent', 'actor_version': '1.0.0', 'actor_kind': 'role', 'policy_version': 'policy-v1', 'action_type': 'diff', 'ts_utc': '2026-09-01T00:00:%06dZ' % i})",
      'ledger.close()',
    ].join('\n'),
  ]);
  if (seed.status !== 0) {
    record('packaged ledger writes', false, (seed.stderr || seed.stdout).trim().split('\n').slice(-3).join(' | '));
    return { ok: false, steps, vsix };
  }
  record('packaged ledger writes', true, '5 entries appended by the shipped meridian_core');

  const doctor = () =>
    runPython(sidecarDir, [
      '-m',
      'meridian_core.cli',
      'doctor',
      '--workspace',
      workspace,
      '--signing-key-file',
      keyFile,
    ]);
  const ledgerStatus = (result) => {
    try {
      return JSON.parse(result.stdout).checks.find((check) => check.id === 'ledger')?.status;
    } catch {
      return undefined;
    }
  };

  // The control first: without it, the induced failure below could be doctor
  // failing for any reason at all.
  const healthy = doctor();
  record(
    'packaged doctor passes an intact workspace',
    healthy.status === 0 && ledgerStatus(healthy) === 'pass',
    `exit ${healthy.status}, ledger ${ledgerStatus(healthy) ?? 'unreported'}`,
  );

  const bundle = path.join(scratch, 'bundle.json');
  const exported = runPython(sidecarDir, [
    '-m',
    'meridian_core.cli',
    'export',
    '--workspace',
    workspace,
    '--out',
    bundle,
    '--signing-key-file',
    keyFile,
  ]);
  const verify = (file) => runPython(sidecarDir, [path.join(sidecarDir, 'verify.py'), file]);
  if (exported.status !== 0 || !existsSync(bundle)) {
    record('packaged verifier verifies a packaged export', false, `export exit ${exported.status}: ${exported.stderr.trim().split('\n').at(-1)}`);
  } else {
    const verified = verify(bundle);
    record(
      'packaged verifier verifies a packaged export',
      verified.status === 0,
      `verify.py exit ${verified.status}`,
    );
    const tampered = JSON.parse(readFileSync(bundle, 'utf8'));
    tampered.entries[1].actorId = 'somebody-else';
    const tamperedPath = path.join(scratch, 'tampered.json');
    writeFileSync(tamperedPath, JSON.stringify(tampered), 'utf8');
    const rejected = verify(tamperedPath);
    record(
      'packaged verifier rejects a tampered export',
      rejected.status !== 0,
      `verify.py exit ${rejected.status} on an altered entry`,
    );
  }

  // -- MV5: the evidence-gate scorer and the two-bundle comparison ---------
  // Packaging-sensitive in exactly the way MP7 means: three new modules and a
  // jsonschema import exist in the checkout whether or not they reached the
  // package. So both commands run from the extracted copy, before the ledger
  // is corrupted below.
  const cli = (...args) => runPython(sidecarDir, ['-m', 'meridian_core.cli', ...args]);
  let thresholdsDigest;
  try {
    thresholdsDigest = JSON.parse(cli('evidence-gate', '--print-preregistration').stdout).thresholdsDigest;
  } catch {
    thresholdsDigest = undefined;
  }
  const study = path.join(scratch, 'study.json');
  writeFileSync(
    study,
    JSON.stringify({
      studyId: 'package-validation',
      preregistration: {
        registeredAt: '2026-09-14T09:00:00Z',
        thresholdsDigest: thresholdsDigest ?? 'not printed',
      },
      allocation: [{ storyId: 'VALIDATE-1', arm: 'C', kind: 'greenfield' }],
    }),
    'utf8',
  );
  const gateOut = path.join(scratch, 'gate');
  const scored = cli(
    'evidence-gate',
    '--workspace',
    workspace,
    '--study',
    study,
    '--out',
    gateOut,
    '--signing-key-file',
    keyFile,
  );
  let gateReport;
  try {
    gateReport = JSON.parse(readFileSync(path.join(gateOut, 'evidence-gate-report.json'), 'utf8'));
  } catch {
    gateReport = undefined;
  }
  const slice = path.join(gateOut, 'ledger-slice.json');
  const sliceVerifies = existsSync(slice) && verify(slice).status === 0;
  record(
    'packaged evidence gate scores a study',
    scored.status === 0 &&
      gateReport?.preregistration?.state === 'intact' &&
      gateReport?.recommendation?.verdict === 'insufficient_evidence' &&
      existsSync(path.join(gateOut, 'DECISION-DRAFT.md')) &&
      sliceVerifies,
    scored.status === 0
      ? `outcome ${gateReport?.recommendation?.verdict ?? 'unreported'}, preregistration ${gateReport?.preregistration?.state ?? 'unreported'}, slice ${sliceVerifies ? 'verifies' : 'does not verify'}`
      : `exit ${scored.status}: ${(scored.stderr || scored.stdout).trim().split('\n').at(-1)}`,
  );

  if (existsSync(bundle) && existsSync(slice)) {
    const same = cli('compare-evidence', bundle, slice);
    const altered = JSON.parse(readFileSync(bundle, 'utf8'));
    altered.entries[0].actorId = 'somebody-else';
    const alteredPath = path.join(scratch, 'altered-for-comparison.json');
    writeFileSync(alteredPath, JSON.stringify(altered), 'utf8');
    const different = cli('compare-evidence', bundle, alteredPath);
    record(
      'packaged compare-evidence passes one shape and fails an altered bundle',
      same.status === 0 && different.status === 1,
      `two exports of one ledger exit ${same.status}; altered bundle exit ${different.status}`,
    );
  } else {
    record(
      'packaged compare-evidence passes one shape and fails an altered bundle',
      false,
      'no packaged export and ledger slice to compare',
    );
  }

  // The induced failure: one entry altered behind the ledger's back.
  const corrupt = runPython(sidecarDir, [
    '-c',
    [
      'import sqlite3',
      `c = sqlite3.connect(${JSON.stringify(path.join(workspace, '.meridian', 'ledger', 'ledger.db'))})`,
      "c.execute('DROP TRIGGER IF EXISTS ledger_entry_no_update')",
      "c.execute(\"UPDATE ledger_entry SET actor_id = 'somebody-else' WHERE seq = 3\")",
      'c.commit()',
      'c.close()',
    ].join('\n'),
  ]);
  const broken = doctor();
  record(
    'packaged doctor exits non-zero on an induced failure',
    corrupt.status === 0 && broken.status !== 0 && ledgerStatus(broken) === 'fail',
    `altered entry 3; doctor exit ${broken.status}, ledger ${ledgerStatus(broken) ?? 'unreported'}`,
  );

  // -- the library ----------------------------------------------------------
  const source = path.join(root, 'extension', 'library');
  const shipped = names
    .filter((name) => name.startsWith('extension/library/'))
    .map((name) => name.slice('extension/library/'.length))
    .sort();
  const onDisk = existsSync(source) ? filesUnder(source).sort() : [];
  const differing = shipped.filter(
    (name) =>
      !onDisk.includes(name) ||
      digest(archive.bytes(`extension/library/${name}`)) !== digest(readFileSync(path.join(source, name))),
  );
  const missingFromPackage = onDisk.filter((name) => !shipped.includes(name));
  const counts = ['agents', 'skills', 'instructions'].map(
    (kind) => `${shipped.filter((name) => name.startsWith(`${kind}/`)).length} ${kind}`,
  );
  const empty = ['agents/', 'skills/', 'instructions/'].some(
    (prefix) => !shipped.some((name) => name.startsWith(prefix)),
  );
  record(
    'shipped library matches its source',
    differing.length === 0 && missingFromPackage.length === 0 && !empty,
    differing.length || missingFromPackage.length
      ? `differs: ${[...differing, ...missingFromPackage].slice(0, 5).join(', ')}`
      : `${counts.join(', ')}, byte-identical to extension/library/`,
  );

  return { ok: steps.every((step) => step.ok), steps, vsix };
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const vsixArg = process.argv.slice(2).find((arg) => !arg.startsWith('--'));
  const result = validatePackage({ vsixPath: vsixArg });
  for (const step of result.steps) {
    console.log(`  ${step.ok ? 'ok  ' : 'FAIL'} ${step.step} — ${step.detail}`);
  }
  const failed = result.steps.filter((step) => !step.ok).length;
  console.log(
    failed
      ? `validate-package: ${failed} of ${result.steps.length} checks failed against the installed package.`
      : `validate-package: all ${result.steps.length} checks passed against ${path.basename(result.vsix)}, run from the package copy.`,
  );
  if (process.argv.includes('--record')) {
    const platform =
      process.platform === 'win32' ? 'windows' : process.platform === 'darwin' ? 'macos' : 'linux';
    mkdirSync(BASELINES, { recursive: true });
    const target = path.join(BASELINES, `${new Date().toISOString().slice(0, 10)}-${platform}.json`);
    writeFileSync(
      target,
      `${JSON.stringify({ recordedAt: new Date().toISOString(), platform, package: result.vsix ? path.basename(result.vsix) : null, steps: result.steps }, null, 2)}\n`,
      'utf8',
    );
    console.log(`  recorded in ${path.relative(root, target)}`);
  }
  process.exit(failed ? 1 : 0);
}
