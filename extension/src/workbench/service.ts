import { promises as fs } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { TierName } from "../../../shared/ts/bus-types";
import type {
  ImportReport,
  LearningArtifact,
  LearningSurface,
  PortableAgentDocument,
  RegistryBrowseResult,
  RegistryInstallResult,
  RegistryListingEntry,
  SdlcPhase,
  WorkbenchAgent,
  WorkbenchAgentInput,
  WorkbenchDeliverable,
  WorkbenchInstruction,
  WorkbenchInstructionInput,
  WorkbenchRequest,
  WorkbenchRun,
  WorkbenchSkill,
  WorkbenchSkillInput,
  WorkbenchSnapshot,
} from "../../../shared/ts/workbench";
import { SDLC_PHASES } from "../../../shared/ts/workbench";
import type {
  IntegrationConnection,
  IntegrationConnectionInput,
  IntegrationReadResult,
} from "../../../shared/ts/integrations";
import { integrationById } from "../../../shared/ts/integrations";
import {
  defaultTransport,
  probeIntegration,
  readIntegration,
  type IntegrationTransport,
} from "./integrations";
import { composeBriefing, convene } from "./briefing";
import {
  HostedSteerController,
  NotHostedSessionError,
} from "../governance/steer";
import { parsePackage, slugify } from "./packages";
import {
  validateAdapterManifest,
  type AdapterManifest,
} from "../adapters/manifest";
import {
  launchAdapter,
  type AdapterSession,
  type LaunchOptions,
} from "../adapters/launch";
import type { LaunchTarget } from "../adapters/launch";
import {
  noteAgentIdentity,
  type AgentIdentity,
} from "../adapters/identity";
import { verifyAdapterPin } from "../adapters/pinning";
import {
  AcpRegistrySource,
  type RegistryEntry,
  type RegistryStatus,
} from "../adapters/registry-source";
import { DEFAULT_IMPORT_PERMISSIONS } from "./packages";
import {
  createPolicyGate,
  type PolicyGateSidecar,
} from "../adapters/permission-gate";
import { parseAcpPermissionPolicy } from "../adapters/policy";
import type { PermissionApprover } from "../acp/client";
import { hostedSessionRegistry } from "../governance/session-registry";
import {
  STUDIO_DOCUMENT_KINDS,
  type StudioDocument,
} from "../../../shared/ts/studio";
import {
  loadBuiltinLibrary,
  planSeed,
  type RuntimePreset,
} from "./library";

interface StoredState {
  schemaVersion: 1;
  revision: number;
  /**
   * Every library entry this workspace has ever been offered, as
   * `kind:id`. Recorded rather than inferred from what is present, because
   * "not present" cannot distinguish *never seeded* from *seeded and then
   * deleted*, and reseeding a deleted entry would make the delete button a
   * suggestion. Absent in state files written before the shipped library.
   */
  seededBuiltins?: string[];
  agents: WorkbenchAgent[];
  skills: WorkbenchSkill[];
  instructions: WorkbenchInstruction[];
  integrations: IntegrationConnection[];
  deliverables: WorkbenchDeliverable[];
  runs: WorkbenchRun[];
  learning: LearningArtifact[];
  documents: StudioDocument[];
  documentRevisions: StudioDocument[];
}

export interface WorkbenchServiceOptions {
  /**
   * The installed extension directory, used to find the shipped library.
   * Optional: tests that do not care about it omit it and get the empty
   * catalogues they had before.
   */
  extensionPath?: string;
  workspaceDir(): string | undefined;
  /**
   * FR-M34-03 (MV3-T02): the ACP Registry client. Injected so tests never
   * touch a network, and lazily constructed in production so opening a
   * workspace builds nothing that could fetch.
   */
  registry?: (workspaceDir: string) => AcpRegistrySource;
  trusted(): boolean;
  enabledTiers(): readonly TierName[];
  sidecar(): PolicyGateSidecar | undefined;
  humanApprover?: PermissionApprover;
  /** Bundled policy/acp-permissions.yaml, after the workspace override. */
  policyPaths?: readonly string[];
  onError?: (message: string) => void;
  /** Tests inject a conformant ACP session; production uses launchAdapter. */
  launcher?: (
    adapter: LaunchTarget,
    options: LaunchOptions,
  ) => AdapterSession;
  /**
   * The OS keychain, for integration credentials. Absent in tests that do not
   * exercise integrations; when absent, saving a secret is refused rather
   * than silently written to the workspace.
   */
  secrets?: {
    get(key: string): Thenable<string | undefined> | Promise<string | undefined>;
    store(key: string, value: string): Thenable<void> | Promise<void>;
    delete(key: string): Thenable<void> | Promise<void>;
  };
  /** Injectable so integration reads are testable without a network. */
  transport?: IntegrationTransport;
}

function blankState(): StoredState {
  return {
    schemaVersion: 1,
    revision: 0,
    agents: [],
    skills: [],
    instructions: [],
    integrations: [],
    deliverables: [],
    runs: [],
    learning: [],
    documents: [],
    documentRevisions: [],
  };
}
/**
 * FR-M44-01 read ahead of the install: `npx` and `uvx` fetch the agent
 * package at launch, so an agent installed from such an entry can never have
 * a verifiable identity. Saying so on the listing — before the install —
 * is the difference between a limitation and a surprise.
 */
/**
 * This host in the registry's platform vocabulary (FORMAT.md:
 * `darwin-aarch64`, `linux-x86_64`, `windows-x86_64`, …).
 */
function registryPlatformKey(): string {
  const os =
    process.platform === "win32"
      ? "windows"
      : process.platform === "darwin"
        ? "darwin"
        : "linux";
  const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
  return `${os}-${arch}`;
}

function projectRegistryEntry(entry: RegistryEntry): RegistryListingEntry {
  const distributions = Object.keys(entry.distribution ?? {});
  return {
    id: entry.id,
    name: entry.name,
    version: entry.version,
    description: entry.description ?? "",
    authors: [...(entry.authors ?? [])],
    license: entry.license ?? "",
    website: entry.website ?? entry.repository ?? "",
    distributions,
    identityVerifiable: distributions.includes("binary"),
  };
}

/** The one sentence a person acts on, per state (`B2`). */
function registryNotice(status: RegistryStatus): string | undefined {
  if (status.state === "idle") return status.detail;
  if (status.state === "fresh") return undefined;
  return status.warning;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Expected an object.");
  return value as Record<string, unknown>;
}
function string(
  value: unknown,
  label: string,
  max: number,
  allowEmpty = false,
): string {
  if (
    typeof value !== "string" ||
    value.length > max ||
    (!allowEmpty && !value.trim()) ||
    value.includes("\0")
  ) {
    throw new Error(
      `${label} must be ${allowEmpty ? "text" : "non-empty text"} of at most ${max} characters.`,
    );
  }
  return value;
}
function id(value: unknown): string {
  const result = string(value, "ID", 100);
  if (!/^[a-z0-9][a-z0-9-]*$/.test(result))
    throw new Error("ID must contain lowercase letters, digits, and dashes.");
  return result;
}
function list(value: unknown, label: string, max = 100): string[] {
  if (!Array.isArray(value) || value.length > max)
    throw new Error(`${label} must be a list of at most ${max} entries.`);
  return value.map((entry) =>
    string(entry, label, 4_000, label === "Arguments"),
  );
}

function documentFields(
  value: unknown,
): Pick<StudioDocument, "kind" | "title" | "body" | "tags"> {
  const raw = record(value);
  if (!(STUDIO_DOCUMENT_KINDS as readonly unknown[]).includes(raw.kind))
    throw new Error("Unknown studio document kind.");
  return {
    kind: raw.kind as StudioDocument["kind"],
    title: string(raw.title, "Document title", 200).trim(),
    body: string(raw.body, "Document body", 250_000, true),
    tags: list(raw.tags, "Document tags", 30).map((tag) =>
      string(tag, "Tag", 80).trim(),
    ),
  };
}

/** The existing ACP adapter schema remains the authoritative launch validator. */
export function agentManifest(agent: WorkbenchAgentInput): AdapterManifest {
  const parsed = validateAdapterManifest(
    {
      adapter: {
        id: agent.id,
        version: agent.version,
        provenance: "custom",
        vendor: agent.vendor,
      },
      acp: { command: agent.command, args: agent.args, env: {} },
      role: { fills: [agent.role] },
      permissions: { allow: agent.permissions },
      learning: {
        trainable: agent.trainable,
        frozen: ["policy", "rules", "memory", "skills", "calibration"].filter(
          (surface) => !agent.trainable.includes(surface as never),
        ),
      },
      governance: { autonomy_tier: "suggest" },
    },
    "Agent configuration",
  );
  if (!parsed.ok) throw new Error(parsed.errors.join("\n"));
  return parsed.manifest;
}

/**
 * Emit YAML frontmatter plus a Markdown body. Values are written as quoted
 * scalars or flow sequences so a name containing a colon cannot break the
 * document it describes.
 */
function frontmatterDocument(
  data: Record<string, string | string[]>,
  body: string,
): string {
  const quote = (value: string) => `"${value.replace(/(["\\])/g, "\\$1")}"`;
  const lines = Object.entries(data)
    .filter(([, value]) => (Array.isArray(value) ? value.length : value !== ""))
    .map(([key, value]) =>
      Array.isArray(value)
        ? `${key}: [${value.map(quote).join(", ")}]`
        : `${key}: ${quote(value)}`,
    );
  return `---\n${lines.join("\n")}\n---\n\n${body}\n`;
}

/**
 * Where one credential lives in the OS keychain. Namespaced by connection so
 * two Jira sites, or a staging and a production cluster, never collide.
 */
function secretKey(connectionId: string, field: string): string {
  return `meridianLoom.integration.${connectionId}.${field}`;
}

/** SDLC phase tags, closed to the nine of `vision.md` §3. */
function phaseList(value: unknown): SdlcPhase[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > SDLC_PHASES.length)
    throw new Error("Phases must be a list of SDLC phase identifiers.");
  const seen = new Set<SdlcPhase>();
  for (const entry of value) {
    if (typeof entry !== "string" || !(SDLC_PHASES as readonly string[]).includes(entry))
      throw new Error(`'${String(entry)}' is not one of the nine SDLC phases.`);
    seen.add(entry as SdlcPhase);
  }
  return [...seen];
}

export function validateWorkbenchSkill(value: unknown): WorkbenchSkillInput {
  const raw = record(value);
  return {
    id: id(raw.id),
    name: string(raw.name, "Skill name", 120).trim(),
    summary: string(raw.summary, "Summary", 500, true),
    version: string(raw.version, "Version", 40),
    tags: list(raw.tags, "Tags", 20),
    body: string(raw.body, "Skill body", 200_000, true),
  };
}

export function validateWorkbenchInstruction(
  value: unknown,
): WorkbenchInstructionInput {
  const raw = record(value);
  const scope = string(raw.scope, "Scope", 20);
  if (!["adapter", "workspace", "user", "organisation"].includes(scope))
    throw new Error(
      "Instruction scope must be adapter, workspace, user or organisation.",
    );
  return {
    id: id(raw.id),
    name: string(raw.name, "Instruction name", 120).trim(),
    summary: string(raw.summary, "Summary", 500, true),
    scope: scope as WorkbenchInstructionInput["scope"],
    body: string(raw.body, "Instruction body", 200_000, true),
  };
}

/**
 * A tool connection, minus its credentials. `secrets` is accepted on the way
 * in and immediately handed to the keychain; it is never part of the stored
 * or returned shape, so it is validated separately by the save handler.
 */
export function validateIntegrationConnection(
  value: unknown,
): IntegrationConnectionInput {
  const raw = record(value);
  const integrationId = string(raw.integrationId, "Integration", 60);
  const definition = integrationById(integrationId);
  if (!definition)
    throw new Error(`'${integrationId}' is not an integration Meridian knows about.`);
  const config: Record<string, string> = {};
  const rawConfig = raw.config === undefined ? {} : record(raw.config);
  for (const field of definition.fields) {
    if (field.kind === "secret") continue;
    const supplied = rawConfig[field.key];
    const text = supplied === undefined ? "" : string(supplied, field.label, 2_000, true);
    if (field.required && !text.trim())
      throw new Error(`${definition.name} needs ${field.label}.`);
    config[field.key] = text.trim();
  }
  // A URL field that is set must be http(s): a connection is a network reach,
  // and file:// or a shell-ish string has no business being dialled.
  for (const field of definition.fields)
    if (field.kind === "url" && config[field.key] && !/^https?:\/\//i.test(config[field.key]))
      throw new Error(`${field.label} must be an http or https URL.`);
  return {
    id: id(raw.id),
    integrationId,
    name: string(raw.name, "Connection name", 120).trim(),
    config,
  };
}

export function validateWorkbenchAgent(value: unknown): WorkbenchAgentInput {
  const raw = record(value);
  const agent: WorkbenchAgentInput = {
    id: id(raw.id),
    name: string(raw.name, "Name", 120).trim(),
    role: string(raw.role, "Role", 120).trim(),
    description: string(raw.description, "Description", 2_000, true),
    vendor: string(raw.vendor, "Vendor", 120, true),
    version: string(raw.version, "Version", 40),
    command: string(raw.command, "Executable", 2_000).trim(),
    args: list(raw.args, "Arguments"),
    instructions: string(raw.instructions, "Instructions", 40_000, true),
    permissions: list(
      raw.permissions,
      "Permissions",
      9,
    ) as WorkbenchAgentInput["permissions"],
    trainable: list(
      raw.trainable,
      "Trainable surfaces",
      5,
    ) as WorkbenchAgentInput["trainable"],
    // Absent on agents stored before phase tagging existed: an older
    // state.json must keep loading, so these default to empty rather than
    // failing validation.
    phases: phaseList(raw.phases),
    skillIds: raw.skillIds === undefined ? [] : list(raw.skillIds, "Skills", 100),
    instructionIds:
      raw.instructionIds === undefined
        ? []
        : list(raw.instructionIds, "Instructions", 100),
    integrationIds:
      raw.integrationIds === undefined
        ? []
        : list(raw.integrationIds, "Integrations", 100),
  };
  // Secrets belong in the launched agent's environment/credential store. This
  // service intentionally offers no environment-value persistence surface.
  if (
    agent.args.some((arg) =>
      /(?:api[-_]?key|access[-_]?token|password|secret)\s*=/i.test(arg),
    )
  ) {
    throw new Error(
      "Use the agent credential store or environment for credentials; do not put secrets in arguments.",
    );
  }
  agentManifest(agent);
  return agent;
}

/**
 * How many finished runs the workbench keeps in its own state file.
 *
 * This is a display window, not a retention policy. The durable record of a
 * run is the hash-chained ledger — `acp/sessionBegin` and `acp/sessionEnd`
 * are written to it before and after every run, and that is what an audit
 * reads. What lives in `state.json` is the recent-activity list the panel
 * renders, and keeping it unbounded was a real fault rather than a
 * conservative one: each run carries its full briefing (up to the 60 KB
 * briefing budget) plus up to 100 KB of captured output, so a few hundred
 * runs reach the 20 MB ceiling on `persist()`. Past that the workbench
 * cannot save *anything* — not a new run, not an accepted memory note, not
 * an integration change — while the in-memory state keeps moving, so the
 * panel shows work that silently vanishes on the next reload.
 *
 * A bounded window turns that cliff into a boundary nobody notices. Two
 * hundred is roughly a month of steady use and tens of megabytes below the
 * ceiling, leaving it as the backstop it was meant to be.
 */
const RETAINED_RUNS = 200;

/** Local drafts and participation are independent from the sidecar. Only
 * explicit run actions start ACP processes; one agent writes at a time. */
export class WorkbenchService {
  private state = blankState();
  private loadedRoot: string | undefined;
  private tail: Promise<unknown> = Promise.resolve();
  private readonly listeners = new Set<() => void>();
  private readonly sessions = new Map<
    string,
    {
      session: AdapterSession;
      controller: AbortController;
      sessionId?: string;
      acceptingSteering?: boolean;
    }
  >();
  private readonly output = new Map<string, string>();
  /** Runtime presets from the shipped library; empty until `load` runs. */
  private runtimes: RuntimePreset[] = [];
  /**
   * AMD-M25 / G-03: the one steering implementation. The workbench used to
   * call `steer.send` itself and inject the turn itself, which meant the
   * clarifying-question protocol, uncertainty escalation and partial
   * acceptance existed on one path and not the other. Runs now register with
   * the canonical controller, and `run/steer` delegates to it.
   */
  private steerController: HostedSteerController | undefined;
  private pumping = false;
  private disposed = false;
  /** MV3-T02: built on first browse, never at open. */
  private registryClient: AcpRegistrySource | undefined;
  private registryRoot: string | undefined;
  private changeTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(private readonly options: WorkbenchServiceOptions) {}

  /**
   * The canonical steering controller, built on first use because it needs a
   * connected sidecar. Absent when there is none — in which case a run simply
   * is not steerable, and `run/steer` says so rather than half-working.
   */
  private steering(): HostedSteerController | undefined {
    const sidecar = this.options.sidecar();
    if (!sidecar) return undefined;
    this.steerController ??= new HostedSteerController({
      registry: hostedSessionRegistry,
      sidecar: { request: (method, params) => sidecar.request(method, params) },
      enabledTiers: this.options.enabledTiers,
    });
    return this.steerController;
  }

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
  private capabilities(): WorkbenchSnapshot["capabilities"] {
    const workspaceOpen = Boolean(this.options.workspaceDir());
    const workspaceChanged = Boolean(
      this.loadedRoot &&
        (!this.options.workspaceDir() ||
          path.resolve(this.options.workspaceDir()!) !== this.loadedRoot),
    );
    const trusted = this.options.trusted();
    const governorEnabled = this.options.enabledTiers().includes("governor");
    const executionBlockedReason = workspaceChanged
      ? "The workspace changed. Reopen the Meridian window before running agents."
      : !workspaceOpen
        ? "Open a workspace to run agents."
        : !trusted
          ? "Trust this workspace before running its configured executables."
          : !governorEnabled
            ? "Enable the Governor tier to run agents."
            : !this.options.sidecar()
              ? "Wait for the sidecar so permission decisions can be recorded."
              : !this.options.humanApprover
                ? "The host permission approver is unavailable."
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
    const result = structuredClone({
      ...this.state,
      capabilities: this.capabilities(),
    });
    return {
      revision: result.revision,
      // How to launch a real ACP agent, so binding one is a choice rather
      // than a guess. Read-only, and carries no credential.
      runtimes: this.runtimes,
      skills: result.skills,
      instructions: result.instructions,
      integrations: result.integrations,
      deliverables: result.deliverables,
      learning: result.learning,
      documents: result.documents,
      documentRevisions: result.documentRevisions,
      agents: result.agents.map((agent) => ({
        ...agent,
        runtime: this.state.runs.some(
          (run) => run.agentId === agent.id && run.state === "running",
        )
          ? "running"
          : "idle",
        learningState: this.state.learning.some(
          (note) => note.agentId === agent.id && note.state === "pending",
        )
          ? "review"
          : "waiting",
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
          "The workspace was closed. Reopen the Meridian window before making changes.",
        );
      return;
    }
    const root = path.resolve(current);
    if (root === this.loadedRoot) return;
    if (this.loadedRoot)
      throw new Error(
        "The workspace changed. Reopen Meridian before editing this workbench.",
      );
    const file = path.join(root, ".meridian", "workbench", "state.json");
    let content: string;
    try {
      await this.assertContained(root, file);
      const stat = await fs.stat(file);
      if (stat.size > 20_000_000)
        throw new Error("Workbench state exceeds the 20 MB safety limit.");
      content = await fs.readFile(file, "utf8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      // No state file: a workspace opening Meridian for the first time. This
      // is the *main* case for seeding, not an edge of it — returning here
      // without seeding is what left every genuinely new workspace with the
      // empty catalogues the library exists to fill.
      this.loadedRoot = root;
      await this.seedLibrary();
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
        "Workbench state is invalid or from an unsupported version. It has been left untouched.",
      );
    }
    for (const entry of raw.agents) {
      validateWorkbenchAgent(entry);
      if (!["active", "learning"].includes(record(entry).mode as string))
        throw new Error("Invalid stored agent mode.");
    }
    const loaded = raw as unknown as StoredState;
    // Skills and instructions arrived after the first stored schema. An older
    // state.json simply has no such key; default it rather than refusing to
    // load a workspace the user has real work in.
    if (loaded.skills === undefined) loaded.skills = [];
    if (loaded.instructions === undefined) loaded.instructions = [];
    if (!Array.isArray(loaded.skills) || !Array.isArray(loaded.instructions))
      throw new Error("Invalid stored skills or instructions.");
    for (const entry of loaded.skills) {
      validateWorkbenchSkill(entry);
      if (typeof entry.enabled !== "boolean")
        throw new Error("Invalid stored skill state.");
    }
    for (const entry of loaded.instructions) {
      validateWorkbenchInstruction(entry);
      if (typeof entry.enabled !== "boolean")
        throw new Error("Invalid stored instruction state.");
    }
    // Absent in files written before the shipped library; an absent record
    // means "never offered anything", which is exactly right for those.
    if (loaded.seededBuiltins === undefined) loaded.seededBuiltins = [];
    if (
      !Array.isArray(loaded.seededBuiltins) ||
      loaded.seededBuiltins.some((entry) => typeof entry !== "string")
    )
      throw new Error("Invalid stored library record.");
    if (loaded.integrations === undefined) loaded.integrations = [];
    if (!Array.isArray(loaded.integrations))
      throw new Error("Invalid stored integrations.");
    for (const entry of loaded.integrations) {
      validateIntegrationConnection(entry);
      if (typeof entry.enabled !== "boolean")
        throw new Error("Invalid stored integration state.");
      // A stored connection must never carry a secret. If one is present the
      // file has been hand-edited; drop it rather than load it into memory.
      delete (entry as unknown as Record<string, unknown>).secrets;
    }
    for (const key of ["documents", "documentRevisions"] as const) {
      if (loaded[key] === undefined) loaded[key] = [];
      if (!Array.isArray(loaded[key]))
        throw new Error("Invalid stored studio documents.");
      for (const entry of loaded[key]) {
        documentFields(entry);
        id(entry.id);
        if (!Number.isSafeInteger(entry.version) || entry.version < 1)
          throw new Error("Invalid document version.");
        string(entry.createdAt, "Document creation date", 40);
        string(entry.updatedAt, "Document update date", 40);
      }
    }
    for (const run of loaded.runs) {
      if (
        !run ||
        typeof run.id !== "string" ||
        typeof run.agentId !== "string" ||
        !["queued", "running", "completed", "failed", "cancelled"].includes(
          run.state,
        )
      )
        throw new Error("Invalid stored run.");
      if (run.state === "running" || run.state === "queued") {
        run.state = "cancelled";
        run.finishedAt = new Date().toISOString();
        run.error =
          "The extension stopped before this run finished. Run again explicitly.";
      }
    }
    for (const item of loaded.deliverables) {
      if (!item || typeof item.id !== "string" || !Array.isArray(item.agentIds))
        throw new Error("Invalid stored deliverable.");
      if (item.state === "running") item.state = "failed";
    }
    for (const note of loaded.learning) {
      if (
        !note ||
        typeof note.id !== "string" ||
        typeof note.content !== "string" ||
        !["pending", "accepted", "dismissed"].includes(note.state)
      )
        throw new Error("Invalid stored learning note.");
    }
    this.state = loaded;
    // A state file written before the window existed can be sitting just
    // under the ceiling, where the next change of any kind fails to save.
    // Trimming on open is what lets such a workspace recover by itself,
    // rather than needing someone to hand-edit JSON to get their tool back.
    this.pruneRuns();
    this.loadedRoot = root;
    await this.seedLibrary();
  }

  /**
   * Put the shipped library into a workspace that has not seen it yet.
   *
   * Runs on every open and adds only what has never been offered, so a later
   * extension version delivers its new entries without disturbing anything
   * the user has edited, disabled or deleted. Shipped agents land in Learning
   * with the import permission floor — `read`, `search`, `think` — and no
   * command, so nothing shipped can run until a person binds it to an adapter
   * and activates it.
   *
   * Failure here is never fatal. An empty catalogue is the behaviour this
   * replaced; refusing to open the workspace would be strictly worse.
   */
  private async seedLibrary(): Promise<void> {
    const extensionPath = this.options.extensionPath;
    if (!extensionPath) return;
    try {
      const library = await loadBuiltinLibrary(extensionPath);
      // Presets are not seeded into state — they are a read-only catalogue
      // that follows the installed extension, so an updated list arrives with
      // an update rather than being frozen into a workspace at first run.
      this.runtimes = library.runtimes;
      const plan = planSeed(
        library,
        {
          agents: this.state.agents.map((entry) => entry.id),
          skills: this.state.skills.map((entry) => entry.id),
          instructions: this.state.instructions.map((entry) => entry.id),
        },
        this.state.seededBuiltins ?? [],
      );
      const added =
        plan.agents.length + plan.skills.length + plan.instructions.length;
      const unchanged =
        added === 0 &&
        (this.state.seededBuiltins ?? []).length === plan.seeded.length;
      if (unchanged) return;

      const now = new Date().toISOString();
      // The shipped instruction documents are bound to the shipped agents.
      // `brief()` selects instruction files by `instructionIds`, so unbound
      // they would reach nobody — and the engineering-standards document
      // opens by saying it applies to every agent in the workspace, which
      // would then be false. They ship as a set and are written for each
      // other. Binding text grants no permission; it only decides what the
      // agent reads.
      //
      // Skills are deliberately *not* bound. A skill pack specialises a role
      // — bind `golang-service` and the Developer is a Go developer — so
      // binding all ten would make it ten contradictory things at once. That
      // choice is the user's, and it is the mechanic the product is built on.
      const libraryInstructions = library.instructions.map((entry) => entry.id);
      // A shipped stack agent declares the pack that specialises it. Bind
      // only to packs this workspace actually has: a declared id is a
      // reference into the catalogue, and a dangling one would show a binding
      // that resolves to nothing in the briefing.
      const available = new Set([
        ...this.state.skills.map((entry) => entry.id),
        ...plan.skills.map((entry) => entry.id),
      ]);
      for (const input of plan.agents)
        this.state.agents.push({
          ...input,
          skillIds: input.skillIds.filter((id) => available.has(id)),
          instructionIds: libraryInstructions,
          source: "builtin",
          mode: "learning",
          runtime: "idle",
          learningState: "waiting",
          createdAt: now,
          updatedAt: now,
        });
      for (const input of plan.skills)
        this.state.skills.push({
          ...input,
          enabled: true,
          source: "builtin",
          createdAt: now,
          updatedAt: now,
        });
      for (const input of plan.instructions)
        this.state.instructions.push({
          ...input,
          enabled: true,
          source: "builtin",
          createdAt: now,
          updatedAt: now,
        });
      this.state.seededBuiltins = plan.seeded;
      this.state.revision++;
      await this.persist();
      this.notify();
    } catch (error) {
      this.options.onError?.(
        `The built-in library could not be installed: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  }
  private async persist(): Promise<void> {
    if (!this.loadedRoot)
      throw new Error("Open a workspace before saving workbench changes.");
    const directory = path.join(this.loadedRoot, ".meridian", "workbench");
    // Check existing parents before creating any descendants: even mkdir
    // must not follow a workspace junction outside the project.
    let parent = this.loadedRoot;
    for (const segment of [".meridian", "workbench"]) {
      parent = path.join(parent, segment);
      try {
        await this.assertContained(this.loadedRoot, parent);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
      await fs.mkdir(parent).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== "EEXIST") throw error;
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
    if (relative.startsWith("..") || path.isAbsolute(relative))
      throw new Error("Workbench storage must remain inside the workspace.");
    const temporary = path.join(directory, `.state-${randomUUID()}.tmp`);
    const serialized = JSON.stringify(this.state, null, 2);
    if (Buffer.byteLength(serialized, "utf8") > 20_000_000)
      throw new Error(
        "Workbench state would exceed 20 MB. Run history is trimmed " +
          `automatically to the last ${RETAINED_RUNS} runs, so the size is ` +
          "coming from stored agents, studio documents or accepted memory — " +
          "export and remove what you no longer need. Completed runs remain " +
          "in the ledger either way.",
      );
    try {
      await fs.writeFile(temporary, serialized, {
        encoding: "utf8",
        flag: "wx",
        mode: 0o600,
      });
      await fs.rename(temporary, path.join(directory, "state.json"));
    } finally {
      await fs.unlink(temporary).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== "ENOENT") this.options.onError?.(error.message);
      });
    }
  }
  private async assertContained(root: string, target: string): Promise<void> {
    const [realRoot, realTarget] = await Promise.all([
      fs.realpath(root),
      fs.realpath(target),
    ]);
    const relative = path.relative(realRoot, realTarget);
    if (
      relative === ".." ||
      relative.startsWith(`..${path.sep}`) ||
      path.isAbsolute(relative)
    )
      throw new Error("Workbench storage must remain inside the workspace.");
  }
  private agent(agentId: string): WorkbenchAgent {
    const agent = this.state.agents.find((entry) => entry.id === agentId);
    if (!agent) throw new Error(`Agent '${agentId}' does not exist.`);
    return agent;
  }
  private archiveDocument(document: StudioDocument): void {
    const prior = this.state.documentRevisions.filter(
      (entry) => entry.id === document.id,
    );
    this.state.documentRevisions = this.state.documentRevisions.filter(
      (entry) => entry.id !== document.id,
    );
    this.state.documentRevisions.push(
      ...prior.slice(-19),
      structuredClone(document),
    );
  }
  private deliverable(deliverableId: string): WorkbenchDeliverable {
    const item = this.state.deliverables.find(
      (entry) => entry.id === deliverableId,
    );
    if (!item) throw new Error("Deliverable does not exist.");
    return item;
  }
  private cancelRun(run: WorkbenchRun, reason: string): void {
    if (run.state !== "queued" && run.state !== "running") return;
    run.state = "cancelled";
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
    const runs = this.state.runs.filter(
      (run) => run.deliverableId === deliverableId,
    );
    // No rows left to read means no verdict to reach. `pruneRuns` pins the
    // runs of an unsettled deliverable precisely so this cannot happen, but
    // inferring "review" from an empty set would turn a failed deliverable
    // into a passed one, and that is not a conclusion to reach by accident.
    if (!runs.length) return;
    item.state = runs.some(
      (run) => run.state === "queued" || run.state === "running",
    )
      ? "running"
      : runs.some((run) => run.state !== "completed")
        ? "failed"
        : "review";
    item.updatedAt = new Date().toISOString();
  }
  /**
   * Everything an agent is bound to — its skills, its instruction files, the
   * systems this workspace is connected to and the memory a human accepted —
   * assembled into the document the agent actually receives.
   *
   * Only *enabled* skills and instructions are included. A disabled entry is
   * out of service, and quietly applying one would make the enable switch a
   * decoration.
   */
  private brief(
    agent: WorkbenchAgent,
    task: { title?: string; body: string },
    phase?: SdlcPhase,
  ): string {
    return composeBriefing({
      agent,
      task,
      ...(phase ? { phase } : {}),
      skills: this.state.skills.filter(
        (skill) => skill.enabled && agent.skillIds.includes(skill.id),
      ),
      instructions: this.state.instructions.filter(
        (entry) => entry.enabled && agent.instructionIds.includes(entry.id),
      ),
      integrations: this.state.integrations.filter(
        (entry) => entry.enabled && agent.integrationIds.includes(entry.id),
      ),
      // An agent that freezes memory receives none, however many notes were
      // accepted for it; the freeze is a promise, not a preference.
      memory: agent.trainable.includes("memory")
        ? this.state.learning
            .filter(
              (note) => note.agentId === agent.id && note.state === "accepted",
            )
            .slice(-20)
        : [],
    });
  }

  private queueRun(
    agent: WorkbenchAgent,
    prompt: string,
    deliverableId?: string,
    phase?: SdlcPhase,
  ): void {
    if (agent.mode !== "active")
      throw new Error(
        `Activate ${agent.name} before running it; Learning agents do not receive deliverables.`,
      );
    // One agent runs at a time. A phase-by-phase dispatch queues the same
    // agent more than once, which is intended — designing and later reviewing
    // are different acts — so the guard is on *ad-hoc* runs only, and the
    // queue itself serialises the rest.
    if (
      !deliverableId &&
      this.state.runs.some(
        (run) =>
          run.agentId === agent.id &&
          (run.state === "running" || run.state === "queued"),
      )
    )
      throw new Error(`${agent.name} already has a queued or running task.`);
    this.state.runs.push({
      id: randomUUID(),
      agentId: agent.id,
      agentName: agent.name,
      prompt,
      state: "queued",
      startedAt: new Date().toISOString(),
      ...(deliverableId ? { deliverableId } : {}),
      ...(phase ? { phase } : {}),
    });
    this.pruneRuns();
  }

  /**
   * Drop the oldest finished runs once the display window is full.
   *
   * Two things are never dropped, whatever the cap says. A queued or running
   * run owns a live session and is what `run/steer`, cancellation and the
   * queue pump look up by id; forgetting one would strand a subprocess with
   * nothing able to reach it. And a run belonging to a deliverable that has
   * not settled is still load-bearing, because `settleDeliverable` decides
   * that deliverable's state by reading exactly these rows.
   *
   * So the window is a floor, not a ceiling: it can be exceeded by live work,
   * and it shrinks back on its own as that work finishes.
   */
  private pruneRuns(): void {
    if (this.state.runs.length <= RETAINED_RUNS) return;
    const open = new Set(
      this.state.deliverables
        .filter((item) => item.state !== "completed")
        .map((item) => item.id),
    );
    const pinned = (run: WorkbenchRun): boolean =>
      run.state === "queued" ||
      run.state === "running" ||
      (run.deliverableId !== undefined && open.has(run.deliverableId));
    let removable = this.state.runs.length - RETAINED_RUNS;
    if (removable <= 0) return;
    // Oldest first: `runs` is append-ordered, so a forward pass is
    // chronological without having to trust a timestamp an import may have
    // written.
    this.state.runs = this.state.runs.filter((run) => {
      if (removable > 0 && !pinned(run)) {
        removable -= 1;
        this.output.delete(run.id);
        return false;
      }
      return true;
    });
  }

  async request(request: WorkbenchRequest): Promise<unknown> {
    // Probing and reading reach the network. They run outside the mutation
    // queue deliberately: a fifteen-second timeout against an unreachable
    // host must not stall snapshot polling or every other action behind it.
    if (
      request.action === "integration/probe" ||
      request.action === "integration/read"
    )
      return this.integrationRequest(request);
    // FR-M34-03: browsing reaches a network Meridian does not own, so it
    // runs outside the mutation queue for the same reason a probe does — a
    // ten-second timeout must not stall every other action behind it — and
    // it changes nothing, so there is nothing to commit.
    if (request.action === "registry/browse") return this.browseRegistry();
    if (request.action === "registry/install")
      return this.installFromRegistry(record(request.params ?? {}));
    // FR-M4 (audit TASK-301): loop.* actions are direct sidecar pass-
    // throughs — they orchestrate governed work (checkpointed, ledger-
    // recorded there), they change no local workbench state, and they run
    // outside the mutation queue because a loop can take minutes.
    if (typeof request.action === "string" && request.action.startsWith("loop.")) {
      const sidecar = this.options.sidecar();
      if (!sidecar) throw new Error("The sidecar is not connected.");
      return sidecar.request(request.action, request.params ?? {});
    }
    return this.serialize(async () => {
      if (this.disposed) throw new Error("The workbench has been closed.");
      await this.load();
      const params = record(request.params ?? {});
      if (request.action === "snapshot") return this.snapshot();
      if (request.action === "document/export") {
        const document = this.state.documents.find(
          (entry) => entry.id === id(params.id),
        );
        if (!document) throw new Error("Document no longer exists.");
        return {
          fileName: `${document.kind}-${document.id}.meridian-document.json`,
          content: JSON.stringify(
            { kind: "meridian-studio-document", schemaVersion: 1, document },
            null,
            2,
          ),
        };
      }
      if (request.action === "agent/export") {
        const agent = this.agent(id(params.id));
        // Portability means the whole agent: its bound skills and
        // instructions travel with it, so an import elsewhere reproduces the
        // agent rather than a shell that references things that are not there.
        const portable: PortableAgentDocument = {
          kind: "meridian-portable-agent",
          schemaVersion: 1,
          agent: validateWorkbenchAgent(agent),
          memory: this.state.learning
            .filter(
              (note) => note.agentId === agent.id && note.state === "accepted",
            )
            .map(({ title, content }) => ({ title, content })),
          skills: this.state.skills
            .filter((skill) => agent.skillIds.includes(skill.id))
            .map((skill) => validateWorkbenchSkill(skill)),
          instructions: this.state.instructions
            .filter((entry) => agent.instructionIds.includes(entry.id))
            .map((entry) => validateWorkbenchInstruction(entry)),
        };
        return {
          fileName: `${agent.id}.meridian-agent.json`,
          content: JSON.stringify(portable, null, 2),
        };
      }
      if (request.action === "skill/export") {
        const skill = this.state.skills.find(
          (entry) => entry.id === id(params.id),
        );
        if (!skill) throw new Error("That skill no longer exists.");
        // SKILL.md shape, so the export is usable by anything that reads the
        // open format rather than only by Meridian.
        return {
          fileName: `${skill.id}.SKILL.md`,
          content: frontmatterDocument(
            {
              kind: "skill",
              id: skill.id,
              name: skill.name,
              version: skill.version,
              description: skill.summary,
              tags: skill.tags,
            },
            skill.body,
          ),
        };
      }
      if (request.action === "instruction/export") {
        const instruction = this.state.instructions.find(
          (entry) => entry.id === id(params.id),
        );
        if (!instruction) throw new Error("That instruction no longer exists.");
        return {
          fileName: `${instruction.id}.AGENTS.md`,
          content: frontmatterDocument(
            {
              kind: "instruction",
              id: instruction.id,
              name: instruction.name,
              scope: instruction.scope,
              description: instruction.summary,
            },
            instruction.body,
          ),
        };
      }
      if (!this.loadedRoot)
        throw new Error("Open a workspace before making workbench changes.");
      const previous = structuredClone(this.state);
      let importReport: ImportReport | undefined;
      try {
        const now = new Date().toISOString();
        switch (request.action) {
          case "document/save": {
            const raw = record(params.document);
            const fields = documentFields(raw);
            const existing =
              raw.id === undefined
                ? undefined
                : this.state.documents.find((entry) => entry.id === id(raw.id));
            if (raw.id !== undefined && !existing)
              throw new Error(
                "Document no longer exists. Refresh before saving.",
              );
            if (existing && raw.expectedVersion !== existing.version)
              throw new Error(
                "This document changed in another view. Refresh before saving your changes.",
              );
            if (existing && fields.kind !== existing.kind)
              throw new Error("A document cannot change its kind.");
            if (existing) this.archiveDocument(existing);
            const document: StudioDocument = {
              ...fields,
              id: existing?.id ?? randomUUID(),
              version: (existing?.version ?? 0) + 1,
              createdAt: existing?.createdAt ?? now,
              updatedAt: now,
            };
            if (existing)
              this.state.documents[this.state.documents.indexOf(existing)] =
                document;
            else this.state.documents.unshift(document);
            break;
          }
          case "document/import": {
            const raw = record(
              JSON.parse(string(params.content, "Document JSON", 2_000_000)),
            );
            if (
              raw.kind !== "meridian-studio-document" ||
              raw.schemaVersion !== 1
            )
              throw new Error(
                "Expected a Meridian studio document, schema version 1.",
              );
            this.state.documents.unshift({
              ...documentFields(raw.document),
              id: randomUUID(),
              version: 1,
              createdAt: now,
              updatedAt: now,
            });
            break;
          }
          case "document/remove": {
            const existing = this.state.documents.find(
              (entry) => entry.id === id(params.id),
            );
            if (!existing) throw new Error("Document no longer exists.");
            if (params.expectedVersion !== existing.version)
              throw new Error("Document changed. Refresh before removing it.");
            this.state.documents = this.state.documents.filter(
              (entry) => entry.id !== existing.id,
            );
            this.state.documentRevisions = this.state.documentRevisions.filter(
              (entry) => entry.id !== existing.id,
            );
            break;
          }
          case "document/restore": {
            const existing = this.state.documents.find(
              (entry) => entry.id === id(params.id),
            );
            if (!existing || existing.version !== params.expectedVersion)
              throw new Error("Document changed. Refresh before restoring it.");
            const old = this.state.documentRevisions.find(
              (entry) =>
                entry.id === existing.id && entry.version === params.version,
            );
            if (!old)
              throw new Error("Requested document revision is unavailable.");
            this.archiveDocument(existing);
            this.state.documents[this.state.documents.indexOf(existing)] = {
              ...structuredClone(old),
              version: existing.version + 1,
              updatedAt: now,
            };
            break;
          }
          case "agent/save": {
            const input = validateWorkbenchAgent(params.agent);
            const existing = this.state.agents.find(
              (entry) => entry.id === input.id,
            );
            if (
              existing &&
              this.state.runs.some(
                (run) =>
                  run.agentId === input.id &&
                  ["running", "queued"].includes(run.state),
              )
            )
              throw new Error(
                "Stop this agent before changing its configuration.",
              );
            const agent: WorkbenchAgent = {
              ...input,
              mode: existing?.mode ?? "learning",
              runtime: "idle",
              learningState: "waiting",
              createdAt: existing?.createdAt ?? now,
              updatedAt: now,
            };
            if (existing)
              this.state.agents[this.state.agents.indexOf(existing)] = agent;
            else this.state.agents.push(agent);
            break;
          }
          case "agent/import": {
            const content = string(
              params.content,
              "Portable agent JSON",
              20_000_000,
            );
            if (Buffer.byteLength(content, "utf8") > 20_000_000)
              throw new Error(
                "Portable agent JSON must be smaller than 20 MB.",
              );
            const raw = record(JSON.parse(content));
            if (
              raw.kind !== "meridian-portable-agent" ||
              raw.schemaVersion !== 1
            )
              throw new Error(
                "Expected a Meridian portable agent document, schema version 1.",
              );
            const input = validateWorkbenchAgent(raw.agent);
            if (this.state.agents.some((entry) => entry.id === input.id))
              throw new Error(
                `Agent '${input.id}' already exists. Edit it or change the imported ID.`,
              );
            this.state.agents.push({
              ...input,
              mode: "learning",
              runtime: "idle",
              learningState: "waiting",
              createdAt: now,
              updatedAt: now,
            });
            if (raw.memory !== undefined) {
              if (!Array.isArray(raw.memory))
                throw new Error(
                  "Portable memory must be a list of reviewable notes.",
                );
              for (const entry of raw.memory) {
                const note = record(entry);
                this.state.learning.push({
                  id: randomUUID(),
                  agentId: input.id,
                  deliverableId: "portable-import",
                  title: string(note.title, "Memory title", 200),
                  content: string(note.content, "Memory note", 40_000),
                  state: "pending",
                  createdAt: now,
                  surface: "memory",
                });
              }
            }
            break;
          }
          case "agent/assign": {
            const agent = this.agent(id(params.id));
            if (params.phases !== undefined)
              agent.phases = phaseList(params.phases);
            if (params.skillIds !== undefined) {
              const ids = list(params.skillIds, "Skills", 100);
              for (const skillId of ids)
                if (!this.state.skills.some((skill) => skill.id === skillId))
                  throw new Error(`Skill '${skillId}' no longer exists.`);
              agent.skillIds = ids;
            }
            if (params.instructionIds !== undefined) {
              const ids = list(params.instructionIds, "Instructions", 100);
              for (const instructionId of ids)
                if (
                  !this.state.instructions.some(
                    (entry) => entry.id === instructionId,
                  )
                )
                  throw new Error(
                    `Instruction '${instructionId}' no longer exists.`,
                  );
              agent.instructionIds = ids;
            }
            if (params.integrationIds !== undefined) {
              const ids = list(params.integrationIds, "Integrations", 100);
              for (const connectionId of ids)
                if (
                  !this.state.integrations.some(
                    (entry) => entry.id === connectionId,
                  )
                )
                  throw new Error(
                    `Connection '${connectionId}' no longer exists.`,
                  );
              agent.integrationIds = ids;
            }
            agent.updatedAt = now;
            break;
          }
          case "integration/save": {
            const input = validateIntegrationConnection(params.connection);
            const definition = integrationById(input.integrationId)!;
            const supplied = record(
              record(params.connection).secrets ?? {},
            ) as Record<string, unknown>;
            const secretFields = definition.fields.filter(
              (field) => field.kind === "secret",
            );
            for (const key of Object.keys(supplied))
              if (!secretFields.some((field) => field.key === key))
                throw new Error(
                  `${definition.name} has no credential field called '${key}'.`,
                );

            const existing = this.state.integrations.find(
              (entry) => entry.id === input.id,
            );
            const secretKeys = new Set(existing?.secretKeys ?? []);
            for (const [key, value] of Object.entries(supplied)) {
              const text = string(value, "Credential", 8_000, true);
              if (!text) continue;
              if (!this.options.secrets)
                throw new Error(
                  "The OS keychain is unavailable, so this credential cannot be " +
                    "stored. Meridian never writes credentials to the workspace.",
                );
              await this.options.secrets.store(
                secretKey(input.id, key),
                text,
              );
              secretKeys.add(key);
            }
            // A required credential with nothing stored is a connection that
            // cannot work; say so now rather than at the first probe.
            for (const field of secretFields)
              if (field.required && !secretKeys.has(field.key))
                throw new Error(`${definition.name} needs ${field.label}.`);

            if (existing) {
              Object.assign(existing, input, {
                secretKeys: [...secretKeys],
                updatedAt: now,
              });
            } else {
              this.state.integrations.unshift({
                ...input,
                enabled: true,
                secretKeys: [...secretKeys],
                createdAt: now,
                updatedAt: now,
              });
            }
            break;
          }
          case "integration/remove": {
            const connectionId = id(params.id);
            const connection = this.state.integrations.find(
              (entry) => entry.id === connectionId,
            );
            if (!connection) throw new Error("That connection no longer exists.");
            // Removing a connection removes its credentials. Leaving keychain
            // entries behind for a connection the user deleted would be a
            // quiet betrayal of what "remove" means.
            for (const key of connection.secretKeys)
              await this.options.secrets?.delete(secretKey(connectionId, key));
            this.state.integrations = this.state.integrations.filter(
              (entry) => entry.id !== connectionId,
            );
            for (const agent of this.state.agents)
              if (agent.integrationIds.includes(connectionId)) {
                agent.integrationIds = agent.integrationIds.filter(
                  (entry) => entry !== connectionId,
                );
                agent.updatedAt = now;
              }
            break;
          }
          case "integration/toggle": {
            const connection = this.state.integrations.find(
              (entry) => entry.id === id(params.id),
            );
            if (!connection) throw new Error("That connection no longer exists.");
            if (typeof params.enabled !== "boolean")
              throw new Error("Enabled must be true or false.");
            connection.enabled = params.enabled;
            connection.updatedAt = now;
            break;
          }
          case "skill/save": {
            const input = validateWorkbenchSkill(params.skill);
            const existing = this.state.skills.find(
              (entry) => entry.id === input.id,
            );
            if (existing) Object.assign(existing, input, { updatedAt: now });
            else
              this.state.skills.unshift({
                ...input,
                enabled: true,
                source: "authored",
                createdAt: now,
                updatedAt: now,
              });
            break;
          }
          case "skill/remove": {
            const skillId = id(params.id);
            if (!this.state.skills.some((entry) => entry.id === skillId))
              throw new Error("That skill no longer exists.");
            this.state.skills = this.state.skills.filter(
              (entry) => entry.id !== skillId,
            );
            // A removed skill must not linger as a dangling binding on an agent.
            for (const agent of this.state.agents) {
              if (!agent.skillIds.includes(skillId)) continue;
              agent.skillIds = agent.skillIds.filter((entry) => entry !== skillId);
              agent.updatedAt = now;
            }
            break;
          }
          case "skill/toggle": {
            const skill = this.state.skills.find(
              (entry) => entry.id === id(params.id),
            );
            if (!skill) throw new Error("That skill no longer exists.");
            if (typeof params.enabled !== "boolean")
              throw new Error("Enabled must be true or false.");
            skill.enabled = params.enabled;
            skill.updatedAt = now;
            break;
          }
          case "instruction/save": {
            const input = validateWorkbenchInstruction(params.instruction);
            const existing = this.state.instructions.find(
              (entry) => entry.id === input.id,
            );
            if (existing) Object.assign(existing, input, { updatedAt: now });
            else
              this.state.instructions.unshift({
                ...input,
                enabled: true,
                source: "authored",
                createdAt: now,
                updatedAt: now,
              });
            break;
          }
          case "instruction/remove": {
            const instructionId = id(params.id);
            if (
              !this.state.instructions.some(
                (entry) => entry.id === instructionId,
              )
            )
              throw new Error("That instruction no longer exists.");
            this.state.instructions = this.state.instructions.filter(
              (entry) => entry.id !== instructionId,
            );
            for (const agent of this.state.agents) {
              if (!agent.instructionIds.includes(instructionId)) continue;
              agent.instructionIds = agent.instructionIds.filter(
                (entry) => entry !== instructionId,
              );
              agent.updatedAt = now;
            }
            break;
          }
          case "instruction/toggle": {
            const instruction = this.state.instructions.find(
              (entry) => entry.id === id(params.id),
            );
            if (!instruction) throw new Error("That instruction no longer exists.");
            if (typeof params.enabled !== "boolean")
              throw new Error("Enabled must be true or false.");
            instruction.enabled = params.enabled;
            instruction.updatedAt = now;
            break;
          }
          case "agent/importPackage": {
            // Answers with what it created as well as the state, so the
            // interface reports the outcome instead of implying one. The
            // report rides out through the shared commit path below.
            importReport = this.importPackage(params, now);
            break;
          }
          case "agent/remove": {
            const agent = this.agent(id(params.id));
            for (const run of this.state.runs.filter(
              (entry) => entry.agentId === agent.id,
            ))
              this.cancelRun(run, "Agent removed by the user.");
            this.state.agents = this.state.agents.filter(
              (entry) => entry.id !== agent.id,
            );
            this.state.learning = this.state.learning.filter(
              (note) => note.agentId !== agent.id,
            );
            break;
          }
          case "agent/bindRuntime": {
            // Set an agent's executable from a shipped preset. Purely a
            // convenience over typing the same command by hand — it grants
            // nothing, changes no permission, and leaves the agent in
            // whatever mode it was in. A preset carries no credential, so
            // there is nothing here to leak into the workspace file.
            const agent = this.agent(id(params.id));
            const preset = this.runtimes.find(
              (entry) => entry.id === string(params.runtimeId, "Runtime", 200),
            );
            if (!preset)
              throw new Error(
                "That agent runtime is not one of the shipped presets. Set " +
                  "the executable directly if you are using your own build.",
              );
            agent.command = preset.command;
            agent.args = [...preset.args];
            agent.updatedAt = now;
            break;
          }
          case "agent/mode": {
            const agent = this.agent(id(params.id));
            if (params.mode !== "active" && params.mode !== "learning")
              throw new Error("Mode must be active or learning.");
            agent.mode = params.mode;
            agent.updatedAt = now;
            if (agent.mode === "learning")
              for (const run of this.state.runs.filter(
                (entry) => entry.agentId === agent.id,
              ))
                this.cancelRun(run, "Agent deactivated; moved to Learning.");
            break;
          }
          case "agent/run": {
            const capability = this.capabilities();
            if (!capability.executionReady)
              throw new Error(capability.executionBlockedReason);
            const runAgent = this.agent(id(params.id));
            this.queueRun(
              runAgent,
              this.brief(runAgent, {
                body: string(params.prompt, "Task prompt", 40_000),
              }),
            );
            break;
          }
          case "run/cancel": {
            const run = this.state.runs.find(
              (entry) => entry.id === id(params.id),
            );
            if (!run) throw new Error("Run does not exist.");
            this.cancelRun(run, "Cancelled by the user.");
            break;
          }
          case "run/steer": {
            const run = this.state.runs.find(
              (entry) => entry.id === id(params.id),
            );
            const handle = run && this.sessions.get(run.id);
            if (
              !run ||
              run.state !== "running" ||
              !handle?.sessionId ||
              !handle.acceptingSteering ||
              handle.controller.signal.aborted
            )
              throw new Error(
                "Choose a running workbench session that is accepting guidance. This task may be finishing.",
              );
            if (!this.capabilities().executionReady)
              throw new Error(this.capabilities().executionBlockedReason);
            const message = string(params.message, "Steering message", 20_000);
            if (
              (run.steering?.filter((entry) => entry.state === "queued")
                .length ?? 0) >= 20
            )
              throw new Error(
                "This run already has 20 queued steering messages. Wait for the next turn.",
              );
            const controller = this.steering();
            if (!controller)
              throw new Error(
                "Steering needs a connected sidecar; it records the act before " +
                  "it reaches the agent. Check the Runtime tab.",
              );
            // One implementation of the protocol: the controller records the
            // steering act in the ledger first, then injects it into the live
            // session. This service no longer does either itself.
            let result: { accepted: boolean; sequence: number };
            try {
              // Recorded through the canonical controller; delivered by this
              // service at the next turn boundary, which is what the interface
              // promises and what a one-turn-at-a-time adapter can accept.
              result = await controller.steer(handle.sessionId, message, {
                deliver: "nextTurn",
              });
            } catch (error) {
              if (error instanceof NotHostedSessionError)
                throw new Error(
                  "That session is no longer running here, so there is nothing " +
                    "to steer. It may have finished between the click and now.",
                );
              throw error;
            }
            if (!result.accepted || !Number.isSafeInteger(result.sequence))
              throw new Error(
                "The sidecar did not record the steering message.",
              );
            run.steering ??= [];
            run.steering.push({
              message,
              sequence: result.sequence,
              state: "queued",
              submittedAt: now,
            });
            break;
          }
          case "deliverable/save": {
            const title = string(params.title, "Title", 200).trim();
            const brief = string(params.brief, "Brief", 40_000);
            const existing =
              params.id === undefined
                ? undefined
                : this.deliverable(id(params.id));
            if (existing && existing.state !== "draft")
              throw new Error(
                "Only draft deliverables can be edited. Create a new draft for another iteration.",
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
                state: "draft",
                agentIds: [],
                createdAt: now,
                updatedAt: now,
              });
            break;
          }
          case "deliverable/dispatch": {
            const capability = this.capabilities();
            if (!capability.executionReady)
              throw new Error(capability.executionBlockedReason);
            const item = this.deliverable(id(params.id));
            if (item.state !== "draft")
              throw new Error(
                "Only a draft can be dispatched. Create a new draft to run again.",
              );
            // The delivery chain: for each of the nine phases in order, the
            // active agents tagged for it. Where no agent is tagged at all,
            // every active agent is convened once, unphased.
            const convened = convene(this.state.agents);
            const agents = [
              ...new Map(
                convened.map((entry) => [entry.agent.id, entry.agent]),
              ).values(),
            ];
            if (
              params.expectedBriefUpdatedAt !== undefined &&
              params.expectedBriefUpdatedAt !== item.updatedAt
            )
              throw new Error(
                "The brief changed after review. Recheck the launch.",
              );
            if (params.expectedTeam !== undefined) {
              if (!Array.isArray(params.expectedTeam))
                throw new Error("Expected team must be an array.");
              const expected = params.expectedTeam
                .map((entry) => {
                  const member = record(entry);
                  return {
                    id: id(member.id),
                    updatedAt: string(
                      member.updatedAt,
                      "Profile update time",
                      40,
                    ),
                  };
                })
                .sort((a, b) => a.id.localeCompare(b.id));
              const actual = agents
                .map((agent) => ({ id: agent.id, updatedAt: agent.updatedAt }))
                .sort((a, b) => a.id.localeCompare(b.id));
              if (JSON.stringify(expected) !== JSON.stringify(actual))
                throw new Error(
                  "The participating team changed after review. Recheck the launch.",
                );
            }
            if (!convened.length)
              throw new Error(
                this.state.agents.some((agent) => agent.mode === "active")
                  ? "Every active agent is tagged for phases none of them cover. " +
                    "Tag at least one active agent on the SDLC phases board."
                  : "Activate at least one agent before dispatching a deliverable.",
              );
            item.agentIds = agents.map((agent) => agent.id);
            item.state = "running";
            item.updatedAt = now;
            for (const { agent, phase } of convened)
              this.queueRun(
                agent,
                this.brief(
                  agent,
                  { title: item.title, body: item.brief },
                  phase,
                ),
                item.id,
                phase,
              );
            break;
          }
          case "deliverable/complete": {
            const item = this.deliverable(id(params.id));
            if (item.state !== "review")
              throw new Error(
                "Review the completed agent turns before marking this deliverable complete.",
              );
            const feedback = string(params.feedback, "Review feedback", 20_000);
            item.state = "completed";
            item.feedback = feedback;
            item.updatedAt = now;
            for (const agent of this.state.agents.filter(
              (entry) =>
                entry.mode === "learning" && entry.trainable.includes("memory"),
            )) {
              this.state.learning.push({
                id: randomUUID(),
                agentId: agent.id,
                deliverableId: item.id,
                title: `Review: ${item.title}`,
                content: `Source deliverable: ${item.id}\n\nHuman feedback:\n${feedback}\n\nProposed memory: Apply this feedback when it is relevant to your role (${agent.role}). Review before accepting; this note does not modify policies, executable code, or model weights.`,
                state: "pending",
                createdAt: now,
                surface: "memory",
              });
            }
            break;
          }
          case "learning/review": {
            const note = this.state.learning.find(
              (entry) => entry.id === id(params.id),
            );
            if (!note || note.state !== "pending")
              throw new Error(
                "This learning note is no longer awaiting review.",
              );
            if (
              params.decision !== "accepted" &&
              params.decision !== "dismissed"
            )
              throw new Error(
                "Learning decision must be accepted or dismissed.",
              );
            if (
              params.decision === "accepted" &&
              !this.agent(note.agentId).trainable.includes("memory")
            )
              throw new Error(
                "This agent freezes memory. Enable trainable memory before accepting a note.",
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
            this.cancelRun(run, "Agent stopped; state could not be saved.");
        throw error;
      }
      this.notify();
      void this.pump();
      const snapshot = this.snapshot();
      return importReport ? { snapshot, report: importReport } : snapshot;
    });
  }

  /**
   * Probe or read a tool connection.
   *
   * The connection is read under the queue so it reflects committed state,
   * the network call happens outside it, and a probe result is committed back
   * under the queue. A read commits nothing: looking at Jira is not a change
   * to your workspace, and recording one would make the revision counter lie.
   */
  /**
   * Refuse to launch an agent whose installed folder has changed
   * (`FR-M44-04`, `SEC-33`).
   *
   * Only agents Meridian installed have a pin, so only they can drift.
   * An agent with no folder — the ordinary case, a command bound by hand —
   * reads as `unpinned` and launches: it was never installed here, there is
   * no baseline, and refusing it would break every preset binding.
   *
   * Throwing refuses the launch. `launchAdapter` awaits this hook precisely
   * so a refusal can arrive before the process starts rather than after it
   * has already acted.
   */
  private async refuseDriftedAdapter(
    agentId: string,
    workspaceDir: string,
  ): Promise<void> {
    const root = path.join(workspaceDir, ".meridian", "adapters");
    const verdict = await verifyAdapterPin(
      root,
      agentId,
      path.join(root, agentId),
    ).catch(() => undefined);
    if (verdict?.state !== "drifted") return;

    // MV3-T01, SEC-33: a drift mismatch refuses the load, names both digests,
    // AND writes a ledger entry. The first two were built and the third was
    // not, which meant the one event this check exists to catch — somebody
    // changed an installed agent — left no record once the error dialog was
    // dismissed. The refusal is Meridian's own act on bytes it digested
    // itself, so the entry is `direct` and attributed to Meridian, and it
    // carries the digests, never the adapter's contents.
    //
    // The refusal stands whether or not the entry lands. A refusal that a
    // failed ledger write could turn into a launch would make the integrity
    // check depend on the audit trail being available, which is backwards.
    let recorded = false;
    const sidecar = this.options.sidecar();
    if (sidecar) {
      try {
        await sidecar.request("ledger.append", {
          storyId: agentId,
          phase: "build",
          loopId: "adapter-integrity",
          loopIteration: 1,
          actorId: "meridian-pin-check",
          actorVersion: "adapter-pin/v1",
          actorKind: "meta",
          policyVersion: "adapter-pin/v1",
          actionType: "adapter_drift_refused",
          decision: "rejected",
          vendor: "meridian",
          observationConfidence: "direct",
          reworkReason: verdict.detail.slice(0, 4000),
          input: JSON.stringify({
            adapterId: agentId,
            expected: verdict.expected,
            actual: verdict.actual,
            expectedFiles: verdict.expectedFiles,
            actualFiles: verdict.actualFiles,
          }),
        });
        recorded = true;
      } catch (error) {
        this.options.onError?.(
          `The refusal to launch '${agentId}' was not recorded in the ledger: ` +
            `${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    throw new Error(
      recorded
        ? verdict.detail
        : `${verdict.detail} This refusal could not be recorded in the ledger.`,
    );
  }

  /**
   * Record which binary this agent actually is (FR-M44-01/02, AC-52).
   *
   * Two things happen and neither may stop the run: the identity is
   * remembered locally so a later swap is visible, and it is appended to the
   * ledger so attribution recorded afterwards can be read back against a
   * known binary. A launch that failed because a provenance write failed
   * would trade a governance feature for an outage, so failures here are
   * reported and the run proceeds — with the gap itself reported, rather
   * than passing silently.
   */
  private async recordAgentIdentity(
    agentId: string,
    vendor: string,
    workspaceDir: string,
    identity: AgentIdentity,
  ): Promise<void> {
    let warning: string | undefined;
    try {
      const comparison = await noteAgentIdentity(
        path.join(workspaceDir, ".meridian"),
        agentId,
        identity,
      );
      warning = comparison.warning;
    } catch (error) {
      this.options.onError?.(
        `Meridian could not remember which binary '${agentId}' is, so a future ` +
          `swap would go unnoticed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
    if (warning) this.options.onError?.(warning);

    const sidecar = this.options.sidecar();
    if (!sidecar) return;
    try {
      await sidecar.request("ledger.append", {
        storyId: agentId,
        phase: "build",
        loopId: "agent-identity",
        loopIteration: 1,
        actorId: agentId,
        actorVersion: identity.declaredVersion ?? "unknown",
        actorKind: "external",
        policyVersion: "agent-identity/v1",
        actionType: "agent_identity",
        vendor: vendor || "unknown",
        // The entry is Meridian's own observation of which file is on disk.
        // Digested here: `direct`. Not digestable — a run-time fetcher, or
        // nothing on PATH: `inferred`, which is a clamp DOWN and never up
        // (SEC-34). There is no rung for "the agent told us its name".
        observationConfidence: identity.assurance === "verified" ? "direct" : "inferred",
        ...(warning ? { reworkReason: warning.slice(0, 4000) } : {}),
        input: JSON.stringify(identity),
      });
    } catch (error) {
      this.options.onError?.(
        `Agent identity for '${agentId}' was not recorded in the ledger: ` +
          `${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // -- the ACP Registry (FR-M34-03, FR-M44-03; MV3-T02) ---------------------

  /**
   * The registry client for this workspace, built on demand.
   *
   * On demand is the point. Constructing it at open would be harmless today
   * and would be exactly the seam through which an activation-time fetch
   * arrives later; there is nothing to reach the network with until someone
   * asks to browse.
   */
  private registrySource(): AcpRegistrySource | undefined {
    const workspaceDir = this.options.workspaceDir();
    if (!workspaceDir) return undefined;
    if (!this.registryClient || this.registryRoot !== workspaceDir) {
      this.registryClient =
        this.options.registry?.(workspaceDir) ??
        new AcpRegistrySource({ workspaceDir });
      this.registryRoot = workspaceDir;
    }
    return this.registryClient;
  }

  /**
   * What the registry lists, projected into the fixed shape the interface
   * renders (`FR-M34-03`).
   *
   * A projection rather than a pass-through: the index is untrusted input,
   * and handing an arbitrary parsed object to a surface is how a field
   * nobody expected ends up rendered. Nothing in it is executed here or
   * anywhere else; `packages.ts` has the same rule for archives.
   */
  private async browseRegistry(): Promise<RegistryBrowseResult> {
    const source = this.registrySource();
    if (!source) {
      return {
        state: "idle",
        entries: [],
        registryUrl: "",
        notice:
          "Open a workspace first. A registry install writes an adapter " +
          "folder, and there is nowhere to put one.",
      };
    }
    // The explicit action. This is the one call in the product that reaches
    // a network Meridian does not own, and it happens because a person
    // pressed something.
    const status = await source.refresh();
    return {
      state: status.state,
      entries: status.entries.map((entry) => projectRegistryEntry(entry)),
      registryUrl: source.url,
      ...("fetchedAt" in status ? { fetchedAt: status.fetchedAt } : {}),
      ...(registryNotice(status) ? { notice: registryNotice(status) } : {}),
    };
  }

  /**
   * Install a listed agent into probation (`FR-M34-03`, `FR-M15-03`/`05`).
   *
   * The network and filesystem work happens outside the mutation queue and
   * the state change is committed inside it, the same shape `integration/probe`
   * uses. The install itself pins the adapter (`FR-M44-03`, in
   * `AcpRegistrySource.install`), so there is no registry path that skips
   * what a sideload gets — `J7`, one path and not two.
   */
  private async installFromRegistry(
    params: Record<string, unknown>,
  ): Promise<RegistryInstallResult> {
    const source = this.registrySource();
    const workspaceDir = this.options.workspaceDir();
    if (!source || !workspaceDir) {
      return {
        ok: false,
        errors: ["Open a workspace before installing from the registry."],
        snapshot: this.snapshot(),
      };
    }
    const wanted = id(params.id);
    const result = await source.install(wanted, {
      platformKey: registryPlatformKey(),
      // A platform binary can be digested and therefore identified
      // (FR-M44-01); npx and uvx fetch at launch and cannot. Preferring the
      // binary is preferring the distribution that can be verified.
      preferBinary: true,
    });
    if (!result.ok) {
      return { ok: false, errors: result.errors, snapshot: this.snapshot() };
    }

    const { adapter } = result;
    const permissions = [...DEFAULT_IMPORT_PERMISSIONS];
    const snapshot = await this.serialize(async () => {
      if (this.disposed) throw new Error("The workbench has been closed.");
      await this.load();
      const now = new Date().toISOString();
      const existing = this.state.agents.findIndex(
        (entry) => entry.id === adapter.id,
      );
      const agent = {
        id: adapter.id,
        name: adapter.manifest.id,
        role: adapter.manifest.roles[0] ?? "Developer",
        description:
          `Installed from the ACP Registry on ${now}. ` +
          `Its contents are pinned; the registry vouches for nothing.`,
        // An entry that names no vendor is not "unknown vendor" dressed as
        // a blank: the field is required and an empty one would render as a
        // missing value rather than an absent claim (P26).
        vendor: adapter.manifest.vendor ?? "unattributed",
        version: adapter.manifest.version,
        command: adapter.manifest.acp.command,
        args: [...(adapter.manifest.acp.args ?? [])],
        instructions: "",
        // FR-M15-03/05: probation at the import floor. A registry install is
        // not a recommendation, and there is no fast path that skips this.
        permissions,
        trainable: [] as LearningSurface[],
        phases: [] as SdlcPhase[],
        skillIds: [] as string[],
        instructionIds: [] as string[],
        // Nothing connected. A registry agent has been on this machine for
        // seconds; binding it to a production system is a decision someone
        // makes afterwards, deliberately.
        integrationIds: [] as string[],
      };
      const row = {
        ...agent,
        source: "imported" as const,
        mode: "learning" as const,
        runtime: "idle" as const,
        learningState: "waiting" as const,
        createdAt: now,
        updatedAt: now,
      };
      if (existing >= 0) {
        // A reinstall replaces the record and re-enters probation: the
        // binary behind it may be different, and inheriting the old agent's
        // standing would carry trust across a change nobody reviewed.
        this.state.agents[existing] = {
          ...row,
          createdAt: this.state.agents[existing].createdAt,
        };
      } else {
        this.state.agents.push(row);
      }
      this.state.revision++;
      await this.persist();
      this.notify();
      return this.snapshot();
    });

    return {
      ok: true,
      errors: [],
      installed: {
        id: adapter.id,
        dir: adapter.dir,
        ...(adapter.pin.expected ? { pinDigest: adapter.pin.expected } : {}),
        permissions,
      },
      snapshot,
    };
  }

  private async integrationRequest(request: WorkbenchRequest): Promise<unknown> {
    const params = record(request.params ?? {});
    const connectionId = id(params.id);
    const connection = await this.serialize(async () => {
      if (this.disposed) throw new Error("The workbench has been closed.");
      await this.load();
      const found = this.state.integrations.find(
        (entry) => entry.id === connectionId,
      );
      if (!found) throw new Error("That connection no longer exists.");
      return structuredClone(found);
    });

    const secret = (field: string) =>
      Promise.resolve(
        this.options.secrets?.get(secretKey(connectionId, field)) ?? undefined,
      );
    const transport = this.options.transport ?? defaultTransport();

    if (request.action === "integration/read") {
      if (!connection.enabled)
        throw new Error(
          `${connection.name} is disabled. Enable it before reading from it.`,
        );
      const operationId = string(params.operationId, "Operation", 60);
      return (await readIntegration(
        connection,
        operationId,
        transport,
        secret,
      )) satisfies IntegrationReadResult;
    }

    const result = await probeIntegration(connection, transport, secret);
    return this.serialize(async () => {
      await this.load();
      const stored = this.state.integrations.find(
        (entry) => entry.id === connectionId,
      );
      // The connection may have been removed while the probe was in flight;
      // that is not an error, there is simply nothing left to record it on.
      if (stored) {
        stored.lastProbe = { ...result, at: new Date().toISOString() };
        this.state.revision++;
        await this.persist();
        this.notify();
      }
      return this.snapshot();
    });
  }

  /**
   * Ingest a Markdown, ZIP or portable-JSON package into the workbench.
   *
   * Every agent enters in Learning mode, exactly as a manually created one
   * does — an imported agent has earned no participation. Identifier
   * collisions are resolved by suffixing rather than by overwriting, because
   * silently replacing an agent the user already tuned is the worse failure.
   */
  private importPackage(params: Record<string, unknown>, now: string): ImportReport {
    const fileName = string(params.fileName, "File name", 400, true);
    const hasText = params.content !== undefined;
    const hasBytes = params.contentBase64 !== undefined;
    if (hasText === hasBytes)
      throw new Error(
        "Supply exactly one of file text or archive bytes when importing a package.",
      );
    const content = hasText
      ? string(params.content, "Package content", 20_000_000, true)
      : undefined;
    const contentBase64 = hasBytes
      ? string(params.contentBase64, "Archive bytes", 60_000_000, true)
      : undefined;

    const parsed = parsePackage({ fileName, content, contentBase64 });
    const report: ImportReport = {
      agents: [],
      skills: [],
      instructions: [],
      skipped: [...parsed.skipped],
      format: parsed.format,
    };

    const uniqueId = (candidate: string, taken: Set<string>, prefix: string) => {
      const base = slugify(candidate, prefix);
      if (!taken.has(base)) return base;
      for (let suffix = 2; suffix < 500; suffix += 1) {
        const next = `${base}-${suffix}`.slice(0, 60);
        if (!taken.has(next)) return next;
      }
      throw new Error(`Too many packages already use the identifier '${base}'.`);
    };

    const skillIds = new Set(this.state.skills.map((entry) => entry.id));
    const remappedSkills = new Map<string, string>();
    for (const skill of parsed.skills) {
      const input = validateWorkbenchSkill(skill);
      const finalId = uniqueId(input.id, skillIds, "skill");
      skillIds.add(finalId);
      remappedSkills.set(input.id, finalId);
      this.state.skills.unshift({
        ...input,
        id: finalId,
        enabled: true,
        source: "imported",
        createdAt: now,
        updatedAt: now,
      });
      report.skills.push(finalId);
    }

    const instructionIds = new Set(
      this.state.instructions.map((entry) => entry.id),
    );
    const remappedInstructions = new Map<string, string>();
    for (const instruction of parsed.instructions) {
      const input = validateWorkbenchInstruction(instruction);
      const finalId = uniqueId(input.id, instructionIds, "instruction");
      instructionIds.add(finalId);
      remappedInstructions.set(input.id, finalId);
      this.state.instructions.unshift({
        ...input,
        id: finalId,
        enabled: true,
        source: "imported",
        createdAt: now,
        updatedAt: now,
      });
      report.instructions.push(finalId);
    }

    const agentIds = new Set(this.state.agents.map((entry) => entry.id));
    for (const agent of parsed.agents) {
      const input = validateWorkbenchAgent({
        ...agent,
        // Rebind to the identifiers the collision resolver actually assigned.
        skillIds: agent.skillIds
          .map((entry) => remappedSkills.get(entry) ?? entry)
          .filter((entry) => skillIds.has(entry)),
        instructionIds: agent.instructionIds
          .map((entry) => remappedInstructions.get(entry) ?? entry)
          .filter((entry) => instructionIds.has(entry)),
      });
      const finalId = uniqueId(input.id, agentIds, "agent");
      agentIds.add(finalId);
      this.state.agents.push({
        ...input,
        id: finalId,
        mode: "learning",
        runtime: "idle",
        learningState: "waiting",
        createdAt: now,
        updatedAt: now,
      });
      report.agents.push(finalId);
    }

    if (!report.agents.length && !report.skills.length && !report.instructions.length)
      throw new Error("That package contained nothing importable.");
    return report;
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
          this.capabilities().executionBlockedReason ??
            "Execution is unavailable.",
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
          const run = this.state.runs.find((entry) => entry.state === "queued");
          if (!run) return undefined;
          if (
            !this.capabilities().executionReady ||
            this.agent(run.agentId).mode !== "active"
          ) {
            this.cancelRun(
              run,
              this.capabilities().executionBlockedReason ??
                "Agent is in Learning mode.",
            );
            this.state.revision++;
            await this.persist();
            this.notify();
            return null;
          }
          run.state = "running";
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
      this.options.onError?.(
        `Workbench execution stopped: ${(error as Error).message}`,
      );
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
        path.join(workspaceDir, ".meridian", "policy", "acp-permissions.yaml"),
        ...(this.options.policyPaths ?? []),
      ]) {
        if (!file) continue;
        try {
          policyText = await fs.readFile(file, "utf8");
          break;
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
      }
      // A missing policy has no grants. Activation controls participation;
      // it never bypasses probation or elevates autonomy.
      const policy = parseAcpPermissionPolicy(
        policyText ?? "version: 1\nadapters: {}",
        "ACP permission policy",
      );
      if (policy.errors.length) throw new Error(policy.errors.join("\n"));
      if (
        this.disposed ||
        this.state.runs.find((entry) => entry.id === run.id)?.state !==
          "running"
      )
        return;
      if (!this.capabilities().executionReady)
        throw new Error(this.capabilities().executionBlockedReason);
      let permissionRecordingFailed = false;
      const gate = createPolicyGate({
        policy,
        adapter: manifest,
        adapterState: "probation",
        humanApprover: async (request, context) => {
          if (
            permissionRecordingFailed ||
            this.disposed ||
            controller.signal.aborted ||
            !this.capabilities().executionReady
          )
            return { outcome: "cancelled" };
          return this.options.humanApprover!(request, context);
        },
        sidecar: this.options.sidecar(),
        onRecordError: (message) => {
          permissionRecordingFailed = true;
          this.options.onError?.(message);
        },
      });
      const session = (this.options.launcher ?? launchAdapter)(
        { id: agent.id, tier: "workspace", dir: workspaceDir, manifest },
        {
          workspaceDir,
          enabledTiers: this.options.enabledTiers(),
          // FR-M44-01/02, AC-52 (MV3-T01b): which binary is about to run,
          // recorded before it runs. Awaited by `launchAdapter`, so a swap
          // is known before the agent has done anything.
          onIdentity: async (identity) => {
            // FR-M44-04 (MV3-T01): verify the pin at LOAD, where load means
            // the moment this agent is about to run.
            //
            // The check used to live only in `discoverAdapters`, which the
            // shipped extension never calls — so the whole verify half was
            // tree-shaken out of the bundle and pinning wrote a digest
            // nothing ever read back. The package check found it: the
            // refusal text was absent from extension.js. A control that
            // does not run is not a control.
            await this.refuseDriftedAdapter(agent.id, workspaceDir);
            await this.recordAgentIdentity(
              agent.id,
              agent.vendor,
              workspaceDir,
              identity,
            );
          },
          approvePermission: async (request, context) => {
            if (
              this.disposed ||
              controller.signal.aborted ||
              !this.capabilities().executionReady
            )
              return { outcome: "cancelled" };
            const decision = await gate(request, context);
            return permissionRecordingFailed ||
              this.disposed ||
              controller.signal.aborted ||
              !this.capabilities().executionReady
              ? { outcome: "cancelled" }
              : decision;
          },
          onUpdate: (notification) => {
            const update = notification.update;
            if (
              update.sessionUpdate === "agent_message_chunk" &&
              update.content.type === "text"
            ) {
              this.output.set(
                run.id,
                ((this.output.get(run.id) ?? "") + update.content.text).slice(
                  0,
                  100_000,
                ),
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
      if (!recorder)
        throw new Error(
          "The sidecar disconnected before the session could be recorded.",
        );
      await recorder.request("acp/sessionBegin", {
        agentId: agent.id,
        agentVersion: agent.version,
        sessionId,
        cwd: workspaceDir,
        startedAt: run.startedAt,
      });
      recordedSession = sessionId;
      const handle = this.sessions.get(run.id);
      if (handle) handle.sessionId = sessionId;
      await this.serialize(async () => {
        const current = this.state.runs.find((entry) => entry.id === run.id);
        if (current) current.sessionId = sessionId;
        if (handle) handle.acceptingSteering = true;
        this.state.revision++;
        await this.persist();
        this.notify();
      });
      if (controller.signal.aborted) return;
      unregister = hostedSessionRegistry.register(sessionId, {
        halt: (reason) => {
          failure = `Governance halted this session: ${reason}`;
          controller.abort();
          session.stop();
        },
      });
      // Hand the live session to the canonical steering controller for the
      // duration of the run. This service owns the lifecycle; the controller
      // owns the protocol, and there is only one of it (AMD-M25 / G-03).
      this.steering()?.adoptSession({
        client: {
          prompt: (id, text) => session.prompt(id, text),
          stop: () => session.stop(),
        },
        sessionId,
        adapterId: agent.id,
      });
      // The briefing was composed once, at queue time, and recorded on the
      // run. It is sent verbatim: composing a second time here would send the
      // agent's instructions and memory twice, and — worse — would mean the
      // prompt in the run history was not the prompt the agent received,
      // which is the whole basis on which a run is reproducible evidence.
      stopReason = await session.prompt(sessionId, run.prompt, {
        signal: controller.signal,
      });
      while (
        stopReason === "end_turn" &&
        !controller.signal.aborted &&
        !this.disposed
      ) {
        const followUp = await this.serialize(async () => {
          const current = this.state.runs.find((entry) => entry.id === run.id);
          const messages =
            current?.steering?.filter((entry) => entry.state === "queued") ??
            [];
          if (!messages.length || current?.state !== "running") {
            if (handle) handle.acceptingSteering = false;
            return undefined;
          }
          for (const entry of messages) entry.state = "sent";
          this.state.revision++;
          await this.persist();
          this.notify();
          return messages
            .map(
              (entry) =>
                `Human steering (ledger #${entry.sequence}):\n${entry.message}`,
            )
            .join("\n\n");
        });
        if (!followUp || controller.signal.aborted) break;
        stopReason = await session.prompt(sessionId, followUp, {
          signal: controller.signal,
        });
      }
    } catch (error) {
      failure = error instanceof Error ? error.message : String(error);
    } finally {
      const handle = this.sessions.get(run.id);
      if (handle) handle.acceptingSteering = false;
      // Give the session back: a finished run must not look steerable.
      if (recordedSession) this.steerController?.release(recordedSession);
      unregister?.();
      this.sessions.get(run.id)?.session.stop();
      this.sessions.delete(run.id);
      if (recordedSession) {
        try {
          const recorder = this.options.sidecar();
          if (!recorder)
            throw new Error(
              "The sidecar disconnected before the session end could be recorded.",
            );
          await recorder.request("acp/sessionEnd", {
            sessionId: recordedSession,
            agentId: run.agentId,
            stopReason: controller.signal.aborted
              ? "cancelled"
              : (stopReason ?? "failed"),
            endedAt: new Date().toISOString(),
          });
        } catch (error) {
          failure ??= (error as Error).message;
          this.options.onError?.(failure);
        }
      }
      await this.serialize(async () => {
        const current = this.state.runs.find((entry) => entry.id === run.id);
        if (!current) return;
        current.output = this.output.get(run.id) ?? "";
        this.output.delete(run.id);
        if (current.state === "running") {
          current.state = controller.signal.aborted
            ? "cancelled"
            : failure
              ? "failed"
              : stopReason === "cancelled"
                ? "cancelled"
                : stopReason === "end_turn"
                  ? "completed"
                  : "failed";
          current.finishedAt = new Date().toISOString();
          if (failure) current.error = failure;
          else if (current.state === "failed")
            current.error = `The agent stopped before completing the task: ${stopReason ?? "no stop reason"}.`;
          if (stopReason) current.stopReason = stopReason;
        }
        this.settleDeliverable(current.deliverableId);
        // Settling may have released runs this deliverable was pinning, and
        // a finished run is itself the largest thing the state file just
        // grew by. Reclaim here rather than only on the next dispatch, so a
        // workspace that stops queueing work does not sit at the ceiling.
        this.pruneRuns();
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
    for (const run of this.state.runs) this.cancelRun(run, "Workbench closed.");
    this.listeners.clear();
    if (this.loadedRoot)
      void this.serialize(async () => {
        this.state.revision++;
        await this.persist();
      }).catch((error: Error) => this.options.onError?.(error.message));
  }
}
