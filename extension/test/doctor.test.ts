import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import type { DoctorCheck, DoctorRunResult } from '../../shared/ts/bus-types';
import { registerCommands } from '../src/commands';
import { renderDoctorReport, runDoctor, type DoctorDeps } from '../src/doctor';
import { InterpreterResolutionError } from '../src/interpreter';
import { SecretStorageUnavailableError } from '../src/secrets';

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __outputChannels: Map<string, { lines: string[]; shown: boolean }>;
  __shownErrors: string[];
  __shownWarnings: string[];
  __shownInfos: string[];
};

const NAMES: Record<string, string> = {
  interpreter: 'Python interpreter',
  sidecar: 'Meridian Core sidecar',
  keychain: 'OS keychain (SecretStorage)',
  'signing-key': 'Ledger signing key',
  ledger: 'Ledger integrity',
  'git-hooks': 'Git provenance hooks',
  observers: 'Observer health',
};

function sidecarCheck(id: string, status: DoctorCheck['status'] = 'pass'): DoctorCheck {
  const check: DoctorCheck = { id, name: NAMES[id] ?? id, status, detail: `${id} detail` };
  if (status !== 'pass') {
    check.remediation = `${id} remediation`;
  }
  return check;
}

function fullSidecarReport(status: DoctorCheck['status'] = 'pass'): DoctorRunResult {
  return {
    status,
    checks: [
      sidecarCheck('interpreter'),
      sidecarCheck('sidecar'),
      sidecarCheck('signing-key', 'warn'),
      sidecarCheck('ledger', 'warn'),
      sidecarCheck('git-hooks', 'warn'),
      sidecarCheck('observers', 'warn'),
    ],
  };
}

function happyDeps(): DoctorDeps {
  return {
    verifySecrets: () => Promise.resolve(),
    runSidecarDoctor: () => Promise.resolve(fullSidecarReport('warn')),
  };
}

describe('runDoctor (FR-M30-01)', () => {
  it('merges host and sidecar checks into the canonical order', async () => {
    const report = await runDoctor(happyDeps());
    expect(report.checks.map((c) => c.id)).toEqual([
      'interpreter',
      'sidecar',
      'keychain',
      'signing-key',
      'ledger',
      'git-hooks',
      'observers',
    ]);
    // keychain comes from the host even though the sidecar ran.
    expect(report.checks.find((c) => c.id === 'keychain')?.status).toBe('pass');
    // Worst status wins: sidecar reported warns for the not-yet-built parts.
    expect(report.status).toBe('warn');
  });

  it('reports pass only when every check passes', async () => {
    const report = await runDoctor({
      verifySecrets: () => Promise.resolve(),
      runSidecarDoctor: () =>
        Promise.resolve({
          status: 'pass',
          checks: [
            sidecarCheck('interpreter'),
            sidecarCheck('sidecar'),
            sidecarCheck('signing-key'),
            sidecarCheck('ledger'),
            sidecarCheck('git-hooks'),
            sidecarCheck('observers'),
          ],
        }),
    });
    expect(report.status).toBe('pass');
    expect(renderDoctorReport(report).at(-1)).toContain('overall: PASS');
  });

  it('keychain failure is a fail with the SecretStorage remediation', async () => {
    const report = await runDoctor({
      ...happyDeps(),
      verifySecrets: () => Promise.reject(new SecretStorageUnavailableError()),
    });
    const keychain = report.checks.find((c) => c.id === 'keychain');
    expect(report.status).toBe('fail');
    expect(keychain?.status).toBe('fail');
    expect(keychain?.remediation).toContain('gnome-keyring');
  });

  it('without a sidecar the host still diagnoses: interpreter runs, sidecar fails, rest warn', async () => {
    const report = await runDoctor({
      verifySecrets: () => Promise.resolve(),
      probeInterpreter: () =>
        Promise.resolve({
          executable: '/usr/bin/python3',
          source: 'path',
          version: [3, 11, 9],
        }),
      workspaceDir: '/repo',
    });
    expect(report.status).toBe('fail');
    const byId = new Map(report.checks.map((c) => [c.id, c]));
    expect(byId.get('interpreter')?.status).toBe('pass');
    expect(byId.get('interpreter')?.detail).toContain('/usr/bin/python3');
    expect(byId.get('sidecar')?.status).toBe('fail');
    expect(byId.get('sidecar')?.detail).toContain('not running');
    for (const id of ['signing-key', 'ledger', 'git-hooks', 'observers']) {
      expect(byId.get(id)?.status).toBe('warn');
      expect(byId.get(id)?.detail).toContain('sidecar is unavailable');
    }
    expect(byId.get('keychain')?.status).toBe('pass');
  });

  it('an unreachable sidecar produces the same shape, with the RPC error named', async () => {
    const report = await runDoctor({
      ...happyDeps(),
      runSidecarDoctor: () => Promise.reject(new Error('sidecar is not running')),
      probeInterpreter: () => Promise.reject(new InterpreterResolutionError(['python: ENOENT'])),
    });
    const byId = new Map(report.checks.map((c) => [c.id, c]));
    expect(byId.get('sidecar')?.status).toBe('fail');
    expect(byId.get('sidecar')?.detail).toContain('sidecar is not running');
    // Interpreter resolution failure lists what was tried (FR-M3-04/05).
    expect(byId.get('interpreter')?.status).toBe('fail');
    expect(byId.get('interpreter')?.detail).toContain('python: ENOENT');
    expect(byId.get('interpreter')?.remediation).toContain('meridian.python.interpreterPath');
  });

  it('a sidecar report missing a check yields a visible warn, not silence', async () => {
    const report = await runDoctor({
      verifySecrets: () => Promise.resolve(),
      runSidecarDoctor: () =>
        Promise.resolve({
          status: 'pass',
          checks: [sidecarCheck('interpreter'), sidecarCheck('sidecar')],
        }),
    });
    const ledger = report.checks.find((c) => c.id === 'ledger');
    expect(ledger?.status).toBe('warn');
    expect(ledger?.detail).toContain('not reported');
  });

  it('renders one line per check plus remediation and summary lines', async () => {
    const report = await runDoctor(happyDeps());
    const rendered = renderDoctorReport(report);
    const checkLines = rendered.filter((l) => /^[✓!✗] /.test(l));
    expect(checkLines).toHaveLength(7);
    expect(rendered.some((l) => l.includes('overall: WARN'))).toBe(true);
    // Every non-pass entry carries a remediation pointer.
    for (const check of report.checks.filter((c) => c.status !== 'pass')) {
      expect(check.remediation).toBeTruthy();
    }
  });
});

describe('meridian.doctor command wiring (FR-M30-01)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('renders the report into the Doctor output channel and summarises', async () => {
    const disposables = registerCommands({ runDoctor: () => runDoctor(happyDeps()) });
    const handler = mock.__registeredCommands.get('meridian.doctor');
    expect(handler).toBeDefined();
    await (handler as () => Promise<void>)();

    const channel = mock.__outputChannels.get('Meridian Loom Doctor');
    expect(channel).toBeDefined();
    expect(channel?.shown).toBe(true);
    expect(channel?.lines.some((l) => l.includes('Ledger integrity'))).toBe(true);
    expect(channel?.lines.some((l) => l.includes('overall: WARN'))).toBe(true);
    expect(mock.__shownWarnings.some((m) => m.includes('passed with warnings'))).toBe(true);
    for (const disposable of disposables) {
      disposable.dispose();
    }
  });

  it('reports a failing run as an error message', async () => {
    registerCommands({
      runDoctor: () =>
        Promise.resolve({
          status: 'fail',
          checks: [
            { id: 'sidecar', name: 'Meridian Core sidecar', status: 'fail', detail: 'down' },
          ],
        }),
    });
    await (mock.__registeredCommands.get('meridian.doctor') as () => Promise<void>)();
    expect(mock.__shownErrors.some((m) => m.includes('failing checks'))).toBe(true);
  });

  it('without a wired runner it says so instead of silently succeeding', async () => {
    registerCommands();
    await (mock.__registeredCommands.get('meridian.doctor') as () => Promise<void>)();
    expect(mock.__shownWarnings.some((m) => m.includes('meridian.doctor'))).toBe(true);
  });

  it('other commands keep their not-connected behaviour', async () => {
    registerCommands({ runDoctor: () => runDoctor(happyDeps()) });
    await (mock.__registeredCommands.get('meridian.steer') as () => Promise<void>)();
    expect(mock.__shownWarnings.some((m) => m.includes('meridian.steer'))).toBe(true);
  });
});
