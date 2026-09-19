import * as vscode from 'vscode';
import type { InterpreterResolution } from './interpreter';

export type SidecarState = 'starting' | 'ready' | 'failed';

/**
 * FR-M3-05: the resolved interpreter is shown in the status bar, so a
 * misresolved environment is visible instead of being debugged blind.
 * The item also carries the sidecar lifecycle state.
 */
export class SidecarStatusBar {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
    this.item.show();
  }

  showStarting(): void {
    this.item.text = '$(sync~spin) Meridian: starting';
    this.item.tooltip = 'Meridian Core sidecar is starting';
  }

  showReady(resolution: InterpreterResolution): void {
    this.item.text = `$(check) Meridian: Python ${resolution.version.join('.')}`;
    this.item.tooltip =
      `Meridian Core sidecar ready\nInterpreter: ${resolution.executable}\n` +
      `Resolved via: ${resolution.source}`;
  }

  showFailed(reason: string): void {
    this.item.text = '$(error) Meridian: failed';
    this.item.tooltip = reason;
  }

  dispose(): void {
    this.item.dispose();
  }
}
