import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import * as vscode from 'vscode';

const execFileAsync = promisify(execFile);

/**
 * Python interpreter resolution (FR-M3-05) and its actionable errors
 * (FR-M3-04). The chain is exactly the spec's order:
 *
 *  1. the `meridian.python.interpreterPath` setting;
 *  2. the VS Code Python extension's environment API, if installed;
 *  3. a bundled runtime — per D4 we ship none, so this step always misses;
 *  4. `python3`/`python` on PATH.
 *
 * Every candidate is probed with `-c 'import sys, json; …'` and must report
 * >= MIN_PYTHON_VERSION; the probe returns the canonical sys.executable so
 * the child is always spawned by absolute path. Every miss is recorded and
 * surfaced in the final error, so "not found" always says what was tried.
 *
 * Remote (FR-M3-11): under VS Code Remote the extension host — and therefore
 * this resolution — runs on the remote host, so the setting, the Python
 * extension's remote environments, and PATH are all the *remote* ones. No
 * local path ever crosses the wire.
 */

export const MIN_PYTHON_VERSION: readonly [number, number] = [3, 11];

export type InterpreterSource = 'setting' | 'python-extension' | 'bundled' | 'path';

export interface InterpreterResolution {
  /** Canonical absolute path (sys.executable reported by the probe). */
  executable: string;
  source: InterpreterSource;
  version: [number, number, number];
}

export interface ProbeResult {
  executable: string;
  version: [number, number, number];
}

export type Probe = (command: string) => Promise<ProbeResult>;

export class InterpreterResolutionError extends Error {
  constructor(readonly attempts: string[]) {
    super(
      'Meridian Loom could not find a usable Python interpreter (>= ' +
        `${MIN_PYTHON_VERSION.join('.')}). Tried, in order:\n` +
        attempts.map((attempt) => `  - ${attempt}`).join('\n') +
        '\nInstall Python 3.11+ or set meridian.python.interpreterPath to one.',
    );
    this.name = 'InterpreterResolutionError';
  }
}

const VERSION_PROBE_SNIPPET =
  'import sys, json; print(json.dumps({"executable": sys.executable, "version": list(sys.version_info[:3])}))';

/** Default probe: spawn the candidate, parse its self-reported version. */
export const spawnProbe: Probe = async (command) => {
  const { stdout } = await execFileAsync(command, ['-c', VERSION_PROBE_SNIPPET], {
    timeout: 10_000,
    windowsHide: true,
  });
  const parsed = JSON.parse(stdout.trim()) as {
    executable: string;
    version: [number, number, number];
  };
  return parsed;
};

function versionOk(version: [number, number, number]): boolean {
  return version[0] > MIN_PYTHON_VERSION[0] ||
    (version[0] === MIN_PYTHON_VERSION[0] && version[1] >= MIN_PYTHON_VERSION[1]);
}

function configuredPath(): string | undefined {
  const value = vscode.workspace
    .getConfiguration('meridian.python')
    .get<string>('interpreterPath');
  return value && value.trim().length > 0 ? value.trim() : undefined;
}

/**
 * Step 2: the Python extension's environment API. Accessed defensively —
 * the API has changed shape across releases, and its absence must simply
 * move the chain along.
 */
async function pythonExtensionInterpreter(): Promise<string | undefined> {
  const extension = vscode.extensions.getExtension('ms-python.python');
  if (!extension) {
    return undefined;
  }
  const api = (await extension.activate()) as {
    environments?: {
      getActiveEnvironmentPath?: () => { path?: string } | undefined;
      resolveEnvironment?: (env: { path?: string }) =>
        | Promise<{ executable?: { uri?: { fsPath?: string } } } | undefined>
        | { executable?: { uri?: { fsPath?: string } } }
        | undefined;
    };
    settings?: { getExecutionDetails?: () => { execCommand?: string[] } };
  };
  const activePath = api.environments?.getActiveEnvironmentPath?.();
  if (activePath?.path) {
    const resolved = await api.environments?.resolveEnvironment?.(activePath);
    const fsPath = resolved?.executable?.uri?.fsPath;
    if (fsPath) {
      return fsPath;
    }
    return activePath.path;
  }
  const execCommand = api.settings?.getExecutionDetails?.().execCommand;
  return execCommand?.[0];
}

/** PATH candidates, platform-ordered (FR-M3-05 step 4). */
export function pathCandidates(platform: NodeJS.Platform = process.platform): string[] {
  return platform === 'win32' ? ['python', 'python3'] : ['python3', 'python'];
}

export interface ResolveOptions {
  probe?: Probe;
  platform?: NodeJS.Platform;
}

export async function resolveInterpreter(
  options: ResolveOptions = {},
): Promise<InterpreterResolution> {
  const probe = options.probe ?? spawnProbe;
  const attempts: string[] = [];

  const candidates: Array<{ source: InterpreterSource; describe: string; command: string | undefined }> = [];

  const configured = configuredPath();
  candidates.push({
    source: 'setting',
    describe: configured
      ? `meridian.python.interpreterPath (${configured})`
      : 'meridian.python.interpreterPath (not set)',
    command: configured,
  });

  let pythonExtension: string | undefined;
  try {
    pythonExtension = await pythonExtensionInterpreter();
  } catch {
    pythonExtension = undefined;
  }
  candidates.push({
    source: 'python-extension',
    describe: pythonExtension
      ? `Python extension environment (${pythonExtension})`
      : 'Python extension (not installed or no active environment)',
    command: pythonExtension,
  });

  // Step 3, per D4: no bundled runtime is shipped, so there is nothing to
  // probe. Recorded so the final diagnostic shows the full chain.
  candidates.push({
    source: 'bundled',
    describe: 'bundled runtime (none shipped per D4)',
    command: undefined,
  });

  for (const candidate of pathCandidates(options.platform)) {
    candidates.push({
      source: 'path',
      describe: `'${candidate}' on PATH`,
      command: candidate,
    });
  }

  for (const candidate of candidates) {
    if (!candidate.command) {
      attempts.push(`${candidate.describe}: skipped`);
      continue;
    }
    try {
      const probed = await probe(candidate.command);
      if (!versionOk(probed.version)) {
        attempts.push(
          `${candidate.describe}: Python ${probed.version.join('.')} is too old ` +
            `(need >= ${MIN_PYTHON_VERSION.join('.')})`,
        );
        continue;
      }
      return {
        executable: probed.executable,
        source: candidate.source,
        version: probed.version,
      };
    } catch (error) {
      attempts.push(`${candidate.describe}: ${(error as Error).message}`);
    }
  }
  throw new InterpreterResolutionError(attempts);
}
