import { useEffect, useRef } from 'react';
import type {
  LedgerGetEntryParams,
  LedgerProofParams,
  LedgerQueryParams,
  LedgerVerifyParams,
} from '../../../shared/ts/bus-types';
import type { WebviewRpcClient } from '../rpc/client';
import { useRpcQuery } from './useRpcQuery';

/**
 * Real-data hooks (G0d / G3): the webview gets data only through the
 * extension host. Every hook carries loading / error / ready explicitly —
 * observation degrades, never silently; an error renders as an ErrorState.
 */

/** X-29 / 10.46: observed external-agent sessions plus sticky warnings. */
export function useObserveSessions(
  client: WebviewRpcClient | undefined,
  enabled = true,
  refreshKey?: unknown,
) {
  return useRpcQuery(client, 'observe/sessions', {}, enabled, refreshKey);
}

/** 10.45 Weave / 10.7 stream: ledger entries, filterable (FR-M10-12). */
export function useLedgerQuery(
  client: WebviewRpcClient | undefined,
  params: LedgerQueryParams,
  enabled = true,
  refreshKey?: unknown,
) {
  return useRpcQuery(client, 'ledger.query', params, enabled, refreshKey);
}

/** FR-M11-01: the chain-integrity verdict behind the Selvage strip. */
export function useLedgerVerify(
  client: WebviewRpcClient | undefined,
  enabled = true,
  refreshKey?: unknown,
) {
  const params: LedgerVerifyParams = {};
  return useRpcQuery(client, 'ledger.verify', params, enabled, refreshKey);
}

/** 10.46: observer adapter health (FR-M35-08, NFR-32). */
export function useObserveHealth(client: WebviewRpcClient | undefined, enabled = true) {
  return useRpcQuery(client, 'observe/health', {}, enabled);
}

/** 10.7 entry drawer: full record incl. decrypted blob availability. */
export function useLedgerEntry(client: WebviewRpcClient | undefined, params: LedgerGetEntryParams) {
  return useRpcQuery(client, 'ledger.getEntry', params);
}

/** 10.7 proof inspection: inclusion and/or consistency proofs. */
export function useLedgerProof(client: WebviewRpcClient | undefined, params: LedgerProofParams) {
  return useRpcQuery(client, 'ledger.proof', params);
}

/**
 * X-29 budget: re-run `callback` every `delayMs` while `delayMs` is set.
 * Push events remain the primary refresh; the interval is the backstop that
 * keeps the Crown within two seconds of the sidecar knowing a session.
 */
export function useInterval(callback: () => void, delayMs: number | null): void {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (delayMs === null) {
      return;
    }
    const timer = setInterval(() => saved.current(), delayMs);
    return () => clearInterval(timer);
  }, [delayMs]);
}
