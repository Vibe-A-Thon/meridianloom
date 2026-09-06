// Single typed message bus between the extension host and the webview
// (VIGUIX_Final §17: discriminated union, schema-versioned, version checked
// on handshake). Shared by the extension host, the webview and both sides'
// tests — one definition, no drift.
//
// Direction naming is from the webview's perspective:
//   HostMessage — extension host → webview
//   WebviewMessage — webview → extension host

import type { RequestId, RequestMethod, TierName } from './bus-types';

/** Bump when either union's shape changes incompatibly. */
export const WEBVIEW_PROTOCOL_VERSION = 1;

export type { RequestId, RequestMethod };

/** Boot payload: everything the webview needs to render its first honest frame. */
export interface HostInitPayload {
  /** Mirrors WEBVIEW_PROTOCOL_VERSION; the webview refuses on mismatch. */
  protocolVersion: number;
  /** FR-M36-05: enabled tiers, so the webview's registry filter (X-28)
   *  matches the host's without a second round-trip. */
  enabledTiers: readonly TierName[];
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
  | { kind: 'sessions/changed'; detail: string };

/** JSON-RPC error object, structured detail preserved end to end so the
 *  webview can distinguish e.g. TIER_DISABLED (-32003) from a dead sidecar. */
export interface WebviewRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export type WebviewMessage =
  | { type: 'ready'; protocolVersion: number }
  | { type: 'rpc/request'; id: RequestId; method: RequestMethod; params?: unknown }
  /** UI-state changes the host may persist beyond the panel's life. */
  | { type: 'state/update'; state: Record<string, unknown> };

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
  const message = value as { type?: unknown; method?: unknown; id?: unknown };
  return (
    message.type === 'ready' ||
    message.type === 'state/update' ||
    (message.type === 'rpc/request' &&
      typeof message.method === 'string' &&
      (typeof message.id === 'number' || typeof message.id === 'string'))
  );
}
