/**
 * Steer & clarify end-to-end against the REAL sidecar (FR-M25-01/02/03/04/06,
 * FR-M10-08; F1 Workstream D tasks 17-18).
 *
 * The extension's framed sidecar client talks to a real spawned
 * `python -m meridian_core`: a hosted session begin, a steering act, a
 * question/answer pair, an escalation, a partial acceptance and a dry-run
 * plan all land in the real ledger and read back through the real RPCs —
 * including the structured NOT_HOSTED refusal for a session Meridian only
 * observes (task 18).
 */
import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ErrorCode } from '../../shared/ts/bus-types';
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

let workspace: string;

beforeEach(async () => {
  workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-steer-e2e-'));
  // FR-M12-07 is a production invariant: anonymous approval is forbidden.
  // This fixture exercises approval/steering, so it must provide the same
  // deterministic local git identity a real workspace owner would configure.
  execFileSync('git', ['init'], {
    cwd: workspace,
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  execFileSync('git', ['config', 'user.name', 'Meridian CI Human'], {
    cwd: workspace,
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  execFileSync('git', ['config', 'user.email', 'meridian-ci@example.invalid'], {
    cwd: workspace,
    stdio: ['ignore', 'ignore', 'pipe'],
  });
});

afterEach(async () => {
  // Windows: the sidecar's file handles release asynchronously after the
  // exit event — retry the cleanup instead of flaking on EBUSY.
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      await fs.rm(workspace, { recursive: true, force: true });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  await fs.rm(workspace, { recursive: true, force: true }).catch(() => undefined);
});

async function startSidecar(): Promise<StdioSidecarClient> {
  const client = new StdioSidecarClient({
    command: python!,
    cwd: coreDir,
    tiers: ['flight-recorder', 'governor'],
    workspaceDir: workspace,
  });
  await client.start();
  return client;
}

run('steer & clarify against the real sidecar (FR-M25)', () => {
  it(
    'hosted begin → steer → question → answer → accept → plan, all durable and queryable',
    { timeout: 60_000 },
    async () => {
      const sidecar = await startSidecar();
      try {
        const signal = new AbortController().signal;
        const begin = await sidecar.call('acp/sessionBegin', {
          agentId: 'gemini',
          agentVersion: '0.30.0',
          sessionId: 'e2e-sess',
          cwd: workspace,
          mode: 'dry-run',
        }, signal);
        expect(begin).toEqual({ recorded: true });

        // FR-M25-01: the steering act is durable before the ack.
        const steered = await sidecar.call('steer.send', {
          sessionId: 'e2e-sess',
          message: 'prefer the sqlite backend',
        }, signal);
        expect(steered.accepted).toBe(true);
        const steerEntries = await sidecar.call('ledger.query', {
          storyId: 'acp:e2e-sess',
          actionType: 'steer',
        }, signal);
        expect(steerEntries.entries).toHaveLength(1);
        expect(steerEntries.entries[0].externalSessionId).toBe('e2e-sess');
        // FR-M20-01: the resolved git identity, never a free-text param.
        expect(steerEntries.entries[0].humanActor).toContain('@');

        // FR-M25-02: question before answer, answer resumes.
        const asked = await sidecar.call('steer/question', {
          sessionId: 'e2e-sess',
          question: 'Which backend?',
          options: [
            { optionId: 'a', name: 'SQLite', recommended: true },
            { optionId: 'b', name: 'Memory' },
          ],
        }, signal);
        const answered = await sidecar.call('steer/answer', {
          sessionId: 'e2e-sess',
          questionSequence: asked.sequence,
          selectedOptionId: 'a',
        }, signal);
        expect(answered.resumed).toBe(true);

        // FR-M25-03: the escalation is a durable event.
        const raised = await sidecar.call('steer/escalate', {
          sessionId: 'e2e-sess',
          actionClass: 'execute',
          confidence: 0.3,
          threshold: 0.9,
        }, signal);
        expect(raised.escalated).toBe(true);

        // FR-M25-04: partial acceptance recorded and queryable.
        await sidecar.call('steer/accept', {
          sessionId: 'e2e-sess',
          accepted: [{ file: 'src/a.ts', hunks: [{ index: 0 }] }],
          rejected: [{ file: 'src/b.ts', hunks: [{ index: 1 }] }],
        }, signal);
        const status = await sidecar.call('steer/acceptanceStatus', {
          sessionId: 'e2e-sess',
        }, signal);
        expect(status.hosted).toBe(true);
        const byFile = Object.fromEntries(status.files.map((f: { file: string }) => [f.file, f]));
        expect(byFile['src/a.ts'].hunks).toEqual([{ index: 0, state: 'accepted' }]);
        expect(byFile['src/b.ts'].hunks).toEqual([{ index: 1, state: 'rejected' }]);

        // FR-M25-06: the dry-run plan is durable.
        const plan = await sidecar.call('steer/plan', {
          sessionId: 'e2e-sess',
          entries: [{ content: 'Plan only', status: 'pending' }],
          costEstimate: { currency: 'USD' },
        }, signal);
        expect(plan.accepted).toBe(true);

        // Task 18: the capability payload carries hosted + the dry-run mode.
        const session = await sidecar.call('steer/status', {
          sessionId: 'e2e-sess',
        }, signal);
        expect(session).toMatchObject({ hosted: true, mode: 'dry-run' });
      } finally {
        await new Promise<void>((resolve) => {
          sidecar.once('exit', () => resolve());
          sidecar.kill();
          setTimeout(resolve, 5_000).unref?.();
        });
      }
    },
  );

  it(
    'an observed session refuses steer with the structured NOT_HOSTED error and records nothing',
    { timeout: 60_000 },
    async () => {
      const sidecar = await startSidecar();
      try {
        const signal = new AbortController().signal;
        const failure = (await sidecar
          .request('steer.send', { sessionId: 'observed-1', message: 'stop' }, signal)
          .catch((error: unknown) => error)) as {
          code: number;
          message: string;
          data: { hosted: boolean; sessionId: string; remediation: string };
        };
        expect(failure.code).toBe(ErrorCode.NOT_HOSTED);
        expect(failure.message).toContain('observed, not hosted');
        expect(failure.data).toMatchObject({ hosted: false, sessionId: 'observed-1' });
        expect(failure.data.remediation).toContain('hosted');

        // The status payload says so plainly — no dead control possible.
        const status = await sidecar.call('steer/status', { sessionId: 'observed-1' }, signal);
        expect(status).toEqual({ sessionId: 'observed-1', hosted: false });
        const acceptance = await sidecar.call(
          'steer/acceptanceStatus',
          { sessionId: 'observed-1' },
          signal,
        );
        expect(acceptance).toEqual({ sessionId: 'observed-1', hosted: false, files: [] });
        const entries = await sidecar.call(
          'ledger.query',
          { storyId: 'acp:observed-1' },
          signal,
        );
        expect(entries.entries).toEqual([]);
      } finally {
        await new Promise<void>((resolve) => {
          sidecar.once('exit', () => resolve());
          sidecar.kill();
          setTimeout(resolve, 5_000).unref?.();
        });
      }
    },
  );
});
