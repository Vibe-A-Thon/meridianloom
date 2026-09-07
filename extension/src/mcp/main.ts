/**
 * Standalone entrypoint for the Meridian MCP server (FR-M34-06; F1
 * Workstream A task 6).
 *
 * Spawned as its own process, speaking MCP on stdio:
 *
 *   node dist/mcp/mcp-server.js --core <coreDir> [--workspace <dir>]
 *        [--python <interpreter>] [--tiers flight-recorder,governor]
 *
 * The process spawns the Python sidecar over the same framed JSON-RPC the
 * extension host uses (FR-M3-01), forwards every MCP tools/call as one
 * tier-gated, ledger-recorded `mcp/invoke`, and serves the doctor report as
 * a live resource. Stdout carries ONLY MCP frames (FR-M3-09 discipline);
 * diagnostics go to stderr.
 *
 * This module is vscode-free: it runs under plain node, including on a
 * remote host where the workspace lives (FR-M3-11).
 */

import type { SidecarClient } from '../sidecar';
import { StdioSidecarClient } from '../stdio-client';
import type { TierName } from '../../../shared/ts/bus-types';
import { McpServer } from './server';

interface McpServerArgv {
  coreDir: string;
  workspaceDir?: string;
  python?: string;
  tiers?: readonly TierName[];
}

const USAGE =
  'usage: mcp-server --core <coreDir> [--workspace <dir>] [--python <interpreter>] ' +
  '[--tiers flight-recorder,governor]';

export function parseArgv(argv: string[]): McpServerArgv {
  const parsed: McpServerArgv = { coreDir: '' };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    const value = argv[index + 1];
    switch (flag) {
      case '--core':
        parsed.coreDir = value;
        index += 1;
        break;
      case '--workspace':
        parsed.workspaceDir = value;
        index += 1;
        break;
      case '--python':
        parsed.python = value;
        index += 1;
        break;
      case '--tiers':
        parsed.tiers = value.split(',').filter(Boolean) as TierName[];
        index += 1;
        break;
      default:
        throw new Error(`unknown argument: ${flag ?? '(missing)'}\n${USAGE}`);
    }
  }
  if (!parsed.coreDir) {
    throw new Error(`--core <coreDir> is required\n${USAGE}`);
  }
  return parsed;
}

/** The sidecar-backed production backend (McpServerBackend lives in server.ts). */
export function createSidecarBackend(client: SidecarClient): {
  invoke(tool: string, args: Record<string, unknown>): Promise<unknown>;
  doctorRun(): Promise<unknown>;
} {
  // The MCP server owns no cancellation UI; requests live for the
  // connection's lifetime.
  const signal = new AbortController().signal;
  return {
    invoke: (tool, args) => client.request('mcp/invoke', { tool, arguments: args }, signal),
    doctorRun: () => client.request('doctor/run', {}, signal),
  };
}

export async function main(argv: string[]): Promise<void> {
  const options = parseArgv(argv);
  const sidecar = new StdioSidecarClient({
    command: options.python ?? (process.platform === 'win32' ? 'python' : 'python3'),
    cwd: options.coreDir,
    ...(options.workspaceDir ? { workspaceDir: options.workspaceDir } : {}),
    ...(options.tiers ? { tiers: options.tiers } : {}),
    onStderr: (line) => process.stderr.write(`[sidecar] ${line}\n`),
  });
  await sidecar.start();
  process.stderr.write(
    'meridian mcp-server: connected to sidecar; serving MCP on stdio\n',
  );

  const server = new McpServer(createSidecarBackend(sidecar));
  const sidecarExited = new Promise<void>((resolve) => sidecar.on('exit', resolve));
  const stdinEnded = server.serve(process.stdin, process.stdout);
  await Promise.race([stdinEnded, sidecarExited]);

  // The MCP client closed stdin (or the sidecar died): tear the sidecar
  // down politely and never outlive our pipes (FR-M3-02/03).
  await sidecar.request('shutdown', { reason: 'mcp server stdin closed' }, new AbortController().signal).catch(() => undefined);
  sidecar.kill();
  await new Promise((resolve) => sidecar.on('exit', resolve));
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((error: unknown) => {
    process.stderr.write(`meridian mcp-server: ${String(error)}\n`);
    process.exitCode = 1;
  });
}
