import { useCallback, useEffect, useRef, useState } from 'react';
import type { MethodMap, RequestMethod } from '../../../shared/ts/bus-types';
import type { WebviewRpcClient } from '../rpc/client';

/**
 * Real-data hooks (G0d / G3): the webview gets data only through the
 * extension host. Every hook carries loading / error / ready explicitly —
 * observation degrades never silently; an error renders as an ErrorState.
 */

export type QueryStatus = 'loading' | 'error' | 'ready';

export type RpcQueryState<M extends RequestMethod> =
  | {
      status: 'loading';
      data: undefined;
      error: undefined;
      refresh: () => void;
    }
  | {
      status: 'error';
      data: undefined;
      error: unknown;
      refresh: () => void;
    }
  | {
      status: 'ready';
      data: MethodMap[M]['result'];
      error: undefined;
      refresh: () => void;
    };

export function useRpcQuery<M extends RequestMethod>(
  client: WebviewRpcClient | undefined,
  method: M,
  params: MethodMap[M]['params'],
  enabled = true,
  /** Bumping this re-issues the request (host push events). */
  refreshKey: unknown = undefined,
): RpcQueryState<M> {
  const [state, setState] = useState<
    | { status: 'loading'; data: undefined; error: undefined }
    | { status: 'error'; data: undefined; error: unknown }
    | { status: 'ready'; data: MethodMap[M]['result']; error: undefined }
  >({ status: 'loading', data: undefined, error: undefined });
  const generation = useRef(0);

  const run = useCallback(() => {
    if (!client || !enabled) {
      // Not an error: the handshake has not completed (or the host has not
      // delivered init yet). The UI shows its loading state and the query
      // fires the moment it is enabled.
      setState({ status: 'loading', data: undefined, error: undefined });
      return;
    }
    const mine = ++generation.current;
    setState({ status: 'loading', data: undefined, error: undefined });
    client
      .request(method, params)
      .then((data) => {
        if (generation.current === mine) {
          setState({ status: 'ready', data, error: undefined });
        }
      })
      .catch((error) => {
        if (generation.current === mine) {
          setState({ status: 'error', data: undefined, error });
        }
      });
  }, [client, method, JSON.stringify(params), enabled, refreshKey]);

  useEffect(() => {
    run();
    return () => {
      generation.current++;
    };
  }, [run]);

  return { ...state, refresh: run };
}
