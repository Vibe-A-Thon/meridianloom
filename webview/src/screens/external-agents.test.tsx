import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';

/**
 * 10.46 External Agents (gaps_guix §3) against a scripted host: session
 * list with vendor tags + confidence (X-27/X-29), per-session detail from
 * attrib/diff + attrib/classify + trailers/parse, observer health with
 * NFR-32 degradation prominent and the verbatim NO_OTEL_DIRECT_WARNING,
 * and the FR-M35-06 guarantee that nothing on the screen drives an agent.
 */

const NO_OTEL_WARNING =
  'Local Claude Code is observed without OpenTelemetry: `direct` confidence is not available. ' +
  'Enable Claude Code\'s OTel export for direct observation; until then Meridian uses ' +
  'Co-Authored-By trailers and filesystem inference (telemetry at best).';

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
  warnings: ['copilot observer degraded to inferred'],
});

const healthFixture = () => ({
  monitorRunning: true,
  observers: [
    {
      name: 'claude-code',
      vendor: 'claude-code',
      status: 'ok',
      detail: `OTel export not configured — ${NO_OTEL_WARNING}`,
      vendorRelease: '1.0',
      adapterVersion: '1.0.0',
      warnings: [],
    },
    {
      name: 'copilot',
      vendor: 'copilot',
      status: 'degraded',
      detail: 'SCM API response schema drifted from adapter expectations',
      vendorRelease: '2026.09',
      adapterVersion: '0.9.0',
      warnings: ['copilot observation downgraded to inferred'],
    },
  ],
});

const diffFixture = () => ({
  repoPath: '/repo/ws',
  base: null,
  compare: null,
  staged: false,
  files: [
    {
      path: 'src/PaymentController.java',
      oldPath: null,
      status: 'modified',
      hunks: [
        {
          oldStart: 40,
          oldCount: 3,
          newStart: 40,
          newCount: 5,
          lines: [
            { kind: 'context', oldLine: 40, newLine: 40, content: '  public Result submit() {' },
            { kind: 'added', oldLine: null, newLine: 41, content: '    String key = idempotency();' },
            { kind: 'added', oldLine: null, newLine: 42, content: '    return submitWith(key);' },
            { kind: 'context', oldLine: 41, newLine: 43, content: '  }' },
          ],
        },
      ],
    },
  ],
});

const classifyFixture = () => ({
  repoPath: '/repo/ws',
  files: [
    {
      path: 'src/PaymentController.java',
      linesAdded: 2,
      linesRemoved: 0,
      burstLines: 2,
      multiLineInsertRate: 1,
      editTimestamp: '2026-09-20T10:05:00Z',
      attribution: 'agent',
      agentWeight: 0.82,
      observationConfidence: 'telemetry',
      rationale: ['Co-Authored-By trailer present', 'multi-line insertion burst'],
    },
  ],
});

const trailersSinceFixture = () => ({
  commits: [
    {
      commit: 'abc123def4567890',
      authoredAt: '2026-09-20T10:05:00Z',
      attributions: [
        { name: 'Claude', email: 'noreply@anthropic.com', vendor: 'claude', meridianAuthored: false },
      ],
      meridianLedger: ['4398-4402'],
    },
  ],
});

async function renderExternalAgents(host: ReturnType<typeof makeHost>) {
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  render(<App client={client} />);
  await act(async () => {});
  await host.settle();
  fireEvent.click(screen.getByRole('button', { name: 'External Agents' }));
  await act(async () => {});
  await host.settle();
  return client;
}

describe('10.46 External Agents screen', () => {
  it('lists sessions with VendorTag + confidence and sticky warnings (X-27, X-29, NFR-32)', async () => {
    const host = makeHost({
      'observe/sessions': sessionsFixture(),
      'observe/health': healthFixture(),
    });
    const client = await renderExternalAgents(host);

    const tags = screen.getAllByTestId('vendor-tag');
    expect(tags[0]).toHaveAccessibleName('Claude Code, from telemetry');
    expect(tags[1]).toHaveAccessibleName('Copilot, observed directly');
    expect(screen.getByTestId('observer-warnings')).toHaveTextContent(
      'copilot observer degraded to inferred',
    );
    expect(screen.getByText(/Meridian observes these sessions/)).toBeInTheDocument();
    client.dispose();
  });

  it('observer health: degradation prominent, monitor state, NO_OTEL warning verbatim', async () => {
    const host = makeHost({
      'observe/sessions': sessionsFixture(),
      'observe/health': healthFixture(),
    });
    const client = await renderExternalAgents(host);

    expect(screen.getByText(/Session monitor is polling/)).toBeInTheDocument();
    const degraded = screen.getByText(/⚠ copilot/).closest('li')!;
    expect(degraded).toHaveAttribute('data-status', 'degraded');
    expect(degraded).toHaveTextContent('copilot observation downgraded to inferred');
    // The F0-D mandate text renders verbatim from the sidecar payload.
    expect(screen.getByText(new RegExp(NO_OTEL_WARNING.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeInTheDocument();
    client.dispose();
  });

  it('session detail attributes hunks, shows classify confidence + rationale and trailers', async () => {
    const host = makeHost({
      'observe/sessions': sessionsFixture(),
      'observe/health': healthFixture(),
      'attrib/diff': diffFixture(),
      'attrib/classify': classifyFixture(),
      'trailers/parse': trailersSinceFixture(),
    });
    const client = await renderExternalAgents(host);

    fireEvent.click(screen.getByRole('button', { name: /Claude Code/ }));
    await host.settle();

    expect(host.requests).toContainEqual(
      expect.objectContaining({ method: 'attrib/diff', params: { repoPath: '/repo/ws' } }),
    );
    expect(host.requests).toContainEqual(
      expect.objectContaining({
        method: 'attrib/classify',
        params: expect.objectContaining({
          repoPath: '/repo/ws',
          observedSessions: [
            expect.objectContaining({ sessionId: 'sess-1', vendor: 'claude-code' }),
          ],
        }),
      }),
    );
    expect(host.requests).toContainEqual(
      expect.objectContaining({
        method: 'trailers/parse',
        params: { repoPath: '/repo/ws', since: '2026-09-20T10:00:00Z' },
      }),
    );

    const detail = screen.getByTestId('session-detail');
    expect(detail).toHaveTextContent('src/PaymentController.java');
    expect(detail).toHaveTextContent('+2 −0');
    expect(detail).toHaveTextContent('agent · telemetry');
    expect(detail).toHaveTextContent('Co-Authored-By trailer present');
    expect(detail).toHaveTextContent('Claude (claude)');
    expect(detail).toHaveTextContent('Meridian-Ledger: 4398-4402');
    client.dispose();
  });

  it('without a workspace folder the detail says so instead of guessing', async () => {
    const host = makeHost(
      {
        'observe/sessions': sessionsFixture(),
        'observe/health': healthFixture(),
      },
      { workspaceDir: undefined },
    );
    const client = await renderExternalAgents(host);

    fireEvent.click(screen.getByRole('button', { name: /Claude Code/ }));
    await host.settle();

    expect(screen.getByRole('note')).toHaveTextContent('Open a folder in this window');
    expect(host.requests.filter((r) => r.method.startsWith('attrib/'))).toHaveLength(0);
    client.dispose();
  });

  it('FR-M35-06: nothing on the screen can steer, stop or reconfigure an agent', async () => {
    const host = makeHost({
      'observe/sessions': sessionsFixture(),
      'observe/health': healthFixture(),
      'attrib/diff': diffFixture(),
      'attrib/classify': classifyFixture(),
      'trailers/parse': trailersSinceFixture(),
    });
    const client = await renderExternalAgents(host);
    fireEvent.click(screen.getByRole('button', { name: /Claude Code/ }));
    await host.settle();

    const driveControls = screen
      .getAllByRole('button')
      .filter((button) => /steer|stop|pause|interrupt|reconfigure/i.test(button.textContent ?? ''));
    expect(driveControls).toHaveLength(0);
    client.dispose();
  });

  it('X-29: a pushed session change re-queries while the screen is open', async () => {
    const host = makeHost({
      'observe/sessions': sessionsFixture(),
      'observe/health': healthFixture(),
    });
    const client = await renderExternalAgents(host);
    const before = host.requests.filter((r) => r.method === 'observe/sessions').length;

    host.deliverHostMessage({
      type: 'event',
      event: { kind: 'sessions/changed', detail: 'cursor appeared' },
    });
    await act(async () => {});
    await host.settle();

    await waitFor(() =>
      expect(host.requests.filter((r) => r.method === 'observe/sessions').length).toBeGreaterThan(
        before,
      ),
    );
    client.dispose();
  });
});
