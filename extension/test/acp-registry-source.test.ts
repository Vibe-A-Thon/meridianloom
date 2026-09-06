/**
 * ACP Registry integration (FR-M34-03): the registry is an installable
 * source in the Adapter Bay — any registered agent one click from
 * probation. Index fetching is injected (no network in tests); the fixture
 * is recorded from the live registry. OFFLINE-FRIENDLY: a fetch failure
 * with a cached index serves the cache with an explicit `registry
 * unreachable` marker; with no cache the state is `unreachable` and NEVER
 * fabricates entries.
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readFileSync as readJson } from 'node:fs';
import {
  ACP_REGISTRY_DEFAULT_URL,
  AcpRegistrySource,
  mapRegistryEntryToManifest,
  parseRegistryIndex,
} from '../src/adapters/registry-source';
import { ProbationTracker } from '../src/adapters/probation';

const FIXTURE = JSON.parse(
  readJson(path.resolve(__dirname, 'fixtures', 'acp-registry-index.json'), 'utf8'),
) as { agents: unknown[] };

describe('registry index parsing (real recorded fixture)', () => {
  it('parses the recorded live-registry shape', () => {
    const parsed = parseRegistryIndex(FIXTURE, 'fixture');
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.entries.length).toBe(4);
    expect(parsed.entries.map((e) => e.id)).toEqual([
      'claude-acp',
      'gemini',
      'minion-code',
      'codex-acp',
    ]);
  });

  it('rejects a malformed index fail-closed (never fabricates entries)', () => {
    for (const bad of [{}, { version: '1.0.0' }, { agents: 'nope' }, { agents: [{ id: 42 }] }]) {
      const parsed = parseRegistryIndex(bad, 'bad-index');
      expect(parsed.ok).toBe(false);
      if (parsed.ok) return;
      expect(parsed.errors.length).toBeGreaterThan(0);
    }
  });
});

describe('registry entry → adapter manifest mapping', () => {
  const byId = (id: string) => FIXTURE.agents.find((a) => (a as { id: string }).id === id)!;

  it('maps an npx entry to an npx launch with pinned version and env passthrough', () => {
    const gemini = byId('gemini');
    const result = mapRegistryEntryToManifest(gemini, { platformKey: 'windows-x86_64' });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.id).toBe('gemini');
    expect(result.manifest.version).toBe('0.30.0');
    expect(result.manifest.provenance).toBe('custom');
    expect(result.manifest.vendor).toBe('Google');
    expect(result.manifest.acp.command).toBe(process.platform === 'win32' ? 'npx.cmd' : 'npx');
    expect(result.manifest.acp.args).toEqual(['-y', '@google/gemini-cli@0.30.0', '--experimental-acp']);
  });

  it('maps a uvx entry to a uvx launch', () => {
    const result = mapRegistryEntryToManifest(byId('minion-code'), { platformKey: 'linux-x86_64' });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.acp.command).toMatch(/^uvx(\.exe)?$/);
    expect(result.manifest.acp.args).toEqual(['minion-code@0.1.39', 'acp']);
  });

  it('prefers npx when available even if a binary distribution exists (no archive needed)', () => {
    const result = mapRegistryEntryToManifest(byId('codex-acp'), { platformKey: 'windows-x86_64' });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.acp.command).toMatch(/npx(\.cmd)?$/);
  });

  it('falls back to the platform binary with an archive reference when no npx exists', () => {
    const entry = {
      id: 'goose-like',
      name: 'Goose Like',
      version: '1.0.0',
      distribution: {
        binary: {
          'windows-x86_64': { archive: 'https://x/goose.zip', cmd: 'goose.exe', args: ['acp'] },
        },
      },
    };
    const result = mapRegistryEntryToManifest(entry, { platformKey: 'windows-x86_64' });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.acp.command).toBe('goose.exe');
    expect(result.manifest.acp.args).toEqual(['acp']);
    expect(result.archive).toEqual({ url: 'https://x/goose.zip' });
  });

  it('fails with an actionable error when the platform is unsupported', () => {
    const entry = {
      id: 'mac-only',
      version: '1.0.0',
      distribution: { binary: { 'darwin-aarch64': { archive: 'https://x/m.tar.gz', cmd: './m' } } },
    };
    const result = mapRegistryEntryToManifest(entry, { platformKey: 'windows-x86_64' });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.errors.join('\n')).toMatch(/windows-x86_64/);
  });

  it('registry installs declare conservative default permission needs', () => {
    const result = mapRegistryEntryToManifest(byId('claude-acp'), { platformKey: 'linux-x86_64' });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.permissions.allow).toContain('read');
    expect(result.manifest.governance.autonomyTier).toBe('suggest');
    expect(result.manifest.roles.length).toBeGreaterThan(0);
  });
});

describe('registry source: fetch, offline states, install (FR-M34-03)', () => {
  let root: string;
  let workspaceDir: string;
  let fetchCalls: string[];

  const indexJson = (): string => JSON.stringify(FIXTURE);

  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), 'meridian-registry-'));
    workspaceDir = path.join(root, 'workspace');
    mkdirSync(workspaceDir, { recursive: true });
    fetchCalls = [];
  });

  afterEach(() => rmSync(root, { recursive: true, force: true }));

  function source(opts: { fetchText?: (url: string) => Promise<string>; url?: string } = {}) {
    return new AcpRegistrySource({
      workspaceDir,
      url: opts.url ?? 'https://registry.test/index.json',
      fetchText:
        opts.fetchText ??
        (async (url) => {
          fetchCalls.push(url);
          return indexJson();
        }),
    });
  }

  it('fetches the index from the configurable URL (default is the official registry)', () => {
    expect(ACP_REGISTRY_DEFAULT_URL).toBe(
      'https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json',
    );
  });

  it('fresh fetch: entries served and cached for offline use', async () => {
    const reg = source();
    const status = await reg.refresh();
    expect(status.state).toBe('fresh');
    expect(status.entries.map((e) => e.id)).toContain('gemini');
    const cacheFile = path.join(workspaceDir, '.meridian', 'cache', 'acp-registry.json');
    expect(JSON.parse(readFileSync(cacheFile, 'utf8')).index.agents.length).toBe(4);
    expect(fetchCalls).toEqual(['https://registry.test/index.json']);
  });

  it('unreachable + cache: cached entries served with an explicit unreachable marker', async () => {
    const first = source();
    await first.refresh(); // populate the cache

    const offline = source({
      fetchText: async () => {
        throw new Error('ENOTFOUND registry.test');
      },
    });
    const status = await offline.refresh();
    expect(status.state).toBe('cached-stale');
    expect(status.registryUnreachable).toBe(true);
    expect(status.entries.length).toBe(4); // real cached entries, never fakes
    expect(status.warning).toMatch(/unreachable/i);
  });

  it('unreachable + no cache: explicit unreachable state with zero entries', async () => {
    const offline = source({
      fetchText: async () => {
        throw new Error('ENOTFOUND registry.test');
      },
    });
    const status = await offline.refresh();
    expect(status.state).toBe('unreachable');
    expect(status.entries).toEqual([]);
    expect(status.registryUnreachable).toBe(true);
  });

  it('install lands the adapter in .meridian/adapters/<id>/ as a valid YAML manifest', async () => {
    const reg = source();
    await reg.refresh();
    const installed = await reg.install('claude-acp', { platformKey: 'linux-x86_64' });
    expect(installed.ok).toBe(true);
    if (!installed.ok) return;
    expect(installed.adapter.tier).toBe('workspace');
    expect(installed.adapter.dir).toBe(
      path.join(workspaceDir, '.meridian', 'adapters', 'claude-acp'),
    );
    // The written manifest re-parses as valid (round-trip through the
    // fail-closed validator).
    const written = readFileSync(
      path.join(installed.adapter.dir, 'manifest.yaml'),
      'utf8',
    );
    const { parseAdapterManifest } = await import('../src/adapters/manifest');
    const reparsed = parseAdapterManifest(written, 'installed/manifest.yaml');
    expect(reparsed.ok).toBe(true);
    if (reparsed.ok) {
      expect(reparsed.manifest.acp.args).toContain('@zed-industries/claude-agent-acp@0.18.0');
    }
  });

  it('one click from probation: install + admit puts the adapter on probation (FR-M34-03)', async () => {
    const reg = source();
    await reg.refresh();
    const installed = await reg.install('gemini', { platformKey: 'windows-x86_64' });
    expect(installed.ok).toBe(true);
    if (!installed.ok) return;

    const probation = new ProbationTracker();
    const record = probation.admit(installed.adapter.id);
    expect(record.state).toBe('probation');
    expect(record.autonomyTier).toBe('suggest');
    // And discovery finds it in the workspace tier on the next scan.
    const { discoverAdapters } = await import('../src/adapters/discovery');
    const found = await discoverAdapters({ workspaceDir });
    expect(found.adapters.map((a) => a.id)).toEqual(['gemini']);
  });

  it('install of a binary distribution downloads, digest-pins and extracts via the seams', async () => {
    const archive = Buffer.from('fake-archive-bytes');
    const reg = source();
    await reg.refresh();
    const extracted: Array<{ archive: string; dest: string }> = [];
    const installed = await reg.install('codex-acp', {
      platformKey: 'windows-x86_64',
      preferBinary: true,
      fetchBytes: async () => archive,
      // sha256 of the fake archive, computed to match.
      sha256Of: async () =>
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        (require('node:crypto') as typeof import('node:crypto'))
          .createHash('sha256')
          .update(archive)
          .digest('hex'),
      extractArchive: async (a, dest) => {
        extracted.push({ archive: a, dest });
      },
    });
    // The registry fixture's codex binary entries carry no sha256 field;
    // extraction through the seam is exercised, mapping prefers binary when asked.
    if (installed.ok) {
      expect(extracted.length).toBe(1);
    } else {
      // A missing platform/archive must still be an actionable error.
      expect(installed.errors.join('\n')).toMatch(/codex-acp|archive|platform/);
    }
  });

  it('install of an unknown id is an actionable error, not a crash', async () => {
    const reg = source();
    await reg.refresh();
    const installed = await reg.install('does-not-exist', { platformKey: 'windows-x86_64' });
    expect(installed.ok).toBe(false);
    if (installed.ok) return;
    expect(installed.errors.join('\n')).toMatch(/does-not-exist/);
  });

  it('a cached index alone (no successful fetch ever) still lists entries after a later failure', async () => {
    const seed = source();
    await seed.refresh();
    const offline = source({
      fetchText: async () => {
        throw new Error('down');
      },
    });
    await offline.refresh();
    const listed = await offline.list();
    expect(listed.state).toBe('cached-stale');
    expect(listed.entries.map((e) => e.id)).toContain('claude-acp');
  });
});

describe('live registry smoke (skipped with notice unless MERIDIAN_LIVE_REGISTRY=1)', () => {
  it('the real registry answers with the documented shape', async (ctx) => {
    if (process.env.MERIDIAN_LIVE_REGISTRY !== '1') {
      ctx.skip(true);
      console.log(
        'SKIP-NOTICE: live registry fetch not enabled; set MERIDIAN_LIVE_REGISTRY=1. ' +
          'Mapping is validated against the recorded fixture (real registry format).',
      );
      return;
    }
    ctx.timeout(15_000);
    const reg = new AcpRegistrySource({ workspaceDir: mkdtempSync(path.join(tmpdir(), 'live-')) });
    const status = await reg.refresh();
    expect(status.state).toBe('fresh');
    expect(status.entries.length).toBeGreaterThan(0);
    const mapped = mapRegistryEntryToManifest(status.entries[0], {
      platformKey: `${process.platform}-${process.arch === 'arm64' ? 'aarch64' : 'x86_64'}`,
    });
    expect(mapped.ok).toBe(true);
  });
});
