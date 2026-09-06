import { describe, expect, it } from 'vitest';
import type { HostMessage } from '../../../shared/ts/webview-messages';
import { WEBVIEW_PROTOCOL_VERSION } from '../../../shared/ts/webview-messages';
import {
  RpcError,
  RpcProtocolError,
  WebviewRpcClient,
  assertProtocolCompatible,
  type RpcTransport,
} from './client';

/** Scripted transport: queue inbound host messages, record outbound. */
function makeTransport() {
  const inbound: Array<(message: HostMessage) => void> = [];
  const outbound: unknown[] = [];
  const transport: RpcTransport = {
    postMessage(message) {
      outbound.push(message);
    },
    onMessage(handler) {
      inbound.push(handler);
      return () => {
        const i = inbound.indexOf(handler);
        if (i >= 0) inbound.splice(i, 1);
      };
    },
  };
  return {
    transport,
    outbound,
    push(message: HostMessage) {
      for (const handler of [...inbound]) handler(message);
    },
  };
}

describe('WebviewRpcClient over the postMessage channel', () => {
  it('correlates responses by id and resolves with the typed result', async () => {
    const { transport, outbound, push } = makeTransport();
    const client = new WebviewRpcClient(transport, { timeoutMs: 1000 });
    const promise = client.request('observe/sessions', {});
    expect(outbound).toEqual([
      { type: 'rpc/request', id: 1, method: 'observe/sessions', params: {} },
    ]);
    push({
      type: 'rpc/response',
      id: 1,
      result: { sessions: [], warnings: ['w'] },
    });
    await expect(promise).resolves.toEqual({ sessions: [], warnings: ['w'] });
    client.dispose();
  });

  it('rejects with the structured error, preserving the JSON-RPC code', async () => {
    const { transport, push } = makeTransport();
    const client = new WebviewRpcClient(transport, { timeoutMs: 1000 });
    const promise = client.request('gate.evaluate', { storyId: 's', gate: 'security' });
    push({
      type: 'rpc/response',
      id: 1,
      error: { code: -32003, message: 'tier governor is not enabled', data: { tier: 'governor' } },
    });
    await expect(promise).rejects.toMatchObject({
      name: 'RpcError',
      code: -32003,
      message: 'tier governor is not enabled',
      data: { tier: 'governor' },
    });
    client.dispose();
  });

  it('times out with a distinct code instead of hanging forever', async () => {
    const { transport } = makeTransport();
    const client = new WebviewRpcClient(transport, { timeoutMs: 25 });
    await expect(client.request('ping', {})).rejects.toMatchObject({ code: -32010 });
    client.dispose();
  });

  it('dispose rejects in-flight requests', async () => {
    const { transport } = makeTransport();
    const client = new WebviewRpcClient(transport, { timeoutMs: 1000 });
    const promise = client.request('ping', {});
    client.dispose();
    await expect(promise).rejects.toMatchObject({ code: -32011 });
  });

  it('records the host protocol version from init and checks it on handshake', () => {
    const { transport, push } = makeTransport();
    const client = new WebviewRpcClient(transport);
    expect(client.hostProtocolVersion).toBeUndefined();
    assertProtocolCompatible(client); // unknown yet: no throw
    push({ type: 'init', init: { protocolVersion: WEBVIEW_PROTOCOL_VERSION, enabledTiers: [] } });
    expect(client.hostProtocolVersion).toBe(WEBVIEW_PROTOCOL_VERSION);
    expect(() => assertProtocolCompatible(client)).not.toThrow();
    push({ type: 'init', init: { protocolVersion: 999, enabledTiers: [] } });
    expect(() => assertProtocolCompatible(client)).toThrow(RpcProtocolError);
    client.dispose();
  });

  it('ignores malformed and unrelated inbound messages', async () => {
    const { transport, push } = makeTransport();
    const client = new WebviewRpcClient(transport, { timeoutMs: 1000 });
    const promise = client.request('ping', {});
    push({ type: 'event', event: { kind: 'sessions/changed', detail: 'x' } } as HostMessage);
    push({ type: 'rpc/response', id: 999, result: { pong: true } } as HostMessage);
    push({ type: 'rpc/response', id: 1, result: { pong: true, seq: 1, uptimeSeconds: 0 } });
    await expect(promise).resolves.toMatchObject({ pong: true });
    client.dispose();
  });
});

describe('RpcError', () => {
  it('is an Error with the code attached', () => {
    const error = RpcError.from({ code: -32004, message: 'ledger unavailable' });
    expect(error).toBeInstanceOf(Error);
    expect(error.code).toBe(-32004);
    expect(error.message).toBe('ledger unavailable');
  });
});
