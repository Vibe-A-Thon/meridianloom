import { mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchService } from '../src/workbench/service';
import type { WorkbenchSnapshot } from '../../shared/ts/workbench';
import type { IntegrationTransport } from '../src/workbench/integrations';

/**
 * Tool connections at the service boundary.
 *
 * The claim this file exists to hold: a credential the user types into the
 * Integrations tab reaches the OS keychain and nothing else. Not the
 * workspace state file, not a snapshot, not an export, not a log. Everything
 * else here — probing, disabling, unbinding on removal — is the behaviour the
 * GUI depends on.
 */

/** A stand-in keychain, so the test can assert exactly what was stored. */
function keychain() {
  const store = new Map<string, string>();
  return {
    store,
    get: async (key: string) => store.get(key),
    store_: async (key: string, value: string) => void store.set(key, value),
    delete: async (key: string) => void store.delete(key),
  };
}

const services: WorkbenchService[] = [];
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
});

async function setup(transport?: IntegrationTransport) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-integrations-'));
  const keys = keychain();
  const service = new WorkbenchService({
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ['flight-recorder', 'governor'],
    sidecar: () => ({ request: async () => ({ entries: [] }) }),
    humanApprover: async () => ({ outcome: 'cancelled' }),
    secrets: {
      get: keys.get,
      store: keys.store_,
      delete: keys.delete,
    },
    transport,
  });
  services.push(service);
  const snapshot = async () =>
    (await service.request({ action: 'snapshot' })) as WorkbenchSnapshot;
  return { root, service, snapshot, keys };
}

const gitlab = (over: Record<string, unknown> = {}) => ({
  id: 'gitlab-prod',
  integrationId: 'gitlab',
  name: 'Production GitLab',
  config: { baseUrl: 'https://gitlab.example.com', projectId: '42' },
  secrets: { token: 'glpat-supersecret-value' },
  ...over,
});

function transport(handler: (url: string) => unknown): IntegrationTransport {
  return {
    async http(request) {
      const body = handler(request.url);
      if (body instanceof Error) throw body;
      return { status: 200, ok: true, text: JSON.stringify(body) };
    },
    async exec() {
      return { code: 0, stdout: '', stderr: '' };
    },
  };
}

describe('saving a connection', () => {
  it('puts the credential in the keychain and nowhere near the workspace', async () => {
    const { service, snapshot, root, keys } = await setup();
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });

    // In the keychain, namespaced by connection.
    expect(keys.store.get('meridianLoom.integration.gitlab-prod.token')).toBe(
      'glpat-supersecret-value',
    );

    // Not in the snapshot — not even redacted, because a redacted secret
    // still tells you its length.
    const state = await snapshot();
    expect(JSON.stringify(state)).not.toContain('glpat-supersecret-value');
    expect(state.integrations[0].secretKeys).toEqual(['token']);
    expect(state.integrations[0].config.baseUrl).toBe('https://gitlab.example.com');

    // Not on disk.
    const stored = await readFile(
      path.join(root, '.meridian/workbench/state.json'),
      'utf8',
    );
    expect(stored).not.toContain('glpat-supersecret-value');
    expect(stored).toContain('gitlab-prod');
  });

  it('keeps an existing credential when the field is left empty on edit', async () => {
    const { service, keys } = await setup();
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    await service.request({
      action: 'integration/save',
      params: {
        connection: gitlab({ name: 'Renamed', secrets: { token: '' } }),
      },
    });
    expect(keys.store.get('meridianLoom.integration.gitlab-prod.token')).toBe(
      'glpat-supersecret-value',
    );
  });

  it('refuses a required credential that was never supplied', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'integration/save',
        params: { connection: gitlab({ secrets: {} }) },
      }),
    ).rejects.toThrow(/Personal access token/);
  });

  it('refuses a credential field the integration does not have', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'integration/save',
        params: { connection: gitlab({ secrets: { token: 'x', sneaky: 'y' } }) },
      }),
    ).rejects.toThrow(/no credential field called 'sneaky'/);
  });

  it('refuses an unknown integration rather than storing a stub', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'integration/save',
        params: { connection: gitlab({ integrationId: 'skynet' }) },
      }),
    ).rejects.toThrow(/not an integration Meridian knows about/);
  });

  it('refuses a URL that is not http or https', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'integration/save',
        params: {
          connection: gitlab({
            config: { baseUrl: 'file:///etc/passwd', projectId: '1' },
          }),
        },
      }),
    ).rejects.toThrow(/http or https/);
  });

  it('names the missing required field instead of saving a broken connection', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'integration/save',
        params: {
          connection: gitlab({
            config: { baseUrl: 'https://gitlab.example.com', projectId: '' },
          }),
        },
      }),
    ).rejects.toThrow(/needs Project/);
  });

  it('refuses to store a credential at all when there is no keychain', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-nokeys-'));
    const service = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ['flight-recorder'],
      sidecar: () => undefined,
    });
    services.push(service);
    // Falling back to the workspace file would be the tempting behaviour and
    // the wrong one; refusing is the promise the product makes.
    await expect(
      service.request({ action: 'integration/save', params: { connection: gitlab() } }),
    ).rejects.toThrow(/keychain is unavailable/);
  });
});

describe('probing a connection', () => {
  it('records what answered, with a latency, on the connection', async () => {
    const { service, snapshot } = await setup(
      transport(() => ({ version: '17.2.1' })),
    );
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    await service.request({ action: 'integration/probe', params: { id: 'gitlab-prod' } });

    const probe = (await snapshot()).integrations[0].lastProbe;
    expect(probe?.ok).toBe(true);
    expect(probe?.detail).toContain('17.2.1');
    expect(typeof probe?.latencyMs).toBe('number');
    expect(probe?.at).toMatch(/^\d{4}-/);
  });

  it('records a failure as a recorded fact, not as a thrown request', async () => {
    const { service, snapshot } = await setup(
      transport(() => new Error('getaddrinfo ENOTFOUND gitlab.example.com')),
    );
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    // The request resolves; the *connection* is what failed, and the user
    // needs to see why on the card rather than as an exception banner.
    await service.request({ action: 'integration/probe', params: { id: 'gitlab-prod' } });
    const probe = (await snapshot()).integrations[0].lastProbe;
    expect(probe?.ok).toBe(false);
    expect(probe?.detail).toContain('ENOTFOUND');
  });

  it('never records the credential in the probe detail', async () => {
    const { service, snapshot, root } = await setup(
      transport(() => new Error('rejected token glpat-supersecret-value')),
    );
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    await service.request({ action: 'integration/probe', params: { id: 'gitlab-prod' } });
    expect((await snapshot()).integrations[0].lastProbe?.detail).not.toContain(
      'glpat-supersecret-value',
    );
    const stored = await readFile(
      path.join(root, '.meridian/workbench/state.json'),
      'utf8',
    );
    expect(stored).not.toContain('glpat-supersecret-value');
  });
});

describe('reading through a connection', () => {
  it('returns rows without touching the workspace revision', async () => {
    const { service, snapshot } = await setup(
      transport((url) =>
        url.includes('/pipelines')
          ? [{ id: 9, ref: 'main', status: 'success', updated_at: 'now' }]
          : { version: '17.2.1' },
      ),
    );
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    const before = (await snapshot()).revision;
    const result = (await service.request({
      action: 'integration/read',
      params: { id: 'gitlab-prod', operationId: 'pipelines' },
    })) as { rows: unknown[] };

    expect(result.rows).toHaveLength(1);
    // Looking at GitLab is not a change to your workspace; recording one
    // would make the revision counter — and the change event — lie.
    expect((await snapshot()).revision).toBe(before);
  });

  it('refuses to read through a disabled connection', async () => {
    const { service } = await setup(transport(() => []));
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    await service.request({
      action: 'integration/toggle',
      params: { id: 'gitlab-prod', enabled: false },
    });
    await expect(
      service.request({
        action: 'integration/read',
        params: { id: 'gitlab-prod', operationId: 'pipelines' },
      }),
    ).rejects.toThrow(/disabled/);
  });
});

describe('removing a connection', () => {
  it('deletes its credentials from the keychain too', async () => {
    const { service, keys } = await setup();
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    expect(keys.store.size).toBe(1);
    await service.request({
      action: 'integration/remove',
      params: { id: 'gitlab-prod' },
    });
    // Leaving keychain entries behind for a connection the user deleted is a
    // quiet betrayal of what "remove" means.
    expect(keys.store.size).toBe(0);
  });

  it('unbinds it from every agent that could reach it', async () => {
    const { service, snapshot } = await setup();
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    await service.request({
      action: 'agent/save',
      params: {
        agent: {
          id: 'atlas',
          name: 'Atlas',
          role: 'developer',
          description: '',
          vendor: 'custom',
          version: '1.0.0',
          command: 'atlas-acp',
          args: [],
          instructions: '',
          permissions: ['read'],
          trainable: ['memory'],
          phases: [],
          skillIds: [],
          instructionIds: [],
          integrationIds: [],
        },
      },
    });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', integrationIds: ['gitlab-prod'] },
    });
    expect((await snapshot()).agents[0].integrationIds).toEqual(['gitlab-prod']);

    await service.request({
      action: 'integration/remove',
      params: { id: 'gitlab-prod' },
    });
    expect((await snapshot()).agents[0].integrationIds).toEqual([]);
  });

  it('refuses to bind an agent to a connection that does not exist', async () => {
    const { service } = await setup();
    await service.request({
      action: 'agent/save',
      params: {
        agent: {
          id: 'atlas',
          name: 'Atlas',
          role: 'developer',
          description: '',
          vendor: 'custom',
          version: '1.0.0',
          command: 'atlas-acp',
          args: [],
          instructions: '',
          permissions: ['read'],
          trainable: ['memory'],
          phases: [],
          skillIds: [],
          instructionIds: [],
          integrationIds: [],
        },
      },
    });
    await expect(
      service.request({
        action: 'agent/assign',
        params: { id: 'atlas', integrationIds: ['nope'] },
      }),
    ).rejects.toThrow(/no longer exists/);
  });
});

describe('backward compatibility', () => {
  it('loads a state.json written before integrations existed', async () => {
    const { service, snapshot, root } = await setup();
    await service.request({
      action: 'integration/save',
      params: { connection: gitlab() },
    });
    const file = path.join(root, '.meridian/workbench/state.json');
    const revisionBefore = JSON.parse(await readFile(file, 'utf8')).revision;

    service.dispose();
    services.length = 0;

    // dispose() bumps the revision and persists WITHOUT being awaitable —
    // it is a fire-and-forget `void this.serialize(...)`. Rewriting the file
    // straight after the call is a race: under load the pending write lands
    // afterwards and puts the integrations key back, and the test then fails
    // claiming a legacy file was read wrongly when nothing was read wrongly
    // at all. Wait for that write to land before touching the file.
    for (let attempt = 0; attempt < 200; attempt += 1) {
      const current = JSON.parse(await readFile(file, 'utf8'));
      if (current.revision > revisionBefore) break;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    // Rewrite the file without the key, as an older build would have left it.
    const state = JSON.parse(await readFile(file, 'utf8'));
    delete state.integrations;
    const { writeFile } = await import('node:fs/promises');
    await writeFile(file, JSON.stringify(state), 'utf8');

    const reopened = new WorkbenchService({
      workspaceDir: () => root,
      trusted: () => true,
      enabledTiers: () => ['flight-recorder'],
      sidecar: () => undefined,
    });
    services.push(reopened);
    const loaded = (await reopened.request({
      action: 'snapshot',
    })) as WorkbenchSnapshot;
    expect(loaded.integrations).toEqual([]);
    void snapshot;
    void vi;
  }, 10_000);
});
