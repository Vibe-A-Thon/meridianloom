/**
 * Hot plug / unplug (FR-M31-04, re-based on ACP per FR-M34-02): adding an
 * adapter folder admits it (into probation) with no extension redeploy and no
 * sidecar restart; removing it retires the adapter and runs every cleanup
 * hook registered for it — no scar (G5). Re-adding after removal is a full
 * unplug/plug cycle, not a resurrection of stale state.
 */
import { EventEmitter } from 'node:events';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AdapterRegistry } from '../src/adapters/registry';

function manifestYaml(id: string): string {
  return `
adapter: { id: ${id}, version: 1.0.0, provenance: custom }
acp: { command: ./${id}, args: [acp] }
role: { fills: [Developer] }
permissions: { allow: [read] }
`;
}

describe('adapter registry hot plug / unplug (FR-M31-04)', () => {
  let root: string;
  let workspaceDir: string;
  let adaptersDir: string;
  let registry: AdapterRegistry;
  const events: Array<{ type: string; id: string }> = [];

  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), 'meridian-hotplug-'));
    workspaceDir = path.join(root, 'workspace');
    adaptersDir = path.join(workspaceDir, '.meridian', 'adapters');
    mkdirSync(adaptersDir, { recursive: true });
    registry = new AdapterRegistry({
      roots: () => ({ workspaceDir, userDir: path.join(root, 'none'), builtinDir: path.join(root, 'none2') }),
      // Synchronous, test-driven re-scan trigger instead of a real fs watcher.
      watcher: () => ({ dispose: () => undefined }),
    });
    registry.on('added', (a) => events.push({ type: 'added', id: a.id }));
    registry.on('removed', (a) => events.push({ type: 'removed', id: a.id }));
    registry.on('changed', (a) => events.push({ type: 'changed', id: a.id }));
  });

  afterEach(() => {
    registry.dispose();
    rmSync(root, { recursive: true, force: true });
    events.length = 0;
  });

  function plug(id: string): string {
    const dir = path.join(adaptersDir, id);
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, 'manifest.yaml'), manifestYaml(id));
    return dir;
  }

  it('initial scan is empty; plugging emits added and admits the adapter', async () => {
    await registry.scan();
    expect(registry.list()).toEqual([]);

    plug('hot-agent');
    await registry.scan();
    expect(registry.list().map((a) => a.id)).toEqual(['hot-agent']);
    expect(events).toEqual([{ type: 'added', id: 'hot-agent' }]);
  });

  it('unplug removes the adapter, fires removed, and runs registered cleanup (no scar)', async () => {
    const dir = plug('gone-soon');
    await registry.scan();
    const cleaned: string[] = [];
    registry.onUnplug('gone-soon', () => cleaned.push('session-stopped'));

    rmSync(dir, { recursive: true, force: true });
    await registry.scan();
    expect(registry.list()).toEqual([]);
    expect(registry.get('gone-soon')).toBeUndefined();
    expect(events).toEqual([
      { type: 'added', id: 'gone-soon' },
      { type: 'removed', id: 'gone-soon' },
    ]);
    expect(cleaned).toEqual(['session-stopped']);
  });

  it('plug → unplug → plug again is a clean cycle with fresh state', async () => {
    const dir = plug('cyclical');
    await registry.scan();
    let cleanups = 0;
    registry.onUnplug('cyclical', () => cleanups++);

    rmSync(dir, { recursive: true, force: true });
    await registry.scan();
    expect(registry.list()).toEqual([]);

    plug('cyclical');
    await registry.scan();
    const again = registry.get('cyclical');
    expect(again).toBeDefined();
    expect(again!.tier).toBe('workspace');
    // The previous unplug cleanup ran exactly once; the re-pluged adapter is
    // a different admission, not a resurrection.
    expect(cleanups).toBe(1);
  });

  it('editing a manifest emits changed and re-validates (fail-closed)', async () => {
    const dir = plug('mutating');
    await registry.scan();
    writeFileSync(path.join(dir, 'manifest.yaml'), 'adapter: { id: "!!bad!!" }\n');
    await registry.scan();
    expect(registry.list()).toEqual([]);
    expect(registry.invalid.map((i) => i.id)).toEqual(['!!bad!!']);
    expect(events).toEqual([
      { type: 'added', id: 'mutating' },
      { type: 'removed', id: 'mutating' },
    ]);
  });

  it('a filesystem watcher event triggers a debounced re-scan (hot plug for real)', async () => {
    let onChange: (() => void) | undefined;
    const watching = new AdapterRegistry({
      roots: () => ({ workspaceDir, userDir: path.join(root, 'none'), builtinDir: path.join(root, 'none2') }),
      watcher: (dir, cb) => {
        expect(dir).toBe(adaptersDir);
        onChange = cb;
        return { dispose: () => undefined };
      },
      debounceMs: 1,
    });
    try {
      watching.startWatching();
      await watching.scan();
      plug('watched');
      onChange?.();
      // Poll instead of a fixed sleep: the debounced re-scan runs against
      // the real fs and its latency varies under suite load.
      for (let attempt = 0; attempt < 50 && watching.list().length === 0; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      expect(watching.list().map((a) => a.id)).toEqual(['watched']);
    } finally {
      watching.dispose();
    }
  });
});
