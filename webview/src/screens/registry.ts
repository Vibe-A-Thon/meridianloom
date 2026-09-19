import type { ComponentType } from 'react';
import type { TierName } from '../../../shared/ts/bus-types';
import type { RpcQueryState } from '../hooks/useRpcQuery';
import type { WebviewRpcClient } from '../rpc/client';
import { FlightRecorderScreen } from './FlightRecorderScreen';
import { ExternalAgentsScreen } from './ExternalAgentsScreen';
import { LaunchScreen } from './LaunchScreen';
import { LedgerScreen } from './LedgerScreen';

/**
 * X-28 / DS-3: the Loom Bar is generated from this registry, filtered by
 * the enabled tiers from the init handshake. A screen whose tier is not
 * enabled is ABSENT — never rendered as a disabled entry or an empty
 * state (banned pattern 30). Governor and Orchestra screens register here
 * when those tiers land (GF1/GF3); until then there is nothing to leak.
 */

export interface ScreenProps {
  client: WebviewRpcClient;
  ready: boolean;
  /** The live observe/sessions query (App-level, X-29 polling + push). */
  sessions: RpcQueryState<'observe/sessions'>;
  workspaceDir: string | undefined;
  /** FR-M36-05 tiers enabled in this workspace (init handshake, X-28). */
  enabledTiers: readonly TierName[];
}

export interface ScreenDefinition {
  id: string;
  title: string;
  tier: TierName;
  component: ComponentType<ScreenProps>;
}

export const SCREEN_REGISTRY: readonly ScreenDefinition[] = [
  {
    id: 'flight-recorder',
    title: 'Flight Recorder',
    tier: 'flight-recorder',
    component: FlightRecorderScreen,
  },
  {
    id: 'external-agents',
    title: 'External Agents',
    tier: 'flight-recorder',
    component: ExternalAgentsScreen,
  },
  {
    id: 'ledger',
    title: 'Ledger',
    tier: 'flight-recorder',
    component: LedgerScreen,
  },
  // 10.51 Launch (FR-M40-11, MV2-T06). Governor tier, which is what makes
  // it ABSENT below that tier: `visibleScreens` filters on the tier, so a
  // Flight Recorder user has no Launch entry in the Loom Bar at all —
  // there is no Meridian agent to start there, and a locked entry would be
  // a scar rather than an explanation.
  {
    id: 'launch',
    title: 'Launch',
    tier: 'governor',
    component: LaunchScreen,
  },
];

export function visibleScreens(enabledTiers: readonly TierName[]): ScreenDefinition[] {
  return SCREEN_REGISTRY.filter((screen) => enabledTiers.includes(screen.tier));
}
