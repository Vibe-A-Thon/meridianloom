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
import { resolveAgentIdentity, type AgentIdentity } from './identity';

export type { DiscoveredAdapter };

/**
 * What launching actually needs: the id, the folder, and the manifest that
 * carries the command.
 *
 * Deliberately narrower than `DiscoveredAdapter`, which also carries an
 * integrity verdict (MV3-T01). The workbench launches agents it configured
 * itself, which never came from a discovered folder and so have no pin to
 * report; widening this to the full type would force that path to invent a
 * `pinned` verdict for something nobody pinned. Drifted folder adapters are
 * refused earlier, in discovery, and never reach here.
 */
export type LaunchTarget = Pick<DiscoveredAdapter, 'id' | 'tier' | 'dir' | 'manifest'>;

export interface AdapterSession {
  readonly adapterId: string;
  /**
   * FR-M44-01 (MV3-T01b): what was actually executed, resolved during
   * `start()` and before the process is spawned. `undefined` until then —
   * an identity reported before it was taken would be a guess.
   */
  readonly identity: AgentIdentity | undefined;
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
  /**
   * FR-M44-01/02, AC-52 (MV3-T01b): called with the resolved identity
   * BEFORE the agent is spawned, so the caller can record it and warn on a
   * binary swap. Awaited: a swap warning that arrives after the agent has
   * already started work is a notification, not a control.
   *
   * Throwing refuses the launch. Nothing here throws on its own — an
   * identity that cannot be established comes back `unverified` rather than
   * as an error — so a refusal is the caller's policy decision, not this
   * module's.
   */
  onIdentity?: (identity: AgentIdentity) => void | Promise<void>;
  /** Test seam; production resolves against the real PATH. */
  resolveIdentity?: (
    command: string,
    args: readonly string[],
  ) => Promise<AgentIdentity>;
}

/**
 * Launch the discovered adapter's ACP agent. Throws AcpTierDisabledError
 * when the governor tier is disabled — the workspace hosts nothing (G5).
 */
export function launchAdapter(
  adapter: LaunchTarget,
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
  let identity: AgentIdentity | undefined;
  const resolve = options.resolveIdentity ?? ((command, args) =>
    resolveAgentIdentity(command, args, {
      declaredVersion: adapter.manifest.version,
      declaredPublisher: adapter.manifest.vendor,
    }));
  return {
    adapterId: adapter.id,
    get identity() {
      return identity;
    },
    get pid() {
      return client.pid;
    },
    // Identify first, then spawn. The other order records the identity of a
    // process that is already running and possibly already acting, which
    // makes the record a description rather than a check.
    start: async () => {
      identity = await resolve(adapter.manifest.acp.command, adapter.manifest.acp.args ?? []);
      await options.onIdentity?.(identity);
      return client.start();
    },
    newSession: (cwd?) => client.newSession(cwd),
    prompt: (sessionId, text, opts?) =>
      client.prompt(sessionId, text, opts).then((stopReason) => String(stopReason)),
    stop: () => client.stop(),
  };
}
