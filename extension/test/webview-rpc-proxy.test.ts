import { describe, expect, it } from 'vitest';
import { ErrorCode } from '../../shared/ts/bus-types';
import { WEBVIEW_PROTOCOL_VERSION } from '../../shared/ts/webview-messages';
import {
  dispatchWebviewMessage,
  type SidecarRequestor,
} from '../src/webview/webview-rpc-proxy';

const recorderTiers = ['flight-recorder'] as const;

function sidecarOf(impl: (method: string, params: unknown) => Promise<unknown>): SidecarRequestor {
  return { request: (method, params) => impl(method, params) };
}

describe('dispatchWebviewMessage — the extension-host proxy (G0c/G0d)', () => {
  it('answers ready with an init carrying protocol version and enabled tiers', async () => {
    const reply = await dispatchWebviewMessage(
      { type: 'ready', protocolVersion: WEBVIEW_PROTOCOL_VERSION },
      { enabledTiers: () => [...recorderTiers], sidecar: undefined },
    );
    expect(reply).toEqual({
      type: 'init',
      init: { protocolVersion: WEBVIEW_PROTOCOL_VERSION, enabledTiers: ['flight-recorder'] },
    });
  });

  it('drops messages that are not recognisably the webview bus', async () => {
    for (const garbage of [null, 'x', 42, { type: 'eval' }, { type: 'rpc/request' }]) {
      expect(await dispatchWebviewMessage(garbage, {
        enabledTiers: () => [...recorderTiers],
        sidecar: undefined,
      })).toBeUndefined();
    }
  });

  it('forwards enabled-tier RPCs to the sidecar and returns the result', async () => {
    const calls: Array<[string, unknown]> = [];
    const sidecar = sidecarOf(async (method, params) => {
      calls.push([method, params]);
      return { sessions: [], warnings: [] };
    });
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 7, method: 'observe/sessions', params: {} },
      { enabledTiers: () => [...recorderTiers], sidecar },
    );
    expect(calls).toEqual([['observe/sessions', {}]]);
    expect(reply).toEqual({
      type: 'rpc/response',
      id: 7,
      result: { sessions: [], warnings: [] },
    });
  });

  it('applies the tier gate before the sidecar: TIER_DISABLED, structured', async () => {
    let called = false;
    const sidecar = sidecarOf(async () => {
      called = true;
      return {};
    });
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 3, method: 'gate.evaluate', params: { storyId: 's', gate: 'x' } },
      { enabledTiers: () => [...recorderTiers], sidecar },
    );
    expect(called).toBe(false);
    expect(reply).toMatchObject({
      type: 'rpc/response',
      id: 3,
      error: { code: ErrorCode.TIER_DISABLED, data: { method: 'gate.evaluate', tier: 'governor' } },
    });
    expect((reply as { error: { message: string } }).error.message).toContain('governor');
  });

  it('passes the same call once the tier is enabled (G5: settings change only)', async () => {
    const sidecar = sidecarOf(async () => ({ decision: 'pass' }));
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 4, method: 'gate.evaluate', params: { storyId: 's', gate: 'x' } },
      { enabledTiers: () => ['flight-recorder', 'governor'], sidecar },
    );
    expect(reply).toEqual({ type: 'rpc/response', id: 4, result: { decision: 'pass' } });
  });

  it('surfaces "sidecar down" as a structured error, never a hang', async () => {
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 5, method: 'ledger.query', params: {} },
      { enabledTiers: () => [...recorderTiers], sidecar: undefined },
    );
    expect(reply).toMatchObject({
      type: 'rpc/response',
      id: 5,
      error: { code: ErrorCode.INTERNAL_ERROR },
    });
    expect((reply as { error: { message: string } }).error.message).toContain('sidecar');
  });

  it('preserves the sidecar error code through the hop (e.g. LEDGER_UNAVAILABLE)', async () => {
    const sidecar = sidecarOf(async () => {
      throw { code: ErrorCode.LEDGER_UNAVAILABLE, message: 'no workspace configured' };
    });
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 6, method: 'ledger.query', params: {} },
      { enabledTiers: () => [...recorderTiers], sidecar },
    );
    expect(reply).toEqual({
      type: 'rpc/response',
      id: 6,
      error: { code: ErrorCode.LEDGER_UNAVAILABLE, message: 'no workspace configured', data: undefined },
    });
  });

  it('maps unexpected sidecar failures to INTERNAL_ERROR with the message', async () => {
    const sidecar = sidecarOf(async () => {
      throw new Error('stdio pipe broke');
    });
    const reply = await dispatchWebviewMessage(
      { type: 'rpc/request', id: 8, method: 'ping', params: {} },
      { enabledTiers: () => [...recorderTiers], sidecar },
    );
    expect(reply).toMatchObject({
      type: 'rpc/response',
      id: 8,
      error: { code: ErrorCode.INTERNAL_ERROR, message: 'stdio pipe broke' },
    });
  });
});
