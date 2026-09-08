import { ErrorCode } from '../../../shared/ts/bus-types';
import type { TierName } from '../../../shared/ts/bus-types';
import {
  WEBVIEW_PROTOCOL_VERSION,
  isWebviewMessage,
  type HostMessage,
  type WebviewRpcError,
} from '../../../shared/ts/webview-messages';
import { capabilityForRpcMethod, isRpcMethodEnabled } from '../../../shared/ts/tiers';
import type { WorkbenchRequest } from '../../../shared/ts/workbench';

/**
 * The extension-host half of the webview message bus (G0c/G0d). Pure by
 * construction: it knows nothing about vscode, so both the panel class and
 * the e2e suite drive the exact same code the production host runs.
 *
 * The webview never talks to the sidecar directly (VIGUIX_Final §17); every
 * request passes this gate, where the tier check (X-28/FR-M36-05) is applied
 * before the RPC reaches the sidecar. The sidecar enforces the same gate,
 * so a refused call here is defence in depth, not the only wall.
 */

/** The slice of StdioSidecarClient the proxy needs. */
export interface SidecarRequestor {
  request(method: string, params: unknown, signal?: AbortSignal): Promise<unknown>;
}

export interface ProxyContext {
  /** FR-M36-05: enabled tiers, read lazily so a settings change applies to
   *  the very next request. */
  enabledTiers(): readonly TierName[];
  /** Undefined while the sidecar is not up — requests surface that
   *  structured failure instead of hanging. */
  sidecar: SidecarRequestor | undefined;
  /** The workspace folder the sidecar was pointed at; handed to the webview
   *  in `init` so attrib/hook RPCs get a real repoPath. */
  workspaceDir?: () => string | undefined;
  /** 10.45/10.7 Export: persists a downloaded audit bundle through the
   *  host's save dialog (the webview has no filesystem, VIGUIX_Final §17). */
  saveFile?: (fileName: string, content: string, mimeType?: string) => void | Promise<void>;
  openEditor?: (path: string, line?: number) => Promise<void>;
  /** Local workspace management survives a sidecar reconnect. Execution is
   * separately checked by the service against workspace trust and tiers. */
  workbench?: (request: WorkbenchRequest) => Promise<unknown>;
  hostAction?: (action: 'open-settings' | 'open-folder') => Promise<void>;
}

function toErrorObject(error: unknown): WebviewRpcError {
  const candidate = error as { code?: unknown; message?: unknown; data?: unknown };
  if (typeof candidate?.code === 'number' && typeof candidate?.message === 'string') {
    return { code: candidate.code, message: candidate.message, data: candidate.data };
  }
  return {
    code: ErrorCode.INTERNAL_ERROR,
    message: error instanceof Error ? error.message : String(error),
  };
}

/**
 * Handle one inbound webview message. Resolves with the message to post
 * back, or undefined when the inbound message is not recognisably ours
 * (dropped — the webview is untrusted input too).
 */
export async function dispatchWebviewMessage(
  message: unknown,
  context: ProxyContext,
): Promise<HostMessage | undefined> {
  if (!isWebviewMessage(message)) {
    return undefined;
  }
  if (message.type === 'ready') {
    // Only explicit, allow-listed native actions cross this boundary.
    const workspaceDir = context.workspaceDir?.();
    return {
      type: 'init',
      init: {
        protocolVersion: WEBVIEW_PROTOCOL_VERSION,
        enabledTiers: [...context.enabledTiers()],
        ...(workspaceDir ? { workspaceDir } : {}),
      },
    };
  }
  if (message.type === 'download') {
    // Export (FR-M36-04): the bundle is already signed and in the webview's
    // hands; the host only offers the save dialog. Fire-and-forget — there
    // is nothing to ack, and a save failure surfaces host-side.
    await context.saveFile?.(message.fileName, message.content, message.mimeType);
    return undefined;
  }
  if (message.type === 'host/action') {
    await context.hostAction?.(message.action);
    return undefined;
  }
  if (message.type === 'editor/open') {
    await context.openEditor?.(message.path, message.line);
    return undefined;
  }
  if (message.type === 'state/update') {
    // Panel state lives in the webview's own getState/setState (VIGUIX_Final
    // §17); a host-side mirror is not needed for GF0. Acknowledge nothing —
    // state/update is fire-and-forget.
    return undefined;
  }
  if (message.type === 'workbench/request') {
    try {
      if (!context.workbench) {
        throw new Error('The workspace workbench is not available. Reopen the Meridian panel.');
      }
      const result = await context.workbench({ action: message.action, params: message.params });
      return { type: 'rpc/response', id: message.id, result };
    } catch (error) {
      return { type: 'rpc/response', id: message.id, error: toErrorObject(error) };
    }
  }

  const { method, params, id } = message;
  const enabled = context.enabledTiers();
  if (!isRpcMethodEnabled(method, enabled)) {
    const capability = capabilityForRpcMethod(method);
    return {
      type: 'rpc/response',
      id,
      error: {
        code: ErrorCode.TIER_DISABLED,
        message:
          `'${method}' belongs to the ${capability?.tier ?? 'unknown'} tier, which is ` +
          'not enabled in this workspace. Enable it in the meridian.tiers setting.',
        data: { method, tier: capability?.tier ?? null },
      },
    };
  }
  if (!context.sidecar) {
    return {
      type: 'rpc/response',
      id,
      error: {
        code: ErrorCode.INTERNAL_ERROR,
        message:
          'The Meridian sidecar is not connected, so the recorder cannot answer ' +
          `'${method}' yet. It starts with the extension — retry in a moment, ` +
          'or run Meridian: Doctor if it never comes up.',
        data: { method },
      },
    };
  }
  try {
    const result = await context.sidecar.request(method, params, new AbortController().signal);
    return { type: 'rpc/response', id, result };
  } catch (error) {
    return { type: 'rpc/response', id, error: toErrorObject(error) };
  }
}
