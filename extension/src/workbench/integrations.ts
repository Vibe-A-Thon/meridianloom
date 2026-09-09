import { execFile } from 'node:child_process';
import {
  INTEGRATION_READ_LIMIT,
  integrationById,
  type IntegrationConnection,
  type IntegrationDefinition,
  type IntegrationReadResult,
  type IntegrationRow,
  type IntegrationRowState,
} from '../../../shared/ts/integrations';

/**
 * Reaching the systems delivery actually runs on.
 *
 * Everything in this file is a **read**. Nothing here creates an issue,
 * triggers a pipeline, posts a message or restarts a workload. That is a
 * deliberate boundary for this pass, not an oversight: a tool that can change
 * production has to earn that through review and an explicit human gate, and
 * until it has, the honest capability is to look.
 *
 * Three further rules hold throughout:
 *
 *  - Secrets arrive as a lookup function backed by the OS keychain. They are
 *    never stored in the workspace, never logged, and `redact()` strips them
 *    from any error before it reaches the interface.
 *  - Every call is bounded: a timeout, a response-size cap, and a row limit.
 *    A misconfigured endpoint fails in seconds with a sentence, rather than
 *    hanging the panel.
 *  - The transport is injectable, so the whole surface is testable without a
 *    network or a cluster. Production wires `defaultTransport()`.
 */

export interface HttpRequest {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  timeoutMs?: number;
}

export interface HttpResponse {
  status: number;
  ok: boolean;
  text: string;
}

export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
}

export interface IntegrationTransport {
  http(request: HttpRequest): Promise<HttpResponse>;
  exec(
    command: string,
    args: string[],
    options?: { env?: Record<string, string>; timeoutMs?: number },
  ): Promise<ExecResult>;
}

/** Ceiling on a single response body, so a huge payload cannot exhaust memory. */
const MAX_RESPONSE_BYTES = 8_000_000;
const DEFAULT_TIMEOUT_MS = 15_000;

export function defaultTransport(): IntegrationTransport {
  return {
    async http(request) {
      const response = await fetch(request.url, {
        method: request.method ?? 'GET',
        headers: request.headers,
        body: request.body,
        signal: AbortSignal.timeout(request.timeoutMs ?? DEFAULT_TIMEOUT_MS),
      });
      const buffer = await response.arrayBuffer();
      if (buffer.byteLength > MAX_RESPONSE_BYTES)
        throw new Error(
          `That endpoint returned ${Math.round(buffer.byteLength / 1_000_000)} MB, ` +
            'more than Meridian will read in one call.',
        );
      return {
        status: response.status,
        ok: response.ok,
        text: Buffer.from(buffer).toString('utf8'),
      };
    },
    exec(command, args, options) {
      return new Promise((resolve, reject) => {
        execFile(
          command,
          args,
          {
            timeout: options?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
            maxBuffer: MAX_RESPONSE_BYTES,
            windowsHide: true,
            env: { ...process.env, ...options?.env },
          },
          (error, stdout, stderr) => {
            if (error && (error as NodeJS.ErrnoException).code === 'ENOENT') {
              reject(
                new Error(
                  `${command} is not on this machine's PATH. Install it, or ` +
                    'point the connection at the directory that holds it.',
                ),
              );
              return;
            }
            const code =
              error && typeof (error as { code?: unknown }).code === 'number'
                ? ((error as { code: number }).code ?? 1)
                : error
                  ? 1
                  : 0;
            resolve({ code, stdout: String(stdout), stderr: String(stderr) });
          },
        );
      });
    },
  };
}

export interface IntegrationContext {
  definition: IntegrationDefinition;
  connection: IntegrationConnection;
  transport: IntegrationTransport;
  /** Reads one secret field from the keychain. Undefined when never set. */
  secret(key: string): Promise<string | undefined>;
}

// ——— helpers ————————————————————————————————————————————————————————————

function config(ctx: IntegrationContext, key: string): string {
  return (ctx.connection.config[key] ?? '').trim();
}

function requireConfig(ctx: IntegrationContext, key: string): string {
  const value = config(ctx, key);
  if (!value) {
    const field = ctx.definition.fields.find((entry) => entry.key === key);
    throw new Error(
      `This connection needs ${field?.label ?? key} before it can be used.`,
    );
  }
  return value;
}

async function requireSecret(
  ctx: IntegrationContext,
  key: string,
): Promise<string> {
  const value = await ctx.secret(key);
  if (!value) {
    const field = ctx.definition.fields.find((entry) => entry.key === key);
    throw new Error(
      `This connection has no stored ${field?.label ?? key}. Edit it and supply one.`,
    );
  }
  return value;
}

function base(ctx: IntegrationContext, fallback = ''): string {
  const value = (config(ctx, 'baseUrl') || fallback).replace(/\/+$/, '');
  if (!value)
    throw new Error('This connection needs a URL before it can be used.');
  if (!/^https?:\/\//i.test(value))
    throw new Error(`"${value}" is not an http or https URL.`);
  return value;
}

/**
 * Strip anything secret-shaped from a message before it is shown or stored.
 * Errors from HTTP clients and CLIs regularly echo the credential back.
 */
export function redact(message: string, secrets: readonly string[]): string {
  let out = message;
  for (const value of secrets)
    if (value && value.length >= 6) out = out.split(value).join('«redacted»');
  return out
    .replace(/(Bearer|Basic|token|api[-_]?key|password)[=:\s]+\S+/gi, '$1 «redacted»')
    .slice(0, 2_000);
}

async function getJson(
  ctx: IntegrationContext,
  url: string,
  headers: Record<string, string>,
  method = 'GET',
  body?: string,
): Promise<unknown> {
  const response = await ctx.transport.http({ url, headers, method, body });
  if (!response.ok) {
    throw new HttpFailure(
      response.status,
      `${method} ${strip(url)} returned ${response.status}${
        response.text ? `: ${firstLine(response.text)}` : '.'
      }`,
    );
  }
  try {
    return JSON.parse(response.text) as unknown;
  } catch {
    throw new Error(
      `${strip(url)} answered with ${response.status} but the body was not JSON. ` +
        'That usually means a proxy or login page answered instead of the API.',
    );
  }
}

export class HttpFailure extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'HttpFailure';
  }
}

/** Query strings can carry tokens; never echo one back into the interface. */
function strip(url: string): string {
  const index = url.indexOf('?');
  return index < 0 ? url : `${url.slice(0, index)}?…`;
}

function firstLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 240);
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function obj(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function str(value: unknown, fallback = ''): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

/** Trim to the read limit and report honestly that there was more. */
function take<T>(items: T[]): { items: T[]; truncated: boolean } {
  return items.length > INTEGRATION_READ_LIMIT
    ? { items: items.slice(0, INTEGRATION_READ_LIMIT), truncated: true }
    : { items, truncated: false };
}

/** Parse one JSON document per line, as several CLIs emit. */
function jsonLines(stdout: string): Record<string, unknown>[] {
  return stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [obj(JSON.parse(line))];
      } catch {
        return [];
      }
    });
}

async function runCli(
  ctx: IntegrationContext,
  command: string,
  args: string[],
  env?: Record<string, string>,
): Promise<string> {
  const result = await ctx.transport.exec(command, args, { env });
  if (result.code !== 0) {
    const detail = firstLine(result.stderr || result.stdout) || 'no output';
    throw new Error(`${command} exited with code ${result.code}: ${detail}`);
  }
  return result.stdout;
}

/** kubectl and oc share their whole read surface; only the binary differs. */
function kubeArgs(
  ctx: IntegrationContext,
  rest: string[],
  namespaceKey: 'namespace' | 'project',
): string[] {
  const args: string[] = [];
  const context = config(ctx, 'context');
  if (context) args.push('--context', context);
  const namespace = config(ctx, namespaceKey);
  if (namespace) args.push('-n', namespace);
  return [...args, ...rest];
}

function kubeRows(
  stdout: string,
  kind: 'pods' | 'deployments' | 'events' | 'nodes',
): IntegrationRow[] {
  const items = asArray(obj(JSON.parse(stdout)).items).map(obj);
  return items.map((item) => {
    const meta = obj(item.metadata);
    const name = str(meta.name, '(unnamed)');
    if (kind === 'pods') {
      const status = obj(item.status);
      const containers = asArray(status.containerStatuses).map(obj);
      const ready = containers.filter((c) => c.ready === true).length;
      const restarts = containers.reduce(
        (sum, c) => sum + (typeof c.restartCount === 'number' ? c.restartCount : 0),
        0,
      );
      const phase = str(status.phase, 'Unknown');
      return {
        id: name,
        cells: [name, `${ready}/${containers.length}`, phase, String(restarts)],
        state:
          phase === 'Running' && ready === containers.length && containers.length > 0
            ? restarts > 0
              ? 'warn'
              : 'ok'
            : phase === 'Succeeded'
              ? 'idle'
              : 'fail',
      } satisfies IntegrationRow;
    }
    if (kind === 'deployments') {
      const status = obj(item.status);
      const desired =
        typeof obj(item.spec).replicas === 'number' ? Number(obj(item.spec).replicas) : 0;
      const ready = typeof status.readyReplicas === 'number' ? status.readyReplicas : 0;
      return {
        id: name,
        cells: [
          name,
          `${ready}/${desired}`,
          str(status.updatedReplicas, '0'),
          str(status.availableReplicas, '0'),
        ],
        state: desired === 0 ? 'idle' : ready === desired ? 'ok' : ready > 0 ? 'warn' : 'fail',
      } satisfies IntegrationRow;
    }
    if (kind === 'nodes') {
      const conditions = asArray(obj(item.status).conditions).map(obj);
      const ready = conditions.find((c) => str(c.type) === 'Ready');
      const info = obj(obj(item.status).nodeInfo);
      const roles = Object.keys(obj(meta.labels))
        .filter((label) => label.startsWith('node-role.kubernetes.io/'))
        .map((label) => label.split('/')[1])
        .join(', ');
      return {
        id: name,
        cells: [
          name,
          str(ready?.status) === 'True' ? 'Ready' : 'NotReady',
          str(info.kubeletVersion),
          roles || '—',
        ],
        state: str(ready?.status) === 'True' ? 'ok' : 'fail',
      } satisfies IntegrationRow;
    }
    const involved = obj(item.involvedObject);
    const type = str(item.type, 'Normal');
    return {
      id: `${name}`,
      cells: [
        `${str(involved.kind)}/${str(involved.name)}`,
        str(item.reason),
        firstLine(str(item.message)),
        type,
      ],
      state: type === 'Warning' ? 'warn' : 'ok',
    } satisfies IntegrationRow;
  });
}

// ——— per-integration handlers ——————————————————————————————————————————

interface Handler {
  /** Resolves with a sentence describing what answered. Throws otherwise. */
  probe(ctx: IntegrationContext): Promise<string>;
  read(
    ctx: IntegrationContext,
    operationId: string,
  ): Promise<{ rows: IntegrationRow[]; truncated: boolean; detail: string }>;
}

const gitlab: Handler = {
  async probe(ctx) {
    const token = await requireSecret(ctx, 'token');
    const version = obj(
      await getJson(ctx, `${base(ctx)}/api/v4/version`, { 'PRIVATE-TOKEN': token }),
    );
    return `GitLab ${str(version.version, 'of unknown version')} answered and accepted the token.`;
  },
  async read(ctx, operationId) {
    const token = await requireSecret(ctx, 'token');
    const project = encodeURIComponent(requireConfig(ctx, 'projectId'));
    const root = `${base(ctx)}/api/v4/projects/${project}`;
    const headers = { 'PRIVATE-TOKEN': token };
    if (operationId === 'pipelines') {
      const raw = asArray(
        await getJson(ctx, `${root}/pipelines?per_page=${INTEGRATION_READ_LIMIT}`, headers),
      ).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} pipelines from ${strip(root)}.`,
        rows: items.map((item) => ({
          id: str(item.id),
          cells: [
            `#${str(item.id)}`,
            str(item.ref),
            str(item.status),
            str(item.updated_at),
          ],
          state:
            str(item.status) === 'success'
              ? 'ok'
              : ['failed', 'canceled'].includes(str(item.status))
                ? 'fail'
                : ['running', 'pending'].includes(str(item.status))
                  ? 'warn'
                  : 'idle',
          href: str(item.web_url) || undefined,
        })),
      };
    }
    if (operationId === 'merge-requests') {
      const raw = asArray(
        await getJson(
          ctx,
          `${root}/merge_requests?state=opened&per_page=${INTEGRATION_READ_LIMIT}`,
          headers,
        ),
      ).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} open merge requests.`,
        rows: items.map((item) => ({
          id: str(item.iid),
          cells: [
            `!${str(item.iid)}`,
            str(item.title),
            str(obj(item.author).name),
            str(item.state),
          ],
          state: item.draft === true ? 'warn' : 'ok',
          href: str(item.web_url) || undefined,
        })),
      };
    }
    const raw = asArray(
      await getJson(
        ctx,
        `${root}/issues?state=opened&per_page=${INTEGRATION_READ_LIMIT}`,
        headers,
      ),
    ).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} open issues.`,
      rows: items.map((item) => ({
        id: str(item.iid),
        cells: [
          `#${str(item.iid)}`,
          str(item.title),
          str(obj(asArray(item.assignees)[0]).name, 'Unassigned'),
          str(item.state),
        ],
        state: 'ok',
        href: str(item.web_url) || undefined,
      })),
    };
  },
};

const github: Handler = {
  async probe(ctx) {
    const token = await requireSecret(ctx, 'token');
    const user = obj(
      await getJson(ctx, `${base(ctx, 'https://api.github.com')}/user`, ghHeaders(token)),
    );
    return `GitHub answered and the token identified ${str(user.login, 'an account')}.`;
  },
  async read(ctx, operationId) {
    const token = await requireSecret(ctx, 'token');
    const repo = requireConfig(ctx, 'repo');
    const root = `${base(ctx, 'https://api.github.com')}/repos/${repo}`;
    const headers = ghHeaders(token);
    if (operationId === 'workflow-runs') {
      const payload = obj(
        await getJson(ctx, `${root}/actions/runs?per_page=${INTEGRATION_READ_LIMIT}`, headers),
      );
      const raw = asArray(payload.workflow_runs).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} recent workflow runs on ${repo}.`,
        rows: items.map((item) => ({
          id: str(item.id),
          cells: [
            `#${str(item.run_number)}`,
            str(item.name),
            str(item.conclusion, str(item.status)),
            str(item.updated_at),
          ],
          state:
            str(item.conclusion) === 'success'
              ? 'ok'
              : str(item.conclusion) === 'failure'
                ? 'fail'
                : str(item.status) === 'in_progress'
                  ? 'warn'
                  : 'idle',
          href: str(item.html_url) || undefined,
        })),
      };
    }
    if (operationId === 'pull-requests') {
      const raw = asArray(
        await getJson(ctx, `${root}/pulls?state=open&per_page=${INTEGRATION_READ_LIMIT}`, headers),
      ).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} open pull requests on ${repo}.`,
        rows: items.map((item) => ({
          id: str(item.number),
          cells: [
            `#${str(item.number)}`,
            str(item.title),
            str(obj(item.user).login),
            item.draft === true ? 'draft' : str(item.state),
          ],
          state: item.draft === true ? 'warn' : 'ok',
          href: str(item.html_url) || undefined,
        })),
      };
    }
    const raw = asArray(
      await getJson(ctx, `${root}/issues?state=open&per_page=${INTEGRATION_READ_LIMIT}`, headers),
    )
      .map(obj)
      // The issues endpoint returns pull requests too; they have their own read.
      .filter((item) => item.pull_request === undefined);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} open issues on ${repo}, pull requests excluded.`,
      rows: items.map((item) => ({
        id: str(item.number),
        cells: [
          `#${str(item.number)}`,
          str(item.title),
          str(obj(asArray(item.assignees)[0]).login, 'Unassigned'),
          str(item.state),
        ],
        state: 'ok',
        href: str(item.html_url) || undefined,
      })),
    };
  },
};

function ghHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

const jira: Handler = {
  async probe(ctx) {
    const headers = await jiraHeaders(ctx);
    const me = obj(await getJson(ctx, `${base(ctx)}/rest/api/3/myself`, headers));
    return `Jira answered and named the account ${str(me.displayName, str(me.emailAddress, 'in use'))}.`;
  },
  async read(ctx, operationId) {
    const headers = await jiraHeaders(ctx);
    if (operationId === 'projects') {
      const payload = obj(
        await getJson(
          ctx,
          `${base(ctx)}/rest/api/3/project/search?maxResults=${INTEGRATION_READ_LIMIT}`,
          headers,
        ),
      );
      const raw = asArray(payload.values).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} projects visible to this account.`,
        rows: items.map((item) => ({
          id: str(item.key),
          cells: [
            str(item.key),
            str(item.name),
            str(item.projectTypeKey),
            str(obj(item.lead).displayName, '—'),
          ],
          state: 'ok',
        })),
      };
    }
    const jql = config(ctx, 'jql') || 'assignee = currentUser() AND statusCategory != Done';
    const payload = obj(
      await getJson(
        ctx,
        `${base(ctx)}/rest/api/3/search?jql=${encodeURIComponent(jql)}&maxResults=${INTEGRATION_READ_LIMIT}`,
        headers,
      ),
    );
    const raw = asArray(payload.issues).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} issues for JQL: ${jql}`,
      rows: items.map((item) => {
        const fields = obj(item.fields);
        const category = str(obj(obj(fields.status).statusCategory).key);
        return {
          id: str(item.key),
          cells: [
            str(item.key),
            str(fields.summary),
            str(obj(fields.assignee).displayName, 'Unassigned'),
            str(obj(fields.status).name),
          ],
          state: category === 'done' ? 'ok' : category === 'indeterminate' ? 'warn' : 'idle',
          href: `${base(ctx)}/browse/${str(item.key)}`,
        } satisfies IntegrationRow;
      }),
    };
  },
};

async function jiraHeaders(ctx: IntegrationContext): Promise<Record<string, string>> {
  const email = requireConfig(ctx, 'email');
  const token = await requireSecret(ctx, 'token');
  return {
    Authorization: `Basic ${Buffer.from(`${email}:${token}`).toString('base64')}`,
    Accept: 'application/json',
  };
}

const jenkins: Handler = {
  async probe(ctx) {
    const headers = await basicHeaders(ctx, 'user', 'token');
    const payload = obj(await getJson(ctx, `${base(ctx)}/api/json`, headers));
    return `Jenkins answered as "${str(payload.nodeName, 'the controller')}" and accepted the token.`;
  },
  async read(ctx) {
    const headers = await basicHeaders(ctx, 'user', 'token');
    const payload = obj(
      await getJson(
        ctx,
        `${base(ctx)}/api/json?tree=jobs[name,color,url,lastBuild[number,result,timestamp]]`,
        headers,
      ),
    );
    const raw = asArray(payload.jobs).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} jobs on this controller.`,
      rows: items.map((item) => {
        const last = obj(item.lastBuild);
        const colour = str(item.color);
        return {
          id: str(item.name),
          cells: [
            str(item.name),
            last.number === undefined ? 'never built' : `#${str(last.number)}`,
            str(last.result, colour.includes('anime') ? 'building' : '—'),
            colour,
          ],
          state: colour.startsWith('blue')
            ? 'ok'
            : colour.startsWith('red')
              ? 'fail'
              : colour.startsWith('yellow')
                ? 'warn'
                : 'idle',
          href: str(item.url) || undefined,
        } satisfies IntegrationRow;
      }),
    };
  },
};

async function basicHeaders(
  ctx: IntegrationContext,
  userKey: string,
  secretKey: string,
): Promise<Record<string, string>> {
  const user = requireConfig(ctx, userKey);
  const token = await requireSecret(ctx, secretKey);
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${token}`).toString('base64')}`,
    Accept: 'application/json',
  };
}

const sonarqube: Handler = {
  async probe(ctx) {
    const headers = await sonarHeaders(ctx);
    const status = obj(await getJson(ctx, `${base(ctx)}/api/system/status`, headers));
    if (str(status.status) !== 'UP')
      throw new Error(
        `SonarQube answered but reported status ${str(status.status, 'unknown')}, not UP.`,
      );
    return `SonarQube ${str(status.version, '')} answered and reported status UP.`.replace(
      '  ',
      ' ',
    );
  },
  async read(ctx, operationId) {
    const headers = await sonarHeaders(ctx);
    const project = requireConfig(ctx, 'projectKey');
    if (operationId === 'quality-gate') {
      const payload = obj(
        await getJson(
          ctx,
          `${base(ctx)}/api/qualitygates/project_status?projectKey=${encodeURIComponent(project)}`,
          headers,
        ),
      );
      const gate = obj(payload.projectStatus);
      const conditions = asArray(gate.conditions).map(obj);
      return {
        truncated: false,
        detail: `Quality gate for ${project}: ${str(gate.status, 'unknown')}.`,
        rows: conditions.map((item) => ({
          id: str(item.metricKey),
          cells: [
            str(item.metricKey),
            str(item.actualValue, '—'),
            `${str(item.comparator)} ${str(item.errorThreshold)}`,
            str(item.status),
          ],
          state: str(item.status) === 'OK' ? 'ok' : 'fail',
        })),
      };
    }
    const payload = obj(
      await getJson(
        ctx,
        `${base(ctx)}/api/issues/search?componentKeys=${encodeURIComponent(project)}` +
          `&resolved=false&ps=${INTEGRATION_READ_LIMIT}&s=SEVERITY&asc=false`,
        headers,
      ),
    );
    const raw = asArray(payload.issues).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${str(payload.total, String(raw.length))} unresolved issues on ${project}.`,
      rows: items.map((item) => {
        const severity = str(item.severity);
        return {
          id: str(item.key),
          cells: [
            str(item.rule),
            str(item.component).split(':').pop() ?? '',
            severity,
            str(item.type),
          ],
          state:
            severity === 'BLOCKER' || severity === 'CRITICAL'
              ? 'fail'
              : severity === 'MAJOR'
                ? 'warn'
                : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

async function sonarHeaders(ctx: IntegrationContext): Promise<Record<string, string>> {
  const token = await requireSecret(ctx, 'token');
  // SonarQube takes the token as the basic-auth username with an empty password.
  return {
    Authorization: `Basic ${Buffer.from(`${token}:`).toString('base64')}`,
    Accept: 'application/json',
  };
}

const postman: Handler = {
  async probe(ctx) {
    const key = await requireSecret(ctx, 'apiKey');
    const payload = obj(
      await getJson(ctx, 'https://api.getpostman.com/me', { 'X-Api-Key': key }),
    );
    const user = obj(payload.user);
    return `Postman answered and the key identified ${str(user.username, `account ${str(user.id)}`)}.`;
  },
  async read(ctx, operationId) {
    const key = await requireSecret(ctx, 'apiKey');
    const headers = { 'X-Api-Key': key };
    if (operationId === 'monitors') {
      const payload = obj(
        await getJson(ctx, 'https://api.getpostman.com/monitors', headers),
      );
      const raw = asArray(payload.monitors).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} monitors visible to this key.`,
        rows: items.map((item) => {
          const last = obj(obj(item.lastRun).status);
          const result = str(obj(item.lastRun).status, str(last.status, '—'));
          return {
            id: str(item.uid, str(item.id)),
            cells: [
              str(item.name),
              str(item.collectionUid),
              str(obj(item.lastRun).finishedAt, '—'),
              result,
            ],
            state: result === 'failed' ? 'fail' : result === 'success' ? 'ok' : 'idle',
          } satisfies IntegrationRow;
        }),
      };
    }
    const payload = obj(
      await getJson(ctx, 'https://api.getpostman.com/collections', headers),
    );
    const raw = asArray(payload.collections).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} collections visible to this key.`,
      rows: items.map((item) => ({
        id: str(item.uid, str(item.id)),
        cells: [
          str(item.name),
          str(item.owner),
          str(item.updatedAt, '—'),
          item.fork === undefined ? 'no' : 'yes',
        ],
        state: 'ok',
      })),
    };
  },
};

const docker: Handler = {
  async probe(ctx) {
    const stdout = await runCli(ctx, 'docker', [
      ...dockerContext(ctx),
      'version',
      '--format',
      '{{json .}}',
    ]);
    const payload = obj(JSON.parse(stdout.trim() || '{}'));
    const server = obj(payload.Server);
    if (!server.Version)
      throw new Error(
        'The docker CLI answered but no daemon did. Start Docker and try again.',
      );
    return `The Docker daemon answered, server version ${str(server.Version)}.`;
  },
  async read(ctx, operationId) {
    if (operationId === 'images') {
      const stdout = await runCli(ctx, 'docker', [
        ...dockerContext(ctx),
        'image',
        'ls',
        '--format',
        '{{json .}}',
      ]);
      const raw = jsonLines(stdout);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} local images.`,
        rows: items.map((item) => ({
          id: str(item.ID),
          cells: [str(item.Repository), str(item.Tag), str(item.Size), str(item.CreatedSince)],
          state: str(item.Tag) === '<none>' ? 'warn' : 'ok',
        })),
      };
    }
    const stdout = await runCli(ctx, 'docker', [
      ...dockerContext(ctx),
      'ps',
      '--all',
      '--format',
      '{{json .}}',
    ]);
    const raw = jsonLines(stdout);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} containers on this daemon.`,
      rows: items.map((item) => {
        const state = str(item.State);
        return {
          id: str(item.ID),
          cells: [
            str(item.Names),
            str(item.Image),
            str(item.Status),
            str(item.Ports, '—'),
          ],
          state:
            state === 'running'
              ? 'ok'
              : state === 'exited' || state === 'dead'
                ? 'fail'
                : state === 'restarting'
                  ? 'warn'
                  : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

function dockerContext(ctx: IntegrationContext): string[] {
  const context = config(ctx, 'context');
  return context ? ['--context', context] : [];
}

const kubernetes: Handler = {
  async probe(ctx) {
    const stdout = await runCli(
      ctx,
      'kubectl',
      kubeArgs(ctx, ['version', '-o', 'json'], 'namespace'),
    );
    const payload = obj(JSON.parse(stdout.trim() || '{}'));
    const server = obj(payload.serverVersion);
    if (!server.gitVersion)
      throw new Error(
        'kubectl ran but no API server answered. Check the context and your credentials.',
      );
    return `The API server answered, version ${str(server.gitVersion)}.`;
  },
  async read(ctx, operationId) {
    const kind =
      operationId === 'deployments'
        ? 'deployments'
        : operationId === 'events'
          ? 'events'
          : operationId === 'nodes'
            ? 'nodes'
            : 'pods';
    const args =
      kind === 'nodes'
        ? ['get', 'nodes', '-o', 'json']
        : kubeArgs(ctx, ['get', kind, '-o', 'json'], 'namespace');
    const stdout = await runCli(ctx, 'kubectl', kind === 'nodes' ? nodeArgs(ctx, args) : args);
    const rows = kubeRows(stdout, kind);
    const { items, truncated } = take(rows);
    return {
      truncated,
      detail: `${rows.length} ${kind} in ${config(ctx, 'namespace') || 'the default namespace'}.`,
      rows: kind === 'events' ? items.sort(warningsFirst) : items,
    };
  },
};

function nodeArgs(ctx: IntegrationContext, args: string[]): string[] {
  const context = config(ctx, 'context');
  return context ? ['--context', context, ...args] : args;
}

const warningsFirst = (a: IntegrationRow, b: IntegrationRow) =>
  (b.state === 'warn' ? 1 : 0) - (a.state === 'warn' ? 1 : 0);

const openshift: Handler = {
  async probe(ctx) {
    const who = (await runCli(ctx, 'oc', ['whoami'])).trim();
    if (!who) throw new Error('oc ran but reported no logged-in user. Run `oc login` first.');
    return `oc reached the cluster as ${who}.`;
  },
  async read(ctx, operationId) {
    if (operationId === 'pods') {
      const stdout = await runCli(
        ctx,
        'oc',
        kubeArgs(ctx, ['get', 'pods', '-o', 'json'], 'project'),
      );
      const rows = kubeRows(stdout, 'pods');
      const { items, truncated } = take(rows);
      return {
        truncated,
        detail: `${rows.length} pods in ${config(ctx, 'project') || 'the current project'}.`,
        rows: items,
      };
    }
    if (operationId === 'routes') {
      const stdout = await runCli(
        ctx,
        'oc',
        kubeArgs(ctx, ['get', 'routes', '-o', 'json'], 'project'),
      );
      const raw = asArray(obj(JSON.parse(stdout)).items).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} routes.`,
        rows: items.map((item) => {
          const spec = obj(item.spec);
          return {
            id: str(obj(item.metadata).name),
            cells: [
              str(obj(item.metadata).name),
              str(spec.host),
              str(obj(spec.to).name),
              str(obj(spec.port).targetPort, '—'),
            ],
            state: spec.tls ? 'ok' : 'warn',
            href: spec.host ? `https://${str(spec.host)}` : undefined,
          } satisfies IntegrationRow;
        }),
      };
    }
    const stdout = await runCli(
      ctx,
      'oc',
      kubeArgs(ctx, ['get', 'builds', '-o', 'json'], 'project'),
    );
    const raw = asArray(obj(JSON.parse(stdout)).items).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} builds.`,
      rows: items.map((item) => {
        const phase = str(obj(item.status).phase);
        return {
          id: str(obj(item.metadata).name),
          cells: [
            str(obj(item.metadata).name),
            str(obj(obj(obj(item.spec).strategy)).type, '—'),
            phase,
            str(obj(item.status).startTimestamp, '—'),
          ],
          state:
            phase === 'Complete'
              ? 'ok'
              : phase === 'Failed' || phase === 'Error'
                ? 'fail'
                : phase === 'Running'
                  ? 'warn'
                  : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

const kafka: Handler = {
  async probe(ctx) {
    const stdout = await runCli(ctx, kafkaBin(ctx, 'kafka-topics.sh'), kafkaArgs(ctx, ['--list']));
    const topics = stdout.split(/\r?\n/).filter((line) => line.trim()).length;
    return `The bootstrap servers answered and listed ${topics} topics.`;
  },
  async read(ctx, operationId) {
    const script =
      operationId === 'consumer-groups' ? 'kafka-consumer-groups.sh' : 'kafka-topics.sh';
    const stdout = await runCli(ctx, kafkaBin(ctx, script), kafkaArgs(ctx, ['--list']));
    const raw = stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} ${operationId === 'consumer-groups' ? 'consumer groups' : 'topics'} on ${config(ctx, 'bootstrap')}.`,
      rows: items.map((name) => ({
        id: name,
        cells: [name],
        state: name.startsWith('__') ? 'idle' : 'ok',
      })),
    };
  },
};

function kafkaBin(ctx: IntegrationContext, script: string): string {
  const dir = config(ctx, 'binDir').replace(/[\\/]+$/, '');
  return dir ? `${dir}/${script}` : script;
}

function kafkaArgs(ctx: IntegrationContext, rest: string[]): string[] {
  const args = ['--bootstrap-server', requireConfig(ctx, 'bootstrap'), ...rest];
  const commandConfig = config(ctx, 'commandConfig');
  return commandConfig ? [...args, '--command-config', commandConfig] : args;
}

const slack: Handler = {
  async probe(ctx) {
    const payload = await slackCall(ctx, 'auth.test');
    return `Slack accepted the token for ${str(payload.user, 'a user')} in ${str(payload.team, 'a workspace')}.`;
  },
  async read(ctx) {
    const payload = await slackCall(
      ctx,
      `conversations.list?limit=${INTEGRATION_READ_LIMIT}&exclude_archived=false`,
    );
    const raw = asArray(payload.channels).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} channels visible to this token.`,
      rows: items.map((item) => ({
        id: str(item.id),
        cells: [
          `#${str(item.name)}`,
          str(item.num_members, '—'),
          firstLine(str(obj(item.purpose).value, '—')),
          item.is_archived === true ? 'yes' : 'no',
        ],
        state: item.is_archived === true ? 'idle' : 'ok',
      })),
    };
  },
};

async function slackCall(
  ctx: IntegrationContext,
  method: string,
): Promise<Record<string, unknown>> {
  const token = await requireSecret(ctx, 'token');
  const payload = obj(
    await getJson(ctx, `https://slack.com/api/${method}`, {
      Authorization: `Bearer ${token}`,
    }),
  );
  // Slack answers 200 with ok:false; treating that as success is the classic
  // way an integrations page shows a green light for a dead connection.
  if (payload.ok !== true)
    throw new Error(`Slack refused the call: ${str(payload.error, 'no reason given')}.`);
  return payload;
}

const datadog: Handler = {
  async probe(ctx) {
    const headers = await datadogHeaders(ctx, false);
    const payload = obj(
      await getJson(ctx, `https://api.${datadogSite(ctx)}/api/v1/validate`, headers),
    );
    if (payload.valid !== true)
      throw new Error('Datadog answered but reported the API key as not valid.');
    return `Datadog validated the API key for ${datadogSite(ctx)}.`;
  },
  async read(ctx, operationId) {
    const headers = await datadogHeaders(ctx, true);
    const raw = asArray(
      await getJson(ctx, `https://api.${datadogSite(ctx)}/api/v1/monitor`, headers),
    ).map(obj);
    const alerting = raw.filter((item) =>
      ['Alert', 'Warn', 'No Data'].includes(str(item.overall_state)),
    );
    const source = operationId === 'alerting' ? alerting : raw;
    const { items, truncated } = take(source);
    return {
      truncated,
      detail:
        operationId === 'alerting'
          ? `${alerting.length} of ${raw.length} monitors are alerting, warning or have no data.`
          : `${raw.length} monitors on ${datadogSite(ctx)}.`,
      rows: items.map((item) => {
        const state = str(item.overall_state);
        return {
          id: str(item.id),
          cells: [
            str(item.name),
            str(item.type),
            state,
            asArray(item.tags).map((tag) => str(tag)).slice(0, 4).join(', '),
          ],
          state:
            state === 'OK'
              ? 'ok'
              : state === 'Alert'
                ? 'fail'
                : state === 'Warn' || state === 'No Data'
                  ? 'warn'
                  : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

function datadogSite(ctx: IntegrationContext): string {
  return config(ctx, 'site') || 'datadoghq.com';
}

async function datadogHeaders(
  ctx: IntegrationContext,
  needsAppKey: boolean,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'DD-API-KEY': await requireSecret(ctx, 'apiKey'),
    Accept: 'application/json',
  };
  if (needsAppKey) headers['DD-APPLICATION-KEY'] = await requireSecret(ctx, 'appKey');
  return headers;
}

const grafana: Handler = {
  async probe(ctx) {
    const headers = await bearer(ctx, 'token');
    const payload = obj(await getJson(ctx, `${base(ctx)}/api/health`, headers));
    if (str(payload.database) && str(payload.database) !== 'ok')
      throw new Error(`Grafana answered but its database is ${str(payload.database)}.`);
    return `Grafana ${str(payload.version, '')} answered its health endpoint.`.replace('  ', ' ');
  },
  async read(ctx, operationId) {
    const headers = await bearer(ctx, 'token');
    if (operationId === 'datasources') {
      const raw = asArray(await getJson(ctx, `${base(ctx)}/api/datasources`, headers)).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} data sources.`,
        rows: items.map((item) => ({
          id: str(item.uid, str(item.id)),
          cells: [
            str(item.name),
            str(item.type),
            str(item.url, '—'),
            item.isDefault === true ? 'yes' : 'no',
          ],
          state: 'ok',
        })),
      };
    }
    if (operationId === 'alert-rules') {
      const raw = asArray(
        await getJson(ctx, `${base(ctx)}/api/v1/provisioning/alert-rules`, headers),
      ).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} provisioned alert rules.`,
        rows: items.map((item) => ({
          id: str(item.uid),
          cells: [str(item.title), str(item.folderUID), str(item.ruleGroup), str(item.for, '—')],
          state: item.isPaused === true ? 'idle' : 'ok',
        })),
      };
    }
    const raw = asArray(
      await getJson(ctx, `${base(ctx)}/api/search?limit=${INTEGRATION_READ_LIMIT}`, headers),
    ).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} dashboards and folders.`,
      rows: items.map((item) => ({
        id: str(item.uid),
        cells: [
          str(item.title),
          str(item.folderTitle, '—'),
          str(item.type),
          asArray(item.tags).map((tag) => str(tag)).join(', ') || '—',
        ],
        state: str(item.type) === 'dash-folder' ? 'idle' : 'ok',
        href: str(item.url) ? `${base(ctx)}${str(item.url)}` : undefined,
      })),
    };
  },
};

async function bearer(
  ctx: IntegrationContext,
  key: string,
): Promise<Record<string, string>> {
  return {
    Authorization: `Bearer ${await requireSecret(ctx, key)}`,
    Accept: 'application/json',
  };
}

const kibana: Handler = {
  async probe(ctx) {
    const payload = obj(
      await getJson(ctx, `${base(ctx)}/api/status`, await kibanaHeaders(ctx)),
    );
    const level = str(obj(obj(payload.status).overall).level, str(obj(payload.status).overall));
    if (level && level !== 'available')
      throw new Error(`Kibana answered but reports overall level "${level}".`);
    return `Kibana ${str(obj(payload.version).number, '')} answered, overall level available.`.replace(
      '  ',
      ' ',
    );
  },
  async read(ctx, operationId) {
    const headers = await kibanaHeaders(ctx);
    if (operationId === 'spaces') {
      const raw = asArray(await getJson(ctx, `${base(ctx)}/api/spaces/space`, headers)).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} spaces.`,
        rows: items.map((item) => ({
          id: str(item.id),
          cells: [
            str(item.name),
            str(item.id),
            firstLine(str(item.description, '—')),
            asArray(item.disabledFeatures).length
              ? String(asArray(item.disabledFeatures).length)
              : 'none',
          ],
          state: 'ok',
        })),
      };
    }
    if (operationId === 'data-views') {
      const payload = obj(await getJson(ctx, `${base(ctx)}/api/data_views`, headers));
      const raw = asArray(payload.data_view).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} data views.`,
        rows: items.map((item) => ({
          id: str(item.id),
          cells: [
            str(item.name, str(item.title)),
            str(item.title),
            str(item.timeFieldName, '—'),
            str(item.id),
          ],
          state: 'ok',
        })),
      };
    }
    const payload = obj(await getJson(ctx, `${base(ctx)}/api/status`, headers));
    const statuses = obj(obj(payload.status).core);
    const plugins = obj(obj(payload.status).plugins);
    const entries = [...Object.entries(statuses), ...Object.entries(plugins)];
    const { items, truncated } = take(entries);
    return {
      truncated,
      detail: `${entries.length} core services and plugins reporting.`,
      rows: items.map(([name, value]) => {
        const level = str(obj(value).level);
        return {
          id: name,
          cells: [name, level, firstLine(str(obj(value).summary, '—')), str(obj(value).since, '—')],
          state:
            level === 'available'
              ? 'ok'
              : level === 'degraded'
                ? 'warn'
                : level === 'unavailable' || level === 'critical'
                  ? 'fail'
                  : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

async function kibanaHeaders(ctx: IntegrationContext): Promise<Record<string, string>> {
  const user = config(ctx, 'user');
  const credential = await requireSecret(ctx, 'password');
  return {
    // With a user this is basic auth; without one the stored value is treated
    // as an encoded Elasticsearch API key, which is how Kibana expects it.
    Authorization: user
      ? `Basic ${Buffer.from(`${user}:${credential}`).toString('base64')}`
      : `ApiKey ${credential}`,
    'kbn-xsrf': 'meridian-loom',
    Accept: 'application/json',
  };
}

const aws: Handler = {
  async probe(ctx) {
    const stdout = await runCli(ctx, 'aws', awsArgs(ctx, ['sts', 'get-caller-identity']));
    const payload = obj(JSON.parse(stdout.trim() || '{}'));
    return `STS answered: account ${str(payload.Account)}, ${str(payload.Arn)}.`;
  },
  async read(ctx, operationId) {
    if (operationId === 'identity') {
      const payload = obj(
        JSON.parse(
          (await runCli(ctx, 'aws', awsArgs(ctx, ['sts', 'get-caller-identity']))).trim() || '{}',
        ),
      );
      return {
        truncated: false,
        detail: 'The principal these credentials resolve to.',
        rows: Object.entries(payload).map(([field, value]) => ({
          id: field,
          cells: [field, str(value)],
          state: 'ok' as IntegrationRowState,
        })),
      };
    }
    if (operationId === 'buckets') {
      const payload = obj(
        JSON.parse((await runCli(ctx, 'aws', awsArgs(ctx, ['s3api', 'list-buckets']))).trim() || '{}'),
      );
      const raw = asArray(payload.Buckets).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} buckets owned by this account.`,
        rows: items.map((item) => ({
          id: str(item.Name),
          cells: [str(item.Name), str(item.CreationDate)],
          state: 'ok',
        })),
      };
    }
    if (operationId === 'alarms') {
      const payload = obj(
        JSON.parse(
          (await runCli(ctx, 'aws', awsArgs(ctx, ['cloudwatch', 'describe-alarms']))).trim() || '{}',
        ),
      );
      const raw = asArray(payload.MetricAlarms).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} metric alarms.`,
        rows: items.map((item) => {
          const state = str(item.StateValue);
          return {
            id: str(item.AlarmName),
            cells: [
              str(item.AlarmName),
              state,
              str(item.MetricName, '—'),
              str(item.StateUpdatedTimestamp, '—'),
            ],
            state: state === 'OK' ? 'ok' : state === 'ALARM' ? 'fail' : 'warn',
          } satisfies IntegrationRow;
        }),
      };
    }
    const payload = obj(
      JSON.parse(
        (await runCli(ctx, 'aws', awsArgs(ctx, ['ec2', 'describe-instances']))).trim() || '{}',
      ),
    );
    const raw = asArray(payload.Reservations)
      .map(obj)
      .flatMap((reservation) => asArray(reservation.Instances).map(obj));
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} instances in ${config(ctx, 'region') || "the profile's region"}.`,
      rows: items.map((item) => {
        const state = str(obj(item.State).Name);
        const name = asArray(item.Tags)
          .map(obj)
          .find((tag) => str(tag.Key) === 'Name');
        return {
          id: str(item.InstanceId),
          cells: [
            str(item.InstanceId),
            str(name?.Value, '—'),
            state,
            str(item.InstanceType),
          ],
          state:
            state === 'running'
              ? 'ok'
              : state === 'stopped' || state === 'terminated'
                ? 'idle'
                : 'warn',
        } satisfies IntegrationRow;
      }),
    };
  },
};

function awsArgs(ctx: IntegrationContext, rest: string[]): string[] {
  const args = [...rest, '--output', 'json'];
  const profile = config(ctx, 'profile');
  const region = config(ctx, 'region');
  if (profile) args.push('--profile', profile);
  if (region) args.push('--region', region);
  return args;
}

const controlM: Handler = {
  async probe(ctx) {
    const headers = await bearer(ctx, 'token');
    const payload = await getJson(ctx, `${base(ctx)}/config/servers`, headers);
    const servers = asArray(payload).length;
    return `The Automation API answered and listed ${servers} Control-M/Server${servers === 1 ? '' : 's'}.`;
  },
  async read(ctx, operationId) {
    const headers = await bearer(ctx, 'token');
    if (operationId === 'servers') {
      const raw = asArray(await getJson(ctx, `${base(ctx)}/config/servers`, headers)).map(obj);
      const { items, truncated } = take(raw);
      return {
        truncated,
        detail: `${raw.length} configured servers.`,
        rows: items.map((item) => {
          const state = str(item.state, str(item.status));
          return {
            id: str(item.name),
            cells: [str(item.name), state, str(item.host, '—'), str(item.version, '—')],
            state: /up|running|connected/i.test(state)
              ? 'ok'
              : /down|disconnected/i.test(state)
                ? 'fail'
                : 'idle',
          } satisfies IntegrationRow;
        }),
      };
    }
    const query = config(ctx, 'query');
    const payload = obj(
      await getJson(
        ctx,
        `${base(ctx)}/run/jobs/status?limit=${INTEGRATION_READ_LIMIT}${query ? `&${query}` : ''}`,
        headers,
      ),
    );
    const raw = asArray(payload.statuses).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${str(payload.returned, String(raw.length))} jobs${query ? ` for ${query}` : ''}.`,
      rows: items.map((item) => {
        const status = str(item.status);
        return {
          id: str(item.jobId, str(item.name)),
          cells: [str(item.name), str(item.folder, '—'), status, str(item.host, '—')],
          state: /ended ok|completed/i.test(status)
            ? 'ok'
            : /ended not ok|failed|abend/i.test(status)
              ? 'fail'
              : /executing|running|wait/i.test(status)
                ? 'warn'
                : 'idle',
        } satisfies IntegrationRow;
      }),
    };
  },
};

const chrome: Handler = {
  async probe(ctx) {
    const payload = obj(await getJson(ctx, `${base(ctx)}/json/version`, {}));
    return `Chrome answered on the DevTools port: ${str(payload.Browser, 'an unnamed build')}.`;
  },
  async read(ctx) {
    const raw = asArray(await getJson(ctx, `${base(ctx)}/json/list`, {})).map(obj);
    const { items, truncated } = take(raw);
    return {
      truncated,
      detail: `${raw.length} open targets.`,
      rows: items.map((item) => ({
        id: str(item.id),
        cells: [
          str(item.title, '(untitled)'),
          str(item.type),
          str(item.url),
          str(item.id),
        ],
        state: str(item.type) === 'page' ? 'ok' : 'idle',
      })),
    };
  },
};

const HANDLERS: Readonly<Record<string, Handler>> = {
  gitlab,
  github,
  jira,
  jenkins,
  sonarqube,
  postman,
  docker,
  kubernetes,
  openshift,
  kafka,
  slack,
  datadog,
  grafana,
  kibana,
  aws,
  'control-m': controlM,
  chrome,
};

// ——— public surface ————————————————————————————————————————————————————

function contextFor(
  connection: IntegrationConnection,
  transport: IntegrationTransport,
  secret: (key: string) => Promise<string | undefined>,
): { ctx: IntegrationContext; handler: Handler } {
  const definition = integrationById(connection.integrationId);
  if (!definition)
    throw new Error(
      `"${connection.integrationId}" is not an integration Meridian knows about.`,
    );
  const handler = HANDLERS[definition.id];
  if (!handler)
    throw new Error(`${definition.name} has no reader in this build.`);
  return { ctx: { definition, connection, transport, secret }, handler };
}

/**
 * Attempt a real connection and report exactly what came back. A failure is
 * returned, not thrown: "could not reach it, and here is why" is a result the
 * interface must show, not an exception it must swallow.
 */
export async function probeIntegration(
  connection: IntegrationConnection,
  transport: IntegrationTransport,
  secret: (key: string) => Promise<string | undefined>,
): Promise<{ ok: boolean; detail: string; latencyMs: number; code?: number }> {
  const started = Date.now();
  const used: string[] = [];
  const trackingSecret = async (key: string) => {
    const value = await secret(key);
    if (value) used.push(value);
    return value;
  };
  try {
    const { ctx, handler } = contextFor(connection, transport, trackingSecret);
    const detail = await handler.probe(ctx);
    return { ok: true, detail, latencyMs: Date.now() - started };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      detail: redact(message, used),
      latencyMs: Date.now() - started,
      ...(error instanceof HttpFailure ? { code: error.status } : {}),
    };
  }
}

/** Run one read operation. Throws on failure so the caller can report it. */
export async function readIntegration(
  connection: IntegrationConnection,
  operationId: string,
  transport: IntegrationTransport,
  secret: (key: string) => Promise<string | undefined>,
): Promise<IntegrationReadResult> {
  const started = Date.now();
  const used: string[] = [];
  const trackingSecret = async (key: string) => {
    const value = await secret(key);
    if (value) used.push(value);
    return value;
  };
  const { ctx, handler } = contextFor(connection, transport, trackingSecret);
  const operation = ctx.definition.operations.find((entry) => entry.id === operationId);
  if (!operation)
    throw new Error(
      `${ctx.definition.name} has no read called "${operationId}". ` +
        `It offers: ${ctx.definition.operations.map((entry) => entry.id).join(', ')}.`,
    );
  try {
    const result = await handler.read(ctx, operationId);
    return {
      connectionId: connection.id,
      operationId,
      at: new Date().toISOString(),
      columns: [...operation.columns],
      rows: result.rows,
      detail: result.detail,
      truncated: result.truncated,
      latencyMs: Date.now() - started,
    };
  } catch (error) {
    throw new Error(
      redact(error instanceof Error ? error.message : String(error), used),
    );
  }
}
