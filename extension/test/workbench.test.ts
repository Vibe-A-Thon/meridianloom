import { mkdtemp, readFile, writeFile, mkdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchService, validateWorkbenchAgent, type WorkbenchServiceOptions } from '../src/workbench/service';
import type { WorkbenchAgentInput, WorkbenchSnapshot } from '../../shared/ts/workbench';
import type { AdapterSession } from '../src/adapters/launch';

const input = (id: string): WorkbenchAgentInput => ({ id, name: id.toUpperCase(), role: 'developer', description: 'Portable specialist', vendor: 'custom', version: '1.0.0', command: 'test-acp-agent', args: [], instructions: 'Inspect and explain.', permissions: ['read', 'search', 'think'], trainable: ['memory'] });
const services: WorkbenchService[] = [];
afterEach(() => { services.splice(0).forEach(service => service.dispose()); });
async function setup(overrides: Partial<WorkbenchServiceOptions> = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-workbench-'));
  const prompts: Array<{ id: string; text: string }> = [];
  const stops: string[] = [];
  const service = new WorkbenchService({ workspaceDir: () => root, trusted: () => true, enabledTiers: () => ['flight-recorder', 'governor'], sidecar: () => ({ request: async () => ({ entries: [] }) }), humanApprover: async () => ({ outcome: 'cancelled' }), launcher: (agent, options) => ({ adapterId: agent.id, pid: undefined, start: async () => ({ protocolVersion: 1, agentCapabilities: {}, authMethods: [] }), newSession: async () => agent.id, prompt: async (_session, text) => { prompts.push({ id: agent.id, text }); options.onUpdate?.({ sessionId: agent.id, update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: `Result from ${agent.id}` } } }); return 'end_turn'; }, stop: () => { stops.push(agent.id); } }), ...overrides });
  services.push(service);
  const snapshot = async () => await service.request({ action: 'snapshot' }) as WorkbenchSnapshot;
  return { root, service, snapshot, prompts, stops };
}
const save = (service: WorkbenchService, id: string) => service.request({ action: 'agent/save', params: { agent: input(id) } });
const activate = (service: WorkbenchService, id: string) => service.request({ action: 'agent/mode', params: { id, mode: 'active' } });
async function until(check: () => Promise<boolean>) { await vi.waitFor(async () => expect(await check()).toBe(true), { timeout: 3000, interval: 15 }); }

describe('persisted agent workbench', () => {
  it('creates Learning agents, edits and removes only the selected profile, and reloads from disk', async () => {
    const { service, root, snapshot } = await setup();
    await save(service, 'atlas'); await save(service, 'sage');
    expect((await snapshot()).agents.map(a => a.mode)).toEqual(['learning', 'learning']);
    await activate(service, 'atlas');
    await service.request({ action: 'agent/save', params: { agent: { ...input('atlas'), name: 'Atlas revised' } } });
    const reloaded = new WorkbenchService({ workspaceDir: () => root, trusted: () => true, enabledTiers: () => [], sidecar: () => undefined }); services.push(reloaded);
    const loaded = await reloaded.request({ action: 'snapshot' }) as WorkbenchSnapshot;
    expect(loaded.agents[0]).toMatchObject({ name: 'Atlas revised', mode: 'active' });
    await service.request({ action: 'agent/remove', params: { id: 'atlas' } });
    expect((await snapshot()).agents.map(a => a.id)).toEqual(['sage']);
    expect(JSON.parse(await readFile(path.join(root, '.meridian/workbench/state.json'), 'utf8')).agents).toHaveLength(1);
  });
  it('rejects invalid manifests and unsafe IDs without changing the saved state', async () => {
    const { service, snapshot } = await setup();
    await save(service, 'atlas');
    await expect(service.request({ action: 'agent/save', params: { agent: { ...input('../escape') } } })).rejects.toThrow('ID');
    await expect(service.request({ action: 'agent/save', params: { agent: { ...input('broken'), permissions: ['superuser'] } } })).rejects.toThrow('ACP tool kind');
    expect((await snapshot()).agents).toHaveLength(1);
    expect(() => validateWorkbenchAgent({ ...input('secret'), args: ['--api-key=private'] })).toThrow('credentials');
  });
  it('exports a portable profile, imports without activation, and rejects duplicate imports', async () => {
    const one = await setup(); const two = await setup();
    await save(one.service, 'atlas'); await activate(one.service, 'atlas');
    const document = await one.service.request({ action: 'agent/export', params: { id: 'atlas' } }) as { content: string };
    const raw = JSON.parse(document.content);
    expect(raw.agent).not.toHaveProperty('mode'); expect(raw).not.toHaveProperty('runs');
    await two.service.request({ action: 'agent/import', params: { content: document.content } });
    expect((await two.snapshot()).agents[0]).toMatchObject({ id: 'atlas', mode: 'learning' });
    await expect(two.service.request({ action: 'agent/import', params: { content: document.content } })).rejects.toThrow('already exists');
  });
  it.each(['trust', 'governor', 'sidecar'] as const)('refuses execution when %s is unavailable', async blocked => {
    const { service, snapshot } = await setup({ ...(blocked === 'trust' ? { trusted: () => false } : blocked === 'governor' ? { enabledTiers: () => ['flight-recorder'] } : { sidecar: () => undefined }) });
    await save(service, 'atlas'); await activate(service, 'atlas');
    await expect(service.request({ action: 'agent/run', params: { id: 'atlas', prompt: 'Work' } })).rejects.toThrow();
    expect((await snapshot()).runs).toHaveLength(0);
  });
  it('dispatches only active agents, sequentially, and creates reviewable feedback for Learning agents', async () => {
    const { service, snapshot, prompts } = await setup();
    await save(service, 'atlas'); await save(service, 'nova'); await save(service, 'sage');
    await activate(service, 'atlas'); await activate(service, 'nova');
    await service.request({ action: 'deliverable/save', params: { title: 'An accessible dialog', brief: 'Verify keyboard focus and labels.' } });
    const deliverable = (await snapshot()).deliverables[0];
    await service.request({ action: 'deliverable/dispatch', params: { id: deliverable.id } });
    await until(async () => (await snapshot()).deliverables[0].state === 'review');
    expect(prompts.map(p => p.id)).toEqual(['atlas', 'nova']);
    expect((await snapshot()).deliverables[0].agentIds).toEqual(['atlas', 'nova']);
    expect((await snapshot()).runs[0].output).toContain('Result from atlas');
    await service.request({ action: 'deliverable/complete', params: { id: deliverable.id, feedback: 'Always return focus to the trigger.' } });
    const note = (await snapshot()).learning[0];
    expect(note).toMatchObject({ agentId: 'sage', state: 'pending', surface: 'memory' });
    expect(note.content).toContain('return focus');
    await service.request({ action: 'learning/review', params: { id: note.id, decision: 'accepted' } });
    await activate(service, 'sage');
    await service.request({ action: 'agent/run', params: { id: 'sage', prompt: 'Review another dialog.' } });
    await until(async () => prompts.some(p => p.id === 'sage'));
    expect(prompts.find(p => p.id === 'sage')!.text).toContain('Human-reviewed memory');
    expect(prompts.find(p => p.id === 'sage')!.text).toContain('return focus');
  });
  it('deactivation stops the owned process, cancels queued work, and excludes future dispatch', async () => {
    let stopped = 0;
    let prompted = false;
    const launcher: WorkbenchServiceOptions['launcher'] = agent => ({ adapterId: agent.id, pid: undefined, start: async () => ({ protocolVersion: 1, agentCapabilities: {}, authMethods: [] }), newSession: async () => 's', prompt: async (_id, _text, options) => new Promise(resolve => { prompted = true; options?.signal?.addEventListener('abort', () => resolve('cancelled'), { once: true }); }), stop: () => { stopped++; } } as AdapterSession);
    const { service, snapshot } = await setup({ launcher }); await save(service, 'atlas'); await activate(service, 'atlas');
    await service.request({ action: 'agent/run', params: { id: 'atlas', prompt: 'Long task' } });
    await until(async () => prompted);
    await service.request({ action: 'agent/mode', params: { id: 'atlas', mode: 'learning' } });
    await until(async () => (await snapshot()).runs[0].state === 'cancelled');
    expect((await snapshot()).agents[0].mode).toBe('learning');
    await expect(service.request({ action: 'agent/run', params: { id: 'atlas', prompt: 'Another task' } })).rejects.toThrow('Learning agents');
    expect(stopped).toBeGreaterThan(0);
  });
  it('recovers interrupted runs as cancelled without automatically restarting them', async () => {
    const { service, root } = await setup(); await save(service, 'atlas');
    const file = path.join(root, '.meridian/workbench/state.json');
    const state = JSON.parse(await readFile(file, 'utf8'));
    state.runs = [{ id: 'stale-run', agentId: 'atlas', agentName: 'Atlas', prompt: 'Work', state: 'running', startedAt: new Date().toISOString() }];
    await writeFile(file, JSON.stringify(state));
    const reloaded = new WorkbenchService({ workspaceDir: () => root, trusted: () => true, enabledTiers: () => ['flight-recorder'], sidecar: () => undefined }); services.push(reloaded);
    const recovered = await reloaded.request({ action: 'snapshot' }) as WorkbenchSnapshot;
    expect(recovered.runs[0].state).toBe('cancelled'); expect(recovered.agents[0].runtime).toBe('idle');
  });
  it('leaves corrupt storage untouched and surfaces the error', async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-workbench-corrupt-'));
    await mkdir(path.join(root, '.meridian/workbench'), { recursive: true });
    const file = path.join(root, '.meridian/workbench/state.json'); await writeFile(file, '{not json');
    const { service } = await setup({ workspaceDir: () => root });
    await expect(save(service, 'atlas')).rejects.toThrow(); expect(await readFile(file, 'utf8')).toBe('{not json');
  });
});
