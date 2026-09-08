// Single typed message bus between the extension host and the webview
// (VIGUIX_Final §17: discriminated union, schema-versioned, version checked
// on handshake). Shared by the extension host, the webview and both sides'
// tests — one definition, no drift.
//
// Direction naming is from the webview's perspective:
//   HostMessage — extension host → webview
//   WebviewMessage — webview → extension host

import type { RequestId, RequestMethod, TierName } from './bus-types';
import type { WorkbenchAction } from './workbench';

/** Bump when either union's shape changes incompatibly.
 *  v2: init gained `workspaceDir`; the webview→host union gained the
 *  `download` message (audit-bundle export, FR-M36-04). Both sides are
 *  always built from the same commit, so the handshake version check is
 *  the enforcement. */
export const WEBVIEW_PROTOCOL_VERSION = 4;

export type { RequestId, RequestMethod };

/** Boot payload: everything the webview needs to render its first honest frame. */
export interface HostInitPayload {
  /** Mirrors WEBVIEW_PROTOCOL_VERSION; the webview refuses on mismatch. */
  protocolVersion: number;
  /** FR-M36-05: enabled tiers, so the webview's registry filter (X-28)
   *  matches the host's without a second round-trip. */
  enabledTiers: readonly TierName[];
  /** The workspace folder the sidecar was pointed at (handshake
   *  workspaceDir). attrib/* and hook/* RPCs need it; absent means no
   *  folder is open — the screens say so honestly instead of guessing. */
  workspaceDir?: string;
  /** Workspace configuration the host resolved (density/theme overrides
   *  arrive here once Config › Appearance lands; until then the webview
   *  uses its persisted or default choices). */
  defaultDensity?: 'comfortable' | 'compact' | 'dense';
}

export type HostMessage =
  | { type: 'init'; init: HostInitPayload }
  /** Push events (observer session appearing, tier change) arrive as data. */
  | { type: 'event'; event: HostEvent }
  /** Answer to a WebviewRpcRequest. */
  | {
      type: 'rpc/response';
      id: RequestId;
      result?: unknown;
      error?: WebviewRpcError;
    };

export type HostEvent =
  | { kind: 'tiers/changed'; enabledTiers: readonly TierName[] }
  | { kind: 'sessions/changed'; detail: string }
  | { kind: 'workbench/changed' };

/** JSON-RPC error object, structured detail preserved end to end so the
 *  webview can distinguish e.g. TIER_DISABLED (-32003) from a dead sidecar. */
export interface WebviewRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export type WebviewMessage =
  | { type: 'editor/open'; path: string; line?: number }
  | { type: 'host/action'; action: 'open-settings' | 'open-folder' }
  | { type: 'ready'; protocolVersion: number }
  | { type: 'rpc/request'; id: RequestId; method: RequestMethod; params?: unknown }
  | { type: 'workbench/request'; id: RequestId; action: WorkbenchAction; params?: unknown }
  /** UI-state changes the host may persist beyond the panel's life. */
  | { type: 'state/update'; state: Record<string, unknown> }
  /** 10.45/10.7 Export: the webview cannot write files (VIGUIX_Final §17),
   *  so a signed audit bundle (FR-M36-04) crosses as text and the host
   *  offers the save dialog. Fire-and-forget; the webview already holds
   *  the bundle facts it displays. */
  | { type: 'download'; fileName: string; mimeType: string; content: string };

export function isHostMessage(value: unknown): value is HostMessage {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const type = (value as { type?: unknown }).type;
  return type === 'init' || type === 'event' || type === 'rpc/response';
}

export function isWebviewMessage(value: unknown): value is WebviewMessage {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const message = value as { type?: unknown; method?: unknown; action?: unknown; id?: unknown };
  if (message.type === 'editor/open') {
    const open = value as { path?: unknown; line?: unknown };
    return typeof open.path === 'string' && open.path.length > 0 && open.path.length <= 4_000 &&
      (open.line === undefined || (typeof open.line === 'number' && Number.isSafeInteger(open.line) && open.line > 0));
  }
  if (message.type === 'host/action') return message.action === 'open-settings' || message.action === 'open-folder';
  if (message.type === 'download') {
    const download = value as { fileName?: unknown; mimeType?: unknown; content?: unknown };
    return (
      typeof download.fileName === 'string' &&
      typeof download.mimeType === 'string' &&
      typeof download.content === 'string'
    );
  }
  return (
    message.type === 'ready' ||
    message.type === 'state/update' ||
    (message.type === 'workbench/request' &&
      typeof message.action === 'string' &&
      (typeof message.id === 'number' || typeof message.id === 'string')) ||
    (message.type === 'rpc/request' &&
      typeof message.method === 'string' &&
      (typeof message.id === 'number' || typeof message.id === 'string'))
  );
}
