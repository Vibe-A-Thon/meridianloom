import { getVsCodeApi } from '../host/vscode-api';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';

/**
 * 10.7 Ledger / Selvage Viewer (VIGUIX_Final §10.7) against a scripted
 * host: the always-visible Selvage verdict (FR-M11-01), the filterable
 * entry stream (FR-M10-12 / E-LG-01), the full-record drawer with honest
 * blob availability (decrypted vs crypto-shredded), proof inspection
 * (FR-M10-02/03) and the bundle export (FR-M36-04).
 */

const okVerify = () => ({
  ok: true,
  entriesChecked: 4417,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T14:22:00Z',
});

const streamEntries = () => ({
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
      confidence: 0.87,
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
      decision: 'approved',
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

const getEntryFull = () => ({
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
  confidence: 0.87,
  vendor: 'claude-code',
  observationConfidence: 'telemetry',
  simulated: false,
  entryHash: 'aa'.repeat(32),
  previousHash: 'bb'.repeat(32),
  inputDigest: 'dd'.repeat(32),
  outputDigest: 'ee'.repeat(32),
  inputAvailable: true,
  input: 'add idempotency key to submit',
  outputAvailable: true,
  output: 'diff --git a/src/PaymentController.java …',
});

const inclusionProof = () => ({
  inclusion: {
    treeSize: 4417,
    leafIndex: 4401,
    leafHash: 'aa'.repeat(32),
    rootHash: 'ff'.repeat(32),
    path: ['11'.repeat(32), '22'.repeat(32)],
  },
});

const consistencyProof = () => ({
  consistency: {
    fromSize: 4400,
    toSize: 4417,
    fromRootHash: '99'.repeat(32),
    toRootHash: 'ff'.repeat(32),
    path: ['33'.repeat(32)],
  },
});

async function renderLedger(host: ReturnType<typeof makeHost>) {
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  getVsCodeApi().setState({ version: 1, theme: 'follow-vscode', density: 'comfortable', view: { screen: 'ledger' } });
  render(<App client={client} />);
  await act(async () => {});
  await host.settle();

  await act(async () => {});
  await host.settle();
  return client;
}

describe('10.7 Ledger screen', () => {
  it('Selvage verdict is always visible; stream rows carry VendorTag + confidence (X-27)', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
    });
    const client = await renderLedger(host);

    expect(screen.getByTestId('selvage-verified')).toHaveTextContent('Chain verified to 4417');
    const rows = screen.getAllByTestId('vendor-tag');
    expect(rows[0]).toHaveAccessibleName('Claude Code, from telemetry');
    expect(screen.getByText('#4402')).toBeInTheDocument();
    expect(screen.getByText('#4403')).toBeInTheDocument();
    client.dispose();
  });

  it('filters drive ledger/query with story/agent/vendor/action/seq/time params', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
    });
    const client = await renderLedger(host);

    fireEvent.change(screen.getByLabelText('Story'), {
      target: { value: 'edb-12345' },
    });
    fireEvent.change(screen.getByLabelText('Vendor'), {
      target: { value: 'claude-code' },
    });
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'diff' } });
    fireEvent.change(screen.getByLabelText('From seq'), { target: { value: '4400' } });
    fireEvent.change(screen.getByLabelText('To seq'), { target: { value: '4410' } });
    fireEvent.change(screen.getByLabelText('From time'), {
      target: { value: '2026-09-20T00:00:00Z' },
    });
    fireEvent.change(screen.getByLabelText('To time'), {
      target: { value: '2026-09-21T00:00:00Z' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
    await host.settle();

    const queries = host.requests.filter((r) => r.method === 'ledger.query');
    expect(queries[queries.length - 1]?.params).toEqual({
      limit: 200,
      storyId: 'edb-12345',
      vendor: 'claude-code',
      actionType: 'diff',
      fromSequence: 4400,
      toSequence: 4410,
      fromTimestamp: '2026-09-20T00:00:00Z',
      toTimestamp: '2026-09-21T00:00:00Z',
    });
    client.dispose();
  });

  it('the drawer shows the full record, decrypted input, approver, and confidence with calibration context', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': getEntryFull(),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({ method: 'ledger.getEntry', params: { sequence: 4402 } }),
    );
    const drawer = screen.getByRole('heading', { name: 'Entry #4402' }).closest('section')!;
    expect(drawer).toHaveTextContent('add idempotency key to submit');
    expect(drawer).toHaveTextContent('claude-code · 1.0 (external)');
    // Banned 18: confidence renders with calibration context, never bare.
    expect(drawer.querySelector('[data-testid="confidence-bar"]')).not.toBeNull();
    expect(drawer.querySelector('[data-testid="confidence-calibration"]')).toBeNull();
    expect(drawer).toHaveTextContent(/no calibration history/i);
    client.dispose();
  });

  it('the drawer names the run and the door it came through', async () => {
    // FR-M40-02 (MV2): the ledger has carried `run_id` and `origin` since
    // schema v2, and this drawer did not show them — which left "how did
    // this run start?" answerable only by reading the database, the one
    // question the closed origin vocabulary exists to answer.
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': () => ({
        ...getEntryFull(),
        runId: 'run_20260920T140500_abcd1234',
        origin: 'omnibar',
      }),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();

    const origin = screen.getByTestId('entry-origin');
    expect(origin).toHaveTextContent('run_20260920T140500_abcd1234');
    expect(origin).toHaveTextContent('via omnibar');
    client.dispose();
  });

  it('an entry that belongs to no run says nothing about a door', async () => {
    // Most entries are not run-scoped. Rendering an empty "Run / origin" row
    // for them would be a field with no content, which reads as missing data
    // rather than as not applicable (P26).
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': getEntryFull(),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();

    expect(screen.queryByTestId('entry-origin')).toBeNull();
    client.dispose();
  });

  it('a crypto-shredded blob degrades honestly in the drawer', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': () => ({ ...getEntryFull(), inputAvailable: false, input: undefined }),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();

    const drawer = screen.getByRole('heading', { name: 'Entry #4402' }).closest('section')!;
    expect(drawer).toHaveTextContent('shredded');
    expect(drawer).not.toHaveTextContent('add idempotency key to submit');
    client.dispose();
  });

  it('inclusion proof for the selected entry renders readably', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': getEntryFull(),
      'ledger.proof': inclusionProof(),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect inclusion proof' }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({ method: 'ledger.proof', params: { sequence: 4402 } }),
    );
    const proof = screen.getByTestId('proof-view');
    expect(proof).toHaveTextContent('leaf 4401 of a tree of 4417');
    expect(proof).toHaveTextContent('ff'.repeat(32));
    expect(proof.querySelectorAll('.pathList li, [class*="pathList"] li').length).toBe(2);
    client.dispose();
  });

  it('consistency proof between two tree sizes renders both roots', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.getEntry': getEntryFull(),
      'ledger.proof': consistencyProof(),
    });
    const client = await renderLedger(host);

    fireEvent.click(screen.getByRole('button', { name: /#4402/ }));
    await host.settle();
    fireEvent.change(screen.getByLabelText('From size'), { target: { value: '4400' } });
    fireEvent.change(screen.getByLabelText('To size'), { target: { value: '4417' } });
    fireEvent.click(screen.getByRole('button', { name: 'Consistency proof' }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({
        method: 'ledger.proof',
        params: { fromSize: 4400, toSize: 4417 },
      }),
    );
    const proof = screen.getByTestId('proof-view');
    expect(proof).toHaveTextContent('tree of 4400 extends to 4417');
    expect(proof).toHaveTextContent('99'.repeat(32));
    expect(proof).toHaveTextContent('ff'.repeat(32));
    client.dispose();
  });

  it('bundle export is present and crosses the download channel', async () => {
    const host = makeHost({
      'observe/sessions': { sessions: [], warnings: [] },
      'ledger.query': streamEntries(),
      'ledger.verify': okVerify(),
      'ledger.exportBundle': () => ({
        formatVersion: 1,
        generatedAt: '2026-09-20T14:25:00Z',
        signer: { algorithm: 'Ed25519', publicKey: 'KEY' },
        treeHead: { seq: 4417, rootHash: 'ff'.repeat(32), signedAt: '2026-09-20T14:22:00Z', signature: 'sig' },
        range: { fromSequence: 4398, toSequence: 4417 },
        filter: {},
        entries: [{ sequence: 4402 }],
        proofs: { treeSize: 4417, rootHash: 'ff'.repeat(32), inclusion: [] },
        signature: { algorithm: 'Ed25519', signedAt: '2026-09-20T14:25:00Z', digest: 'ab'.repeat(32), signature: 'sig' },
        compliance: { standards: ['NIST SSDF AI provenance'], mappings: [] },
      }),
    });
    const client = await renderLedger(host);

    fireEvent.change(screen.getByLabelText('From sequence'), { target: { value: '4398' } });
    fireEvent.click(screen.getByRole('button', { name: 'Export audit bundle' }));
    await host.settle();

    const download = host.sent.find((m) => m.type === 'download');
    expect(download).toMatchObject({ fileName: 'meridian-bundle-4398-4417.json' });
    await waitFor(() => expect(screen.getByTestId('export-done')).toBeInTheDocument());
    client.dispose();
  });
});
