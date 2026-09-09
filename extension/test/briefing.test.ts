import { mkdtemp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { WorkbenchService } from '../src/workbench/service';
import { composeBriefing, convene, BRIEFING_BUDGET } from '../src/workbench/briefing';
import type {
  WorkbenchAgent,
  WorkbenchSnapshot,
} from '../../shared/ts/workbench';

/**
 * What the agent actually receives.
 *
 * These are the tests the catalogue was missing. Before them, skills,
 * instruction files, phase tags and connected systems were stored, displayed,
 * exported and bound — and none of it reached the running agent, while the
 * interface said it did. Every assertion here exists to keep one of those
 * claims true, at the only place that decides it: the prompt.
 */

const agent = (over: Partial<WorkbenchAgent> = {}): WorkbenchAgent => ({
  id: 'atlas',
  name: 'Atlas',
  role: 'Architect',
  description: '',
  vendor: 'custom',
  version: '1.0.0',
  command: 'test-acp-agent',
  args: [],
  instructions: '',
  permissions: ['read'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
  mode: 'active',
  runtime: 'idle',
  learningState: 'waiting',
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: '2026-09-09T00:00:00Z',
  ...over,
});

const base = {
  skills: [],
  instructions: [],
  integrations: [],
  memory: [],
} as const;

// --- composition ---------------------------------------------------------

describe('composeBriefing', () => {
  it('puts a bound skill in the prompt, which is the only thing that makes it real', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { title: 'Add checkout', body: 'Implement the flow.' },
      skills: [
        {
          id: 'java',
          name: 'Java Spring',
          summary: 'Gradle, not Maven.',
          version: '2.0.0',
          tags: [],
          body: '# Build\n\nUse ./gradlew build, never mvn.',
          enabled: true,
          source: 'authored',
          createdAt: '',
          updatedAt: '',
        },
      ],
    });
    expect(document).toContain('Java Spring');
    expect(document).toContain('./gradlew build, never mvn');
  });

  it('orders instruction files least specific first, and says the rule in words', () => {
    const make = (id: string, scope: 'organisation' | 'workspace' | 'adapter') => ({
      id,
      name: id,
      summary: '',
      scope,
      body: `body-${id}`,
      enabled: true,
      source: 'authored' as const,
      createdAt: '',
      updatedAt: '',
    });
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'Do the thing.' },
      // Supplied in the wrong order on purpose.
      instructions: [make('adapter-rules', 'adapter'), make('house', 'organisation'), make('repo', 'workspace')],
    });
    const positions = ['body-house', 'body-repo', 'body-adapter-rules'].map((needle) =>
      document.indexOf(needle),
    );
    expect(positions.every((position) => position > 0)).toBe(true);
    // Least specific first, so the most specific is the last thing read.
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(document).toContain('adapter over workspace over user over organisation');
  });

  it('names the phase it was convened for, and what that phase is for', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'Review it.' },
      phase: 'review',
    });
    expect(document).toContain('Review & Integration');
    expect(document).toContain('Critique adversarially');
  });

  it('gives connection facts but never a credential, and says the agent must bring its own', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'Check the pipeline.' },
      integrations: [
        {
          id: 'gitlab-prod',
          integrationId: 'gitlab',
          name: 'Production GitLab',
          config: { baseUrl: 'https://gitlab.example.com', projectId: '42' },
          enabled: true,
          secretKeys: ['token'],
          createdAt: '',
          updatedAt: '',
          lastProbe: { ok: true, at: '2026-09-09T10:00:00Z', detail: 'answered', latencyMs: 20 },
        },
      ],
    });
    expect(document).toContain('https://gitlab.example.com');
    expect(document).toContain('projectId=42');
    expect(document).toContain('Meridian can read: Pipelines');
    // The whole point: no secret, and no pretence that the agent has access.
    expect(document).toContain('does not pass them to you');
    expect(document).not.toMatch(/token[=:]\s*\S/);
  });

  it('reports an unreachable connection as unreachable rather than as available', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'x' },
      integrations: [
        {
          id: 'dd',
          integrationId: 'datadog',
          name: 'Datadog',
          config: { site: 'datadoghq.com' },
          enabled: true,
          secretKeys: [],
          createdAt: '',
          updatedAt: '',
          lastProbe: { ok: false, at: 'then', detail: 'API key rejected', latencyMs: 9 },
        },
      ],
    });
    expect(document).toContain('NOT reachable');
    expect(document).toContain('API key rejected');
  });

  it('includes accepted memory and nothing awaiting review', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'x' },
      memory: [
        {
          id: '1',
          agentId: 'atlas',
          deliverableId: 'd',
          title: 'Prefer composition',
          content: 'Use composition over inheritance here.',
          state: 'accepted',
          createdAt: '',
          surface: 'memory',
        },
      ],
    });
    expect(document).toContain('Prefer composition');
    expect(document).toContain('A human reviewed and accepted');
  });

  it('is deterministic, so a run can be reproduced from what was recorded', () => {
    const input = {
      ...base,
      agent: agent(),
      task: { title: 'T', body: 'B' },
      phase: 'build' as const,
    };
    expect(composeBriefing(input)).toBe(composeBriefing(input));
  });

  it('truncates rather than blowing a context window, and says that it did', () => {
    const document = composeBriefing({
      ...base,
      agent: agent(),
      task: { body: 'x' },
      skills: [
        {
          id: 'huge',
          name: 'Huge',
          summary: '',
          version: '1.0.0',
          tags: [],
          body: 'z'.repeat(200_000),
          enabled: true,
          source: 'authored',
          createdAt: '',
          updatedAt: '',
        },
      ],
    });
    expect(document.length).toBeLessThanOrEqual(BRIEFING_BUDGET + 400);
    expect(document).toContain('Meridian truncated');
  });
});

// --- convening -----------------------------------------------------------

describe('convene', () => {
  it('convenes by phase, in phase order, not in roster order', () => {
    const convened = convene([
      agent({ id: 'rel', name: 'Rel', phases: ['release'] }),
      agent({ id: 'des', name: 'Des', phases: ['design'] }),
      agent({ id: 'bui', name: 'Bui', phases: ['build'] }),
    ]);
    expect(convened.map((entry) => entry.agent.id)).toEqual(['des', 'bui', 'rel']);
    expect(convened.map((entry) => entry.phase)).toEqual(['design', 'build', 'release']);
  });

  it('convenes one agent once per phase it is tagged for', () => {
    const convened = convene([agent({ phases: ['design', 'review'] })]);
    expect(convened).toHaveLength(2);
    expect(convened.map((entry) => entry.phase)).toEqual(['design', 'review']);
  });

  it('does not convene a Learning agent, however it is tagged', () => {
    const convened = convene([
      agent({ id: 'a', mode: 'learning', phases: ['build'] }),
      agent({ id: 'b', mode: 'active', phases: ['build'] }),
    ]);
    expect(convened.map((entry) => entry.agent.id)).toEqual(['b']);
  });

  it('does not convene an untagged agent once tagging is in use', () => {
    const convened = convene([
      agent({ id: 'tagged', phases: ['build'] }),
      agent({ id: 'untagged', phases: [] }),
    ]);
    expect(convened.map((entry) => entry.agent.id)).toEqual(['tagged']);
  });

  it('falls back to every active agent when nobody is tagged at all', () => {
    // A workspace that predates phase tagging, or a user who never opened the
    // board, must not silently stop working.
    const convened = convene([agent({ id: 'a' }), agent({ id: 'b' })]);
    expect(convened.map((entry) => entry.agent.id)).toEqual(['a', 'b']);
    expect(convened.every((entry) => entry.phase === undefined)).toBe(true);
  });
});

// --- end to end through the service --------------------------------------

const services: WorkbenchService[] = [];
afterEach(() => services.splice(0).forEach((service) => service.dispose()));

async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-briefing-'));
  const prompts: string[] = [];
  const service = new WorkbenchService({
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ['flight-recorder', 'governor'],
    sidecar: () => ({ request: async () => ({ entries: [] }) }),
    humanApprover: async () => ({ outcome: 'cancelled' }),
    launcher: (adapter, options) => ({
      adapterId: adapter.id,
      pid: undefined,
      start: async () => ({ protocolVersion: 1, agentCapabilities: {}, authMethods: [] }),
      newSession: async () => adapter.id,
      prompt: async (_session, text) => {
        prompts.push(text);
        options.onUpdate?.({
          sessionId: adapter.id,
          update: {
            sessionUpdate: 'agent_message_chunk',
            content: { type: 'text', text: 'done' },
          },
        });
        return 'end_turn';
      },
      stop: () => {},
    }),
  });
  services.push(service);
  const snapshot = async () =>
    (await service.request({ action: 'snapshot' })) as WorkbenchSnapshot;
  return { service, snapshot, prompts };
}

const until = async (check: () => Promise<boolean>, budgetMs = 5_000) => {
  const deadline = Date.now() + budgetMs;
  while (Date.now() < deadline) {
    if (await check()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error('condition not reached in time');
};

describe('a dispatched deliverable', () => {
  it('sends the bound skill and instruction to the agent that runs', async () => {
    const { service, snapshot, prompts } = await setup();
    await service.request({
      action: 'skill/save',
      params: {
        skill: {
          id: 'java',
          name: 'Java Spring',
          summary: '',
          version: '1.0.0',
          tags: [],
          body: 'Use ./gradlew build, never mvn.',
        },
      },
    });
    await service.request({
      action: 'instruction/save',
      params: {
        instruction: {
          id: 'house',
          name: 'House rules',
          summary: '',
          scope: 'workspace',
          body: 'Small commits, always.',
        },
      },
    });
    await service.request({ action: 'agent/save', params: { agent: agent() } });
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'active' } });
    await service.request({
      action: 'agent/assign',
      params: {
        id: 'atlas',
        skillIds: ['java'],
        instructionIds: ['house'],
        phases: ['build'],
      },
    });
    await service.request({
      action: 'deliverable/save',
      params: { title: 'Checkout', brief: 'Implement it.' },
    });
    await service.request({
      action: 'deliverable/dispatch',
      params: { id: (await snapshot()).deliverables[0].id },
    });
    await until(async () => prompts.length > 0);

    // The claim the Skills tab makes, asserted where it is decided.
    expect(prompts[0]).toContain('Use ./gradlew build, never mvn');
    expect(prompts[0]).toContain('Small commits, always');
    expect(prompts[0]).toContain('Implementation');
    expect(prompts[0]).toContain('Checkout');
  });

  it('records the phase on the run, so the history says why the agent ran', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent() } });
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'active' } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', phases: ['design', 'review'] },
    });
    await service.request({
      action: 'deliverable/save',
      params: { title: 'Checkout', brief: 'Implement it.' },
    });
    await service.request({
      action: 'deliverable/dispatch',
      params: { id: (await snapshot()).deliverables[0].id },
    });
    const runs = (await snapshot()).runs;
    // One agent, two phases, two runs — designing and reviewing your own work
    // are different acts.
    expect(runs).toHaveLength(2);
    expect(runs.map((run) => run.phase)).toEqual(['design', 'review']);
  });

  it('does not convene an active agent that carries no phase tag when others do', async () => {
    const { service, snapshot } = await setup();
    for (const id of ['atlas', 'vale']) {
      await service.request({ action: 'agent/save', params: { agent: agent({ id, name: id }) } });
      await service.request({ action: 'agent/mode', params: { id, mode: 'active' } });
    }
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', phases: ['build'] },
    });
    await service.request({
      action: 'deliverable/save',
      params: { title: 'Checkout', brief: 'Implement it.' },
    });
    await service.request({
      action: 'deliverable/dispatch',
      params: { id: (await snapshot()).deliverables[0].id },
    });
    const runs = (await snapshot()).runs;
    expect(runs).toHaveLength(1);
    expect(runs[0].agentId).toBe('atlas');
  });

  it('refuses the dispatch, naming the reason, when tagging excludes everyone', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent() } });
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'active' } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', phases: ['build'] },
    });
    // Take the tag away again: active, but tagged for nothing, while the
    // roster as a whole is in tagged mode.
    await service.request({ action: 'agent/assign', params: { id: 'atlas', phases: [] } });
    await service.request({
      action: 'deliverable/save',
      params: { title: 'Checkout', brief: 'Implement it.' },
    });
    // With nobody tagged the fallback applies, so this must still run.
    await service.request({
      action: 'deliverable/dispatch',
      params: { id: (await snapshot()).deliverables[0].id },
    });
    expect((await snapshot()).runs).toHaveLength(1);
  });

  it('does not send a disabled skill, so the enable switch is not a decoration', async () => {
    const { service, snapshot, prompts } = await setup();
    await service.request({
      action: 'skill/save',
      params: {
        skill: {
          id: 'java',
          name: 'Java',
          summary: '',
          version: '1.0.0',
          tags: [],
          body: 'NEVER-SEE-THIS',
        },
      },
    });
    await service.request({ action: 'agent/save', params: { agent: agent() } });
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'active' } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', skillIds: ['java'] },
    });
    await service.request({
      action: 'skill/toggle',
      params: { id: 'java', enabled: false },
    });
    await service.request({
      action: 'agent/run',
      params: { id: 'atlas', prompt: 'Do the thing.' },
    });
    await until(async () => prompts.length > 0);
    expect(prompts[0]).not.toContain('NEVER-SEE-THIS');
  });

  it('records the briefing verbatim on the run, so it can be reproduced', async () => {
    const { service, snapshot, prompts } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent() } });
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'active' } });
    await service.request({
      action: 'agent/run',
      params: { id: 'atlas', prompt: 'Do the thing.' },
    });
    await until(async () => prompts.length > 0);
    expect((await snapshot()).runs[0].prompt).toBe(prompts[0]);
  });
});
