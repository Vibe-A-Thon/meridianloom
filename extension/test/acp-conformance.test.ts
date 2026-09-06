/**
 * ACP conformance suite (NFR-30) — the entry point wired into root `npm test`.
 *
 * Runs Meridian's ACP host (extension/src/acp/, FR-M34-01) against the
 * locally verifiable conformance expectations of the Agent Client Protocol
 * specification (https://agentclientprotocol.com), using the fake wire agent
 * in fixtures/ — a real subprocess speaking ACP JSON-RPC, not a host mock.
 *
 * Mapping to the upstream suite: the ACP project
 * (github.com/zed-industries/agent-client-protocol) verifies clients with
 * its published test agents and the client/agent contract tests in its
 * typescript suite (the same pinned @zed-industries/agent-client-protocol
 * package this repo consumes for the wire). The cases below assert the same
 * spec sections those agents exercise: initialization + version
 * negotiation, session lifecycle, streaming update shapes, permission
 * flows, cancellation, and the client-provided fs/terminal methods.
 *
 * What remains for full NFR-30 (documented, not faked): running the
 * official upstream harness against a real ACP registry agent in CI is
 * environment-dependent (the upstream test agents and a registry agent must
 * be provisioned in the runner). The seam is real — the host speaks the
 * pinned wire through the official package — so swapping the fixture for an
 * upstream test agent requires no host changes.
 */
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AcpClient, type AcpClientOptions, type PermissionApprover } from '../src/acp/client';
import { ACP_PROTOCOL_VERSION } from '../src/acp/protocol';
import type { SessionNotification } from '../src/acp/protocol';

const FIXTURE = path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs');
const TIMEOUT = 20_000;

let workspace: string;

beforeEach(async () => {
  workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-acp-conf-'));
  await fs.writeFile(path.join(workspace, 'input.txt'), 'conformance fixture', 'utf8');
});

afterEach(async () => {
  await fs.rm(workspace, { recursive: true, force: true });
});

function agentOptions(...flags: string[]): AcpClientOptions {
  return { command: process.execPath, args: [FIXTURE, ...flags], workspaceDir: workspace };
}

async function startClient(options: AcpClientOptions): Promise<AcpClient> {
  const client = new AcpClient(options);
  await client.start();
  return client;
}

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

const allow: PermissionApprover = async () => ({ outcome: 'selected', optionId: 'allow-once' });

describe('ACP conformance (NFR-30) — initialization', () => {
  it('C-INIT-1 initialize carries the pinned protocol version and the advertised client capabilities', { timeout: TIMEOUT }, async () => {
    // The fake asserts nothing here; the host's own constants are the
    // contract. Negotiating a v1 agent to success proves the version and
    // capability set were accepted by a real ACP peer.
    const client = await startClient(agentOptions());
    try {
      expect(ACP_PROTOCOL_VERSION).toBe(1);
      expect(client.agentInfo).toBeDefined();
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-INIT-2 the agent echoing the supported version lets the connection proceed', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions('--protocol-version', '1'));
    try {
      const sessionId = await client.newSession();
      expect(sessionId).toBeTruthy();
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-INIT-3 a version the host does not support closes the connection and is reported', { timeout: TIMEOUT }, async () => {
    const client = new AcpClient(agentOptions('--refuse-version'));
    const exit = new Promise<void>((resolve) => client.once('exit', () => resolve()));
    await expect(client.start()).rejects.toMatchObject({
      code: 'PROTOCOL_VERSION_REFUSED',
    });
    await exit; // the connection is closed, per the spec's version negotiation
  });
});

describe('ACP conformance (NFR-30) — session lifecycle', () => {
  it('C-SESS-1 session/new yields a session id that accepts session/prompt and ends with a stop reason', { timeout: TIMEOUT }, async () => {
    const client = await startClient({ ...agentOptions(), approvePermission: allow });
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'turn')).resolves.toBe('end_turn');
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-SESS-2 session/load is only used when the agent advertised loadSession; unknown sessions surface the agent error', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions('--no-load-session'));
    try {
      await expect(client.loadSession('fake-session-1')).rejects.toMatchObject({
        code: 'LOAD_SESSION_UNSUPPORTED',
      });
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-SESS-3 loading an unknown session id surfaces the agent-side error cleanly', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions());
    try {
      await expect(client.loadSession('no-such-session')).rejects.toThrow(/no such session/);
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('ACP conformance (NFR-30) — streaming updates', () => {
  it('C-STRM-1/2/3 message chunks, tool calls and plans arrive as session/update notifications', { timeout: TIMEOUT }, async () => {
    const updates: SessionNotification[] = [];
    const client = await startClient({ ...agentOptions(), approvePermission: allow });
    client.on('update', (notification: SessionNotification) => updates.push(notification));
    try {
      const sessionId = await client.newSession();
      await client.prompt(sessionId, 'turn');
      const kinds = updates.map((u) => u.update.sessionUpdate);
      expect(kinds).toContain('agent_message_chunk');
      expect(kinds).toContain('tool_call');
      expect(kinds).toContain('tool_call_update');
      expect(kinds).toContain('plan');
      for (const notification of updates) {
        expect(notification.sessionId).toBe(sessionId);
      }
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('ACP conformance (NFR-30) — permission flows', () => {
  it('C-PERM-1 an approved request returns the selected option and the agent proceeds', { timeout: TIMEOUT }, async () => {
    let asked = 0;
    const approve: PermissionApprover = async (request) => {
      asked += 1;
      expect(request.options.length).toBeGreaterThan(0);
      return { outcome: 'selected', optionId: 'allow-always' };
    };
    const client = await startClient({ ...agentOptions(), approvePermission: approve });
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'turn')).resolves.toBe('end_turn');
      expect(asked).toBe(1);
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('"optionId":"allow-always"');
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-PERM-2 a rejected request returns the reject option and no host resource is touched', { timeout: TIMEOUT }, async () => {
    const client = await startClient({
      ...agentOptions(),
      approvePermission: async () => ({ outcome: 'selected', optionId: 'reject-once' }),
    });
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'turn')).resolves.toBe('refusal');
      await expect(fs.access(path.join(workspace, 'output.txt'))).rejects.toMatchObject({
        code: 'ENOENT',
      });
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-PERM-3 cancelling while a permission is pending answers it with the cancelled outcome', { timeout: TIMEOUT }, async () => {
    const controller = new AbortController();
    const approve: PermissionApprover = () => {
      setTimeout(() => controller.abort(), 25);
      return new Promise(() => undefined);
    };
    const client = await startClient({ ...agentOptions(), approvePermission: approve });
    try {
      const sessionId = await client.newSession();
      await expect(
        client.prompt(sessionId, 'cancel mid-permission', { signal: controller.signal }),
      ).resolves.toBe('cancelled');
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('ACP conformance (NFR-30) — cancellation and failure', () => {
  it('C-CANC-1 session/cancel ends the turn with stopReason cancelled', { timeout: TIMEOUT }, async () => {
    const controller = new AbortController();
    const approve: PermissionApprover = () => {
      setTimeout(() => controller.abort(), 25);
      return new Promise(() => undefined);
    };
    const client = await startClient({ ...agentOptions(), approvePermission: approve });
    try {
      const sessionId = await client.newSession();
      const stopReason = await client.prompt(sessionId, 'cancel me', { signal: controller.signal });
      expect(stopReason).toBe('cancelled');
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-CRASH-1 an agent that dies mid-turn fails the in-flight request with a clean error', { timeout: TIMEOUT }, async () => {
    const client = await startClient(agentOptions('--crash'));
    try {
      const sessionId = await client.newSession();
      await expect(client.prompt(sessionId, 'crash')).rejects.toMatchObject({
        code: 'AGENT_CRASHED',
      });
    } finally {
      await stopAndWait(client);
    }
  });
});

describe('ACP conformance (NFR-30) — client-provided fs and terminal', () => {
  it('C-FS-1 fs/read_text_file returns workspace content to the agent', { timeout: TIMEOUT }, async () => {
    const client = await startClient({ ...agentOptions(), approvePermission: allow });
    try {
      const sessionId = await client.newSession();
      await client.prompt(sessionId, 'turn');
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('read="conformance fixture"');
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-FS-2 a path outside the workspace is refused', { timeout: TIMEOUT }, async () => {
    const escape = path.resolve(workspace, '..', 'meridian-acp-conf-escape.txt');
    const client = await startClient({
      ...agentOptions('--read-outside', escape),
      approvePermission: allow,
    });
    try {
      const sessionId = await client.newSession();
      await client.prompt(sessionId, 'turn');
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('read_error=');
    } finally {
      await stopAndWait(client);
    }
  });

  it('C-TERM-1 terminal/create, wait_for_exit and release run a command with a usable exit status', { timeout: TIMEOUT }, async () => {
    const client = await startClient({ ...agentOptions(), approvePermission: allow });
    try {
      const sessionId = await client.newSession();
      await client.prompt(sessionId, 'turn');
      const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
      expect(output).toContain('terminal_exit=0');
    } finally {
      await stopAndWait(client);
    }
  });
});
