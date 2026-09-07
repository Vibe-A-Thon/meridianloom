import { useCallback, useEffect, useRef, useState } from 'react';
import type { WorkbenchAction, WorkbenchActionMap, WorkbenchExecute, WorkbenchSnapshot } from '../../../shared/ts/workbench';
import type { WebviewRpcClient } from '../rpc/client';

export interface WorkbenchController {
  snapshot: WorkbenchSnapshot | undefined;
  busy: boolean;
  error: string | null;
  execute: WorkbenchExecute;
  refresh: () => Promise<void>;
}

export function useWorkbench(client: WebviewRpcClient, ready: boolean): WorkbenchController {
  const [snapshot, setSnapshot] = useState<WorkbenchSnapshot>();
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const accept = useCallback((next: WorkbenchSnapshot) => {
    if (mounted.current) setSnapshot(previous => !previous || next.revision >= previous.revision ? next : previous);
  }, []);
  const refresh = useCallback(async () => {
    if (!ready) return;
    try {
      accept(await client.workbench('snapshot', {}));
      if (mounted.current) setError(null);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [client, ready, accept]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = ready ? setInterval(() => void refresh(), 5000) : undefined;
    const unsubscribe = client.addListener(message => {
      if (message.type === 'event' && (message.event.kind === 'workbench/changed' || message.event.kind === 'tiers/changed')) void refresh();
    });
    return () => { mounted.current = false; clearInterval(timer); unsubscribe(); };
  }, [client, ready, refresh]);
  const execute: WorkbenchExecute = useCallback(async <A extends WorkbenchAction>(action: A, params: WorkbenchActionMap[A]['params']) => {
    setPending(count => count + 1);
    setError(null);
    try {
      const result = await client.workbench(action, params);
      if ('revision' in result) accept(result as WorkbenchSnapshot);
      return result;
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    } finally {
      if (mounted.current) setPending(count => count - 1);
    }
  }, [client, accept]);
  return { snapshot, busy: pending > 0, error, execute, refresh };
}
