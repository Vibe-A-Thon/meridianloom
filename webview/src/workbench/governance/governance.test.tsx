import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LedgerEntry } from '../../../../shared/ts/bus-types';
import type { StudioDocument } from '../../../../shared/ts/studio';
import type { WorkbenchExecute, WorkbenchSnapshot } from '../../../../shared/ts/workbench';
import { WebviewRpcClient } from '../../rpc/client';
import { makeHost } from '../../test/host-harness';
import { aggregateSpend, calibrationBins } from './Analytics';
import { GovernanceStudio } from './GovernanceStudio';
import { EvidencePlans, evidenceGaps, readPlan } from './EvidencePlans';
import type { GovernanceProps } from './common';

function harness(responses: Record<string, unknown> = {}, documents: StudioDocument[] = []) {
  const host = makeHost({ 'gate.profiles': { profiles: [{ name: 'verify', description: 'Tests', criteria: ['tests'] }], policyVersion: 'governance/v1', failClosed: false, errors: [] }, 'ledger.query': { entries: [] }, ...responses });
  const snapshot: WorkbenchSnapshot = { revision: 1, agents: [], skills: [], instructions: [], integrations: [], deliverables: [], runs: [], learning: [], documents, capabilities: { workspaceOpen: true, trusted: true, governorEnabled: true, executionReady: true } };
  const execute = vi.fn(async () => snapshot);
  const props: GovernanceProps = { client: new WebviewRpcClient(host.transport), ready: true, enabledTiers: ['flight-recorder', 'governor'], workspaceDir: '/workspace', onNavigate: vi.fn(), controller: { snapshot, busy: false, error: null, execute: execute as WorkbenchExecute, refresh: async () => {} } };
  return { host, props, execute };
}
const plan: StudioDocument = { id: 'quality-1', kind: 'verification', title: 'Authentication checks', version: 3, tags: ['auth'], createdAt: '2026-09-08T00:00:00Z', updatedAt: '2026-09-08T00:00:00Z', body: JSON.stringify({ criteria: ['Reject expired sessions', 'Accept valid sessions'], notes: 'CI evidence', records: [{ id: 'test-1', title: 'Expired session test', criterion: 'Reject expired sessions', category: 'unit', status: 'pass', severity: 'unspecified', evidence: 'CI run 123 / junit.xml', retries: '' }] }) };
const row = (extra: Partial<LedgerEntry>) => ({ sequence: 1, timestamp: '2026-09-08T00:00:00Z', storyId: 'S-1', actorId: 'atlas', vendor: 'custom', simulated: false, ...extra }) as LedgerEntry;

describe('Governance decision controls', () => {
  it('never evaluates a gate automatically and rejects malformed evidence locally', async () => {
    const h = harness(); render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    expect(h.host.requests.every(request => ['gate.profiles', 'ledger.query'].includes(request.method))).toBe(true);
    fireEvent.change(screen.getByLabelText('Story ID'), { target: { value: 'S-1' } });
    fireEvent.change(screen.getByLabelText('Evidence packet (JSON)'), { target: { value: '[]' } });
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate and record' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('JSON object');
    expect(h.host.requests.some(request => request.method === 'gate.evaluate')).toBe(false);
  });
  it('records a concrete packet and exposes each failing criterion', async () => {
    const h = harness({ 'gate.evaluate': { decision: 'block', profile: 'verify', policyVersion: 'governance/v1', failClosed: false, criteria: [{ id: 'tests', kind: 'testEvidence', passed: false, reason: 'No passing test artifact' }], reasons: ['Verification missing'] } });
    render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    fireEvent.change(screen.getByLabelText('Story ID'), { target: { value: 'S-1' } });
    fireEvent.change(screen.getByLabelText('Evidence packet (JSON)'), { target: { value: '{"evidence":[]}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate and record' })); await h.host.settle();
    expect(h.host.requests.find(request => request.method === 'gate.evaluate')?.params).toEqual({ storyId: 'S-1', gate: 'verify', packet: { evidence: [] } });
    expect(screen.getByText('No passing test artifact')).toBeInTheDocument();
  });
  it('binds approval to the inspected full head and requires a reviewed confirmation', async () => {
    const h = harness({ 'gate.status': { status: 'blocked', subject: 'pr:org/repo#7', requiredApproval: true, halted: false, missing: ['Another approver required'], requiredApprovals: 2, approvalsReceived: 1 }, 'gate.approve': { recorded: true, sequence: 41, approver: { name: 'Reviewer', email: 'reviewer@example.test' }, subject: 'pr:org/repo#7', commit: 'a'.repeat(40) } });
    render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    fireEvent.change(screen.getByLabelText('Branch or PR subject'), { target: { value: 'pr:org/repo#7' } });
    fireEvent.change(screen.getByLabelText('Full head commit'), { target: { value: 'a'.repeat(40) } });
    expect(screen.getByRole('button', { name: 'Review approval' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect approval requirements' })); await h.host.settle();
    fireEvent.click(screen.getByRole('button', { name: 'Review approval' }));
    const dialog = screen.getByRole('dialog'); expect(within(dialog).getByText(/pr:org\/repo#7/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Record approval' })).toBeDisabled();
    expect(h.host.requests.some(request => request.method === 'gate.approve')).toBe(false);
    fireEvent.click(within(dialog).getByLabelText('I have reviewed the target and consequences.'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record approval' })); await h.host.settle();
    expect(h.host.requests.find(request => request.method === 'gate.approve')?.params).toEqual({ subject: 'pr:org/repo#7', commit: 'a'.repeat(40) });
  });
  it('keeps errors visible and permits retry without granting permissions', async () => {
    const h = harness({ 'gate.profiles': new Error('Governor unavailable') }); render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    expect(screen.getByRole('alert')).toHaveTextContent('Governor unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    h.host.replace('gate.profiles', { profiles: [], policyVersion: 'v1', failClosed: false, errors: [] }); await h.host.settle();
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('requires inspection again when the head changes while a status response is in flight', async () => {
    const h = harness({ 'gate.status': { status: 'blocked', subject: 'main', requiredApproval: true, halted: false, missing: ['Approval required'] } });
    render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    fireEvent.change(screen.getByLabelText('Branch or PR subject'), { target: { value: 'main' } });
    fireEvent.change(screen.getByLabelText('Full head commit'), { target: { value: 'a'.repeat(40) } });
    fireEvent.click(screen.getByRole('button', { name: 'Inspect approval requirements' }));
    fireEvent.change(screen.getByLabelText('Full head commit'), { target: { value: 'b'.repeat(40) } });
    await h.host.settle();
    expect(screen.getByRole('button', { name: 'Review approval' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect approval requirements' })); await h.host.settle();
    expect(screen.getByRole('button', { name: 'Review approval' })).toBeEnabled();
  });
  it('preserves the approval dialog and reports runtime refusal without announcing success', async () => {
    const h = harness({ 'gate.status': { status: 'blocked', subject: 'main', requiredApproval: true, halted: false, missing: ['Approval required'] }, 'gate.approve': { recorded: false, sequence: 0 } });
    render(<GovernanceStudio view="gates" {...h.props} />); await h.host.settle();
    fireEvent.change(screen.getByLabelText('Branch or PR subject'), { target: { value: 'main' } });
    fireEvent.change(screen.getByLabelText('Full head commit'), { target: { value: 'a'.repeat(40) } });
    fireEvent.click(screen.getByRole('button', { name: 'Inspect approval requirements' })); await h.host.settle();
    fireEvent.click(screen.getByRole('button', { name: 'Review approval' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByLabelText('I have reviewed the target and consequences.'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record approval' })); await h.host.settle();
    expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent('did not complete');
    expect(screen.queryByText(/Approval recorded by/)).toBeNull();
  });
  it('previews named delegation and records the host-authorized grant only after confirmation', async () => {
    const h = harness({ 'roles/list': { roles: [{ name: 'Approver', description: 'Approve changes', permissions: ['approve'], readOnly: false }], policyVersion: 'roles/v1', source: 'policy/roles.yaml', failClosed: false, errors: [], defaultRole: 'Approver', approvals: { soD: { forbidSelfApproval: true } }, delegation: { maxTtlDays: 7 }, hygiene: {} }, 'roles/delegate': { recorded: true, sequence: 44, delegation: { delegator: { name: 'Host User', email: 'host@example.test' }, to: 'reviewer@example.test', role: 'Approver', expiresAt: '2026-09-10T00:00:00Z', depth: 1 } } });
    render(<GovernanceStudio view="approvals" {...h.props} />); await h.host.settle();
    fireEvent.change(screen.getByLabelText('Recipient'), { target: { value: 'reviewer@example.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review delegation' }));
    expect(h.host.requests.some(request => request.method === 'roles/delegate')).toBe(false);
    const dialog = screen.getByRole('dialog'); expect(dialog).toHaveTextContent('reviewer@example.test');
    fireEvent.click(within(dialog).getByLabelText('I have reviewed the target and consequences.'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record delegation' })); await h.host.settle();
    expect(h.host.requests.find(request => request.method === 'roles/delegate')?.params).toEqual({ to: 'reviewer@example.test', role: 'Approver', holderRole: 'Governor', ttlDays: 1 });
    expect(screen.getByRole('status')).toHaveTextContent('ledger #44');
  });
  it('refuses worktree removal until its exact target is confirmed and defaults to preserving dirty work', async () => {
    const tree = { storyId: 'S-2', branch: 'meridian/S-2', path: '/workspace/.meridian/worktrees/S-2', worktreeRef: '.meridian/worktrees/S-2', baseBranch: 'main', baseCommit: 'a'.repeat(40), headCommit: 'b'.repeat(40), adapterId: 'atlas', dirty: true, unpushedCommits: 2 };
    const h = harness({ 'worktree/list': { worktrees: [tree] }, 'worktree/remove': { removed: true, storyId: 'S-2', branch: 'meridian/S-2', worktreeRef: tree.worktreeRef } });
    render(<GovernanceStudio view="repositories" {...h.props} />); await h.host.settle();
    fireEvent.click(screen.getByRole('button', { name: 'Remove worktree' })); const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(tree.path); expect(within(dialog).getByRole('button', { name: 'Remove worktree' })).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText('I have reviewed the target and consequences.'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove worktree' })); await h.host.settle();
    expect(h.host.requests.find(request => request.method === 'worktree/remove')?.params).toEqual({ storyId: 'S-2', force: false, reason: 'Removed from Repositories & Worktrees' });
  });
  it('previews PR intake before any ledger mutation', async () => {
    const h = harness({ 'pr/ingest': { subject: 'pr:org/repo#7', storyId: 'S-1', sequences: { origin: 1, passes: [], gates: [] }, gates: [], agents: [], hunks: [] } }); render(<GovernanceStudio view="pipeline" {...h.props} />);
    fireEvent.change(screen.getByLabelText('PR evidence envelope (JSON)'), { target: { value: '{"pr":{"number":7,"title":"Fix sessions"},"evidence":[],"approvals":[]}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review PR ingestion' })); expect(h.host.requests.some(request => request.method === 'pr/ingest')).toBe(false);
    const dialog = screen.getByRole('dialog'); expect(dialog).toHaveTextContent('Fix sessions');
    fireEvent.click(within(dialog).getByLabelText('I have reviewed the target and consequences.'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ingest and evaluate PR' })); await h.host.settle();
    expect(h.host.requests.find(request => request.method === 'pr/ingest')?.params).toEqual({ pr: { number: 7, title: 'Fix sessions' }, evidence: [], approvals: [] });
  });
});

describe('Persisted verification evidence', () => {
  it('marks uncovered criteria and preserves optimistic version when editing evidence', async () => {
    const h = harness({}, [plan]); render(<EvidencePlans controller={h.props.controller} kind="verification" />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Authentication checks' }));
    expect(screen.getByText('Uncovered')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit Expired session test' }));
    fireEvent.change(screen.getByLabelText('Evidence source and result'), { target: { value: 'CI run 124 / junit.xml' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save evidence record' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('document/save', { document: expect.objectContaining({ id: plan.id, expectedVersion: 3, kind: 'verification', body: expect.stringContaining('CI run 124') }) }));
  });
  it('requires evidence for pass and does not turn a user-authored record into an RPC verdict', async () => {
    const h = harness({}, [plan]); render(<EvidencePlans controller={h.props.controller} kind="verification" />); fireEvent.click(screen.getByRole('button', { name: 'Inspect Authentication checks' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence record' }));
    fireEvent.change(screen.getByLabelText('Record title'), { target: { value: 'Valid session test' } });
    fireEvent.change(screen.getByLabelText('Observed state'), { target: { value: 'pass' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Save evidence record' }).closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('supporting evidence'); expect(h.execute).not.toHaveBeenCalled(); expect(h.host.requests).toHaveLength(0);
  });
  it('keeps malformed portable evidence readable and never treats missing records as coverage', () => {
    expect(readPlan({ ...plan, body: 'Legacy review notes' })).toEqual({ criteria: [], records: [], notes: 'Legacy review notes' });
    expect(evidenceGaps(readPlan(plan))).toEqual(['Accept valid sessions']);
  });
});

describe('Evidence-derived analytics', () => {
  it('excludes simulated cost and distinguishes zero-cost from missing-price activity', () => {
    const result = aggregateSpend([row({ costUsd: 0 }), row({ costUsd: undefined }), row({ vendor: 'other', costUsd: 2.5 }), row({ costUsd: 100, simulated: true })], 'vendor');
    expect(result).toEqual([['other', { cost: 2.5, priced: 1, unpriced: 0, tokens: 0 }], ['custom', { cost: 0, priced: 1, unpriced: 1, tokens: 0 }]]);
  });
  it('uses explicit confidence/decision pairs and excludes narrative-only or simulated confidence', () => {
    const bins = calibrationBins([row({ confidence: .9, decision: 'pass' }), row({ confidence: .8, decision: 'block' }), row({ confidence: .99 }), row({ confidence: .9, decision: 'pass', simulated: true })]);
    expect(bins[4]).toMatchObject({ low: .8, high: 1, count: 2, outcome: .5 });
    expect(bins[4].confidence).toBeCloseTo(.85);
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(2);
  });
  it('shows empty spend as unattributable, not a fabricated zero bill', async () => {
    const h = harness({
      // An empty result from the real instrument, not an absent one: the
      // sidecar answered and there is genuinely nothing priced in scope.
      'spend/series': {
        scope: {}, dimension: 'agent', totals: { cost: 0, tokens: 0, calls: 0 },
        byValue: {}, spendSeries: {}, cacheHit: false,
        coverage: { value: null, rowsConsidered: 0, rowsAvailable: 0, truncated: false, sequenceRange: [null, null], coverage: 1, label: 'complete' },
      },
    });
    render(<GovernanceStudio view="spend" {...h.props} />); await h.host.settle();
    // N1-T25: the spend view now consumes spend/series rather than recomputing
    // from ledger.query. The invariant is unchanged — an empty sample must
    // never read as a zero vendor bill — so this asserts the same refusal
    // against the surface that now makes it.
    expect(await screen.findByText(/no spend can be attributed/)).toBeInTheDocument();
  });
});
