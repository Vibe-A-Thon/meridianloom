import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { SCREEN_REGISTRY, visibleScreens } from './registry';

/**
 * Screen-level invariants that hold across every GF0 screen, whatever
 * panel they appear in:
 *
 * X-27 — every agent-attributed row carries a VendorTag whose accessible
 *   name states the observation confidence (banned 18: never bare).
 * X-28 — the Loom Bar is registry-generated and tier-filtered; upper
 *   tiers are absent, never disabled entries.
 * X-29 — a sessions/changed push re-queries observe/sessions and the
 *   Crown indicator reflects the new truth within the poll window.
 * X-30 — every provenance-target opens the same provenance card on
 *   focus (hover optional), with approval state stated honestly.
 */

const okVerify = () => ({
  ok: true,
  entriesChecked: 4402,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T14:22:00Z',
});

const ledgerEntries = () => ({
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

const sessionsFixture = () => ({
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
    {
      sessionId: 'sess-2',
      vendor: 'copilot',
      confidence: 'direct',
      source: 'scm-api',
      detail: 'PR #4821 · 14 files',
      pid: null,
      startedAt: '2026-09-20T09:40:00Z',
      lastActivityAt: null,
      agentId: 'copilot',
    },
  ],
  warnings: [],
});

const healthFixture = () => ({
  monitorRunning: true,
  observers: [
    {
      name: 'claude-code',
      vendor: 'claude-code',
      status: 'ok',
      detail: 'OTel export not configured — trailers + filesystem inference in use',
      vendorRelease: '1.0',
      adapterVersion: '1.0.0',
      warnings: [],
    },
  ],
});

function fullHost(overrides: Record<string, unknown> = {}) {
  return makeHost({
    'observe/sessions': sessionsFixture(),
    'observe/health': healthFixture(),
    'ledger.query': ledgerEntries(),
    'ledger.verify': okVerify(),
    ...overrides,
  });
}

async function renderApp(host: ReturnType<typeof makeHost>) {
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  render(<App client={client} />);
  await act(async () => {});
  await host.settle();
  return client;
}

async function gotoScreen(host: ReturnType<typeof makeHost>, title: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Evidence' }));
  await host.settle();
  const label = { 'Flight Recorder': 'Flight recorder', 'External Agents': 'External sessions', 'Ledger': 'Audit ledger' }[title];
  fireEvent.click(screen.getByRole('tab', { name: new RegExp(label!) }));
  await act(async () => {});
  await host.settle();
}

const CONFIDENCE_NAME = /observed directly|from telemetry|inferred from file changes/;

describe('X-27: VendorTag + confidence on every agent-attributed row, on every screen', () => {
  it('all three screens name the confidence in every vendor tag', async () => {
    const host = fullHost();
    const client = await renderApp(host);

    for (const title of ['Flight Recorder', 'External Agents', 'Ledger']) {
      await gotoScreen(host, title);
      const tags = screen.getAllByTestId('vendor-tag');
      expect(tags.length, `vendor tags on ${title}`).toBeGreaterThan(0);
      for (const tag of tags) {
        expect(tag, `vendor tag on ${title}`).toHaveAccessibleName(CONFIDENCE_NAME);
      }
    }
    client.dispose();
  });
});

describe('X-28: Loom Bar is registry-generated, tier-filtered, nothing upper leaks', () => {
  it('an upper-tier screen is absent from a Flight Recorder bar, and present with its tier', async () => {
    const host = fullHost();
    const client = await renderApp(host);

    const visible = visibleScreens(['flight-recorder']);
    expect(visible.map((s) => s.id)).toEqual(['flight-recorder', 'external-agents', 'ledger']);

    // The invariant, rather than the state of the registry on the day it was
    // written. This assertion used to be "every screen is flight-recorder",
    // which was true only while no upper-tier screen had been built: it would
    // have had to be deleted the first time one was, taking the check with
    // it. What matters is that a screen above the enabled tier does not reach
    // the bar — and, in the other direction, that enabling the tier does
    // bring it, so absence is tiering and not a screen that never worked.
    const upper = SCREEN_REGISTRY.filter((def) => def.tier !== 'flight-recorder');
    expect(upper.length).toBeGreaterThan(0);
    for (const def of upper) {
      expect(visible.map((s) => s.id)).not.toContain(def.id);
      expect(visibleScreens(['flight-recorder', def.tier]).map((s) => s.id)).toContain(def.id);
    }

    const bar = screen.getByRole('navigation', { name: 'Workspace navigation' });
    const tabs = Array.from(bar.querySelectorAll('button')).map((b) => b.getAttribute('aria-label'));
    // The tab bar is generated from WORKBENCH_TABS and filtered by tier:
    // with only flight-recorder enabled, Governance is absent from the row
    // rather than present and disabled (banned 30).
    expect(tabs).toEqual([
      'Dashboard',
      'Deliverables',
      'Runs',
      'Agents',
      'Skills',
      'Instructions',
      'SDLC phases',
      'Learning',
      'Integrations',
      'Portfolio',
      'Modeling',
      'Evidence',
      'Runtime',
      'Settings',
    ]);
    expect(bar).not.toHaveTextContent('Governor');
    expect(bar).not.toHaveTextContent('Orchestra');
    client.dispose();
  });
});

describe('X-29: sessions/changed push re-queries and the Crown updates', () => {
  it('the Crown flips from watching to recording while a non-recorder screen is open', async () => {
    let sessions = { sessions: [] as unknown[], warnings: [] as string[] };
    const host = fullHost({ 'observe/sessions': () => sessions });
    const client = await renderApp(host);
    await gotoScreen(host, 'Ledger');

    expect(screen.getByTestId('crown-indicator')).toHaveTextContent(
      'Watching for agent sessions',
    );
    const before = host.requests.filter((r) => r.method === 'observe/sessions').length;

    sessions = {
      sessions: [
        {
          sessionId: 'sess-9',
          vendor: 'claude-code',
          confidence: 'telemetry',
          source: 'git-trailers',
          detail: '1 file · 1 commit',
          pid: null,
          startedAt: '2026-09-20T14:30:00Z',
          lastActivityAt: null,
          agentId: 'claude-code',
        },
      ],
      warnings: [],
    };
    host.deliverHostMessage({
      type: 'event',
      event: { kind: 'sessions/changed', detail: 'claude appeared' },
    });
    await act(async () => {});
    await host.settle();

    await waitFor(() =>
      expect(host.requests.filter((r) => r.method === 'observe/sessions').length).toBeGreaterThan(
        before,
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId('crown-indicator')).toHaveTextContent('1 sessions observed'),
    );
    client.dispose();
  });
});

describe('X-30: one provenance card, focus-opened, on every screen', () => {
  it('focus opens the card; approval state is honest (null = not yet gated, absent = n/a)', async () => {
    const host = fullHost();
    const client = await renderApp(host);

    await gotoScreen(host, 'Flight Recorder');
    // Flight Recorder: the weave's diff pass has no approval on record.
    const weaveRow = screen.getAllByTestId('provenance-target')[0]!;
    fireEvent.focus(weaveRow);
    const card = screen.getByTestId('provenance-card');
    expect(card.querySelector('[data-testid="vendor-tag"]')).toHaveAccessibleName(
      'Claude Code, from telemetry',
    );
    expect(screen.getByTestId('provenance-approval')).toHaveTextContent(
      'not yet gated — no recorded approval',
    );
    fireEvent.blur(weaveRow);
    expect(screen.queryByTestId('provenance-card')).toBeNull();

    // External Agents: observing-only rows have no approval concept at all.
    await gotoScreen(host, 'External Agents');
    fireEvent.focus(screen.getAllByTestId('provenance-target')[0]!);
    const sessionCard = screen.getByTestId('provenance-card');
    expect(sessionCard.querySelector('[data-testid="vendor-tag"]')).toHaveAccessibleName(
      'Claude Code, from telemetry',
    );
    expect(sessionCard).toHaveTextContent('observed via git-trailers');
    // approvedBy is undefined here: the line is omitted, not negated.
    expect(screen.queryByTestId('provenance-approval')).toBeNull();

    // Ledger: the human approval pass names its approver.
    await gotoScreen(host, 'Ledger');
    const targets = screen.getAllByTestId('provenance-target');
    fireEvent.focus(targets[targets.length - 1]!);
    const ledgerCard = screen.getByTestId('provenance-card');
    expect(ledgerCard).toHaveTextContent('approved by Priya Nair');
    client.dispose();
  });
});
