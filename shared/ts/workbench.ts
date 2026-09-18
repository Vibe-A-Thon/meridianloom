import type { StudioDocument, StudioDocumentInput } from "./studio";
import type {
  IntegrationConnection,
  IntegrationConnectionInput,
  IntegrationReadResult,
} from "./integrations";
/** Extension-host workbench state. This channel does not require the Python sidecar. */
export type AgentMode = "active" | "learning";
export type AgentPermission =
  | "read"
  | "edit"
  | "delete"
  | "move"
  | "execute"
  | "search"
  | "think"
  | "unknown"
  | "other";
export type LearningSurface =
  | "policy"
  | "rules"
  | "memory"
  | "skills"
  | "calibration";

/**
 * The nine SDLC phases of `vision.md` §3. An agent is tagged with the phases
 * it may take part in; a deliverable dispatch convenes, for each phase, only
 * the active agents tagged for it. The set is fixed here because `D8` leaves
 * the phase set configurable from policy and the workbench must not fork it.
 */
export const SDLC_PHASES = [
  "intake",
  "design",
  "plan",
  "build",
  "verify",
  "security",
  "review",
  "release",
  "operate",
] as const;
export type SdlcPhase = (typeof SDLC_PHASES)[number];

export const SDLC_PHASE_LABELS: Readonly<Record<SdlcPhase, string>> = {
  intake: "Intake & Analysis",
  design: "Architecture & Design",
  plan: "Planning & Decomposition",
  build: "Implementation",
  verify: "Verification",
  security: "Security & Compliance",
  review: "Review & Integration",
  release: "Release",
  operate: "Operate & Maintain",
};

export interface WorkbenchAgentInput {
  id: string;
  name: string;
  role: string;
  description: string;
  vendor: string;
  version: string;
  command: string;
  args: string[];
  instructions: string;
  permissions: AgentPermission[];
  trainable: LearningSurface[];
  /** SDLC phases this agent may be convened for (`vision.md` §3). */
  phases: SdlcPhase[];
  /** Skills bound to this agent at run time (`vision.md` §2.4 — identity is data). */
  skillIds: string[];
  /** Instruction documents this agent works from (`vision.md` §2.8 property 4). */
  instructionIds: string[];
  /**
   * Tool connections this agent may read from. Bound explicitly, because an
   * agent that can see your production cluster should be one you chose to
   * give that to.
   */
  integrationIds: string[];
}

/**
 * A skill pack in the `SKILL.md` shape: YAML frontmatter plus a Markdown
 * body. Binding a skill to a role agent is what makes it a stack agent.
 */
export interface WorkbenchSkillInput {
  id: string;
  name: string;
  summary: string;
  version: string;
  /** Free-form stack/domain tags used for discovery. */
  tags: string[];
  /** The SKILL.md body: conventions, layout, build/test invocations, checklist. */
  body: string;
}

export interface WorkbenchSkill extends WorkbenchSkillInput {
  /** Disabled skills stay in the catalogue but bind to no agent. */
  enabled: boolean;
  /**
   * Where it came from, so a packaged import is never mistaken for authored
   * work — and so a shipped one is never mistaken for either. `builtin`
   * entries arrive with the extension; they are ordinary records in every
   * other respect, and editing, disabling or deleting one is allowed.
   */
  source: "authored" | "imported" | "builtin";
  createdAt: string;
  updatedAt: string;
}

/** An instruction file — `AGENTS.md`, `CONVENTIONS.md` and their kin. */
export interface WorkbenchInstructionInput {
  id: string;
  name: string;
  summary: string;
  /** Precedence tier, per the Instruction Library (`FR-M7-14`…`16`). */
  scope: "adapter" | "workspace" | "user" | "organisation";
  body: string;
}

export interface WorkbenchInstruction extends WorkbenchInstructionInput {
  enabled: boolean;
  source: "authored" | "imported" | "builtin";
  createdAt: string;
  updatedAt: string;
}

export interface WorkbenchAgent extends WorkbenchAgentInput {
  /**
   * How this agent got here. Optional because state files written before
   * the shipped library existed have no such field, and an agent with no
   * recorded provenance is an authored one by definition.
   */
  source?: "authored" | "imported" | "builtin";
  mode: AgentMode;
  runtime: "idle" | "running";
  learningState: "waiting" | "review";
  createdAt: string;
  updatedAt: string;
  lastRunAt?: string;
}

export interface WorkbenchRun {
  id: string;
  agentId: string;
  agentName: string;
  deliverableId?: string;
  /**
   * The SDLC phase this agent was convened for, when the deliverable was
   * dispatched by phase. Absent for an ad-hoc run, and for a dispatch where
   * no agent carried a phase tag.
   */
  phase?: SdlcPhase;
  /**
   * The full briefing the agent received — brief, role, phase, instruction
   * files, skills, connected systems and accepted memory. Recorded verbatim,
   * because a run you cannot reproduce is not evidence.
   */
  prompt: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  startedAt: string;
  finishedAt?: string;
  stopReason?: string;
  error?: string;
  output?: string;
  sessionId?: string;
  steering?: {
    message: string;
    sequence: number;
    state: "queued" | "sent";
    submittedAt: string;
  }[];
}

export interface WorkbenchDeliverable {
  id: string;
  title: string;
  brief: string;
  state: "draft" | "running" | "review" | "completed" | "failed";
  agentIds: string[];
  createdAt: string;
  updatedAt: string;
  feedback?: string;
}

export interface LearningArtifact {
  id: string;
  agentId: string;
  deliverableId: string;
  title: string;
  content: string;
  state: "pending" | "accepted" | "dismissed";
  createdAt: string;
  reviewedAt?: string;
  /** These are reviewable memory notes, never model-weight training. */
  surface: "memory";
}

/**
 * How to launch one real ACP agent. Meridian does not bundle an AI; it
 * governs one you already have, so these say how each is started and the
 * user supplies their own account. No credential is ever present here.
 */
export interface RuntimePreset {
  id: string;
  name: string;
  vendor: string;
  command: string;
  args: string[];
  /** What must already be installed for the command to resolve. */
  requires: string;
  /** How the user authenticates: with that agent, never with Meridian. */
  auth: string;
  docs: string;
}

export interface WorkbenchSnapshot {
  revision: number;
  agents: WorkbenchAgent[];
  /** Shipped ACP runtimes an agent can be bound to. Read-only. */
  runtimes?: RuntimePreset[];
  skills: WorkbenchSkill[];
  instructions: WorkbenchInstruction[];
  /** Configured tool connections. Secrets are never present here. */
  integrations: IntegrationConnection[];
  deliverables: WorkbenchDeliverable[];
  runs: WorkbenchRun[];
  learning: LearningArtifact[];
  documents?: StudioDocument[];
  documentRevisions?: StudioDocument[];
  capabilities: {
    workspaceOpen: boolean;
    trusted: boolean;
    governorEnabled: boolean;
    executionReady: boolean;
    executionBlockedReason?: string;
  };
}

/** Portable declared launch configuration; credentials and run history are excluded. */
export interface PortableAgentDocument {
  kind: "meridian-portable-agent";
  schemaVersion: 1;
  agent: WorkbenchAgentInput;
  memory?: { title: string; content: string }[];
  /** Skills and instructions travel with the agent so it is portable whole. */
  skills?: WorkbenchSkillInput[];
  instructions?: WorkbenchInstructionInput[];
}

/**
 * What an imported package produced, so the interface can report exactly what
 * was created rather than claiming a silent success.
 */
export interface ImportReport {
  agents: string[];
  skills: string[];
  instructions: string[];
  /** Entries the reader recognised but deliberately skipped, with the reason. */
  skipped: { path: string; reason: string }[];
  format: "markdown" | "zip" | "json";
}

export interface WorkbenchActionMap {
  "document/save": {
    params: { document: StudioDocumentInput };
    result: WorkbenchSnapshot;
  };
  "document/remove": {
    params: { id: string; expectedVersion: number };
    result: WorkbenchSnapshot;
  };
  "document/export": {
    params: { id: string };
    result: { fileName: string; content: string };
  };
  "document/import": { params: { content: string }; result: WorkbenchSnapshot };
  "document/restore": {
    params: { id: string; version: number; expectedVersion: number };
    result: WorkbenchSnapshot;
  };
  snapshot: { params: Record<string, never>; result: WorkbenchSnapshot };
  "agent/save": {
    params: { agent: WorkbenchAgentInput };
    result: WorkbenchSnapshot;
  };
  "agent/remove": { params: { id: string }; result: WorkbenchSnapshot };
  "agent/mode": {
    params: { id: string; mode: AgentMode };
    result: WorkbenchSnapshot;
  };
  /**
   * Point an agent at one of the shipped ACP runtimes. A convenience over
   * typing the same command by hand: it grants nothing and carries no
   * credential.
   */
  "agent/bindRuntime": {
    params: { id: string; runtimeId: string };
    result: WorkbenchSnapshot;
  };
  "agent/import": { params: { content: string }; result: WorkbenchSnapshot };
  "agent/export": {
    params: { id: string };
    result: { fileName: string; content: string };
  };
  /**
   * Ingest an agent, skill or instruction package the user supplies as a
   * Markdown document or a ZIP archive. `contentBase64` carries the archive
   * bytes; `content` carries Markdown or JSON text. Exactly one is required.
   */
  "agent/importPackage": {
    params: { fileName: string; content?: string; contentBase64?: string };
    result: { snapshot: WorkbenchSnapshot; report: ImportReport };
  };
  /** Tag an agent to SDLC phases and bind its skills and instructions. */
  "agent/assign": {
    params: {
      id: string;
      phases?: SdlcPhase[];
      skillIds?: string[];
      instructionIds?: string[];
      integrationIds?: string[];
    };
    result: WorkbenchSnapshot;
  };
  "skill/save": {
    params: { skill: WorkbenchSkillInput };
    result: WorkbenchSnapshot;
  };
  "skill/remove": { params: { id: string }; result: WorkbenchSnapshot };
  "skill/toggle": {
    params: { id: string; enabled: boolean };
    result: WorkbenchSnapshot;
  };
  "skill/export": {
    params: { id: string };
    result: { fileName: string; content: string };
  };
  "instruction/save": {
    params: { instruction: WorkbenchInstructionInput };
    result: WorkbenchSnapshot;
  };
  "instruction/remove": { params: { id: string }; result: WorkbenchSnapshot };
  "instruction/toggle": {
    params: { id: string; enabled: boolean };
    result: WorkbenchSnapshot;
  };
  "instruction/export": {
    params: { id: string };
    result: { fileName: string; content: string };
  };
  /**
   * Save a tool connection. `secrets` travels one way: it is written to the
   * OS keychain and never appears in a snapshot.
   */
  "integration/save": {
    params: { connection: IntegrationConnectionInput };
    result: WorkbenchSnapshot;
  };
  "integration/remove": { params: { id: string }; result: WorkbenchSnapshot };
  "integration/toggle": {
    params: { id: string; enabled: boolean };
    result: WorkbenchSnapshot;
  };
  /** Actually reach the system and report what answered. */
  "integration/probe": {
    params: { id: string };
    result: WorkbenchSnapshot;
  };
  /** Run one read operation against a connected system. Reads only. */
  "integration/read": {
    params: { id: string; operationId: string };
    result: IntegrationReadResult;
  };
  "agent/run": {
    params: { id: string; prompt: string };
    result: WorkbenchSnapshot;
  };
  "run/cancel": { params: { id: string }; result: WorkbenchSnapshot };
  "run/steer": {
    params: { id: string; message: string };
    result: WorkbenchSnapshot;
  };
  "deliverable/save": {
    params: { id?: string; title: string; brief: string };
    result: WorkbenchSnapshot;
  };
  "deliverable/dispatch": {
    params: {
      id: string;
      expectedBriefUpdatedAt?: string;
      expectedTeam?: Array<{ id: string; updatedAt: string }>;
    };
    result: WorkbenchSnapshot;
  };
  "deliverable/complete": {
    params: { id: string; feedback: string };
    result: WorkbenchSnapshot;
  };
  "learning/review": {
    params: { id: string; decision: "accepted" | "dismissed" };
    result: WorkbenchSnapshot;
  };
  /**
   * FR-M34-03 (MV3-T02): fetch the ACP Registry index.
   *
   * An action, never a subscription and never part of opening the
   * workbench. This is the only thing in the product that reaches a network
   * Meridian does not own, and it happens because somebody asked.
   */
  "registry/browse": { params: Record<string, never>; result: RegistryBrowseResult };
  /**
   * FR-M34-03, FR-M44-03: install a listed agent, pinned, into probation.
   */
  "registry/install": { params: { id: string }; result: RegistryInstallResult };
  /**
   * FR-M4 (audit TASK-301): the six canonical loops over the Orchestra tier.
   * Every action is ledger-recorded by the sidecar; replay is the FR-M4-07
   * modified-state fork and never counted as live work.
   */
  "loop.start": {
    params: {
      loopId: string;
      storyId: string;
      kind: "L1-micro" | "L2-task" | "L3-phase" | "L4-delivery" | "L5-learning" | "L6-organisation";
    };
    result: { runId: string; status: string; iterations: number; checkpointed: boolean };
  };
  "loop.status": {
    params: { loopId: string };
    result: { loopId: string; kind: string; state: string; iteration: number };
  };
  "loop.stop": {
    params: { loopId: string; reason?: string };
    result: { stopped: boolean; was: string };
  };
  "loop.resume": {
    params: { loopId: string };
    result: { status: string; iteration: number };
  };
  "loop.replay": {
    params: { loopId: string; stateOverrides: Record<string, unknown> };
    result: { forkRunId: string; status: string };
  };
  /**
   * FR-M31 (audit TASK-305): adapter discovery and hot-plug lifecycle.
   * Plug admits to probation; promote gates probation -> active; unplug
   * retires with in-flight work checkpointed by the sidecar.
   */
  "adapters/discover": {
    params: { roots?: string[] };
    result: {
      adapters: { id: string; version: string; valid: boolean; errors: string[] }[];
      states: Record<string, string>;
    };
  };
  "adapters/plug": {
    params: { folder: string };
    result: { id: string; valid: boolean; state: string };
  };
  "adapters/unplug": {
    params: { id: string; inflight?: Record<string, unknown> };
    result: { retired: boolean; checkpointed: boolean };
  };
  "adapters/promote": {
    params: { id: string };
    result: { state: string };
  };
  /* The remaining Orchestra/F4+ surfaces (audits TASK-302…309) share one
   * shape discipline: params and results mirror shared/schema/methods.json
   * exactly — the webview never invents a field the sidecar does not send. */
  "router/dependencyRatio": {
    params: {
      agentId?: string;
      phase?: string;
      storyId?: string;
      actionClass?: string;
      ceiling?: number;
    };
    result: {
      modelCalls: number;
      engineExecutions: number;
      ratio: number | null;
      ceiling: number | null;
      breached: boolean | null;
    };
  };
  "memory/retrieve": {
    params: { agentId: string; queryTerms: string[]; budgetChars: number; tiers?: string[] };
    result: { included: { entryId: string; subject: string; digest: string }[]; cut: string[] };
  };
  "memory/write": {
    params: {
      entry: {
        tier: "procedural" | "semantic" | "episodic";
        subject: string;
        content: string;
        author: string;
        confidence: number;
        origin: string;
        pinned?: boolean;
        source?: string;
      };
      actorIsHuman?: boolean;
    };
    result: { written: boolean; reason: string | null };
  };
  "comprehension/gate": {
    params: { path: string };
    result: { allowed: boolean; path: string; reason: string; record: Record<string, unknown> };
  };
  "queue/enqueue": {
    params: { story: { storyId: string; priority: number; tenantId: string; dependencies?: string[] } };
    result: { enqueued: boolean };
  };
  "queue/tick": { params: Record<string, never>; result: { admitted: string[] } };
  "issues/record": {
    params: { agentId: string; severity: "info" | "warning" | "critical"; description: string; storyId: string };
    result: { sequence: number };
  };
  "annotations/add": {
    params: { targetSeq: number; author: string; text: string; bookmark?: boolean };
    result: { sequence: number };
  };
  "decisions/gate": {
    params: {
      testsPassed: boolean;
      scansPassed: boolean;
      approvals: string[];
      changeClass: string;
      ablations?: number[];
    };
    result: { passed: boolean };
  };
  "trainer/train": {
    params: { openPhases: string[] };
    result: { ran: boolean; refusedReason: string | null };
  };
  "simulation/timeControl": {
    params: { action: "pause" | "step" | "play" | "jump"; rate?: number; sequence?: number };
    result: { position: number; paused: boolean };
  };
  "golden/run": {
    params: { folder: string };
    result: { storyId: string; ok: boolean; ledgerRoot: string; expectedRoot: string; entries: number };
  };
}

/**
 * One ACP Registry listing, as the interface needs it — `FR-M34-03`.
 *
 * A projection of the registry's own entry, not a pass-through. The index is
 * untrusted input: what crosses into the interface is a fixed set of fields
 * with known types, so a field nobody expected cannot arrive and be
 * rendered. Nothing here is executable and nothing here is executed.
 */
export interface RegistryListingEntry {
  id: string;
  name: string;
  version: string;
  description: string;
  /** Who publishes it, as the registry states. A claim, not a verification. */
  authors: string[];
  license: string;
  website: string;
  /** How it would be launched: `npx`, `uvx`, or a platform binary. */
  distributions: string[];
  /**
   * FR-M44-01: whether installing this would yield a verifiable agent
   * identity. `npx`/`uvx` entries fetch their package at launch, so the
   * answer is no and the surface must say so before the install, not after.
   */
  identityVerifiable: boolean;
}

/**
 * `B2`: the five states of the registry, each rendered differently, because
 * an operator acts on each differently. `notice` carries the one sentence
 * that says what happened and what to do.
 */
export type RegistryState =
  | "idle"
  | "fresh"
  | "cached-stale"
  | "unreachable"
  | "malformed";

export interface RegistryBrowseResult {
  state: RegistryState;
  entries: RegistryListingEntry[];
  registryUrl: string;
  fetchedAt?: string;
  notice?: string;
}

export interface RegistryInstallResult {
  ok: boolean;
  errors: string[];
  installed?: {
    id: string;
    /** Where it landed, so a person can go and look at it. */
    dir: string;
    /** FR-M44-03: the content digest recorded at install. */
    pinDigest?: string;
    /**
     * FR-M15-03/05: every install enters probation at `suggest`, with the
     * same read/search/think floor an imported agent gets. There is no
     * registry fast path.
     */
    permissions: AgentPermission[];
  };
  snapshot: WorkbenchSnapshot;
}

export type WorkbenchAction = keyof WorkbenchActionMap;
export interface WorkbenchRequest {
  action: WorkbenchAction;
  params?: unknown;
}
export type WorkbenchExecute = <A extends WorkbenchAction>(
  action: A,
  params: WorkbenchActionMap[A]["params"],
) => Promise<WorkbenchActionMap[A]["result"]>;
