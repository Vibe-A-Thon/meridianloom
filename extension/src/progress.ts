import * as vscode from 'vscode';
import type { SidecarClient } from './sidecar';

export interface ProgressWorkOptions {
  title: string;
}

export type ProgressWork<T> = (
  signal: AbortSignal,
  progress: vscode.Progress<{ message?: string; increment?: number }>,
) => Promise<T>;

/**
 * FR-M1-09: all long-running work surfaces through withProgress, always
 * cancellable. User cancellation of the VS Code cancellation token aborts
 * an AbortSignal; work passes that signal to SidecarClient.request so the
 * cancellation reaches the sidecar loop.
 */
export async function runWithProgress<T>(
  options: ProgressWorkOptions,
  work: ProgressWork<T>,
): Promise<T> {
  return vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: options.title,
      cancellable: true,
    },
    async (progress, token) => {
      const controller = new AbortController();
      if (token.isCancellationRequested) {
        controller.abort();
      }
      const subscription = token.onCancellationRequested(() => {
        controller.abort();
      });
      try {
        return await work(controller.signal, progress);
      } finally {
        subscription.dispose();
      }
    },
  ) as Promise<T>;
}

/**
 * Convenience wrapper for the common case: one cancellable sidecar request
 * shown as progress.
 */
export async function requestWithProgress<TResponse>(
  sidecar: SidecarClient,
  options: ProgressWorkOptions & { method: string; params?: unknown },
): Promise<TResponse> {
  return runWithProgress(options, (signal) =>
    sidecar.request<TResponse>(options.method, options.params ?? {}, signal),
  );
}
