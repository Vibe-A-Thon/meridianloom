import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as vscode from 'vscode';
import type { RunPreflight } from '../../shared/ts/bus-types';
import { registerCommands } from '../src/commands';

/**
 * `meridian.startRun` — the command-palette door (FR-M40-01/02/03/09, AC-38).
 *
 * What is being tested is that this door is a *door*, not a second product.
 * It collects an intent, asks the sidecar what the run would do, shows that
 * to a human, and calls the one entry point. Every rule about what a run is —
 * which answers are required, who may launch, what gets recorded — lives on
 * the other side of the bus, so the thing to check here is that the palette
 * never decides any of it for itself.
 *
 * The invariant with teeth: **nothing reaches `run/start` that a human did
 * not confirm, and nothing is confirmable that preflight called incomplete.**
 */

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __messageChoices: string[];
  __inputResponses: Array<string | undefined>;
  __inputBoxCalls: unknown[];
  __shownInfos: string[];
  __shownWarnings: string[];
  __shownErrors: string[];
};

function preflight(over: Partial<RunPreflight> = {}): RunPreflight {
  return {
    runId: 'run_20260913T120000_abcd1234',
    origin: 'command',
    intent: 'Add an idempotency key to the payment submission endpoint',
    adapters: { Developer: 'acme-java-developer' },
    repo: 'payments-service',
    baseBranch: 'main',
    branch: 'meridian/run_20260913T120000_abcd1234',
    worktree: '.meridian/worktrees/run_20260913T120000_abcd1234',
    estimateUsd: 3.1,
    costCeilingUsd: 6,
    gates: ['DoR', 'DoD', 'Security'],
    mode: 'dry_run',
    confirmable: true,
    missing: [],
    ...over,
  } as RunPreflight;
}

function wire(over: Partial<RunPreflight> = {}) {
  const runStart = vi.fn(async () => ({
    runId: preflight(over).runId,
    origin: 'command',
    branch: preflight(over).branch,
    worktree: preflight(over).worktree,
    mode: preflight(over).mode,
    authorisedBy: 'alice@example.com',
    assurance: 'asserted',
    sequence: 1,
  }));
  const runCancel = vi.fn(async () => ({ runId: preflight(over).runId, cancelled: true }));
  const runPreflight = vi.fn(async () => ({ preflight: preflight(over) }));
  registerCommands({
    runPreflight: runPreflight as never,
    runStart: runStart as never,
    runCancel: runCancel as never,
  });
  const start = mock.__registeredCommands.get('meridian.startRun') as () => Promise<void>;
  return { start, runPreflight, runStart, runCancel };
}

describe('the palette door', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('records the door it came through and nothing else about it', async () => {
    // AC-38: what distinguishes this initiation path from the workbench is
    // the `origin` it reports. If the palette started sending its own
    // branch, mode or gate list, five doors would mean five ideas of what a
    // run is — which is the thing M40 exists to prevent.
    const { start, runPreflight } = wire();
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await start();
    expect(runPreflight).toHaveBeenCalledTimes(1);
    const params = runPreflight.mock.calls[0][0] as unknown as { origin: string };
    expect(params.origin).toBe('command');
  });

  it('shows the four answers and where the run will stop', async () => {
    const { start } = wire();
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await start();
    const shown = mock.__shownWarnings.at(-1) ?? '';
    expect(shown).toContain('idempotency key');
    expect(shown).toContain('acme-java-developer');
    expect(shown).toContain('payments-service');
    expect(shown).toContain('$3.10');
    expect(shown).toContain('$6.00');
    expect(shown).toContain('Security');
    // The product's core safety claim belongs where the decision is made.
    expect(shown).toContain('your working tree is untouched');
    expect(shown).toContain('Nothing exists until you confirm');
  });

  it('starts the run once the human confirms', async () => {
    const { start, runStart } = wire();
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await start();
    expect(runStart).toHaveBeenCalledTimes(1);
    const params = runStart.mock.calls[0][0] as unknown as { confirmed: boolean };
    expect(params.confirmed).toBe(true);
    expect(mock.__shownInfos.at(-1)).toContain('authorised by alice@example.com');
    // The assurance is on screen: a run authorised by a git name must never
    // read later as one that was verified.
    expect(mock.__shownInfos.at(-1)).toContain('assurance asserted');
  });

  it('does not start a run the human dismissed', async () => {
    const { start, runStart, runCancel } = wire();
    mock.__inputResponses.push('Add an idempotency key');
    // No choice queued: the modal returns undefined, as Escape does.
    await start();
    expect(runStart).not.toHaveBeenCalled();
    // FR-M40-09: the cancellation is still a fact worth keeping.
    expect(runCancel).toHaveBeenCalledTimes(1);
  });

  it('does not preflight a run with no intent', async () => {
    // Escaping the input box is a decision not to start, and it should not
    // produce a run id, a preflight, or a ledger entry.
    const { start, runPreflight, runCancel } = wire();
    await start();
    expect(runPreflight).not.toHaveBeenCalled();
    expect(runCancel).not.toHaveBeenCalled();
  });

  it('refuses to offer a button for an incomplete preflight', async () => {
    // The invariant. `confirmable` is the sidecar's answer, and the palette
    // must not second-guess it: a modal offering "Start" over an incomplete
    // preflight collects consent for a run nobody could describe.
    const { start, runStart } = wire({
      confirmable: false,
      missing: ['estimate', 'gates'],
    });
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await start();
    expect(runStart).not.toHaveBeenCalled();
    const warned = mock.__shownWarnings.at(-1) ?? '';
    expect(warned).toContain('estimate');
    expect(warned).toContain('Nothing has been created');
  });

  it('a live run is confirmed in its own words', async () => {
    // B9: a live run writes to a real repository and spends real money, and
    // the confirm must not read like the dry run's.
    const { start, runStart } = wire({ mode: 'live' });
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Confirm live run');
    await start();
    expect(runStart).toHaveBeenCalledTimes(1);
  });

  it('never renders an unknown estimate as a free run', async () => {
    // P26: `null` is unknown. "$0.00" would tell a human this costs nothing.
    const { start } = wire({ estimateUsd: null, costCeilingUsd: null });
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await start();
    const shown = mock.__shownWarnings.at(-1) ?? '';
    expect(shown).toContain('not estimated');
    expect(shown).not.toContain('$0.00');
  });

  it('reports a refusal instead of throwing it', async () => {
    // A launch the role pack refuses arrives here as a rejected promise. An
    // unhandled rejection would leave the human with neither a run nor a
    // reason.
    registerCommands({
      runPreflight: (async () => ({ preflight: preflight() })) as never,
      runStart: (async () => {
        throw new Error('alice@example.com is not permitted to start a live run');
      }) as never,
    });
    const start = mock.__registeredCommands.get('meridian.startRun') as () => Promise<void>;
    mock.__inputResponses.push('Add an idempotency key');
    mock.__messageChoices.push('Start dry run');
    await expect(start()).resolves.toBeUndefined();
    expect(mock.__shownErrors.at(-1)).toContain('not permitted');
  });

  it('reports rather than acts when the sidecar is not connected', async () => {
    registerCommands({});
    const start = mock.__registeredCommands.get('meridian.startRun') as () => Promise<void>;
    await start();
    expect(mock.__shownWarnings.at(-1)).toContain('not connected');
    expect(mock.__inputBoxCalls).toHaveLength(0);
  });
});
