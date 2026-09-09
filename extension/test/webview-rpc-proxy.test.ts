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
  it('forwards validated source locations and refuses malformed line numbers', async () => {
    const opened: Array<[string, number | undefined]> = [];
    const context = { enabledTiers: () => [...recorderTiers], sidecar: undefined, openEditor: async (file: string, line?: number) => { opened.push([file, line]); } };
    await dispatchWebviewMessage({ type: 'editor/open', path: 'src/main.ts', line: 8 }, context);
    for (const line of [0, -1, 1.5, '8', null]) await dispatchWebviewMessage({ type: 'editor/open', path: 'src/main.ts', line }, context);
    expect(opened).toEqual([['src/main.ts', 8]]);
  });
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

  it('init carries the workspace folder when one is open (attrib repoPath)', async () => {
    const reply = await dispatchWebviewMessage(
      { type: 'ready', protocolVersion: WEBVIEW_PROTOCOL_VERSION },
      {
        enabledTiers: () => [...recorderTiers],
        sidecar: undefined,
        workspaceDir: () => '/repo/workspace',
      },
    );
    expect(reply).toMatchObject({
      type: 'init',
      init: { workspaceDir: '/repo/workspace' },
    });
    // …and absent entirely when no folder is open — never an empty string.
    const bare = await dispatchWebviewMessage(
      { type: 'ready', protocolVersion: WEBVIEW_PROTOCOL_VERSION },
      { enabledTiers: () => [...recorderTiers], sidecar: undefined },
    );
    expect((bare as { init: Record<string, unknown> }).init.workspaceDir).toBeUndefined();
  });

  it('a download message goes to the host save channel, fire-and-forget', async () => {
    const saved: Array<[string, string]> = [];
    const reply = await dispatchWebviewMessage(
      {
        type: 'download',
        fileName: 'meridian-bundle.json',
        mimeType: 'application/json',
        content: '{"formatVersion":1}',
      },
      {
        enabledTiers: () => [...recorderTiers],
        sidecar: undefined,
        saveFile: (fileName, content) => {
          saved.push([fileName, content]);
        },
      },
    );
    expect(reply).toBeUndefined();
    expect(saved).toEqual([['meridian-bundle.json', '{"formatVersion":1}']]);
  });

  it('rejects malformed download messages at the boundary', async () => {
    let called = false;
    for (const garbage of [
      { type: 'download' },
      { type: 'download', fileName: 'x.json', mimeType: 'application/json' },
      { type: 'download', fileName: 7, mimeType: 'application/json', content: '{}' },
    ]) {
      expect(
        await dispatchWebviewMessage(garbage, {
          enabledTiers: () => [...recorderTiers],
          sidecar: undefined,
          saveFile: () => {
            called = true;
          },
        }),
      ).toBeUndefined();
    }
    expect(called).toBe(false);
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
