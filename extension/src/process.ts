/**
 * Minimal child-process surface the sidecar client and supervisor depend on.
 * Abstracted from node:child_process.ChildProcess so tests can inject fakes
 * and so the supervisor can swap the spawner under VS Code Remote (FR-M3-11)
 * without touching RPC logic.
 */
import { spawn } from 'node:child_process';
import type { EventEmitter } from 'node:events';

export interface ProcessStream extends EventEmitter {
  write?(data: string): boolean;
  setEncoding?(encoding: string): unknown;
}

export interface ChildProcessLike extends EventEmitter {
  readonly pid?: number;
  readonly stdin: ProcessStream | null;
  readonly stdout: ProcessStream | null;
  readonly stderr: ProcessStream | null;
  readonly killed: boolean;
  kill(signal?: NodeJS.Signals | number): boolean;
}

export interface SpawnOptions {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export type ProcessSpawner = (options: SpawnOptions) => ChildProcessLike;

/**
 * Default spawner. Never uses a shell: a shell wrapper would put an extra
 * process between us and the interpreter, breaking signal delivery and the
 * teardown contract (FR-M3-02/03). Spawning directly also keeps behaviour
 * identical on the remote extension host (FR-M3-11).
 */
export const defaultSpawner: ProcessSpawner = (options) =>
  spawn(options.command, options.args, {
    cwd: options.cwd,
    env: options.env,
    shell: false,
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  }) as unknown as ChildProcessLike;
