/**
 * Claims check — MV0-T03, principle MP5.
 *
 * `docs/claims.md` binds every capability this product asserts in customer-
 * facing text to the test that makes it true. This check keeps that binding
 * honest: a row naming a test that does not exist fails the build.
 *
 * It exists because two classes of defect got through without it. A
 * requirements document asserted a green suite that was red, and a README
 * listed two project directories that were not there. Both were assertions
 * nobody could run.
 *
 * Row format (see docs/claims.md for the prose):
 *   | Claim | Where | Backing test | Disposition |
 *
 * Dispositions:
 *   backed     — must name a test that resolves (file exists, name present)
 *   limitation — a disclosure, not a capability claim; must name no test.
 *                A test asserting we still cannot do something is theatre.
 *   withdrawn  — asserted once, found false, removed from the text; kept as
 *                history and must name no test.
 *
 * Test reference syntax:
 *   pytest  path/to/test_x.py::test_name
 *   vitest  path/to/x.test.ts > test name
 *   a bare path is accepted when the whole file is the evidence
 *
 * Exit codes: 0 = every claim resolves; 1 = a claim does not, listed.
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CLAIMS = path.join(root, 'docs', 'claims.md');

const DISPOSITIONS = new Set(['backed', 'limitation', 'withdrawn']);

/** Strip markdown emphasis, strikethrough and code fences from a prose cell. */
function plain(cell) {
  return cell.replace(/[`*~]/g, '').trim();
}

/**
 * Clean a test reference. Only backticks come off: test names legitimately
 * contain `*` (the activation-events guard asserts the literal string "*"),
 * and stripping it would silently look for a name that does not exist.
 */
function literal(cell) {
  return cell.replace(/`/g, '').trim();
}

function parseRows(markdown) {
  const rows = [];
  for (const line of markdown.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) continue;
    const cells = trimmed.slice(1, -1).split('|');
    if (cells.length !== 4) continue;
    const disposition = plain(cells[3]).toLowerCase();
    // The table of dispositions and the how-to-read table share this shape;
    // only rows whose last cell is a disposition are claims.
    if (!DISPOSITIONS.has(disposition)) continue;
    rows.push({
      claim: plain(cells[0]),
      // The raw cell keeps its backticks, which is how a withdrawn row
      // names the exact token that must no longer appear in the text.
      rawClaim: cells[0],
      where: plain(cells[1]),
      test: literal(cells[2]),
      disposition,
    });
  }
  return rows;
}

/** Does the named test exist? Returns null when it does, a reason when not. */
function resolveTest(reference) {
  const [filePart, namePart] = reference.includes('::')
    ? reference.split('::')
    : reference.includes(' > ')
      ? reference.split(' > ')
      : [reference, undefined];

  const file = filePart.trim();
  const absolute = path.join(root, file);
  if (!existsSync(absolute)) return `no such file: ${file}`;
  if (!namePart) return null;

  const name = namePart.trim();
  const contents = readFileSync(absolute, 'utf8');
  if (!contents.includes(name)) return `${file} does not contain: ${name}`;
  return null;
}

export function runClaimsCheck({ claimsPath = CLAIMS } = {}) {
  if (!existsSync(claimsPath)) {
    return { ok: false, rows: 0, problems: ['docs/claims.md does not exist'] };
  }
  const rows = parseRows(readFileSync(claimsPath, 'utf8'));
  const problems = [];
  const counts = { backed: 0, limitation: 0, withdrawn: 0 };

  for (const row of rows) {
    counts[row.disposition] += 1;
    const hasTest = row.test.length > 0 && row.test !== '—' && row.test !== '-';

    if (row.disposition === 'backed') {
      if (!hasTest) {
        problems.push(`"${row.claim}" is backed but names no test.`);
        continue;
      }
      const reason = resolveTest(row.test);
      if (reason) problems.push(`"${row.claim}" — ${reason}`);
    } else if (hasTest) {
      problems.push(
        `"${row.claim}" is ${row.disposition} but names a test (${row.test}). ` +
          `A disclosure needs to be true, not tested.`,
      );
    }

    // AC-63: a withdrawn claim must be gone from the text, not merely
    // recorded as withdrawn here. Recording it and leaving it in place is
    // the worse of the two failures — the table then says we fixed
    // something we did not.
    if (row.disposition === 'withdrawn') {
      const tokens = [...row.rawClaim.matchAll(/`([^`]+)`/g)].map((m) => m[1]);
      const files = [...row.where.matchAll(/([A-Za-z0-9._/-]+\.(?:md|json|ts|tsx))/g)].map(
        (m) => m[1],
      );
      for (const file of files) {
        const absolute = path.join(root, file);
        if (!existsSync(absolute)) continue;
        const contents = readFileSync(absolute, 'utf8');
        for (const token of tokens) {
          if (contents.includes(token)) {
            problems.push(
              `"${row.claim}" is marked withdrawn but ${file} still contains ${token}. ` +
                `Withdraw it from the text, or change the disposition.`,
            );
          }
        }
      }
    }
  }

  if (rows.length === 0) problems.push('docs/claims.md contains no claim rows.');
  return { ok: problems.length === 0, rows: rows.length, counts, problems };
}

const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const report = runClaimsCheck();
  for (const problem of report.problems) console.error(`  ${problem}`);
  if (report.ok) {
    const { backed, limitation, withdrawn } = report.counts;
    console.log(
      `claims: ${report.rows} claims — ${backed} backed by a resolving test, ` +
        `${limitation} declared limitations, ${withdrawn} withdrawn.`,
    );
  } else {
    console.error(
      'claims: a claim does not resolve. Give it a test, or take it out of the text — ' +
        'do not edit this check.',
    );
  }
  process.exit(report.ok ? 0 : 1);
}
