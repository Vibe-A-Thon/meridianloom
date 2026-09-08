import * as vscode from 'vscode';
import * as path from 'node:path';
import { WorkbenchService } from './workbench';
import { createVscodePermissionApprover } from './acp/permissions';
import { TIERS, type TierName } from '../../shared/ts/bus-types';
import { normalizeEnabledTiers, TIER_CONTEXT_KEYS } from '../../shared/ts/tiers';
import { registerCommands } from './commands';
import { runDoctor } from './doctor';
import { handleGateHaltNotification } from './governance/gate-halt';
import {  handleSpendCeilingNotification,
  SpendCeilingPauseTracker,
} from './governance/spend-ceiling';
import { hostedSessionRegistry } from './governance/session-registry';
import { resolveInterpreter } from './interpreter';
import { resolveCoreDir } from './layout';
import { RecorderPanel } from './recorder-panel';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
import { SidecarStatusBar } from './status';
import { StdioSidecarClient } from './stdio-client';
import { SidecarSupervisor } from './supervisor';
import { registerViews } from './views';

let supervisor: SidecarSupervisor | undefined;
let workbench: WorkbenchService | undefined;

/** FR-M39-02/D33: pause-pending state for hosted sessions that breached a spend ceiling. */
const spendCeilingPauses = new SpendCeilingPauseTracker();

/** The workspace folder the sidecar is pointed at (handshake workspaceDir). */
function workspaceDir(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

/**
 * 10.45/10.7 Export (FR-M36-04): the webview cannot write files, so a signed
 * audit bundle crosses the bus as text and the host offers the save dialog.
 * A cancelled dialog is not an error — the bundle facts stay in the UI.
 */
async function saveDownload(request: {
  fileName: string;
  content: string;
  mimeType?: string;
}): Promise<void> {
  const formats: Record<string, Record<string, string[]>> = {
    'application/json': { 'Meridian JSON document': ['json'] },
    'image/svg+xml': { 'SVG diagram': ['svg'] },
    'text/csv': { 'CSV table': ['csv'] },
    'text/plain': { 'Text document': ['md', 'mmd', 'txt'] },
  };
  const target = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.basename(request.fileName)),
    filters: formats[request.mimeType ?? 'application/json'] ?? formats['application/json'],
  });
  if (!target) {
    return;
  }
  await vscode.workspace.fs.writeFile(target, Buffer.from(request.content, 'utf8'));
}

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
  RecorderPanel.broadcast({ kind: 'tiers/changed', enabledTiers: enabled });
  void workbench?.reconcile().catch(error => void vscode.window.showErrorMessage(String(error)));
}

/**
 * FR-M1-04: activation performs synchronous registration only. The runtime
 * startup (SecretStorage probe, then the sidecar) is deferred off the call
 * stack so the extension host thread is never blocked.
 */
export function activate(context: vscode.ExtensionContext): void {
  workbench = new WorkbenchService({
    workspaceDir, trusted: () => vscode.workspace.isTrusted,
    enabledTiers: readEnabledTiers, sidecar: () => {
      const client = supervisor?.isRunning ? supervisor.currentClient : undefined;
      return client ? { request: (method, params) => client.request(method, params, new AbortController().signal) } : undefined;
    },
    humanApprover: createVscodePermissionApprover(),
    policyPaths: context.extensionPath ? [path.join(context.extensionPath, 'policy', 'acp-permissions.yaml'), path.resolve(context.extensionPath, '..', 'policy', 'acp-permissions.yaml')] : [],
    onError: message => void vscode.window.showErrorMessage(message),
  });
  context.subscriptions.push(workbench);
  const workspaceListener = vscode.workspace.onDidChangeWorkspaceFolders?.(() => {
    void workbench?.reconcile().catch(error => void vscode.window.showErrorMessage(String(error)));
  });
  if (workspaceListener) context.subscriptions.push(workspaceListener);
  const enabledTiers = readEnabledTiers();
  applyTierContextKeys(enabledTiers);
  context.subscriptions.push(
    ...registerViews(),
    RecorderPanel.registerSerializer(context, {
      workbench,
      extensionPath: context.extensionPath,
      enabledTiers: readEnabledTiers,
      sidecar: () => supervisor?.currentClient,
      workspaceDir,
      onDownload: saveDownload,
      onError: (message) => void vscode.window.showErrorMessage(message),
    }),
    ...registerCommands({
      enabledTiers: readEnabledTiers,
      // F0 Workstream G: the recorder command opens the dashboard webview;
      // the panel proxies sidecar RPCs with the tier gate applied.
      openRecorder: async () => {
        RecorderPanel.createOrShow({
          workbench,
          extensionPath: context.extensionPath,
          enabledTiers: readEnabledTiers,
          sidecar: () => supervisor?.currentClient,
          workspaceDir,
          onDownload: saveDownload,
          onError: (message) => void vscode.window.showErrorMessage(message),
        });
      },
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
      // FR-M18-04 (F1 Workstream A task 5): story abort — worktree + branch
      // removal, ledger-recorded, primary tree untouched (AC-14).
      abortStory: (storyId) => {
        const client = supervisor?.currentClient;
        if (!client) {
          return Promise.reject(new Error('sidecar is not connected'));
        }
        return client.request(
          'worktree/abortStory',
          { storyId },
          new AbortController().signal,
        );
      },
      // FR-M18-08: the open-in-window command resolves the story worktree
      // path over worktree/list before vscode.openFolder.
      listWorktrees: () => {
        const client = supervisor?.currentClient;
        if (!client) {
          return Promise.reject(new Error('sidecar is not connected'));
        }
        return client.request('worktree/list', {}, new AbortController().signal);
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
    // FR-M20-01 (D9): the identity source of record, read at spawn time so
    // a supervisor restart picks up a settings change. "git" resolves the
    // workspace's user.name/user.email (assurance local); "oidc" is the
    // enterprise stub until the enterprise tier lands.
    const identityProvider = vscode.workspace
      .getConfiguration('meridian')
      .get<string>('identityProvider');
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
          ...(identityProvider ? { identityProvider } : {}),
          onStderr: (line) => console.debug('[sidecar]', line),
        }),
      onError: (message) => {
        statusBar.showFailed(message);
        void vscode.window.showErrorMessage(message);
      },
      onStateChange: state => {
        void workbench?.reconcile().catch(error => void vscode.window.showErrorMessage(String(error)));
        if (state === 'ready') supervisor?.currentClient?.on('notification', (method: string, params: unknown) => {
          const handledByGateHalt = handleGateHaltNotification(method, params, {
            registry: hostedSessionRegistry,
            warn: message => void vscode.window.showWarningMessage(message),
          });
          if (!handledByGateHalt) {
            handleSpendCeilingNotification(method, params, {
              registry: hostedSessionRegistry,
              tracker: spendCeilingPauses,
              warn: message => void vscode.window.showWarningMessage(message),
              log: message => console.debug('[spend-ceiling]', message),
            });
          }
        });
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
  workbench?.dispose();
  workbench = undefined;
  const current = supervisor;
  supervisor = undefined;
  await current?.stop();
}
