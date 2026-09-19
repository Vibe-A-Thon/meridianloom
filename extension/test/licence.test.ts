import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as vscode from 'vscode';
import type { LicenceRemoveResult, LicenceStatusResult } from '../../shared/ts/bus-types';
import { registerCommands, type CommandDeps } from '../src/commands';
import {
  createLicenceNotifier,
  describeEdition,
  isLicenceRequired,
  statusLines,
} from '../src/licence';

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __shownErrors: string[];
  __shownWarnings: string[];
  __shownInfos: string[];
  __quickPickCalls: Array<{ items: Array<{ label: string; description?: string }>; options?: { placeHolder?: string } }>;
  __messageChoices: string[];
};

const FINGERPRINT = 'MLM1-28C35-08B9B-A44A6-4D215-A4541';

function community(overrides: Partial<LicenceStatusResult> = {}): LicenceStatusResult {
  return {
    edition: 'community',
    state: 'none',
    reason: 'No Meridian Loom Premium licence is installed; the free Community edition is active.',
    premiumActive: false,
    machineFingerprint: FINGERPRINT,
    ...overrides,
  };
}

function premium(overrides: Partial<LicenceStatusResult> = {}): LicenceStatusResult {
  return {
    edition: 'premium',
    state: 'valid',
    reason: 'Premium licence active until 2027-09-19T00:00:00Z.',
    premiumActive: true,
    daysRemaining: 300,
    machineFingerprint: FINGERPRINT,
    licence: {
      licenceId: 'ML-20260919-ABCD1234',
      licensee: 'Acme Software Ltd',
      kind: 'developer',
      seats: 5,
      features: ['*'],
      expiresAt: '2027-09-19T00:00:00Z',
      trial: false,
    },
    ...overrides,
  };
}

function deps(overrides: Partial<CommandDeps> = {}): CommandDeps {
  return {
    licenceStatus: () => Promise.resolve(community()),
    licenceInstall: () => Promise.resolve(premium()),
    licenceRemove: () => Promise.resolve<LicenceRemoveResult>({ removed: ['x.mlic'], status: community() }),
    pickLicenceFile: () => Promise.resolve('C:/licences/acme.mlic'),
    copyText: () => Promise.resolve(),
    openLicensingGuide: () => Promise.resolve(),
    ...overrides,
  };
}

async function run(d: CommandDeps): Promise<void> {
  registerCommands(d);
  const handler = mock.__registeredCommands.get('meridian.licence');
  expect(handler).toBeDefined();
  await (handler as () => Promise<void>)();
}

describe('meridian.licence', () => {
  beforeEach(() => mock.__reset());

  it('is registered', () => {
    registerCommands(deps());
    expect(mock.__registeredCommands.has('meridian.licence')).toBe(true);
  });

  it('reports instead of acting when the runtime is not wired', async () => {
    await run({});
    expect(mock.__shownWarnings.some((m) => m.includes('meridian.licence'))).toBe(true);
    expect(mock.__quickPickCalls).toHaveLength(0);
  });

  it('a status failure is a message, never a throw', async () => {
    await run(deps({ licenceStatus: () => Promise.reject(new Error('sidecar is not connected')) }));
    expect(mock.__shownErrors.some((m) => m.includes('sidecar is not connected'))).toBe(true);
  });

  it('Community: offers install, fingerprint and the guide — but not remove', async () => {
    await run(deps());
    const labels = mock.__quickPickCalls[0].items.map((i) => i.label);
    expect(labels).toEqual([
      'Install licence file…',
      'Install licence for all users on this machine…',
      "Copy this machine's fingerprint",
      'About licensing',
    ]);
    expect(mock.__quickPickCalls[0].options?.placeHolder).toContain('Community (free)');
  });

  it('Premium: shows the licensee and offers remove', async () => {
    await run(deps({ licenceStatus: () => Promise.resolve(premium()) }));
    const call = mock.__quickPickCalls[0];
    expect(call.items.map((i) => i.label)).toContain('Remove installed licence');
    expect(call.options?.placeHolder).toContain('Acme Software Ltd');
  });

  it('a machine with no identifier does not offer a fingerprint', async () => {
    await run(deps({ licenceStatus: () => Promise.resolve(community({ machineFingerprint: null })) }));
    expect(mock.__quickPickCalls[0].items.map((i) => i.label)).not.toContain("Copy this machine's fingerprint");
  });

  it('installs a chosen file per-user and says Premium is active', async () => {
    const install = vi.fn(() => Promise.resolve(premium()));
    mock.__messageChoices.push('Install licence file…');
    await run(deps({ licenceInstall: install }));
    expect(install).toHaveBeenCalledWith({ path: 'C:/licences/acme.mlic', scope: 'user' });
    expect(mock.__shownInfos.some((m) => m.includes('Premium is now active'))).toBe(true);
  });

  it('installs machine-wide when asked', async () => {
    const install = vi.fn(() => Promise.resolve(premium()));
    mock.__messageChoices.push('Install licence for all users on this machine…');
    await run(deps({ licenceInstall: install }));
    expect(install).toHaveBeenCalledWith({ path: 'C:/licences/acme.mlic', scope: 'machine' });
  });

  it('cancelling the file dialog installs nothing', async () => {
    const install = vi.fn();
    mock.__messageChoices.push('Install licence file…');
    await run(deps({ licenceInstall: install as never, pickLicenceFile: () => Promise.resolve(undefined) }));
    expect(install).not.toHaveBeenCalled();
    expect(mock.__shownErrors).toHaveLength(0);
  });

  it('a refused licence shows the sidecar\'s reason and stores nothing', async () => {
    mock.__messageChoices.push('Install licence file…');
    await run(
      deps({
        licenceInstall: () =>
          Promise.reject(new Error('licence not installed: licence signature does not match its contents')),
      }),
    );
    expect(mock.__shownErrors.some((m) => m.includes('does not match its contents'))).toBe(true);
    expect(mock.__shownInfos.some((m) => m.includes('Premium is now active'))).toBe(false);
  });

  it('stored-but-inactive is reported honestly, not as success', async () => {
    mock.__messageChoices.push('Install licence file…');
    await run(
      deps({ licenceInstall: () => Promise.resolve(premium({ premiumActive: false, edition: 'community', state: 'wrong-developer', reason: 'git identity mismatch' })) }),
    );
    expect(mock.__shownInfos.some((m) => m.includes('Premium is not active yet') && m.includes('git identity mismatch'))).toBe(true);
    expect(mock.__shownInfos.some((m) => m.includes('Premium is now active'))).toBe(false);
  });

  it('copies the fingerprint and says what it is', async () => {
    const copy = vi.fn(() => Promise.resolve());
    mock.__messageChoices.push("Copy this machine's fingerprint");
    await run(deps({ copyText: copy }));
    expect(copy).toHaveBeenCalledWith(FINGERPRINT);
    expect(mock.__shownInfos.some((m) => m.includes('one-way'))).toBe(true);
  });

  it('remove needs confirmation', async () => {
    const remove = vi.fn(() => Promise.resolve<LicenceRemoveResult>({ removed: ['x'], status: community() }));
    mock.__messageChoices.push('Remove installed licence'); // pick
    // no confirmation choice queued -> the modal is dismissed
    await run(deps({ licenceStatus: () => Promise.resolve(premium()), licenceRemove: remove }));
    expect(remove).not.toHaveBeenCalled();
  });

  it('remove, once confirmed, returns to Community', async () => {
    const remove = vi.fn(() => Promise.resolve<LicenceRemoveResult>({ removed: ['x'], status: community() }));
    mock.__messageChoices.push('Remove installed licence', 'Remove licence');
    await run(deps({ licenceStatus: () => Promise.resolve(premium()), licenceRemove: remove }));
    expect(remove).toHaveBeenCalledWith({ scope: 'user' });
    expect(mock.__shownInfos.some((m) => m.includes('Licence removed') && m.includes('Community'))).toBe(true);
  });
});

describe('licence helpers', () => {
  it('isLicenceRequired matches only the licence error code', () => {
    expect(isLicenceRequired(Object.assign(new Error('x'), { code: -32006 }))).toBe(true);
    expect(isLicenceRequired(Object.assign(new Error('x'), { code: -32003 }))).toBe(false);
    expect(isLicenceRequired(new Error('x'))).toBe(false);
    expect(isLicenceRequired(null)).toBe(false);
  });

  it('describes editions plainly', () => {
    expect(describeEdition(community())).toBe('Community (free)');
    expect(describeEdition(premium())).toBe('Premium · Acme Software Ltd');
    expect(describeEdition(premium({ daysRemaining: 9 }))).toContain('9 day(s) left');
    expect(describeEdition(premium({ state: 'grace', daysRemaining: -3 }))).toContain('grace');
    expect(describeEdition(community({ state: 'expired' }))).toBe('Community — expired');
    const trial = premium();
    trial.licence!.trial = true;
    expect(describeEdition(trial)).toContain('Premium trial');
  });

  it('statusLines never contain a signature or fingerprint of other seats', () => {
    const text = statusLines(premium()).join('\n');
    expect(text).toContain('Acme Software Ltd');
    expect(text).toContain('all Premium features');
    expect(text.toLowerCase()).not.toContain('signature');
  });
});

describe('the Premium-required explanation', () => {
  beforeEach(() => mock.__reset());

  const actions = () => ({ install: vi.fn(() => Promise.resolve()), openGuide: vi.fn(() => Promise.resolve()) });
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('explains once per feature per session', async () => {
    const notify = createLicenceNotifier(actions());
    notify({ feature: 'governor', licenceState: 'none' });
    notify({ feature: 'governor', licenceState: 'none' });
    notify({ feature: 'orchestra', licenceState: 'none' });
    await flush();
    expect(mock.__shownInfos).toHaveLength(2);
    expect(mock.__shownInfos[0]).toContain('"governor"');
    expect(mock.__shownInfos[1]).toContain('"orchestra"');
  });

  it('tailors the hint to why the licence is not working', async () => {
    const notify = createLicenceNotifier(actions());
    notify({ feature: 'governor', licenceState: 'expired' });
    notify({ feature: 'orchestra', licenceState: 'wrong-machine' });
    await flush();
    expect(mock.__shownInfos[0]).toContain('expired');
    expect(mock.__shownInfos[1]).toContain('different machine');
  });

  it('offers the install action', async () => {
    const a = actions();
    mock.__messageChoices.push('Install licence…');
    createLicenceNotifier(a)({ feature: 'governor', licenceState: 'none' });
    await flush();
    expect(a.install).toHaveBeenCalledTimes(1);
    expect(a.openGuide).not.toHaveBeenCalled();
  });

  it('survives malformed data', async () => {
    const notify = createLicenceNotifier(actions());
    expect(() => notify(undefined)).not.toThrow();
    expect(() => notify('nonsense')).not.toThrow();
  });
});
