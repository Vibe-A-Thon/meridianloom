import { promises as fs } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import type { TierName } from '../../../shared/ts/bus-types';
import type {
  LearningArtifact,
  PortableAgentDocument,
  WorkbenchAgent,
  WorkbenchAgentInput,
  WorkbenchDeliverable,
  WorkbenchRequest,
  WorkbenchRun,
  WorkbenchSnapshot,
} from '../../../shared/ts/workbench';
import { validateAdapterManifest, type AdapterManifest } from '../adapters/manifest';
import { launchAdapter, type AdapterSession, type LaunchOptions } from '../adapters/launch';
import type { DiscoveredAdapter } from '../adapters/discovery';
import { createPolicyGate, type PolicyGateSidecar } from '../adapters/permission-gate';
import { parseAcpPermissionPolicy } from '../adapters/policy';
import type { PermissionApprover } from '../acp/client';
import { hostedSessionRegistry } from '../governance/session-registry';
import { STUDIO_DOCUMENT_KINDS, type StudioDocument } from '../../../shared/ts/studio';

interface StoredState {
  schemaVersion: 1;
  revision: number;
  agents: WorkbenchAgent[];
  deliverables: WorkbenchDeliverable[];
  runs: WorkbenchRun[];
  learning: LearningArtifact[];
  documents: StudioDocument[];
  documentRevisions: StudioDocument[];
}

export interface WorkbenchServiceOptions {
  workspaceDir(): string | undefined;
  trusted(): boolean;
  enabledTiers(): readonly TierName[];
  sidecar(): PolicyGateSidecar | undefined;
  humanApprover?: PermissionApprover;
  /** Bundled policy/acp-permissions.yaml, after the workspace override. */
  policyPaths?: readonly string[];
  onError?: (message: string) => void;
  /** Tests inject a conformant ACP session; production uses launchAdapter. */
  launcher?: (adapter: DiscoveredAdapter, options: LaunchOptions) => AdapterSession;
}

function blankState(): StoredState {
  return { schemaVersion: 1, revision: 0, agents: [], deliverables: [], runs: [], learning: [], documents: [], documentRevisions: [] };
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Expected an object.');
  return value as Record<string, unknown>;
}
function string(value: unknown, label: string, max: number, allowEmpty = false): string {
  if (
    typeof value !== 'string' ||
    value.length > max ||
    (!allowEmpty && !value.trim()) ||
    value.includes('\0')
  ) {
    throw new Error(
      `${label} must be ${allowEmpty ? 'text' : 'non-empty text'} of at most ${max} characters.`,
    );
  }
  return value;
}
function id(value: unknown): string {
  const result = string(value, 'ID', 100);
  if (!/^[a-z0-9][a-z0-9-]*$/.test(result))
    throw new Error('ID must contain lowercase letters, digits, and dashes.');
  return result;
}
function list(value: unknown, label: string, max = 100): string[] {
  if (!Array.isArray(value) || value.length > max)
    throw new Error(`${label} must be a list of at most ${max} entries.`);
  return value.map((entry) => string(entry, label, 4_000, label === 'Arguments'));
}

function documentFields(value: unknown): Pick<StudioDocument, 'kind' | 'title' | 'body' | 'tags'> {
  const raw = record(value);
  if (!(STUDIO_DOCUMENT_KINDS as readonly unknown[]).includes(raw.kind)) throw new Error('Unknown studio document kind.');
  return { kind: raw.kind as StudioDocument['kind'], title: string(raw.title, 'Document title', 200).trim(),
    body: string(raw.body, 'Document body', 250_000, true),
    tags: list(raw.tags, 'Document tags', 30).map(tag => string(tag, 'Tag', 80).trim()) };
}

/** The existing ACP adapter schema remains the authoritative launch validator. */
export function agentManifest(agent: WorkbenchAgentInput): AdapterManifest {
  const parsed = validateAdapterManifest(
    {
      adapter: { id: agent.id, version: agent.version, provenance: 'custom', vendor: agent.vendor },
      acp: { command: agent.command, args: agent.args, env: {} },
      role: { fills: [agent.role] },
      permissions: { allow: agent.permissions },
      learning: {
        trainable: agent.trainable,
        frozen: ['policy', 'rules', 'memory', 'skills', 'calibration'].filter(
          (surface) => !agent.trainable.includes(surface as never),
        ),
      },
      governance: { autonomy_tier: 'suggest' },
    },
    'Agent configuration',
  );
  if (!parsed.ok) throw new Error(parsed.errors.join('\n'));
  return parsed.manifest;
}

export function validateWorkbenchAgent(value: unknown): WorkbenchAgentInput {
  const raw = record(value);
  const agent: WorkbenchAgentInput = {
    id: id(raw.id),
    name: string(raw.name, 'Name', 120).trim(),
    role: string(raw.role, 'Role', 120).trim(),
    description: string(raw.description, 'Description', 2_000, true),
    vendor: string(raw.vendor, 'Vendor', 120, true),
    version: string(raw.version, 'Version', 40),
    command: string(raw.command, 'Executable', 2_000).trim(),
    args: list(raw.args, 'Arguments'),
    instructions: string(raw.instructions, 'Instructions', 40_000, true),
    permissions: list(raw.permissions, 'Permissions', 9) as WorkbenchAgentInput['permissions'],
    trainable: list(raw.trainable, 'Trainable surfaces', 5) as WorkbenchAgentInput['trainable'],
  };
  // Secrets belong in the launched agent's environment/credential store. This
  // service intentionally offers no environment-value persistence surface.
  if (agent.args.some((arg) => /(?:api[-_]?key|access[-_]?token|password|secret)\s*=/i.test(arg))) {
    throw new Error(
      'Use the agent credential store or environment for credentials; do not put secrets in arguments.',
    );
  }
  agentManifest(agent);
  return agent;
}

/** Local drafts and participation are independent from the sidecar. Only
 * explicit run actions start ACP processes; one agent writes at a time. */
export class WorkbenchService {
  private state = blankState();
  private loadedRoot: string | undefined;
  private tail: Promise<unknown> = Promise.resolve();
  private readonly listeners = new Set<() => void>();
  private readonly sessions = new Map<
    string,
    { session: AdapterSession; controller: AbortController; sessionId?: string; acceptingSteering?: boolean }
  >();
  private readonly output = new Map<string, string>();
  private pumping = false;
  private disposed = false;
  private changeTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(private readonly options: WorkbenchServiceOptions) {}

  onDidChange(listener: () => void): { dispose(): void } {
    this.listeners.add(listener);
    return { dispose: () => this.listeners.delete(listener) };
  }

  private notify(): void {
    if (this.disposed || this.changeTimer) return;
    this.changeTimer = setTimeout(() => {
      this.changeTimer = undefined;
      for (const listener of this.listeners) listener();
    }, 50);
  }
  private serialize<T>(task: () => Promise<T>): Promise<T> {
    const next = this.tail.then(task, task);
    this.tail = next.catch(() => undefined);
    return next;
  }
  private capabilities(): WorkbenchSnapshot['capabilities'] {
    const workspaceOpen = Boolean(this.options.workspaceDir());
    const workspaceChanged = Boolean(
      this.loadedRoot &&
        (!this.options.workspaceDir() ||
          path.resolve(this.options.workspaceDir()!) !== this.loadedRoot),
    );
    const trusted = this.options.trusted();
    const governorEnabled = this.options.enabledTiers().includes('governor');
    const executionBlockedReason = workspaceChanged
      ? 'The workspace changed. Reopen the Meridian window before running agents.'
      : !workspaceOpen
        ? 'Open a workspace to run agents.'
        : !trusted
          ? 'Trust this workspace before running its configured executables.'
          : !governorEnabled
            ? 'Enable the Governor tier to run agents.'
            : !this.options.sidecar()
              ? 'Wait for the sidecar so permission decisions can be recorded.'
              : !this.options.humanApprover
                ? 'The host permission approver is unavailable.'
                : undefined;
    return {
      workspaceOpen,
      trusted,
      governorEnabled,
      executionReady: !executionBlockedReason,
      ...(executionBlockedReason ? { executionBlockedReason } : {}),
    };
  }
  private snapshot(): WorkbenchSnapshot {
    const result = structuredClone({ ...this.state, capabilities: this.capabilities() });
    return {
      revision: result.revision,
      deliverables: result.deliverables,
      learning: result.learning,
      documents: result.documents,
      documentRevisions: result.documentRevisions,
      agents: result.agents.map((agent) => ({
        ...agent,
        runtime: this.state.runs.some((run) => run.agentId === agent.id && run.state === 'running')
          ? 'running'
          : 'idle',
        learningState: this.state.learning.some(
          (note) => note.agentId === agent.id && note.state === 'pending',
        )
          ? 'review'
          : 'waiting',
      })),
      runs: result.runs.map((run) => ({
        ...run,
        ...(this.output.has(run.id) ? { output: this.output.get(run.id) } : {}),
      })),
      capabilities: result.capabilities,
    };
  }
  private async load(): Promise<void> {
    const current = this.options.workspaceDir();
    if (!current) {
      if (this.loadedRoot)
        throw new Error(
          'The workspace was closed. Reopen the Meridian window before making changes.',
        );
      return;
    }
    const root = path.resolve(current);
    if (root === this.loadedRoot) return;
    if (this.loadedRoot)
      throw new Error('The workspace changed. Reopen Meridian before editing this workbench.');
    const file = path.join(root, '.meridian', 'workbench', 'state.json');
    let content: string;
    try {
      await this.assertContained(root, file);
      const stat = await fs.stat(file);
      if (stat.size > 20_000_000)
        throw new Error('Workbench state exceeds the 20 MB safety limit.');
      content = await fs.readFile(file, 'utf8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      this.loadedRoot = root;
      return;
    }
    const raw = record(JSON.parse(content));
    if (
      raw.schemaVersion !== 1 ||
      !Number.isSafeInteger(raw.revision) ||
      !Array.isArray(raw.agents) ||
      !Array.isArray(raw.deliverables) ||
      !Array.isArray(raw.runs) ||
      !Array.isArray(raw.learning)
    ) {
      throw new Error(
        'Workbench state is invalid or from an unsupported version. It has been left untouched.',
      );
    }
    for (const entry of raw.agents) {
      validateWorkbenchAgent(entry);
      if (!['active', 'learning'].includes(record(entry).mode as string))
        throw new Error('Invalid stored agent mode.');
    }
    const loaded = raw as unknown as StoredState;
    for (const key of ['documents', 'documentRevisions'] as const) {
      if (loaded[key] === undefined) loaded[key] = [];
      if (!Array.isArray(loaded[key])) throw new Error('Invalid stored studio documents.');
      for (const entry of loaded[key]) {
        documentFields(entry); id(entry.id);
        if (!Number.isSafeInteger(entry.version) || entry.version < 1) throw new Error('Invalid document version.');
        string(entry.createdAt, 'Document creation date', 40); string(entry.updatedAt, 'Document update date', 40);
      }
    }
    for (const run of loaded.runs) {
      if (
        !run ||
        typeof run.id !== 'string' ||
        typeof run.agentId !== 'string' ||
        !['queued', 'running', 'completed', 'failed', 'cancelled'].includes(run.state)
      )
        throw new Error('Invalid stored run.');
      if (run.state === 'running' || run.state === 'queued') {
        run.state = 'cancelled';
        run.finishedAt = new Date().toISOString();
        run.error = 'The extension stopped before this run finished. Run again explicitly.';
      }
    }
    for (const item of loaded.deliverables) {
      if (!item || typeof item.id !== 'string' || !Array.isArray(item.agentIds))
        throw new Error('Invalid stored deliverable.');
      if (item.state === 'running') item.state = 'failed';
    }
    for (const note of loaded.learning) {
      if (
        !note ||
        typeof note.id !== 'string' ||
        typeof note.content !== 'string' ||
        !['pending', 'accepted', 'dismissed'].includes(note.state)
      )
        throw new Error('Invalid stored learning note.');
    }
    this.state = loaded;
    this.loadedRoot = root;
  }
  private async persist(): Promise<void> {
    if (!this.loadedRoot) throw new Error('Open a workspace before saving workbench changes.');
    const directory = path.join(this.loadedRoot, '.meridian', 'workbench');
    // Check existing parents before creating any descendants: even mkdir
    // must not follow a workspace junction outside the project.
    let parent = this.loadedRoot;
    for (const segment of ['.meridian', 'workbench']) {
      parent = path.join(parent, segment);
      try {
        await this.assertContained(this.loadedRoot, parent);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      }
      await fs.mkdir(parent).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== 'EEXIST') throw error;
      });
      await this.assertContained(this.loadedRoot, parent);
    }
    // Resolve the actual parent before writing; a symlink cannot redirect
    // workbench mutations outside the workspace.
    const [realRoot, realDirectory] = await Promise.all([
      fs.realpath(this.loadedRoot),
      fs.realpath(directory),
    ]);
    const relative = path.relative(realRoot, realDirectory);
    if (relative.startsWith('..') || path.isAbsolute(relative))
      throw new Error('Workbench storage must remain inside the workspace.');
    const temporary = path.join(directory, `.state-${randomUUID()}.tmp`);
    const serialized = JSON.stringify(this.state, null, 2);
    if (Buffer.byteLength(serialized, 'utf8') > 20_000_000)
      throw new Error(
        'Workbench state would exceed 20 MB. Export and remove unused profiles or memory before adding more data.',
      );
    try {
      await fs.writeFile(temporary, serialized, {
        encoding: 'utf8',
        flag: 'wx',
        mode: 0o600,
      });
      await fs.rename(temporary, path.join(directory, 'state.json'));
    } finally {
      await fs.unlink(temporary).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== 'ENOENT') this.options.onError?.(error.message);
      });
    }
  }
  private async assertContained(root: string, target: string): Promise<void> {
    const [realRoot, realTarget] = await Promise.all([fs.realpath(root), fs.realpath(target)]);
    const relative = path.relative(realRoot, realTarget);
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative))
      throw new Error('Workbench storage must remain inside the workspace.');
  }
  private agent(agentId: string): WorkbenchAgent {
    const agent = this.state.agents.find((entry) => entry.id === agentId);
    if (!agent) throw new Error(`Agent '${agentId}' does not exist.`);
    return agent;
  }
  private archiveDocument(document: StudioDocument): void {
    const prior = this.state.documentRevisions.filter(entry => entry.id === document.id);
    this.state.documentRevisions = this.state.documentRevisions.filter(entry => entry.id !== document.id);
    this.state.documentRevisions.push(...prior.slice(-19), structuredClone(document));
  }
  private deliverable(deliverableId: string): WorkbenchDeliverable {
    const item = this.state.deliverables.find((entry) => entry.id === deliverableId);
    if (!item) throw new Error('Deliverable does not exist.');
    return item;
  }
  private cancelRun(run: WorkbenchRun, reason: string): void {
    if (run.state !== 'queued' && run.state !== 'running') return;
    run.state = 'cancelled';
    run.error = reason;
    run.finishedAt = new Date().toISOString();
    const handle = this.sessions.get(run.id);
    handle?.controller.abort();
    handle?.session.stop();
    this.settleDeliverable(run.deliverableId);
  }
  private settleDeliverable(deliverableId?: string): void {
    if (!deliverableId) return;
    const item = this.deliverable(deliverableId);
    const runs = this.state.runs.filter((run) => run.deliverableId === deliverableId);
    item.state = runs.some((run) => run.state === 'queued' || run.state === 'running')
      ? 'running'
      : runs.some((run) => run.state !== 'completed')
        ? 'failed'
        : 'review';
    item.updatedAt = new Date().toISOString();
  }
  private queueRun(agent: WorkbenchAgent, prompt: string, deliverableId?: string): void {
    if (agent.mode !== 'active')
      throw new Error(
        `Activate ${agent.name} before running it; Learning agents do not receive deliverables.`,
      );
    if (
      this.state.runs.some(
        (run) => run.agentId === agent.id && (run.state === 'running' || run.state === 'queued'),
      )
    )
      throw new Error(`${agent.name} already has a queued or running task.`);
    this.state.runs.push({
      id: randomUUID(),
      agentId: agent.id,
      agentName: agent.name,
      prompt,
      state: 'queued',
      startedAt: new Date().toISOString(),
      ...(deliverableId ? { deliverableId } : {}),
    });
  }

  async request(request: WorkbenchRequest): Promise<unknown> {
    return this.serialize(async () => {
      if (this.disposed) throw new Error('The workbench has been closed.');
      await this.load();
      const params = record(request.params ?? {});
      if (request.action === 'snapshot') return this.snapshot();
      if (request.action === 'document/export') {
        const document = this.state.documents.find(entry => entry.id === id(params.id));
        if (!document) throw new Error('Document no longer exists.');
        return { fileName: `${document.kind}-${document.id}.meridian-document.json`, content: JSON.stringify({ kind: 'meridian-studio-document', schemaVersion: 1, document }, null, 2) };
      }
      if (request.action === 'agent/export') {
        const agent = this.agent(id(params.id));
        const portable: PortableAgentDocument = {
          kind: 'meridian-portable-agent',
          schemaVersion: 1,
          agent: validateWorkbenchAgent(agent),
          memory: this.state.learning
            .filter((note) => note.agentId === agent.id && note.state === 'accepted')
            .map(({ title, content }) => ({ title, content })),
        };
        return {
          fileName: `${agent.id}.meridian-agent.json`,
          content: JSON.stringify(portable, null, 2),
        };
      }
      if (!this.loadedRoot) throw new Error('Open a workspace before making workbench changes.');
      const previous = structuredClone(this.state);
      try {
        const now = new Date().toISOString();
        switch (request.action) {
          case 'document/save': {
            const raw = record(params.document);
            const fields = documentFields(raw);
            const existing = raw.id === undefined ? undefined : this.state.documents.find(entry => entry.id === id(raw.id));
            if (raw.id !== undefined && !existing) throw new Error('Document no longer exists. Refresh before saving.');
            if (existing && raw.expectedVersion !== existing.version) throw new Error('This document changed in another view. Refresh before saving your changes.');
            if (existing && fields.kind !== existing.kind) throw new Error('A document cannot change its kind.');
            if (existing) this.archiveDocument(existing);
            const document: StudioDocument = { ...fields, id: existing?.id ?? randomUUID(), version: (existing?.version ?? 0) + 1, createdAt: existing?.createdAt ?? now, updatedAt: now };
            if (existing) this.state.documents[this.state.documents.indexOf(existing)] = document;
            else this.state.documents.unshift(document);
            break;
          }
          case 'document/import': {
            const raw = record(JSON.parse(string(params.content, 'Document JSON', 2_000_000)));
            if (raw.kind !== 'meridian-studio-document' || raw.schemaVersion !== 1) throw new Error('Expected a Meridian studio document, schema version 1.');
            this.state.documents.unshift({ ...documentFields(raw.document), id: randomUUID(), version: 1, createdAt: now, updatedAt: now });
            break;
          }
          case 'document/remove': {
            const existing = this.state.documents.find(entry => entry.id === id(params.id));
            if (!existing) throw new Error('Document no longer exists.');
            if (params.expectedVersion !== existing.version) throw new Error('Document changed. Refresh before removing it.');
            this.state.documents = this.state.documents.filter(entry => entry.id !== existing.id);
            this.state.documentRevisions = this.state.documentRevisions.filter(entry => entry.id !== existing.id);
            break;
          }
          case 'document/restore': {
            const existing = this.state.documents.find(entry => entry.id === id(params.id));
            if (!existing || existing.version !== params.expectedVersion) throw new Error('Document changed. Refresh before restoring it.');
            const old = this.state.documentRevisions.find(entry => entry.id === existing.id && entry.version === params.version);
            if (!old) throw new Error('Requested document revision is unavailable.');
            this.archiveDocument(existing);
            this.state.documents[this.state.documents.indexOf(existing)] = { ...structuredClone(old), version: existing.version + 1, updatedAt: now };
            break;
          }
          case 'agent/save': {
            const input = validateWorkbenchAgent(params.agent);
            const existing = this.state.agents.find((entry) => entry.id === input.id);
            if (
              existing &&
              this.state.runs.some(
                (run) => run.agentId === input.id && ['running', 'queued'].includes(run.state),
              )
            )
              throw new Error('Stop this agent before changing its configuration.');
            const agent: WorkbenchAgent = {
              ...input,
              mode: existing?.mode ?? 'learning',
              runtime: 'idle',
              learningState: 'waiting',
              createdAt: existing?.createdAt ?? now,
              updatedAt: now,
            };
            if (existing) this.state.agents[this.state.agents.indexOf(existing)] = agent;
            else this.state.agents.push(agent);
            break;
          }
          case 'agent/import': {
            const content = string(params.content, 'Portable agent JSON', 20_000_000);
            if (Buffer.byteLength(content, 'utf8') > 20_000_000)
              throw new Error('Portable agent JSON must be smaller than 20 MB.');
            const raw = record(JSON.parse(content));
            if (raw.kind !== 'meridian-portable-agent' || raw.schemaVersion !== 1)
              throw new Error('Expected a Meridian portable agent document, schema version 1.');
            const input = validateWorkbenchAgent(raw.agent);
            if (this.state.agents.some((entry) => entry.id === input.id))
              throw new Error(
                `Agent '${input.id}' already exists. Edit it or change the imported ID.`,
              );
            this.state.agents.push({
              ...input,
              mode: 'learning',
              runtime: 'idle',
              learningState: 'waiting',
              createdAt: now,
              updatedAt: now,
            });
            if (raw.memory !== undefined) {
              if (!Array.isArray(raw.memory))
                throw new Error('Portable memory must be a list of reviewable notes.');
              for (const entry of raw.memory) {
                const note = record(entry);
                this.state.learning.push({
                  id: randomUUID(),
                  agentId: input.id,
                  deliverableId: 'portable-import',
                  title: string(note.title, 'Memory title', 200),
                  content: string(note.content, 'Memory note', 40_000),
                  state: 'pending',
                  createdAt: now,
                  surface: 'memory',
                });
              }
            }
            break;
          }
          case 'agent/remove': {
            const agent = this.agent(id(params.id));
            for (const run of this.state.runs.filter((entry) => entry.agentId === agent.id))
              this.cancelRun(run, 'Agent removed by the user.');
            this.state.agents = this.state.agents.filter((entry) => entry.id !== agent.id);
            this.state.learning = this.state.learning.filter((note) => note.agentId !== agent.id);
            break;
          }
          case 'agent/mode': {
            const agent = this.agent(id(params.id));
            if (params.mode !== 'active' && params.mode !== 'learning')
              throw new Error('Mode must be active or learning.');
            agent.mode = params.mode;
            agent.updatedAt = now;
            if (agent.mode === 'learning')
              for (const run of this.state.runs.filter((entry) => entry.agentId === agent.id))
                this.cancelRun(run, 'Agent deactivated; moved to Learning.');
            break;
          }
          case 'agent/run': {
            const capability = this.capabilities();
            if (!capability.executionReady) throw new Error(capability.executionBlockedReason);
            this.queueRun(this.agent(id(params.id)), string(params.prompt, 'Task prompt', 40_000));
            break;
          }
          case 'run/cancel': {
            const run = this.state.runs.find((entry) => entry.id === id(params.id));
            if (!run) throw new Error('Run does not exist.');
            this.cancelRun(run, 'Cancelled by the user.');
            break;
          }
          case 'run/steer': {
            const run = this.state.runs.find(entry => entry.id === id(params.id));
            const handle = run && this.sessions.get(run.id);
            if (!run || run.state !== 'running' || !handle?.sessionId || !handle.acceptingSteering || handle.controller.signal.aborted) throw new Error('Choose a running workbench session that is accepting guidance. This task may be finishing.');
            if (!this.capabilities().executionReady) throw new Error(this.capabilities().executionBlockedReason);
            const message = string(params.message, 'Steering message', 20_000);
            if ((run.steering?.filter(entry => entry.state === 'queued').length ?? 0) >= 20) throw new Error('This run already has 20 queued steering messages. Wait for the next turn.');
            const result = await this.options.sidecar()!.request('steer.send', { sessionId: handle.sessionId, message }) as { accepted?: boolean; sequence?: number };
            if (!result.accepted || !Number.isSafeInteger(result.sequence)) throw new Error('The sidecar did not record the steering message.');
            run.steering ??= [];
            run.steering.push({ message, sequence: result.sequence!, state: 'queued', submittedAt: now });
            break;
          }
          case 'deliverable/save': {
            const title = string(params.title, 'Title', 200).trim();
            const brief = string(params.brief, 'Brief', 40_000);
            const existing = params.id === undefined ? undefined : this.deliverable(id(params.id));
            if (existing && existing.state !== 'draft')
              throw new Error(
                'Only draft deliverables can be edited. Create a new draft for another iteration.',
              );
            if (existing) {
              existing.title = title;
              existing.brief = brief;
              existing.updatedAt = now;
            } else
              this.state.deliverables.unshift({
                id: randomUUID(),
                title,
                brief,
                state: 'draft',
                agentIds: [],
                createdAt: now,
                updatedAt: now,
              });
            break;
          }
          case 'deliverable/dispatch': {
            const capability = this.capabilities();
            if (!capability.executionReady) throw new Error(capability.executionBlockedReason);
            const item = this.deliverable(id(params.id));
            if (item.state !== 'draft')
              throw new Error('Only a draft can be dispatched. Create a new draft to run again.');
            const agents = this.state.agents.filter((agent) => agent.mode === 'active');
            if (!agents.length)
              throw new Error('Activate at least one agent before dispatching a deliverable.');
            item.agentIds = agents.map((agent) => agent.id);
            item.state = 'running';
            item.updatedAt = now;
            for (const agent of agents)
              this.queueRun(
                agent,
                `${item.title}\n\n${item.brief}\n\nYour role: ${agent.role}. Work only within this brief and explain what you changed and verified.`,
                item.id,
              );
            break;
          }
          case 'deliverable/complete': {
            const item = this.deliverable(id(params.id));
            if (item.state !== 'review')
              throw new Error(
                'Review the completed agent turns before marking this deliverable complete.',
              );
            const feedback = string(params.feedback, 'Review feedback', 20_000);
            item.state = 'completed';
            item.feedback = feedback;
            item.updatedAt = now;
            for (const agent of this.state.agents.filter(
              (entry) => entry.mode === 'learning' && entry.trainable.includes('memory'),
            )) {
              this.state.learning.push({
                id: randomUUID(),
                agentId: agent.id,
                deliverableId: item.id,
                title: `Review: ${item.title}`,
                content: `Source deliverable: ${item.id}\n\nHuman feedback:\n${feedback}\n\nProposed memory: Apply this feedback when it is relevant to your role (${agent.role}). Review before accepting; this note does not modify policies, executable code, or model weights.`,
                state: 'pending',
                createdAt: now,
                surface: 'memory',
              });
            }
            break;
          }
          case 'learning/review': {
            const note = this.state.learning.find((entry) => entry.id === id(params.id));
            if (!note || note.state !== 'pending')
              throw new Error('This learning note is no longer awaiting review.');
            if (params.decision !== 'accepted' && params.decision !== 'dismissed')
              throw new Error('Learning decision must be accepted or dismissed.');
            if (
              params.decision === 'accepted' &&
              !this.agent(note.agentId).trainable.includes('memory')
            )
              throw new Error(
                'This agent freezes memory. Enable trainable memory before accepting a note.',
              );
            note.state = params.decision;
            note.reviewedAt = now;
            break;
          }
          default:
            throw new Error(`Unknown workbench action '${request.action}'.`);
        }
        this.state.revision++;
        await this.persist();
      } catch (error) {
        this.state = previous;
        // Cancellation is irreversible. Reflect stopped runs even when the
        // disk write failed; do not claim the process is still running.
        for (const run of this.state.runs)
          if (this.sessions.get(run.id)?.controller.signal.aborted)
            this.cancelRun(run, 'Agent stopped; state could not be saved.');
        throw error;
      }
      this.notify();
      void this.pump();
      return this.snapshot();
    });
  }

  /** Stop owned work immediately when trust/tier/connectivity changes. */
  async reconcile(): Promise<void> {
    return this.serialize(async () => {
      if (this.capabilities().executionReady) {
        this.notify();
        return;
      }
      for (const run of this.state.runs)
        this.cancelRun(
          run,
          this.capabilities().executionBlockedReason ?? 'Execution is unavailable.',
        );
      if (this.loadedRoot) {
        this.state.revision++;
        await this.persist();
      }
      this.notify();
    });
  }

  private async pump(): Promise<void> {
    if (this.pumping || this.disposed) return;
    this.pumping = true;
    try {
      while (!this.disposed) {
        const next = await this.serialize(async () => {
          const run = this.state.runs.find((entry) => entry.state === 'queued');
          if (!run) return undefined;
          if (!this.capabilities().executionReady || this.agent(run.agentId).mode !== 'active') {
            this.cancelRun(
              run,
              this.capabilities().executionBlockedReason ?? 'Agent is in Learning mode.',
            );
            this.state.revision++;
            await this.persist();
            this.notify();
            return null;
          }
          run.state = 'running';
          run.startedAt = new Date().toISOString();
          this.agent(run.agentId).lastRunAt = run.startedAt;
          this.state.revision++;
          await this.persist();
          this.notify();
          return structuredClone(run);
        });
        if (next === undefined) break;
        if (next === null) continue;
        await this.executeRun(next);
      }
    } catch (error) {
      this.options.onError?.(`Workbench execution stopped: ${(error as Error).message}`);
    } finally {
      this.pumping = false;
    }
  }

  private async executeRun(run: WorkbenchRun): Promise<void> {
    const controller = new AbortController();
    let stopReason: string | undefined;
    let failure: string | undefined;
    let unregister: (() => void) | undefined;
    let recordedSession: string | undefined;
    try {
      const agent = this.agent(run.agentId);
      const manifest = agentManifest(agent);
      const workspaceDir = this.options.workspaceDir()!;
      let policyText: string | undefined;
      for (const file of [
        path.join(workspaceDir, '.meridian', 'policy', 'acp-permissions.yaml'),
        ...(this.options.policyPaths ?? []),
      ]) {
        if (!file) continue;
        try {
          policyText = await fs.readFile(file, 'utf8');
          break;
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
        }
      }
      // A missing policy has no grants. Activation controls participation;
      // it never bypasses probation or elevates autonomy.
      const policy = parseAcpPermissionPolicy(
        policyText ?? 'version: 1\nadapters: {}',
        'ACP permission policy',
      );
      if (policy.errors.length) throw new Error(policy.errors.join('\n'));
      if (
        this.disposed ||
        this.state.runs.find((entry) => entry.id === run.id)?.state !== 'running'
      )
        return;
      if (!this.capabilities().executionReady)
        throw new Error(this.capabilities().executionBlockedReason);
      let permissionRecordingFailed = false;
      const gate = createPolicyGate({
        policy,
        adapter: manifest,
        adapterState: 'probation',
        humanApprover: async (request, context) => {
          if (
            permissionRecordingFailed ||
            this.disposed ||
            controller.signal.aborted ||
            !this.capabilities().executionReady
          )
            return { outcome: 'cancelled' };
          return this.options.humanApprover!(request, context);
        },
        sidecar: this.options.sidecar(),
        onRecordError: (message) => {
          permissionRecordingFailed = true;
          this.options.onError?.(message);
        },
      });
      const session = (this.options.launcher ?? launchAdapter)(
        { id: agent.id, tier: 'workspace', dir: workspaceDir, manifest },
        {
          workspaceDir,
          enabledTiers: this.options.enabledTiers(),
          approvePermission: async (request, context) => {
            if (this.disposed || controller.signal.aborted || !this.capabilities().executionReady)
              return { outcome: 'cancelled' };
            const decision = await gate(request, context);
            return permissionRecordingFailed ||
              this.disposed ||
              controller.signal.aborted ||
              !this.capabilities().executionReady
              ? { outcome: 'cancelled' }
              : decision;
          },
          onUpdate: (notification) => {
            const update = notification.update;
            if (update.sessionUpdate === 'agent_message_chunk' && update.content.type === 'text') {
              this.output.set(
                run.id,
                ((this.output.get(run.id) ?? '') + update.content.text).slice(0, 100_000),
              );
              this.notify();
            }
          },
        },
      );
      this.sessions.set(run.id, { session, controller });
      await session.start();
      if (controller.signal.aborted) return;
      const sessionId = await session.newSession(workspaceDir);
      if (controller.signal.aborted) return;
      const recorder = this.options.sidecar();
      if (!recorder) throw new Error('The sidecar disconnected before the session could be recorded.');
      await recorder.request('acp/sessionBegin', { agentId: agent.id, agentVersion: agent.version, sessionId, cwd: workspaceDir, startedAt: run.startedAt });
      recordedSession = sessionId;
      const handle = this.sessions.get(run.id);
      if (handle) handle.sessionId = sessionId;
      await this.serialize(async () => {
        const current = this.state.runs.find(entry => entry.id === run.id);
        if (current) current.sessionId = sessionId;
        if (handle) handle.acceptingSteering = true;
        this.state.revision++; await this.persist(); this.notify();
      });
      if (controller.signal.aborted) return;
      unregister = hostedSessionRegistry.register(sessionId, {
        halt: (reason) => {
          failure = `Governance halted this session: ${reason}`;
          controller.abort();
          session.stop();
        },
      });
      const memory = agent.trainable.includes('memory')
        ? this.state.learning
            .filter((note) => note.agentId === agent.id && note.state === 'accepted')
            .slice(-20)
            .map((note) => note.content)
            .join('\n\n')
        : '';
      const prompt = [
        agent.instructions && `Agent instructions:\n${agent.instructions}`,
        memory && `Human-reviewed memory (apply only where relevant):\n${memory}`,
        `Current task:\n${run.prompt}`,
      ]
        .filter(Boolean)
        .join('\n\n');
      stopReason = await session.prompt(sessionId, prompt, { signal: controller.signal });
      while (stopReason === 'end_turn' && !controller.signal.aborted && !this.disposed) {
        const followUp = await this.serialize(async () => {
          const current = this.state.runs.find(entry => entry.id === run.id);
          const messages = current?.steering?.filter(entry => entry.state === 'queued') ?? [];
          if (!messages.length || current?.state !== 'running') {
            if (handle) handle.acceptingSteering = false;
            return undefined;
          }
          for (const entry of messages) entry.state = 'sent';
          this.state.revision++; await this.persist(); this.notify();
          return messages.map(entry => `Human steering (ledger #${entry.sequence}):\n${entry.message}`).join('\n\n');
        });
        if (!followUp || controller.signal.aborted) break;
        stopReason = await session.prompt(sessionId, followUp, { signal: controller.signal });
      }
    } catch (error) {
      failure = error instanceof Error ? error.message : String(error);
    } finally {
      const handle = this.sessions.get(run.id);
      if (handle) handle.acceptingSteering = false;
      unregister?.();
      this.sessions.get(run.id)?.session.stop();
      this.sessions.delete(run.id);
      if (recordedSession) {
        try {
          const recorder = this.options.sidecar();
          if (!recorder) throw new Error('The sidecar disconnected before the session end could be recorded.');
          await recorder.request('acp/sessionEnd', { sessionId: recordedSession, agentId: run.agentId, stopReason: controller.signal.aborted ? 'cancelled' : stopReason ?? 'failed', endedAt: new Date().toISOString() });
        } catch (error) { failure ??= (error as Error).message; this.options.onError?.(failure); }
      }
      await this.serialize(async () => {
        const current = this.state.runs.find((entry) => entry.id === run.id);
        if (!current) return;
        current.output = this.output.get(run.id) ?? '';
        this.output.delete(run.id);
        if (current.state === 'running') {
          current.state = controller.signal.aborted
            ? 'cancelled'
            : failure
              ? 'failed'
              : stopReason === 'cancelled'
                ? 'cancelled'
                : stopReason === 'end_turn'
                  ? 'completed'
                  : 'failed';
          current.finishedAt = new Date().toISOString();
          if (failure) current.error = failure;
          else if (current.state === 'failed')
            current.error = `The agent stopped before completing the task: ${stopReason ?? 'no stop reason'}.`;
          if (stopReason) current.stopReason = stopReason;
        }
        this.settleDeliverable(current.deliverableId);
        this.state.revision++;
        await this.persist();
        this.notify();
      });
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    clearTimeout(this.changeTimer);
    for (const run of this.state.runs) this.cancelRun(run, 'Workbench closed.');
    this.listeners.clear();
    if (this.loadedRoot)
      void this.serialize(async () => {
        this.state.revision++;
        await this.persist();
      }).catch((error: Error) => this.options.onError?.(error.message));
  }
}
