/**
 * Orchestra services — wire-shape tests (audit TASK-301…309).
 *
 * A fake transport records every RPC name + params; each test asserts the
 * exact contract surface the sidecar implements (core/tests/test_orchestra_rpc.py
 * proves the other half). These tests fail if a service drifts from the
 * method names registered in shared/schema/methods.json.
 */

import { describe, expect, it } from 'vitest';

import {
  adaptersDiscover,
  adaptersPlug,
  adaptersPromote,
  adaptersUnplug,
  annotationsAdd,
  comprehensionGate,
  comprehensionRecord,
  decisionsAblate,
  decisionsGate,
  decisionsRecord,
  goldenRun,
  issuesRecord,
  loopReplay,
  loopResume,
  loopStart,
  loopStatus,
  loopStop,
  memoryLayered,
  memoryRetrieve,
  memoryWrite,
  portabilityDiff,
  portabilityExport,
  portabilityImport,
  portabilityTrust,
  queueEnqueue,
  queueTick,
  routerDependencyRatio,
  routerRequestModelCall,
  simulationServe,
  simulationTimeControl,
  tenancyRegister,
  toolsInvoke,
  trainerPromote,
  trainerRollback,
  trainerTrain,
  type OrchestraTransport,
} from '../src/orchestra/services';

function fakeTransport() {
  const calls: { method: string; params: unknown }[] = [];
  const transport: OrchestraTransport = {
    async request(method: string, params: unknown) {
      calls.push({ method, params });
      return { ok: true };
    },
  };
  return { transport, calls };
}

describe('orchestra services wire shape', () => {
  it('TASK-301: loops call the loop.* family', async () => {
    const { transport, calls } = fakeTransport();
    await loopStart(transport, { loopId: 'L1', storyId: 'S1', kind: 'L2-task' });
    await loopStatus(transport, 'L1', 'L2-task');
    await loopStop(transport, 'L1', 'operator');
    await loopResume(transport, 'L1');
    await loopReplay(transport, 'L1', { approved: true });
    expect(calls.map((c) => c.method)).toEqual([
      'loop.start',
      'loop.status',
      'loop.stop',
      'loop.resume',
      'loop.replay',
    ]);
    expect(calls[0].params).toEqual({ loopId: 'L1', storyId: 'S1', kind: 'L2-task' });
  });

  it('TASK-302: router surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await routerRequestModelCall(transport, {
      actionClass: 'detect_ambiguity', agentId: 'a', storyId: 'S1', phase: 'build',
    });
    await routerDependencyRatio(transport, { storyId: 'S1' });
    expect(calls.map((c) => c.method)).toEqual([
      'router/requestModelCall',
      'router/dependencyRatio',
    ]);
  });

  it('TASK-303: memory surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await memoryRetrieve(transport, { agentId: 'a', queryTerms: ['x'], budgetChars: 1000 });
    await memoryWrite(transport, {
      entry: {
        tier: 'semantic', subject: 's', content: 'c', author: 'a',
        confidence: 0.9, origin: 'workspace',
      },
    });
    await memoryLayered(transport, [{ tier: 'org', dir: '/o' }]);
    expect(calls.map((c) => c.method)).toEqual([
      'memory/retrieve', 'memory/write', 'memory/layered',
    ]);
  });

  it('TASK-304: comprehension surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await comprehensionRecord(transport, 'src/payments.py');
    await comprehensionGate(transport, 'src/payments.py');
    expect(calls.map((c) => c.method)).toEqual([
      'comprehension/record', 'comprehension/gate',
    ]);
  });

  it('TASK-305: adapter lifecycle surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await adaptersDiscover(transport);
    await adaptersPlug(transport, '/adapters/developer');
    await adaptersPromote(transport, 'developer');
    await adaptersUnplug(transport, 'developer', { story: 'S1' });
    expect(calls.map((c) => c.method)).toEqual([
      'adapters/discover', 'adapters/plug', 'adapters/promote', 'adapters/unplug',
    ]);
  });

  it('TASK-306: portability surfaces incl. trust', async () => {
    const { transport, calls } = fakeTransport();
    await portabilityExport(transport, { adapterId: 'dev', destination: '/out' });
    await portabilityDiff(transport, '/pkg.zip');
    await portabilityImport(transport, { package: '/pkg.zip', confirm: true, availableTools: ['build'] });
    await portabilityTrust(transport, { fingerprint: 'ab' * 32, humanApproved: true });
    expect(calls.map((c) => c.method)).toEqual([
      'portability/export', 'portability/diff', 'portability/import', 'portability/trust',
    ]);
  });

  it('TASK-307: trainer surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await trainerTrain(transport, ['intake']);
    await trainerPromote(transport, {
      kind: 'rule', subject: 'r', content: 'c', incumbentScore: 0.8,
      candidateScore: 0.9, humanApproved: true,
    });
    await trainerRollback(transport, 'rule', 'r');
    expect(calls.map((c) => c.method)).toEqual([
      'trainer/train', 'trainer/promote', 'trainer/rollback',
    ]);
  });

  it('TASK-308: queue/tenancy/issues/annotations surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await tenancyRegister(transport, { tenantId: 'acme', root: '/t' });
    await queueEnqueue(transport, { storyId: 'S1', priority: 1, tenantId: 'acme' });
    await queueTick(transport);
    await issuesRecord(transport, {
      agentId: 'qa', severity: 'critical', description: 'd', storyId: 'S1',
    });
    await annotationsAdd(transport, { targetSeq: 1, author: 'aud', text: 't', bookmark: true });
    expect(calls.map((c) => c.method)).toEqual([
      'tenancy/register', 'queue/enqueue', 'queue/tick', 'issues/record', 'annotations/add',
    ]);
  });

  it('TASK-309: simulation + golden surfaces', async () => {
    const { transport, calls } = fakeTransport();
    await simulationServe(transport, { method: 'ledger.query', params: {}, scenario: 'clean-story' });
    await simulationTimeControl(transport, { action: 'jump', sequence: 3 });
    await goldenRun(transport, '/golden/EDB-12345');
    expect(calls.map((c) => c.method)).toEqual([
      'simulation/serve', 'simulation/timeControl', 'golden/run',
    ]);
    expect(calls[0].params).toEqual({
      method: 'ledger.query', params: {}, scenario: 'clean-story',
    });
  });

  it('decisions and tools surfaces match the contract', async () => {
    const { transport, calls } = fakeTransport();
    await decisionsRecord(transport, {
      agentId: 'a', inputs: { x: 1 }, output: 'ok', confidence: 0.9,
      replay: { actionClass: 'detect_ambiguity' },
    });
    await decisionsAblate(transport, { decisionId: 'dec-1', withoutFactor: 'x', inputs: {} });
    await decisionsGate(transport, {
      testsPassed: true, scansPassed: true, approvals: ['lead'], changeClass: 'ordinary',
    });
    await toolsInvoke(transport, { agentId: 'a', tool: 'build', argv: ['echo', 'hi'] });
    expect(calls.map((c) => c.method)).toEqual([
      'decisions/record', 'decisions/ablate', 'decisions/gate', 'tools/invoke',
    ]);
  });
});
