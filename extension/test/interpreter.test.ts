import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import {
  InterpreterResolutionError,
  MIN_PYTHON_VERSION,
  pathCandidates,
  resolveInterpreter,
  installCommand,
  RUNTIME_DEPENDENCIES,
  type Probe,
} from '../src/interpreter';

const mock = vscode as unknown as {
  __reset(): void;
  __configuration: Map<string, unknown>;
  __extensions: Map<string, unknown>;
};

const OK = { executable: '/usr/bin/python3.11', version: [3, 11, 9] as [number, number, number] };

function probeOf(map: Record<string, typeof OK | Error>): Probe {
  return async (command: string) => {
    const entry = map[command];
    if (!entry) {
      throw new Error(`spawn ${command} ENOENT`);
    }
    if (entry instanceof Error) {
      throw entry;
    }
    return entry;
  };
}

beforeEach(() => mock.__reset());

describe('sidecar dependency contract and recovery', () => {
  it('checks every pinned runtime distribution in pyproject.toml', () => {
    const project = readFileSync(path.resolve(__dirname, '../../core/pyproject.toml'), 'utf8');
    const dependencies = project.split('dependencies = [')[1].split(']')[0];
    const pins = [...dependencies.matchAll(/"([A-Za-z0-9_-]+==[^"\s]+)"/g)].map(match => match[1]);
    expect(Object.values(RUNTIME_DEPENDENCIES).sort()).toEqual(pins.sort());
  });

  it('uses pinned pip distribution names and a literal PowerShell executable', () => {
    const command = installCommand({ ...OK, source: 'setting', executable: "C:\\O'Brien $tools\\python.exe", missing: ['yaml', 'tree_sitter'] }, 'win32');
    expect(command).toBe("& 'C:\\O''Brien $tools\\python.exe' -m pip install 'PyYAML==6.0.2' 'tree-sitter==0.25.1'");
  });

  it('quotes shell metacharacters in POSIX recovery commands', () => {
    expect(installCommand({ ...OK, source: 'setting', executable: "/opt/it's $(safe)/python", missing: ['cryptography'] }, 'linux'))
      .toBe("'/opt/it'\\''s $(safe)/python' -m pip install 'cryptography==49.0.0'");
  });

  it('refuses to turn an unknown probe result into a pip argument', () => {
    expect(() => installCommand({ ...OK, source: 'path', missing: ['--index-url=untrusted'] }))
      .toThrow('Unknown sidecar dependency');
  });
});

describe('interpreter resolution chain (FR-M3-05)', () => {
  it('prefers the configured interpreterPath over everything', async () => {
    mock.__configuration.set('meridian.python.interpreterPath', '/opt/custom/python');
    mock.__extensions.set('ms-python.python', {
      environments: {
        getActiveEnvironmentPath: () => ({ path: '/venv/bin/python' }),
      },
    });
    const probe = probeOf({
      '/opt/custom/python': { executable: '/opt/custom/python', version: [3, 12, 1] },
    });
    const resolution = await resolveInterpreter({ probe });
    expect(resolution.source).toBe('setting');
    expect(resolution.executable).toBe('/opt/custom/python');
    expect(resolution.version).toEqual([3, 12, 1]);
  });

  it('falls through to the Python extension environment API', async () => {
    mock.__extensions.set('ms-python.python', {
      environments: {
        getActiveEnvironmentPath: () => ({ path: '/venv/bin/python' }),
        resolveEnvironment: () =>
          Promise.resolve({ executable: { uri: { fsPath: '/venv/bin/python' } } }),
      },
    });
    const probe = probeOf({ '/venv/bin/python': OK });
    const resolution = await resolveInterpreter({ probe });
    expect(resolution.source).toBe('python-extension');
  });

  it('falls through to PATH when neither setting nor Python extension exist', async () => {
    const probe = probeOf({ python3: OK });
    const resolution = await resolveInterpreter({ probe, platform: 'linux' });
    expect(resolution.source).toBe('path');
    expect(resolution.executable).toBe('/usr/bin/python3.11');
  });

  it('skips candidates that fail to spawn and records why', async () => {
    const probe = probeOf({ python: OK });
    const resolution = await resolveInterpreter({ probe, platform: 'win32' });
    expect(resolution.source).toBe('path');
    expect(resolution.executable).toBe('/usr/bin/python3.11');
  });

  it('rejects an interpreter older than 3.11 and keeps looking', async () => {
    mock.__configuration.set('meridian.python.interpreterPath', '/old/python');
    const probe = probeOf({
      '/old/python': { executable: '/old/python', version: [3, 9, 7] },
      python3: OK,
    });
    const resolution = await resolveInterpreter({ probe, platform: 'linux' });
    expect(resolution.source).toBe('path');
  });

  it('fails with an actionable error listing every attempt', async () => {
    mock.__configuration.set('meridian.python.interpreterPath', '/broken/python');
    const probe = probeOf({
      '/broken/python': { executable: '/broken/python', version: [3, 8, 0] },
    });
    const failure = await resolveInterpreter({ probe, platform: 'linux' }).catch(
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(InterpreterResolutionError);
    const message = (failure as Error).message;
    expect(message).toContain('3.8.0 is too old');
    expect(message).toContain('Python extension (not installed');
    expect(message).toContain('bundled runtime (none shipped per D4)');
    expect(message).toContain('ENOENT');
    expect(message).toContain('meridian.python.interpreterPath');
  });

  it('probes PATH candidates in platform order', () => {
    expect(pathCandidates('win32')).toEqual(['python', 'python3']);
    expect(pathCandidates('linux')).toEqual(['python3', 'python']);
    expect(pathCandidates('darwin')).toEqual(['python3', 'python']);
  });

  it('declares 3.11 as the minimum (matches core/pyproject.toml)', () => {
    expect(MIN_PYTHON_VERSION).toEqual([3, 11]);
  });
});

describe('real probe against this machine', () => {
  it('resolves a real interpreter with version >= 3.11', { timeout: 30_000 }, async () => {
    // No injected probe: exercises the actual spawn + version parse.
    const resolution = await resolveInterpreter();
    expect(resolution.version[0]).toBeGreaterThanOrEqual(3);
    expect(resolution.version[1]).toBeGreaterThanOrEqual(11);
    expect(resolution.executable).toBeTruthy();
  });
});
