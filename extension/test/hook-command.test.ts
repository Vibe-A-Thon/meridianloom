import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as vscode from 'vscode';
import type {
  DoctorCheck,
  DoctorRunResult,
  HookInstallResult,
  HookRemoveResult,
  HookStatusResult,
} from '../../shared/ts/bus-types';
import { registerCommands, type CommandDeps } from '../src/commands';

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __shownErrors: string[];
  __shownWarnings: string[];
  __shownInfos: string[];
  __quickPickCalls: Array<{ items: Array<{ label: string }> }>;
  __messageChoices: string[];
};

function notInstalledStatus(): HookStatusResult {
  return {
    installed: false,
    foreignHook: false,
    hookPath: '/repo/.git/hooks/commit-msg',
    detail: 'commit-msg hook not installed (provenance trailers are opt-in)',
  };
}

function installedStatus(): HookStatusResult {
  return {
    installed: true,
    foreignHook: false,
    hookPath: '/repo/.git/hooks/commit-msg',
    chained: false,
    detail: 'Meridian commit-msg hook installed',
  };
}

function foreignStatus(): HookStatusResult {
  return {
    installed: false,
    foreignHook: true,
    hookPath: '/repo/.git/hooks/commit-msg',
    detail: "a commit-msg hook exists that is not Meridian's — left untouched",
  };
}

function installResult(): HookInstallResult {
  return { installed: true, hookPath: '/repo/.git/hooks/commit-msg', chained: false, alreadyInstalled: false };
}

function removeResult(): HookRemoveResult {
  return { removed: true, restoredBackup: false, detail: 'Meridian hook removed' };
}

function gitHooksCheck(status: DoctorCheck['status']): DoctorRunResult {
  const check: DoctorCheck = {
    id: 'git-hooks',
    name: 'Git provenance hooks',
    status,
    detail: `${status} detail`,
  };
  return { status, checks: [check] };
}

function hookDeps(overrides: Partial<CommandDeps> = {}): CommandDeps {
  return {
    hookStatus: () => Promise.resolve(notInstalledStatus()),
    hookInstall: () => Promise.resolve(installResult()),
    hookRemove: () => Promise.resolve(removeResult()),
    runDoctor: () => Promise.resolve(gitHooksCheck('pass')),
    ...overrides,
  };
}

async function runInstallHook(deps: CommandDeps): Promise<void> {
  registerCommands(deps);
  const handler = mock.__registeredCommands.get('meridian.installHook');
  expect(handler).toBeDefined();
  await (handler as () => Promise<void>)();
}

describe('meridian.installHook (FR-M36-03, D23)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('is registered as a command', () => {
    registerCommands(hookDeps());
    expect(mock.__registeredCommands.has('meridian.installHook')).toBe(true);
  });

  it('reports instead of acting when the runtime is not wired', async () => {
    await runInstallHook({});
    expect(mock.__shownWarnings.some((m) => m.includes('installHook'))).toBe(true);
    expect(mock.__quickPickCalls).toHaveLength(0);
  });

  it('offers install when no hook exists; confirms before touching the repo', async () => {
    const install = vi.fn(() => Promise.resolve(installResult()));
    // First choice: the quick-pick entry; second: the modal confirmation.
    mock.__messageChoices.push('Install commit-msg provenance hook', 'Install');
    await runInstallHook(hookDeps({ hookInstall: install }));
    expect(install).toHaveBeenCalledTimes(1);
    // After the action the doctor git-hooks result is surfaced.
    expect(
      mock.__shownInfos.some((m) => m.includes('git-hooks') && m.includes('pass')),
    ).toBe(true);
  });

  it('does nothing when the quick pick is cancelled', async () => {
    const install = vi.fn(() => Promise.resolve(installResult()));
    const remove = vi.fn(() => Promise.resolve(removeResult()));
    await runInstallHook(hookDeps({ hookInstall: install, hookRemove: remove }));
    expect(install).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
    expect(mock.__shownWarnings.some((m) => m.includes('Install'))).toBe(false);
  });

  it('does nothing when the confirmation is declined', async () => {
    const install = vi.fn(() => Promise.resolve(installResult()));
    mock.__messageChoices.push('Install commit-msg provenance hook');
    // The modal confirmation answers undefined (declined / dismissed).
    await runInstallHook(hookDeps({ hookInstall: install }));
    expect(install).not.toHaveBeenCalled();
  });

  it('offers removal when the Meridian hook is installed', async () => {
    const remove = vi.fn(() => Promise.resolve(removeResult()));
    mock.__messageChoices.push('Remove Meridian commit-msg hook', 'Remove');
    await runInstallHook(
      hookDeps({ hookStatus: () => Promise.resolve(installedStatus()), hookRemove: remove }),
    );
    expect(remove).toHaveBeenCalledTimes(1);
    expect(
      mock.__shownInfos.some((m) => m.includes('git-hooks')),
    ).toBe(true);
  });

  it('explains chaining when a foreign commit-msg hook exists', async () => {
    const install = vi.fn(() => Promise.resolve({ ...installResult(), chained: true }));
    mock.__messageChoices.push(
      'Install and chain onto the existing commit-msg hook',
      'Install',
    );
    await runInstallHook(
      hookDeps({ hookStatus: () => Promise.resolve(foreignStatus()), hookInstall: install }),
    );
    expect(install).toHaveBeenCalledTimes(1);
    // The confirmation mentions the existing hook is backed up, not replaced.
    expect(mock.__shownWarnings.some((m) => m.includes('backed up'))).toBe(true);
  });

  it('surfaces sidecar failures as errors without throwing', async () => {
    await runInstallHook(
      hookDeps({ hookStatus: () => Promise.reject(new Error('sidecar is not running')) }),
    );
    expect(mock.__shownErrors.some((m) => m.includes('sidecar is not running'))).toBe(true);
  });

  it('still shows the doctor result when the action itself reports failure', async () => {
    const install = vi.fn(() => Promise.reject(new Error('core.hooksPath conflict')));
    mock.__messageChoices.push('Install commit-msg provenance hook', 'Install');
    await runInstallHook(hookDeps({ hookInstall: install }));
    expect(mock.__shownErrors.some((m) => m.includes('core.hooksPath conflict'))).toBe(true);
  });
});
