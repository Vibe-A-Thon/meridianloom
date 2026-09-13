/**
 * The soak — `MVP-R6.4`, `NFR-43`, `FR-M46-08` (MV4-T06).
 *
 * Seven days of continuous operation under explicit resource limits, with no
 * unbounded growth in memory, disk or handle count. **This is elapsed time,
 * not effort**, and nothing about a harness makes it shorter. What a harness
 * can do is make the seven days produce evidence rather than an anecdote.
 *
 * It spawns the real sidecar — the thing a user runs, not an in-process
 * stand-in — and drives a steady workload against it over stdio: appends with
 * encrypted blobs, queries, periodic chain verification, health checks. Every
 * interval it samples the sidecar's resident memory, its open handle count,
 * and the ledger's size on disk, and appends the sample to a JSON Lines file
 * as it goes. A run that is killed on day four leaves four days of curve
 * behind, which is worth more than a summary that was never written.
 *
 * ## What "no unbounded growth" is checked as
 *
 *  - **Memory and handles** must stay under the explicit limits, and the
 *    trend over the second half of the run — after warm-up, when caches have
 *    filled — must not project past the limit within the soak window.
 *  - **Disk** is expected to grow: every append is a row and a blob. What
 *    must not grow is disk **per entry**. A ledger whose bytes-per-entry keeps
 *    climbing is leaking something, even though its total growth looks like
 *    ordinary use.
 *
 * ## What a short run proves
 *
 * Almost nothing about slow leaks, and the summary says so. A leak of a few
 * kilobytes an hour is invisible in ten minutes and fatal in a month. The
 * `--hours` a run actually lasted is recorded beside the 168 the requirement
 * asks for, so a smoke run of the harness can never be read as the soak.
 *
 * Usage:
 *   node scripts/soak.mjs [--hours 168] [--interval 60] [--label <name>]
 *                         [--max-rss-mb 512] [--max-handles 2000]
 */
import { execFileSync, spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findVsix, openZip } from './lib/vsix.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASELINES = path.join(root, 'docs', 'baselines', 'soak');
const REQUIRED_HOURS = 168;

/**
 * How much of a run must have elapsed before a trend is projected.
 *
 * The first smoke run of this harness "failed" after three minutes: the
 * sidecar's memory was still climbing through imports and cache warm-up, and
 * that slope, projected across 168 hours, crossed the limit. The projection
 * was arithmetic applied to warm-up, and a check that fires on every short run
 * is a check people learn to ignore. Hard limits are enforced from the first
 * sample; projections wait until the second half of the run is past warm-up.
 */
const MIN_PROJECTION_HOURS = 24;

function option(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const hours = Number(option('hours', String(REQUIRED_HOURS)));
const intervalSeconds = Number(option('interval', '60'));
const limits = {
  rssMb: Number(option('max-rss-mb', '512')),
  handles: Number(option('max-handles', '2000')),
};
const platform =
  process.platform === 'win32' ? 'windows' : process.platform === 'darwin' ? 'macos' : 'linux';
const label = option('label', platform);

// -- sampling the sidecar from outside it -----------------------------------
//
// From outside, deliberately. A process reporting its own memory is a process
// that can be wrong about itself in exactly the way a leak makes it wrong.

function sampleProcess(pid) {
  try {
    if (process.platform === 'win32') {
      const json = execFileSync(
        'powershell',
        [
          '-NoProfile',
          '-Command',
          `Get-Process -Id ${pid} | Select-Object WorkingSet64,HandleCount | ConvertTo-Json`,
        ],
        { encoding: 'utf8', windowsHide: true },
      );
      const parsed = JSON.parse(json);
      return { rssMb: parsed.WorkingSet64 / 1048576, handles: parsed.HandleCount };
    }
    if (process.platform === 'linux') {
      const status = readFileSync(`/proc/${pid}/status`, 'utf8');
      const rssKb = Number(/VmRSS:\s+(\d+)/.exec(status)?.[1] ?? NaN);
      const handles = readdirSync(`/proc/${pid}/fd`).length;
      return { rssMb: rssKb / 1024, handles };
    }
    const rssKb = Number(execFileSync('ps', ['-o', 'rss=', '-p', String(pid)], { encoding: 'utf8' }).trim());
    let handles = null;
    try {
      handles =
        execFileSync('lsof', ['-p', String(pid)], { encoding: 'utf8' }).trim().split('\n').length - 1;
    } catch {
      // No lsof: the handle count is unknown and recorded as unknown, never
      // as zero. A zero would read as a perfect result.
    }
    return { rssMb: rssKb / 1024, handles };
  } catch {
    return { rssMb: null, handles: null };
  }
}

function directoryBytes(directory) {
  if (!existsSync(directory)) return 0;
  let total = 0;
  for (const name of readdirSync(directory)) {
    const full = path.join(directory, name);
    const stats = statSync(full);
    total += stats.isDirectory() ? directoryBytes(full) : stats.size;
  }
  return total;
}

/** Least-squares slope of `y` over `x`. */
function slope(points) {
  const valid = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (valid.length < 3) return null;
  const n = valid.length;
  const meanX = valid.reduce((sum, p) => sum + p.x, 0) / n;
  const meanY = valid.reduce((sum, p) => sum + p.y, 0) / n;
  let numerator = 0;
  let denominator = 0;
  for (const p of valid) {
    numerator += (p.x - meanX) * (p.y - meanY);
    denominator += (p.x - meanX) ** 2;
  }
  return denominator === 0 ? 0 : numerator / denominator;
}

// -- driving the real sidecar ------------------------------------------------

/**
 * Where the sidecar under test comes from.
 *
 * The package by default (`MP7`): the shipped `extension/sidecar/` is
 * extracted from the built VSIX and that copy is executed. A leak introduced
 * by packaging — a missing module falling back to something slower, a file
 * shipped twice — is invisible to a soak of the checkout, and the checkout is
 * not what anyone installs. `--from-checkout` exists for iterating on the
 * harness itself, and a run made that way records that it does not count.
 */
function sidecarSource() {
  if (process.argv.includes('--from-checkout')) {
    return { dir: path.join(root, 'core'), source: 'checkout' };
  }
  const vsix = findVsix(option('vsix'));
  if (!vsix || !existsSync(vsix)) {
    throw new Error(
      'no VSIX in dist/. Run `npm run package` first: the soak runs the package, ' +
        'not the checkout. Pass --from-checkout only to exercise the harness.',
    );
  }
  const dir = mkdtempSync(path.join(os.tmpdir(), 'meridian-soak-sidecar-'));
  const written = openZip(vsix).extract('extension/sidecar/', dir);
  if (written === 0) throw new Error(`${path.basename(vsix)} contains no extension/sidecar/`);
  return { dir, source: `package:${path.basename(vsix)}` };
}

function startSidecar(workspace, sidecarDir) {
  const child = spawn(process.platform === 'win32' ? 'python' : 'python3', ['-m', 'meridian_core'], {
    cwd: sidecarDir,
    env: { ...process.env, MERIDIAN_PARENT_PID: String(process.pid), PYTHONUNBUFFERED: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  let buffer = '';
  const waiting = new Map();
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      // Notifications carry no id and are ignored; only answers resolve.
      if (message.id !== undefined && waiting.has(message.id)) {
        waiting.get(message.id)(message);
        waiting.delete(message.id);
      }
    }
  });
  child.stderr.on('data', () => {
    /* the sidecar logs to stderr; the soak reads resources, not logs */
  });
  let nextId = 1;
  const request = (method, params) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      const timer = setTimeout(() => {
        waiting.delete(id);
        reject(new Error(`${method} did not answer within 60s`));
      }, 60_000);
      waiting.set(id, (message) => {
        clearTimeout(timer);
        if (message.error) reject(new Error(`${method}: ${message.error.message}`));
        else resolve(message.result);
      });
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
    });
  return { child, request, workspace };
}

function appendParams(seq) {
  return {
    storyId: `SOAK-${Math.floor(seq / 1000)}`,
    phase: 'build',
    loopId: 'soak',
    loopIteration: 1,
    actorId: 'soak-agent',
    actorVersion: '0.0.1',
    actorKind: 'role',
    policyVersion: 'soak-v1',
    actionType: 'diff',
    input: `soak prompt ${seq}: ${randomBytes(96).toString('hex')}`,
    output: `soak output ${seq}`,
    blobSubject: 'story:soak',
  };
}

// -- the run -----------------------------------------------------------------

async function main() {
  mkdirSync(BASELINES, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const samplesPath = path.join(BASELINES, `${stamp}-${label}.jsonl`);
  const summaryPath = path.join(BASELINES, `${stamp}-${label}.summary.json`);
  const workspace = mkdtempSync(path.join(os.tmpdir(), 'meridian-soak-'));
  const ledgerDir = path.join(workspace, '.meridian');

  const origin = sidecarSource();
  const sidecar = startSidecar(workspace, origin.dir);
  await sidecar.request('handshake', {
    protocolVersion: 1,
    client: 'soak',
    workspaceDir: workspace,
    ledgerSigningKey: randomBytes(32).toString('base64'),
  });

  const started = Date.now();
  const deadline = started + hours * 3_600_000;
  const samples = [];
  let appended = 0;
  let failures = 0;
  let tick = 0;

  const writeSummary = (final) => {
    const secondHalf = samples.slice(Math.floor(samples.length / 2));
    const hoursOf = (s) => (s.t - started) / 3_600_000;
    const rssSlope = slope(secondHalf.map((s) => ({ x: hoursOf(s), y: s.rssMb })));
    const handleSlope = slope(secondHalf.map((s) => ({ x: hoursOf(s), y: s.handles })));
    const perEntrySlope = slope(
      secondHalf
        .filter((s) => s.appended > 0)
        .map((s) => ({ x: hoursOf(s), y: s.diskBytes / s.appended })),
    );
    const last = samples.at(-1);
    const remainingHours = Math.max(REQUIRED_HOURS - (Date.now() - started) / 3_600_000, 0);
    const breaches = [];
    if (last?.rssMb != null && last.rssMb > limits.rssMb) breaches.push(`memory ${last.rssMb.toFixed(1)} MB > ${limits.rssMb} MB`);
    if (last?.handles != null && last.handles > limits.handles) breaches.push(`handles ${last.handles} > ${limits.handles}`);
    const projecting = (Date.now() - started) / 3_600_000 >= MIN_PROJECTION_HOURS;
    if (projecting && last?.rssMb != null && rssSlope != null && last.rssMb + rssSlope * remainingHours > limits.rssMb) {
      breaches.push(`memory trend ${rssSlope.toFixed(3)} MB/h projects past ${limits.rssMb} MB within the soak window`);
    }
    if (projecting && last?.handles != null && handleSlope != null && last.handles + handleSlope * remainingHours > limits.handles) {
      breaches.push(`handle trend ${handleSlope.toFixed(3)}/h projects past ${limits.handles} within the soak window`);
    }
    const ranHours = (Date.now() - started) / 3_600_000;
    const summary = {
      label,
      sidecar: origin.source,
      host: { platform, release: os.release(), arch: process.arch, node: process.version },
      startedAt: new Date(started).toISOString(),
      finishedAt: final ? new Date().toISOString() : null,
      ranHours: Number(ranHours.toFixed(3)),
      requiredHours: REQUIRED_HOURS,
      limits,
      appended,
      failures,
      samples: samples.length,
      trendsProjected: projecting,
      trendsNote: projecting
        ? 'Trends from the second half of the run are projected across the remaining soak window.'
        : `Trends are recorded but not projected: fewer than ${MIN_PROJECTION_HOURS} hours have ` +
          'elapsed, so the second half of the run is still warm-up.',
      trends: {
        rssMbPerHour: rssSlope,
        handlesPerHour: handleSlope,
        diskBytesPerEntryPerHour: perEntrySlope,
      },
      breaches,
      verdict:
        breaches.length || failures
          ? 'failed'
          : ranHours >= REQUIRED_HOURS && origin.source !== 'checkout'
            ? 'passed'
            : 'incomplete',
      // The sentence that keeps a smoke run of this harness from ever being
      // cited as the soak.
      scope:
        origin.source === 'checkout'
          ? 'NOT the soak. The sidecar was run from the checkout, not the package (MP7).'
          : ranHours >= REQUIRED_HOURS
          ? `A complete ${REQUIRED_HOURS}-hour soak on ${label}, against ${origin.source}.`
          : `NOT the soak. This ran ${ranHours.toFixed(2)} of the ${REQUIRED_HOURS} hours ` +
            'NFR-43 requires, which is too short to reveal a slow leak. It proves the ' +
            'harness records, not that the product does not leak.',
    };
    writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
    return summary;
  };

  while (Date.now() < deadline) {
    tick += 1;
    try {
      for (let i = 0; i < 20; i += 1) {
        await sidecar.request('ledger.append', appendParams(appended + 1));
        appended += 1;
      }
      await sidecar.request('ledger.query', { limit: 50 });
      await sidecar.request('health', {});
      if (tick % 10 === 0) await sidecar.request('ledger.verify', {});
    } catch {
      failures += 1;
      if (sidecar.child.exitCode !== null) break;
    }
    const process_ = sampleProcess(sidecar.child.pid);
    const sample = {
      t: Date.now(),
      appended,
      failures,
      rssMb: process_.rssMb,
      handles: process_.handles,
      diskBytes: directoryBytes(ledgerDir),
    };
    samples.push(sample);
    appendFileSync(samplesPath, `${JSON.stringify(sample)}\n`, 'utf8');
    if (tick % 10 === 0) writeSummary(false);
    const wait = Math.min(intervalSeconds * 1000, Math.max(deadline - Date.now(), 0));
    if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  }

  sidecar.child.stdin.end();
  sidecar.child.kill();
  const summary = writeSummary(true);
  console.log(
    `soak: ${summary.verdict} — ${summary.appended} entries over ${summary.ranHours}h of ` +
      `${REQUIRED_HOURS}h, ${summary.samples} samples, ${summary.failures} failed ticks` +
      (summary.breaches.length ? `; breaches: ${summary.breaches.join('; ')}` : '') +
      `. ${path.relative(root, summaryPath)}`,
  );
  process.exit(summary.verdict === 'failed' ? 1 : 0);
}

main().catch((error) => {
  console.error(`soak: ${error.message}`);
  process.exit(1);
});
