/**
 * ACP Registry integration (FR-M34-03): the registry
 * (https://agentclientprotocol.com/registry, index at
 * cdn.agentclientprotocol.com/registry/v1/latest/registry.json) is an
 * installable source in the Adapter Bay — any registered agent one click
 * from probation. Entries map to Meridian governance manifests (an adapter
 * is an ACP agent + manifest, FR-M34-02); install lands the manifest in the
 * workspace's `.meridian/adapters/<id>/` and the host admits it into
 * probation.
 *
 * OFFLINE-FRIENDLY: a failed fetch with a cached index serves the cache and
 * says so (`registryUnreachable`, `cached-stale`); with no cache the state
 * is `unreachable` — entries are never fabricated. Network access lives
 * entirely behind injectable seams (`fetchText`, `fetchBytes`,
 * `extractArchive`) so tests run with zero network.
 */
import { promises as fsp } from 'node:fs';
import path from 'node:path';
import { stringify } from 'yaml';
import {
  parseAdapterManifest,
  validateAdapterManifest,
  type AdapterManifest,
  type ManifestValidation,
  type PermissionKind,
} from './manifest';
import type { DiscoveredAdapter } from './discovery';

/** The official registry index, per agentclientprotocol/registry README. */
export const ACP_REGISTRY_DEFAULT_URL =
  'https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json';

/** Registry installs start conservative; policy (FR-M34-04) narrows further. */
const REGISTRY_DEFAULT_PERMISSIONS: PermissionKind[] = ['read', 'search', 'edit', 'execute'];

// -- registry index shape (FORMAT.md) -----------------------------------------

export interface RegistryNpxDistribution {
  package: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface RegistryUvXDistribution {
  package: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface RegistryBinaryTarget {
  archive: string;
  sha256?: string;
  cmd: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface RegistryEntry {
  id: string;
  name: string;
  version: string;
  description?: string;
  repository?: string;
  website?: string;
  authors?: string[];
  license?: string;
  icon?: string;
  distribution: {
    npx?: RegistryNpxDistribution;
    uvx?: RegistryUvXDistribution;
    binary?: Record<string, RegistryBinaryTarget>;
  };
}

export type RegistryParseResult =
  | { ok: true; entries: RegistryEntry[] }
  | { ok: false; errors: string[] };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Parse (and structurally check) a registry index. Fail-closed. */
export function parseRegistryIndex(raw: unknown, source: string): RegistryParseResult {
  const errors: string[] = [];
  if (!isRecord(raw) || !Array.isArray(raw.agents)) {
    return { ok: false, errors: [`${source}: registry index must be an object with an 'agents' array`] };
  }
  const entries: RegistryEntry[] = [];
  for (const [index, agent] of raw.agents.entries()) {
    if (!isRecord(agent) || typeof agent.id !== 'string' || typeof agent.version !== 'string') {
      errors.push(`${source}: agents[${index}]: missing string id/version`);
      continue;
    }
    if (!isRecord(agent.distribution) ||
        !(isRecord(agent.distribution.npx) ||
          isRecord(agent.distribution.uvx) ||
          isRecord(agent.distribution.binary))) {
      errors.push(`${source}: agents[${index}] (${agent.id}): no usable distribution`);
      continue;
    }
    entries.push(agent as unknown as RegistryEntry);
  }
  if (errors.length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, entries };
}

// -- entry → manifest mapping ---------------------------------------------------

export interface MapContext {
  /**
   * The registry platform key for this host, e.g. `windows-x86_64`
   * (FORMAT.md: darwin-aarch64, darwin-x86_64, linux-aarch64,
   * linux-x86_64, windows-aarch64, windows-x86_64).
   */
  platformKey: string;
}

export type RegistryMapResult =
  | { ok: true; manifest: AdapterManifest; archive?: { url: string; sha256?: string } }
  | { ok: false; errors: string[] };

function commandFor(kind: 'npx' | 'uvx'): string {
  // npx/uvx are shim scripts on Windows — spawn needs the real executable.
  if (process.platform !== 'win32') {
    return kind;
  }
  return kind === 'npx' ? 'npx.cmd' : 'uvx.exe';
}

/**
 * Map one registry entry to a governance manifest. Package distributions
 * (npx/uvx) are preferred — no archive handling; binary distributions are
 * used only when nothing else exists, and the archive reference rides
 * along for the installer to fetch and extract.
 */
export function mapRegistryEntryToManifest(
  raw: unknown,
  context: MapContext,
): RegistryMapResult {
  const parsed = parseRegistryIndex({ version: '1.0.0', agents: [raw] }, 'entry');
  if (!parsed.ok) {
    return { ok: false, errors: parsed.errors };
  }
  const entry = parsed.entries[0];
  const distribution = entry.distribution;

  let acp: { command: string; args: string[]; env: Record<string, string> };
  let archive: { url: string; sha256?: string } | undefined;
  if (distribution.npx) {
    acp = {
      command: commandFor('npx'),
      args: ['-y', distribution.npx.package, ...(distribution.npx.args ?? [])],
      env: distribution.npx.env ?? {},
    };
  } else if (distribution.uvx) {
    acp = {
      command: commandFor('uvx'),
      args: [distribution.uvx.package, ...(distribution.uvx.args ?? [])],
      env: distribution.uvx.env ?? {},
    };
  } else if (distribution.binary) {
    const target = distribution.binary[context.platformKey];
    if (!target) {
      return {
        ok: false,
        errors: [
          `registry entry '${entry.id}' has no ${context.platformKey} binary and no npx/uvx ` +
            'distribution — this agent cannot run on this host',
        ],
      };
    }
    acp = {
      command: target.cmd,
      args: target.args ?? [],
      env: target.env ?? {},
    };
    archive = { url: target.archive, ...(target.sha256 ? { sha256: target.sha256 } : {}) };
  } else {
    return { ok: false, errors: [`registry entry '${entry.id}' has no usable distribution`] };
  }

  const candidate = {
    adapter: {
      id: entry.id,
      version: entry.version,
      provenance: 'custom',
      ...(entry.authors && entry.authors.length > 0 ? { vendor: entry.authors[0] } : {}),
    },
    acp,
    role: { fills: [entry.name] },
    permissions: { allow: [...REGISTRY_DEFAULT_PERMISSIONS] },
    governance: { autonomy_tier: 'suggest' },
  };
  const validated = validateAdapterManifest(candidate, `registry:${entry.id}`);
  if (!validated.ok) {
    return { ok: false, errors: validated.errors };
  }
  return {
    ok: true,
    manifest: validated.manifest,
    ...(archive ? { archive } : {}),
  };
}

// -- the installable source -------------------------------------------------------

export interface RegistrySourceOptions {
  workspaceDir: string;
  /** Configurable index URL; defaults to the official registry. */
  url?: string;
  /** Injectable text fetch (tests inject; default uses global fetch). */
  fetchText?: (url: string) => Promise<string>;
  /** Injectable binary fetch for archive distributions. */
  fetchBytes?: (url: string) => Promise<Uint8Array>;
  /** Injectable archive extraction (default: system tar, see below). */
  extractArchive?: (archivePath: string, destDir: string) => Promise<void>;
  /** Injectable digest (tests pin; default sha256 via node:crypto). */
  sha256Of?: (bytes: Uint8Array) => Promise<string>;
  /** Injectable clock for cache timestamps. */
  now?: () => Date;
}

export type RegistryStatus =
  | {
      state: 'fresh';
      entries: RegistryEntry[];
      registryUnreachable: false;
      fetchedAt: string;
    }
  | {
      state: 'cached-stale';
      entries: RegistryEntry[];
      registryUnreachable: true;
      fetchedAt: string;
      warning: string;
    }
  | {
      state: 'unreachable';
      entries: [];
      registryUnreachable: true;
      warning: string;
    };

export type InstallResult =
  | { ok: true; adapter: DiscoveredAdapter }
  | { ok: false; errors: string[] };

export interface InstallOptions extends MapContext {
  /** Prefer the platform binary over npx/uvx when both exist. */
  preferBinary?: boolean;
  fetchBytes?: (url: string) => Promise<Uint8Array>;
  extractArchive?: (archivePath: string, destDir: string) => Promise<void>;
  sha256Of?: (bytes: Uint8Array) => Promise<string>;
}

interface CacheDocument {
  fetchedAt: string;
  url: string;
  index: unknown;
}

async function defaultFetchText(url: string): Promise<string> {
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`registry answered HTTP ${response.status}`);
  }
  return response.text();
}

/** Windows 10+ ships bsdtar as tar.exe; it handles zip and tar.* archives. */
async function defaultExtractArchive(archivePath: string, destDir: string): Promise<void> {
  const { execFile } = await import('node:child_process');
  const { promisify } = await import('node:util');
  await promisify(execFile)('tar', ['-xf', archivePath, '-C', destDir], {
    windowsHide: true,
  });
}

export class AcpRegistrySource {
  private entries: RegistryEntry[] = [];
  private status: RegistryStatus | undefined;

  constructor(private readonly options: RegistrySourceOptions) {}

  get url(): string {
    return this.options.url ?? ACP_REGISTRY_DEFAULT_URL;
  }

  private cacheFile(): string {
    return path.join(this.options.workspaceDir, '.meridian', 'cache', 'acp-registry.json');
  }

  /** Fetch + parse + cache the index; degrade to cache, then to unreachable. */
  async refresh(): Promise<RegistryStatus> {
    const fetchText = this.options.fetchText ?? defaultFetchText;
    try {
      const text = await fetchText(this.url);
      let raw: unknown;
      try {
        raw = JSON.parse(text);
      } catch (error) {
        throw new Error(`registry index is not JSON: ${(error as Error).message}`);
      }
      const parsed = parseRegistryIndex(raw, this.url);
      if (!parsed.ok) {
        throw new Error(parsed.errors.join('; '));
      }
      this.entries = parsed.entries;
      const fetchedAt = (this.options.now ?? (() => new Date()))().toISOString();
      this.status = { state: 'fresh', entries: this.entries, registryUnreachable: false, fetchedAt };
      await this.writeCache({ fetchedAt, url: this.url, index: raw });
      return this.status;
    } catch (error) {
      const cached = await this.readCache();
      if (cached !== undefined) {
        const parsed = parseRegistryIndex(cached.index, 'cached registry index');
        if (parsed.ok) {
          this.entries = parsed.entries;
          this.status = {
            state: 'cached-stale',
            entries: this.entries,
            registryUnreachable: true,
            fetchedAt: cached.fetchedAt,
            warning:
              `ACP registry is unreachable (${(error as Error).message}); showing the cached ` +
              `index from ${cached.fetchedAt}. Entries may be out of date.`,
          };
          return this.status;
        }
      }
      this.entries = [];
      this.status = {
        state: 'unreachable',
        entries: [],
        registryUnreachable: true,
        warning:
          `ACP registry is unreachable (${(error as Error).message}) and no cached index ` +
          'exists. Connect to the network and retry.',
      };
      return this.status;
    }
  }

  /** The last known status (refresh first in a live session). */
  async list(): Promise<RegistryStatus> {
    return this.status ?? (await this.refresh());
  }

  /**
   * One click from probation (FR-M34-03): materialise the adapter in
   * `.meridian/adapters/<id>/`. The host admits the result via the
   * ProbationTracker; discovery picks it up on the next scan.
   */
  async install(id: string, options: InstallOptions): Promise<InstallResult> {
    const status = await this.list();
    const entry = status.entries.find((candidate) => candidate.id === id);
    if (!entry) {
      const why =
        status.state === 'unreachable'
          ? 'the registry is unreachable and no cached index exists'
          : status.state === 'cached-stale'
            ? 'the cached registry index (registry unreachable)'
            : 'the registry index';
      return { ok: false, errors: [`adapter '${id}' is not in ${why}`] };
    }

    let mapped: ReturnType<typeof mapRegistryEntryToManifest>;
    const binaryTarget = entry.distribution.binary?.[options.platformKey];
    if (options.preferBinary && binaryTarget) {
      mapped = mapRegistryEntryToManifest(
        { ...entry, distribution: { binary: { [options.platformKey]: binaryTarget } } },
        options,
      );
    } else {
      mapped = mapRegistryEntryToManifest(entry, options);
    }
    if (!mapped.ok) {
      return { ok: false, errors: mapped.errors };
    }

    const adapterDir = path.join(this.options.workspaceDir, '.meridian', 'adapters', id);
    try {
      await fsp.mkdir(adapterDir, { recursive: true });
      if (mapped.archive) {
        await this.installBinary(mapped.archive, adapterDir, options);
      }
      await fsp.writeFile(
        path.join(adapterDir, 'manifest.yaml'),
        stringify(manifestToYamlDocument(mapped.manifest)),
        'utf8',
      );
    } catch (error) {
      // A half-written adapter folder must not linger (G5: no scar).
      await fsp.rm(adapterDir, { recursive: true, force: true }).catch(() => undefined);
      return { ok: false, errors: [`installing '${id}' failed: ${(error as Error).message}`] };
    }

    // Round-trip through the fail-closed validator: what we wrote is what
    // discovery will load.
    const written = await fsp.readFile(path.join(adapterDir, 'manifest.yaml'), 'utf8');
    const reparsed = parseAdapterManifest(written, path.join(id, 'manifest.yaml'));
    if (!reparsed.ok) {
      await fsp.rm(adapterDir, { recursive: true, force: true }).catch(() => undefined);
      return { ok: false, errors: reparsed.errors };
    }
    return {
      ok: true,
      adapter: { id, tier: 'workspace', dir: adapterDir, manifest: reparsed.manifest },
    };
  }

  private async installBinary(
    archive: { url: string; sha256?: string },
    adapterDir: string,
    options: InstallOptions,
  ): Promise<void> {
    const fetchBytes = options.fetchBytes ?? this.options.fetchBytes ?? defaultFetchBytes;
    const bytes = await fetchBytes(archive.url);
    if (archive.sha256) {
      const sha256Of = options.sha256Of ?? this.options.sha256Of ?? defaultSha256;
      const digest = (await sha256Of(bytes)).toLowerCase();
      if (digest !== archive.sha256.toLowerCase()) {
        throw new Error(
          `archive digest mismatch for ${archive.url}: expected sha256:${archive.sha256}, got ${digest}`,
        );
      }
    }
    const archivePath = path.join(adapterDir, path.basename(archive.url));
    await fsp.writeFile(archivePath, bytes);
    const extract =
      options.extractArchive ?? this.options.extractArchive ?? defaultExtractArchive;
    try {
      await extract(archivePath, adapterDir);
    } finally {
      await fsp.rm(archivePath, { force: true }).catch(() => undefined);
    }
  }

  private async writeCache(cache: CacheDocument): Promise<void> {
    try {
      await fsp.mkdir(path.dirname(this.cacheFile()), { recursive: true });
      await fsp.writeFile(this.cacheFile(), JSON.stringify(cache), 'utf8');
    } catch {
      // A missing cache degrades the next offline session to `unreachable`.
    }
  }

  private async readCache(): Promise<CacheDocument | undefined> {
    try {
      return JSON.parse(await fsp.readFile(this.cacheFile(), 'utf8')) as CacheDocument;
    } catch {
      return undefined;
    }
  }
}

async function defaultFetchBytes(url: string): Promise<Uint8Array> {
  const response = await fetch(url, { signal: AbortSignal.timeout(60_000) });
  if (!response.ok) {
    throw new Error(`archive download answered HTTP ${response.status}`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

async function defaultSha256(bytes: Uint8Array): Promise<string> {
  const { createHash } = await import('node:crypto');
  return createHash('sha256').update(bytes).digest('hex');
}

/** Manifest → YAML document using the §7.9 spelling (round-trippable). */
function manifestToYamlDocument(manifest: AdapterManifest): Record<string, unknown> {
  return {
    adapter: {
      id: manifest.id,
      version: manifest.version,
      provenance: manifest.provenance,
      ...(manifest.vendor !== undefined ? { vendor: manifest.vendor } : {}),
      ...(manifest.signature !== undefined ? { signature: manifest.signature } : {}),
    },
    acp: manifest.acp,
    role: { fills: manifest.roles },
    permissions: { allow: manifest.permissions.allow },
    ...(manifest.learning.trainable.length > 0 || manifest.learning.frozen.length > 0
      ? { learning: manifest.learning }
      : {}),
    governance: {
      autonomy_tier: manifest.governance.autonomyTier,
      ...(Object.keys(manifest.governance.probation).length > 0
        ? {
            probation: {
              ...(manifest.governance.probation.taskSet !== undefined
                ? { task_set: manifest.governance.probation.taskSet }
                : {}),
              ...(manifest.governance.probation.passThreshold !== undefined
                ? { pass_threshold: manifest.governance.probation.passThreshold }
                : {}),
            },
          }
        : {}),
    },
  };
}
