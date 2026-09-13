import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { PullRequestCard } from './PullRequestCard';

/**
 * The pull-request evidence card — `FR-M46-03`, `MVP-R2.5`, `J2`, `H7`
 * (MV3-T04).
 *
 * The load-bearing test is `an approved gate on a stale head is not a pass`.
 * A checks-passed badge means the checks passed on *some* revision; if the
 * head has moved, the badge describes code that is not the code being
 * merged. Every interface that renders a green tick beside a stale commit is
 * asserting something it never checked, and this card exists to stop doing
 * that.
 *
 * The rest is `J2` and `H7`: a figure that could not be computed says so
 * rather than rendering blank, and the finding is a sentence naming the
 * action rather than a status chip naming the state.
 */

const HEAD = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const MOVED = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

const ENFORCEMENT = {
  vocabularyVersion: 1,
  vocabulary: ['editor', 'extension_host', 'sidecar', 'scm', 'ci', 'advisory_only'],
  scmBindingConfigured: false,
  controls: {
    merge_gate: {
      control: 'merge_gate',
      enforcementPoint: 'sidecar',
      enforced: true,
      boundaryNote: 'Computed in the Meridian sidecar and consumed by CI/SCM connectors.',
    },
  },
};

function status(over: Record<string, unknown> = {}) {
  return {
    subject: 'pr:acme/payments-service#4417',
    ingested: true,
    storyId: 'edb-4417',
    headCommit: HEAD,
    baseBranch: 'main',
    gates: [
      { gate: 'Verify', decision: 'pass', sequence: 10 },
      { gate: 'Security', decision: 'pass', sequence: 11 },
    ],
    merge: { status: 'approved', subject: 'pr:acme/payments-service#4417', requiredApproval: true, halted: false },
    ...over,
  };
}

function conflicts(over: Record<string, unknown> = {}) {
  return {
    repoPath: '/repo',
    base: 'main',
    ref: HEAD,
    storyId: 'edb-4417',
    hunks: [
      {
        path: 'src/Payments.java',
        oldStart: 1,
        oldCount: 2,
        newStart: 1,
        newCount: 4,
        agent: { agentId: 'claude-code:claude', vendor: 'claude-code', name: 'claude', confidence: 'telemetry', source: 'trailer' },
        commit: HEAD,
      },
    ],
    conflicts: [],
    recorded: 0,
    duplicatesSkipped: 0,
    ...over,
  };
}

function mount(responses: Record<string, unknown> = {}) {
  const host = makeHost({
    'governance/enforcementPoints': ENFORCEMENT,
    'pr/status': status(),
    'pr/conflicts': conflicts(),
    'spend/series': { scope: {}, dimension: 'story', totals: { costUsd: 12.5 }, byValue: {} },
    ...responses,
  });
  const client = new WebviewRpcClient(host.transport);
  render(<PullRequestCard client={client} ready />);
  return { host, client };
}

async function load(host: ReturnType<typeof mount>['host']) {
  fireEvent.change(screen.getByTestId('pr-subject'), {
    target: { value: 'pr:acme/payments-service#4417' },
  });
  fireEvent.click(screen.getByTestId('pr-load'));
  await host.settle();
  await waitFor(() => expect(screen.getByTestId('pr-card')).toBeInTheDocument());
}

describe('the revision actually tested', () => {
  it('an approved gate on a stale head is not a pass', async () => {
    // The test the card exists for. Verify and Security both passed, the
    // merge gate is approved — and they all describe a commit that is no
    // longer the head of the branch.
    const { host, client } = mount({
      'pr/conflicts': conflicts({ ref: MOVED }),
    });
    await load(host);
    expect(screen.getByTestId('pr-revision')).toHaveTextContent(
      'describe a different revision from the one you would merge',
    );
    expect(screen.getByTestId('pr-action')).toHaveTextContent(
      'Re-run the gates against the current head',
    );
    client.dispose();
  });

  it('says so plainly when the head is still the head', async () => {
    const { host, client } = mount();
    await load(host);
    expect(screen.getByTestId('pr-revision')).toHaveTextContent('still the head of the branch');
    client.dispose();
  });

  it('does not claim a match it could not check', async () => {
    // J2/P26: when the branch could not be read there is nothing to compare,
    // and "still the head" would be an assertion nobody made.
    const { host, client } = mount({
      'pr/conflicts': new Error('not a git repository'),
    });
    await load(host);
    expect(screen.getByTestId('pr-revision')).toHaveTextContent(
      'could not read the branch to check',
    );
    client.dispose();
  });

  it('says when no revision was recorded at all', async () => {
    const { host, client } = mount({ 'pr/status': status({ headCommit: null }) });
    await load(host);
    expect(screen.getByTestId('pr-revision')).toHaveTextContent(
      'nothing to check the gate verdicts against',
    );
    client.dispose();
  });
});

describe('H7: the finding is a sentence, and it names the action', () => {
  it('a blocked gate says what to fix and what approving over it means', async () => {
    const { host, client } = mount({
      'pr/status': status({
        gates: [
          { gate: 'Verify', decision: 'pass', sequence: 10 },
          { gate: 'Security', decision: 'block', sequence: 11 },
        ],
      }),
    });
    await load(host);
    expect(screen.getByTestId('pr-action')).toHaveTextContent('Fix what Security blocked');
    expect(screen.getByTestId('pr-action')).toHaveTextContent('recorded as such');
    client.dispose();
  });

  it('a halt outranks everything else on the card', async () => {
    const { host, client } = mount({
      'pr/status': status({
        merge: { status: 'blocked', subject: 'x', requiredApproval: true, halted: true },
      }),
    });
    await load(host);
    expect(screen.getByTestId('pr-action')).toHaveTextContent('governance halt is active');
    client.dispose();
  });

  it('a missing approval names what is missing', async () => {
    const { host, client } = mount({
      'pr/status': status({
        merge: {
          status: 'blocked',
          subject: 'x',
          requiredApproval: true,
          halted: false,
          missing: ['two approvals required, one recorded'],
        },
      }),
    });
    await load(host);
    expect(screen.getByTestId('pr-action')).toHaveTextContent('two approvals required');
    client.dispose();
  });

  it('a clean pull request still frames approving as a recorded decision', async () => {
    const { host, client } = mount();
    await load(host);
    expect(screen.getByTestId('pr-action')).toHaveTextContent(
      'recorded as having made',
    );
    client.dispose();
  });
});

describe('change risk', () => {
  it('agent-vs-agent overlap is the strongest signal', async () => {
    const { host, client } = mount({
      'pr/conflicts': conflicts({
        conflicts: [
          {
            path: 'src/Payments.java',
            kind: 'edited-over-agent-lines',
            agents: [],
            recordedSequence: null,
            alreadyRecorded: false,
          },
        ],
      }),
    });
    await load(host);
    expect(screen.getByTestId('pr-risk')).toHaveTextContent('high');
    expect(screen.getByTestId('pr-risk')).toHaveTextContent('no single review');
    client.dispose();
  });

  it('unmeasured risk is not rendered as low risk', async () => {
    // The failure this guards against: a gap that reads as reassurance.
    const { host, client } = mount({ 'pr/conflicts': new Error('analysis failed') });
    await load(host);
    expect(screen.getByTestId('pr-risk')).toHaveTextContent('unknown');
    expect(screen.getByTestId('pr-risk')).not.toHaveTextContent('low');
    client.dispose();
  });
});

describe('J2: a figure that was not measured says so', () => {
  it('an unavailable cost is not zero', async () => {
    const { host, client } = mount({ 'spend/series': new Error('pricing pack missing') });
    await load(host);
    expect(screen.getByTestId('pr-cost')).toHaveTextContent('Not measured');
    expect(screen.getByTestId('pr-cost')).not.toHaveTextContent('$0.00');
    client.dispose();
  });

  it('an unrecorded cost inside a measured result is not zero either', async () => {
    const { host, client } = mount({
      'spend/series': { scope: {}, dimension: 'story', totals: {}, byValue: {} },
    });
    await load(host);
    expect(screen.getByTestId('pr-cost')).toHaveTextContent('not recorded');
    expect(screen.getByTestId('pr-cost')).not.toHaveTextContent('$0.00');
    client.dispose();
  });

  it('no attributed hunks means nothing to compare, not a clean bill', async () => {
    const { host, client } = mount({ 'pr/conflicts': conflicts({ hunks: [] }) });
    await load(host);
    expect(screen.getByTestId('pr-coverage')).toHaveTextContent(
      'nothing to compare',
    );
    client.dispose();
  });
});

describe('what the card will not do', () => {
  it('carries the enforcement point of the control behind its verdict', async () => {
    const { host, client } = mount();
    await load(host);
    expect(screen.getByTestId('enforcement-badge')).toBeInTheDocument();
    client.dispose();
  });

  it('offers no approve button', async () => {
    // An approve control here would be a second, quieter route to a governed
    // decision, away from the surface that binds it to an identity.
    const { host, client } = mount();
    await load(host);
    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull();
    expect(screen.getByTestId('pr-footnote')).toHaveTextContent('Gate Room');
    client.dispose();
  });

  it('reads nothing until a pull request is named', async () => {
    const { host, client } = mount();
    await waitFor(() => expect(screen.getByTestId('pr-subject')).toBeInTheDocument());
    expect(host.requests.some((r) => r.method === 'pr/status')).toBe(false);
    client.dispose();
  });
});
