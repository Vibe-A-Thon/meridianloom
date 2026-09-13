import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { LaunchScreen } from './LaunchScreen';
import { PullRequestCard } from './PullRequestCard';
import { InteropPanel } from './InteropPanel';

/**
 * The assistive journeys — `MVP-R6.5`, `FR-M46-05`, `B3` (MV4-T07).
 *
 * Three journeys an evaluator actually performs — **launch, review and
 * export** — completed without a mouse. A product that cannot be operated
 * from the keyboard is not adoptable in any organisation with an
 * accessibility policy, and that is most of them.
 *
 * ## What this proves, and what it cannot
 *
 * These assert the **structural preconditions** for keyboard and
 * screen-reader operation, which is the half a machine can check honestly:
 *
 *  - every control on the journey is a real control (`button`, `a`, an input)
 *    rather than a clickable `div`, so it is reachable by Tab at all;
 *  - every control has an accessible name, so a screen reader announces
 *    something other than "button";
 *  - the controls appear in the document in the order the journey needs them,
 *    so Tab order follows the task;
 *  - no control on the path is focus-excluded with `tabindex="-1"`;
 *  - state that matters is announced, not only coloured.
 *
 * They do **not** prove a person completed the journey. A recorded pass per
 * journey per mode, by someone using a real screen reader, is the evidence
 * `MV4-T07` asks for, and jsdom cannot stand in for it — jsdom has no
 * accessibility tree and no focus model worth the name. Full WCAG 2.1 AA
 * certification stays `POST-MVP`.
 */

/** Everything a keyboard can land on, in document order. */
function focusables(container: HTMLElement): HTMLElement[] {
  return [
    ...container.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [tabindex]',
    ),
  ].filter((element) => element.getAttribute('tabindex') !== '-1');
}

function accessibleName(element: HTMLElement): string {
  const label = element.getAttribute('aria-label');
  if (label) return label;
  const labelledBy = element.getAttribute('aria-labelledby');
  if (labelledBy) {
    const target = element.ownerDocument.getElementById(labelledBy);
    if (target?.textContent) return target.textContent;
  }
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    const id = element.getAttribute('id');
    const labelled = id
      ? element.ownerDocument.querySelector(`label[for="${id}"]`)
      : element.closest('label');
    if (labelled?.textContent) return labelled.textContent;
    if (element.getAttribute('placeholder')) return element.getAttribute('placeholder') ?? '';
  }
  return element.textContent ?? '';
}

/** No control on the journey announces as a bare role. */
function expectEveryControlNamed(container: HTMLElement) {
  for (const control of focusables(container)) {
    expect(
      accessibleName(control).trim(),
      `a ${control.tagName.toLowerCase()} on this journey has no accessible name, so a ` +
        'screen reader announces only its role',
    ).not.toBe('');
  }
}

const ENFORCEMENT = {
  vocabularyVersion: 1,
  vocabulary: ['editor', 'extension_host', 'sidecar', 'scm', 'ci', 'advisory_only'],
  scmBindingConfigured: false,
  controls: {
    permission_policy: {
      control: 'permission_policy',
      enforcementPoint: 'sidecar',
      enforced: true,
      boundaryNote: 'Checked in the Meridian sidecar on the acting identity.',
    },
    merge_gate: {
      control: 'merge_gate',
      enforcementPoint: 'sidecar',
      enforced: true,
      boundaryNote: 'Computed in the Meridian sidecar.',
    },
  },
};

const PREFLIGHT = {
  runId: 'run_20260913T120000_abcd1234',
  origin: 'ui',
  intent: 'Add an idempotency key',
  adapters: { Developer: 'acme-java-developer' },
  repo: '/repo/ws',
  baseBranch: 'main',
  branch: 'meridian/run_20260913T120000_abcd1234',
  worktree: '.meridian/worktrees/run_20260913T120000_abcd1234',
  estimateUsd: 3.1,
  costCeilingUsd: 6,
  gates: ['DoR', 'DoD'],
  mode: 'dry_run',
  confirmable: true,
  missing: [] as string[],
};

describe('journey 1 — launch, without a mouse', () => {
  function mount() {
    const host = makeHost({
      'governance/enforcementPoints': ENFORCEMENT,
      'run/preflight': { preflight: PREFLIGHT },
      'run/start': {
        runId: PREFLIGHT.runId,
        origin: 'ui',
        branch: PREFLIGHT.branch,
        worktree: PREFLIGHT.worktree,
        mode: 'dry_run',
        authorisedBy: 'alice@example.com',
        assurance: 'asserted',
        sequence: 41,
      },
      'run/cancel': { runId: PREFLIGHT.runId, cancelled: true },
    });
    const client = new WebviewRpcClient(host.transport);
    const view = render(<LaunchScreen client={client} ready workspaceDir="/repo/ws" />);
    return { host, client, view };
  }

  it('the intent field is labelled, not placeholder-only', async () => {
    // A placeholder is not a label: it disappears on focus, which is exactly
    // when a screen-reader user needs it.
    const { client, view } = mount();
    const field = within(view.container).getByLabelText('What should this run do?');
    expect(field).toBeInTheDocument();
    client.dispose();
  });

  it('every control on the way to a started run has an accessible name', async () => {
    const { host, client, view } = mount();
    expectEveryControlNamed(view.container);

    fireEvent.change(screen.getByTestId('launch-intent'), {
      target: { value: 'Add an idempotency key' },
    });
    fireEvent.click(screen.getByTestId('launch-preflight'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('preflight-confirm')).toBeInTheDocument());

    expectEveryControlNamed(view.container);
    client.dispose();
  });

  it('the preflight is a dialog, so a screen reader enters it as one', async () => {
    // Without the role, the decision a person is being asked to make is just
    // more page content that happens to be below the form.
    const { host, client } = mount();
    fireEvent.change(screen.getByTestId('launch-intent'), {
      target: { value: 'Add an idempotency key' },
    });
    fireEvent.click(screen.getByTestId('launch-preflight'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Confirm this run' })).toBeInTheDocument(),
    );
    client.dispose();
  });

  it('cancel comes before confirm in document order', async () => {
    // Tab order follows the document, and the destructive option should not
    // be the first thing a keyboard lands on inside the decision.
    const { host, client, view } = mount();
    fireEvent.change(screen.getByTestId('launch-intent'), {
      target: { value: 'Add an idempotency key' },
    });
    fireEvent.click(screen.getByTestId('launch-preflight'));
    await host.settle();
    await waitFor(() => screen.getByTestId('preflight-confirm'));

    const order = focusables(view.container).map((element) => element.dataset.testid);
    expect(order.indexOf('preflight-cancel')).toBeGreaterThanOrEqual(0);
    expect(order.indexOf('preflight-cancel')).toBeLessThan(order.indexOf('preflight-confirm'));
    client.dispose();
  });

  it('a refusal is announced, not only shown', async () => {
    const host = makeHost({
      'governance/enforcementPoints': ENFORCEMENT,
      'run/preflight': new Error('this workspace requires a verified identity'),
    });
    const client = new WebviewRpcClient(host.transport);
    render(<LaunchScreen client={client} ready workspaceDir="/repo/ws" />);
    fireEvent.change(screen.getByTestId('launch-intent'), { target: { value: 'x' } });
    fireEvent.click(screen.getByTestId('launch-preflight'));
    await host.settle();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    client.dispose();
  });
});

describe('journey 2 — review, without a mouse', () => {
  function mount() {
    const host = makeHost({
      'governance/enforcementPoints': ENFORCEMENT,
      'pr/status': {
        subject: 'pr:acme/payments#4417',
        ingested: true,
        storyId: 'edb-4417',
        headCommit: 'a'.repeat(40),
        baseBranch: 'main',
        gates: [{ gate: 'Security', decision: 'block', sequence: 11 }],
        merge: { status: 'blocked', subject: 'x', requiredApproval: true, halted: false },
      },
      'pr/conflicts': {
        repoPath: '/repo',
        base: 'main',
        ref: 'a'.repeat(40),
        storyId: 'edb-4417',
        hunks: [],
        conflicts: [],
        recorded: 0,
        duplicatesSkipped: 0,
      },
      'spend/series': { scope: {}, dimension: 'story', totals: { costUsd: 1 }, byValue: {} },
    });
    const client = new WebviewRpcClient(host.transport);
    const view = render(<PullRequestCard client={client} ready />);
    return { host, client, view };
  }

  it('the pull-request field is labelled and every control is named', async () => {
    const { host, client, view } = mount();
    expect(within(view.container).getByLabelText('Pull request')).toBeInTheDocument();
    expectEveryControlNamed(view.container);

    fireEvent.change(screen.getByTestId('pr-subject'), {
      target: { value: 'pr:acme/payments#4417' },
    });
    fireEvent.click(screen.getByTestId('pr-load'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('pr-card')).toBeInTheDocument());
    expectEveryControlNamed(view.container);
    client.dispose();
  });

  it('the finding reads as text, not as a colour', async () => {
    // A-02 generalised: the thing a reviewer must act on is a sentence. A
    // risk chip carrying the whole message would be unreadable to anybody
    // not looking at it.
    const { host, client } = mount();
    fireEvent.change(screen.getByTestId('pr-subject'), {
      target: { value: 'pr:acme/payments#4417' },
    });
    fireEvent.click(screen.getByTestId('pr-load'));
    await host.settle();
    await waitFor(() => expect(screen.getByTestId('pr-action')).toBeInTheDocument());
    expect(screen.getByTestId('pr-action').textContent?.trim().length ?? 0).toBeGreaterThan(30);
    client.dispose();
  });
});

describe('journey 3 — export, without a mouse', () => {
  function mount() {
    const host = makeHost({
      'interop/records': { records: [] },
      'interop/notarise': { notarised: 0, alreadyNotarised: 0, records: [] },
      'interop/verify': { verdicts: [], altered: 0, missing: 0, unreadable: 0 },
    });
    const client = new WebviewRpcClient(host.transport);
    const view = render(<InteropPanel client={client} ready />);
    return { host, client, view };
  }

  it('every evidence control is a real control with a name', async () => {
    // The export journey ends here: reading what is recorded and taking it
    // away. A clickable div would be invisible to Tab.
    const { client, view } = mount();
    const controls = focusables(view.container);
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) {
      expect(['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']).toContain(control.tagName);
    }
    expectEveryControlNamed(view.container);
    client.dispose();
  });

  it('the panel is a landmark, so it can be jumped to', async () => {
    const { client } = mount();
    expect(
      screen.getByRole('region', { name: "Other tools' records" }),
    ).toBeInTheDocument();
    client.dispose();
  });

  it('an alteration is announced rather than only coloured', async () => {
    const host = makeHost({
      'interop/records': { records: [] },
      'interop/verify': { verdicts: [], altered: 3, missing: 0, unreadable: 0 },
    });
    const client = new WebviewRpcClient(host.transport);
    render(<InteropPanel client={client} ready />);
    fireEvent.click(screen.getByTestId('interop-verify'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('interop-verification')).toHaveTextContent('ALTERED'),
    );
    client.dispose();
  });
});
