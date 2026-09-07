/**
 * MCP server exposure of Meridian's governed surfaces (FR-M34-06; F1
 * Workstream A task 6).
 *
 * The server under test implements the MCP protocol directly (JSON-RPC 2.0
 * over newline-delimited stdio, 2025-03-26 surface: initialize, ping,
 * tools/list, tools/call, resources/list, resources/read) and forwards each
 * tool call to the sidecar as one tier-gated, ledger-recorded `mcp/invoke`.
 *
 * Two layers, both speaking the real protocol over real streams:
 *
 *  - unit: an in-process MCP server over PassThrough stream pairs backed by
 *    a scripted backend — exercises protocol shapes, the permission-denied
 *    mirror (TIER_DISABLED shape preserved), resources, and error mapping;
 *  - e2e: a real spawned Python sidecar (same convention as
 *    stdio-e2e/webview-e2e — skips with notice when no Python is on PATH):
 *    the governor tier gate refuses tools/call with the sidecar's
 *    TIER_DISABLED shape, and after tiers/set widens the tier set the same
 *    call succeeds and lands in the ledger.
 */
import { execFileSync } from 'node:child_process';
import { PassThrough } from 'node:stream';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ErrorCode } from '../../shared/ts/bus-types';
import { createFrameDecoder, encodeFrame } from '../src/framing';
import {
  MCP_PROTOCOL_VERSION,
  MCP_TOOLS,
  McpServer,
  type McpServerBackend,
} from '../src/mcp/server';
import { StdioSidecarClient } from '../src/stdio-client';

// -- test client double ------------------------------------------------------

/**
 * A real MCP client: speaks JSON-RPC 2.0 over the same NDJSON stdio framing
 * the spec mandates, against an McpServer bound to a stream pair.
 */
class TestMcpClient {
  private readonly decoder = createFrameDecoder();
  private nextId = 1;
  private readonly waiters = new Map<number, (message: any) => void>();

  constructor(server: McpServer) {
    const clientToServer = new PassThrough();
    const serverToClient = new PassThrough();
    serverToClient.on('data', (chunk: string) => {
      for (const message of this.decoder.push(chunk.toString())) {
        const frame = message as { id?: number };
        if (typeof frame.id === 'number') {
          this.waiters.get(frame.id)?.(frame);
          this.waiters.delete(frame.id);
        }
      }
    });
    void server.serve(clientToServer, serverToClient);
    this.out = clientToServer;
  }

  private readonly out: PassThrough;

  request(method: string, params: unknown): Promise<any> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timeout waiting for ${method}`)), 10_000);
      this.waiters.set(id, (frame) => {
        clearTimeout(timer);
        resolve(frame);
      });
      this.out.write(encodeFrame({ jsonrpc: '2.0', id, method, params }));
    });
  }

  notify(method: string, params: unknown): void {
    this.out.write(encodeFrame({ jsonrpc: '2.0', method, params }));
  }
}

/** Scripted backend: records invocations, replays queued outcomes. */
class FakeBackend implements McpServerBackend {
  calls: Array<{ tool: string; args: Record<string, unknown> }> = [];
  doctorCalls = 0;
  constructor(
    private readonly outcomes: unknown[] = [{ tool: 'ledger_query', result: { entries: [] } }],
    private readonly failure: (() => Error) | undefined = undefined,
    private readonly doctorResult: unknown = { checks: [] },
  ) {}

  async invoke(tool: string, args: Record<string, unknown>): Promise<unknown> {
    this.calls.push({ tool, args });
    if (this.failure) {
      throw this.failure();
    }
    return this.outcomes.length
      ? this.outcomes.shift()
      : { tool, result: { entries: [] } };
  }

  async doctorRun(): Promise<unknown> {
    this.doctorCalls += 1;
    if (this.failure) {
      throw this.failure();
    }
    return this.doctorResult;
  }
}

function tierDisabledError(): Error {
  const error = new Error(
    'mcp/invoke belongs to the governor tier (capability governor.mcp-server), which is disabled in this workspace.',
  );
  Object.assign(error, {
    code: ErrorCode.TIER_DISABLED,
    data: {
      method: 'mcp/invoke',
      capability: 'governor.mcp-server',
      tier: 'governor',
      enabledTiers: ['flight-recorder'],
      remediation: 'Enable the governor tier by adding "governor" to the meridian.tiers workspace setting; no reinstall is needed (FR-M36-05).',
    },
  });
  return error;
}

// -- unit: protocol over in-process streams ----------------------------------

describe('MCP server (unit, real protocol over streams)', () => {
  it('initialize negotiates the protocol version and introduces the server', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('initialize', {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: 'test-double', version: '0.0.0' },
    });
    expect(response.result.protocolVersion).toBe(MCP_PROTOCOL_VERSION);
    expect(response.result.serverInfo.name).toBe('meridian-loom');
    expect(response.result.serverInfo.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(response.result.capabilities.tools).toBeDefined();
    expect(response.result.capabilities.resources).toBeDefined();
  });

  it('answers an older client protocolVersion with the newest it supports', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'old-client', version: '0.0.0' },
    });
    expect(response.result.protocolVersion).toBe(MCP_PROTOCOL_VERSION);
  });

  it('accepts the initialized notification without a response', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    await client.request('initialize', {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: 'test-double', version: '0.0.0' },
    });
    client.notify('notifications/initialized', {});
    // A ping round-trip proves the notification did not derail the server.
    const ping = await client.request('ping', {});
    expect(ping.result).toEqual({});
  });

  it('tools/list advertises the four governed tools with input schemas', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('tools/list', {});
    const names = response.result.tools.map((tool: { name: string }) => tool.name);
    expect(names).toEqual([
      'ledger_query',
      'ledger_export_bundle',
      'ledger_verify',
      'trust_rejection_rate',
    ]);
    expect(names).toEqual(MCP_TOOLS.map((tool) => tool.name));
    for (const tool of response.result.tools) {
      expect(tool.description).toBeTruthy();
      expect(tool.inputSchema.type).toBe('object');
    }
  });

  it('tools/call forwards to the backend and unwraps the tool result', async () => {
    const backend = new FakeBackend([
      { tool: 'ledger_query', result: { entries: [{ sequence: 1, storyId: 's1' }] } },
    ]);
    const client = new TestMcpClient(new McpServer(backend));
    const response = await client.request('tools/call', {
      name: 'ledger_query',
      arguments: { storyId: 's1' },
    });
    expect(backend.calls).toEqual([{ tool: 'ledger_query', args: { storyId: 's1' } }]);
    expect(response.result.isError).toBeFalsy();
    const text = response.result.content[0];
    expect(text.type).toBe('text');
    expect(JSON.parse(text.text)).toEqual({ entries: [{ sequence: 1, storyId: 's1' }] });
  });

  it('tools/call refuses an unknown tool with the available tools listed', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('tools/call', {
      name: 'rm_rf',
      arguments: {},
    });
    expect(response.error.code).toBe(-32602);
    for (const name of MCP_TOOLS.map((tool) => tool.name)) {
      expect(response.error.data.availableTools).toContain(name);
    }
  });

  it('permission-denied mirrors the sidecar TIER_DISABLED shape verbatim', async () => {
    const backend = new FakeBackend([], tierDisabledError);
    const client = new TestMcpClient(new McpServer(backend));
    const response = await client.request('tools/call', {
      name: 'ledger_query',
      arguments: {},
    });
    expect(response.error.code).toBe(ErrorCode.TIER_DISABLED);
    expect(response.error.data).toMatchObject({
      method: 'mcp/invoke',
      capability: 'governor.mcp-server',
      tier: 'governor',
      enabledTiers: ['flight-recorder'],
    });
    expect(response.error.message).toContain('governor');
  });

  it('backend errors keep their code, message and data', async () => {
    const backend = new FakeBackend([], () => {
      const error = new Error('no workspace configured');
      Object.assign(error, { code: ErrorCode.LEDGER_UNAVAILABLE, data: { hint: 'handshake' } });
      return error;
    });
    const client = new TestMcpClient(new McpServer(backend));
    const response = await client.request('tools/call', {
      name: 'ledger_verify',
      arguments: {},
    });
    expect(response.error.code).toBe(ErrorCode.LEDGER_UNAVAILABLE);
    expect(response.error.message).toBe('no workspace configured');
    expect(response.error.data).toEqual({ hint: 'handshake' });
  });

  it('resources/list offers the spec pointer and the live doctor report', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('resources/list', {});
    const uris = response.result.resources.map((resource: { uri: string }) => resource.uri);
    expect(uris).toEqual(['meridian://open-ledger-spec', 'meridian://doctor-report']);
  });

  it('resources/read serves the open ledger spec pointer', async () => {
    const backend = new FakeBackend();
    const client = new TestMcpClient(new McpServer(backend));
    const response = await client.request('resources/read', {
      uri: 'meridian://open-ledger-spec',
    });
    expect(backend.doctorCalls).toBe(0);
    const text = response.result.contents[0];
    expect(text.uri).toBe('meridian://open-ledger-spec');
    expect(text.text).toContain('docs/open-ledger-spec');
  });

  it('resources/read fetches the doctor report live from the sidecar', async () => {
    const backend = new FakeBackend([], undefined, { checks: [{ id: 'ledger', ok: true }] });
    const client = new TestMcpClient(new McpServer(backend));
    const response = await client.request('resources/read', {
      uri: 'meridian://doctor-report',
    });
    expect(backend.doctorCalls).toBe(1);
    const text = response.result.contents[0];
    expect(text.mimeType).toBe('application/json');
    expect(JSON.parse(text.text)).toEqual({ checks: [{ id: 'ledger', ok: true }] });
  });

  it('resources/read refuses an unknown uri', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const response = await client.request('resources/read', { uri: 'meridian://nope' });
    expect(response.error.code).toBe(-32602);
  });

  it('unknown methods answer METHOD_NOT_FOUND; bad frames answer INVALID_REQUEST', async () => {
    const client = new TestMcpClient(new McpServer(new FakeBackend()));
    const missing = await client.request('tools/callButDifferent', {});
    expect(missing.error.code).toBe(-32601);

    const raw = new McpServer(new FakeBackend());
    const direct = await raw.handleMessage({ jsonrpc: '2.0', id: 99, params: {} });
    expect((direct as any).error.code).toBe(-32600);
  });
});

// -- e2e: real sidecar over real stdio ----------------------------------------

const coreDir = path.resolve(__dirname, '..', '..', 'core');

function findPython(): string | undefined {
  for (const candidate of ['python', 'python3']) {
    try {
      const executable = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (executable) {
        return candidate;
      }
    } catch {
      // try the next candidate
    }
  }
  return undefined;
}

const python = findPython();
const run = python ? describe : describe.skip;

run('MCP server ↔ real sidecar (FR-M34-06 e2e)', () => {
  it(
    'tier gate, tool call, and ledger recording round-trip the full path',
    { timeout: 60_000 },
    async () => {
      const workspaceDir = mkdtempSync(path.join(tmpdir(), 'meridian-mcp-e2e-'));
      const sidecar = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        workspaceDir,
        tiers: ['flight-recorder'],
      });
      await sidecar.start();
      const signal = new AbortController().signal;
      try {
        const never = new AbortController();
        const backend: McpServerBackend = {
          invoke: (tool, args) =>
            sidecar.call('mcp/invoke', { tool, arguments: args }, never.signal),
          doctorRun: () => sidecar.call('doctor/run', {}, never.signal),
        };
        const client = new TestMcpClient(new McpServer(backend));

        const init = await client.request('initialize', {
          protocolVersion: MCP_PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: { name: 'e2e-double', version: '0.0.0' },
        });
        expect(init.result.serverInfo.name).toBe('meridian-loom');

        const tools = await client.request('tools/list', {});
        expect(tools.result.tools).toHaveLength(4);

        // Governor disabled: the sidecar refuses mcp/invoke and the MCP
        // server mirrors the TIER_DISABLED shape to the MCP client.
        const denied = await client.request('tools/call', {
          name: 'ledger_query',
          arguments: {},
        });
        expect(denied.error.code).toBe(ErrorCode.TIER_DISABLED);
        expect(denied.error.data).toMatchObject({
          capability: 'governor.mcp-server',
          tier: 'governor',
        });
        // The refused call left no governance trail (the sidecar never ran).
        const before = await sidecar.call(
          'ledger.query',
          { actionType: 'tool_call' },
          signal,
        );
        expect(before.entries).toHaveLength(0);

        // Widen the tier set (a config flip, no reinstall — G5) and the
        // same MCP client call succeeds end to end.
        sidecar.notify('tiers/set', { tiers: ['flight-recorder', 'governor'] });
        await sidecar.call(
          'ledger.append',
          {
            storyId: 'mcp-e2e',
            phase: 'build',
            loopId: 'L1',
            loopIteration: 1,
            actorId: 'claude-code',
            actorVersion: '1.0.0',
            actorKind: 'external',
            policyVersion: 'e2e',
            actionType: 'diff',
            vendor: 'claude-code',
          },
          signal,
        );

        const ok = await client.request('tools/call', {
          name: 'ledger_query',
          arguments: { storyId: 'mcp-e2e' },
        });
        expect(ok.error).toBeUndefined();
        const entries = JSON.parse(ok.result.content[0].text).entries;
        expect(entries.some((entry: { storyId: string }) => entry.storyId === 'mcp-e2e')).toBe(
          true,
        );

        // The call itself is ledger-recorded through the sidecar.
        const recorded = await sidecar.call(
          'ledger.query',
          { actionType: 'tool_call' },
          signal,
        );
        expect(recorded.entries).toHaveLength(1);
        expect(recorded.entries[0]).toMatchObject({
          storyId: 'mcp:ledger_query',
          vendor: 'mcp',
          actorKind: 'external',
        });

        // The doctor report resource serves live sidecar state.
        const doctor = await client.request('resources/read', {
          uri: 'meridian://doctor-report',
        });
        expect(JSON.parse(doctor.result.contents[0].text)).toHaveProperty('checks');
      } finally {
        await sidecar
          .request('shutdown', { reason: 'mcp e2e' }, signal)
          .catch(() => undefined);
        await new Promise((resolve) => sidecar.on('exit', resolve));
      }
    },
  );
});

if (!python) {
  // eslint-disable-next-line no-console
  console.warn('python not found on PATH; skipping MCP↔sidecar e2e tests');
}
