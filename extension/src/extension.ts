import * as vscode from 'vscode';
import { TIERS, type TierName } from '../../shared/ts/bus-types';
import { normalizeEnabledTiers, TIER_CONTEXT_KEYS } from '../../shared/ts/tiers';
import { registerCommands } from './commands';
import { runDoctor } from './doctor';
import { resolveInterpreter } from './interpreter';
import { resolveCoreDir } from './layout';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
import { SidecarStatusBar } from './status';
import { StdioSidecarClient } from './stdio-client';
import { SidecarSupervisor } from './supervisor';
import { registerViews } from './views';

let supervisor: SidecarSupervisor | undefined;

/**
 * FR-M36-05: the workspace's enabled tiers from the `meridian.tiers`
 * setting, normalised (base tier always on, unknown names dropped).
 */
export function readEnabledTiers(): TierName[] {
  return normalizeEnabledTiers(
    vscode.workspace.getConfiguration('meridian').get<string[]>('tiers'),
  );
}

/**
 * X-28: publish tier state as context keys so the manifest's `when` clauses
 * hide disabled-tier commands and views — not even empty states render.
 */
function applyTierContextKeys(enabled: readonly TierName[]): void {
  for (const tier of TIERS) {
    void vscode.commands.executeCommand(
      'setContext',
      TIER_CONTEXT_KEYS[tier],
      enabled.includes(tier),
    );
  }
}

/**
 * FR-M36-05: a settings change is the whole cost of a tier flip — update the
 * context keys and notify the running sidecar; no reinstall, no reload.
 */
function onConfigurationChanged(event: vscode.ConfigurationChangeEvent): void {
  if (!event.affectsConfiguration('meridian.tiers')) {
    return;
  }
  const enabled = readEnabledTiers();
  applyTierContextKeys(enabled);
  supervisor?.currentClient?.notify?.('tiers/set', { tiers: enabled });
}

/**
 * FR-M1-04: activation performs synchronous registration only. The runtime
 * startup (SecretStorage probe, then the sidecar) is deferred off the call
 * stack so the extension host thread is never blocked.
 */
export function activate(context: vscode.ExtensionContext): void {
  const enabledTiers = readEnabledTiers();
  applyTierContextKeys(enabledTiers);
  context.subscriptions.push(
    ...registerViews(),
    ...registerCommands({
      enabledTiers: readEnabledTiers,
      // FR-M30-01: doctor is wired at activation; the sidecar leg resolves
      // lazily at run time so it works whenever a sidecar is up.
      runDoctor: () =>
        runDoctor({
          verifySecrets: () => SecretStore.verifyAvailable(context.secrets),
          runSidecarDoctor: supervisor?.currentClient
            ? (params, signal) => {
                const client = supervisor?.currentClient;
                if (!client) {
                  return Promise.reject(new Error('sidecar went away'));
                }
                return client.request('doctor/run', params, signal);
              }
            : undefined,
          workspaceDir: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
        }),
      // FR-M36-03 / D23: the hook lifecycle resolves the sidecar lazily at
      // run time, so the command works whenever a sidecar is up and reports
      // instead of acting when it is not.
      hookStatus: () => {
        const client = supervisor?.currentClient;
        if (!client) {
          return Promise.reject(new Error('sidecar is not connected'));
        }
        return client.request('hook/status', {}, new AbortController().signal);
      },
      hookInstall: () => {
        const client = supervisor?.currentClient;
        if (!client) {
          return Promise.reject(new Error('sidecar is not connected'));
        }
        return client.request('hook/install', {}, new AbortController().signal);
      },
      hookRemove: () => {
        const client = supervisor?.currentClient;
        if (!client) {
          return Promise.reject(new Error('sidecar is not connected'));
        }
        return client.request('hook/remove', {}, new AbortController().signal);
      },
    }),
    vscode.workspace.onDidChangeConfiguration(onConfigurationChanged),
  );
  context.subscriptions.push({
    dispose: () => {
      // FR-M3-02: any deactivation path — window close, reload, disable —
      // disposes subscriptions, and disposal terminates the sidecar.
      void supervisor?.stop();
    },
  });
  void startRuntime(context);
}

/**
 * Deferred runtime startup. FR-M1-07: if SecretStorage is unavailable the
 * extension surfaces an actionable error and refuses to start — no
 * plaintext fallback, no half-started runtime.
 */
export async function startRuntime(context: vscode.ExtensionContext): Promise<void> {
  // Yield first: even the probe call itself must not run inside activate().
  await Promise.resolve();
  try {
    await SecretStore.verifyAvailable(context.secrets);
  } catch (error) {
    if (error instanceof SecretStorageUnavailableError) {
      void vscode.window.showErrorMessage(error.message);
      return;
    }
    throw error;
  }
  const statusBar = new SidecarStatusBar();
  context.subscriptions.push(statusBar);
  statusBar.showStarting();
  try {
    const coreDir = await resolveCoreDir(context.extensionPath);
    // FR-M3-05: the interpreter comes from the resolution chain; the
    // resolved path is shown in the status bar.
    const interpreter = await resolveInterpreter();
    // FR-M10-04/SEC-06: the ledger signing seed lives in the OS keychain
    // (SecretStorage); it is provisioned to the sidecar over the handshake
    // and held in memory there only.
    const ledgerSigningKey = await SecretStore.getOrCreateLedgerSigningKey(
      context.secrets,
    );
    const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    supervisor = new SidecarSupervisor({
      clientFactory: () =>
        new StdioSidecarClient({
          command: interpreter.executable,
          cwd: coreDir,
          // FR-M36-05: read at spawn time so a supervisor restart picks up a
          // tier change even if the tiers/set notification was missed.
          tiers: readEnabledTiers(),
          ...(workspaceDir ? { workspaceDir } : {}),
          ledgerSigningKey,
          onStderr: (line) => console.debug('[sidecar]', line),
        }),
      onError: (message) => {
        statusBar.showFailed(message);
        void vscode.window.showErrorMessage(message);
      },
    });
    await supervisor.start();
    statusBar.showReady(interpreter);
  } catch (error) {
    // supervisor.start() failures are already surfaced via onError; layout
    // and interpreter-resolution failures are not — surface them here.
    if (supervisor === undefined) {
      const message = error instanceof Error ? error.message : String(error);
      statusBar.showFailed(message);
      void vscode.window.showErrorMessage(message);
    }
  }
}

/**
 * FR-M3-02: deactivation terminates the sidecar (graceful RPC, then
 * SIGTERM, then a tree kill). VS Code awaits the returned promise.
 */
export async function deactivate(): Promise<void> {
  const current = supervisor;
  supervisor = undefined;
  await current?.stop();
}
