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
import {
  verifyAdapterPin,
  type PinFs,
  type PinVerdict,
} from './pinning';

/** Which discovery root an adapter came from, highest precedence first. */
export type AdapterTier = 'workspace' | 'user' | 'builtin';

export const TIER_PRECEDENCE: readonly AdapterTier[] = ['workspace', 'user', 'builtin'];

export interface DiscoveredAdapter {
  id: string;
  tier: AdapterTier;
  /** The adapter folder — the portable unit (FR-M31-12). */
  dir: string;
  manifest: AdapterManifest;
  /**
   * FR-M44-04: whether this is still the adapter that was installed. Always
   * present, because a surface that has to ask "was this checked?" will
   * eventually assume it was.
   */
  pin: PinVerdict;
}

export interface InvalidAdapter {
  id: string;
  tier: AdapterTier;
  dir: string;
  errors: string[];
  /**
   * Present when this adapter was refused for drift rather than for a bad
   * manifest. The two are different failures and an operator acts on them
   * differently: a manifest error is a mistake, drift is a question about
   * who changed the folder.
   */
  pin?: PinVerdict;
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
  /**
   * Raw bytes, for the content digest (MV3-T01). Optional: a test seam that
   * only serves text still works, digesting the UTF-8 encoding of what it
   * serves. Production supplies the real bytes, because a digest taken over
   * a UTF-8 round trip would not survive a binary file.
   */
  readFileBytes?(file: string): Promise<Uint8Array>;
  readFile(file: string): Promise<string>;
  stat(file: string): Promise<{ isDirectory(): boolean }>;
}

const nodeFs: AdapterFs = {
  readdir: (dir) => fsp.readdir(dir),
  readFileBytes: (file) => fsp.readFile(file),
  readFile: (file) => fsp.readFile(file, 'utf8'),
  stat: (file) => fsp.stat(file),
};

const MANIFEST_NAMES = ['manifest.yaml', 'manifest.yml'] as const;

function isEnoent(error: unknown): boolean {
  return (error as NodeJS.ErrnoException).code === 'ENOENT';
}

function isMissingDiscoveryEntry(error: unknown): boolean {
  const code = (error as NodeJS.ErrnoException).code;
  return code === 'ENOENT' || code === 'ENOTDIR';
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
export interface DiscoveryOptions {
  /**
   * FR-M44-04 (MV3-T01): the integrity check applied to every discovered
   * adapter. Injectable so discovery stays headless in tests; production
   * uses the real digest over the real folder.
   */
  verifyPin?: (args: {
    root: string;
    id: string;
    dir: string;
    tier: AdapterTier;
  }) => Promise<PinVerdict>;
}

/**
 * The pin check, reading through the same filesystem discovery is walking.
 *
 * It has to be the same one. The first version defaulted to the real disk
 * while discovery read from an injected seam, so every adapter in a headless
 * test resolved to a folder that was not there, came back `unreadable`, and
 * was refused — an integrity check failing adapters for existing only in
 * memory. A check that consults a different world than the thing it is
 * checking is not a check.
 */
function pinCheckFor(fs: AdapterFs): NonNullable<DiscoveryOptions['verifyPin']> {
  const encoder = new TextEncoder();
  const pinFs: PinFs = {
    readdir: (dir) => fs.readdir(dir),
    readFileBytes: fs.readFileBytes
      ? (file) => fs.readFileBytes!(file)
      : async (file) => encoder.encode(await fs.readFile(file)),
    readFileText: (file) => fs.readFile(file),
    stat: (file) => fs.stat(file),
    // Verification never writes. A seam that cannot write is not a reduced
    // capability here, it is the accurate one.
    writeFileText: async () => {
      throw new Error('discovery does not write pins');
    },
    mkdirp: async () => {
      throw new Error('discovery does not write pins');
    },
  };
  return async ({ root, id, dir, tier }) =>
    verifyAdapterPin(root, id, dir, { tier, fs: pinFs });
}

export async function discoverAdapters(
  roots: DiscoveryRoots,
  fs: AdapterFs = nodeFs,
  options: DiscoveryOptions = {},
): Promise<DiscoveryResult> {
  const adapters: DiscoveredAdapter[] = [];
  const invalid: InvalidAdapter[] = [];
  const verifyPin = options.verifyPin ?? pinCheckFor(fs);

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
    for (const entry of entries.sort()) {
      const dir = path.join(base, entry);
      let stats: { isDirectory(): boolean };
      try {
        stats = await fs.stat(dir);
      } catch (error) {
        if (isMissingDiscoveryEntry(error)) {
          continue;
        }
        throw error;
      }
      if (!stats.isDirectory()) {
        continue;
      }
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
        // FR-M44-04/SEC-33: a folder that has changed since it was installed
        // is not loaded. It is reported beside the manifest failures, with
        // both digests named, because the operator's next question is "did I
        // do that?" and only the two hashes can answer it.
        const pin = await verifyPin({ root: base, id: parsed.manifest.id, dir, tier });
        if (pin.state === 'drifted' || pin.state === 'unreadable') {
          invalid.push({
            id: parsed.manifest.id,
            tier,
            dir,
            errors: [pin.detail],
            pin,
          });
          continue;
        }
        adapters.push({
          id: parsed.manifest.id,
          tier,
          dir,
          manifest: parsed.manifest,
          pin,
        });
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
