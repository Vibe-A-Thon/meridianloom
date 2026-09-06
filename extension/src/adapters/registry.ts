/**
 * The adapter registry (FR-M31-02/04, re-based on ACP per FR-M34-02): the
 * live view over discovered adapters, with hot plug/unplug. Adding an
 * adapter folder admits it (the host then runs it through probation,
 * FR-M31-07); removing it retires the adapter, runs every unplug cleanup
 * hook — hosted sessions stopped, probation records dropped — and leaves
 * no scar (G5). No extension redeploy, no sidecar restart.
 *
 * Watching is seam-injected: production uses fs.watch per root and per
 * adapter folder (Windows-robust — a full re-scan per debounced burst
 * beats recursive-watch platform quirks); tests drive the re-scan by hand.
 */
import { EventEmitter } from 'node:events';
import { watch } from 'node:fs';
import path from 'node:path';
import {
  discoverAdapters,
  TIER_PRECEDENCE,
  type AdapterFs,
  type DiscoveredAdapter,
  type DiscoveryResult,
  type DiscoveryRoots,
  type InvalidAdapter,
} from './discovery';

export interface WatcherHandle {
  dispose(): void;
}

/** Production watch: one handle per directory, bubbling to a re-scan. */
export type WatcherFactory = (dir: string, onChange: () => void) => WatcherHandle;

export interface AdapterRegistryOptions {
  /** Roots are read lazily so a workspace move applies to the next scan. */
  roots: () => DiscoveryRoots;
  fs?: AdapterFs;
  watcher?: WatcherFactory;
  /** Debounce window for watcher-triggered re-scans. */
  debounceMs?: number;
}

const defaultWatcher: WatcherFactory = (dir, onChange) => {
  const handle = watch(dir, () => onChange());
  handle.on('error', () => undefined); // a deleted root must not crash the host
  return { dispose: () => handle.close() };
};

export class AdapterRegistry extends EventEmitter {
  private adapters = new Map<string, DiscoveredAdapter>();
  private invalidAdapters: InvalidAdapter[] = [];
  private readonly unplugHooks = new Map<string, Set<() => void>>();
  private readonly watchers = new Map<string, WatcherHandle>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  constructor(private readonly options: AdapterRegistryOptions) {
    super();
  }

  get invalid(): readonly InvalidAdapter[] {
    return this.invalidAdapters;
  }

  list(): DiscoveredAdapter[] {
    return [...this.adapters.values()];
  }

  get(id: string): DiscoveredAdapter | undefined {
    return this.adapters.get(id);
  }

  /**
   * Register cleanup for an adapter's in-flight work (FR-M31-04: stop
   * hosted sessions, checkpoint and escalate — never lose work silently).
   * Fires exactly once per unplug, even if registered twice.
   */
  onUnplug(id: string, hook: () => void): void {
    let hooks = this.unplugHooks.get(id);
    if (!hooks) {
      hooks = new Set();
      this.unplugHooks.set(id, hooks);
    }
    hooks.add(hook);
  }

  /** Re-scan every root, diff against the live view, emit transitions. */
  async scan(): Promise<DiscoveryResult> {
    const result = await discoverAdapters(this.options.roots(), this.options.fs);
    const next = new Map(result.adapters.map((a) => [a.id, a]));

    for (const [id, previous] of this.adapters) {
      const current = next.get(id);
      if (current === undefined) {
        // Unplug: cleanup first, then announce — observers never see a
        // live adapter whose sessions are still running.
        const hooks = this.unplugHooks.get(id);
        this.unplugHooks.delete(id);
        for (const hook of hooks ?? []) {
          try {
            hook();
          } catch {
            // Cleanup must never block retirement (G5: no scar, no crash).
          }
        }
        this.adapters.delete(id);
        this.emit('removed', previous);
      } else if (JSON.stringify(previous.manifest) !== JSON.stringify(current.manifest)) {
        this.adapters.set(id, current);
        this.emit('changed', current);
      }
    }
    for (const [id, current] of next) {
      if (!this.adapters.has(id)) {
        this.adapters.set(id, current);
        this.emit('added', current);
      }
    }
    this.invalidAdapters = result.invalid;
    this.watchAdapterDirs(result);
    return result;
  }

  /** Watch the adapter roots (and each adapter folder) for plug/unplug. */
  startWatching(): void {
    const roots = this.options.roots();
    for (const tier of TIER_PRECEDENCE) {
      const base = adapterRootForWatch(roots, tier);
      if (base !== undefined) {
        this.ensureWatcher(base);
      }
    }
  }

  /** Debounced re-scan entry point used by watchers. */
  scheduleScan(): void {
    if (this.disposed) {
      return;
    }
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      void this.scan().catch(() => undefined);
    }, this.options.debounceMs ?? 100);
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.timer);
    for (const handle of this.watchers.values()) {
      handle.dispose();
    }
    this.watchers.clear();
    this.removeAllListeners();
  }

  private ensureWatcher(dir: string): void {
    if (this.watchers.has(dir) || this.disposed) {
      return;
    }
    const factory = this.options.watcher ?? defaultWatcher;
    try {
      this.watchers.set(
        dir,
        factory(dir, () => this.scheduleScan()),
      );
    } catch {
      // an unwatched root degrades to manual re-scan, never a crash
    }
  }

  private watchAdapterDirs(result: DiscoveryResult): void {
    for (const adapter of result.adapters) {
      this.ensureWatcher(adapter.dir);
    }
  }
}

function adapterRootForWatch(roots: DiscoveryRoots, tier: 'workspace' | 'user' | 'builtin'): string | undefined {
  if (tier === 'builtin') {
    return roots.builtinDir;
  }
  const base = tier === 'workspace' ? roots.workspaceDir : roots.userDir;
  return base === undefined ? undefined : path.join(base, '.meridian', 'adapters');
}
