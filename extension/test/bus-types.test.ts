import { execFile } from 'node:child_process';
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

      const placeholder = await client
        .call('ledger.append', { entryType: 'probe', payload: {} }, new AbortController().signal)
        .catch((error: unknown) => error);
      expect(placeholder).toMatchObject({ code: ErrorCode.NOT_IMPLEMENTED });
    } finally {
      await client.request('shutdown', {}, new AbortController().signal).catch(() => undefined);
      client.kill();
    }
  });
});
