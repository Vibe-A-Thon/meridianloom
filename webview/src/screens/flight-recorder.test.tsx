import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';

/**
 * 10.45 Flight Recorder (gaps_guix §3) against a scripted host: the Weave
 * of recorded passes, the Any Line provenance answer (telemetry vs
 * inferred, told/approved/sequence), the bundle export through the host
 * download channel, and the Selvage verdict (FR-M11-01) including the
 * tamper case. Fixture RPC responses live at the client boundary — the
 * legitimate test seam; no fixtures ship in webview source.
 */

const okVerify = () => ({
  ok: true,
  entriesChecked: 12,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T10:09:00Z',
});

const weaveEntries = () => ({
  entries: [
    {
      sequence: 4402,
      timestamp: '2026-09-20T14:05:00Z',
      storyId: 'edb-12345',
      phase: 'build',
      loopId: 'L2-task',
      loopIteration: 1,
      actorId: 'claude-code',
      actorVersion: '1.0',
      actorKind: 'external',
      policyVersion: 'f0',
      actionType: 'diff',
      vendor: 'claude-code',
      observationConfidence: 'telemetry',
      simulated: false,
      entryHash: 'aa'.repeat(32),
      previousHash: 'bb'.repeat(32),
      hasInputBlob: true,
      hasOutputBlob: true,
    },
    {
      sequence: 4403,
      timestamp: '2026-09-20T14:07:00Z',
      storyId: 'edb-12345',
      phase: 'review',
      loopId: 'L2-task',
      loopIteration: 1,
      actorId: 'priya.nair',
      actorVersion: '1',
      actorKind: 'human',
      policyVersion: 'f0',
      actionType: 'approval',
      humanActor: 'Priya Nair',
      humanRole: 'Tech Lead',
      vendor: 'meridian',
      observationConfidence: 'direct',
      simulated: false,
      entryHash: 'cc'.repeat(32),
      previousHash: 'aa'.repeat(32),
      hasInputBlob: false,
      hasOutputBlob: false,
    },
  ],
});

const blameFixture = () => ({
  repoPath: '/repo/ws',
  ref: 'HEAD',
  lines: [
    {
      path: 'src/PaymentController.java',
      line: 47,
      commit: 'abc123def4567890',
      authorName: 'Claude',
      authorEmail: 'noreply@anthropic.com',
      authorTime: '2026-09-20T14:05:00Z',
      content: 'return submitWithIdempotency(key);',
    },
  ],
});

const trailerFixture = (withAttribution = true) => ({
  commits: [
    {
      commit: 'abc123def4567890',
      authoredAt: '2026-09-20T14:05:00Z',
      attributions: withAttribution
        ? [
            {
              name: 'Claude',
              email: 'noreply@anthropic.com',
              vendor: 'claude',
              meridianAuthored: false,
            },
          ]
        : [],
      meridianLedger: withAttribution ? ['4398-4402'] : [],
    },
  ],
});

const ledgerRangeFixture = () => ({
  entries: [
    {
      sequence: 4401,
      timestamp: '2026-09-20T14:06:00Z',
      storyId: 'edb-12345',
      phase: 'review',
      loopId: 'L2-task',
      loopIteration: 1,
      actorId: 'priya.nair',
      actorVersion: '1',
      actorKind: 'human',
      policyVersion: 'f0',
      actionType: 'approval',
      humanActor: 'Priya Nair',
      humanRole: 'Tech Lead',
      vendor: 'meridian',
      observationConfidence: 'direct',
      simulated: false,
      entryHash: 'dd'.repeat(32),
      previousHash: 'ee'.repeat(32),
      hasInputBlob: false,
      hasOutputBlob: false,
    },
    {
      sequence: 4402,
      timestamp: '2026-09-20T14:05:00Z',
      storyId: 'edb-12345',
      phase: 'build',
      loopId: 'L2-task',
      loopIteration: 1,
      actorId: 'claude-code',
      actorVersion: '1.0',
      actorKind: 'external',
      policyVersion: 'f0',
      actionType: 'diff',
      vendor: 'claude-code',
      observationConfidence: 'telemetry',
      simulated: false,
      entryHash: 'aa'.repeat(32),
      previousHash: 'bb'.repeat(32),
      hasInputBlob: true,
      hasOutputBlob: true,
    },
  ],
});

const bundleFixture = () => ({
  formatVersion: 1,
  generatedAt: '2026-09-20T14:10:00Z',
  signer: { algorithm: 'Ed25519', publicKey: 'KEY' },
  treeHead: {
    seq: 12,
    rootHash: 'ff'.repeat(32),
    signedAt: '2026-09-20T14:09:00Z',
    signature: 'sig',
  },
  range: { fromSequence: 1, toSequence: 12 },
  filter: {},
  entries: [
    { sequence: 1, entryHash: '11'.repeat(32), previousHash: '00'.repeat(32) },
    { sequence: 2, entryHash: '22'.repeat(32), previousHash: '11'.repeat(32) },
  ],
  proofs: { treeSize: 12, rootHash: 'ff'.repeat(32), inclusion: [] },
  signature: {
    algorithm: 'Ed25519',
    signedAt: '2026-09-20T14:10:00Z',
    digest: 'ab'.repeat(32),
    signature: 'sig',
  },
  compliance: {
    standards: ['NIST SSDF AI provenance', 'ISO/IEC 42001'],
    mappings: [],
  },
});

function renderApp(host: ReturnType<typeof makeHost>) {
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  render(<App client={client} />);
  return client;
}

describe('10.45 Flight Recorder screen', () => {
  it('the Weave renders recorded passes, each with VendorTag + confidence (X-27)', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': weaveEntries(),
      'ledger.verify': okVerify(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const tags = screen.getAllByTestId('vendor-tag');
    expect(tags.length).toBeGreaterThanOrEqual(2);
    expect(tags[0]).toHaveAccessibleName('Claude Code, from telemetry');
    // Banned 31: the telemetry row never claims direct.
    expect(tags[0]).not.toHaveAccessibleName(/observed directly/);
    expect(screen.getByText(/diff — claude-code/)).toBeInTheDocument();
    client.dispose();
  });

  it('X-30: focusing a weave row opens the same provenance card, with approval state', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': weaveEntries(),
      'ledger.verify': okVerify(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const row = screen.getAllByTestId('provenance-target')[0]!;
    fireEvent.focus(row);
    const card = screen.getByTestId('provenance-card');
    expect(card).toHaveTextContent('not yet gated');
    expect(card.querySelector('[data-testid="vendor-tag"]')).not.toBeNull();
    fireEvent.blur(row);
    await waitFor(() =>
      expect(screen.queryByTestId('provenance-card')).not.toBeInTheDocument(),
    );
    client.dispose();
  });

  it('Any Line answers agent / told / confident / approved from real RPCs', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': ledgerRangeFixture(),
      'ledger.verify': okVerify(),
      'attrib/blame': blameFixture(),
      'attrib/symbol': () => ({
        path: 'src/PaymentController.java',
        line: 47,
        language: 'java',
        symbol: 'PaymentController.submit',
      }),
      'trailers/parse': trailerFixture(),
      'ledger.getEntry': () => ({
        sequence: 4402,
        timestamp: '2026-09-20T14:05:00Z',
        storyId: 'edb-12345',
        phase: 'build',
        loopId: 'L2-task',
        loopIteration: 1,
        actorId: 'claude-code',
        actorVersion: '1.0',
        actorKind: 'external',
        policyVersion: 'f0',
        actionType: 'diff',
        vendor: 'claude-code',
        observationConfidence: 'telemetry',
        simulated: false,
        entryHash: 'aa'.repeat(32),
        previousHash: 'bb'.repeat(32),
        inputDigest: 'dd'.repeat(32),
        inputAvailable: true,
        input: 'add idempotency key to submit',
        outputAvailable: false,
      }),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    fireEvent.change(screen.getByPlaceholderText('src/PaymentController.java'), {
      target: { value: 'src/PaymentController.java' },
    });
    fireEvent.change(screen.getByPlaceholderText('47'), { target: { value: '47' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }));
    await host.settle();

    const answer = screen.getByTestId('any-line-answer');
    expect(answer).toHaveTextContent('src/PaymentController.java:47');
    // Agent, labelled with its observation confidence (telemetry).
    expect(answer.querySelector('[data-testid="vendor-tag"]')).toHaveAccessibleName(
      'Claude Code, from telemetry',
    );
    expect(answer).toHaveTextContent('PaymentController.submit');
    expect(answer).toHaveTextContent('seq 4402');
    expect(answer).toHaveTextContent('Meridian-Ledger: 4398-4402');
    expect(answer).toHaveTextContent('“add idempotency key to submit”');
    expect(answer).toHaveTextContent('recorded in the ledger');
    expect(answer).toHaveTextContent('Priya Nair (Tech Lead)');
    // The blame call got the real repoPath + file filter.
    expect(host.requests).toContainEqual(
      expect.objectContaining({
        method: 'attrib/blame',
        params: { repoPath: '/repo/ws', paths: ['src/PaymentController.java'] },
      }),
    );
    client.dispose();
  });

  it('Any Line with no agent trailer answers visibly labelled inferred (G3/B12)', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
      'attrib/blame': blameFixture(),
      'attrib/symbol': () => ({
        path: 'src/PaymentController.java',
        line: 47,
        language: 'java',
        symbol: 'PaymentController.submit',
      }),
      'trailers/parse': trailerFixture(false),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    fireEvent.change(screen.getByPlaceholderText('src/PaymentController.java'), {
      target: { value: 'src/PaymentController.java' },
    });
    fireEvent.change(screen.getByPlaceholderText('47'), { target: { value: '47' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }));
    await host.settle();

    const badge = screen.getByTestId('inferred-label');
    expect(badge).toHaveTextContent('inferred');
    const answer = screen.getByTestId('any-line-answer');
    expect(answer.querySelector('[data-testid="vendor-tag"]')).toHaveAccessibleName(
      'Unknown vendor, inferred from file changes',
    );
    // No ledger trailer → no made-up sequence, told or approval.
    expect(answer).not.toHaveTextContent('seq 4402');
    expect(answer).toHaveTextContent('— (not yet gated)');
    client.dispose();
  });

  it('Any Line says so when the input blob was crypto-shredded', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': ledgerRangeFixture(),
      'ledger.verify': okVerify(),
      'attrib/blame': blameFixture(),
      'attrib/symbol': () => ({
        path: 'src/PaymentController.java',
        line: 47,
        language: 'java',
        symbol: 'PaymentController.submit',
      }),
      'trailers/parse': trailerFixture(),
      'ledger.getEntry': () => ({
        sequence: 4402,
        timestamp: '2026-09-20T14:05:00Z',
        storyId: 'edb-12345',
        phase: 'build',
        loopId: 'L2-task',
        loopIteration: 1,
        actorId: 'claude-code',
        actorVersion: '1.0',
        actorKind: 'external',
        policyVersion: 'f0',
        actionType: 'diff',
        vendor: 'claude-code',
        observationConfidence: 'telemetry',
        simulated: false,
        entryHash: 'aa'.repeat(32),
        previousHash: 'bb'.repeat(32),
        inputDigest: 'dd'.repeat(32),
        inputAvailable: false,
        outputAvailable: false,
      }),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    fireEvent.change(screen.getByPlaceholderText('src/PaymentController.java'), {
      target: { value: 'src/PaymentController.java' },
    });
    fireEvent.change(screen.getByPlaceholderText('47'), { target: { value: '47' } });
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }));
    await host.settle();

    expect(screen.getByTestId('any-line-answer')).toHaveTextContent('shredded');
    client.dispose();
  });

  it('Export calls ledger/exportBundle and offers the JSON through the host', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': { entries: [] },
      'ledger.verify': okVerify(),
      'ledger.exportBundle': bundleFixture(),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    fireEvent.click(screen.getByRole('button', { name: 'Export audit bundle' }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({ method: 'ledger.exportBundle', params: {} }),
    );
    const download = host.sent.find((m) => m.type === 'download');
    expect(download).toMatchObject({
      type: 'download',
      fileName: 'meridian-bundle-1-12.json',
      mimeType: 'application/json',
    });
    const parsed = JSON.parse((download as { content: string }).content);
    expect(parsed.formatVersion).toBe(1);
    expect(parsed.entries).toHaveLength(2);
    // The success line carries the real payload facts.
    const done = screen.getByTestId('export-done');
    expect(done).toHaveTextContent('2 entries');
    expect(done).toHaveTextContent('verifies without Meridian installed');
    expect(done).toHaveTextContent('NIST SSDF AI provenance, ISO/IEC 42001');
    client.dispose();
  });

  it('Selvage names the first divergent sequence when the chain fails (FR-M11-01)', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': weaveEntries(),
      'ledger.verify': () => ({
        ok: false,
        entriesChecked: 4406,
        firstDivergentSequence: 4407,
        detail: 'entry hash mismatch at 4407',
        verifiedAt: '2026-09-20T14:11:00Z',
      }),
    });
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    const broken = screen.getByTestId('selvage-broken');
    expect(broken).toHaveTextContent('Chain verification failed');
    expect(broken).toHaveTextContent('first divergent sequence 4407');
    expect(screen.getByTestId('selvage-strip').firstChild).toHaveAttribute(
      'data-chain-ok',
      'false',
    );
    client.dispose();
  });

  it('X-28: upper tiers are absent, and one unlock affordance discloses what Governor adds', async () => {
    const host = makeHost(
      {
        'observe/sessions': { sessions: [], warnings: [] },
        'ledger.query': weaveEntries(),
        'ledger.verify': okVerify(),
      },
      { enabledTiers: ['flight-recorder'] },
    );
    const client = renderApp(host);
    await act(async () => {});
    await host.settle();

    // Loom Bar carries only the Flight Recorder — no Governor/Orchestra
    // entries, not even disabled ones (banned 30).
    const nav = screen.getByRole('navigation', { name: 'Screens' });
    expect(nav).toHaveTextContent('Flight Recorder');
    expect(nav).not.toHaveTextContent('Governor');
    expect(nav).not.toHaveTextContent('Orchestra');
    // The single unlock affordance (X-28) with its one-line statement.
    fireEvent.click(screen.getByRole('button', { name: 'Unlock Governor' }));
    expect(screen.getByRole('note')).toHaveTextContent('gates over external agents');
    client.dispose();
  });
});
