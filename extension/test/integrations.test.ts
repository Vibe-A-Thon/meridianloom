import { describe, expect, it, vi } from 'vitest';
import {
  INTEGRATIONS,
  integrationById,
  type IntegrationConnection,
} from '../../shared/ts/integrations';
import {
  probeIntegration,
  readIntegration,
  redact,
  type ExecResult,
  type HttpRequest,
  type IntegrationTransport,
} from '../src/workbench/integrations';

/**
 * Reaching real systems, without a network.
 *
 * The transport is injected, so these tests assert the two things that
 * actually matter and cannot be checked against a live endpoint in CI: that
 * Meridian builds the right request and reads the answer correctly, and that
 * it never lies about what came back — no green light for a dead connection,
 * no credential in an error message, no write disguised as a read.
 */

const connection = (
  integrationId: string,
  config: Record<string, string> = {},
  over: Partial<IntegrationConnection> = {},
): IntegrationConnection => ({
  id: `${integrationId}-1`,
  integrationId,
  name: `${integrationId} test`,
  config,
  enabled: true,
  secretKeys: ['token'],
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: '2026-09-09T00:00:00Z',
  ...over,
});

function transport(
  http: (request: HttpRequest) => { status?: number; body: unknown } | Error,
  exec?: (command: string, args: string[]) => ExecResult | Error,
): IntegrationTransport & { requests: HttpRequest[]; commands: string[][] } {
  const requests: HttpRequest[] = [];
  const commands: string[][] = [];
  return {
    requests,
    commands,
    async http(request) {
      requests.push(request);
      const result = http(request);
      if (result instanceof Error) throw result;
      const status = result.status ?? 200;
      return {
        status,
        ok: status >= 200 && status < 300,
        text: typeof result.body === 'string' ? result.body : JSON.stringify(result.body),
      };
    },
    async exec(command, args) {
      commands.push([command, ...args]);
      const result = exec?.(command, args);
      if (result instanceof Error) throw result;
      return result ?? { code: 0, stdout: '', stderr: '' };
    },
  };
}

const secret = (value = 'tok-abcdef123456') => vi.fn(async () => value);
/** A connection with nothing in the keychain. Separate from `secret()`
    because passing undefined there would hit the default parameter. */
const noSecret = () => vi.fn(async (): Promise<string | undefined> => undefined);

// --- the registry itself -------------------------------------------------

describe('the integration registry', () => {
  it('names every system the tool claims to reach, each with a reader', () => {
    const ids = INTEGRATIONS.map((entry) => entry.id);
    for (const expected of [
      'gitlab',
      'github',
      'jira',
      'jenkins',
      'sonarqube',
      'postman',
      'docker',
      'kubernetes',
      'openshift',
      'kafka',
      'slack',
      'datadog',
      'grafana',
      'kibana',
      'aws',
      'control-m',
      'chrome',
    ])
      expect(ids, `${expected} is missing from the catalogue`).toContain(expected);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every definition states what a successful probe proves, and offers a read', () => {
    for (const definition of INTEGRATIONS) {
      expect(definition.probeLabel.length, definition.id).toBeGreaterThan(10);
      // "it works" is exactly the claim the probe label exists to avoid.
      expect(definition.probeLabel.toLowerCase()).not.toBe('it works');
      expect(definition.operations.length, definition.id).toBeGreaterThan(0);
      for (const operation of definition.operations)
        expect(operation.columns.length, `${definition.id}/${operation.id}`).toBeGreaterThan(0);
    }
  });

  it('a CLI integration names the binary it needs, so a failure is diagnosable', () => {
    for (const definition of INTEGRATIONS.filter((entry) => entry.transport === 'cli'))
      expect(definition.binary, definition.id).toBeTruthy();
  });
});

// --- probes --------------------------------------------------------------

describe('probing', () => {
  it('reports what answered rather than a bare success', async () => {
    const io = transport(() => ({ body: { version: '17.2.1' } }));
    const result = await probeIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: '7' }),
      io,
      secret(),
    );
    expect(result.ok).toBe(true);
    expect(result.detail).toContain('17.2.1');
    expect(io.requests[0].url).toBe('https://gitlab.example.com/api/v4/version');
    expect(io.requests[0].headers?.['PRIVATE-TOKEN']).toBe('tok-abcdef123456');
  });

  it('returns a failure as a result, not an exception, with the status in it', async () => {
    const io = transport(() => ({ status: 401, body: '401 Unauthorized' }));
    const result = await probeIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: '7' }),
      io,
      secret(),
    );
    expect(result.ok).toBe(false);
    expect(result.code).toBe(401);
    expect(result.detail).toContain('401');
  });

  it('never lets a credential reach the failure message', async () => {
    // A surprising number of HTTP clients echo the request back in an error.
    const io = transport(() => new Error('connect failed for token=tok-abcdef123456'));
    const result = await probeIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: '7' }),
      io,
      secret('tok-abcdef123456'),
    );
    expect(result.ok).toBe(false);
    expect(result.detail).not.toContain('tok-abcdef123456');
    expect(result.detail).toContain('«redacted»');
  });

  it('refuses to call a Slack ok:false a success', async () => {
    // Slack answers HTTP 200 with ok:false. Treating that as reachable is the
    // classic way an integrations page shows green for a dead connection.
    const io = transport(() => ({ body: { ok: false, error: 'invalid_auth' } }));
    const result = await probeIntegration(connection('slack'), io, secret());
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('invalid_auth');
  });

  it('refuses to call a SonarQube DOWN a success', async () => {
    const io = transport(() => ({ body: { status: 'DOWN', version: '10.5' } }));
    const result = await probeIntegration(
      connection('sonarqube', { baseUrl: 'https://sonar.example.com', projectKey: 'svc' }),
      io,
      secret(),
    );
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('DOWN');
  });

  it('says the docker CLI answered but no daemon did', async () => {
    const io = transport(
      () => ({ body: {} }),
      () => ({ code: 0, stdout: JSON.stringify({ Client: { Version: '27.0' } }), stderr: '' }),
    );
    const result = await probeIntegration(connection('docker'), io, noSecret());
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('no daemon');
  });

  it('reports a non-JSON body as a proxy or login page, not as a parse error', async () => {
    const io = transport(() => ({ body: '<html><title>Sign in</title></html>' }));
    const result = await probeIntegration(
      connection('grafana', { baseUrl: 'https://grafana.example.com' }),
      io,
      secret(),
    );
    expect(result.ok).toBe(false);
    expect(result.detail).toMatch(/proxy or login page/);
  });

  it('names the missing credential instead of failing obscurely', async () => {
    const io = transport(() => ({ body: {} }));
    const result = await probeIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: '7' }),
      io,
      noSecret(),
    );
    expect(result.ok).toBe(false);
    expect(result.detail).toContain('Personal access token');
  });

  it('refuses a URL that is not http or https before dialling it', async () => {
    const io = transport(() => ({ body: {} }));
    const result = await probeIntegration(
      connection('grafana', { baseUrl: 'file:///etc/passwd' }),
      io,
      secret(),
    );
    expect(result.ok).toBe(false);
    expect(io.requests).toHaveLength(0);
  });
});

// --- reads ---------------------------------------------------------------

describe('reading', () => {
  it('maps GitLab pipelines onto rows with an honest state per row', async () => {
    const io = transport(() => ({
      body: [
        { id: 1, ref: 'main', status: 'success', updated_at: 'now', web_url: 'u1' },
        { id: 2, ref: 'fix', status: 'failed', updated_at: 'now', web_url: 'u2' },
        { id: 3, ref: 'wip', status: 'running', updated_at: 'now' },
      ],
    }));
    const result = await readIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: 'g%2Fp' }),
      'pipelines',
      io,
      secret(),
    );
    expect(result.rows.map((row) => row.state)).toEqual(['ok', 'fail', 'warn']);
    expect(result.columns).toEqual(['Pipeline', 'Ref', 'Status', 'Updated']);
    expect(result.rows[0].href).toBe('u1');
    expect(result.detail).toContain('3 pipelines');
  });

  it('excludes pull requests from the GitHub issues read, as GitHub does not', async () => {
    const io = transport(() => ({
      body: [
        { number: 1, title: 'A bug', state: 'open', assignees: [] },
        { number: 2, title: 'A PR', state: 'open', assignees: [], pull_request: { url: 'x' } },
      ],
    }));
    const result = await readIntegration(
      connection('github', { baseUrl: 'https://api.github.com', repo: 'o/r' }),
      'issues',
      io,
      secret(),
    );
    expect(result.rows).toHaveLength(1);
    expect(result.detail).toContain('pull requests excluded');
  });

  it('computes pod readiness and restarts from the kubectl payload', async () => {
    const payload = {
      items: [
        {
          metadata: { name: 'api-1' },
          status: {
            phase: 'Running',
            containerStatuses: [{ ready: true, restartCount: 0 }],
          },
        },
        {
          metadata: { name: 'api-2' },
          status: {
            phase: 'Running',
            containerStatuses: [
              { ready: true, restartCount: 3 },
              { ready: false, restartCount: 0 },
            ],
          },
        },
        {
          metadata: { name: 'job-1' },
          status: { phase: 'Failed', containerStatuses: [] },
        },
      ],
    };
    const io = transport(
      () => ({ body: {} }),
      () => ({ code: 0, stdout: JSON.stringify(payload), stderr: '' }),
    );
    const result = await readIntegration(
      connection('kubernetes', { namespace: 'prod', context: 'live' }),
      'pods',
      io,
      noSecret(),
    );
    expect(result.rows[0].cells).toEqual(['api-1', '1/1', 'Running', '0']);
    // Ready but restarting is not healthy, and not failing either.
    expect(result.rows[1].state).toBe('fail');
    expect(result.rows[2].state).toBe('fail');
    expect(io.commands[0]).toEqual([
      'kubectl',
      '--context',
      'live',
      '-n',
      'prod',
      'get',
      'pods',
      '-o',
      'json',
    ]);
  });

  it('passes the configured profile and region to the AWS CLI', async () => {
    const io = transport(
      () => ({ body: {} }),
      () => ({
        code: 0,
        stdout: JSON.stringify({ Account: '1234', Arn: 'arn:aws:iam::1234:user/ci' }),
        stderr: '',
      }),
    );
    const result = await readIntegration(
      connection('aws', { profile: 'prod', region: 'eu-west-1' }),
      'identity',
      io,
      noSecret(),
    );
    expect(io.commands[0]).toEqual([
      'aws',
      'sts',
      'get-caller-identity',
      '--output',
      'json',
      '--profile',
      'prod',
      '--region',
      'eu-west-1',
    ]);
    expect(result.rows.map((row) => row.cells[0])).toEqual(['Account', 'Arn']);
  });

  it('separates Datadog monitors that are alerting from the full list', async () => {
    const body = [
      { id: 1, name: 'CPU', type: 'metric', overall_state: 'OK', tags: [] },
      { id: 2, name: 'Errors', type: 'log', overall_state: 'Alert', tags: ['team:api'] },
      { id: 3, name: 'Gap', type: 'metric', overall_state: 'No Data', tags: [] },
    ];
    const io = transport(() => ({ body }));
    const all = await readIntegration(
      connection('datadog', { site: 'datadoghq.eu' }),
      'monitors',
      io,
      secret(),
    );
    const alerting = await readIntegration(
      connection('datadog', { site: 'datadoghq.eu' }),
      'alerting',
      io,
      secret(),
    );
    expect(all.rows).toHaveLength(3);
    expect(alerting.rows).toHaveLength(2);
    expect(alerting.detail).toContain('2 of 3');
    expect(io.requests[0].url).toContain('api.datadoghq.eu');
  });

  it('caps a large result and says it was capped', async () => {
    const io = transport(() => ({
      body: Array.from({ length: 250 }, (_, index) => ({
        id: index,
        ref: 'main',
        status: 'success',
        updated_at: 'now',
      })),
    }));
    const result = await readIntegration(
      connection('gitlab', { baseUrl: 'https://gitlab.example.com', projectId: '7' }),
      'pipelines',
      io,
      secret(),
    );
    expect(result.rows).toHaveLength(100);
    expect(result.truncated).toBe(true);
  });

  it('names the reads a system offers when asked for one it does not have', async () => {
    const io = transport(() => ({ body: [] }));
    await expect(
      readIntegration(
        connection('chrome', { baseUrl: 'http://127.0.0.1:9222' }),
        'restart-everything',
        io,
        noSecret(),
      ),
    ).rejects.toThrow(/targets/);
  });

  it('makes no write request for any read operation in the catalogue', async () => {
    // The whole surface is read-only for this pass. If a handler ever starts
    // POSTing, this fails before anyone's production system finds out.
    for (const definition of INTEGRATIONS.filter((entry) => entry.transport === 'http')) {
      const io = transport(() => ({ body: bodyFor(definition.id) }));
      for (const operation of definition.operations) {
        try {
          await readIntegration(
            connection(definition.id, configFor(definition.id)),
            operation.id,
            io,
            secret(),
          );
        } catch {
          // A mapping failure against a stub body is fine; the request the
          // handler made before failing is what this test is inspecting.
        }
      }
      for (const request of io.requests)
        expect(
          request.method ?? 'GET',
          `${definition.id} used a non-GET method`,
        ).toBe('GET');
    }
  });
});

function configFor(id: string): Record<string, string> {
  const definition = integrationById(id)!;
  const config: Record<string, string> = {};
  for (const field of definition.fields)
    if (field.kind !== 'secret')
      config[field.key] =
        field.kind === 'url' ? 'https://example.test' : (field.placeholder ?? 'x') || 'x';
  return config;
}

function bodyFor(id: string): unknown {
  // Enough shape that the mappers reach their request, whatever they expect.
  if (id === 'slack') return { ok: true, channels: [], user: 'u', team: 't' };
  if (id === 'jira') return { values: [], issues: [], displayName: 'A' };
  if (id === 'postman') return { collections: [], monitors: [], user: { username: 'a' } };
  if (id === 'jenkins') return { jobs: [], nodeName: 'controller' };
  if (id === 'sonarqube')
    return { status: 'UP', issues: [], total: 0, projectStatus: { status: 'OK', conditions: [] } };
  if (id === 'kibana') return { status: { core: {}, plugins: {} }, data_view: [], version: {} };
  if (id === 'control-m') return { statuses: [], returned: 0 };
  if (id === 'github') return { workflow_runs: [] };
  return [];
}

// --- redaction -----------------------------------------------------------

describe('redact', () => {
  it('removes a known secret wherever it appears', () => {
    expect(redact('failed with tok-abcdef123456 at the end', ['tok-abcdef123456'])).toBe(
      'failed with «redacted» at the end',
    );
  });

  it('also strips credential-shaped text it was never told about', () => {
    expect(redact('Authorization: Bearer eyJhbGciOi', [])).toContain('«redacted»');
    expect(redact('?api_key=zzzz', [])).toContain('«redacted»');
  });

  it('leaves a short value alone rather than mangling ordinary words', () => {
    expect(redact('the region is eu', ['eu'])).toBe('the region is eu');
  });
});
