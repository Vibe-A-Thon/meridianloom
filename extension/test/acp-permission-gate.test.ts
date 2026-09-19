/**
 * Policy-checked ACP permission requests (FR-M34-04, SEC-28): the gate sits
 * BETWEEN the hosted agent's session/request_permission and the human. The
 * requested tool kind is checked against (a) the Meridian policy allow-list
 * (policy/acp-permissions.yaml, D16-style) and (b) the adapter's declared
 * permission needs + autonomy state, BEFORE the vscode prompt. Every
 * decision — allow, human answer, policy denial, SEC-28 auto-denial — is
 * ledger-recorded via the acp/permissionDecision sidecar RPC.
 *
 * SEC-28: re-requesting a denied permission CANNOT escalate. The gate
 * remembers denials (in-memory per instance, durable via the ledger) and
 * auto-denies a re-request, citing the prior decision.
 */
import { describe, expect, it } from 'vitest';
import type { RequestPermissionRequest } from '../src/acp/protocol';
import { createPolicyGate } from '../src/adapters/permission-gate';
import { parseAcpPermissionPolicy, POLICY_STAR } from '../src/adapters/policy';
import type { AdapterManifest, PermissionKind } from '../src/adapters/manifest';
import type { AdapterState } from '../src/adapters/probation';

const POLICY_YAML = `
version: 1
adapters:
  '*':
    probation: [read, search]
    active: [read, search, edit, execute]
  gemini:
    probation: [read]
    active: [read, edit, execute]
`;

function manifest(overrides: Partial<AdapterManifest> = {}): AdapterManifest {
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
    ...overrides,
  };
}

const EXECUTE_REQUEST: RequestPermissionRequest = {
  sessionId: 'sess-1',
  toolCall: { toolCallId: 'tc-1', title: 'Run the test suite', kind: 'execute' },
  options: [
    { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
    { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
  ],
};

interface RecordedDecision {
  method: string;
  params: Record<string, unknown>;
}

function fakeSidecar(recorded: RecordedDecision[], priorEntries: unknown[] = []) {
  return {
    async request(method: string, params: unknown): Promise<unknown> {
      // The gate's SEC-28 ledger lookups are bookkeeping, not governance
      // records: `recorded` tracks only the acp/permissionDecision trail so
      // the assertions below read as the audit log.
      if (method !== 'ledger.query') {
        recorded.push({ method, params: params as Record<string, unknown> });
      }
      if (method === 'ledger.query') {
        return { entries: priorEntries };
      }
      return { recorded: true };
    },
  };
}

function gate(options: {
  adapterState?: AdapterState;
  humanDecision?: { outcome: 'selected'; optionId: string } | { outcome: 'cancelled' };
  policyYaml?: string;
  sidecar?: ReturnType<typeof fakeSidecar>;
  onRecordError?: (message: string) => void;
}) {
  const humanCalls: RequestPermissionRequest[] = [];
  const approver = createPolicyGate({
    policy: parseAcpPermissionPolicy(options.policyYaml ?? POLICY_YAML, 'test-policy.yaml'),
    adapter: manifest(),
    adapterState: options.adapterState ?? 'active',
    sidecar: options.sidecar,
    humanApprover: async (request) => {
      humanCalls.push(request);
      return options.humanDecision ?? { outcome: 'selected', optionId: 'allow-once' };
    },
    ...(options.onRecordError ? { onRecordError: options.onRecordError } : {}),
  });
  return { approver, humanCalls };
}

describe('ACP permission policy parsing (policy/acp-permissions.yaml shape)', () => {
  it('parses allow lists per adapter and autonomy state', () => {
    const policy = parseAcpPermissionPolicy(POLICY_YAML, 'test');
    expect(policy.errors).toEqual([]);
    expect(policy.allows('gemini', 'probation')).toEqual(['read']);
    expect(policy.allows('gemini', 'active')).toEqual(['read', 'edit', 'execute']);
    expect(policy.allows('someone-else', 'active')).toEqual(['read', 'search', 'edit', 'execute']);
  });

  it('honours deny lists before allow', () => {
    const policy = parseAcpPermissionPolicy(
      `version: 1\nadapters:\n  '*':\n    probation: [read]\n    active: [read, execute]\n    deny: [execute]\n`,
      'test',
    );
    expect(policy.errors).toEqual([]);
    expect(policy.isAllowed('any', 'active', 'execute')).toBe(false);
    expect(policy.isAllowed('any', 'active', 'read')).toBe(true);
  });

  it('invalid policy is fail-closed: nothing is allowed, errors surface', () => {
    const policy = parseAcpPermissionPolicy('adapters: [broken', 'broken.yaml');
    expect(policy.errors.length).toBeGreaterThan(0);
    expect(policy.isAllowed('gemini', 'active', 'read')).toBe(false);
  });

  it('exposes the policy version for the ledger record', () => {
    const policy = parseAcpPermissionPolicy(POLICY_YAML, 'test');
    expect(policy.version).toBe(1);
    expect(POLICY_STAR).toBe('*');
  });
});

describe('policy gate (FR-M34-04): allow reaches the human', () => {
  it('an allowed request shows the vscode prompt and records the human answer', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({ sidecar: fakeSidecar(recorded) });
    const decision = await approver(EXECUTE_REQUEST, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'allow-once' });
    expect(humanCalls).toHaveLength(1);
    expect(recorded).toHaveLength(1);
    expect(recorded[0].method).toBe('acp/permissionDecision');
    expect(recorded[0].params).toMatchObject({
      sessionId: 'sess-1',
      adapterId: 'gemini',
      toolKind: 'execute',
      outcome: 'selected',
      optionId: 'allow-once',
    });
  });

  it('a human cancellation is recorded as cancelled', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({
      sidecar: fakeSidecar(recorded),
      humanDecision: { outcome: 'cancelled' },
    });
    const decision = await approver(EXECUTE_REQUEST, {});
    expect(decision).toEqual({ outcome: 'cancelled' });
    expect(humanCalls).toHaveLength(1);
    expect(recorded[0].params.outcome).toBe('cancelled');
  });
});

describe('policy gate (FR-M34-04): deny NEVER reaches the human', () => {
  it('policy-deny: the vscode prompt is never called, the denial is ledger-recorded', async () => {
    const recorded: RecordedDecision[] = [];
    // gemini on probation may only read — execute is policy-denied.
    const { approver, humanCalls } = gate({ adapterState: 'probation', sidecar: fakeSidecar(recorded) });
    const decision = await approver(EXECUTE_REQUEST, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0); // the human NEVER saw the prompt
    expect(recorded[0].params).toMatchObject({
      outcome: 'denied_by_policy',
      toolKind: 'execute',
      adapterId: 'gemini',
    });
    expect(String(recorded[0].params.reason)).toMatch(/probation/);
  });

  it('declared-needs violation: a kind the manifest never declared is denied', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({ sidecar: fakeSidecar(recorded) });
    const undeclared: RequestPermissionRequest = {
      ...EXECUTE_REQUEST,
      toolCall: { toolCallId: 'tc-9', title: 'Delete a file', kind: 'delete' as PermissionKind },
    };
    // 'delete' is NOT in gemini's declared permissions.allow.
    const decision = await approver(undeclared, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0);
    expect(recorded[0].params.outcome).toBe('denied_by_policy');
    expect(String(recorded[0].params.reason)).toMatch(/not declared/);
  });

  it('a suspended adapter is denied everything', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({
      adapterState: 'suspended',
      sidecar: fakeSidecar(recorded),
    });
    const readRequest: RequestPermissionRequest = {
      ...EXECUTE_REQUEST,
      toolCall: { toolCallId: 'tc-r', title: 'Read a file', kind: 'read' },
    };
    const decision = await approver(readRequest, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0);
    expect(String(recorded[0].params.reason)).toMatch(/suspended/);
  });

  it('without a sidecar the gate still decides, and surfaces the recording failure', async () => {
    const failures: string[] = [];
    const { approver, humanCalls } = gate({ onRecordError: (m) => failures.push(m) });
    const decision = await approver(EXECUTE_REQUEST, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'allow-once' });
    expect(humanCalls).toHaveLength(1);
    expect(failures.length).toBeGreaterThan(0); // never silent (G3)
  });
});

describe('SEC-28: re-requesting a denied permission cannot escalate', () => {
  it('a re-request after a policy denial is auto-denied, citing the prior decision', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({ adapterState: 'probation', sidecar: fakeSidecar(recorded) });

    const first = await approver(EXECUTE_REQUEST, {});
    expect(first).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0);

    // The agent asks again — the exact SEC-28 attack.
    const second = await approver(
      { ...EXECUTE_REQUEST, toolCall: { ...EXECUTE_REQUEST.toolCall, toolCallId: 'tc-2' } },
      {},
    );
    expect(second).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0); // still never reaches the human
    expect(recorded).toHaveLength(2);
    expect(recorded[1].params.outcome).toBe('denied_by_policy');
    const reason = String(recorded[1].params.reason);
    expect(reason).toMatch(/previously denied/);
    expect(reason).toMatch(/execute/);
  });

  it('a denial remembered from the ledger (new session, restarted host) still blocks', async () => {
    const prior = [
      {
        sequence: 41,
        actionType: 'permission_decision',
        decision: 'rejected',
        reworkReason: 'execute is not in the probation allow-list for gemini',
        externalSessionId: 'old-session',
      },
    ];
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({
      adapterState: 'probation',
      sidecar: fakeSidecar(recorded, prior),
    });
    // A different session id, a different tool call id — same permission.
    const request: RequestPermissionRequest = {
      ...EXECUTE_REQUEST,
      sessionId: 'sess-brand-new',
      toolCall: { toolCallId: 'tc-fresh', title: 'Run tests', kind: 'execute' },
    };
    const decision = await approver(request, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
    expect(humanCalls).toHaveLength(0);
    expect(String(recorded[0].params.reason)).toMatch(/previously denied/);
    expect(String(recorded[0].params.reason)).toMatch(/#41/); // the prior decision is cited
  });

  it('a denied kind stays deniable while an allowed kind still reaches the human', async () => {
    const recorded: RecordedDecision[] = [];
    const { approver, humanCalls } = gate({ adapterState: 'probation', sidecar: fakeSidecar(recorded) });
    await approver(EXECUTE_REQUEST, {}); // execute denied
    const readRequest: RequestPermissionRequest = {
      ...EXECUTE_REQUEST,
      toolCall: { toolCallId: 'tc-read', title: 'Read', kind: 'read' },
    };
    const decision = await approver(readRequest, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'allow-once' });
    expect(humanCalls).toHaveLength(1); // read is allowed on probation — prompt shown
  });
});
