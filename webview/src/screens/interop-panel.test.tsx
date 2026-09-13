import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { InteropPanel } from './InteropPanel';

/**
 * Other tools' records, on the surface — `M52`, `SEC-43`, `AC-59` (MV3-T06).
 *
 * The panel's job is to make a tamper-evident record legible without letting
 * anybody read more into it than it says. Two failures would be worse than
 * having no panel at all:
 *
 *  - presenting somebody else's claim as Meridian's own observation, or at a
 *    confidence Meridian has no basis for (`FR-M52-02`);
 *  - letting a signature beside a claim read as a signature on the claim
 *    (`SEC-43`).
 *
 * And one that would make the feature pointless: showing an altered record
 * as though nothing had happened.
 */

const RECORD = {
  tool: 'aider',
  kind: 'git-note' as const,
  source: 'refs/notes/aider',
  commit: 'abcdef0123456789',
  digest: `sha256:${'a'.repeat(64)}`,
  observedAt: '2026-09-13T10:00:00Z',
  confidence: 'inferred' as const,
  truncated: false,
  notEndorsed: 'Meridian signed the digest of this record, not its content.',
};

function mount(responses: Record<string, unknown> = {}) {
  const host = makeHost({
    'interop/records': { records: [RECORD] },
    'interop/notarise': { notarised: 1, alreadyNotarised: 0, records: [RECORD] },
    'interop/verify': { verdicts: [], altered: 0, missing: 0, unreadable: 0 },
    ...responses,
  });
  const client = new WebviewRpcClient(host.transport);
  render(<InteropPanel client={client} ready />);
  return { host, client };
}

describe('what the panel says before anything is read', () => {
  it('states what the signature covers, and what it does not', () => {
    // SEC-43. The documentation is not open while somebody is looking at
    // this, so the sentence has to be here.
    mount();
    const boundary = screen.getByTestId('interop-boundary');
    expect(boundary).toHaveTextContent('signs the digest, not the claim');
    expect(boundary).toHaveTextContent('does not vouch for them');
    expect(boundary).toHaveTextContent('inferred');
  });

  it('reads nothing until asked', async () => {
    const { host, client } = mount();
    await waitFor(() => expect(screen.getByTestId('interop-boundary')).toBeInTheDocument());
    expect(host.requests).toEqual([]);
    client.dispose();
  });
});

describe('reading is separate from recording', () => {
  it('showing what is here writes nothing', async () => {
    // Looking at your own repository should not be an action that records.
    const { host, client } = mount();
    fireEvent.click(screen.getByTestId('interop-read'));
    await host.settle();
    expect(host.requests.map((r) => r.method)).toEqual(['interop/records']);
    expect(host.requests.some((r) => r.method === 'interop/notarise')).toBe(false);
    client.dispose();
  });

  it('attributes each record to the tool that wrote it, at inferred', async () => {
    // X-27 and FR-M52-02 together: the vendor tag carries the confidence, and
    // the confidence is the bottom rung because Meridian read a file rather
    // than watching the work.
    const { host, client } = mount();
    fireEvent.click(screen.getByTestId('interop-read'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('interop-records')).toBeInTheDocument());
    const tag = screen.getByTestId('vendor-tag');
    expect(tag).toHaveTextContent('Aider');
    expect(tag).toHaveAccessibleName(/inferred/);
    client.dispose();
  });

  it('notarising says what it recorded', async () => {
    const { host, client } = mount();
    fireEvent.click(screen.getByTestId('interop-notarise'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-notarised')).toHaveTextContent(
        'Recorded the digest of 1 record',
      ),
    );
    client.dispose();
  });

  it('says plainly when there was nothing new to record', async () => {
    // Proving the same unchanged thing again is not progress, and reporting
    // it as though it were would inflate what the ledger appears to hold.
    const { host, client } = mount({
      'interop/notarise': { notarised: 0, alreadyNotarised: 3, records: [RECORD] },
    });
    fireEvent.click(screen.getByTestId('interop-notarise'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-notarised')).toHaveTextContent(
        'Nothing new to record',
      ),
    );
    client.dispose();
  });
});

describe('AC-59 on the surface', () => {
  it('an altered record is unmissable', async () => {
    const { host, client } = mount({
      'interop/verify': {
        verdicts: [
          {
            ok: false,
            tool: 'aider',
            source: 'refs/notes/aider',
            commit: 'abcdef0123456789',
            digestAtNotarisation: `sha256:${'a'.repeat(64)}`,
            digestNow: `sha256:${'b'.repeat(64)}`,
            detail: 'This record has been altered since Meridian notarised it.',
          },
        ],
        altered: 1,
        missing: 0,
        unreadable: 0,
      },
    });
    fireEvent.click(screen.getByTestId('interop-verify'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-verification')).toHaveTextContent('ALTERED'),
    );
    expect(screen.getByTestId('interop-verdict-abcdef0123456789')).toHaveTextContent(
      'altered since Meridian notarised it',
    );
    client.dispose();
  });

  it('a removed record is reported as gone, not as altered', async () => {
    const { host, client } = mount({
      'interop/verify': { verdicts: [], altered: 0, missing: 2, unreadable: 0 },
    });
    fireEvent.click(screen.getByTestId('interop-verify'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-verification')).toHaveTextContent(
        'gone, which is not the same as altered',
      ),
    );
    client.dispose();
  });

  it('an entry that could not be checked is not reported as passing', async () => {
    // P26: "we could not look" is not "we looked and it was fine".
    const { host, client } = mount({
      'interop/verify': { verdicts: [], altered: 0, missing: 0, unreadable: 1 },
    });
    fireEvent.click(screen.getByTestId('interop-verify'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-verification')).toHaveTextContent(
        'could not be read back, so they were not checked',
      ),
    );
    client.dispose();
  });
});

const CLAIM_MERIDIAN = {
  claimant: 'meridian-ledger',
  tool: 'meridian',
  agents: ['copilot'],
  confidence: 'direct' as const,
  evidence: 'ledger 3-4',
};
const CLAIM_AIDER = {
  claimant: 'refs/notes/aider',
  tool: 'aider',
  agents: ['aider'],
  confidence: 'inferred' as const,
  evidence: `sha256:${'c'.repeat(64)}`,
};
const NOT_RESOLVED =
  'These records disagree about which agent produced this commit. Meridian reports the disagreement and does not decide it: no claim is preferred, including Meridian’s own.';

function conflicts(overrides: Record<string, unknown> = {}) {
  return {
    examined: 12,
    truncated: false,
    claimed: 3,
    agreeing: 1,
    disagreements: [
      {
        commit: 'abcdef0123456789',
        kind: 'conflicting',
        claims: [CLAIM_MERIDIAN, CLAIM_AIDER],
        digest: `sha256:${'d'.repeat(64)}`,
        notResolved: NOT_RESOLVED,
      },
    ],
    recorded: 0,
    ...overrides,
  };
}

describe('AC-60 on the surface: when records disagree', () => {
  it('finding disagreements reads and records nothing', async () => {
    const { host, client } = mount({ 'interop/conflicts': conflicts() });
    fireEvent.click(screen.getByTestId('interop-conflicts'));
    await host.settle();
    expect(host.requests.map((r) => [r.method, r.params])).toEqual([['interop/conflicts', {}]]);
    client.dispose();
  });

  it('shows every claim beside the others and prefers none, including its own', async () => {
    const { host, client } = mount({ 'interop/conflicts': conflicts() });
    fireEvent.click(screen.getByTestId('interop-conflicts'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('interop-disagreements')).toBeInTheDocument());
    const tags = screen.getAllByTestId('vendor-tag');
    expect(tags).toHaveLength(2);
    expect(tags[0]).toHaveAccessibleName(/direct/);
    expect(tags[1]).toHaveAccessibleName(/inferred/);
    expect(screen.getByTestId('interop-not-resolved')).toHaveTextContent('no claim is preferred');
    expect(screen.getByText('Records name different agents')).toBeInTheDocument();
    client.dispose();
  });

  it('does not present a walk that stopped early as a clean report', async () => {
    const { host, client } = mount({
      'interop/conflicts': conflicts({ truncated: true, disagreements: [] }),
    });
    fireEvent.click(screen.getByTestId('interop-conflicts'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-conflicts-summary')).toHaveTextContent('not a clean report'),
    );
    client.dispose();
  });

  it('records disagreements only when asked, and says what it recorded', async () => {
    const { host, client } = mount({ 'interop/conflicts': conflicts({ recorded: 1 }) });
    fireEvent.click(screen.getByTestId('interop-conflicts'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('interop-conflicts-record')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('interop-conflicts-record'));
    await host.settle();
    expect(host.requests.map((r) => r.params)).toEqual([{}, { record: true }]);
    await waitFor(() =>
      expect(screen.getByTestId('interop-conflicts-recorded')).toHaveTextContent(
        'Recorded 1 disagreement',
      ),
    );
    client.dispose();
  });
});

describe('the ordinary repository', () => {
  it('says an absence of other tools is not a fault', async () => {
    // Most repositories. Reporting this as a problem would teach people to
    // ignore the panel that matters.
    const { host, client } = mount({ 'interop/records': { records: [] } });
    fireEvent.click(screen.getByTestId('interop-read'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-empty')).toHaveTextContent(
        'not a fault',
      ),
    );
    client.dispose();
  });
});
