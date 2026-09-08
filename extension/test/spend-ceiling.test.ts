/**
 * FR-M39-02 host half (D33): the sidecar's `spend/ceiling` notification
 * marks a hosted ACP session pause-pending — the pause is enforced at the
 * next turn boundary (ACP has no pause primitive, so nothing mid-flight is
 * touched), observed sessions get the advisory-only warning (FR-M35-06,
 * never a fake pause), and a clean re-run of spend/ceilingCheck resumes.
 */
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  asSpendCeilingNotification,
  assertNotPausePending,
  handleSpendCeilingNotification,
  PAUSE_PENDING_CODE,
  resumeAfterCeilingCleared,
  SpendCeilingPausePendingError,
  SpendCeilingPauseTracker,
  type SpendCeilingHandlerDeps,
} from '../src/governance/spend-ceiling';
import { HostedSessionRegistry } from '../src/governance/session-registry';
import { HostedSteerController } from '../src/governance/steer';
import { AcpClient, type AcpClientOptions } from '../src/acp/client';
import { normalizeEnabledTiers } from '../../shared/ts/tiers';

const FIXTURE = path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs');
const TIMEOUT = 20_000;
const GOVERNOR = normalizeEnabledTiers(['governor']);

const CEILING = {
  sequence: 77,
  sessionId: 'acp-session-9',
  actorId: 'agent-9',
  action: 'pauseAtCheckpoint',
  spentUsd: 12.5,
};

function fixture() {
  const registry = new HostedSessionRegistry();
  const tracker = new SpendCeilingPauseTracker();
  const warnings: string[] = [];
  const logs: string[] = [];
  const deps: SpendCeilingHandlerDeps = {
    registry,
    tracker,
    warn: (m: string) => warnings.push(m),
    log: (m: string) => logs.push(m),
  };
  return { registry, tracker, warnings, logs, deps };
}

describe('spend/ceiling notification routing (FR-M39-02, D33)', () => {
  it('marks a registered hosted session pause-pending and warns', () => {
    const { registry, tracker, warnings, deps } = fixture();
    registry.register(CEILING.sessionId!, { halt: () => undefined });

    const handled = handleSpendCeilingNotification('spend/ceiling', CEILING, deps);

    expect(handled).toBe(true);
    expect(tracker.isPaused(CEILING.sessionId!)).toBe(true);
    expect(tracker.get(CEILING.sessionId!)).toMatchObject({
      sessionId: CEILING.sessionId,
      sequence: 77,
      spentUsd: 12.5,
    });
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('acp-session-9');
    expect(warnings[0]).toContain('seq 77');
    expect(warnings[0]).toContain('pause-pending');
    expect(warnings[0]).toContain('next checkpoint');
  });

  it('a session is paused exactly once even if the notification repeats', () => {
    const { registry, tracker, deps } = fixture();
    registry.register(CEILING.sessionId!, { halt: () => undefined });
    handleSpendCeilingNotification('spend/ceiling', CEILING, deps);
    handleSpendCeilingNotification(
      'spend/ceiling',
      { ...CEILING, sequence: 78, spentUsd: 13 },
      deps,
    );
    expect(tracker.ids()).toEqual([CEILING.sessionId]);
    // The first pause's ledger sequence is kept — the pause is one act.
    expect(tracker.get(CEILING.sessionId!)?.sequence).toBe(77);
  });

  it('an observed (not hosted) session is warned only — never paused', () => {
    const { tracker, warnings, deps } = fixture();
    // Nothing registered: this host does not run the session.

    const handled = handleSpendCeilingNotification('spend/ceiling', CEILING, deps);

    expect(handled).toBe(true);
    expect(tracker.ids()).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('observed, not hosted');
    expect(warnings[0]).toContain('advisory only');
    expect(warnings[0]).toContain('FR-M35-06');
    expect(warnings[0]).toContain('no pause applied');
  });

  it('an unbound notification (no sessionId) applies no pause and says so', () => {
    const { tracker, warnings, deps } = fixture();
    const handled = handleSpendCeilingNotification(
      'spend/ceiling',
      { sequence: 80, actorId: 'agent-x', action: 'pauseAtCheckpoint', spentUsd: 3 },
      deps,
    );
    expect(handled).toBe(true);
    expect(tracker.ids()).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('no pause applied');
  });

  it('does not claim other notifications or malformed params', () => {
    const { registry, tracker, warnings, deps } = fixture();
    expect(handleSpendCeilingNotification('gate/halt', CEILING, deps)).toBe(false);
    expect(handleSpendCeilingNotification('spend/ceiling', { nope: true }, deps)).toBe(false);
    expect(
      handleSpendCeilingNotification(
        'spend/ceiling',
        { ...CEILING, action: 'warned' },
        deps,
      ),
    ).toBe(false);
    expect(warnings).toHaveLength(0);
    expect(tracker.ids()).toEqual([]);
    expect(registry.ids()).toEqual([]);
  });

  it('asSpendCeilingNotification validates the wire shape', () => {
    expect(asSpendCeilingNotification('spend/ceiling', CEILING)).toEqual(CEILING);
    expect(
      asSpendCeilingNotification('spend/ceiling', { sequence: 'x', action: 'pauseAtCheckpoint' }),
    ).toBeUndefined();
    expect(
      asSpendCeilingNotification('spend/ceiling', { sequence: 1, action: 'other' }),
    ).toBeUndefined();
    expect(asSpendCeilingNotification('gate/halt', CEILING)).toBeUndefined();
  });
});

describe('SpendCeilingPauseTracker', () => {
  it('pause/resume/isPaused lifecycle', () => {
    const tracker = new SpendCeilingPauseTracker();
    expect(tracker.pause(CEILING)).toBe(true);
    expect(tracker.pause(CEILING)).toBe(false);
    expect(tracker.isPaused(CEILING.sessionId!)).toBe(true);
    expect(tracker.resume(CEILING.sessionId!)).toBe(true);
    expect(tracker.isPaused(CEILING.sessionId!)).toBe(false);
    expect(tracker.resume(CEILING.sessionId!)).toBe(false);
  });

  it('a pause with no sessionId is not tracked', () => {
    const tracker = new SpendCeilingPauseTracker();
    expect(
      tracker.pause({ sequence: 1, action: 'pauseAtCheckpoint', sessionId: null }),
    ).toBe(false);
    expect(tracker.ids()).toEqual([]);
  });

  it('assertNotPausePending throws the structured error with resume data', () => {
    const tracker = new SpendCeilingPauseTracker();
    tracker.pause(CEILING);
    let caught: unknown;
    try {
      assertNotPausePending(tracker, CEILING.sessionId!);
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(SpendCeilingPausePendingError);
    const error = caught as SpendCeilingPausePendingError;
    expect(error.data.code).toBe(PAUSE_PENDING_CODE);
    expect(error.data.sessionId).toBe(CEILING.sessionId);
    expect(error.data.sequence).toBe(77);
    expect(error.message).toContain('pause-pending');
    expect(error.message).toContain('spend/ceilingCheck');
    expect(() => assertNotPausePending(tracker, 'someone-else')).not.toThrow();
  });
});

describe('resumeAfterCeilingCleared (FR-M39-02 resume path)', () => {
  it('a clean spend/ceilingCheck re-query releases the pause', async () => {
    const tracker = new SpendCeilingPauseTracker();
    tracker.pause(CEILING);
    const calls: { method: string; params: unknown }[] = [];
    const sidecar = {
      async request(method: string, params: unknown) {
        calls.push({ method, params });
        return { action: 'none' };
      },
    };

    const outcome = await resumeAfterCeilingCleared(CEILING.sessionId!, tracker, sidecar);

    expect(outcome).toEqual({ resumed: true, action: 'none' });
    expect(tracker.isPaused(CEILING.sessionId!)).toBe(false);
    expect(calls).toEqual([
      { method: 'spend/ceilingCheck', params: { sessionId: CEILING.sessionId } },
    ]);
  });

  it('a still-breached re-query keeps the pause', async () => {
    const tracker = new SpendCeilingPauseTracker();
    tracker.pause(CEILING);
    const sidecar = { request: async () => ({ action: 'paused_at_checkpoint' }) };

    const outcome = await resumeAfterCeilingCleared(CEILING.sessionId!, tracker, sidecar);

    expect(outcome).toEqual({ resumed: false, action: 'paused_at_checkpoint' });
    expect(tracker.isPaused(CEILING.sessionId!)).toBe(true);
  });
});

describe('checkpoint enforcement (pause at the next turn boundary)', () => {
  interface RecordedCall {
    method: string;
    params: Record<string, unknown>;
  }

  function fakeSidecar(calls: RecordedCall[], steerAction: 'none' | 'paused_at_checkpoint') {
    let sequence = 0;
    return {
      calls,
      async request(method: string, params: unknown): Promise<unknown> {
        calls.push({ method, params: params as Record<string, unknown> });
        if (method === 'steer.send') return { accepted: true, sequence: ++sequence };
        if (method === 'spend/ceilingCheck') return { action: steerAction };
        return { recorded: true };
      },
    };
  }

  function fakeClient(wireLog: string[]): AcpClient {
    return {
      prompt: async (sessionId: string, text: string) => {
        wireLog.push(`${sessionId}:${text}`);
        return 'end_turn';
      },
      stop: () => undefined,
    } as unknown as AcpClient;
  }

  async function beginHosted(
    controller: HostedSteerController,
    sessionId: string,
    client: AcpClient,
  ): Promise<void> {
    await controller.beginSession({
      client,
      sessionId,
      adapterId: 'agent-9',
      cwd: '/tmp/ws',
    });
  }

  it('steer() refuses a pause-pending session before anything is recorded or sent', async () => {
    const registry = new HostedSessionRegistry();
    const tracker = new SpendCeilingPauseTracker();
    const calls: RecordedCall[] = [];
    const wireLog: string[] = [];
    const sidecar = fakeSidecar(calls, 'paused_at_checkpoint');
    const controller = new HostedSteerController({
      registry,
      sidecar,
      enabledTiers: () => GOVERNOR,
      spendPauses: tracker,
    });
    const sessionId = CEILING.sessionId!;
    await beginHosted(controller, sessionId, fakeClient(wireLog));
    // The notification handler is the entry point: hosted → pause-pending.
    expect(
      handleSpendCeilingNotification('spend/ceiling', CEILING, {
        registry,
        tracker,
        warn: () => undefined,
      }),
    ).toBe(true);

    let caught: unknown;
    try {
      await controller.steer(sessionId, 'keep going');
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(SpendCeilingPausePendingError);
    // Nothing ledger-recorded, nothing on the wire.
    expect(calls.map((c) => c.method)).not.toContain('steer.send');
    expect(wireLog).toEqual([]);
  });

  it('steer() resumes once the ceiling re-query comes back clean', async () => {
    const registry = new HostedSessionRegistry();
    const tracker = new SpendCeilingPauseTracker();
    const calls: RecordedCall[] = [];
    const wireLog: string[] = [];
    const sidecar = fakeSidecar(calls, 'none');
    const controller = new HostedSteerController({
      registry,
      sidecar,
      enabledTiers: () => GOVERNOR,
      spendPauses: tracker,
    });
    const sessionId = CEILING.sessionId!;
    await beginHosted(controller, sessionId, fakeClient(wireLog));
    handleSpendCeilingNotification('spend/ceiling', CEILING, {
      registry,
      tracker,
      warn: () => undefined,
    });

    const outcome = await resumeAfterCeilingCleared(sessionId, tracker, sidecar);
    expect(outcome.resumed).toBe(true);

    const steer = await controller.steer(sessionId, 'keep going');
    expect(steer.stopReason).toBe('end_turn');
    expect(wireLog).toEqual([`${sessionId}:keep going`]);
  });

  it('AcpClient.prompt consults the checkpoint gate before sending a turn', { timeout: TIMEOUT }, async () => {
    const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-spend-'));
    try {
      const options: AcpClientOptions = {
        command: process.execPath,
        args: [FIXTURE],
        workspaceDir: workspace,
        // The fixture's default turn asks one permission before finishing.
        approvePermission: async (request) => ({
          outcome: 'selected',
          optionId: request.options.find((option) => option.kind.startsWith('allow'))!.optionId,
        }),
      };
      const client = new AcpClient({
        ...options,
        checkpointGate: (sessionId: string) => {
          if (sessionId === 'paused-session') {
            throw new SpendCeilingPausePendingError({
              sessionId,
              sequence: 77,
              spentUsd: 12.5,
              pausedAt: new Date(0).toISOString(),
            });
          }
        },
      });
      await client.start();
      try {
        const freeSession = await client.newSession(workspace);
        // The gate only refuses the paused session: a free one turns fine.
        await expect(client.prompt(freeSession, 'hello')).resolves.toBe('end_turn');
        await expect(client.prompt('paused-session', 'hello')).rejects.toBeInstanceOf(
          SpendCeilingPausePendingError,
        );
      } finally {
        // Windows: the temp workspace can only be removed once the agent
        // process is actually gone — taskkill is asynchronous.
        const exited = new Promise<void>((resolve) => {
          client.once('exit', () => resolve());
          setTimeout(resolve, 5_000).unref?.();
        });
        client.stop();
        await exited;
      }
    } finally {
      await fs.rm(workspace, { recursive: true, force: true });
    }
  });
});
