import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { DoctorRunResult } from '../../shared/ts/bus-types';
import { ErrorCode } from '../../shared/ts/bus-types';
import { StdioSidecarClient } from '../src/stdio-client';

const coreDir = path.resolve(__dirname, '..', '..', 'core');

function findPython(): string | undefined {
  for (const candidate of ['python', 'python3']) {
    try {
      const executable = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (executable) {
        return candidate;
      }
    } catch {
      // try the next candidate
    }
  }
  return undefined;
}

const python = findPython();
const run = python ? describe : describe.skip;

run('doctor/run against the real Python sidecar (FR-M30-01)', () => {
  it(
    'round-trips the full check registry over real stdio',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({ command: python!, cwd: coreDir });
      await client.start();
      try {
        const report = await client.call('doctor/run', {}, new AbortController().signal);
        expect(['pass', 'warn', 'fail']).toContain(report.status);
        const ids = report.checks.map((c) => c.id);
        expect(ids).toEqual([
          'interpreter',
          'sidecar',
          'signing-key',
          'ledger',
          'git-hooks',
          'observers',
        ]);
        // The live interpreter must pass; the not-yet-built subsystems must
        // warn with remediation, never crash. Observers are built (F0
        // Workstream D): they pass when healthy and warn when degraded.
        const byId = new Map(report.checks.map((c) => [c.id, c]));
        expect(byId.get('interpreter')?.status).toBe('pass');
        expect(byId.get('sidecar')?.status).toBe('pass');
        for (const id of ['signing-key', 'ledger', 'git-hooks']) {
          expect(byId.get(id)?.status).toBe('warn');
          expect(byId.get(id)?.remediation).toBeTruthy();
        }
        expect(['pass', 'warn']).toContain(byId.get('observers')?.status);
        if (byId.get('observers')?.status === 'warn') {
          expect(byId.get('observers')?.remediation).toBeTruthy();
        }
      } finally {
        client.kill();
      }
    },
  );

  it(
    'rejects an unknown check id with INVALID_PARAMS and the valid ids',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({ command: python!, cwd: coreDir });
      await client.start();
      try {
        await expect(
          client.request<DoctorRunResult>(
            'doctor/run',
            { checks: ['nope'] },
            new AbortController().signal,
          ),
        ).rejects.toMatchObject({ code: ErrorCode.INVALID_PARAMS });
      } finally {
        client.kill();
      }
    },
  );

  it(
    'runs a selected subset only',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({ command: python!, cwd: coreDir });
      await client.start();
      try {
        const report = await client.call(
          'doctor/run',
          { checks: ['sidecar'] },
          new AbortController().signal,
        );
        expect(report.checks.map((c) => c.id)).toEqual(['sidecar']);
        expect(report.status).toBe('pass');
      } finally {
        client.kill();
      }
    },
  );
});

if (!python) {
  // eslint-disable-next-line no-console
  console.warn('python not found on PATH; skipping doctor e2e tests');
}
