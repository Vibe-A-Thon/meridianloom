import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { getVsCodeApi } from '../host/vscode-api';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { EvidenceStudio } from '../workbench/EvidenceStudio';
import { ProvenanceReconciliation } from './ProvenanceReconciliation';

describe('reachable, not only registered (MP4)', () => {
  it('is a tab of the Evidence studio, and the tab renders the screen', () => {
    // MV3-T05 found a screen that existed in tests and in a registry nothing
    // rendered. This pins the other half: the studio actually mounts it.
    const host = makeHost({});
    const client = new WebviewRpcClient(host.transport);
    render(
      <EvidenceStudio
        client={client}
        ready
        sessions={{ status: 'ready', data: { sessions: [] } } as never}
        workspaceDir="/repo"
        enabledTiers={['flight-recorder']}
        initialTab="reconciliation"
      />,
    );
    expect(screen.getByRole('tab', { name: /Provenance reconciliation/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByTestId('provenance-reconciliation')).toBeInTheDocument();
    client.dispose();
  });

  it('opens straight to the reconciliation tab from its route id', async () => {
    // The catalogue gives the screen a route; the app must send that route to
    // this tab rather than to the studio's first one.
    const host = makeHost({ 'observe/sessions': { sessions: [], warnings: [] } });
    const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
    getVsCodeApi().setState({
      version: 1,
      theme: 'follow-vscode',
      density: 'comfortable',
      view: { screen: 'reconciliation' },
    });
    render(<App client={client} />);
    await act(async () => {});
    await host.settle();
    await act(async () => {});
    await host.settle();
    expect(screen.getByTestId('provenance-reconciliation')).toBeInTheDocument();
    client.dispose();
  });
});

/**
 * 10.54 Provenance Reconciliation (CP1-T04). The screen writes nothing into
 * somebody's repository unless they ask, knowing what and where.
 */

const DOCUMENT = {
  schema: 'meridian-loom/attribution-export@1',
  totals: { agent: 4, human: 10, unattributed: 2 },
  files: [],
  commits: {},
  disagreements: [],
};

const PLAN = {
  ref: 'refs/notes/meridian-attribution',
  commits: 3,
  truncated: false,
  toWrite: 3,
  unchanged: 0,
  written: 0,
};

function mount(responses: Record<string, unknown> = {}) {
  const host = makeHost({
    'interop/export': (params: { format?: string; write?: boolean }) =>
      params.format === 'attribution-json'
        ? { format: 'attribution-json', document: DOCUMENT }
        : { format: 'git-notes', notes: params.write ? { ...PLAN, toWrite: 3, written: 3 } : PLAN },
    ...responses,
  });
  const client = new WebviewRpcClient(host.transport);
  render(<ProvenanceReconciliation client={client} ready />);
  return { host, client };
}

describe('10.54 Provenance reconciliation', () => {
  it('carries the records panel and reads nothing until asked', async () => {
    const { host, client } = mount();
    expect(screen.getByTestId('interop-boundary')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Find disagreements' })).toBeInTheDocument();
    await host.settle();
    expect(host.requests).toEqual([]);
    client.dispose();
  });

  it('downloads the attribution export and says nothing was written', async () => {
    const post = vi.spyOn(getVsCodeApi(), 'postMessage');
    const { host, client } = mount();
    fireEvent.click(screen.getByTestId('reconciliation-download'));
    await host.settle();
    expect(host.requests.map((r) => r.params)).toEqual([{ format: 'attribution-json' }]);
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'download', fileName: 'meridian-attribution-export.json' }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('reconciliation-downloaded')).toHaveTextContent(
        'Nothing was written to the repository',
      ),
    );
    post.mockRestore();
    client.dispose();
  });

  it('plans notes before writing, and writes only after a confirmation naming the ref', async () => {
    const { host, client } = mount();
    fireEvent.click(screen.getByTestId('reconciliation-plan-notes'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('reconciliation-plan')).toBeInTheDocument());
    expect(host.requests.map((r) => r.params)).toEqual([{ format: 'git-notes' }]);

    const write = screen.getByTestId('reconciliation-write-notes');
    expect(write).toBeDisabled();
    expect(screen.getByTestId('reconciliation-confirm').parentElement).toHaveTextContent(
      'refs/notes/meridian-attribution',
    );

    fireEvent.click(screen.getByTestId('reconciliation-confirm'));
    expect(write).toBeEnabled();
    fireEvent.click(write);
    await host.settle();
    expect(host.requests.map((r) => r.params)).toEqual([
      { format: 'git-notes' },
      { format: 'git-notes', write: true },
    ]);
    await waitFor(() =>
      expect(screen.getByTestId('reconciliation-written')).toHaveTextContent('Wrote 3 note(s)'),
    );
    client.dispose();
  });

  it('offers no write when every note already says the same thing', async () => {
    const { host, client } = mount({
      'interop/export': { format: 'git-notes', notes: { ...PLAN, toWrite: 0, unchanged: 3 } },
    });
    fireEvent.click(screen.getByTestId('reconciliation-plan-notes'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('reconciliation-plan')).toBeInTheDocument());
    expect(screen.queryByTestId('reconciliation-write-notes')).toBeNull();
    client.dispose();
  });

  it('shows a failure rather than a success', async () => {
    const { host, client } = mount({ 'interop/export': new Error('no such commit: main') });
    fireEvent.click(screen.getByTestId('reconciliation-download'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('reconciliation-error')).toHaveTextContent('no such commit'),
    );
    expect(screen.queryByTestId('reconciliation-downloaded')).toBeNull();
    client.dispose();
  });
});
