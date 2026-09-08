/**
 * ACP host client (FR-M34-01) — the Agent Client Protocol host side,
 * running in the extension host. Spawns an ACP-conformant agent subprocess
 * and drives it over newline-delimited JSON-RPC on stdio, using the
 * official `@zed-industries/agent-client-protocol` ClientSideConnection for
 * the wire (see protocol.ts for the pinned version and capability set).
 *
 * Responsibilities beyond the raw connection:
 *
 *  - lifecycle: spawn → initialize handshake with protocol-version
 *    negotiation → session/new | session/load → session/prompt → teardown
 *    (Windows-robust: tree kills via taskkill /T, never a shell wrapper);
 *  - streaming: session/update notifications are re-emitted as 'update'
 *    events (message chunks, tool calls, plans);
 *  - permission gate: every session/request_permission from the agent goes
 *    through an injectable host approver BEFORE the agent may proceed. In
 *    production that approver is a vscode window prompt (permissions.ts);
 *    tests inject a fake. The DEFAULT is deny.
 *  - client-provided fs/terminal access: fs/read_text_file and
 *    fs/write_text_file are served from the user's workspace root with a
 *    path-escape guard; terminal/* commands are spawned through the host,
 *    also rooted at the workspace.
 *  - failure honesty: an agent crash mid-turn rejects the in-flight
 *    request with a clean, named error (never a hang).
 *
 * This module is governor tier — the extension wires the tier check at the
 * entry point (index.ts); a disabled governor means no hosted sessions (G5).
 * It contains no model client of any kind (FR-M36-07 holds by nature).
 */
import { spawn, type ChildProcess } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { promises as fsp } from 'node:fs';
import path from 'node:path';
import { Readable, Writable } from 'node:stream';
import {
  ClientSideConnection,
  ndJsonStream,
  RequestError,
  type Client,
  type CreateTerminalRequest,
  type CreateTerminalResponse,
  type InitializeResponse,
  type KillTerminalCommandRequest,
  type PromptResponse,
  type ReadTextFileRequest,
  type ReadTextFileResponse,
  type ReleaseTerminalRequest,
  type RequestPermissionRequest,
  type RequestPermissionResponse,
  type SessionNotification,
  type TerminalOutputRequest,
  type WaitForTerminalExitRequest,
  type WriteTextFileRequest,
} from '@zed-industries/agent-client-protocol';
import { killProcessTree } from '../supervisor';
import { ACP_CLIENT_CAPABILITIES, ACP_PROTOCOL_VERSION } from './protocol';

export type AcpErrorCode =
  | 'SPAWN_ERROR'
  | 'HANDSHAKE_TIMEOUT'
  | 'PROTOCOL_VERSION_REFUSED'
  | 'AGENT_CRASHED'
  | 'NOT_RUNNING'
  | 'LOAD_SESSION_UNSUPPORTED'
  | 'PATH_OUTSIDE_WORKSPACE';

export class AcpError extends Error {
  constructor(
    message: string,
    readonly code: AcpErrorCode,
    options?: { cause?: unknown; data?: Record<string, unknown> },
  ) {
    super(message, options);
    this.name = 'AcpError';
  }
}

/** The host's answer to an agent permission request. */
export type AcpPermissionDecision =
  | { outcome: 'selected'; optionId: string }
  | { outcome: 'cancelled' };

/**
 * The approval path for tool execution (FR-M34-01: the host MUST approve
 * before the agent proceeds). Injected by callers: vscode window prompts
 * in production (permissions.ts), fakes in tests. Receives the full ACP
 * request so the UI can show exactly what the agent asked for.
 */
export type PermissionApprover = (
  request: RequestPermissionRequest,
  context: { signal?: AbortSignal },
) => Promise<AcpPermissionDecision>;

export interface AcpSpawnOptions {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export type AcpSpawner = (options: AcpSpawnOptions) => ChildProcess;

export interface AcpClientOptions {
  /** Agent executable (ACP-conformant). */
  command: string;
  args?: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  /** The user's workspace; fs and terminal access are rooted here. */
  workspaceDir: string;
  /** Tool-approval path; absent means deny-by-default. */
  approvePermission?: PermissionApprover;
  onStderr?: (line: string) => void;
  spawner?: AcpSpawner;
  /** Whole-tree kill; defaults to taskkill /T on Windows, SIGKILL elsewhere. */
  killTree?: (pid: number) => void;
  /** ms to wait for the initialize response. */
  handshakeTimeoutMs?: number;
  /**
   * Turn-boundary governance gate (FR-M39-02, D33: spend-ceiling pause).
   * ACP has no pause primitive, so a pause-pending session refuses its
   * NEXT turn here — an honest checkpoint, never a mid-flight cancel. May
   * throw (e.g. SpendCeilingPausePendingError) to refuse the turn.
   */
  checkpointGate?: (sessionId: string) => void;
}

interface TerminalRecord {
  child: ChildProcess;
  buffer: string;
  truncated: boolean;
  byteLimit: number | null;
  exited: boolean;
  exitStatus: { exitCode: number | null; signal: string | null };
  spawnError: Error | null;
  exitPromise: Promise<{ exitCode: number | null; signal: string | null }>;
}

/**
 * Resolve a client-supplied path against the workspace root, refusing
 * escapes. The ACP spec passes absolute paths; relative ones are treated as
 * workspace-relative. Exported for direct unit testing of the guard.
 */
export function resolveWorkspacePath(workspaceDir: string, requested: string): string {
  const root = path.resolve(workspaceDir);
  const abs = path.resolve(root, requested);
  const rel = path.relative(root, abs);
  if (rel !== '' && (rel.startsWith('..') || path.isAbsolute(rel))) {
    throw new AcpError(
      `refusing access outside the workspace: '${requested}'`,
      'PATH_OUTSIDE_WORKSPACE',
      { data: { reason: 'path_outside_workspace', workspaceDir: root, requested } },
    );
  }
  return abs;
}

/** Deny by default: pick the agent's reject option if it offered one. */
const denyByDefault: PermissionApprover = async (request) => {
  const reject = request.options.find((option) => option.kind.startsWith('reject'));
  if (!reject) {
    throw new RequestError(-32603, 'no permission approver configured (default deny)', {
      reason: 'no_permission_approver',
    });
  }
  return { outcome: 'selected', optionId: reject.optionId };
};

/** Race a permission decision against turn cancellation. */
async function decideWithCancellation(
  approver: PermissionApprover,
  request: RequestPermissionRequest,
  signal: AbortSignal | undefined,
): Promise<AcpPermissionDecision> {
  if (!signal) {
    return approver(request, {});
  }
  return new Promise<AcpPermissionDecision>((resolve, reject) => {
    const onAbort = () => resolve({ outcome: 'cancelled' });
    signal.addEventListener('abort', onAbort, { once: true });
    Promise.resolve(approver(request, { signal })).then(
      (decision) => {
        signal.removeEventListener('abort', onAbort);
        resolve(decision);
      },
      (error: unknown) => {
        signal.removeEventListener('abort', onAbort);
        reject(error);
      },
    );
  });
}

export class AcpClient extends EventEmitter {
  private child: ChildProcess | undefined;
  private connection: ClientSideConnection | undefined;
  private initialized = false;
  private exited = false;
  private stopped = false;
  private exitInfo: { code: number | null; signal: string | null } | undefined;
  private stderrTail = '';
  private agentCapabilities: InitializeResponse['agentCapabilities'];
  private readonly terminals = new Map<string, TerminalRecord>();
  private nextTerminalId = 1;
  /** Rejects when the child dies while a request is in flight. */
  private death: Promise<never> = Promise.reject(new Error('not started'));
  private rejectDeath: (error: Error) => void = () => undefined;
  /** Signal of the prompt turn currently in flight, if any. */
  private turnSignal: AbortSignal | undefined;

  constructor(private readonly options: AcpClientOptions) {
    super();
    // The initial placeholder rejection is expected; attach a no-op so it is
    // never surfaced as an unhandled rejection before start() replaces it.
    this.death.catch(() => undefined);
  }

  get pid(): number | undefined {
    return this.child?.pid;
  }

  get agentInfo(): InitializeResponse['agentCapabilities'] {
    return this.agentCapabilities;
  }

  /** Spawn the agent and complete the initialize handshake. */
  async start(): Promise<InitializeResponse> {
    if (this.child) {
      throw new Error('ACP agent already started');
    }
    this.death = new Promise<never>((_, reject) => {
      this.rejectDeath = reject;
    });
    this.death.catch(() => undefined);

    const spawner: AcpSpawner =
      this.options.spawner ??
      ((spawnOptions) =>
        spawn(spawnOptions.command, spawnOptions.args, {
          cwd: spawnOptions.cwd,
          env: spawnOptions.env,
          shell: false,
          stdio: ['pipe', 'pipe', 'pipe'],
          windowsHide: true,
        }));
    let child: ChildProcess;
    try {
      child = spawner({
        command: this.options.command,
        args: this.options.args ?? [],
        cwd: this.options.cwd ?? this.options.workspaceDir,
        env: { ...process.env, ...this.options.env },
      });
    } catch (error) {
      throw new AcpError(`failed to spawn ACP agent: ${String(error)}`, 'SPAWN_ERROR', {
        cause: error,
      });
    }
    this.child = child;

    child.stderr?.setEncoding('utf8');
    child.stderr?.on('data', (chunk: string) => {
      this.stderrTail = (this.stderrTail + chunk).slice(-4000);
      for (const line of chunk.split(/\r?\n/)) {
        if (line.length > 0) {
          this.options.onStderr?.(line);
        }
      }
    });

    const onSpawnError = (error: NodeJS.ErrnoException) => {
      this.rejectDeath(
        new AcpError(`failed to spawn ACP agent '${this.options.command}': ${error.message}`, 'SPAWN_ERROR', {
          cause: error,
          data: { errno: error.code },
        }),
      );
    };
    child.once('error', onSpawnError);
    child.on('exit', (code, signal) => {
      this.exited = true;
      this.exitInfo = { code, signal };
      this.rejectDeath(this.exitError());
      for (const terminalId of [...this.terminals.keys()]) {
        this.killTerminalById(terminalId);
      }
      this.emit('exit', code, signal);
    });

    if (!child.stdin || !child.stdout) {
      this.kill();
      throw new AcpError('ACP agent stdio is not piped', 'SPAWN_ERROR');
    }

    // Wire the ND-JSON ACP stream over the child's stdio. No shell wrapper:
    // signal delivery and teardown stay direct (Windows: tree kill).
    const stream = ndJsonStream(
      Writable.toWeb(child.stdin) as WritableStream<Uint8Array>,
      Readable.toWeb(child.stdout) as ReadableStream<Uint8Array>,
    );

    this.connection = new ClientSideConnection(() => this.clientHandler(), stream);

    const timeoutMs = this.options.handshakeTimeoutMs ?? 10_000;
    let response: InitializeResponse;
    try {
      response = await this.guard(
        withTimeout(
          this.connection.initialize({
            protocolVersion: ACP_PROTOCOL_VERSION,
            clientCapabilities: ACP_CLIENT_CAPABILITIES,
          }),
          timeoutMs,
          () =>
            new AcpError(
              `ACP agent did not answer initialize within ${timeoutMs} ms. ` +
                `Recent stderr: ${this.stderrTail || '(empty)'}`,
              'HANDSHAKE_TIMEOUT',
            ),
        ),
      );
    } catch (error) {
      this.kill();
      throw error;
    }

    // Version negotiation per the ACP spec: the agent echoes our version
    // when it supports it, otherwise it answers with its own latest — which
    // we do not support, so we close and report (futures.md: pin what we
    // implement).
    if (response.protocolVersion !== ACP_PROTOCOL_VERSION) {
      this.kill();
      throw new AcpError(
        `ACP agent '${this.options.command}' speaks protocol version ` +
          `${String(response.protocolVersion)}; this host supports version ` +
          `${ACP_PROTOCOL_VERSION} only.`,
        'PROTOCOL_VERSION_REFUSED',
        { data: { expected: ACP_PROTOCOL_VERSION, offered: response.protocolVersion } },
      );
    }
    this.agentCapabilities = response.agentCapabilities;
    this.initialized = true;
    return response;
  }

  // -- session lifecycle ------------------------------------------------------

  async newSession(cwd?: string): Promise<string> {
    this.assertUsable();
    const response = await this.guard(
      this.connection!.newSession({
        cwd: cwd ?? this.options.workspaceDir,
        mcpServers: [],
      }),
    );
    return response.sessionId;
  }

  async loadSession(sessionId: string, cwd?: string): Promise<void> {
    this.assertUsable();
    // session/load is optional in ACP; the agent advertises it at initialize.
    if (!this.agentCapabilities?.loadSession) {
      throw new AcpError(
        `ACP agent '${this.options.command}' does not advertise the loadSession capability`,
        'LOAD_SESSION_UNSUPPORTED',
      );
    }
    await this.guard(
      this.connection!.loadSession({
        sessionId,
        cwd: cwd ?? this.options.workspaceDir,
        mcpServers: [],
      }),
    );
  }

  /**
   * Send one user prompt and resolve with the stop reason when the turn
   * ends. While the turn is in flight, `signal` aborts send
   * `session/cancel` and answers any pending permission request with the
   * `cancelled` outcome, per the ACP cancellation rules.
   */
  async prompt(
    sessionId: string,
    text: string,
    options?: { signal?: AbortSignal },
  ): Promise<PromptResponse['stopReason']> {
    this.assertUsable();
    const signal = options?.signal;
    if (signal?.aborted) {
      throw new DOMException('prompt aborted', 'AbortError');
    }
    // FR-M39-02 (D33): the checkpoint gate refuses a new turn for a
    // pause-pending session before anything goes on the wire.
    this.options.checkpointGate?.(sessionId);
    const onAbort = () => {
      void this.connection?.cancel({ sessionId });
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    this.turnSignal = signal;
    try {
      const response = await this.guard(
        this.connection!.prompt({ sessionId, prompt: [{ type: 'text', text }] }),
      );
      return response.stopReason;
    } finally {
      signal?.removeEventListener('abort', onAbort);
      if (this.turnSignal === signal) {
        this.turnSignal = undefined;
      }
    }
  }

  // -- teardown -----------------------------------------------------------------

  /**
   * Kill the agent and every terminal it was granted. Always safe to call;
   * never throws.
   */
  stop(): void {
    if (this.stopped) {
      return;
    }
    this.stopped = true;
    for (const terminalId of [...this.terminals.keys()]) {
      this.killTerminalById(terminalId);
    }
    this.child?.stdin?.end();
    this.kill();
  }

  /** Kill the agent process tree (taskkill /T on Windows, SIGKILL elsewhere). */
  kill(): void {
    const pid = this.child?.pid;
    try {
      if (pid !== undefined) {
        (this.options.killTree ?? killProcessTree)(pid);
      } else {
        this.child?.kill();
      }
    } catch {
      // already dead
    }
  }

  // -- ACP Client handler (agent → host requests) -------------------------------

  private clientHandler(): Client {
    return {
      sessionUpdate: (params: SessionNotification) => {
        this.emit('update', params);
        return Promise.resolve();
      },
      requestPermission: (params) => this.handlePermissionRequest(params),
      readTextFile: (params) => this.readTextFile(params),
      writeTextFile: (params) => this.writeTextFile(params),
      createTerminal: (params) => this.createTerminal(params),
      terminalOutput: (params) => this.terminalOutput(params),
      waitForTerminalExit: (params) => this.waitForTerminalExit(params),
      killTerminal: (params) => this.killTerminal(params),
      releaseTerminal: (params) => this.releaseTerminal(params),
    };
  }

  private async handlePermissionRequest(
    params: RequestPermissionRequest,
  ): Promise<RequestPermissionResponse> {
    const approver = this.options.approvePermission ?? denyByDefault;
    const decision = await decideWithCancellation(approver, params, this.turnSignal);
    // The ACP response nests the decision: { outcome: { outcome, optionId? } }.
    return { outcome: decision };
  }

  // -- client-provided file system (rooted at the workspace) ---------------------

  private async readTextFile(
    params: ReadTextFileRequest,
  ): Promise<ReadTextFileResponse> {
    const abs = resolveWorkspacePath(this.options.workspaceDir, params.path);
    let content: string;
    try {
      content = await fsp.readFile(abs, 'utf8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        throw RequestError.resourceNotFound(params.path);
      }
      throw error;
    }
    // ACP line window: 1-based start line + max line count.
    if (params.line != null || params.limit != null) {
      const lines = content.split('\n');
      const start = Math.max(1, params.line ?? 1) - 1;
      const end = params.limit != null ? start + Math.max(0, params.limit) : lines.length;
      content = lines.slice(start, end).join('\n');
    }
    return { content };
  }

  private async writeTextFile(
    params: WriteTextFileRequest,
  ): Promise<Record<string, never>> {
    const abs = resolveWorkspacePath(this.options.workspaceDir, params.path);
    await fsp.mkdir(path.dirname(abs), { recursive: true });
    await fsp.writeFile(abs, params.content, 'utf8');
    return {};
  }

  // -- client-provided terminals (rooted at the workspace) ------------------------

  private async createTerminal(
    params: CreateTerminalRequest,
  ): Promise<CreateTerminalResponse> {
    const cwd = resolveWorkspacePath(this.options.workspaceDir, params.cwd ?? this.options.workspaceDir);
    const env: NodeJS.ProcessEnv = { ...process.env };
    for (const variable of params.env ?? []) {
      env[variable.name] = variable.value;
    }
    const child = spawn(params.command, params.args ?? [], {
      cwd,
      env,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    const record: TerminalRecord = {
      child,
      buffer: '',
      truncated: false,
      byteLimit: params.outputByteLimit ?? null,
      exited: false,
      exitStatus: { exitCode: null, signal: null },
      spawnError: null,
      exitPromise: new Promise<{ exitCode: number | null; signal: string | null }>(
        (resolve, reject) => {
          child.once('error', (error) => {
            record.spawnError = error;
            reject(error);
          });
          child.on('exit', (exitCode, signal) => {
            record.exited = true;
            record.exitStatus = { exitCode, signal };
            resolve({ exitCode, signal });
          });
        },
      ),
    };
    const append = (chunk: Buffer): void => {
      record.buffer += chunk.toString('utf8');
      if (record.byteLimit != null) {
        // Truncate from the beginning, at a character boundary.
        while (record.buffer.length > 0 && Buffer.byteLength(record.buffer, 'utf8') > record.byteLimit) {
          record.buffer = record.buffer.slice(Math.max(1, Math.floor(record.buffer.length / 4)));
          record.truncated = true;
        }
      }
    };
    child.stdout?.on('data', append);
    child.stderr?.on('data', append);
    const terminalId = `terminal-${this.nextTerminalId++}`;
    this.terminals.set(terminalId, record);
    return { terminalId };
  }

  private terminalOutput(params: TerminalOutputRequest): Promise<{
    output: string;
    truncated: boolean;
    exitStatus: { exitCode: number | null; signal: string | null } | null;
  }> {
    const record = this.mustGetTerminal(params.terminalId);
    return Promise.resolve({
      output: record.buffer,
      truncated: record.truncated,
      exitStatus: record.exited ? record.exitStatus : null,
    });
  }

  private async waitForTerminalExit(
    params: WaitForTerminalExitRequest,
  ): Promise<{ exitCode: number | null; signal: string | null }> {
    const record = this.mustGetTerminal(params.terminalId);
    return record.exitPromise;
  }

  private async killTerminal(params: KillTerminalCommandRequest): Promise<Record<string, never>> {
    const record = this.mustGetTerminal(params.terminalId);
    this.killTerminalProcess(record);
    return {};
  }

  private async releaseTerminal(params: ReleaseTerminalRequest): Promise<Record<string, never>> {
    const record = this.mustGetTerminal(params.terminalId);
    this.killTerminalProcess(record);
    this.terminals.delete(params.terminalId);
    return {};
  }

  private mustGetTerminal(terminalId: string): TerminalRecord {
    const record = this.terminals.get(terminalId);
    if (!record) {
      throw RequestError.resourceNotFound(terminalId);
    }
    return record;
  }

  private killTerminalById(terminalId: string): void {
    const record = this.terminals.get(terminalId);
    if (record) {
      this.killTerminalProcess(record);
      this.terminals.delete(terminalId);
    }
  }

  /** Windows-robust kill: child.kill() only reaches the direct child there. */
  private killTerminalProcess(record: TerminalRecord): void {
    const pid = record.child.pid;
    try {
      if (pid !== undefined) {
        (this.options.killTree ?? killProcessTree)(pid);
      } else {
        record.child.kill();
      }
    } catch {
      // already dead
    }
  }

  // -- plumbing -------------------------------------------------------------------

  private assertUsable(): void {
    if (!this.initialized || !this.connection) {
      throw new AcpError('ACP agent is not initialized — call start() first', 'NOT_RUNNING');
    }
    if (this.exited) {
      throw this.exitError();
    }
  }

  private exitError(): AcpError {
    const { code, signal } = this.exitInfo ?? { code: null, signal: null };
    return new AcpError(
      `ACP agent '${this.options.command}' exited unexpectedly ` +
        `(code=${code} signal=${signal}). Recent stderr: ${this.stderrTail || '(empty)'}`,
      'AGENT_CRASHED',
      { data: { code, signal } },
    );
  }

  /** Fail in-flight agent requests cleanly when the child dies. */
  private guard<T>(promise: Promise<T>): Promise<T> {
    if (this.exited) {
      return Promise.reject(this.exitError());
    }
    return Promise.race([promise, this.death]);
  }
}

async function withTimeout<T>(promise: Promise<T>, ms: number, onTimeout: () => Error): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(onTimeout()), ms);
      }),
    ]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}
