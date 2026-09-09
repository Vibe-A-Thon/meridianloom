import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { activate } from '../src/extension';
import { COMMANDS } from '../src/commands';
import { TREE_VIEWS, WORKBENCH_VIEW } from '../src/views';

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

  it('registers the workbench webview view and no tree views (FR-M1-02)', () => {
    const context = mockContext();
    activate(context);
    const trees = (vscode as unknown as {
      __registeredTreeProviders: Map<string, unknown>;
    }).__registeredTreeProviders;
    const webviews = (vscode as unknown as {
      __registeredWebviewViewProviders: Map<string, unknown>;
    }).__registeredWebviewViewProviders;
    expect([...trees.keys()]).toEqual([]);
    // The Activity Bar container resolves straight into the workbench.
    expect([...webviews.keys()]).toEqual([WORKBENCH_VIEW.id]);
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
    // +1: the sidecar teardown disposable (FR-M3-02); +1: the meridian.tiers
    // configuration listener (FR-M36-05); +1: the recorder panel serializer
    // (VIGUIX_Final §17 — panel revival after reload).
    // +1 sidecar teardown (FR-M3-02); +1 meridian.tiers listener
    // (FR-M36-05); +1 panel serializer (VIGUIX_Final §17); +1 workbench view
    // provider and +1 its registration disposable.
    expect(context.subscriptions).toHaveLength(
      TREE_VIEWS.length + COMMANDS.length + 7,
    );
  });
});
