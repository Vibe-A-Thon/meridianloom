import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';

/**
 * 10.40 First-Run rewritten (gaps_guix §4 amendment): four steps, no
 * credential, no Meridian agent, no walkthrough fixtures (banned 32).
 * Step state is computed only from real RPC results: workspace connected
 * (init), a session observed (observe/sessions, X-29 poll), the ledger
 * holding entries, and a bundle export that really succeeded.
 */

const okVerify = () => ({
  ok: true,
  entriesChecked: 3,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T10:09:00Z',
});

const bundleFixture = () => ({
  formatVersion: 1,
  generatedAt: '2026-09-20T10:12:00Z',
  signer: { algorithm: 'Ed25519', publicKey: 'KEY' },
  treeHead: { seq: 3, rootHash: 'ff'.repeat(32), signedAt: '2026-09-20T10:09:00Z', signature: 'sig' },
  range: { fromSequence: 1, toSequence: 3 },
  filter: {},
  entries: [{ sequence: 1 }, { sequence: 2 }, { sequence: 3 }],
  proofs: { treeSize: 3, rootHash: 'ff'.repeat(32), inclusion: [] },
  signature: {
    algorithm: 'Ed25519',
    signedAt: '2026-09-20T10:12:00Z',
    digest: 'ab'.repeat(32),
    signature: 'sig',
  },
  compliance: { standards: ['NIST SSDF AI provenance'], mappings: [] },
});

function renderApp(host: ReturnType<typeof makeHost>) {
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  render(<App client={client} />);
  return client;
}

describe('10.40 First-Run, rewritten', () => {
  it('shows four honest steps when nothing is recorded — no mock rows, no loom bar', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const firstRun = screen.getByTestId('first-run');
    // Step 1 is done — the harness host reports a workspace folder.
    expect(firstRun).toHaveTextContent('Watching /repo/ws');
    // Step 2 is the current actionable step with the no-credential promise.
    const steps = Array.from(firstRun.querySelectorAll('[data-step-state]'));
    expect(steps.map((s) => s.getAttribute('data-step-state'))).toEqual([
      'done',
      'current',
      'waiting',
      'current',
    ]);
    expect(firstRun).toHaveTextContent('no model credential, no Meridian agent');
    // No invented data anywhere.
    expect(screen.queryByTestId('vendor-tag')).toBeNull();
    expect(screen.queryByTestId('provenance-target')).toBeNull();
    client.dispose();
  });

  it('step 1 is the actionable one when no folder is open', async () => {
    const host = makeHost(
      {
        'observe/sessions': { sessions: [], warnings: [] },
        'ledger.query': { entries: [] },
        'ledger.verify': okVerify(),
      },
      { workspaceDir: undefined },
    );
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const firstRun = screen.getByTestId('first-run');
    expect(firstRun).toHaveTextContent('Open a folder in this window');
    const steps = Array.from(firstRun.querySelectorAll('[data-step-state]'));
    expect(steps.map((s) => s.getAttribute('data-step-state'))).toEqual([
      'current',
      'waiting',
      'waiting',
      'waiting',
    ]);
    // Without a repository the export offer is absent, not disabled.
    expect(screen.queryByRole('button', { name: 'Export audit bundle' })).toBeNull();
    client.dispose();
  });

  it('an observed session flips the panel to the recorder — step 2 completes on real data', async () => {
    // Mutable fixtures: the sidecar "learns" a session mid-test.
    let known: { sessions: unknown[]; warnings: string[] } = { sessions: [], warnings: [] };
    let ledgerEntries: unknown[] = [];
    const host = makeHost({
      'observe/sessions': () => known,
      'ledger.query': () => ({ entries: ledgerEntries }),
      'ledger.verify': okVerify(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();
    expect(screen.getByTestId('first-run')).toBeInTheDocument();

    known = {
      sessions: [
        {
          sessionId: 'sess-1',
          vendor: 'claude-code',
          confidence: 'telemetry',
          source: 'git-trailers',
          detail: '2 files · 1 commit',
          pid: null,
          startedAt: '2026-09-20T10:10:00Z',
          lastActivityAt: null,
          agentId: 'claude-code',
        },
      ],
      warnings: [],
    };
    // X-29: the host tells us; the app re-queries and leaves first-run.
    host.deliverHostMessage({
      type: 'event',
      event: { kind: 'sessions/changed', detail: 'claude appeared' },
    });
    await act(async () => {});
    await host.settle();

    await waitFor(() => expect(screen.queryByTestId('first-run')).not.toBeInTheDocument());
    expect(screen.getByTestId('crown-indicator')).toHaveTextContent('Recording');
    expect(screen.getByTestId('vendor-tag')).toHaveAccessibleName('Claude Code, from telemetry');
    client.dispose();
  });

  it('step 4 completes only when a signed export really succeeds', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
      'ledger.exportBundle': bundleFixture(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const firstRun = screen.getByTestId('first-run');
    expect(firstRun).toHaveTextContent('A signed audit bundle');
    expect(firstRun).not.toHaveTextContent('Bundle signed ·');

    fireEvent.click(screen.getByRole('button', { name: 'Export audit bundle' }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({ method: 'ledger.exportBundle' }),
    );
    expect(host.sent.find((m) => m.type === 'download')).toMatchObject({
      fileName: 'meridian-bundle-1-3.json',
    });
    await waitFor(() =>
      expect(screen.getByTestId('first-run')).toHaveTextContent('Bundle signed · 3 entries'),
    );
    client.dispose();
  });

  it('a ledger with entries but no live session is not first-run — the weave shows', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': () => ({ entries: [{ sequence: 9 }] }),
      'ledger.verify': okVerify(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    expect(screen.queryByTestId('first-run')).not.toBeInTheDocument();
    expect(screen.getByTestId('crown-indicator')).toHaveTextContent(
      'Watching for agent sessions',
    );
    client.dispose();
  });
});
