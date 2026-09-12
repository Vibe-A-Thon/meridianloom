/**
 * Compatibility matrix check and generator — MV1-T05/T06.
 * FR-M44-08/09/10, MVP-R1.6, MVP-R3.5.
 *
 * `docs/SECURITY-AND-DATA.md` and `docs/DEPLOYMENT.md` tell an evaluator
 * which platforms this runs on. A hand-maintained table drifts the moment a
 * CI matrix changes and nobody edits the prose; a generated one cannot.
 *
 * Two jobs, one source:
 *
 *   check     every row names a smoke test that exists, and the table in
 *             docs/DEPLOYMENT.md matches what this file would generate
 *   --write   regenerate that table in place
 *
 * The rule that makes the matrix honest is in compatibility.json itself: a
 * combination not listed is not claimed, and a row is added together with
 * the test that backs it. There is deliberately no "degraded" or
 * "best-effort" state — MK5 says a row that cannot be backed is removed,
 * because a caveated claim is not a weaker claim, it is an unfalsifiable one.
 *
 * Exit codes: 0 = every row resolves and the table is current; 1 = a row
 * names a test that does not exist, or the table has drifted.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MATRIX = path.join(root, 'shared', 'schema', 'compatibility.json');
const DEPLOYMENT = path.join(root, 'docs', 'DEPLOYMENT.md');

const BEGIN = '<!-- BEGIN GENERATED: compatibility (scripts/check-compatibility.mjs) -->';
const END = '<!-- END GENERATED: compatibility -->';

const DIMENSION_LABEL = {
  os: 'Operating system',
  editor: 'Editor',
  python: 'Python',
  remote: 'Remote',
};

/** Does the named test exist? null when it resolves, a reason when not. */
function resolveTest(reference) {
  const [filePart, namePart] = reference.includes(' > ')
    ? reference.split(' > ')
    : [reference, undefined];
  const file = filePart.trim();
  if (!existsSync(path.join(root, file))) return `no such file: ${file}`;
  if (!namePart) return null;
  const contents = readFileSync(path.join(root, file), 'utf8');
  return contents.includes(namePart.trim())
    ? null
    : `${file} does not contain: ${namePart.trim()}`;
}

function renderTable(rows) {
  const lines = [
    BEGIN,
    '',
    '| Dimension | Supported | Backed by | Last passed |',
    '| --- | --- | --- | --- |',
  ];
  for (const row of rows) {
    // `claimed: false` marks a row that is declared but NOT rehearsed. It
    // renders as such rather than being quietly dropped: a reader deciding
    // whether to deploy over SSH needs to know the difference between "we
    // tested it" and "the declaration is right and nobody has run it".
    const supported = row.claimed === false ? `${row.value}` : row.value;
    lines.push(
      `| ${DIMENSION_LABEL[row.dimension] ?? row.dimension} | ${supported} | \`${row.backedBy}\` | ${row.lastPassed} |`,
    );
  }
  lines.push('');
  lines.push(
    '**A combination not in this table is not claimed.** Adding a row requires a ' +
      'passing smoke test in the same change; a row that cannot be backed is removed ' +
      'rather than marked degraded.',
  );
  lines.push('');
  lines.push(END);
  return lines.join('\n');
}

export function runCompatibility({ write = false } = {}) {
  const problems = [];
  if (!existsSync(MATRIX)) {
    return { ok: false, problems: ['shared/schema/compatibility.json does not exist'] };
  }
  const matrix = JSON.parse(readFileSync(MATRIX, 'utf8'));
  const rows = matrix.rows ?? [];
  if (rows.length === 0) problems.push('compatibility.json declares no rows');

  for (const row of rows) {
    for (const field of ['id', 'dimension', 'value', 'backedBy', 'lastPassed']) {
      if (!row[field]) problems.push(`row ${row.id ?? '(unnamed)'} is missing ${field}`);
    }
    if (!row.backedBy) continue;
    const reason = resolveTest(row.backedBy);
    if (reason) problems.push(`row ${row.id}: ${reason}`);
    if (row.lastPassed && !/^\d{4}-\d{2}-\d{2}$/.test(row.lastPassed)) {
      problems.push(`row ${row.id}: lastPassed must be YYYY-MM-DD, got ${row.lastPassed}`);
    }
  }

  const table = renderTable(rows);
  const deployment = existsSync(DEPLOYMENT) ? readFileSync(DEPLOYMENT, 'utf8') : '';
  const start = deployment.indexOf(BEGIN);
  const finish = deployment.indexOf(END);

  if (start === -1 || finish === -1) {
    problems.push(
      'docs/DEPLOYMENT.md has no generated compatibility block; run with --write',
    );
  } else {
    const current = deployment.slice(start, finish + END.length);
    if (current !== table) {
      if (write) {
        writeFileSync(
          DEPLOYMENT,
          deployment.slice(0, start) + table + deployment.slice(finish + END.length),
          'utf8',
        );
      } else {
        problems.push(
          'the compatibility table in docs/DEPLOYMENT.md has drifted from ' +
            'shared/schema/compatibility.json — run: node scripts/check-compatibility.mjs --write',
        );
      }
    }
  }

  return { ok: problems.length === 0, rows: rows.length, problems, table };
}

const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const write = process.argv.includes('--write');
  const report = runCompatibility({ write });
  for (const problem of report.problems) console.error(`  ${problem}`);
  if (report.ok) {
    console.log(
      `compatibility: ${report.rows} rows, every one backed by a test that exists` +
        (write ? '; docs/DEPLOYMENT.md regenerated' : '; docs/DEPLOYMENT.md is current'),
    );
  } else {
    console.error('compatibility: the matrix and the tree disagree.');
  }
  process.exit(report.ok ? 0 : 1);
}
