import type { LedgerQueryParams } from '../../../shared/ts/bus-types';
import type { WebviewRpcClient } from '../rpc/client';
import { useRpcQuery } from './useRpcQuery';

/** X-29 / 10.46: observed external-agent sessions plus sticky warnings. */
export function useObserveSessions(client: WebviewRpcClient | undefined) {
  return useRpcQuery(client, 'observe/sessions', {});
}

/** 10.7: the ledger entry stream behind the Selvage Viewer. */
export function useLedgerQuery(
  client: WebviewRpcClient | undefined,
  params: LedgerQueryParams,
) {
  return useRpcQuery(client, 'ledger.query', params);
}
