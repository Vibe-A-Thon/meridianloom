import { act } from '@testing-library/react';
import { WEBVIEW_PROTOCOL_VERSION } from '../../../shared/ts/webview-messages';
import type { HostMessage, WebviewMessage } from '../../../shared/ts/webview-messages';
import type { TierName } from '../../../shared/ts/bus-types';
import type { RpcTransport } from '../rpc/client';

/**
 * In-page host harness shared by the screen test suites. `init` answers the
 * `ready` handshake synchronously (so the app reaches its loading state
 * deterministically); RPC responses are scripted per method and only
 * delivered when the test calls flush()/settle() — the loading → ready
 * transition is choreographed, not racy.
 *
 * A scripted value may be a constant or a (params) => result function, so a
 * test can answer sequential multi-RPC flows (Any Line runs blame →
 * symbol/trailers → ledger). Fixture responses at the client boundary are
 * the legitimate seam: no fixtures ever ship in webview source.
 */

export type ScriptedResponse =
  | unknown
  | ((params: unknown, request: { id: number; method: string }) => unknown);

export interface HostHarness {
  transport: RpcTransport;
  /** Every WebviewMessage the app sent, in order (assert on requests). */
  sent: WebviewMessage[];
  /** RPC requests received, with params (assert on what the screen asked). */
  requests: Array<{ id: number; method: string; params: unknown }>;
  /** Swap a queued (not yet delivered) response — error injection, retries. */
  replace(method: string, result: unknown): void;
  /** Push an unsolicited host → webview message (events). */
  deliverHostMessage(message: HostMessage): void;
  /** Deliver every queued response inside one act(). */
  flush(): Promise<void>;
  /** flush() repeatedly until a sequential RPC flow has no more pending. */
  settle(maxRounds?: number): Promise<void>;
}

export function makeHost(
  responses: Record<string, ScriptedResponse>,
  options?: {
    /** Override the workspace folder in init; undefined = omit the field. */
    workspaceDir?: string;
    enabledTiers?: readonly TierName[];
  },
): HostHarness {
  const sent: WebviewMessage[] = [];
  const requests: Array<{ id: number; method: string; params: unknown }> = [];
  let inbound: ((message: HostMessage) => void) | undefined;
  const queue: Array<{ id: number; method: string; params: unknown; result: unknown }> = [];
  const initPayload: HostMessage = {
    type: 'init',
    init: {
      protocolVersion: WEBVIEW_PROTOCOL_VERSION,
      enabledTiers: options?.enabledTiers ?? ['flight-recorder'],
      ...(options && 'workspaceDir' in options
        ? options.workspaceDir !== undefined
          ? { workspaceDir: options.workspaceDir }
          : {}
        : { workspaceDir: '/repo/ws' }),
    },
  };
  const transport: RpcTransport = {
    postMessage(message) {
      sent.push(message);
      if (message.type === 'ready') {
        act(() => {
          inbound?.(initPayload);
        });
      }
      if (message.type === 'rpc/request') {
        if (!(message.method in responses)) {
          throw new Error(`host harness: no scripted response for '${message.method}'`);
        }
        const scripted = responses[message.method];
        const result =
          typeof scripted === 'function'
            ? (scripted as (params: unknown, request: { id: number; method: string }) => unknown)(
                message.params,
                { id: message.id as number, method: message.method },
              )
            : scripted;
        requests.push({ id: message.id as number, method: message.method, params: message.params });
        queue.push({ id: message.id as number, method: message.method, params: message.params, result });
      }
    },
    onMessage(handler) {
      inbound = handler;
      return () => {
        inbound = undefined;
      };
    },
  };
  const harness: HostHarness = {
    transport,
    sent,
    requests,
    replace(method, result) {
      for (const pending of queue) {
        if (pending.method === method) {
          pending.result = result;
        }
      }
    },
    deliverHostMessage(message) {
      act(() => {
        inbound?.(message);
      });
    },
    async flush() {
      await act(async () => {
        for (const pending of queue.splice(0)) {
          if (pending.result instanceof Error) {
            inbound?.({
              type: 'rpc/response',
              id: pending.id,
              error: { code: -32004, message: pending.result.message },
            });
          } else {
            inbound?.({ type: 'rpc/response', id: pending.id, result: pending.result });
          }
          await Promise.resolve();
        }
      });
    },
    async settle(maxRounds = 10) {
      for (let round = 0; round < maxRounds; round++) {
        await harness.flush();
        if (queue.length === 0) {
          return;
        }
      }
      throw new Error('host.settle: RPC flow did not quiesce within maxRounds');
    },
  };
  return harness;
}
