/**
 * MVP traceability check — MV0-T04, principle MP1.
 *
 * The frozen requirement set (mvp-req-final.md) and the plan that builds it
 * (mvp-impl-plan.md) are two documents that must agree. They drifted twice
 * during the freeze audit — once with `MVP-GAP` requirements that no task
 * built, once with task text that cited a requirement id by range rather than
 * literally — and both times the drift was found by hand. This makes it
 * mechanical.
 *
 * Two directions, both fatal:
 *
 *   1. Every requirement group marked MVP-GAP in the requirements (MVP-Rn.n)
 *      must be scheduled against a task id in the plan.
 *   2. Every requirement identifier marked MVP-GAP (FR-Mnn-nn, NFR-nn,
 *      SEC-nn, AC-nn) must appear somewhere in the plan, so no in-scope
 *      requirement is left with nothing that builds it.
 *   3. Every MVP-Rn.n the plan cites must exist in the requirements, so the
 *      plan cannot schedule work against an identifier nobody wrote down.
 *
 * Dispositions other than MVP-GAP are deliberately not checked. BUILT needs
 * no task, POST-MVP must not have one, and MVP-HUMAN is blocked on people —
 * scheduling any of them would be the defect, not the fix.
 *
 * Exit codes: 0 = the two documents agree; 1 = drift, listed.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const REQUIREMENTS = path.join(root, 'mvp-req-final.md');
const PLAN = path.join(root, 'mvp-impl-plan.md');

/** Identifier namespaces a requirement row can carry. */
const ID = /(FR-M\d+-\d+|NFR-\d+|SEC-\d+|AC-\d+)/g;
const GROUP = /MVP-R\d+\.\d+/g;

function matchAll(text, re) {
  return new Set(text.match(new RegExp(re.source, 'g')) ?? []);
}

export function runTraceability({
  requirementsPath = REQUIREMENTS,
  planPath = PLAN,
} = {}) {
  const requirements = readFileSync(requirementsPath, 'utf8');
  const plan = readFileSync(planPath, 'utf8');

  // A requirement is in scope when its own table row says MVP-GAP. Reading
  // the row rather than the section keeps this honest for the mixed sections
  // where BUILT and MVP-GAP rows sit side by side.
  const gapRows = requirements
    .split('\n')
    .filter((line) => line.trim().startsWith('|') && line.includes('MVP-GAP'));

  const gapGroups = new Set();
  const gapIds = new Set();
  for (const row of gapRows) {
    for (const g of matchAll(row, GROUP)) gapGroups.add(g);
    for (const i of matchAll(row, ID)) gapIds.add(i);
  }

  const allGroups = matchAll(requirements, GROUP);
  const planGroups = matchAll(plan, GROUP);

  const unscheduledGroups = [...gapGroups].filter((g) => !planGroups.has(g)).sort();
  const unscheduledIds = [...gapIds].filter((i) => !plan.includes(i)).sort();
  const planOnlyGroups = [...planGroups].filter((g) => !allGroups.has(g)).sort();

  const ok =
    unscheduledGroups.length === 0 &&
    unscheduledIds.length === 0 &&
    planOnlyGroups.length === 0;

  return {
    ok,
    counts: {
      gapGroups: gapGroups.size,
      gapIds: gapIds.size,
      groupsInPlan: planGroups.size,
    },
    unscheduledGroups,
    unscheduledIds,
    planOnlyGroups,
  };
}

function print(report) {
  const { counts } = report;
  for (const g of report.unscheduledGroups) {
    console.error(
      `  ${g} is MVP-GAP in mvp-req-final.md and no task in mvp-impl-plan.md schedules it.`,
    );
  }
  for (const i of report.unscheduledIds) {
    console.error(
      `  ${i} is MVP-GAP and appears nowhere in mvp-impl-plan.md — nothing builds it.`,
    );
  }
  for (const g of report.planOnlyGroups) {
    console.error(
      `  ${g} is scheduled in mvp-impl-plan.md but is not a requirement in mvp-req-final.md.`,
    );
  }
  if (report.ok) {
    console.log(
      `mvp-traceability: ${counts.gapGroups} MVP-GAP groups and ${counts.gapIds} identifiers all scheduled; ` +
        `${counts.groupsInPlan} groups cited by the plan all exist.`,
    );
  } else {
    console.error(
      'mvp-traceability: the requirement set and the plan disagree. ' +
        'Either schedule the work or change the disposition — do not edit this check.',
    );
  }
}

const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const report = runTraceability();
  print(report);
  process.exit(report.ok ? 0 : 1);
}
