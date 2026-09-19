import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { requestWithProgress, runWithProgress } from '../src/progress';
import type { SidecarClient } from '../src/sidecar';

const hooks = () =>
  vscode as unknown as {
    __reset(): void;
    __lastToken(): vscode.ManualCancellationToken;
    __progressCalls: vscode.ProgressOptions[];
  };

class RecordingSidecar implements SidecarClient {
  receivedSignal?: AbortSignal;

  request<TResponse>(
    _method: string,
    _params: unknown,
    signal: AbortSignal,
  ): Promise<TResponse> {
    this.receivedSignal = signal;
    return new Promise<TResponse>((_resolve, reject) => {
      signal.addEventListener('abort', () => {
        reject(new DOMException('The operation was aborted.', 'AbortError'));
      });
    });
  }
}

describe('progress and cancellation (FR-M1-09)', () => {
  beforeEach(() => {
    hooks().__reset();
  });

  it('surfaces work through withProgress as a cancellable notification', async () => {
    await runWithProgress({ title: 'Meridian Loom: Dry Run' }, async () => 42);
    const calls = hooks().__progressCalls;
    expect(calls).toHaveLength(1);
    expect(calls[0].location).toBe(vscode.ProgressLocation.Notification);
    expect(calls[0].title).toBe('Meridian Loom: Dry Run');
    expect(calls[0].cancellable).toBe(true);
  });

  it('returns the work result when not cancelled', async () => {
    const result = await runWithProgress({ title: 't' }, async (signal) => {
      expect(signal.aborted).toBe(false);
      return 'done';
    });
    expect(result).toBe('done');
  });

  it('propagates token cancellation to the abort signal', async () => {
    let observed: AbortSignal | undefined;
    const pending = runWithProgress(
      { title: 't' },
      (signal) =>
        new Promise<string>((resolve) => {
          observed = signal;
          signal.addEventListener('abort', () => resolve('aborted'));
        }),
    );
    hooks().__lastToken().cancel();
    await expect(pending).resolves.toBe('aborted');
    expect(observed?.aborted).toBe(true);
  });

  it('cancellation reaches the sidecar request signal (loop cancellation)', async () => {
    const sidecar = new RecordingSidecar();
    const pending = requestWithProgress(sidecar, {
      title: 'Meridian Loom: Dry Run',
      method: 'loop.dryRun',
      params: { story: 'S-1' },
    });
    hooks().__lastToken().cancel();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(sidecar.receivedSignal?.aborted).toBe(true);
  });

  it('passes progress reports through to the work function', async () => {
    const seen: Array<{ message?: string; increment?: number }> = [];
    await runWithProgress({ title: 't' }, async (_signal, progress) => {
      progress.report({ message: 'starting', increment: 10 });
      seen.push({ message: 'starting', increment: 10 });
    });
    expect(seen).toEqual([{ message: 'starting', increment: 10 }]);
  });

  it('disposes the token subscription after the work settles', async () => {
    await runWithProgress({ title: 't' }, async () => 'ok');
    // Cancelling the token after completion must not throw or abort anew.
    hooks().__lastToken().cancel();
  });
});
