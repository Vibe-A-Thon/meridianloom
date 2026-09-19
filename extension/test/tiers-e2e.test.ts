import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ErrorCode, type ErrorObject, type TierName } from '../../shared/ts/bus-types';
import { StdioSidecarClient } from '../src/stdio-client';

const coreDir = path.resolve(__dirname, '..', '..', 'core');

function findPython(): string | undefined {
  for (const candidate of ['python', 'python3']) {
    try {
      const executable = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (executable) {
        return candidate;
      }
    } catch {
      // try the next candidate
    }
  }
  return undefined;
}

const python = findPython();
const run = python ? describe : describe.skip;

interface RpcFailure {
  message: string;
  code: number;
  data: {
    method: string;
    capability: string;
    tier: string;
    enabledTiers: string[];
    remediation: string;
  };
}

async function expectTierDisabled(
  client: StdioSidecarClient,
  method: 'loop.start' | 'gate.evaluate',
  tier: TierName,
): Promise<void> {
  const failure = (await client
    .request(method, {}, new AbortController().signal)
    .catch((error: unknown) => error)) as RpcFailure;
  expect(failure.code).toBe(ErrorCode.TIER_DISABLED);
  expect(failure.data.method).toBe(method);
  expect(failure.data.tier).toBe(tier);
  expect(failure.data.enabledTiers).toContain('flight-recorder');
  expect(failure.data.remediation).toContain('meridian.tiers');
  expect(failure.data.remediation).toContain('no reinstall');
}

run('tier enforcement against the real sidecar (FR-M36-05, G5)', () => {
  it(
    'default tiers: flight-recorder RPCs work, governor/orchestra are refused with a structured error',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({ command: python!, cwd: coreDir });
      await client.start();
      try {
        // Flight Recorder tier fully functional.
        const ping = await client.call('ping', {}, new AbortController().signal);
        expect(ping.pong).toBe(true);
        const doctor = await client.call('doctor/run', {}, new AbortController().signal);
        expect(doctor.checks.length).toBeGreaterThan(0);

        // Governor and Orchestra refused, structured and actionable.
        await expectTierDisabled(client, 'gate.evaluate', 'governor');
        await expectTierDisabled(client, 'loop.start', 'orchestra');

        // A disabled tier leaves no scar: flight recorder still works after.
        const health = await client.call('health', {}, new AbortController().signal);
        expect(health.status).toBe('ok');
      } finally {
        client.kill();
      }
    },
  );

  it(
    'enabling a tier needs no reinstall: a handshake param or tiers/set notification is the whole cost',
    { timeout: 30_000 },
    async () => {
      // Handshake-time enablement (what a fresh spawn after a config change does).
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        tiers: ['flight-recorder', 'orchestra'],
      });
      await client.start();
      try {
        // Orchestra method now passes the gate and is real (TASK-011): with
        // no workspaceDir the structured refusal is LEDGER_UNAVAILABLE —
        // refused by configuration, not by tier, same shape as gate.evaluate
        // below.
        await expect(
          client.call('loop.start', { loopId: 'x', storyId: 's', kind: 'L1-micro' }, new AbortController().signal),
        ).rejects.toMatchObject({ code: ErrorCode.LEDGER_UNAVAILABLE });
        // Governor remains refused.
        await expectTierDisabled(client, 'gate.evaluate', 'governor');

        // Live flip: tiers/set turns governor on without reconnecting.
        client.notify('tiers/set', { tiers: ['flight-recorder', 'governor'] });
        // gate.evaluate is real now (FR-M12-09): without a workspaceDir the
        // decision cannot be recorded, so the structured refusal is
        // LEDGER_UNAVAILABLE — refused by configuration, not by tier.
        await expect(
          client.call('gate.evaluate', { storyId: 's', gate: 'review', packet: {} }, new AbortController().signal),
        ).rejects.toMatchObject({ code: ErrorCode.LEDGER_UNAVAILABLE });
        // ...and turns orchestra off again — no scar.
        await expectTierDisabled(client, 'loop.start', 'orchestra');
      } finally {
        client.kill();
      }
    },
  );

  it(
    'the base tier cannot be disabled, even by an explicit tiers list',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        tiers: ['governor'],
      });
      await client.start();
      try {
        const ping = await client.call('ping', {}, new AbortController().signal);
        expect(ping.pong).toBe(true);
      } finally {
        client.kill();
      }
    },
  );
});

if (!python) {
  // eslint-disable-next-line no-console
  console.warn('python not found on PATH; skipping tier e2e tests');
}
