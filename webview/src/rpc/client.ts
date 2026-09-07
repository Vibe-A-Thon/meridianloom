import type { HostMessage, WebviewMessage, WebviewRpcError } from '../../../shared/ts/webview-messages';
import { WEBVIEW_PROTOCOL_VERSION } from '../../../shared/ts/webview-messages';
import type { MethodMap, RequestId, RequestMethod } from '../../../shared/ts/bus-types';
import type { WorkbenchAction, WorkbenchActionMap } from '../../../shared/ts/workbench';

/**
 * Thin typed client over the extension↔webview postMessage channel.
 * The webview never touches the sidecar directly (VIGUIX_Final §17): every
 * RPC is a WebviewMessage the host proxies to the sidecar, and the answer
 * comes back correlated by id on this client.
 *
 * This module is React-free on purpose — the extension's e2e suite imports
 * it to drive a real sidecar through the same code the app runs.
 */

/** PostMessage-shaped transport; acquireVsCodeApi() satisfies the send half. */
export interface RpcTransport {
  postMessage(message: WebviewMessage): void;
  /** Subscribe to inbound host messages; returns an unsubscribe. */
  onMessage(handler: (message: HostMessage) => void): () => void;
}

/** Structured error, end to end: the sidecar's JSON-RPC code survives the
 *  hop through the extension host so the UI can tell "tier disabled" apart
 *  from "sidecar down" (X-14: each has its own surface). */
export class RpcError extends Error {
  constructor(
    readonly code: number,
    message: string,
    readonly data?: unknown,
  ) {
    super(message);
    this.name = 'RpcError';
  }

  static from(error: WebviewRpcError): RpcError {
    return new RpcError(error.code, error.message, error.data);
  }
}

export class RpcProtocolError extends Error {
  constructor(
    readonly expected: number,
    readonly actual: number,
  ) {
    super(
      `Webview protocol mismatch: host speaks v${actual}, the webview requires v${expected}. ` +
        'Reload the window; if this persists, the extension and webview were built from different commits.',
    );
    this.name = 'RpcProtocolError';
  }
}

export interface RpcClientOptions {
  timeoutMs?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
}

export class WebviewRpcClient {
  private nextId = 1;
  private readonly pending = new Map<RequestId, PendingRequest>();
  private readonly listeners = new Set<(message: HostMessage) => void>();
  private readonly unsubscribe: () => void;

  constructor(
    private readonly transport: RpcTransport,
    private readonly options: RpcClientOptions = {},
  ) {
    this.unsubscribe = transport.onMessage((message) => this.onHostMessage(message));
  }

  /** The version this client speaks; sent with `ready` and checked on `init`. */
  get protocolVersion(): number {
    return WEBVIEW_PROTOCOL_VERSION;
  }

  /**
   * The version the host reported in its init payload. Undefined until init
   * arrives — the app must not issue RPCs before that (the host drops them,
   * and the app renders its loading state rather than guessing).
   */
  hostProtocolVersion: number | undefined;

  /**
   * Subscribe to every inbound host message (init, events). This is the
   * single subscription point for app-level concerns — the app never
   * touches window 'message' directly, so tests can drive it through the
   * same transport the app uses.
   */
  addListener(handler: (message: HostMessage) => void): () => void {
    this.listeners.add(handler);
    return () => {
      this.listeners.delete(handler);
    };
  }

  /** Fire-and-forget messages (the `ready` handshake, state updates). */
  notify(message: WebviewMessage): void {
    this.transport.postMessage(message);
  }

  request<M extends RequestMethod>(
    method: M,
    params: MethodMap[M]['params'],
  ): Promise<MethodMap[M]['result']> {
    const id = this.nextId++ as RequestId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(
          new RpcError(
            -32010,
            `No answer from the extension host for '${method}' within ${this.options.timeoutMs ?? 30_000}ms.`,
          ),
        );
      }, this.options.timeoutMs ?? 30_000);
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject, timer });
      this.transport.postMessage({ type: 'rpc/request', id, method, params });
    });
  }

  /** Workspace management is hosted by the extension, independently of the sidecar. */
  workbench<A extends WorkbenchAction>(
    action: A,
    params: WorkbenchActionMap[A]['params'],
  ): Promise<WorkbenchActionMap[A]['result']> {
    const id = this.nextId++ as RequestId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new RpcError(-32010, `The workspace did not answer '${action}'. Try again.`));
      }, this.options.timeoutMs ?? 30_000);
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject, timer });
      this.transport.postMessage({ type: 'workbench/request', id, action, params });
    });
  }

  /** Tear down timers and subscriptions (tests call this; React unmount too). */
  dispose(): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(new RpcError(-32011, 'RPC client disposed with requests in flight.'));
      this.pending.delete(id);
    }
    this.unsubscribe();
  }

  private onHostMessage(message: HostMessage): void {
    for (const listener of [...this.listeners]) {
      listener(message);
    }
    if (message.type === 'init') {
      this.hostProtocolVersion = message.init.protocolVersion;
      return;
    }
    if (message.type !== 'rpc/response') {
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) {
      return;
    }
    this.pending.delete(message.id);
    clearTimeout(pending.timer);
    if (message.error) {
      pending.reject(RpcError.from(message.error));
    } else {
      pending.resolve(message.result);
    }
  }
}

/**
 * Assert the host's init version before first render of real data. A
 * mismatch renders a visible protocol error — never a silent half-UI.
 */
export function assertProtocolCompatible(client: WebviewRpcClient): void {
  if (
    client.hostProtocolVersion !== undefined &&
    client.hostProtocolVersion !== WEBVIEW_PROTOCOL_VERSION
  ) {
    throw new RpcProtocolError(WEBVIEW_PROTOCOL_VERSION, client.hostProtocolVersion);
  }
}
