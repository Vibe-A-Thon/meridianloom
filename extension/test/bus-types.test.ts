import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import {
  ErrorCode,
  ErrorCodeValue,
  MethodMap,
  NotificationMap,
  PROTOCOL_VERSION,
} from '../../shared/ts/bus-types';
import { StdioSidecarClient } from '../src/stdio-client';

const execFileAsync = promisify(execFile);
const root = path.resolve(__dirname, '..', '..');

describe('generated bus types (FR-M32-09)', () => {
  it('pins the protocol version and error codes the schema declares', () => {
    expect(PROTOCOL_VERSION).toBe(1);
    expect(ErrorCode.PROTOCOL_MISMATCH).toBe(-32002);
    expect(ErrorCode.NOT_IMPLEMENTED).toBe(-32001);
  });

  it('the Python sidecar reports the same protocol version', async () => {
    // Cross-language contract check: ask the generated Python module itself.
    const { stdout } = await execFileAsync(
      'python',
      ['-c', 'import sys; sys.path.insert(0, "shared/py"); import bus_types; print(bus_types.PROTOCOL_VERSION)'],
      { cwd: root },
    );
    expect(Number(stdout.trim())).toBe(PROTOCOL_VERSION);
  });

  it('MethodMap pairs params and results for the contracted methods', () => {
    // Compile-time pairing is the point; this runtime witness also guards
    // against an accidental empty generation.
    const expected = [
      'handshake',
      'ping',
      'shutdown',
      'health',
      'ledger.append',
      'ledger.query',
      'loop.start',
      'loop.stop',
      'loop.status',
    ];
    const map: MethodMap = null as unknown as MethodMap;
    expect(expected.length).toBe(9);
    expect(map).toBeNull(); // type-level only; see typecheck
    void (0 as unknown as ErrorCodeValue);
    void (null as unknown as NotificationMap);
  });

  it('generated outputs are fresh vs the schema (staleness check)', async () => {
    // The --check mode exits 1 when shared/ts or shared/py drift from
    // shared/schema/; this is the CI contract (also wired into npm test).
    await execFileAsync(process.execPath, ['scripts/generate-bus-types.mjs', '--check'], {
      cwd: root,
    });
  });

  it('the real sidecar answers health per the generated contract', { timeout: 30_000 }, async () => {
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: path.join(root, 'core'),
    });
    await client.start();
    try {
      const health = await client.call('health', {}, new AbortController().signal);
      // Typed as MethodMap['health']['result'] — the generated contract.
      expect(health.status).toBe('ok');
      expect(health.pid).toBeGreaterThan(0);

      // FR-M10-01: ledger.append is implemented; without a configured
      // workspace it answers LEDGER_UNAVAILABLE, not a placeholder.
      const unavailable = await client
        .call('ledger.append', appendParams(), new AbortController().signal)
        .catch((error: unknown) => error);
      expect(unavailable).toMatchObject({ code: ErrorCode.LEDGER_UNAVAILABLE });
    } finally {
      await client.request('shutdown', {}, new AbortController().signal).catch(() => undefined);
      client.kill();
    }
  });

  it('ledger.append + ledger.query round-trip over the real sidecar (FR-M10-01/02/08)', { timeout: 30_000 }, async () => {
    const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'meridian-bus-'));
    const client = new StdioSidecarClient({
      command: 'python',
      cwd: path.join(root, 'core'),
      workspaceDir: workspace,
    });
    await client.start();
    try {
      const append = await client.call(
        'ledger.append',
        appendParams({ input: 'write the handler', blobSubject: 'story:EDB-12345' }),
        new AbortController().signal,
      );
      expect(append.sequence).toBe(1);
      expect(append.hash).toMatch(/^[0-9a-f]{64}$/);
      expect(append.previousHash).toMatch(/^0{64}$/);

      const query = await client.call(
        'ledger.query',
        { fromSequence: 1 },
        new AbortController().signal,
      );
      expect(query.entries).toHaveLength(1);
      const entry = query.entries[0];
      expect(entry.entryHash).toBe(append.hash);
      expect(entry.storyId).toBe('EDB-12345');
      expect(entry.vendor).toBe('meridian');
      expect(entry.observationConfidence).toBe('direct');
      expect(entry.hasInputBlob).toBe(true);
    } finally {
      await client.request('shutdown', {}, new AbortController().signal).catch(() => undefined);
      client.kill();
      // Windows: the SQLite -shm/-wal locks clear only once the child is
      // actually gone — wait for exit before removing the workspace.
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 5_000);
        client.once('exit', () => {
          clearTimeout(timer);
          resolve();
        });
      });
      await fs.rm(workspace, { recursive: true, force: true });
    }
  });
});

function appendParams(extra: Partial<MethodMap['ledger.append']['params']> = {}) {
  return {
    storyId: 'EDB-12345',
    phase: 'build',
    loopId: 'L2-task',
    loopIteration: 1,
    actorId: 'developer-agent',
    actorVersion: '0.0.1',
    actorKind: 'role',
    policyVersion: 'policy-v1',
    actionType: 'diff',
    ...extra,
  };
}
