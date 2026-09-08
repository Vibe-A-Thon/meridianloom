/**
 * Launching an adapter under Meridian governance (FR-M34-02): the manifest's
 * `acp` section IS the launch spec — command, args, env — handed to the ACP
 * host client through the governor tier gate (createAcpClient, FR-M36-05/G5).
 * The returned session is the unplug-cleanup handle (FR-M31-04): stop() is
 * idempotent and never throws, so retirement cannot scar the host.
 *
 * No bespoke protocol: the wire is ACP end to end. Governance surfaces ride
 * in the manifest (see manifest.ts), and the FR-M34-04 permission gate
 * plugs in through the approver seam (see permission-gate.ts, task 4).
 */
import { createAcpClient } from '../acp';
import type { AcpClient, AcpClientOptions, PermissionApprover } from '../acp/client';
import type { InitializeResponse, SessionNotification } from '@zed-industries/agent-client-protocol';
import type { TierName } from '../../../shared/ts/bus-types';
import type { DiscoveredAdapter } from './discovery';

export type { DiscoveredAdapter };

export interface AdapterSession {
  readonly adapterId: string;
  /** The pid of the hosted ACP agent process, once started. */
  readonly pid: number | undefined;
  start(): Promise<InitializeResponse>;
  newSession(cwd?: string): Promise<string>;
  prompt(sessionId: string, text: string, options?: { signal?: AbortSignal }): Promise<string>;
  stop(): void;
}

export interface LaunchOptions {
  /** The user's workspace; fs/terminal access and the session cwd root here. */
  workspaceDir: string;
  /** FR-M36-05: the workspace's enabled tiers — a disabled governor refuses. */
  enabledTiers: readonly TierName[];
  /** FR-M34-01: tool-approval path; the FR-M34-04 gate wraps this (task 4). */
  approvePermission?: PermissionApprover;
  /** Test seam, forwarded to the ACP client. */
  spawner?: AcpClientOptions['spawner'];
  /**
   * FR-M39-02/D33: consulted at the top of every turn (the checkpoint gate).
   * Throwing refuses the turn — how a spend-ceiling pause-pending session
   * stops after its in-flight turn without a mid-flight kill.
   */
  checkpointGate?: AcpClientOptions['checkpointGate'];
  onStderr?: (line: string) => void;
  /** Optional streaming output; callers still own storage and presentation. */
  onUpdate?: (notification: SessionNotification) => void;
}

/**
 * Launch the discovered adapter's ACP agent. Throws AcpTierDisabledError
 * when the governor tier is disabled — the workspace hosts nothing (G5).
 */
export function launchAdapter(
  adapter: DiscoveredAdapter,
  options: LaunchOptions,
): AdapterSession {
  const client: AcpClient = createAcpClient(
    {
      command: adapter.manifest.acp.command,
      args: adapter.manifest.acp.args,
      env: adapter.manifest.acp.env,
      workspaceDir: options.workspaceDir,
      ...(options.approvePermission ? { approvePermission: options.approvePermission } : {}),
      ...(options.spawner ? { spawner: options.spawner } : {}),
      ...(options.checkpointGate ? { checkpointGate: options.checkpointGate } : {}),
      ...(options.onStderr ? { onStderr: options.onStderr } : {}),
    },
    options.enabledTiers,
  );
  if (options.onUpdate) {
    client.on('update', options.onUpdate);
  }
  return {
    adapterId: adapter.id,
    get pid() {
      return client.pid;
    },
    start: () => client.start(),
    newSession: (cwd?) => client.newSession(cwd),
    prompt: (sessionId, text, opts?) =>
      client.prompt(sessionId, text, opts).then((stopReason) => String(stopReason)),
    stop: () => client.stop(),
  };
}
