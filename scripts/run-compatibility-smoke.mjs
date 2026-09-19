/**
 * Run the smoke tests the support matrix claims — `MVP-R1.6`, `FR-M46-06`,
 * `MK5` (MV4-T01).
 *
 * `check-compatibility.mjs` asserts that every published row **names** a test
 * that exists. That is a real check and it is not this one: a row can name a
 * test that exists and has not been run since the claim was made.
 *
 * This runs them, and records where they ran.
 *
 * ## The part that makes it honest
 *
 * Running `stdio-e2e.test.ts` on Windows does not tell you anything about
 * macOS, and a runner that ticked the macOS row because its named test passed
 * here would be manufacturing the evidence the matrix exists to hold. So a
 * row is only **verified** when the machine running it is the thing the row
 * claims:
 *
 *  - an `os` row is verified only on that operating system;
 *  - a `python` row only under that interpreter version;
 *  - an `editor` row is platform-independent and is verified anywhere.
 *
 * Everything else comes back `not-verified-here`, which is neither a pass nor
 * a failure. It is the reason this has to run on the CI matrix to close the
 * whole table, and the reason one developer machine can never close it alone.
 *
 * `MK5`: a row whose test **fails** is a row to remove from the matrix, not
 * to mark degraded. This reports it; removing it is a decision with a
 * disposition, not something a script should do silently.
 *
 * Usage:
 *   node scripts/run-compatibility-smoke.mjs            run and report
 *   node scripts/run-compatibility-smoke.mjs --record   also write a baseline
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MATRIX = path.join(root, 'shared', 'schema', 'compatibility.json');
const BASELINES = path.join(root, 'docs', 'baselines', 'compatibility');

/** What this machine is, in the matrix's own vocabulary. */
function hostFacts() {
  const platform =
    process.platform === 'win32'
      ? 'windows'
      : process.platform === 'darwin'
        ? 'macos'
        : 'linux';
  let python;
  for (const exe of ['python', 'python3']) {
    try {
      python = execFileSync(exe, ['-c', 'import sys;print("%d.%d"%sys.version_info[:2])'], {
        encoding: 'utf8',
      }).trim();
      break;
    } catch {
      /* try the next interpreter */
    }
  }
  return { platform, release: os.release(), python, node: process.version };
}

/**
 * Does this machine satisfy what the row claims?
 *
 * Returns `undefined` when it does, or the reason it does not. The reason is
 * the useful half: "not verified here" with no explanation invites somebody
 * to assume it was close enough.
 */
function unmetBy(row, facts) {
  if (row.dimension === 'os') {
    const wanted = row.id.startsWith('windows')
      ? 'windows'
      : row.id.startsWith('macos')
        ? 'macos'
        : row.id.startsWith('linux')
          ? 'linux'
          : undefined;
    if (!wanted) return `the row id '${row.id}' does not name an operating system this can recognise`;
    if (wanted !== facts.platform) {
      return `this row claims ${wanted}; these tests ran on ${facts.platform}`;
    }
    return undefined;
  }
  if (row.dimension === 'python') {
    const wanted = /(\d+\.\d+)/.exec(row.id)?.[1];
    if (!wanted) return `the row id '${row.id}' does not name a Python version`;
    if (!facts.python) return 'no Python interpreter was found on this machine';
    if (facts.python !== wanted) {
      return `this row claims Python ${wanted}; the interpreter here is ${facts.python}`;
    }
    return undefined;
  }
  // `editor` and anything else: the claim is about the manifest or the
  // declared surface, which does not vary by host.
  return undefined;
}

/** `path/to.test.ts` or `path/to.test.ts > a test name`. */
function parseReference(reference) {
  const [file, name] = reference.split(' > ');
  return { file: file.trim(), name: name?.trim() };
}

function runVitest(file, name) {
  const workspace = file.startsWith('extension/')
    ? 'extension'
    : file.startsWith('webview/')
      ? 'webview'
      : undefined;
  if (!workspace) return { ok: false, detail: `cannot tell which workspace runs ${file}` };
  const relative = file.slice(workspace.length + 1);
  const args = ['vitest', 'run', relative];
  if (name) args.push('-t', name);
  const result = spawnSync('npx', args, {
    cwd: path.join(root, workspace),
    encoding: 'utf8',
    shell: process.platform === 'win32',
    // The suite lock is a whole-suite guard; a single-file smoke run is not
    // the contention it exists to prevent.
    env: { ...process.env, MERIDIAN_ALLOW_CONCURRENT_SUITE: '1' },
  });
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`;
  const summary = /Tests\s+(.+)$/m.exec(output.replace(/\[[0-9;]*m/g, ''));
  return {
    ok: result.status === 0,
    detail: summary ? summary[1].trim() : `exit ${result.status}`,
  };
}

export function runCompatibilitySmoke() {
  const matrix = JSON.parse(readFileSync(MATRIX, 'utf8'));
  const facts = hostFacts();
  const results = [];

  for (const row of matrix.rows) {
    // A row the matrix does not claim is not a promise, so there is nothing
    // to hold it to. It is reported so the count adds up.
    if (row.claimed === false) {
      results.push({ id: row.id, state: 'not-claimed', detail: 'the matrix makes no claim for this row' });
      continue;
    }
    const unmet = unmetBy(row, facts);
    if (unmet) {
      results.push({ id: row.id, state: 'not-verified-here', detail: unmet });
      continue;
    }
    const { file, name } = parseReference(row.backedBy);
    if (!existsSync(path.join(root, file))) {
      results.push({ id: row.id, state: 'failed', detail: `${file} does not exist` });
      continue;
    }
    const outcome = runVitest(file, name);
    results.push({
      id: row.id,
      state: outcome.ok ? 'passed' : 'failed',
      detail: `${row.backedBy} — ${outcome.detail}`,
    });
  }

  const failed = results.filter((result) => result.state === 'failed');
  return { ok: failed.length === 0, results, facts, failed };
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const { ok, results, facts, failed } = runCompatibilitySmoke();
  for (const result of results) {
    console.log(`  ${result.state.padEnd(18)} ${result.id.padEnd(22)} ${result.detail}`);
  }
  const passed = results.filter((r) => r.state === 'passed').length;
  const deferred = results.filter((r) => r.state === 'not-verified-here').length;
  console.log(
    `compatibility-smoke: ${passed} row(s) verified on ${facts.platform} ` +
      `(python ${facts.python ?? 'absent'}), ${deferred} not verifiable here, ` +
      `${failed.length} failed.`,
  );
  if (failed.length) {
    console.error(
      '  MK5: a claimed row whose test fails is removed from the matrix, not ' +
        'marked degraded. Decide and record it.',
    );
  }
  if (process.argv.includes('--record')) {
    mkdirSync(BASELINES, { recursive: true });
    const stamp = new Date().toISOString().slice(0, 10);
    const target = path.join(BASELINES, `${stamp}-${facts.platform}.json`);
    writeFileSync(
      target,
      `${JSON.stringify({ recordedAt: new Date().toISOString(), host: facts, results }, null, 2)}\n`,
      'utf8',
    );
    console.log(`  baseline written to ${path.relative(root, target)}`);
  }
  process.exit(ok ? 0 : 1);
}
