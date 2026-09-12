import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { CAPABILITIES } from '../../shared/ts/bus-types';
import {
  COMMAND_TIERS,
  enabledCommands,
  isRpcMethodEnabled,
  normalizeEnabledTiers,
} from '../../shared/ts/tiers';
import { COMMANDS, registerCommands } from '../src/commands';

/**
 * FR-M40-11, AC-36, AC-40 — MV2-T05.
 *
 * Initiation is **absent** below the Governor tier, not disabled. The
 * distinction is the whole of `G5`: a greyed-out button, a palette entry
 * that apologises, a method that exists and refuses — each of those is a
 * scar, a permanent reminder of something the product will not do. A tier
 * you have not bought should look like a product that was never designed
 * around it.
 *
 * So these tests assert absence: not that the affordance says no, but that
 * a Flight Recorder user cannot find one. And the other half, which is what
 * makes the claim worth anything — Flight Recorder is otherwise whole. A
 * test that only checked absence would pass on a build where nothing worked
 * at all.
 */

const manifest = JSON.parse(
  readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf8'),
);

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __shownInfos: string[];
  __shownWarnings: string[];
};

const FLIGHT_RECORDER = normalizeEnabledTiers(undefined);
const WITH_GOVERNOR = normalizeEnabledTiers(['governor']);

/** Every method the initiation capability owns. */
const RUN_METHODS = CAPABILITIES.find((c) => c.id === 'governor.initiation')?.rpcMethods ?? [];

describe('run initiation is a Governor capability (FR-M40-11)', () => {
  it('the capability exists and owns the run namespace', () => {
    // Without this the tests below would pass vacuously on a build where
    // initiation was never registered at all — absent for the wrong reason,
    // which is the failure mode every check in this repository has had at
    // least once.
    expect(RUN_METHODS.length).toBeGreaterThan(0);
    expect([...RUN_METHODS].sort()).toEqual(['run/cancel', 'run/preflight', 'run/start']);
    expect(CAPABILITIES.find((c) => c.id === 'governor.initiation')?.tier).toBe('governor');
  });

  it('below Governor, no run method passes the gate', () => {
    for (const method of RUN_METHODS) {
      expect(isRpcMethodEnabled(method, FLIGHT_RECORDER)).toBe(false);
    }
  });

  it('enabling Governor enables exactly the run namespace, and no more', () => {
    for (const method of RUN_METHODS) {
      expect(isRpcMethodEnabled(method, WITH_GOVERNOR)).toBe(true);
    }
    // AC-36 in the other direction: enabling a tier does not quietly enable
    // the one above it.
    expect(isRpcMethodEnabled('loop.start', WITH_GOVERNOR)).toBe(false);
  });
});

describe('no initiation affordance below Governor (AC-40)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('the start command is not among a Flight Recorder user’s commands', () => {
    expect(enabledCommands(FLIGHT_RECORDER)).not.toContain('meridian.startRun');
    expect(enabledCommands(WITH_GOVERNOR)).toContain('meridian.startRun');
  });

  it('the palette entry is hidden by a when clause, not rendered and refused', () => {
    const palette: Array<{ command: string; when?: string }> =
      manifest.contributes.menus.commandPalette;
    const entry = palette.find((item) => item.command === 'meridian.startRun');
    expect(entry).toBeDefined();
    expect(entry?.when).toBe('meridian.tiers.governor');
  });

  it('no menu anywhere contributes an ungated initiation item', () => {
    // Not only the palette: an editor context menu or a view title button
    // would be just as much of a scar, and is the sort of thing added later
    // by someone who only knew about `commandPalette`.
    const menus: Record<string, Array<{ command?: string; when?: string }>> =
      manifest.contributes.menus ?? {};
    for (const [where, items] of Object.entries(menus)) {
      for (const item of items) {
        if (item.command !== 'meridian.startRun') continue;
        expect(
          item.when,
          `${where} contributes meridian.startRun without a governor when clause`,
        ).toBe('meridian.tiers.governor');
      }
    }
  });

  it('the programmatic backstop discloses rather than acts', async () => {
    // The `when` clause hides the entry; a keybinding or another extension
    // can still invoke the id. The command must then say what is needed and
    // do nothing — never reach the sidecar, which would refuse at the tier
    // gate with a message about a capability the user never asked for.
    let preflighted = false;
    registerCommands({
      enabledTiers: () => FLIGHT_RECORDER,
      runPreflight: async () => {
        preflighted = true;
        throw new Error('unreachable');
      },
    });
    const start = mock.__registeredCommands.get('meridian.startRun') as () => Promise<void>;
    await start();
    expect(preflighted).toBe(false);
    const message = mock.__shownInfos.at(-1) ?? '';
    expect(message).toContain('governor');
    expect(message).toContain('meridian.tiers');
    expect(message).toContain('no reinstall');
  });
});

describe('Flight Recorder is otherwise whole (AC-36)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('every base-tier command is still registered and still enabled', () => {
    // The discriminating half. Absence of initiation is only a virtue if
    // everything below it still works; a build where nothing was registered
    // would satisfy every assertion above.
    const base = Object.entries(COMMAND_TIERS)
      .filter(([, tier]) => tier === 'flight-recorder')
      .map(([id]) => id);
    expect(base.length).toBeGreaterThan(0);
    registerCommands({ enabledTiers: () => FLIGHT_RECORDER });
    for (const id of base) {
      expect(mock.__registeredCommands.has(id)).toBe(true);
      expect(enabledCommands(FLIGHT_RECORDER)).toContain(id);
    }
  });

  it('initiation is registered as a command id even where it is locked', () => {
    // Registration and availability are different things. VS Code resolves
    // keybindings against registered ids, and an unregistered id produces a
    // raw "command not found" error rather than the disclosure above — a
    // worse scar than the one this avoids.
    registerCommands({ enabledTiers: () => FLIGHT_RECORDER });
    expect(mock.__registeredCommands.has('meridian.startRun')).toBe(true);
    expect(COMMANDS.some((command) => command.id === 'meridian.startRun')).toBe(true);
  });
});
