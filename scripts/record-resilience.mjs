/**
 * Record a resilience rehearsal — `MVP-R1.7`, `FR-M46-07`, `NFR-42`
 * (MV4-T02).
 *
 * `core/tests/test_resilience.py` is the rehearsal. This runs it and writes
 * what happened to `docs/baselines/resilience/`, because the plan asks for
 * **one recorded run per failure per configuration** and a green suite in
 * somebody's terminal is not a record.
 *
 * Four configurations are required: Windows, macOS, Linux and one remote.
 * One machine closes one of them. The baseline names the platform it ran on
 * for exactly that reason — a directory of four files from the same laptop
 * would look complete and prove one quarter of what it claims.
 *
 * Usage: node scripts/record-resilience.mjs [--label <name>]
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASELINES = path.join(root, 'docs', 'baselines', 'resilience');

/** The five failures the plan enumerates, and where each is exercised. */
const FAILURES = [
  ['upgrade-interrupted-mid-write', 'tests/test_resilience.py::TestFailure1UpgradeInterruptedMidWrite'],
  ['disk-exhaustion-during-append', 'tests/test_resilience.py::TestFailure2DiskExhaustionDuringAppend'],
  // Failure 3 lives in its own file, against a real spawned sidecar and a
  // real kill. Referenced rather than duplicated: two tests of one property
  // drift, and the weaker one gets believed.
  ['sidecar-killed-mid-transaction', 'tests/test_ledger_durability.py::test_acked_append_survives_kill_minus_9'],
  ['corrupted-bundle-at-the-verifier', 'tests/test_resilience.py::TestFailure4CorruptedBundleAtTheVerifier'],
  ['restore-after-workspace-deletion', 'tests/test_resilience.py::TestFailure5RestoreAfterWorkspaceDeletion'],
];

function platformName() {
  return process.platform === 'win32'
    ? 'windows'
    : process.platform === 'darwin'
      ? 'macos'
      : 'linux';
}

function runOne(selector) {
  const started = Date.now();
  const result = spawnSync(
    process.platform === 'win32' ? 'python' : 'python3',
    ['-m', 'pytest', selector, '-q', '--no-header'],
    {
      cwd: path.join(root, 'core'),
      encoding: 'utf8',
      env: { ...process.env, MERIDIAN_ALLOW_CONCURRENT_SUITE: '1' },
    },
  );
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`;
  const summary = /^(\d+ passed.*|.*failed.*)$/m.exec(output.replace(/\[[0-9;]*m/g, ''));
  return {
    ok: result.status === 0,
    seconds: (Date.now() - started) / 1000,
    summary: summary ? summary[1].trim() : `exit ${result.status}`,
  };
}

const label = process.argv.includes('--label')
  ? process.argv[process.argv.indexOf('--label') + 1]
  : platformName();

const cases = [];
for (const [name, selector] of FAILURES) {
  process.stdout.write(`  ${name} … `);
  const outcome = runOne(selector);
  console.log(`${outcome.ok ? 'passed' : 'FAILED'} (${outcome.seconds.toFixed(1)}s) — ${outcome.summary}`);
  cases.push({ failure: name, selector, ...outcome });
}

const failed = cases.filter((entry) => !entry.ok);
const record = {
  recordedAt: new Date().toISOString(),
  configuration: label,
  host: {
    platform: platformName(),
    release: os.release(),
    arch: process.arch,
    node: process.version,
  },
  passCondition:
    'NFR-42: zero loss of acknowledged ledger entries, and recovery within ' +
    '15 minutes for the reference dataset. An acknowledged entry is one for ' +
    'which Ledger.append returned.',
  cases,
  verdict: failed.length === 0 ? 'passed' : 'failed',
  // What this run does NOT establish. A baseline directory that does not say
  // so reads as a completed rehearsal the moment somebody counts the files.
  scope:
    `One configuration of the four MV4-T02 requires (${label}). Windows, ` +
    'macOS, Linux and one remote configuration are each a separate rehearsal; ' +
    'this file closes one of them.',
};

mkdirSync(BASELINES, { recursive: true });
const target = path.join(
  BASELINES,
  `${new Date().toISOString().slice(0, 10)}-${label}.json`,
);
writeFileSync(target, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
console.log(
  `resilience: ${cases.length - failed.length}/${cases.length} failures rehearsed on ` +
    `${label}; recorded in ${path.relative(root, target)}`,
);
if (failed.length) {
  console.error(
    '  NFR-42/MK4: a lost acknowledged entry blocks the release. This is not a ' +
      'defect to triage.',
  );
}
process.exit(failed.length === 0 ? 0 : 1);
