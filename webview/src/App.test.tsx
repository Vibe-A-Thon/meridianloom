import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WEBVIEW_PROTOCOL_VERSION } from '../../shared/ts/webview-messages';
import type { HostMessage, WebviewMessage } from '../../shared/ts/webview-messages';
import { App } from './App';
import { WebviewRpcClient, type RpcTransport } from './rpc/client';

/**
 * In-page host harness. `init` answers the `ready` handshake synchronously
 * (so the app reaches its loading state deterministically); RPC responses
 * are queued and only delivered when the test calls flush() — the loading →
 * ready transition is choreographed, not racy.
 */
function makeHost(responses: Record<string, unknown>) {
  const sent: WebviewMessage[] = [];
  let inbound: ((message: HostMessage) => void) | undefined;
  const queue: Array<{ id: number; method: string; result: unknown }> = [];
  const transport: RpcTransport = {
    postMessage(message) {
      sent.push(message);
      if (message.type === 'ready') {
        act(() => {
          inbound?.({
            type: 'init',
            init: { protocolVersion: WEBVIEW_PROTOCOL_VERSION, enabledTiers: ['flight-recorder'] },
          });
        });
      }
      if (message.type === 'rpc/request') {
        queue.push({ id: message.id as number, method: message.method, result: responses[message.method] });
      }
    },
    onMessage(handler) {
      inbound = handler;
      return () => {
        inbound = undefined;
      };
    },
  };
  return {
    transport,
    sent,
    /** Push an unsolicited host → webview message (events). */
    deliverHostMessage(message: HostMessage) {
      act(() => {
        inbound?.(message);
      });
    },
    /** Swap a queued (not yet delivered) response — error injection, retries. */
    replace(method: string, result: unknown) {
      for (const pending of queue) {
        if (pending.method === method) {
          pending.result = result;
        }
      }
    },
    /** Deliver every queued response inside one act(), letting the
     * client's .then continuations (hook setStates) run before it ends. */
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
  };
}

const hostSessions = () => ({
  sessions: [
    {
      sessionId: 'sess-1',
      vendor: 'claude-code',
      confidence: 'telemetry',
      source: 'git-trailers',
      detail: '3 files · 2 commits',
      pid: null,
      startedAt: '2026-09-20T10:00:00Z',
      lastActivityAt: null,
      agentId: 'claude-code',
    },
  ],
  warnings: ['copilot observer degraded to inferred'],
});

describe('App foundation surface against a scripted host', () => {
  it('renders loading, then real session rows with VendorTag + confidence', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    // Flush the post-init commit so the gated queries fire.
    await act(async () => {});

    // Handshake done, data in flight: the honest loading state shows.
    expect(screen.getAllByTestId('loading-state').length).toBeGreaterThan(0);

    await host.flush();

    await waitFor(() => expect(screen.getByTestId('vendor-tag')).toBeInTheDocument());
    const tag = screen.getByTestId('vendor-tag');
    expect(tag).toHaveAccessibleName('Claude Code, from telemetry');
    // NFR-32: the degradation warning is visible, not silent.
    expect(screen.getByTestId('observer-warnings')).toHaveTextContent(
      'copilot observer degraded to inferred',
    );
    // §4–6: the resolved theme lands on <html>.
    expect(document.documentElement.getAttribute('data-ml-theme')).toBe('follow-vscode');
    expect(document.documentElement.getAttribute('data-ml-density')).toBe('comfortable');
    client.dispose();
  });

  it('an empty ledger renders the invitation, not a blank section', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    await host.flush();
    await waitFor(() => expect(screen.getAllByTestId('empty-state').length).toBe(2));
    expect(screen.getAllByTestId('empty-state')).toHaveLength(2);
    expect(screen.getByText('Nothing recorded yet')).toBeInTheDocument();
    client.dispose();
  });

  it('a host push event (sessions/changed) re-issues the sessions query', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    await host.flush();
    await waitFor(() => expect(screen.getByTestId('vendor-tag')).toBeInTheDocument());
    const requestsBefore = host.sent.filter((m) => m.type === 'rpc/request').length;

    // The host pushes a session change; the app must re-query, not sit stale.
    host.deliverHostMessage({
      type: 'event',
      event: { kind: 'sessions/changed', detail: 'new session' },
    });
    await act(async () => {});
    await host.flush();
    await waitFor(() =>
      expect(host.sent.filter((m) => m.type === 'rpc/request').length).toBeGreaterThan(
        requestsBefore,
      ),
    );
    client.dispose();
  });

  it('an RPC error renders the honest ErrorState, and retry re-issues', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    host.replace('ledger.query', new Error('ledger unavailable'));
    await host.flush();

    await waitFor(() => expect(screen.getByTestId('error-state')).toBeInTheDocument());
    expect(screen.getByTestId('error-state')).toHaveTextContent('ledger');

    const retry = screen.getByRole('button', { name: 'Retry' });
    await act(async () => {
      retry.click();
      await Promise.resolve();
    });
    await host.flush();
    await waitFor(() => expect(screen.getByText('No ledger entries yet')).toBeInTheDocument());
    client.dispose();
  });

  it('a protocol-version mismatch renders a visible error, never a half-UI', async () => {
    let inbound: ((message: HostMessage) => void) | undefined;
    const mismatch: RpcTransport = {
      postMessage(message) {
        if ((message as { type?: string }).type === 'ready') {
          act(() => {
            inbound?.({
              type: 'init',
              init: { protocolVersion: 999, enabledTiers: [] },
            });
          });
        }
      },
      onMessage(handler) {
        inbound = handler;
        return () => {
          inbound = undefined;
        };
      },
    };
    const client = new WebviewRpcClient(mismatch, { timeoutMs: 1000 });
    render(<App client={client} />);
    await waitFor(() => expect(screen.getByTestId('error-state')).toBeInTheDocument());
    expect(screen.getByTestId('error-state')).toHaveTextContent('cannot update');
    client.dispose();
  });
});
