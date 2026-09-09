/**
 * FR-M46-02 / AC-43: the surface-coverage orphan check
 * (scripts/check-surface-coverage.mjs) is itself guarded by tests.
 *
 * Each test builds a throwaway registry + consumer tree + allowlist under a
 * temp dir and runs the check as a subprocess, asserting:
 *  - the check runs and exits 0 when every orphan is declared (and any
 *    `mustSurface` instrument has gained a consumer — the AC-43 gate);
 *  - the allowlist schema is enforced (method, reason, reviewed date,
 *    optional boolean mustSurface; unknown methods rejected);
 *  - deliberately-added fake orphan methods are caught (exit 1, named in
 *    the JSON report's undeclaredOrphans);
 *  - `mustSurface: true` with no consumer fails the check, and resolves to
 *    a pass (and a resolvedMustSurface report entry) once a consumer exists.
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { afterAll, describe, expect, it } from 'vitest';

const SCRIPT = path.resolve(__dirname, '..', '..', 'scripts', 'check-surface-coverage.mjs');

let work: string | undefined;

function fixture() {
  work = mkdtempSync(path.join(os.tmpdir(), 'meridian-surface-'));
  const registryDir = path.join(work, 'schema');
  const consumerDir = path.join(work, 'consumers');
  mkdirSync(registryDir, { recursive: true });
  mkdirSync(consumerDir, { recursive: true });

  const registry = {
    'x-tiers': {
      capabilities: [
        {
          id: 'fake.cap',
          tier: 'flight-recorder',
          rpcMethods: [
            'fake/surfaced',
            'fake/orphanDeclared',
            'fake/orphanUndeclared',
            'fake/mustSurfacePending',
            'fake/mustSurfaceMet',
          ],
        },
      ],
    },
  };
  writeFileSync(path.join(registryDir, 'tiers.json'), JSON.stringify(registry), 'utf8');
  // Consumer tree: surfaced + the mustSurface instrument that has been met.
  // A test file must NOT count as a consumer (tests are not the interface).
  writeFileSync(
    path.join(consumerDir, 'panel.ts'),
    `export const a = controller.execute('fake/surfaced');\n`,
    'utf8',
  );
  writeFileSync(
    path.join(consumerDir, 'must-met.ts'),
    `export const b = controller.execute('fake/mustSurfaceMet');\n`,
    'utf8',
  );
  mkdirSync(path.join(consumerDir, '__tests__'), { recursive: true });
  writeFileSync(
    path.join(consumerDir, '__tests__', 'panel.test.ts'),
    `export const c = controller.execute('fake/orphanUndeclared');\n`,
    'utf8',
  );

  const allowlistFile = (entries: unknown) => {
    const file = path.join(registryDir, `allowlist-${Math.random().toString(36).slice(2)}.json`);
    writeFileSync(file, JSON.stringify(entries), 'utf8');
    return file;
  };

  const run = (allowlist: string) => {
    const report = path.join(work!, 'report.json');
    const result = spawnSync(
      process.execPath,
      [
        SCRIPT,
        '--registry', path.join(registryDir, 'tiers.json'),
        '--methods', path.join(registryDir, 'tiers.json'),
        '--allowlist', allowlist,
        '--roots', consumerDir,
        '--json', report,
        '--quiet',
      ],
      { encoding: 'utf8' },
    );
    return { status: result.status, stdout: result.stdout, stderr: result.stderr, report: readJson(report) };
  };
  return { registryDir, consumerDir, allowlistFile, run };
}

function readJson(file: string): Record<string, unknown> | undefined {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return undefined;
  }
}

afterAll(() => {
  if (work) rmSync(work, { recursive: true, force: true });
});

describe('surface-coverage orphan check (FR-M46-02, AC-43)', () => {
  it('runs clean when every orphan is declared and mustSurface instruments have consumers', () => {
    const f = fixture();
    // Both gate instruments have consumers here (one shipped with the
    // fixture, one added as the GUI session would by surfacing it).
    writeFileSync(
      path.join(f.consumerDir, 'new-panel.ts'),
      `export const d = controller.execute('fake/mustSurfacePending');\n`,
      'utf8',
    );
    const result = f.run(
      f.allowlistFile([
        { method: 'fake/orphanDeclared', reason: 'declared acceptable; phase none by design', reviewed: '2026-09-09' },
        { method: 'fake/orphanUndeclared', reason: 'declared so the check passes; tests still catch real orphans', reviewed: '2026-09-09' },
        { method: 'fake/mustSurfacePending', reason: 'gate: must gain a consumer', reviewed: '2026-09-09', mustSurface: true },
        { method: 'fake/mustSurfaceMet', reason: 'gate: already consumed', reviewed: '2026-09-09', mustSurface: true },
      ]),
    );
    expect(result.status, result.stderr).toBe(0);
    const summary = result.report?.summary as Record<string, number>;
    expect(summary.total).toBe(5);
    expect(summary.surfaced).toBe(3);
    expect(summary.undeclaredOrphans).toBe(0);
    expect(summary.mustSurfacePending).toBe(0);
    expect(summary.mustSurfaceResolved).toBe(2);
    const problems = result.report?.problems as Record<string, unknown>;
    expect(problems.undeclaredOrphans).toEqual([]);
    expect(problems.mustSurfaceViolations).toEqual([]);
    expect((problems.resolvedMustSurface as string[]).sort()).toEqual([
      'fake/mustSurfaceMet',
      'fake/mustSurfacePending',
    ]);
  });

  it('the mustSurface gate keeps failing until the instrument gains a consumer', () => {
    const f = fixture();
    const result = f.run(
      f.allowlistFile([
        { method: 'fake/orphanDeclared', reason: 'declared acceptable', reviewed: '2026-09-09' },
        { method: 'fake/orphanUndeclared', reason: 'declared', reviewed: '2026-09-09' },
        { method: 'fake/mustSurfacePending', reason: 'gate: must gain a consumer', reviewed: '2026-09-09', mustSurface: true },
        { method: 'fake/mustSurfaceMet', reason: 'gate: already consumed', reviewed: '2026-09-09', mustSurface: true },
      ]),
    );
    expect(result.status).toBe(1);
    const problems = result.report?.problems as Record<string, unknown>;
    expect(problems.mustSurfaceViolations).toEqual([
      expect.objectContaining({ method: 'fake/mustSurfacePending' }),
    ]);
    expect(problems.resolvedMustSurface).toEqual(['fake/mustSurfaceMet']);
    const summary = result.report?.summary as Record<string, number>;
    expect(summary.mustSurfacePending).toBe(1);
    expect(summary.mustSurfaceResolved).toBe(1);
  });

  it('fails and names a deliberately-added fake orphan missing from the allowlist', () => {
    const f = fixture();
    const result = f.run(
      f.allowlistFile([
        { method: 'fake/orphanDeclared', reason: 'declared', reviewed: '2026-09-09' },
      ]),
    );
    expect(result.status).toBe(1);
    const problems = result.report?.problems as Record<string, unknown>;
    expect(problems.undeclaredOrphans).toContain('fake/orphanUndeclared');
    expect(problems.undeclaredOrphans).toContain('fake/mustSurfacePending');
  });

  it('a test file calling an orphan does not count as an interface consumer', () => {
    const f = fixture();
    const result = f.run(f.allowlistFile([]));
    // fake/orphanUndeclared appears only in __tests__/panel.test.ts — still an orphan.
    const problems = result.report?.problems as Record<string, unknown>;
    expect(problems.undeclaredOrphans).toContain('fake/orphanUndeclared');
  });

  it('enforces the allowlist schema: reason, reviewed date, known method, boolean mustSurface', () => {
    const f = fixture();
    const result = f.run(
      f.allowlistFile([
        { method: 'fake/orphanDeclared' }, // missing reason + reviewed
        { method: 'fake/orphanUndeclared', reason: 'declared', reviewed: '09/09/2026' }, // bad date
        { method: 'fake/unknown', reason: 'not in registry', reviewed: '2026-09-09' }, // unknown method
        { method: 'fake/mustSurfacePending', reason: 'gate', reviewed: '2026-09-09', mustSurface: 'yes' }, // non-boolean
      ]),
    );
    expect(result.status).toBe(1);
    const errors = (result.report?.problems as Record<string, unknown>).allowlistErrors as string[];
    expect(errors.join('\n')).toMatch(/'reason' must be a non-empty string/);
    expect(errors.join('\n')).toMatch(/'reviewed' must be a YYYY-MM-DD date/);
    expect(errors.join('\n')).toMatch(/'fake\/unknown' is not a registry method/);
    expect(errors.join('\n')).toMatch(/'mustSurface' must be a boolean/);
  });
});
