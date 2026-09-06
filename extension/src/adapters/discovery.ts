/**
 * Adapter discovery (FR-M31-02, re-based on ACP per FR-M34-02): walk three
 * roots for adapter folders — the workspace's `.meridian/adapters/`, the
 * user-level `~/.meridian/adapters/`, and the builtin (extension-bundled)
 * set — in that precedence order. A workspace adapter with the same id
 * shadows the user one, which shadows the builtin one. Discovery feeds the
 * Agent Registry (M5) from the filesystem; it runs on demand and on
 * filesystem change (hot plug, FR-M31-04).
 *
 * Validation is fail-closed (FR-M31-03): an invalid manifest is reported
 * with its actionable errors and is NOT admitted. The fs seam makes the
 * walker fully testable headless and keeps path handling platform-neutral.
 */
import { promises as fsp } from 'node:fs';
import path from 'node:path';
import { parseAdapterManifest, type AdapterManifest } from './manifest';

/** Which discovery root an adapter came from, highest precedence first. */
export type AdapterTier = 'workspace' | 'user' | 'builtin';

export const TIER_PRECEDENCE: readonly AdapterTier[] = ['workspace', 'user', 'builtin'];

export interface DiscoveredAdapter {
  id: string;
  tier: AdapterTier;
  /** The adapter folder — the portable unit (FR-M31-12). */
  dir: string;
  manifest: AdapterManifest;
}

export interface InvalidAdapter {
  id: string;
  tier: AdapterTier;
  dir: string;
  errors: string[];
}

export interface DiscoveryResult {
  adapters: DiscoveredAdapter[];
  invalid: InvalidAdapter[];
}

export interface DiscoveryRoots {
  /** The open workspace; adapters live in `<workspaceDir>/.meridian/adapters/`. */
  workspaceDir?: string;
  /** The user's home; adapters live in `<userDir>/.meridian/adapters/`. */
  userDir?: string;
  /** Builtin adapter set bundled with the extension. */
  builtinDir?: string;
}

/** The filesystem slice discovery needs; injectable for headless tests. */
export interface AdapterFs {
  readdir(dir: string): Promise<string[]>;
  readFile(file: string): Promise<string>;
  stat(file: string): Promise<{ isDirectory(): boolean }>;
}

const nodeFs: AdapterFs = {
  readdir: (dir) => fsp.readdir(dir),
  readFile: (file) => fsp.readFile(file, 'utf8'),
  stat: (file) => fsp.stat(file),
};

const MANIFEST_NAMES = ['manifest.yaml', 'manifest.yml'] as const;

function isEnoent(error: unknown): boolean {
  return (error as NodeJS.ErrnoException).code === 'ENOENT';
}

function adapterRoot(root: DiscoveryRoots, tier: AdapterTier): string | undefined {
  if (tier === 'builtin') {
    return root.builtinDir;
  }
  const base = tier === 'workspace' ? root.workspaceDir : root.userDir;
  return base === undefined ? undefined : path.join(base, '.meridian', 'adapters');
}

/**
 * Walk every immediate subdirectory of each root for a manifest document.
 * Nested adapter folders are not scanned — the folder is the unit.
 */
export async function discoverAdapters(
  roots: DiscoveryRoots,
  fs: AdapterFs = nodeFs,
): Promise<DiscoveryResult> {
  const adapters: DiscoveredAdapter[] = [];
  const invalid: InvalidAdapter[] = [];

  for (const tier of TIER_PRECEDENCE) {
    const base = adapterRoot(roots, tier);
    if (base === undefined) {
      continue;
    }
    let entries: string[];
    try {
      entries = await fs.readdir(base);
    } catch (error) {
      if (isEnoent(error)) {
        continue; // a tier with no directory contributes nothing
      }
      throw error;
    }
    for (const entry of entries) {
      const dir = path.join(base, entry);
      let manifestText: string | undefined;
      let manifestPath: string | undefined;
      for (const name of MANIFEST_NAMES) {
        try {
          manifestText = await fs.readFile(path.join(dir, name));
          manifestPath = path.join(dir, name);
          break;
        } catch (error) {
          if (!isEnoent(error)) {
            throw error;
          }
        }
      }
      if (manifestText === undefined || manifestPath === undefined) {
        continue; // a directory without a manifest is not an adapter
      }
      const parsed = parseAdapterManifest(manifestText, manifestPath);
      if (parsed.ok) {
        adapters.push({ id: parsed.manifest.id, tier, dir, manifest: parsed.manifest });
      } else {
        // FR-M31-03: listed with errors, not loaded. The id is best-effort
        // (from the manifest's broken id field, else the folder name).
        invalid.push({
          id: parsed.idHint ?? entry,
          tier,
          dir,
          errors: parsed.errors,
        });
      }
    }
  }

  // FR-M31-02 precedence: one adapter per id — the highest tier wins.
  const seen = new Set<string>();
  const deduped: DiscoveredAdapter[] = [];
  for (const adapter of adapters) {
    if (!seen.has(adapter.id)) {
      seen.add(adapter.id);
      deduped.push(adapter);
    }
  }
  return { adapters: deduped, invalid };
}
