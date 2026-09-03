import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { activate } from '../src/extension';
import { COMMANDS } from '../src/commands';
import { TREE_VIEWS } from '../src/views';

function mockContext(): vscode.ExtensionContext {
  return {
    subscriptions: [] as { dispose(): void }[],
    secrets: new vscode.MemorySecretStorage(),
    // Nowhere real: runtime startup must not find (or spawn) a sidecar from
    // activation tests.
    extensionPath: '/nonexistent/meridian-test',
  };
}

describe('activate', () => {
  beforeEach(() => {
    (vscode as unknown as { __reset(): void }).__reset();
  });

  it('registers providers for all five tree views (FR-M1-02)', () => {
    const context = mockContext();
    activate(context);
    const registered = (vscode as unknown as {
      __registeredTreeProviders: Map<string, unknown>;
    }).__registeredTreeProviders;
    expect([...registered.keys()].sort()).toEqual(
      TREE_VIEWS.map((v) => v.id).sort(),
    );
  });

  it('registers all twelve commands (FR-M1-03)', () => {
    const context = mockContext();
    activate(context);
    const registered = (vscode as unknown as {
      __registeredCommands: Map<string, unknown>;
    }).__registeredCommands;
    expect([...registered.keys()].sort()).toEqual(
      COMMANDS.map((c) => c.id).sort(),
    );
  });

  it('pushes every registration into context.subscriptions', () => {
    const context = mockContext();
    activate(context);
    // +1: the sidecar teardown disposable (FR-M3-02).
    expect(context.subscriptions).toHaveLength(
      TREE_VIEWS.length + COMMANDS.length + 1,
    );
  });
});
