/**
 * Adapter discovery (FR-M31-02, re-based on ACP per FR-M34-02): adapters are
 * discovered from three roots, in precedence order — the workspace's
 * `.meridian/adapters/`, the user-level `~/.meridian/adapters/`, and the
 * builtin (extension-bundled) set. A workspace adapter shadows a user adapter
 * with the same id, which shadows a builtin one. Invalid adapters are listed
 * with their validation errors and are NOT loaded (FR-M31-03, fail-closed).
 */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { discoverAdapters, type AdapterFs } from '../src/adapters/discovery';

function manifestYaml(id: string, extra = ''): string {
  return `
adapter: { id: ${id}, version: 1.0.0, provenance: custom }
acp: { command: ./${id}, args: [acp] }
role: { fills: [Developer] }
permissions: { allow: [read] }
${extra}
`;
}

describe('adapter discovery across three tiers (FR-M31-02)', () => {
  let root: string;
  let workspaceDir: string;
  let userDir: string;
  let builtinDir: string;

  function adapterDir(base: string, id: string): string {
    const dir = path.join(base, id);
    mkdirSync(dir, { recursive: true });
    return dir;
  }

  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), 'meridian-adapters-'));
    workspaceDir = path.join(root, 'workspace');
    userDir = path.join(root, 'user');
    builtinDir = path.join(root, 'builtin');
    mkdirSync(workspaceDir, { recursive: true });
    mkdirSync(userDir, { recursive: true });
    mkdirSync(builtinDir, { recursive: true });
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('discovers adapters from all three roots with tier tags', async () => {
    writeFileSync(path.join(adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'ws-agent'), 'manifest.yaml'), manifestYaml('ws-agent'));
    writeFileSync(path.join(adapterDir(path.join(userDir, '.meridian', 'adapters'), 'user-agent'), 'manifest.yaml'), manifestYaml('user-agent'));
    writeFileSync(path.join(adapterDir(builtinDir, 'builtin-agent'), 'manifest.yaml'), manifestYaml('builtin-agent'));

    const result = await discoverAdapters({ workspaceDir, userDir, builtinDir });
    expect(result.invalid).toEqual([]);
    expect(result.adapters.map((a) => [a.id, a.tier])).toEqual([
      ['ws-agent', 'workspace'],
      ['user-agent', 'user'],
      ['builtin-agent', 'builtin'],
    ]);
    // The whole adapter directory travels with the manifest (FR-M31-12
    // portability: the folder is the unit).
    expect(result.adapters[0].dir).toContain(path.join('.meridian', 'adapters', 'ws-agent'));
  });

  it('precedence: workspace shadows user, user shadows builtin', async () => {
    writeFileSync(path.join(adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'same'), 'manifest.yaml'), manifestYaml('same'));
    writeFileSync(path.join(adapterDir(path.join(userDir, '.meridian', 'adapters'), 'same'), 'manifest.yaml'), manifestYaml('same'));
    writeFileSync(path.join(adapterDir(builtinDir, 'same'), 'manifest.yaml'), manifestYaml('same'));
    writeFileSync(path.join(adapterDir(builtinDir, 'only-builtin'), 'manifest.yaml'), manifestYaml('only-builtin'));

    const result = await discoverAdapters({ workspaceDir, userDir, builtinDir });
    const same = result.adapters.filter((a) => a.id === 'same');
    expect(same).toHaveLength(1);
    expect(same[0].tier).toBe('workspace');
    expect(result.adapters.map((a) => a.id)).toContain('only-builtin');
  });

  it('an invalid adapter is listed with errors and NOT loaded (fail-closed)', async () => {
    writeFileSync(path.join(adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'broken'), 'manifest.yaml'), 'adapter: { id: "!!!" }\n');
    writeFileSync(path.join(adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'good'), 'manifest.yaml'), manifestYaml('good'));

    const result = await discoverAdapters({ workspaceDir, userDir, builtinDir });
    expect(result.adapters.map((a) => a.id)).toEqual(['good']);
    expect(result.invalid).toHaveLength(1);
    expect(result.invalid[0].id).toBe('!!!');
    expect(result.invalid[0].errors.length).toBeGreaterThan(0);
    expect(result.invalid[0].tier).toBe('workspace');
  });

  it('a directory without a manifest is not an adapter at all', async () => {
    adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'not-an-adapter');
    const result = await discoverAdapters({ workspaceDir, userDir, builtinDir });
    expect(result.adapters).toEqual([]);
    expect(result.invalid).toEqual([]);
  });

  it('missing roots are tolerated (a tier with no directory contributes nothing)', async () => {
    const result = await discoverAdapters({ workspaceDir: path.join(root, 'nope'), userDir, builtinDir });
    expect(result.adapters).toEqual([]);
    expect(result.invalid).toEqual([]);
  });

  it('supports the manifest.yml spelling too', async () => {
    writeFileSync(path.join(adapterDir(path.join(workspaceDir, '.meridian', 'adapters'), 'yml-agent'), 'manifest.yml'), manifestYaml('yml-agent'));
    const result = await discoverAdapters({ workspaceDir, userDir, builtinDir });
    expect(result.adapters.map((a) => a.id)).toEqual(['yml-agent']);
  });

  it('works through the injected fs seam (Windows-robust path joining)', async () => {
    const wsRoot = path.join('/', 'ws');
    const adaptersRoot = path.join(wsRoot, '.meridian', 'adapters');
    const fakeDir = path.join(adaptersRoot, 'fake');
    const files = new Map<string, string>();
    const dirs = new Set<string>([fakeDir, adaptersRoot]);
    const fs: AdapterFs = {
      // Returns the entries whose parent is `dir`, rather than one fixed
      // name for every directory. The fixed-name version answered 'fake' for
      // the adapter folder as well as for the root, which meant walking the
      // folder found a child that did not exist — invisible while nothing
      // recursed, and a phantom file the moment the digest walk (MV3-T01)
      // did. A fake filesystem that does not model a filesystem fails the
      // next thing to read it, not the thing it was written for.
      async readdir(dir) {
        if (!dirs.has(dir)) throw Object.assign(new Error(`ENOENT: ${dir}`), { code: 'ENOENT' });
        const children = new Set<string>();
        for (const known of [...files.keys(), ...dirs]) {
          if (known === dir) continue;
          const parent = path.dirname(known);
          if (parent === dir) children.add(path.basename(known));
        }
        return [...children];
      },
      async readFile(p) {
        const text = files.get(p);
        if (text === undefined) throw Object.assign(new Error(`ENOENT: ${p}`), { code: 'ENOENT' });
        return text;
      },
      async stat(p) {
        return { isDirectory: () => dirs.has(p) };
      },
    };
    files.set(path.join(fakeDir, 'manifest.yaml'), manifestYaml('fake'));
    const result = await discoverAdapters(
      { workspaceDir: wsRoot, userDir: path.join('/', 'user'), builtinDir: path.join('/', 'builtin') },
      fs,
    );
    expect(result.adapters.map((a) => a.id)).toEqual(['fake']);
    expect(result.adapters[0].tier).toBe('workspace');
  });
});
