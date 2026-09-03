import * as vscode from 'vscode';
import { registerCommands } from './commands';
import { resolveCoreDir } from './layout';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
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
  try {
    // Interpreter resolution per the FR-M3-05 chain lands in task 8; until
    // then the platform default is used.
    const command = process.platform === 'win32' ? 'python' : 'python3';
    const coreDir = await resolveCoreDir(context.extensionPath);
    supervisor = new SidecarSupervisor({
      clientFactory: () =>
        new StdioSidecarClient({
          command,
          cwd: coreDir,
          onStderr: (line) => console.debug('[sidecar]', line),
        }),
      onError: (message) => void vscode.window.showErrorMessage(message),
    });
    await supervisor.start();
  } catch {
    // start() already surfaced an actionable message via onError.
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
