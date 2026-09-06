import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { CAPABILITIES, REQUEST_METHODS, TIERS } from '../../shared/ts/bus-types';
import {
  BASE_TIER,
  COMMAND_TIERS,
  enabledCommands,
  enabledViews,
  isCommandEnabled,
  isRpcMethodEnabled,
  normalizeEnabledTiers,
  TIER_CONTEXT_KEYS,
  tierLockMessage,
  VIEW_TIERS,
} from '../../shared/ts/tiers';
import { COMMANDS, registerCommands } from '../src/commands';
import { activate } from '../src/extension';
import { TREE_VIEWS } from '../src/views';

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __configuration: Map<string, unknown>;
  __contextKeys: Map<string, unknown>;
  __shownInfos: string[];
  __shownWarnings: string[];
  __fireConfigurationChange(...sections: string[]): void;
};

const manifest = JSON.parse(
  readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf8'),
);

describe('tier registry data (FR-M36-05)', () => {
  it('owns every bus method exactly once', () => {
    const claimed = CAPABILITIES.flatMap((c) => c.rpcMethods);
    expect(new Set(claimed).size).toBe(claimed.length);
    expect([...claimed].sort()).toEqual([...REQUEST_METHODS].sort());
  });

  it('owns every capability by exactly one known tier', () => {
    for (const capability of CAPABILITIES) {
      expect(TIERS).toContain(capability.tier);
    }
    expect(new Set(CAPABILITIES.map((c) => c.id)).size).toBe(CAPABILITIES.length);
  });

  it('maps every contributed command and view to a tier (drift guard)', () => {
    expect(Object.keys(COMMAND_TIERS).sort()).toEqual(COMMANDS.map((c) => c.id).sort());
    expect(Object.keys(VIEW_TIERS).sort()).toEqual(TREE_VIEWS.map((v) => v.id).sort());
  });
});

describe('normalizeEnabledTiers (FR-M36-05)', () => {
  it('defaults to flight-recorder only', () => {
    expect(normalizeEnabledTiers(undefined)).toEqual(['flight-recorder']);
    expect(normalizeEnabledTiers([])).toEqual(['flight-recorder']);
  });

  it('always includes the base tier', () => {
    expect(normalizeEnabledTiers(['orchestra'])).toEqual(['flight-recorder', 'orchestra']);
  });

  it('drops unknown tier names and keeps canonical order', () => {
    expect(normalizeEnabledTiers(['orchestra', 'bogus', 'governor'])).toEqual([
      'flight-recorder',
      'governor',
      'orchestra',
    ]);
  });
});

describe('RPC gating logic (FR-M36-05)', () => {
  it('with only flight-recorder enabled, upper-tier RPCs are refused', () => {
    const enabled = normalizeEnabledTiers(undefined);
    for (const method of ['doctor/run', 'ledger.append', 'health', 'ping']) {
      expect(isRpcMethodEnabled(method, enabled)).toBe(true);
    }
    for (const method of ['gate.evaluate', 'steer.send', 'trust.summary', 'loop.start']) {
      expect(isRpcMethodEnabled(method, enabled)).toBe(false);
    }
  });

  it('enabling a tier enables exactly its methods', () => {
    const enabled = normalizeEnabledTiers(['governor']);
    expect(isRpcMethodEnabled('gate.evaluate', enabled)).toBe(true);
    expect(isRpcMethodEnabled('loop.start', enabled)).toBe(false);
  });

  it('unowned methods are not a tier question', () => {
    expect(isRpcMethodEnabled('no/such.method', [])).toBe(true);
  });
});

describe('command and view filtering (FR-M36-05, X-28)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('with only flight-recorder, upper-tier commands disclose the lock', async () => {
    registerCommands({ enabledTiers: () => normalizeEnabledTiers(undefined) });
    await (mock.__registeredCommands.get('meridian.steer') as () => Promise<void>)();
    const message = mock.__shownInfos.at(-1);
    expect(message).toContain('governor');
    expect(message).toContain('meridian.tiers');
    expect(message).toContain('no reinstall');
    // The locked command did not run its real path.
    expect(mock.__shownWarnings.some((m) => m.includes('not connected'))).toBe(false);
  });

  it('re-enabling a tier is a config change only — no re-registration', async () => {
    let configured: string[] = [];
    registerCommands({ enabledTiers: () => normalizeEnabledTiers(configured) });
    const steer = mock.__registeredCommands.get('meridian.steer') as () => Promise<void>;
    await steer();
    expect(mock.__shownInfos.some((m) => m.includes('governor'))).toBe(true);

    // Flip the setting; the same registered handler now passes the gate.
    configured = ['flight-recorder', 'governor'];
    await steer();
    expect(mock.__shownWarnings.some((m) => m.includes('meridian.steer'))).toBe(true);
  });

  it('enabledCommands/enabledViews reflect the tier set', () => {
    const base = normalizeEnabledTiers(undefined);
    expect(enabledCommands(base).sort()).toEqual(
      [
        'meridian.doctor',
        'meridian.installHook',
        'meridian.openRecorder',
        'meridian.verifyChain',
      ].sort(),
    );
    expect(enabledViews(base)).toEqual(['meridianLoom.ledger']);
    expect(isCommandEnabled('meridian.doctor', base)).toBe(true);
    expect(isCommandEnabled('meridian.haltAll', base)).toBe(false);
    expect(tierLockMessage('meridian.haltAll')).toContain('governor');
  });

  it('the manifest hides upper-tier commands and views via when clauses', () => {
    const palette: Array<{ command: string; when?: string }> =
      manifest.contributes.menus.commandPalette;
    const gated = new Map(palette.map((entry) => [entry.command, entry.when]));
    for (const [commandId, tier] of Object.entries(COMMAND_TIERS)) {
      if (tier === BASE_TIER) {
        expect(gated.has(commandId)).toBe(false);
      } else {
        expect(gated.get(commandId)).toBe(TIER_CONTEXT_KEYS[tier]);
      }
    }
    const views: Array<{ id: string; when?: string }> =
      manifest.contributes.views['meridian-loom'];
    for (const view of views) {
      const tier = VIEW_TIERS[view.id];
      if (tier === BASE_TIER) {
        expect(view.when).toBeUndefined();
      } else {
        expect(view.when).toBe(TIER_CONTEXT_KEYS[tier]);
      }
    }
  });

  it('the manifest declares meridian.tiers defaulting to flight-recorder only', () => {
    const setting = manifest.contributes.configuration.properties['meridian.tiers'];
    expect(setting.default).toEqual(['flight-recorder']);
    expect(setting.items.enum).toEqual([...TIERS]);
  });
});

describe('activation publishes tier state (FR-M36-05, X-28)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  function mockContext() {
    return {
      subscriptions: [] as { dispose(): void }[],
      secrets: new vscode.MemorySecretStorage(),
      extensionPath: '/nonexistent/meridian-test',
    };
  }

  it('sets the tier context keys from configuration at activation', () => {
    activate(mockContext());
    expect(mock.__contextKeys.get('meridian.tiers.flightRecorder')).toBe(true);
    expect(mock.__contextKeys.get('meridian.tiers.governor')).toBe(false);
    expect(mock.__contextKeys.get('meridian.tiers.orchestra')).toBe(false);
  });

  it('a meridian.tiers change updates the context keys without re-activation', async () => {
    activate(mockContext());
    mock.__configuration.set('meridian.tiers', ['flight-recorder', 'governor']);
    mock.__fireConfigurationChange('meridian.tiers');
    await Promise.resolve();
    expect(mock.__contextKeys.get('meridian.tiers.governor')).toBe(true);
    expect(mock.__contextKeys.get('meridian.tiers.orchestra')).toBe(false);
  });

  it('unrelated configuration changes leave tier state alone', async () => {
    activate(mockContext());
    mock.__configuration.set('meridian.tiers', ['flight-recorder', 'orchestra']);
    mock.__fireConfigurationChange('meridian.python.interpreterPath');
    await Promise.resolve();
    expect(mock.__contextKeys.get('meridian.tiers.orchestra')).toBe(false);
  });
});
