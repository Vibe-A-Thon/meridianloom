import * as vscode from 'vscode';
import { registerCommands } from './commands';
import { SecretStorageUnavailableError, SecretStore } from './secrets';
import { registerViews } from './views';

/**
 * FR-M1-04: activation performs synchronous registration only. The runtime
 * startup (SecretStorage probe, then the sidecar) is deferred off the call
 * stack so the extension host thread is never blocked.
 */
export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(...registerViews(), ...registerCommands());
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
  // Sidecar spawn lands with the sidecar client (Workstream B).
}

export function deactivate(): void {
  // Sidecar teardown lands with the sidecar client (Workstream B).
}
