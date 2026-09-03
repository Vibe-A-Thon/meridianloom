import * as vscode from 'vscode';
import { registerCommands } from './commands';
import { registerViews } from './views';

/**
 * FR-M1-04: activation performs synchronous registration only. Any heavier
 * work (SecretStorage probe, sidecar spawn) is deferred off the call stack
 * so the extension host thread is never blocked.
 */
export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(...registerViews(), ...registerCommands());
}

export function deactivate(): void {
  // Sidecar teardown lands with the sidecar client (Workstream B).
}
