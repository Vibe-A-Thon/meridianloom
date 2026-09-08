import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { WebviewRpcClient, type RpcTransport } from './rpc/client';
import { makeHost } from './test/host-harness';
import type { HostMessage } from '../../shared/ts/webview-messages';

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

const okVerify = () => ({
  ok: true,
  entriesChecked: 12,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T10:09:00Z',
});

describe('App shell against a scripted host', () => {
  it('renders loading, then real session rows with VendorTag + confidence', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    // Flush the post-init commit so the gated queries fire.
    await act(async () => {});

    // Handshake done, data in flight: the honest loading state shows.
    expect(screen.getAllByTestId('loading-state').length).toBeGreaterThan(0);

    await host.settle();

    await waitFor(() => expect(screen.getByTestId('vendor-tag')).toBeInTheDocument());
    const tag = screen.getByTestId('vendor-tag');
    expect(tag).toHaveAccessibleName('Claude Code, from telemetry');
    // NFR-32: the degradation warning is visible, not silent.
    expect(screen.getByTestId('observer-warnings')).toHaveTextContent(
      'copilot observer degraded to inferred',
    );
    // X-29: the Crown carries the recording indicator.
    expect(screen.getByTestId('crown-indicator')).toHaveTextContent('sessions observed');
    fireEvent.click(screen.getByRole('button', { name: 'Evidence', exact: true }));
    await host.settle();
    // FR-M11-01: the Selvage names the verified tip.
    expect(screen.getByTestId('selvage-verified')).toHaveTextContent('Chain verified to 12');
    // §4–6: the resolved theme lands on <html>.
    expect(document.documentElement.getAttribute('data-ml-theme')).toBe('follow-vscode');
    expect(document.documentElement.getAttribute('data-ml-density')).toBe('comfortable');
    client.dispose();
  });

  it('with nothing recorded yet the panel shows the 10.40 first-run state', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    await host.settle();
    fireEvent.click(screen.getByRole('button', { name: 'Guided setup' }));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('first-run')).toBeInTheDocument());
    // Four honest steps, no mock rows.
    expect(screen.getByText('Connect a repository')).toBeInTheDocument();
    expect(screen.getByText('Run your existing agent')).toBeInTheDocument();
    expect(screen.getByText('See the Weave')).toBeInTheDocument();
    expect(screen.getByText('Export a bundle')).toBeInTheDocument();
    expect(screen.queryByTestId('vendor-tag')).toBeNull();
    client.dispose();
  });

  it('a host push event (sessions/changed) re-issues the sessions query', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('vendor-tag')).toBeInTheDocument());
    const requestsBefore = host.requests.filter((r) => r.method === 'observe/sessions').length;

    // The host pushes a session change; the app must re-query, not sit stale.
    host.deliverHostMessage({
      type: 'event',
      event: { kind: 'sessions/changed', detail: 'new session' },
    });
    await act(async () => {});
    await host.settle();
    await waitFor(() =>
      expect(host.requests.filter((r) => r.method === 'observe/sessions').length).toBeGreaterThan(
        requestsBefore,
      ),
    );
    client.dispose();
  });

  it('an RPC error renders the honest ErrorState, and retry re-issues', async () => {
    const host = makeHost({
      'observe/sessions': hostSessions(),
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
    });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    render(<App client={client} />);
    await act(async () => {});
    fireEvent.click(screen.getByRole('button', { name: 'Evidence', exact: true }));
    await act(async () => {});
    host.replace('ledger.query', new Error('ledger unavailable'));
    await host.settle();

    await waitFor(() => expect(screen.getByTestId('error-state')).toBeInTheDocument());
    expect(screen.getByTestId('error-state')).toHaveTextContent('ledger');

    const retry = screen.getByRole('button', { name: 'Retry' });
    await act(async () => {
      retry.click();
      await Promise.resolve();
    });
    await host.settle();
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
