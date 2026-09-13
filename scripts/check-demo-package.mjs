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
import { existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findVsix, openZip } from './lib/vsix.mjs';

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
  // MV4-T03/T09: what a security review and a platform team ask for, inside
  // the package. A VSIX sideloaded into an enterprise arrives without the
  // repository, and "see the docs in our repo" is not an answer when the
  // repository is private.
  {
    step: 'MV4-T09 — a reporter knows where to go (AC-69)',
    where: 'extension/docs/SECURITY.md',
    needle: 'Acknowledgement',
    why: 'the vulnerability disclosure process, with a response a maintainer can meet',
  },
  {
    step: 'MV4-T09 — the dependency claim is checkable (AC-70)',
    where: 'extension/docs/THIRD-PARTY-NOTICES.md',
    needle: '| Component | Licence | Note |',
    why: 'the enumeration behind the no-copyleft statement',
  },
  {
    step: 'MV4-T09 — an organisation can plan around us (AC-71)',
    where: 'extension/docs/SUPPORT.md',
    needle: 'Leaving',
    why: 'supported versions, breaking-change notice, migration and the exit path',
  },
  {
    step: 'MV4-T03 — the staged evaluator documents',
    where: 'extension/docs/SECURITY-AND-DATA.md',
    needle: 'Limitations we are telling you about',
    why: 'the limitations a reviewer reads before adopting',
  },
];

/**
 * MV4-T03: structural facts about the package itself, rather than about a
 * step of the demo.
 *
 * The nested-directory check is here because it has bitten before: a build
 * produced `extension/extension/` with 37 tracked CRLF copies of the real
 * tree, and the guard that was supposed to catch it checked the filesystem
 * rather than what git tracked.
 */
function structuralProblems(members) {
  const problems = [];
  const nested = members.filter((name) => name.startsWith('extension/extension/'));
  if (nested.length) {
    problems.push(
      `the package contains a nested extension/extension/ directory (${nested.length} files). ` +
        'That has shipped before; it is duplicate content and it doubles the artefact.',
    );
  }
  const required = [
    ['extension/sidecar/meridian_core/__init__.py', 'the sidecar'],
    ['extension/sidecar/verify.py', 'the standalone verifier'],
    ['extension/library/runtimes.json', 'the runtime presets a first open seeds'],
    ['extension/webview-dist/index.html', 'the interface'],
  ];
  for (const [member, why] of required) {
    if (!members.includes(member)) problems.push(`${member} is not in the package (${why}).`);
  }
  const agents = members.filter((name) =>
    name.startsWith('extension/library/agents/'),
  ).length;
  if (agents === 0) {
    problems.push(
      'no agents are packaged, so a fresh workspace would seed an empty catalogue.',
    );
  }
  return problems;
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
  problems.push(...structuralProblems(archive.names));
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
