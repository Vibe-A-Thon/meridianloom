import { EventEmitter } from 'node:events';
import {
  ErrorCode,
  PROTOCOL_VERSION,
  type ErrorObject,
  type HandshakeResult,
  type MethodMap,
  type RequestMethod,
  type TierName,
} from '../../shared/ts/bus-types';
import { createFrameDecoder, encodeFrame } from './framing';
import type { ChildProcessLike, ProcessSpawner, SpawnOptions } from './process';
import { defaultSpawner } from './process';
import type { SidecarClient } from './sidecar';

// FR-M32-09: the protocol version comes from the generated bus types, which
// shared/schema/ drives; both halves of the wire read the same constant.
export { PROTOCOL_VERSION };

/**
 * How long the sidecar may take to answer its first handshake.
 *
 * Was ten seconds, which is comfortable on a warm machine and too tight on
 * the case that matters most: the very first launch after installing, on
 * Windows, where the interpreter and every module of `meridian_core` are read
 * from a directory the antivirus has never seen and scans on the way past. A
 * user whose first experience is "the sidecar did not answer" concludes the
 * extension is broken, and they are not obviously wrong.
 *
 * Thirty seconds costs nothing in the normal case — the race resolves as soon
 * as the handshake returns, so a fast start is still fast. What it buys is
 * not failing a cold start that was going to succeed a second later. It
 * surfaced here as a test that failed only under load, which is the same
 * shape as a slow machine.
 */
export const DEFAULT_HANDSHAKE_TIMEOUT_MS = 30_000;

/**
 * Third-party telemetry must not ride in on the editor's environment.
 *
 * The sidecar depends on LangGraph, which brings LangSmith: when its variables
 * are set (LANGSMITH_TRACING=true + an API key — the normal setup for anyone who
 * uses LangSmith elsewhere) every graph run is uploaded to LangChain's cloud.
 * VS Code hands its whole environment to extensions, so a variable exported for
 * an unrelated project used to reach the sidecar and exfiltrate loop state
 * (audit CLD-C01, reproduced). The sidecar scrubs the same families itself on
 * import; doing it here too means the values never reach the process at all.
 */
export const SCRUBBED_ENV_PREFIXES = ['LANGSMITH_', 'LANGCHAIN_', 'LANGGRAPH_'] as const;
export const FORCED_OFF_ENV: Readonly<Record<string, string>> = {
  LANGSMITH_TRACING: 'false',
  LANGSMITH_TRACING_V2: 'false',
  LANGCHAIN_TRACING: 'false',
  LANGCHAIN_TRACING_V2: 'false',
  OTEL_SDK_DISABLED: 'true',
};

/** `base` and `extra` merged, minus telemetry variables, plus the off-switches. */
export function sidecarEnvironment(
  base: NodeJS.ProcessEnv,
  extra: NodeJS.ProcessEnv = {},
): NodeJS.ProcessEnv {
  const merged: NodeJS.ProcessEnv = {};
  for (const source of [base, extra]) {
    for (const [key, value] of Object.entries(source)) {
      // Case-insensitive: Windows environment names are.
      const upper = key.toUpperCase();
      if (SCRUBBED_ENV_PREFIXES.some((prefix) => upper.startsWith(prefix))) continue;
      merged[key] = value;
    }
  }
  return { ...merged, ...FORCED_OFF_ENV };
}

export interface StdioSidecarOptions {
  /** Called when the sidecar refuses a Premium method for want of a licence
   * (LICENCE_REQUIRED). The host uses it to explain and offer to install one;
   * the request still rejects normally. */
  onLicenceRequired?: (data: unknown) => void;
  /** Interpreter command (already resolved; FR-M3-05). */
  command: string;
  /** Package root containing the meridian_core package. */
  cwd: string;
  args?: string[];
  env?: NodeJS.ProcessEnv;
  spawner?: ProcessSpawner;
  /** stderr lines land here; the supervisor routes them to an output channel. */
  onStderr?: (line: string) => void;
  /** ms to wait for the handshake before declaring early-exit. */
  handshakeTimeoutMs?: number;
  /** FR-M36-05: enabled tiers, sent with the handshake; absent = sidecar default. */
  tiers?: readonly TierName[];
  /** FR-M10-01: the workspace whose ledger this sidecar serves. */
  workspaceDir?: string;
  /** FR-M10-04/SEC-06: base64 Ed25519 seed from SecretStorage, provisioned
   * to the sidecar in-memory only (never persisted by it). */
  ledgerSigningKey?: string;
  /** FR-M20-01 (D9): the human identity source the sidecar resolves
   * approver/halting/ingesting identity through — "git" (default; the
   * workspace's user.name/user.email, assurance local) or "oidc"
   * (enterprise stub until the enterprise tier lands). Provisioned over
   * the handshake like the ledger signing key; only meaningful alongside
   * workspaceDir. */
  identityProvider?: string;
}

export class SidecarSpawnError extends Error {
  constructor(
    message: string,
    readonly code: 'SPAWN_ERROR' | 'EARLY_EXIT' | 'HANDSHAKE_TIMEOUT' | 'PROTOCOL_MISMATCH',
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = 'SidecarSpawnError';
  }
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
  abort?: () => void;
}

/**
 * Framed JSON-RPC 2.0 client over the sidecar's stdio (FR-M3-01).
 *
 * Implements the Workstream A `SidecarClient` seam. Requests are matched to
 * responses by id; an AbortSignal rejects the pending promise and sends a
 * `$/cancel` notification so the sidecar can drop the work (FR-M1-09).
 * The client emits 'exit' (code, signal) when the child dies — the
 * supervisor owns restart policy on top of that signal.
 *
 * Remote (FR-M3-11): this client holds no local-machine assumptions. Under
 * VS Code Remote (SSH, WSL, Dev Containers, Codespaces) the extension host
 * runs on the remote host where the repository lives — the extension is
 * `extensionKind: workspace` — so child_process spawn, process.env and the
 * resolved interpreter path are all the remote ones, and stdio framing is
 * identical. There is deliberately no TCP transport to port-forward
 * (FR-M3-10).
 */
export class StdioSidecarClient extends EventEmitter implements SidecarClient {
  private child: ChildProcessLike | undefined;
  private readonly pending = new Map<number, PendingRequest>();
  private nextId = 1;
  private stderrTail = '';
  private started = false;
  private exited = false;

  constructor(private readonly options: StdioSidecarOptions) {
    super();
  }

  get pid(): number | undefined {
    return this.child?.pid;
  }

  /** Spawn the child and complete the protocol handshake (FR-M3-08). */
  async start(): Promise<void> {
    if (this.child) {
      throw new Error('sidecar already started');
    }
    const spawner = this.options.spawner ?? defaultSpawner;
    const spawnOptions: SpawnOptions = {
      command: this.options.command,
      args: this.options.args ?? ['-m', 'meridian_core'],
      cwd: this.options.cwd,
      env: sidecarEnvironment(process.env, {
        MERIDIAN_PARENT_PID: String(process.pid),
        ...this.options.env,
      }),
    };
    let child: ChildProcessLike;
    try {
      child = spawner(spawnOptions);
    } catch (error) {
      throw new SidecarSpawnError(
        `failed to spawn sidecar: ${String(error)}`,
        'SPAWN_ERROR',
        error,
      );
    }
    this.child = child;

    // FR-M3-04: the 'error' event (spawn failure: ENOENT/EACCES/EPERM) is
    // distinct from a non-zero exit; both surface here, classified.
    child.on('error', (error: NodeJS.ErrnoException) => {
      const spawnError = new SidecarSpawnError(
        describeSpawnError(this.options.command, error),
        'SPAWN_ERROR',
        error,
      );
      this.failAll(spawnError);
      // Not 'error': an unlistened EventEmitter 'error' event throws.
      this.emit('spawnError', spawnError);
    });
    child.on('exit', (code: number | null, signal: string | null) => {
      this.exited = true;
      const error = this.started
        ? new Error(`sidecar exited (code=${code} signal=${signal})`)
        : new SidecarSpawnError(
            `sidecar exited during startup (code=${code} signal=${signal}). ` +
              `Recent stderr: ${this.stderrTail || '(empty)'}`,
            'EARLY_EXIT',
          );
      this.failAll(error);
      this.emit('exit', code, signal);
    });

    child.stderr?.setEncoding?.('utf8');
    child.stderr?.on('data', (chunk: string) => {
      this.stderrTail = (this.stderrTail + chunk).slice(-4000);
      for (const line of chunk.split(/\r?\n/)) {
        if (line.length > 0) {
          this.options.onStderr?.(line);
        }
      }
    });

    child.stdout?.setEncoding?.('utf8');
    const decoder = createFrameDecoder();
    child.stdout?.on('data', (chunk: string) => {
      let messages: unknown[];
      try {
        messages = decoder.push(chunk);
      } catch (error) {
        this.failAll(error);
        return;
      }
      for (const message of messages) {
        this.dispatch(message);
      }
    });

    const timeoutMs = this.options.handshakeTimeoutMs ?? DEFAULT_HANDSHAKE_TIMEOUT_MS;
    let timer: NodeJS.Timeout | undefined;
    try {
      await Promise.race([
        this.requestInternal('handshake', {
          protocolVersion: PROTOCOL_VERSION,
          client: 'meridian-loom-extension',
          // FR-M36-05: the workspace's enabled tiers ride the handshake so
          // the sidecar's tier gate is correct from the first request.
          ...(this.options.tiers ? { tiers: [...this.options.tiers] } : {}),
          // FR-M10-01/FR-M10-04: locate the ledger and provision the
          // signing key (OS keychain -> SecretStorage -> handshake; the
          // sidecar keeps both in memory only).
          ...(this.options.workspaceDir ? { workspaceDir: this.options.workspaceDir } : {}),
          ...(this.options.ledgerSigningKey
            ? { ledgerSigningKey: this.options.ledgerSigningKey }
            : {}),
          // FR-M20-01/D9: the identity source of record, provisioned with
          // the handshake (the host owns the choice it can later back with
          // SecretStorage OIDC tokens). Only meaningful with a workspace.
          ...(this.options.workspaceDir && this.options.identityProvider
            ? { identityProvider: this.options.identityProvider }
            : {}),
        }).then((result) => {
          const handshake = result as HandshakeResult;
          if (handshake.protocolVersion !== PROTOCOL_VERSION) {
            throw new SidecarSpawnError(
              `sidecar protocol version ${String(handshake.protocolVersion)} ` +
                `does not match extension version ${PROTOCOL_VERSION}. ` +
                'Reinstall the Meridian Loom extension so both halves ship together.',
              'PROTOCOL_MISMATCH',
            );
          }
        }),
        new Promise((_, reject) => {
          timer = setTimeout(
            () =>
              reject(
                new SidecarSpawnError(
                  `The Meridian sidecar did not answer within ${Math.round(
                    timeoutMs / 1000,
                  )} s. ` +
                    (this.stderrTail
                      ? `It reported: ${this.stderrTail}`
                      : // Silence is the common case and the least helpful
                        // one: the process started and is simply still
                        // importing. Saying "(empty)" told the user nothing
                        // they could act on.
                        'It started but printed nothing, which usually means ' +
                        'it is still starting up — a first launch on Windows ' +
                        'can be slow while the interpreter and its modules ' +
                        'are scanned. Raise meridian.sidecar.handshakeTimeoutMs ' +
                        'if this persists, or run Meridian Loom: Doctor to check ' +
                        'the interpreter.'),
                  'HANDSHAKE_TIMEOUT',
                ),
              ),
            timeoutMs,
          );
        }),
      ]);
    } catch (error) {
      this.kill();
      throw error;
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }
    this.started = true;
  }

  async request<TResponse>(
    method: string,
    params: unknown,
    signal: AbortSignal,
  ): Promise<TResponse> {
    if (signal.aborted) {
      throw new DOMException('request aborted', 'AbortError');
    }
    return this.requestInternal(method, params, signal) as Promise<TResponse>;
  }

  /**
   * Schema-typed request (FR-M32-09): params and result are paired by the
   * generated MethodMap, so a contract change is a compile error here.
   */
  call<M extends RequestMethod>(
    method: M,
    params: MethodMap[M]['params'],
    signal: AbortSignal,
  ): Promise<MethodMap[M]['result']> {
    return this.request(method, params, signal);
  }

  private requestInternal(
    method: string,
    params: unknown,
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (!this.child?.stdin || this.exited) {
      return Promise.reject(new Error('sidecar is not running'));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const entry: PendingRequest = { resolve, reject };
      this.pending.set(id, entry);
      if (signal) {
        const onAbort = () => {
          if (this.pending.delete(id)) {
            this.write({ jsonrpc: '2.0', method: '$/cancel', params: { id } });
            reject(new DOMException('request aborted', 'AbortError'));
          }
        };
        entry.abort = onAbort;
        signal.addEventListener('abort', onAbort, { once: true });
      }
      this.write({ jsonrpc: '2.0', id, method, params });
    });
  }

  private write(message: unknown): void {
    this.child?.stdin?.write?.(encodeFrame(message));
  }

  private dispatch(message: unknown): void {
    const frame = message as {
      id?: number;
      result?: unknown;
      error?: ErrorObject;
      method?: string;
      params?: unknown;
    };
    if (typeof frame.id === 'number' && ('result' in frame || 'error' in frame)) {
      const entry = this.pending.get(frame.id);
      if (!entry) {
        return;
      }
      this.pending.delete(frame.id);
      if (frame.error) {
        const error = new Error(frame.error.message);
        Object.assign(error, { code: frame.error.code, data: frame.error.data });
        if (frame.error.code === ErrorCode.LICENCE_REQUIRED) {
          try {
            this.options.onLicenceRequired?.(frame.error.data);
          } catch {
            // Presentation must never turn a refusal into a different failure.
          }
        }
        entry.reject(error);
      } else {
        entry.resolve(frame.result);
      }
    } else if (typeof frame.method === 'string') {
      this.emit('notification', frame.method, frame.params);
    }
  }

  private failAll(error: unknown): void {
    for (const entry of this.pending.values()) {
      entry.reject(error);
    }
    this.pending.clear();
  }

  /**
   * Fire-and-forget notification (e.g. tiers/set after a config change,
   * FR-M36-05). No-op when the sidecar is gone.
   */
  notify(method: string, params: unknown): void {
    this.write({ jsonrpc: '2.0', method, params });
  }

  /** Hard kill without escalation; the supervisor owns graceful teardown. */
  kill(): void {
    try {
      this.child?.kill();
    } catch {
      // already dead
    }
  }
}

/** FR-M3-04: actionable diagnostics per spawn failure class. */
export function describeSpawnError(command: string, error: NodeJS.ErrnoException): string {
  switch (error.code) {
    case 'ENOENT':
      return (
        `Python interpreter not found at '${command}'. Install Python 3.11+ ` +
        'or set the meridian.python.interpreterPath setting to a valid interpreter.'
      );
    case 'EACCES':
      return (
        `Permission denied spawning '${command}'. Check the file is executable ` +
        'and that no security policy is blocking it.'
      );
    case 'EPERM':
      return (
        `Spawning '${command}' was blocked by policy (EPERM). Check antivirus, ` +
        'AppLocker, or your organisation\'s execution policy, or point ' +
        'meridian.python.interpreterPath at an allowed interpreter.'
      );
    default:
      return `Failed to spawn sidecar interpreter '${command}': ${error.message}`;
  }
}
