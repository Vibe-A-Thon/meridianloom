/**
 * The demo path, checked against the built package — `MP7`, MV2-T07, MV3-T05.
 *
 * `DEMO.md` is the script somebody reads aloud in front of a customer. Every
 * step of it depends on something being *in the VSIX* — a command, a surface,
 * a sidecar module — and the checkout is not the VSIX. This project has
 * already shipped a README naming two directories that were not there and a
 * requirements document asserting a green suite that was red; both were
 * assertions nobody could run.
 *
 * So this runs. Given `dist/meridian-loom-<version>.vsix`, it asserts that
 * what the demo tells a presenter to do is present in the artefact they will
 * install.
 *
 * **What it does not do, and nobody should read it as doing:** it does not
 * open VS Code, click the buttons, or watch an agent run. It checks that the
 * package contains what the demo needs, not that the demo works. The
 * click-through on a clean machine is a human step and stays one.
 *
 * Usage:  node scripts/check-demo-package.mjs [path/to.vsix]
 * Exit:   0 every expectation met · 1 something the demo relies on is absent
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { inflateRawSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/**
 * One demo claim and the evidence for it inside the package.
 *
 * `where` is a published path inside the VSIX; `needle` is a string that must
 * appear in it. Deliberately a substring rather than a parse: these are
 * bundled and minified, and the question being asked is only "did this ship",
 * which a substring answers honestly.
 */
const EXPECTATIONS = [
  {
    step: 'DEMO §1 — install',
    where: 'extension/package.json',
    needle: '"meridian.tiers"',
    why: 'the tier setting the whole demo turns on',
  },
  {
    step: 'DEMO §3 — enable the Governor tier',
    where: 'extension/package.json',
    needle: '"meridian.tiers.governor"',
    why: 'the when-clause that hides Governor commands below the tier',
  },
  {
    step: 'DEMO §4 — bind a preset',
    where: 'extension/library/runtimes.json',
    needle: 'claude',
    why: 'the shipped runtime presets the bind step clicks',
  },
  {
    step: 'DEMO §4b — install from the registry',
    where: 'extension/dist/extension.js',
    needle: 'registry/install',
    why: 'the Adapter Bay registry install path',
  },
  {
    step: 'DEMO §4b — the registry is not fetched on activation',
    where: 'extension/webview-dist/assets',
    needle: 'Browse the registry',
    why: 'the explicit browse action, rather than a background fetch',
  },
  {
    step: 'DEMO §4b — a listing is not an endorsement',
    where: 'extension/webview-dist/assets',
    needle: 'not an endorsement',
    why: 'the boundary statement a presenter reads out before installing',
  },
  {
    step: 'DEMO §4b — digest pinning refuses a changed adapter',
    where: 'extension/dist/extension.js',
    needle: 'has changed since it was installed',
    why: 'the refusal, with both digests, that the talking point demonstrates',
  },
  {
    step: 'DEMO §6b — start a governed run',
    where: 'extension/package.json',
    needle: 'meridian.startRun',
    why: 'the command-palette door into run initiation',
  },
  {
    step: 'DEMO §6b — the preflight promise',
    where: 'extension/webview-dist/assets',
    needle: 'your working tree is untouched',
    why: 'the worktree promise, on the screen where the decision is made',
  },
  {
    step: 'DEMO §6b — run initiation reaches the sidecar',
    where: 'extension/sidecar/meridian_core/initiation.py',
    needle: 'def start_run',
    why: 'the single entry point the palette and the Launch screen both call',
  },
  {
    step: 'DEMO §8b — the pull-request card',
    where: 'extension/webview-dist/assets',
    needle: 'different revision from the one you would merge',
    why: 'the stale-head finding, which is the card\'s reason for existing',
  },
  {
    step: "DEMO §8c — another tool's records",
    where: 'extension/sidecar/meridian_core/interop.py',
    needle: 'foreign_record_notarised',
    why: 'the notarisation entry the ledger receives',
  },
  {
    step: 'DEMO §8c — notarising is not endorsing',
    where: 'extension/sidecar/meridian_core/interop.py',
    needle: 'does not vouch for it',
    why: 'the sentence that keeps a signature from reading as agreement',
  },
  {
    step: 'DEMO §9 — take the evidence away',
    where: 'extension/sidecar/verify.py',
    needle: 'def ',
    why: 'the standalone verifier handed to an auditor',
  },
];

function findVsix(explicit) {
  if (explicit) return path.resolve(explicit);
  const dist = path.join(root, 'dist');
  if (!existsSync(dist)) return undefined;
  const candidates = readdirSync(dist)
    .filter((name) => name.endsWith('.vsix'))
    .sort();
  return candidates.length ? path.join(dist, candidates[candidates.length - 1]) : undefined;
}

/**
 * The VSIX is a zip, read here without a dependency and without shelling out.
 *
 * The first version used `tar`, which reads zips on every platform in the
 * matrix — and GNU tar in Git Bash parses a `F:\path` argument as a remote
 * host and tries to *connect* to `F`. A check that fails on the maintainer's
 * own machine because of a drive letter is a check that gets skipped.
 *
 * Stored and deflated members only, which is what `vsce` writes and what the
 * workbench's own archive reader accepts: a bounded reader is easier to
 * reason about than a general one.
 */
function openZip(file) {
  const buffer = readFileSync(file);
  // End of central directory: scan back for the signature, tolerating the
  // trailing comment field.
  let eocd = -1;
  for (let at = buffer.length - 22; at >= 0 && at > buffer.length - 22 - 0xffff; at -= 1) {
    if (buffer.readUInt32LE(at) === 0x06054b50) {
      eocd = at;
      break;
    }
  }
  if (eocd < 0) throw new Error(`${path.basename(file)} is not a zip archive`);

  const count = buffer.readUInt16LE(eocd + 10);
  let at = buffer.readUInt32LE(eocd + 16);
  const entries = new Map();
  for (let index = 0; index < count; index += 1) {
    if (buffer.readUInt32LE(at) !== 0x02014b50) break;
    const method = buffer.readUInt16LE(at + 10);
    const compressedSize = buffer.readUInt32LE(at + 20);
    const nameLength = buffer.readUInt16LE(at + 28);
    const extraLength = buffer.readUInt16LE(at + 30);
    const commentLength = buffer.readUInt16LE(at + 32);
    const localOffset = buffer.readUInt32LE(at + 42);
    const name = buffer.toString('utf8', at + 46, at + 46 + nameLength);
    if (!name.endsWith('/')) {
      entries.set(name, { method, compressedSize, localOffset });
    }
    at += 46 + nameLength + extraLength + commentLength;
  }

  function read(name) {
    const entry = entries.get(name);
    if (!entry) throw new Error(`no such member: ${name}`);
    const header = entry.localOffset;
    if (buffer.readUInt32LE(header) !== 0x04034b50) {
      throw new Error(`corrupt local header for ${name}`);
    }
    const nameLength = buffer.readUInt16LE(header + 26);
    const extraLength = buffer.readUInt16LE(header + 28);
    const start = header + 30 + nameLength + extraLength;
    const raw = buffer.subarray(start, start + entry.compressedSize);
    if (entry.method === 0) return raw.toString('utf8');
    if (entry.method === 8) return inflateRawSync(raw).toString('utf8');
    throw new Error(
      `${name} uses compression method ${entry.method}, which this reader does not accept`,
    );
  }

  return { names: [...entries.keys()], read };
}

export function runDemoPackageCheck({ vsixPath } = {}) {
  const vsix = findVsix(vsixPath);
  const problems = [];
  const notes = [];

  if (!vsix || !existsSync(vsix)) {
    return {
      ok: false,
      checked: 0,
      problems: [
        'no VSIX found in dist/. Run `npm run package` first — the point of ' +
          'this check is that the checkout is not the artefact.',
      ],
    };
  }

  // The demo's own first instruction: compare the digest before installing.
  const checksumFile = `${vsix}.sha256`;
  if (!existsSync(checksumFile)) {
    problems.push(`${path.basename(vsix)} has no .sha256 beside it; DEMO §1 tells the reader to compare one.`);
  } else {
    const published = readFileSync(checksumFile, 'utf8').trim().split(/\s+/)[0];
    const actual = createHash('sha256').update(readFileSync(vsix)).digest('hex');
    if (published !== actual) {
      problems.push(
        `the published digest does not match the file: ${published} vs ${actual}`,
      );
    } else {
      notes.push(`digest matches the published .sha256 (${actual.slice(0, 16)}…)`);
    }
  }

  const archive = openZip(vsix);
  const members = new Set(archive.names);
  const cache = new Map();

  /** Directory expectations concatenate every member beneath the prefix. */
  function contentOf(where) {
    if (cache.has(where)) return cache.get(where);
    let text = '';
    if (members.has(where)) {
      text = archive.read(where);
    } else {
      const beneath = [...members].filter((name) => name.startsWith(`${where}/`));
      if (beneath.length === 0) {
        cache.set(where, undefined);
        return undefined;
      }
      text = beneath.map((name) => archive.read(name)).join('\n');
    }
    cache.set(where, text);
    return text;
  }

  for (const expectation of EXPECTATIONS) {
    const content = contentOf(expectation.where);
    if (content === undefined) {
      problems.push(
        `${expectation.step}: ${expectation.where} is not in the package (${expectation.why}).`,
      );
      continue;
    }
    if (!content.includes(expectation.needle)) {
      problems.push(
        `${expectation.step}: ${expectation.where} does not contain ${JSON.stringify(expectation.needle)} (${expectation.why}).`,
      );
    }
  }

  return { ok: problems.length === 0, checked: EXPECTATIONS.length, problems, notes, vsix };
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const result = runDemoPackageCheck({ vsixPath: process.argv[2] });
  for (const note of result.notes ?? []) console.log(`  ${note}`);
  for (const problem of result.problems) console.error(`  ${problem}`);
  console.log(
    result.ok
      ? `demo-package: ${result.checked} DEMO.md steps are backed by something in ${path.basename(result.vsix)}. ` +
          'This checks the package carries what the demo needs; walking the demo on a clean machine is still a human step.'
      : `demo-package: ${result.problems.length} of ${result.checked} DEMO.md steps are not backed by the package.`,
  );
  process.exit(result.ok ? 0 : 1);
}
