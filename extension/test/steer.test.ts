/**
 * Steer & clarify over hosted ACP sessions (FR-M25-01/02/03/04/06;
 * F1 Workstream D tasks 17-18).
 *
 * The fake agent in fixtures/ is a test double of the ACP WIRE — these
 * tests run a real hosted session against a real subprocess and assert on
 * real effects: steering lands mid-turn on the wire, a question blocks the
 * turn until the human answers, stated low confidence raises an
 * escalation, partial acceptance and dry-run plans are recorded, and the
 * hosted-session registry's halt actually kills the session process.
 * Task 18: an observe-only session refuses steer with the structured,
 * honest NOT_HOSTED error, and every status payload carries hosted.
 */
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AcpClient, type AcpClientOptions, type PermissionApprover } from '../src/acp/client';
import type { RequestPermissionRequest, SessionNotification } from '../src/acp/protocol';
import { HostedSessionRegistry } from '../src/governance/session-registry';
import {
  HostedSteerController,
  NotHostedSessionError,
  NOT_HOSTED_CODE,
  thresholdFor,
  type ClarifyingQuestionEvent,
  type EscalationEvent,
} from '../src/governance/steer';
import { createPolicyGate } from '../src/adapters/permission-gate';
import { parseAcpPermissionPolicy } from '../src/adapters/policy';
import type { AdapterManifest } from '../src/adapters/manifest';
import { normalizeEnabledTiers } from '../../shared/ts/tiers';

const FIXTURE = path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs');
const TIMEOUT = 20_000;
const GOVERNOR = normalizeEnabledTiers(['governor']);

let workspace: string;

beforeEach(async () => {
  workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-steer-'));
  await fs.writeFile(path.join(workspace, 'input.txt'), 'hello workspace', 'utf8');
});

afterEach(async () => {
  await fs.rm(workspace, { recursive: true, force: true });
});

function agentOptions(...scenarioFlags: string[]): AcpClientOptions {
  return {
    command: process.execPath,
    args: [FIXTURE, ...scenarioFlags],
    workspaceDir: workspace,
  };
}

interface RecordedCall {
  method: string;
  params: Record<string, unknown>;
  /** For steer.send: how many wire prompts had gone out when it was recorded. */
  wireSeen?: number;
}

/** The sidecar double: an ordered call log plus canned steer acks. */
function fakeSidecar(calls: RecordedCall[], wireCalls?: string[]) {
  let sequence = 0;
  return {
    async request(method: string, params: unknown): Promise<unknown> {
      calls.push({
        method,
        params: params as Record<string, unknown>,
        ...(method === 'steer.send' ? { wireSeen: wireCalls?.length ?? -1 } : {}),
      });
      if (method === 'steer/status') {
        return { sessionId: (params as { sessionId: string }).sessionId, hosted: false };
      }
      if (method === 'steer.send' || method.startsWith('steer/')) {
        return { accepted: true, sequence: ++sequence, escalated: true, resumed: true };
      }
      return { recorded: true };
    },
  };
}

/** An AcpClient that logs every wire prompt it sends into a shared array. */
class WireSpyClient extends AcpClient {
  constructor(
    options: AcpClientOptions,
    private readonly wireLog: string[],
  ) {
    super(options);
  }
  override async prompt(
    sessionId: string,
    text: string,
    options?: { signal?: AbortSignal },
  ): Promise<string | undefined> {
    this.wireLog.push(text);
    return super.prompt(sessionId, text, options);
  }
}

interface Harness {
  registry: HostedSessionRegistry;
  sidecar: ReturnType<typeof fakeSidecar>;
  controller: HostedSteerController;
  questions: ClarifyingQuestionEvent[];
  escalations: EscalationEvent[];
}

function harness(calls: RecordedCall[], wirePrompts?: string[]): Harness {
  const registry = new HostedSessionRegistry();
  const questions: ClarifyingQuestionEvent[] = [];
  const escalations: EscalationEvent[] = [];
  const sidecar = fakeSidecar(calls, wirePrompts);
  const controller = new HostedSteerController({
    registry,
    sidecar,
    enabledTiers: () => GOVERNOR,
    onQuestion: (event) => questions.push(event),
    onEscalation: (event) => escalations.push(event),
  });
  return { registry, sidecar, controller, questions, escalations };
}

async function startHosted(
  h: Harness,
  client: AcpClient,
  sessionId: string,
  mode?: 'normal' | 'dry-run',
): Promise<void> {
  await client.start();
  await h.controller.beginSession({
    client,
    sessionId,
    adapterId: 'gemini',
    cwd: workspace,
    mode,
  });
}

async function stopAndWait(client: AcpClient): Promise<void> {
  if (client.pid === undefined) {
    client.stop();
    return;
  }
  const exited = new Promise<void>((resolve) => {
    client.once('exit', () => resolve());
    setTimeout(resolve, 5_000).unref?.();
  });
  client.stop();
  await exited;
}

/** Resolve once the agent's update stream carries a chunk matching `needle`. */
function waitForChunk(client: AcpClient, needle: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`no chunk containing '${needle}'`)), 10_000);
    const onUpdate = (notification: SessionNotification): void => {
      const update = notification.update;
      if (update.sessionUpdate === 'agent_message_chunk' && update.content.type === 'text') {
        if (update.content.text.includes(needle)) {
          clearTimeout(timer);
          client.off('update', onUpdate);
          resolve();
        }
      }
    };
    client.on('update', onUpdate);
  });
}

describe('hosted-session registry wiring (FR-M12-06 seam made real)', () => {
  it('begin registers with the client handle; registry halt kills the real process', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient(agentOptions());
    await startHosted(h, client, 'sess-halt');
    expect(h.registry.ids()).toContain('sess-halt');
    expect(h.controller.hosted('sess-halt')).toBe(true);

    const exit = new Promise<{ code: number | null }>((resolve) => {
      client.once('exit', (code: number | null) => resolve({ code }));
    });
    // The task-11 seam: gate/halt routes here, and the kill is real.
    expect(h.registry.halt('sess-halt', 'Governance halt')).toBe(true);
    const { code } = await exit;
    expect(code).not.toBeNull();
    expect(h.registry.ids()).not.toContain('sess-halt');
    // Post-halt capability answers are honest in the same beat (task 18).
    expect(h.controller.hosted('sess-halt')).toBe(false);
    await expect(h.controller.steer('sess-halt', 'x')).rejects.toBeInstanceOf(
      NotHostedSessionError,
    );
    const status = await h.controller.status('sess-halt');
    expect(status).toMatchObject({ hosted: false, steerable: false });
    await stopAndWait(client);
  });

  it('endSession unregisters and records sessionEnd', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient(agentOptions());
    await startHosted(h, client, 'sess-end');
    await h.controller.endSession('sess-end', { stopReason: 'end_turn' });
    expect(h.registry.ids()).not.toContain('sess-end');
    expect(h.controller.hosted('sess-end')).toBe(false);
    const end = calls.find((c) => c.method === 'acp/sessionEnd');
    expect(end?.params).toMatchObject({ sessionId: 'sess-end', stopReason: 'end_turn' });
    await stopAndWait(client);
  });

  it('beginSession refuses when the governor tier is disabled (G5)', async () => {
    const calls: RecordedCall[] = [];
    const registry = new HostedSessionRegistry();
    const controller = new HostedSteerController({
      registry,
      sidecar: fakeSidecar(calls),
      enabledTiers: () => normalizeEnabledTiers(undefined),
    });
    const client = new AcpClient(agentOptions());
    await expect(
      controller.beginSession({ client, sessionId: 's', adapterId: 'gemini', cwd: workspace }),
    ).rejects.toThrow(/governor tier/);
    expect(registry.ids()).toEqual([]);
    expect(calls).toEqual([]);
  });
});

describe('steer a running session (FR-M25-01)', () => {
  it('records the steering act BEFORE injecting it into the live wire', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const wirePrompts: string[] = [];
    const h = harness(calls, wirePrompts);
    // The --steerable fixture writes to the workspace as part of its turn.
    // Host fs effects are gated now (d14b620), and a client with no approver
    // is fail-closed by design — which is the hole that change closed. This
    // test is about steering order, not permissions, so it grants.
    const client = new WireSpyClient(
      {
        ...agentOptions('--steerable'),
        approvePermission: async (request) => ({
          outcome: 'selected',
          optionId:
            request.options.find((option) => option.kind.startsWith('allow'))
              ?.optionId ?? request.options[0].optionId,
        }),
      },
      wirePrompts,
    );
    await startHosted(h, client, 'sess-steer');

    const idling = waitForChunk(client, 'Idling');
    const turn = client.prompt('fake-session-1', 'Do the work.');
    await idling;

    const ack = await h.controller.steer('sess-steer', 'prefer the sqlite backend');
    expect(ack.accepted).toBe(true);
    expect(ack.stopReason).toBe('end_turn');

    // FR-M10-08: the ledger write happened before the wire injection.
    const send = calls.find((c) => c.method === 'steer.send');
    expect(send?.params).toMatchObject({
      sessionId: 'sess-steer',
      message: 'prefer the sqlite backend',
    });
    expect(send?.wireSeen).toBe(1); // only the original turn prompt so far
    expect(wirePrompts[1]).toBe('prefer the sqlite backend');

    // The original turn consumed the steering and completed normally.
    expect(await turn).toBe('end_turn');
    const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
    expect(output).toContain('steered=prefer the sqlite backend');
    await h.controller.endSession('sess-steer');
    await stopAndWait(client);
  });
});

describe('clarifying questions (FR-M25-02)', () => {
  it('question is recorded before the human sees it; answer resumes the loop', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient({
      ...agentOptions('--ask-question'),
      approvePermission: h.controller.clarifyingApprover('sess-q', (async () => {
        return { outcome: 'selected', optionId: 'opt-sqlite' };
      }) as PermissionApprover),
    });
    await startHosted(h, client, 'sess-q');

    const stopReason = await client.prompt('fake-session-1', 'Add a cache.');
    expect(stopReason).toBe('end_turn');

    const questionIndex = calls.findIndex((c) => c.method === 'steer/question');
    const answerIndex = calls.findIndex((c) => c.method === 'steer/answer');
    expect(questionIndex).toBeGreaterThanOrEqual(0);
    expect(answerIndex).toBeGreaterThan(questionIndex);
    expect(calls[questionIndex].params).toMatchObject({
      sessionId: 'sess-q',
      question: 'Which backend should the cache use?',
      toolCallId: 'tc-permission',
    });
    const options = calls[questionIndex].params.options as {
      optionId: string;
      recommended: boolean;
    }[];
    expect(options.find((o) => o.optionId === 'opt-sqlite')?.recommended).toBe(true);
    expect(calls[answerIndex].params).toMatchObject({
      sessionId: 'sess-q',
      selectedOptionId: 'opt-sqlite',
      questionSequence: 1,
    });

    // The host surface saw the blocking question with the recommendation.
    expect(h.questions).toHaveLength(1);
    expect(h.questions[0]).toMatchObject({
      sessionId: 'sess-q',
      question: 'Which backend should the cache use?',
      recommendation: 'opt-sqlite',
    });

    const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
    expect(output).toContain('answer=opt-sqlite');
    await h.controller.endSession('sess-q');
    await stopAndWait(client);
  });

  it('a dismissed question is recorded as a cancelled answer, never dropped', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient({
      ...agentOptions('--ask-question'),
      approvePermission: h.controller.clarifyingApprover('sess-q2', (async () => {
        return { outcome: 'cancelled' };
      }) as PermissionApprover),
    });
    await startHosted(h, client, 'sess-q2');
    const stopReason = await client.prompt('fake-session-1', 'Add a cache.');
    expect(stopReason).toBe('cancelled');
    const answer = calls.find((c) => c.method === 'steer/answer');
    expect(answer?.params).toMatchObject({ sessionId: 'sess-q2', cancelled: true });
    await stopAndWait(client);
  });

  it('plain permission asks (no _meta.question) do not enter the question protocol', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient({
      ...agentOptions(),
      approvePermission: h.controller.clarifyingApprover('sess-plain', (async () => {
        return { outcome: 'selected', optionId: 'allow-once' };
      }) as PermissionApprover),
    });
    await startHosted(h, client, 'sess-plain');
    const stopReason = await client.prompt('fake-session-1', 'Run it.');
    expect(stopReason).toBe('end_turn');
    expect(calls.some((c) => c.method === 'steer/question')).toBe(false);
    expect(h.questions).toHaveLength(0);
    await h.controller.endSession('sess-plain');
    await stopAndWait(client);
  });
});

describe('uncertainty escalation (FR-M25-03)', () => {
  it('stated confidence below the per-class threshold escalates BEFORE the human decides', { timeout: TIMEOUT }, async () => {
    expect(thresholdFor('execute')).toBe(0.9);
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient({
      ...agentOptions('--low-confidence'),
      approvePermission: h.controller.clarifyingApprover('sess-esc', (async () => {
        return { outcome: 'selected', optionId: 'allow-once' };
      }) as PermissionApprover),
    });
    await startHosted(h, client, 'sess-esc');
    const stopReason = await client.prompt('fake-session-1', 'Run the suite.');
    expect(stopReason).toBe('end_turn');

    const escalate = calls.find((c) => c.method === 'steer/escalate');
    expect(escalate?.params).toMatchObject({
      sessionId: 'sess-esc',
      actionClass: 'execute',
      confidence: 0.3,
      threshold: 0.9,
      toolCallId: 'tc-permission',
    });
    expect(h.escalations).toHaveLength(1);
    expect(h.escalations[0]).toMatchObject({ actionClass: 'execute', confidence: 0.3 });
    // The human still decides — the agent asked rather than acting.
    const output = await fs.readFile(path.join(workspace, 'output.txt'), 'utf8');
    expect(output).toContain('permission=');
    await h.controller.endSession('sess-esc');
    await stopAndWait(client);
  });

  it('confident actions raise no escalation', () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const request = {
      sessionId: 's',
      toolCall: { toolCallId: 'tc', title: 't', kind: 'execute' },
      options: [],
      _meta: { confidence: 0.99, actionClass: 'execute' },
    } as unknown as RequestPermissionRequest;
    return h.controller
      .clarifyingApprover('sess-x', (async () => ({ outcome: 'cancelled' })) as PermissionApprover)(
        request,
        {},
      )
      .then(() => {
        expect(calls.some((c) => c.method === 'steer/escalate')).toBe(false);
        expect(h.escalations).toHaveLength(0);
      });
  });
});

describe('partial acceptance (FR-M25-04)', () => {
  it('accept records both halves; status reads back from the sidecar', async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient(agentOptions());
    await startHosted(h, client, 'sess-acc');
    const ack = await h.controller.accept(
      'sess-acc',
      [{ file: 'src/a.ts', hunks: [{ index: 0 }] }],
      [{ file: 'src/b.ts', hunks: [{ index: 0 }, { index: 1 }] }],
    );
    expect(ack.accepted).toBe(true);
    const accept = calls.find((c) => c.method === 'steer/accept');
    expect(accept?.params).toEqual({
      sessionId: 'sess-acc',
      accepted: [{ file: 'src/a.ts', hunks: [{ index: 0 }] }],
      rejected: [{ file: 'src/b.ts', hunks: [{ index: 0 }, { index: 1 }] }],
    });
    await h.controller.acceptanceStatus('sess-acc');
    expect(calls.some((c) => c.method === 'steer/acceptanceStatus')).toBe(true);
    await stopAndWait(client);
  });

  it('dry-run planner output is recorded (FR-M25-06)', async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const client = new AcpClient(agentOptions());
    await startHosted(h, client, 'sess-plan', 'dry-run');
    const begin = calls.find((c) => c.method === 'acp/sessionBegin');
    expect(begin?.params).toMatchObject({ sessionId: 'sess-plan', mode: 'dry-run' });
    await h.controller.recordPlan(
      'sess-plan',
      [{ content: 'Plan the graph', status: 'pending' }],
      { currency: 'USD', maxTokens: 5000 },
    );
    const plan = calls.find((c) => c.method === 'steer/plan');
    expect(plan?.params).toMatchObject({
      sessionId: 'sess-plan',
      costEstimate: { currency: 'USD', maxTokens: 5000 },
    });
    await stopAndWait(client);
  });
});

describe('dry-run denies mutations at the policy gate (FR-M25-06)', () => {
  const POLICY_YAML = `
version: 1
adapters:
  '*':
    probation: [read, search]
    active: [read, search, edit, execute]
`;

  function manifest(): AdapterManifest {
    return {
      id: 'gemini',
      version: '0.30.0',
      provenance: 'custom',
      vendor: 'Google',
      acp: { command: 'npx', args: [], env: {} },
      roles: ['Gemini CLI'],
      permissions: { allow: ['read', 'edit', 'execute'] },
      learning: { trainable: [], frozen: [] },
      governance: { autonomyTier: 'suggest', probation: {} },
    };
  }

  function request(kind: string): RequestPermissionRequest {
    return {
      sessionId: 'sess-dry',
      toolCall: { toolCallId: 'tc-1', title: `a ${kind} tool`, kind: kind as never },
      options: [
        { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
        { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
      ],
    };
  }

  function dryRunGate(calls: RecordedCall[]) {
    const state = { humanCalls: 0 };
    const gate = createPolicyGate({
      policy: parseAcpPermissionPolicy(POLICY_YAML, 'test'),
      adapter: manifest(),
      adapterState: 'active',
      sessionMode: 'dry-run',
      humanApprover: (async () => {
        state.humanCalls++;
        return { outcome: 'selected', optionId: 'allow-once' };
      }) as PermissionApprover,
      sidecar: {
        async request(method: string, params: unknown): Promise<unknown> {
          if (method !== 'ledger.query') calls.push({ method, params: params as Record<string, unknown> });
          return { entries: [] };
        },
      },
    });
    return { gate, state };
  }

  it('mutation kinds are denied before the human, with a recorded dry_run citation', async () => {
    const calls: RecordedCall[] = [];
    const { gate, state } = dryRunGate(calls);
    const decision = await gate(request('execute'), {});
    // Denied via the agent's own reject option; the human never saw it.
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(state.humanCalls).toBe(0);
    const recorded = calls.find((c) => c.method === 'acp/permissionDecision');
    expect(recorded?.params).toMatchObject({
      sessionId: 'sess-dry',
      toolKind: 'execute',
      outcome: 'denied_by_policy',
    });
    expect(String(recorded?.params.reason)).toContain('dry-run');
  });

  it('planning kinds (read) still reach the human in dry-run', async () => {
    const calls: RecordedCall[] = [];
    const { gate, state } = dryRunGate(calls);
    const decision = await gate(request('read'), {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'allow-once' });
    expect(state.humanCalls).toBe(1);
  });

  it('a re-request cannot escalate: the dry-run denial stands (SEC-28)', async () => {
    const calls: RecordedCall[] = [];
    const { gate, state } = dryRunGate(calls);
    await gate(request('edit'), {});
    const again = await gate(request('edit'), {});
    expect(again).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(state.humanCalls).toBe(0);
    const citations = calls.filter((c) => c.method === 'acp/permissionDecision');
    expect(citations).toHaveLength(2);
    for (const citation of citations) {
      expect(String(citation.params.reason)).toContain('dry-run');
    }
  });
});

describe('honest controls for observed agents (task 18)', () => {
  it('steer on an observe-only session refuses with the structured NOT_HOSTED error', async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const failure = await h.controller.steer('obs-1', 'stop').then(
      () => undefined,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(NotHostedSessionError);
    const error = failure as NotHostedSessionError;
    expect(error.data).toMatchObject({
      code: NOT_HOSTED_CODE,
      sessionId: 'obs-1',
      hosted: false,
      observedOnly: true,
    });
    expect(error.message).toContain('observed, not hosted');
    // Honest, not silent: nothing was recorded, nothing was sent.
    expect(calls).toEqual([]);
  });

  it('status carries hosted: false for observe-only and hosted: true with steerable for hosted', { timeout: TIMEOUT }, async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    const observed = await h.controller.status('obs-2');
    expect(observed).toMatchObject({
      sessionId: 'obs-2',
      hosted: false,
      steerable: false,
    });

    const client = new AcpClient(agentOptions());
    await startHosted(h, client, 'sess-live', 'dry-run');
    const live = await h.controller.status('sess-live');
    expect(live).toMatchObject({
      sessionId: 'sess-live',
      hosted: true,
      steerable: true,
      mode: 'dry-run',
    });
    // The recorded (sidecar) half is surfaced alongside the live truth.
    expect(live.recorded).toMatchObject({ sessionId: 'sess-live', hosted: false });
    await h.controller.endSession('sess-live');
    const ended = await h.controller.status('sess-live');
    expect(ended).toMatchObject({ hosted: false, steerable: false });
    await stopAndWait(client);
  });

  it('accept and plan also refuse observe-only sessions honestly', async () => {
    const calls: RecordedCall[] = [];
    const h = harness(calls);
    await expect(h.controller.accept('obs-3', [], [])).rejects.toBeInstanceOf(
      NotHostedSessionError,
    );
    await expect(h.controller.recordPlan('obs-3', [])).rejects.toBeInstanceOf(
      NotHostedSessionError,
    );
    expect(calls).toEqual([]);
  });
});
