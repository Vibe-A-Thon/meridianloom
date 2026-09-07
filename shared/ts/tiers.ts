import {
  CAPABILITIES,
  TIERS,
  type CapabilityDefinition,
  type TierName,
} from './bus-types';

/**
 * FR-M36-05 tiering, host half — the shared logic both the extension and the
 * (future) webview command registry filter on. The registry *data* is
 * generated from shared/schema/tiers.json (CAPABILITIES/TIERS in
 * bus-types.ts); this module holds the lookups and the policy:
 *
 *  - the base tier (flight-recorder) is always enabled;
 *  - unknown tier names in configuration are dropped, never fatal;
 *  - disabling a tier hides its commands and views and makes the sidecar
 *    refuse its RPCs — and re-enabling it is a settings change only (G5).
 *
 * This module imports no vscode API so the webview can consume it as-is.
 */

export type { CapabilityDefinition, TierName };
export { CAPABILITIES, TIERS };

export const BASE_TIER: TierName = 'flight-recorder';

/**
 * Normalise the `meridian.tiers` setting into the effective enabled set:
 * clamped to known tiers, base tier always present, canonical order.
 */
export function normalizeEnabledTiers(configured: readonly unknown[] | undefined): TierName[] {
  const requested = new Set(
    (configured ?? []).filter(
      (tier): tier is TierName =>
        typeof tier === 'string' && (TIERS as readonly string[]).includes(tier),
    ),
  );
  requested.add(BASE_TIER);
  return TIERS.filter((tier) => requested.has(tier));
}

const CAPABILITY_BY_METHOD = new Map<string, CapabilityDefinition>(
  CAPABILITIES.flatMap((capability) =>
    capability.rpcMethods.map((method) => [method, capability] as const),
  ),
);

export function capabilityForRpcMethod(method: string): CapabilityDefinition | undefined {
  return CAPABILITY_BY_METHOD.get(method);
}

const CAPABILITY_BY_ID = new Map<string, CapabilityDefinition>(
  CAPABILITIES.map((capability) => [capability.id, capability]),
);

/**
 * FR-M36-05, host-side features: whether the capability (e.g.
 * `governor.acp-host`, FR-M34-01) is available under the given enabled set.
 * Host-only capabilities (no sidecar RPC of their own) are gated through
 * this lookup, mirroring the sidecar's per-method tier gate (G5: disabling
 * a tier leaves the tiers below fully functional).
 */
export function isCapabilityEnabled(capabilityId: string, enabled: readonly TierName[]): boolean {
  const capability = CAPABILITY_BY_ID.get(capabilityId);
  return capability !== undefined && enabled.includes(capability.tier);
}

/**
 * Whether an RPC would pass the sidecar's tier gate under the given enabled
 * set. Methods nobody owns are not a tier question — the bus answers
 * METHOD_NOT_FOUND for those.
 */
export function isRpcMethodEnabled(method: string, enabled: readonly TierName[]): boolean {
  const capability = CAPABILITY_BY_METHOD.get(method);
  return capability === undefined || enabled.includes(capability.tier);
}

/**
 * Command → owning tier. Every contributed command appears exactly once;
 * extension/test/tiers.test.ts asserts the mapping never drifts from
 * commands.ts. Tier assignments follow the phase map (gaps_implementation
 * §19): recording, provenance and the doctor are Flight Recorder; gates,
 * steer/dry-run and story control are Governor; story ingestion, skills and
 * adapter management are Orchestra.
 */
export const COMMAND_TIERS: Record<string, TierName> = {
  'meridian.ingestStory': 'orchestra',
  'meridian.openRecorder': 'flight-recorder',
  'meridian.installSkill': 'orchestra',
  'meridian.onboardAgent': 'orchestra',
  'meridian.exportAgent': 'orchestra',
  'meridian.importAgent': 'orchestra',
  'meridian.verifyChain': 'flight-recorder',
  'meridian.haltAll': 'governor',
  'meridian.steer': 'governor',
  'meridian.dryRun': 'governor',
  'meridian.abortStory': 'governor',
  'meridian.openWorktree': 'governor',
  'meridian.doctor': 'flight-recorder',
  'meridian.installHook': 'flight-recorder',
};

/** Tree view → owning tier; same drift-checked pattern as COMMAND_TIERS. */
export const VIEW_TIERS: Record<string, TierName> = {
  'meridianLoom.agents': 'orchestra',
  'meridianLoom.stories': 'governor',
  'meridianLoom.loops': 'orchestra',
  'meridianLoom.skills': 'orchestra',
  'meridianLoom.ledger': 'flight-recorder',
};

export function isCommandEnabled(commandId: string, enabled: readonly TierName[]): boolean {
  const tier = COMMAND_TIERS[commandId];
  return tier === undefined || enabled.includes(tier);
}

export function enabledCommands(enabled: readonly TierName[]): string[] {
  return Object.keys(COMMAND_TIERS).filter((id) => isCommandEnabled(id, enabled));
}

export function enabledViews(enabled: readonly TierName[]): string[] {
  return Object.keys(VIEW_TIERS).filter((id) => enabled.includes(VIEW_TIERS[id]));
}

/** X-28: the disclosure for a locked command — what it needs, one action. */
export function tierLockMessage(commandId: string): string {
  const tier = COMMAND_TIERS[commandId];
  return (
    `Meridian Loom: '${commandId}' is part of the ${tier} tier, which is not enabled ` +
    `in this workspace. Add "${tier}" to the meridian.tiers setting to enable it — ` +
    'no reinstall is needed.'
  );
}

/**
 * Context keys the extension sets with `commands.setContext`; package.json
 * `when` clauses key on these so palette entries and views for disabled
 * tiers never render (X-28 — not even as empty states).
 */
export const TIER_CONTEXT_KEYS: Record<TierName, string> = {
  'flight-recorder': 'meridian.tiers.flightRecorder',
  governor: 'meridian.tiers.governor',
  orchestra: 'meridian.tiers.orchestra',
};
