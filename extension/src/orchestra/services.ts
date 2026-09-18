/**
 * Orchestra services (audit TASK-301…309, host half).
 *
 * Typed host-side callers for the Orchestra/F4+ RPC surfaces registered in
 * shared/schema/methods.json. Each function is a thin, honest pass-through:
 * it names the exact RPC, validates required params, and returns the bus
 * result — no caching, no synthesis, no model calls. The workbench screens
 * (owned by the GUI session) consume these; tests drive them with a fake
 * transport asserting the wire shape.
 *
 * The transport is structural — anything with `request(method, params)`
 * matches, including the extension's SidecarClient.
 */

export interface OrchestraTransport {
  request(method: string, params: unknown): Promise<unknown>;
}

/* eslint-disable @typescript-eslint/no-explicit-any */

// -- TASK-301: loops -----------------------------------------------------------

export interface LoopStartParams {
  loopId: string;
  storyId: string;
  kind: 'L1-micro' | 'L2-task' | 'L3-phase' | 'L4-delivery' | 'L5-learning' | 'L6-organisation';
}

export async function loopStart(t: OrchestraTransport, p: LoopStartParams) {
  return t.request('loop.start', p);
}

export async function loopStatus(t: OrchestraTransport, loopId: string, kind?: string) {
  return t.request('loop.status', { loopId, ...(kind ? { kind } : {}) });
}

export async function loopStop(t: OrchestraTransport, loopId: string, reason?: string) {
  return t.request('loop.stop', { loopId, ...(reason ? { reason } : {}) });
}

export async function loopResume(t: OrchestraTransport, loopId: string) {
  return t.request('loop.resume', { loopId });
}

export async function loopReplay(
  t: OrchestraTransport,
  loopId: string,
  stateOverrides: Record<string, unknown>,
) {
  return t.request('loop.replay', { loopId, stateOverrides });
}

// -- TASK-302: router ------------------------------------------------------------

export interface RouterRequestParams {
  actionClass: string;
  agentId: string;
  storyId: string;
  phase: string;
  humanOverride?: boolean;
  payload?: Record<string, unknown>;
}

export async function routerRequestModelCall(t: OrchestraTransport, p: RouterRequestParams) {
  return t.request('router/requestModelCall', p);
}

export async function routerDependencyRatio(
  t: OrchestraTransport,
  scope: { agentId?: string; phase?: string; storyId?: string; actionClass?: string; ceiling?: number },
) {
  return t.request('router/dependencyRatio', scope);
}

// -- TASK-303: memory --------------------------------------------------------------

export interface MemoryEntryParams {
  tier: 'procedural' | 'semantic' | 'episodic';
  subject: string;
  content: string;
  author: string;
  confidence: number;
  origin: 'workspace' | 'user' | 'organisation' | 'story' | 'repository' | 'third_party';
  pinned?: boolean;
  source?: string;
}

export async function memoryRetrieve(
  t: OrchestraTransport,
  p: { agentId: string; queryTerms: string[]; budgetChars: number; tiers?: string[] },
) {
  return t.request('memory/retrieve', p);
}

export async function memoryWrite(
  t: OrchestraTransport,
  p: { entry: MemoryEntryParams; actorIsHuman?: boolean },
) {
  return t.request('memory/write', p);
}

export async function memoryLayered(
  t: OrchestraTransport,
  layers: { tier: string; dir: string }[],
) {
  return t.request('memory/layered', { layers });
}

// -- TASK-304: comprehension ---------------------------------------------------------

export async function comprehensionRecord(t: OrchestraTransport, path: string) {
  return t.request('comprehension/record', { path });
}

export async function comprehensionGate(t: OrchestraTransport, path: string) {
  return t.request('comprehension/gate', { path });
}

// -- TASK-305: adapters -----------------------------------------------------------------

export async function adaptersDiscover(t: OrchestraTransport, roots?: string[]) {
  return t.request('adapters/discover', roots ? { roots } : {});
}

export async function adaptersPlug(t: OrchestraTransport, folder: string) {
  return t.request('adapters/plug', { folder });
}

export async function adaptersUnplug(
  t: OrchestraTransport,
  id: string,
  inflight?: Record<string, unknown>,
) {
  return t.request('adapters/unplug', { id, ...(inflight ? { inflight } : {}) });
}

export async function adaptersPromote(t: OrchestraTransport, id: string) {
  return t.request('adapters/promote', { id });
}

// -- TASK-306: portability -----------------------------------------------------------------

export async function portabilityExport(
  t: OrchestraTransport,
  p: { adapterId: string; destination: string },
) {
  return t.request('portability/export', p);
}

export async function portabilityImport(
  t: OrchestraTransport,
  p: { package: string; confirm: boolean; availableTools: string[] },
) {
  return t.request('portability/import', p);
}

export async function portabilityDiff(t: OrchestraTransport, pkg: string) {
  return t.request('portability/diff', { package: pkg });
}

export async function portabilityTrust(
  t: OrchestraTransport,
  p: { fingerprint: string; humanApproved: boolean },
) {
  return t.request('portability/trust', p);
}

// -- TASK-307: trainer ------------------------------------------------------------------------

export async function trainerTrain(t: OrchestraTransport, openPhases: string[]) {
  return t.request('trainer/train', { openPhases });
}

export async function trainerPromote(
  t: OrchestraTransport,
  p: {
    kind: 'prompt' | 'playbook' | 'checklist' | 'rule';
    subject: string;
    content: string;
    incumbentScore: number;
    candidateScore: number;
    humanApproved: boolean;
    evidence?: Record<string, unknown>;
  },
) {
  return t.request('trainer/promote', p);
}

export async function trainerRollback(t: OrchestraTransport, kind: string, subject: string) {
  return t.request('trainer/rollback', { kind, subject });
}

// -- TASK-308: delivery operations -----------------------------------------------------------------

export async function tenancyRegister(t: OrchestraTransport, p: { tenantId: string; root: string }) {
  return t.request('tenancy/register', p);
}

export async function queueEnqueue(
  t: OrchestraTransport,
  story: { storyId: string; priority: number; tenantId: string; dependencies?: string[] },
) {
  return t.request('queue/enqueue', { story });
}

export async function queueTick(t: OrchestraTransport) {
  return t.request('queue/tick', {});
}

export async function annotationsAdd(
  t: OrchestraTransport,
  p: { targetSeq: number; author: string; text: string; bookmark?: boolean },
) {
  return t.request('annotations/add', p);
}

export async function issuesRecord(
  t: OrchestraTransport,
  p: { agentId: string; severity: 'info' | 'warning' | 'critical'; description: string; storyId: string },
) {
  return t.request('issues/record', p);
}

// -- TASK-309: simulation mode ------------------------------------------------------------------------

export async function simulationServe(
  t: OrchestraTransport,
  p: { method: string; params: Record<string, unknown>; scenario?: string },
) {
  return t.request('simulation/serve', p);
}

export async function simulationTimeControl(
  t: OrchestraTransport,
  p: { action: 'pause' | 'step' | 'play' | 'jump'; rate?: number; sequence?: number },
) {
  return t.request('simulation/timeControl', p);
}

export async function goldenRun(t: OrchestraTransport, folder: string) {
  return t.request('golden/run', { folder });
}

// -- decisions (FR-M13) ----------------------------------------------------------------------------------

export async function decisionsRecord(
  t: OrchestraTransport,
  p: {
    agentId: string;
    inputs: Record<string, unknown>;
    output: unknown;
    confidence: number;
    rationale?: string;
    retrievedMemory?: string[];
    toolCalls?: string[];
    replay?: { actionClass: string; payload?: Record<string, unknown> };
  },
) {
  return t.request('decisions/record', p);
}

export async function decisionsAblate(
  t: OrchestraTransport,
  p: { decisionId: string; withoutFactor: string; inputs: Record<string, unknown>; actionClass?: string },
) {
  return t.request('decisions/ablate', p);
}

export async function decisionsGate(
  t: OrchestraTransport,
  p: {
    testsPassed: boolean;
    scansPassed: boolean;
    approvals: string[];
    changeClass: string;
    ablations?: number[];
  },
) {
  return t.request('decisions/gate', p);
}

// -- tools (FR-M9) ------------------------------------------------------------------------------------------

export async function toolsInvoke(
  t: OrchestraTransport,
  p: { agentId: string; tool: string; argv: string[]; changeClass?: string },
) {
  return t.request('tools/invoke', p);
}
