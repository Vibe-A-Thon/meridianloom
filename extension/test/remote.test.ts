import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { defaultSpawner } from '../src/process';
import { StdioSidecarClient } from '../src/stdio-client';

const manifest = JSON.parse(
  readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf8'),
);

/**
 * FR-M3-11: the extension must run under VS Code Remote — SSH, WSL, Dev
 * Containers, Codespaces — with the sidecar on the remote host. What is
 * headlessly verifiable:
 *
 *  1. extensionKind is "workspace", so VS Code installs/executes the
 *     extension on the remote host where the repository lives.
 *  2. Spawning uses no shell and inherits the (remote) environment, so the
 *     same code path works identically local and remote.
 *  3. No host-side source hard-codes a local absolute path.
 */
describe('remote readiness (FR-M3-11)', () => {
  it('declares extensionKind "workspace" so the sidecar runs on the remote host', () => {
    expect(manifest.extensionKind).toContain('workspace');
  });

  it('spawns without a shell and honours the passed environment', async () => {
    const child = defaultSpawner({
      command: 'python',
      args: ['-c', 'import os, sys; sys.stdout.write(os.environ.get("MERIDIAN_TEST_MARKER", "missing"))'],
      cwd: process.cwd(),
      env: { ...process.env, MERIDIAN_TEST_MARKER: 'remote-env-ok' },
    });
    let out = '';
    child.stdout?.setEncoding?.('utf8');
    child.stdout?.on('data', (chunk: string) => {
      out += chunk;
    });
    const code = await new Promise<number | null>((resolve) =>
      child.on('exit', (exitCode) => resolve(exitCode)),
    );
    expect(code).toBe(0);
    expect(out).toBe('remote-env-ok');
  });

  it('passes the parent PID for the orphan guard through the environment', async () => {
    let capturedEnv: NodeJS.ProcessEnv | undefined;
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: '/anywhere',
      spawner: (options) => {
        capturedEnv = options.env;
        throw new Error('stop after capture');
      },
    });
    await expect(client.start()).rejects.toThrow('stop after capture');
    expect(capturedEnv?.MERIDIAN_PARENT_PID).toBe(String(process.pid));
    // The inherited PATH is what makes remote interpreter lookup work.
    expect(capturedEnv?.PATH ?? capturedEnv?.Path).toBeDefined();
  });

  it('host sources hard-code no local absolute paths', () => {
    const srcDir = path.resolve(__dirname, '..', 'src');
    const files: string[] = readdirSync(srcDir)
      .filter((name) => name.endsWith('.ts'))
      .map((name) => path.join(srcDir, name));
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      // Windows drive paths and POSIX absolute literals would break remote.
      expect(source, file).not.toMatch(/['"][A-Za-z]:[\\/]/);
      expect(source, file).not.toMatch(/['"]\/(usr|opt|home|Users)\//);
    }
  });
});
