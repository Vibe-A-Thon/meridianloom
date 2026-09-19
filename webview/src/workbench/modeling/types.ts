import type { TierName } from '../../../../shared/ts/bus-types';
import type { WebviewRpcClient } from '../../rpc/client';
import type { WorkbenchController } from '../useWorkbench';
export type ModelingView = 'codemap' | 'loops' | 'architecture' | 'uml' | 'flows' | 'diff' | 'replay' | 'comprehension';
export interface ModelingStudioProps {
  view: string;
  client: WebviewRpcClient;
  ready: boolean;
  controller: WorkbenchController;
  workspaceDir: string | undefined;
  enabledTiers: readonly TierName[];
  onNavigate: (route: string) => void;
}
