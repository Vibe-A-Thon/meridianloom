/**
 * Governor-tier entry point for the ACP host (FR-M34-01, FR-M36-05/G5).
 *
 * The ACP host is a Governor capability: hosting agents in VS Code is the
 * F1 differentiator, and a workspace without the governor tier enabled must
 * host nothing — while Flight Recorder below it keeps working untouched.
 * The gate mirrors the sidecar's TIER_DISABLED shape so the UI can disclose
 * the lock the same way it discloses a locked command (X-28).
 */
import { isCapabilityEnabled, type TierName } from '../../../shared/ts/tiers';
import { AcpClient, type AcpClientOptions } from './client';

export const ACP_HOST_CAPABILITY = 'governor.acp-host';

/** Structured refusal, shaped like the sidecar's TIER_DISABLED error data. */
export class AcpTierDisabledError extends Error {
  constructor(readonly enabledTiers: readonly TierName[]) {
    super(
      `Meridian Loom: hosting ACP agents is part of the governor tier, which is ` +
        `not enabled in this workspace. Add "governor" to the meridian.tiers ` +
        `setting to enable it — no reinstall is needed.`,
    );
    this.name = 'AcpTierDisabledError';
  }

  get data(): Record<string, unknown> {
    return {
      capability: ACP_HOST_CAPABILITY,
      tier: 'governor',
      enabledTiers: [...this.enabledTiers],
      remediation:
        'Add "governor" to the meridian.tiers setting to enable it — no reinstall is needed.',
    };
  }
}

export function assertAcpHostEnabled(enabledTiers: readonly TierName[]): void {
  if (!isCapabilityEnabled(ACP_HOST_CAPABILITY, enabledTiers)) {
    throw new AcpTierDisabledError(enabledTiers);
  }
}

/**
 * Create an ACP host client for this workspace, refusing when the governor
 * tier is disabled (G5). Callers pass the workspace's effective enabled
 * tiers (normalizeEnabledTiers of the meridian.tiers setting).
 */
export function createAcpClient(
  options: AcpClientOptions,
  enabledTiers: readonly TierName[],
): AcpClient {
  assertAcpHostEnabled(enabledTiers);
  return new AcpClient(options);
}
