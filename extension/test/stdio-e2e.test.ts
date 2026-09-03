import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { StdioSidecarClient } from '../src/stdio-client';

const coreDir = path.resolve(__dirname, '..', '..', 'core');

function findPython(): string | undefined {
  for (const candidate of ['python', 'python3']) {
    try {
      const executable = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (executable) {
        return candidate;
      }
    } catch {
      // try the next candidate
    }
  }
  return undefined;
}

const python = findPython();
const run = python ? describe : describe.skip;

run('StdioSidecarClient end-to-end against the real Python sidecar (FR-M3-01)', () => {
  it(
    'round-trips handshake, ping and shutdown over real stdio',
    { timeout: 30_000 },
    async () => {
      const stderrLines: string[] = [];
      const client = new StdioSidecarClient({
        command: python!,
        cwd: coreDir,
        onStderr: (line) => stderrLines.push(line),
      });
      await client.start();

      const ping = await client.request<{ pong: boolean; seq: number }>(
        'ping',
        {},
        new AbortController().signal,
      );
      expect(ping.pong).toBe(true);
      expect(ping.seq).toBe(1);

      const shutdown = await client.request<{ ok: boolean }>(
        'shutdown',
        { reason: 'e2e test' },
        new AbortController().signal,
      );
      expect(shutdown.ok).toBe(true);

      const exitCode = await new Promise<number | null>((resolve) => {
        client.on('exit', (code) => resolve(code));
      });
      expect(exitCode).toBe(0);

      // FR-M3-09: the sidecar logged, but only to stderr.
      expect(stderrLines.some((line) => line.includes('sidecar serving'))).toBe(true);
    },
  );

  it(
    'rejects requests once the sidecar has died',
    { timeout: 30_000 },
    async () => {
      const client = new StdioSidecarClient({ command: python!, cwd: coreDir });
      await client.start();
      client.kill();
      await new Promise<void>((resolve) => client.on('exit', () => resolve()));
      await expect(
        client.request('ping', {}, new AbortController().signal),
      ).rejects.toThrow(/not running/);
    },
  );
});

if (!python) {
  // eslint-disable-next-line no-console
  console.warn('python not found on PATH; skipping real sidecar e2e tests');
}
