import * as vscode from 'vscode';
import { registerCommands } from './commands';
import { resolveInterpreter } from './interpreter';
import { resolveCoreDir } from './layout';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
import { SidecarStatusBar } from './status';
import { StdioSidecarClient } from './stdio-client';
import { SidecarSupervisor } from './supervisor';
import { registerViews } from './views';

let supervisor: SidecarSupervisor | undefined;

/**
 * FR-M1-04: activation performs synchronous registration only. The runtime
 * startup (SecretStorage probe, then the sidecar) is deferred off the call
 * stack so the extension host thread is never blocked.
 */
export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(...registerViews(), ...registerCommands());
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
    supervisor = new SidecarSupervisor({
      clientFactory: () =>
        new StdioSidecarClient({
          command: interpreter.executable,
          cwd: coreDir,
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
