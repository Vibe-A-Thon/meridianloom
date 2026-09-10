import * as vscode from 'vscode';
import * as path from 'node:path';
import { WorkbenchService } from './workbench';
import { createEditorSurfaces } from './editor-surfaces';
import { createVscodePermissionApprover } from './acp/permissions';
import { TIERS, type TierName } from '../../shared/ts/bus-types';
import { normalizeEnabledTiers, TIER_CONTEXT_KEYS } from '../../shared/ts/tiers';
import { registerCommands } from './commands';
import { runDoctor } from './doctor';
import { handleGateHaltNotification } from './governance/gate-halt';
import {
  handleSpendCeilingNotification,
  SpendCeilingPauseTracker,
} from './governance/spend-ceiling';
import { hostedSessionRegistry } from './governance/session-registry';
import { installCommand, resolveInterpreter } from './interpreter';
import { resolveCoreDir } from './layout';
import { RecorderPanel } from './recorder-panel';
import { RECORDER_VIEW_ID, RecorderViewProvider } from './recorder-view';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
import { SidecarStatusBar } from './status';
import { StdioSidecarClient } from './stdio-client';
import { SidecarSupervisor } from './supervisor';
import { registerViews } from './views';

let supervisor: SidecarSupervisor | undefined;
let workbench: WorkbenchService | undefined;
let runtimeGeneration = 0;

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
    'text/markdown': { 'Markdown report': ['md'] },
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
  const generation = ++runtimeGeneration;
  const initialWorkspace = workspaceDir();
  workbench = new WorkbenchService({
    workspaceDir, trusted: () => vscode.workspace.isTrusted,
    enabledTiers: readEnabledTiers, sidecar: () => {
      const client = supervisor?.isRunning ? supervisor.currentClient : undefined;
      return client ? { request: (method, params) => client.request(method, params, new AbortController().signal) } : undefined;
    },
    humanApprover: createVscodePermissionApprover(),
    policyPaths: context.extensionPath ? [path.join(context.extensionPath, 'policy', 'acp-permissions.yaml'), path.resolve(context.extensionPath, '..', 'policy', 'acp-permissions.yaml')] : [],
    onError: message => void vscode.window.showErrorMessage(message),
    // Integration credentials go to the OS keychain and nowhere else; the
    // workspace state file never sees one.
    secrets: context.secrets,
  });
  context.subscriptions.push(workbench);
  const workspaceListener = vscode.workspace.onDidChangeWorkspaceFolders?.(() => {
    if (workspaceDir() !== initialWorkspace) {
      ++runtimeGeneration;
      void supervisor?.stop();
      void vscode.window.showWarningMessage('The Meridian workspace changed. Run Developer: Reload Window before continuing.');
    }
    void workbench?.reconcile().catch(error => void vscode.window.showErrorMessage(String(error)));
  });
  if (workspaceListener) context.subscriptions.push(workspaceListener);
  const enabledTiers = readEnabledTiers();
  applyTierContextKeys(enabledTiers);
  const editorSurfaces = createEditorSurfaces({ workspaceDir, request: async (method, params, signal) => {
    const client = supervisor?.currentClient;
    if (!client) throw new Error('The sidecar is not connected yet.');
    return client.request(method, params, signal);
  } });
  context.subscriptions.push(...editorSurfaces.disposables);
  // The Activity Bar container hosts the workbench itself: selecting
  // Meridian Loom resolves this view and the interface is there, with no
  // command in between (the product requirement, and the only VS Code
  // mechanism that satisfies it).
  const workbenchViewDeps = {
    workbench,
    extensionPath: context.extensionPath,
    enabledTiers: readEnabledTiers,
    sidecar: () => supervisor?.currentClient,
    workspaceDir,
    onDownload: saveDownload,
    onError: (message: string) => void vscode.window.showErrorMessage(message),
  };
  const workbenchView = new RecorderViewProvider(workbenchViewDeps);
  context.subscriptions.push(
    ...registerViews(),
    workbenchView,
    vscode.window.registerWebviewViewProvider(RECORDER_VIEW_ID, workbenchView, {
      // A side-bar view is hidden on every Activity Bar switch; losing the
      // workbench each time would be a defect, not a saving. Correctness
      // still does not depend on it — the webview restores from getState().
      webviewOptions: { retainContextWhenHidden: true },
    }),
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
      inspectSource: editorSurfaces.inspect,
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
      if (runtimeGeneration === generation) ++runtimeGeneration;
      // FR-M3-02: any deactivation path — window close, reload, disable —
      // disposes subscriptions, and disposal terminates the sidecar.
      void supervisor?.stop();
    },
  });
  void startRuntime(context, generation);
}

/**
 * Deferred runtime startup. FR-M1-07: if SecretStorage is unavailable the
 * extension surfaces an actionable error and refuses to start — no
 * plaintext fallback, no half-started runtime.
 */
export async function startRuntime(context: vscode.ExtensionContext, generation = ++runtimeGeneration): Promise<void> {
  const current = () => generation === runtimeGeneration && vscode.workspace.isTrusted;
  // Yield first: even the probe call itself must not run inside activate().
  await Promise.resolve();
  if (!current()) return;
  try {
    await SecretStore.verifyAvailable(context.secrets);
    if (!current()) return;
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
    if (!current()) return;
    // FR-M3-05: the interpreter comes from the resolution chain; the
    // resolved path is shown in the status bar.
    const interpreter = await resolveInterpreter();
    if (!current()) return;
    // A resolved interpreter that cannot import the sidecar's dependencies
    // will die at spawn with a ModuleNotFoundError buried in stderr. Say what
    // is wrong and give the exact command, before that happens.
    if (interpreter.missing.length) {
      const command = installCommand(interpreter);
      const choice = await vscode.window.showErrorMessage(
        `Meridian Loom cannot start: ${interpreter.executable} cannot import ` +
          `${interpreter.missing.join(', ')}.`,
        'Copy install command',
      );
      if (choice) await vscode.env.clipboard.writeText(command);
      throw new Error(
        `Python at ${interpreter.executable} is missing ${interpreter.missing.join(', ')}. Run: ${command}`,
      );
    }
    // FR-M10-04/SEC-06: the ledger signing seed lives in the OS keychain
    // (SecretStorage); it is provisioned to the sidecar over the handshake
    // and held in memory there only.
    const ledgerSigningKey = await SecretStore.getOrCreateLedgerSigningKey(
      context.secrets,
    );
    if (!current()) return;
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
    const started = supervisor;
    await started.start();
    if (current() && supervisor === started && started.isRunning) statusBar.showReady(interpreter);
  } catch (error) {
    if (!current()) return;
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
  ++runtimeGeneration;
  workbench?.dispose();
  workbench = undefined;
  const current = supervisor;
  supervisor = undefined;
  await current?.stop();
}
