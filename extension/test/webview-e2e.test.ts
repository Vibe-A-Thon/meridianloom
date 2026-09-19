/**
 * G0d e2e smoke: the webview's real RPC client, the extension host's real
 * dispatchWebviewMessage, and a real spawned Python sidecar — sessions and
 * ledger queries round-trip the whole path the production panel runs, with
 * the tier gate applied on the host. Skips (with notice) when no Python is
 * on PATH, same convention as stdio-e2e.test.ts.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ErrorCode } from '../../shared/ts/bus-types';
import { WEBVIEW_PROTOCOL_VERSION } from '../../shared/ts/webview-messages';
import type { HostMessage, WebviewMessage } from '../../shared/ts/webview-messages';
import { StdioSidecarClient } from '../src/stdio-client';
import { dispatchWebviewMessage, type SidecarRequestor } from '../src/webview/webview-rpc-proxy';
import { RpcError, WebviewRpcClient } from '../../webview/src/rpc/client';
import type { RpcTransport } from '../../webview/src/rpc/client';

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

/** Wire the webview client to the host proxy over an in-memory channel. */
function makeChannel(context: {
  enabledTiers: () => readonly ('flight-recorder' | 'governor' | 'orchestra')[];
  sidecar: () => SidecarRequestor | undefined;
}): WebviewRpcClient {
  let inbound: ((message: HostMessage) => void) | undefined;
  // Lazy getter: the sidecar connection changes over the panel's life.
  const proxyContext = {
    enabledTiers: context.enabledTiers,
    get sidecar() {
      return context.sidecar();
    },
  };
  const transport: RpcTransport = {
    postMessage(message: WebviewMessage) {
      void dispatchWebviewMessage(message, proxyContext).then((reply) => {
        if (reply) {
          inbound?.(reply);
        }
      });
    },
    onMessage(handler) {
      inbound = handler;
      return () => {
        inbound = undefined;
      };
    },
  };
  return new WebviewRpcClient(transport, { timeoutMs: 30_000 });
}

run('webview ↔ host proxy ↔ real sidecar (G0d e2e)', () => {
  it(
    'handshake, sessions, ledger append/query and the tier gate round-trip',
    { timeout: 60_000 },
    async () => {
      const workspaceDir = mkdtempSync(path.join(tmpdir(), 'meridian-webview-e2e-'));
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        workspaceDir,
      });
      await client.start();
      try {
        const webview = makeChannel({
          enabledTiers: () => ['flight-recorder'],
          sidecar: () => client,
        });

        // The `ready` handshake answers with init + enabled tiers, and the
        // protocol version is the one both sides were built from.
        const initPromise = new Promise<HostMessage>((resolve) => {
          const unsubscribe = webview.addListener((message) => {
            if (message.type === 'init') {
              unsubscribe();
              resolve(message);
            }
          });
        });
        webview.notify({ type: 'ready', protocolVersion: WEBVIEW_PROTOCOL_VERSION });
        const init = (await initPromise) as { init: { protocolVersion: number; enabledTiers: string[] } };
        expect(init.init.protocolVersion).toBe(WEBVIEW_PROTOCOL_VERSION);
        expect(init.init.enabledTiers).toEqual(['flight-recorder']);

        // Real data, whole path: observe/sessions against the live sidecar.
        const sessions = await webview.request('observe/sessions', {});
        expect(Array.isArray(sessions.sessions)).toBe(true);
        expect(Array.isArray(sessions.warnings)).toBe(true);

        // Ledger: append a real entry, then read it back through the webview
        // client — the same RPC pair the Ledger screen will use.
        const appended = await webview.request('ledger.append', {
          storyId: 'webview-e2e',
          phase: 'build',
          loopId: 'L2-task',
          loopIteration: 1,
          actorId: 'e2e-agent',
          actorVersion: '0.0.1',
          actorKind: 'external',
          policyVersion: 'e2e',
          actionType: 'diff',
          vendor: 'claude-code',
          observationConfidence: 'telemetry',
          externalSessionId: 'sess-e2e',
        });
        expect(typeof appended.sequence).toBe('number');

        const queried = await webview.request('ledger.query', { storyId: 'webview-e2e' });
        expect(queried.entries.length).toBeGreaterThanOrEqual(1);
        const entry = queried.entries.find((e) => e.sequence === appended.sequence);
        expect(entry).toMatchObject({
          storyId: 'webview-e2e',
          vendor: 'claude-code',
          observationConfidence: 'telemetry',
          actorId: 'e2e-agent',
        });

        // Tier gate on the host: Governor methods are refused with the
        // structured TIER_DISABLED error, surfaced by the client as RpcError.
        const refusal = await webview
          .request('gate.evaluate', { storyId: 's', gate: 'security' })
          .then(() => undefined)
          .catch((error: unknown) => error);
        expect(refusal).toBeInstanceOf(RpcError);
        expect((refusal as RpcError).code).toBe(ErrorCode.TIER_DISABLED);
        expect((refusal as RpcError).data).toMatchObject({ tier: 'governor' });

        webview.dispose();
      } finally {
        await client.request('shutdown', { reason: 'webview e2e' }, new AbortController().signal);
        await new Promise((resolve) => client.on('exit', resolve));
      }
    },
  );
});

if (!python) {
  // eslint-disable-next-line no-console
  console.warn('python not found on PATH; skipping webview↔sidecar e2e tests');
}
