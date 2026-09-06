/**
 * ACP host client tests (FR-M34-01). The fake agent in fixtures/ is a test
 * double of the ACP WIRE: a real Node subprocess speaking newline-delimited
 * JSON-RPC per the pinned @zed-industries/agent-client-protocol schema.
 * These tests therefore exercise the host end to end over real stdio —
 * spawn, handshake, sessions, streaming, permissions, fs, terminals,
 * refusal, denial and crash — with no model client anywhere.
 */
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  AcpClient,
  AcpError,
  resolveWorkspacePath,
  type AcpClientOptions,
  type PermissionApprover,
} from '../src/acp/client';
import { ACP_PROTOCOL_VERSION } from '../src/acp/protocol';
import type { RequestPermissionRequest, SessionNotification } from '../src/acp/protocol';
import { AcpTierDisabledError, createAcpClient } from '../src/acp/index';

const FIXTURE = path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs');
const TIMEOUT = 20_000;

let workspace: string;

beforeEach(async () => {
  workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-acp-'));
  await fs.writeFile(path.join(workspace, 'input.txt'), 'hello workspace', 'utf8');
});

afterEach(async () => {
  await fs.rm(workspace, { recursive: true, force: true });
});

function agentOptions(...scenarioFlags: string[]): AcpClientOptions {
  return {
    command: process.execPath,
    args: [FIXTURE, ...scenarioFlags],
    workspaceDir: workspace,
  };
}

async function startClient(options: AcpClientOptions): Promise<AcpClient> {
  const client = new AcpClient(options);
  await client.start();
  return client;
}

/** Windows: the temp workspace can only be removed once the agent process is
 * actually gone — taskkill is asynchronous — so stop() is followed by the
 * exit event (with a bounded wait so a wedged child cannot hang the suite). */
async function stopAndWait(client: AcpClient): Promise<void> {
  if (client.pid === undefined) {
    client.stop();
    return;
  }
  const exited = new Promise<void>((resolve) => {
    client.once('exit', () => resolve());
    setTimeout(resolve, 5_000).unref?.();
  });
  client.stop();
  await exited;
}

/** An approver that always picks the named option. */
function fixedApprover(optionId: string, seen?: RequestPermissionRequest[]): PermissionApprover {
  return async (request) => {
    seen?.push(request);
    return { outcome: 'selected', optionId };
  };
}

describe('initialize handshake (FR-M34-01)', () => {
  it('negotiates the pinned protocol version and captures agent capabilities', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions());
    try {
      expect(client.agentInfo?.loadSession).toBe(true);
    } finally {
      await stopAndWait(client);
    }
  });

  it('refuses an unsupported protocol version and kills the agent', { timeout: TIMEOUT }, async () => {
    const client = new AcpClient(agentOptions('--refuse-version'));
    const exit = new Promise<{ code: number | null }>((resolve) => {
      client.once('exit', (code: number | null) => resolve({ code }));
    });
    const failure = await client.start().then(
      () => undefined,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(AcpError);
    expect((failure as AcpError).code).toBe('PROTOCOL_VERSION_REFUSED');
    expect((failure as AcpError).message).toContain(String(ACP_PROTOCOL_VERSION));
    // The connection is closed on refusal (per the ACP spec).
    await exit;
  });

  it('surfaces spawn failures as SPAWN_ERROR', { timeout: TIMEOUT }, async () => {
    const client = new AcpClient({
      ...agentOptions(),
      spawner: () => {
        throw Object.assign(new Error('spawn nope'), { code: 'ENOENT' });
      },
    });
    const failure = await client.start().then(
      () => undefined,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(AcpError);
    expect((failure as AcpError).code).toBe('SPAWN_ERROR');
  });
});

describe('session lifecycle and streaming (FR-M34-01)', () => {
  it('runs a full turn: streaming updates, permission approval, fs read/write, terminal', { timeout: TIMEOUT }, async () => {
    const seen: RequestPermissionRequest[] = [];
    const updates: SessionNotification[] = [];
    const client = await startClient({ ...agentOptions(), approvePermission: fixedApprover('allow-once', seen) });
    client.on('update', (notification: SessionNotification) => updates.push(notification));
    try {
      const sessionId = await client.newSession();
      expect(sessionId).toBe('fake-session-1');

      const stopReason = await client.prompt(sessionId, 'do the scripted work');
      expect(stopReason).toBe('end_turn');

      // The agent streamed its progress in order: message, plan, tool call,
      // tool call completion, final message.
      expect(updates.map((u) => u.update.sessionUpdate)).toEqual([
        'agent_message_chunk',
        'plan',
        'tool_call',
        'tool_call_update',
        'agent_message_chunk',
      ]);
      const plan = updates[1].update;
      expect(plan.sessionUpdate === 'plan' && plan.entries[0].content).toBe('Do the scripted work');

      // The host approved exactly the tool call the agent asked about.
      expect(seen).toHaveLength(1);
      expect(seen[0].toolCall.toolCallId).toBe('tc-permission');
      expect(seen[0].options.map((o) => o.optionId)).toContain('allow-once');

      // The client-provided fs and terminal were used for real effects.
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('permission={"outcome":"selected","optionId":"allow-once"}');
      expect(output).toContain('read="hello workspace"');
      expect(output).toContain('terminal_exit=0');
    } finally {
      await stopAndWait(client);
    }
  });

  it('loadSession resumes a session the agent advertised support for', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions());
    try {
      const sessionId = await client.newSession();
      await expect(client.loadSession(sessionId)).resolves.toBeUndefined();
    } finally {
      await stopAndWait(client);
    }
  });

  it('loadSession is refused when the agent does not advertise the capability', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions('--no-load-session'));
    try {
      await expect(client.loadSession('fake-session-1')).rejects.toMatchObject({
        code: 'LOAD_SESSION_UNSUPPORTED',
      });
    } finally {
      await stopAndWait(client);
    }
  });

  it('prompt before start is a clean error, not a hang', { timeout: TIMEOUT }, async () => {
    const client = new AcpClient(agentOptions());
    await expect(client.prompt('nope', 'hi')).rejects.toMatchObject({ code: 'NOT_RUNNING' });
  });
});

describe('permission-gated tool execution (FR-M34-01)', () => {
  it('the deny path reaches the agent: the agent stops with a refusal', { timeout: TIMEOUT }, async () => {
    const seen: RequestPermissionRequest[] = [];
    const client = await startClient({ ...agentOptions(), approvePermission: fixedApprover('reject-once', seen) });
    try {
      const sessionId = await client.newSession();
      const stopReason = await client.prompt(sessionId, 'try to run tools');
      expect(stopReason).toBe('refusal');
      expect(seen).toHaveLength(1);
      // The denied turn never touched the file system.
      await expect(fs.access(path.join(workspace, 'output.txt'))).rejects.toMatchObject({
        code: 'ENOENT',
      });
    } finally {
      await stopAndWait(client);
    }
  });

  it('defaults to deny when no approver is injected', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions()); // no approvePermission
    try {
      const sessionId = await client.newSession();
      // The default path picks the agent's reject option.
      await expect(client.prompt(sessionId, 'try')).resolves.toBe('refusal');
    } finally {
      await stopAndWait(client);
    }
  });

  it('cancelling the turn answers the pending permission as cancelled', { timeout: TIMEOUT }, async () => {
    const controller = new AbortController();
    const seen: RequestPermissionRequest[] = [];
    const approver: PermissionApprover = (request) => {
      seen.push(request);
      setTimeout(() => controller.abort(), 25);
      // Never resolves on its own: cancellation must answer it.
      return new Promise(() => undefined);
    };
    const client = await startClient({ ...agentOptions(), approvePermission: approver });
    try {
      const sessionId = await client.newSession();
      const stopReason = await client.prompt(sessionId, 'cancel me', { signal: controller.signal });
      expect(stopReason).toBe('cancelled');
      expect(seen).toHaveLength(1);
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('client-provided fs and terminal access (FR-M34-01)', () => {
  it('refuses paths outside the workspace root', () => {
    const escape = path.resolve(workspace, '..', 'meridian-acp-escape.txt');
    expect(() => resolveWorkspacePath(workspace, escape)).toThrowError(/outside the workspace/);
    expect(() => resolveWorkspacePath(workspace, `${workspace}${path.sep}sub${path.sep}file.txt`)).not.toThrow();
  });

  it('a wire-level fs escape attempt is refused and visible to the agent', { timeout: TIMEOUT }, async () => {
    const escape = path.resolve(workspace, '..', 'meridian-acp-escape.txt');
    const client = await startClient({
      ...agentOptions('--read-outside', escape),
      approvePermission: fixedApprover('allow-once'),
    });
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'read outside')).resolves.toBe('end_turn');
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('read_error=');
      expect(output.toLowerCase()).toContain('outside the workspace');
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('failure honesty', () => {
  it('an agent crash mid-turn rejects the in-flight prompt with a named error', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions('--crash'));
    try {
      const sessionId = await client.newSession();
      const failure = await client.prompt(sessionId, 'crash now').then(
        () => undefined,
        (error: unknown) => error,
      );
      expect(failure).toBeInstanceOf(AcpError);
      expect((failure as AcpError).code).toBe('AGENT_CRASHED');
      expect((failure as AcpError).message).toContain('code=1');
      expect((failure as AcpError).message).toContain('crashing as requested');
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('governor tier gate (FR-M36-05, G5)', () => {
  it('a disabled governor refuses to create a host client, with disclosure', () => {
    const failure = (() => {
      try {
        createAcpClient(agentOptions(), ['flight-recorder']);
      } catch (error) {
        return error;
      }
      return undefined;
    })();
    expect(failure).toBeInstanceOf(AcpTierDisabledError);
    expect((failure as AcpTierDisabledError).message).toContain('governor');
    expect((failure as AcpTierDisabledError).message).toContain('meridian.tiers');
    expect((failure as AcpTierDisabledError).data).toMatchObject({
      capability: 'governor.acp-host',
      tier: 'governor',
      enabledTiers: ['flight-recorder'],
    });
  });

  it('enabling the governor tier flips the capability on — a config change only', { timeout: TIMEOUT }, async () => {
    const client = createAcpClient(
      { ...agentOptions(), approvePermission: fixedApprover('allow-once') },
      ['flight-recorder', 'governor'],
    );
    await client.start();
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'go')).resolves.toBe('end_turn');
    } finally {
      await stopAndWait(client);
    }
  });
});
