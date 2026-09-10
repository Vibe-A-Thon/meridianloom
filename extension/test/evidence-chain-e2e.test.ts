import { execFileSync } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { StdioSidecarClient } from '../src/stdio-client';
import { WorkbenchService } from '../src/workbench/service';
import type {
  WorkbenchAgentInput,
  WorkbenchSnapshot,
} from '../../shared/ts/workbench';

/**
 * The product's central promise, end to end, with nothing faked.
 *
 * Meridian's claim is not "it runs agents" — plenty of things run agents. The
 * claim is: **run an agent, and get evidence you can take with you.** Until
 * this file existed, the two halves of that sentence were tested separately.
 * `workbench.test.ts` spawned a real ACP subprocess and asserted persistence;
 * `core/tests/test_open_verifier.py` took a bundle and verified it. Nothing
 * crossed the seam between them, so both halves could pass while the product
 * did not work — an agent could run, the ledger could stay empty, and every
 * suite would still be green.
 *
 * This test walks the whole chain with real components at every step:
 *
 *   1. a real Python sidecar over real stdio, with a real workspace;
 *   2. a real ACP agent subprocess, launched by the real WorkbenchService,
 *      dispatched through the real phase-based convening;
 *   3. the real ledger, queried for what the run actually left behind;
 *   4. a real signed bundle from `ledger.exportBundle`;
 *   5. the **shipped** standalone verifier, run as a subprocess against that
 *      bundle — the same file a user gets inside the VSIX, standard library
 *      only, which is what makes "verifies without Meridian installed" a
 *      statement rather than a slogan.
 *
 * If this passes, the sentence on the front of the README is true. If it
 * fails, nothing else in the suite matters much.
 */

const root = path.resolve(__dirname, '..', '..');
const coreDir = path.join(root, 'core');
const VERIFY_PY = path.join(root, 'verifier', 'verify.py');

function findPython(): string | undefined {
  for (const candidate of ['python', 'python3']) {
    try {
      const executable = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (executable) return candidate;
    } catch {
      // try the next candidate
    }
  }
  return undefined;
}

const python = findPython();
const run = python ? describe : describe.skip;

const agent = (over: Partial<WorkbenchAgentInput> = {}): WorkbenchAgentInput => ({
  id: 'atlas',
  name: 'Atlas',
  role: 'Architect',
  description: 'Walks the chain.',
  vendor: 'custom',
  version: '1.0.0',
  command: process.execPath,
  args: [path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs')],
  instructions: '',
  permissions: ['read', 'edit', 'execute'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
  ...over,
});

const services: WorkbenchService[] = [];
const clients: StdioSidecarClient[] = [];
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
  for (const client of clients.splice(0)) {
    // kill() rather than a graceful shutdown: the test may already have
    // torn the sidecar down, and a hung teardown would hide the result.
    client.kill();
  }
});

async function until(check: () => Promise<boolean>, budgetMs = 30_000) {
  const deadline = Date.now() + budgetMs;
  let last: unknown;
  while (Date.now() < deadline) {
    try {
      if (await check()) return;
    } catch (error) {
      last = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`condition not reached in time${last ? `: ${String(last)}` : ''}`);
}

run('the evidence chain, end to end', () => {
  it(
    'an agent run becomes a bundle the shipped verifier accepts',
    { timeout: 120_000 },
    async () => {
      const workspace = await mkdtemp(path.join(os.tmpdir(), 'meridian-chain-'));
      await writeFile(path.join(workspace, 'input.txt'), 'real workspace input');

      // --- 1. a real sidecar over real stdio -------------------------------
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        workspaceDir: workspace,
      });
      clients.push(client);
      await client.start();
      const signal = () => new AbortController().signal;

      // --- 2. a real agent, launched by the real service -------------------
      const service = new WorkbenchService({
        workspaceDir: () => workspace,
        trusted: () => true,
        enabledTiers: () => ['flight-recorder', 'governor'],
        sidecar: () => ({
          request: (method, params) => client.request(method, params, signal()),
        }),
        // The fixture agent asks for permission; granting it keeps the run
        // moving and exercises the approval path the ledger records.
        humanApprover: async (request) => ({
          outcome: 'selected',
          optionId: request.options.find((option) => option.kind === 'allow_once')!
            .optionId,
        }),
      });
      services.push(service);
      const snapshot = async () =>
        (await service.request({ action: 'snapshot' })) as WorkbenchSnapshot;

      await service.request({ action: 'agent/save', params: { agent: agent() } });
      await service.request({
        action: 'agent/mode',
        params: { id: 'atlas', mode: 'active' },
      });
      // Tag a phase so the dispatch goes through the real convening path
      // rather than the untagged fallback.
      await service.request({
        action: 'agent/assign',
        params: { id: 'atlas', phases: ['build'] },
      });
      await service.request({
        action: 'deliverable/save',
        params: {
          title: 'Walk the evidence chain',
          brief: 'Copy input.txt to output.txt and say what you did.',
        },
      });
      await service.request({
        action: 'deliverable/dispatch',
        params: { id: (await snapshot()).deliverables[0].id },
      });

      await until(async () => {
        const state = await snapshot();
        return state.runs.length > 0 && state.runs[0].state !== 'queued';
      });
      await until(async () => {
        const run = (await snapshot()).runs[0];
        return run.state === 'completed' || run.state === 'failed';
      });

      const finished = (await snapshot()).runs[0];
      expect(
        finished.state,
        `the run failed: ${finished.error ?? '(no error recorded)'}`,
      ).toBe('completed');
      // The convening recorded WHY this agent ran, not merely that it did.
      expect(finished.phase).toBe('build');
      // And the briefing it received is on the run, verbatim.
      expect(finished.prompt).toContain('Implementation');
      expect(finished.prompt).toContain('Copy input.txt to output.txt');

      // --- 3. the real ledger, asked what the run left behind ---------------
      const query = await client.request<{ entries: { sequence: number }[] }>(
        'ledger.query',
        { limit: 1000 },
        signal(),
      );
      expect(
        query.entries.length,
        'the run completed but the ledger is empty — the recording seam is broken',
      ).toBeGreaterThan(0);

      // --- 4. a real signed bundle ------------------------------------------
      const bundle = await client.request<Record<string, unknown>>(
        'ledger.exportBundle',
        {},
        signal(),
      );
      expect(bundle).toHaveProperty('entries');
      expect(bundle).toHaveProperty('signature');

      const bundlePath = path.join(workspace, 'bundle.json');
      await writeFile(bundlePath, JSON.stringify(bundle), 'utf8');

      // --- 5. the SHIPPED verifier, as a user would run it -------------------
      // Standard library only, no meridian_core on the path, no cwd inside
      // the repository: exactly what an auditor has.
      const verified = execFileSync(python!, [VERIFY_PY, bundlePath], {
        encoding: 'utf8',
        cwd: os.tmpdir(),
        env: { ...process.env, PYTHONPATH: '' },
      });
      expect(verified.toLowerCase()).toContain('ok');
    },
  );

  it(
    'a tampered bundle is rejected by the shipped verifier',
    { timeout: 60_000 },
    async () => {
      // The other half of the claim. A verifier that accepts everything
      // verifies nothing, and this is the assertion an auditor actually
      // cares about.
      const workspace = await mkdtemp(path.join(os.tmpdir(), 'meridian-tamper-'));
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        workspaceDir: workspace,
      });
      clients.push(client);
      await client.start();
      const signal = () => new AbortController().signal;

      await client.request(
        'ledger.append',
        {
          storyId: 'EDB-12345',
          phase: 'build',
          loopId: 'L2-task',
          loopIteration: 1,
          actorId: 'developer-agent',
          actorVersion: '0.0.1',
          actorKind: 'role',
          policyVersion: 'policy-v1',
          actionType: 'diff',
        },
        signal(),
      );

      const bundle = (await client.request<Record<string, unknown>>(
        'ledger.exportBundle',
        {},
        signal(),
      )) as { entries: { storyId?: string }[] };

      // Change one field of one entry and nothing else.
      bundle.entries[0].storyId = 'chain-tampered';
      const tamperedPath = path.join(workspace, 'tampered.json');
      await writeFile(tamperedPath, JSON.stringify(bundle), 'utf8');

      let rejected = false;
      try {
        execFileSync(python!, [VERIFY_PY, tamperedPath], {
          encoding: 'utf8',
          cwd: os.tmpdir(),
          stdio: ['pipe', 'pipe', 'pipe'],
        });
      } catch {
        rejected = true;
      }
      expect(
        rejected,
        'the verifier accepted a bundle with an altered entry',
      ).toBe(true);
    },
  );
});
