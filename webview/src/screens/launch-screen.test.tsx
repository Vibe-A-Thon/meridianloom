import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { LaunchScreen } from './LaunchScreen';
import { SCREEN_REGISTRY, visibleScreens } from './registry';
import { WorkspaceOperations } from '../workbench/operations/WorkspaceOperations';

/**
 * 10.51 Launch against a scripted host — FR-M40-01/02/03/09, AC-38/39/40,
 * MV2-T06.
 *
 * `preflight-dialog.test.tsx` pins the dialog's own rules — what it shows,
 * when the confirm is disabled, the two-step live arm. These pin the screen
 * *around* it: that it asks the sidecar rather than deciding, that the door
 * it reports is `ui`, that confirming reaches the single entry point, and
 * that cancelling says what it left behind.
 *
 * The claim with teeth: **the screen never decides whether a preflight is
 * confirmable.** The sidecar answers that, and a surface that recomputed it
 * would be a second definition of what a run is.
 */

const PREFLIGHT = {
  runId: 'run_20260913T120000_abcd1234',
  origin: 'ui',
  intent: 'Add an idempotency key to the payment submission endpoint',
  adapters: { Developer: 'acme-java-developer' },
  repo: '/repo/ws',
  baseBranch: 'main',
  branch: 'meridian/run_20260913T120000_abcd1234',
  worktree: '.meridian/worktrees/run_20260913T120000_abcd1234',
  estimateUsd: 3.1,
  costCeilingUsd: 6,
  gates: ['DoR', 'DoD', 'Security'],
  mode: 'dry_run',
  confirmable: true,
  missing: [] as string[],
};

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
  },
};

/** The least a `WorkspaceOperations` render needs; the launch view reads none of it. */
const WORKBENCH_SNAPSHOT = {
  revision: 1,
  agents: [],
  skills: [],
  instructions: [],
  integrations: [],
  deliverables: [],
  learning: [],
  runs: [],
  documents: [],
  capabilities: {
    workspaceOpen: true,
    trusted: true,
    governorEnabled: true,
    executionReady: true,
  },
} as never;

function mount(over: Partial<typeof PREFLIGHT> = {}, extra: Record<string, unknown> = {}) {
  const host = makeHost({
    'governance/enforcementPoints': ENFORCEMENT,
    'run/preflight': { preflight: { ...PREFLIGHT, ...over } },
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
    ...extra,
  });
  const client = new WebviewRpcClient(host.transport);
  render(
    <LaunchScreen
      client={client}
      ready
      workspaceDir="/repo/ws"
    />,
  );
  return { host, client };
}

async function reachPreflight(host: ReturnType<typeof mount>['host']) {
  fireEvent.change(screen.getByTestId('launch-intent'), {
    target: { value: 'Add an idempotency key' },
  });
  fireEvent.click(screen.getByTestId('launch-preflight'));
  await host.settle();
}

describe('the Launch screen is a door, not a second definition of a run', () => {
  it('records the door it came through', async () => {
    // AC-38: what distinguishes this path from the palette is `origin`.
    const { host, client } = mount();
    await reachPreflight(host);
    const call = host.requests.find((r) => r.method === 'run/preflight');
    expect((call?.params as { origin: string }).origin).toBe('ui');
    client.dispose();
  });

  it('asks the sidecar what the run would do rather than working it out', async () => {
    const { host, client } = mount();
    await reachPreflight(host);
    await waitFor(() => expect(screen.getByTestId('preflight-estimate')).toBeInTheDocument());
    expect(screen.getByTestId('preflight-target')).toHaveTextContent('meridian/run_2026');
    expect(screen.getByTestId('preflight-estimate')).toHaveTextContent('$3.10');
    client.dispose();
  });

  it('does not offer a confirm for a preflight the sidecar called incomplete', async () => {
    // The invariant. `confirmable` is read, never recomputed.
    const { host, client } = mount({ confirmable: false, missing: ['estimate'] });
    await reachPreflight(host);
    await waitFor(() => expect(screen.getByTestId('preflight-confirm')).toBeDisabled());
    expect(screen.getByTestId('preflight-missing')).toHaveTextContent(
      'the cost estimate and ceiling',
    );
    expect(host.requests.some((r) => r.method === 'run/start')).toBe(false);
    client.dispose();
  });

  it('confirming reaches the single entry point and reports who authorised it', async () => {
    const { host, client } = mount();
    await reachPreflight(host);
    fireEvent.click(screen.getByTestId('preflight-confirm'));
    await host.settle();
    const start = host.requests.find((r) => r.method === 'run/start');
    expect((start?.params as { confirmed: boolean }).confirmed).toBe(true);
    await waitFor(() =>
      expect(screen.getByTestId('launch-started')).toHaveTextContent('alice@example.com'),
    );
    // The assurance is on screen: a run authorised by a git name must never
    // read later as one that was verified.
    expect(screen.getByTestId('launch-started')).toHaveTextContent('assurance asserted');
    client.dispose();
  });

  it('cancelling records the cancellation and says what it left behind', async () => {
    // AC-39 on the surface: the reassurance belongs where the decision was
    // made, not only in the ledger afterwards.
    const { host, client } = mount();
    await reachPreflight(host);
    fireEvent.click(screen.getByTestId('preflight-cancel'));
    await host.settle();
    expect(host.requests.some((r) => r.method === 'run/cancel')).toBe(true);
    expect(host.requests.some((r) => r.method === 'run/start')).toBe(false);
    await waitFor(() =>
      expect(screen.getByTestId('launch-cancelled')).toHaveTextContent(
        'No worktree and no branch',
      ),
    );
    client.dispose();
  });

  it('a refused launch is shown, not swallowed', async () => {
    const { host, client } = mount(
      {},
      { 'run/start': new Error('not permitted to start a live run') },
    );
    await reachPreflight(host);
    fireEvent.click(screen.getByTestId('preflight-confirm'));
    await host.settle();
    await waitFor(() =>
      expect(screen.getByTestId('launch-error')).toHaveTextContent('not permitted'),
    );
    client.dispose();
  });

  it('carries the enforcement point of the control it renders', async () => {
    // MV1-T02: no control on this screen claims an unqualified "enforced".
    const { host, client } = mount();
    await reachPreflight(host);
    await waitFor(() => expect(screen.getByTestId('enforcement-badge')).toBeInTheDocument());
    client.dispose();
  });
});

describe('Launch is absent below Governor (FR-M40-11, AC-40)', () => {
  it('is registered at the Governor tier and filtered out below it', () => {
    const definition = SCREEN_REGISTRY.find((entry) => entry.id === 'launch');
    expect(definition?.tier).toBe('governor');
    expect(visibleScreens(['flight-recorder']).map((s) => s.id)).not.toContain('launch');
    expect(visibleScreens(['flight-recorder', 'governor']).map((s) => s.id)).toContain('launch');
  });

  it.each([
    [['flight-recorder'] as const, false],
    [['flight-recorder', 'governor'] as const, true],
  ])('the workbench route a user actually reaches gates it too (%s)', async (tiers, expected) => {
    /**
     * The registry assertion above is necessary and was not sufficient.
     * `SCREEN_REGISTRY` has no production consumer, so registering the
     * screen there put it in the tests and nowhere a person could reach —
     * which the package check found by looking for `preflight-confirm` in
     * the built webview bundle and not finding it.
     *
     * This asserts the mount on the route the shipped app renders: the
     * workbench's `launch` view.
     */
    const host = makeHost({
      'governance/enforcementPoints': ENFORCEMENT,
      'run/preflight': { preflight: PREFLIGHT },
      'ledger.query': { entries: [] },
      'worktree/conflicts': { blocked: false, conflicts: [] },
    });
    const client = new WebviewRpcClient(host.transport);
    render(
      <WorkspaceOperations
        view="launch"
        controller={{
          snapshot: WORKBENCH_SNAPSHOT,
          execute: (async () => WORKBENCH_SNAPSHOT) as never,
          busy: false,
          error: null,
          refresh: async () => {},
        }}
        client={client}
        ready
        workspaceDir="/repo/ws"
        enabledTiers={[...tiers]}
        onNavigate={() => {}}
      />,
    );
    expect(Boolean(screen.queryByTestId('launch-preflight'))).toBe(expected);
    client.dispose();
  });
});
