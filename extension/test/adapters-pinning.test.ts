import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { discoverAdapters } from '../src/adapters/discovery';
import {
  computeAdapterDigest,
  pinAdapter,
  readPinIndex,
  verifyAdapterPin,
  writePinIndex,
  type PinFs,
} from '../src/adapters/pinning';

/**
 * Adapter digest pinning — `FR-M44-03`…`05`, `SEC-24`, `SEC-33` (MV3-T01).
 *
 * The property under test is not "a hash is computed". It is that **an
 * adapter which changed after it was installed does not load, and the
 * refusal names both digests.** A check that detects drift and then loads
 * anyway is a log line; a check that refuses without saying what changed
 * leaves an operator unable to tell their own edit from an attack.
 *
 * The states are deliberately five, not two. `unpinned` — an adapter a
 * person dropped in themselves — is not a failure and must not read as one,
 * and it must not read as a pass either (`P26`).
 */

/** An in-memory PinFs. Keys are posix paths; directories are implied. */
function memoryFs(files: Record<string, string | Uint8Array>): PinFs & {
  files: Map<string, Uint8Array>;
} {
  const encoder = new TextEncoder();
  const store = new Map<string, Uint8Array>();
  for (const [key, value] of Object.entries(files)) {
    store.set(norm(key), typeof value === 'string' ? encoder.encode(value) : value);
  }

  function norm(p: string): string {
    return p.split(path.sep).join('/').replace(/^\.\//, '');
  }

  function enoent(p: string): NodeJS.ErrnoException {
    const error = new Error(`ENOENT: no such file or directory, '${p}'`) as NodeJS.ErrnoException;
    error.code = 'ENOENT';
    return error;
  }

  function childrenOf(dir: string): Set<string> {
    const prefix = dir === '' ? '' : `${dir}/`;
    const names = new Set<string>();
    for (const key of store.keys()) {
      if (!key.startsWith(prefix)) continue;
      const rest = key.slice(prefix.length);
      if (rest === '') continue;
      names.add(rest.split('/')[0]);
    }
    return names;
  }

  return {
    files: store,
    async readdir(dir) {
      const key = norm(dir);
      const names = childrenOf(key);
      if (names.size === 0 && !store.has(key)) throw enoent(dir);
      return [...names];
    },
    async readFileBytes(file) {
      const bytes = store.get(norm(file));
      if (!bytes) throw enoent(file);
      return bytes;
    },
    async readFileText(file) {
      const bytes = store.get(norm(file));
      if (!bytes) throw enoent(file);
      return new TextDecoder().decode(bytes);
    },
    async writeFileText(file, contents) {
      store.set(norm(file), encoder.encode(contents));
    },
    async stat(file) {
      const key = norm(file);
      if (store.has(key)) return { isDirectory: () => false };
      if (childrenOf(key).size > 0) return { isDirectory: () => true };
      throw enoent(file);
    },
    async mkdirp() {
      /* directories are implied by their files */
    },
  };
}

const ROOT = 'ws/.meridian/adapters';
const DIR = `${ROOT}/acme-java-developer`;

const MANIFEST = `
adapter:
  id: acme-java-developer
  version: 2.3.0
  provenance: custom
  vendor: acme
acp:
  command: npx
  args: ["-y", "@acme/java-developer@2.3.0", "--acp"]
role:
  fills: [Developer]
  tier: L2
permissions:
  allow: [read, search]
learning:
  trainable: [policy]
  frozen: [skills]
governance:
  autonomy_tier: suggest
  probation:
    task_set: probation/
    pass_threshold: 0.85
`;

function installedAdapter(extra: Record<string, string> = {}) {
  return memoryFs({
    [`${DIR}/manifest.yaml`]: MANIFEST,
    [`${DIR}/README.md`]: 'An adapter.\n',
    ...extra,
  });
}

describe('the digest', () => {
  it('is stable for the same bytes', async () => {
    const a = await computeAdapterDigest(DIR, installedAdapter());
    const b = await computeAdapterDigest(DIR, installedAdapter());
    expect(a.digest).toBe(b.digest);
    expect(a.files).toBe(2);
  });

  it('changes when one byte changes', async () => {
    const before = await computeAdapterDigest(DIR, installedAdapter());
    const after = await computeAdapterDigest(
      DIR,
      installedAdapter({ [`${DIR}/README.md`]: 'An adapter!\n' }),
    );
    expect(after.digest).not.toBe(before.digest);
  });

  it('changes when a file is added or removed', async () => {
    const base = await computeAdapterDigest(DIR, installedAdapter());
    const added = await computeAdapterDigest(
      DIR,
      installedAdapter({ [`${DIR}/extra.md`]: '' }),
    );
    expect(added.digest).not.toBe(base.digest);
    expect(added.files).toBe(3);
  });

  it('does not confuse which file content belongs to', async () => {
    // The framing property. Concatenating path and content without saying
    // how long each is lets two different folders hash the same; the length
    // between them is what prevents it. Same bytes, different owners.
    const left = await computeAdapterDigest(
      'x',
      memoryFs({ 'x/a': '1', 'x/b': '' }),
    );
    const right = await computeAdapterDigest(
      'x',
      memoryFs({ 'x/a': '', 'x/b': '1' }),
    );
    expect(left.digest).not.toBe(right.digest);
  });

  it('ignores what the adapter learns', async () => {
    // FR-M31-12: `learned/` is the adapter's own durable state. Pinning it
    // would make every adapter drift the moment it learned anything, and a
    // check that always fires is a check people switch off.
    const before = await computeAdapterDigest(DIR, installedAdapter());
    const after = await computeAdapterDigest(
      DIR,
      installedAdapter({ [`${DIR}/learned/notes.md`]: 'a thing I learned\n' }),
    );
    expect(after.digest).toBe(before.digest);
  });
});

describe('the pin', () => {
  it('records what was installed and reads back as unchanged', async () => {
    const fs = installedAdapter();
    const pin = await pinAdapter(ROOT, 'acme-java-developer', DIR, 'registry', fs, () =>
      new Date('2026-09-13T10:00:00Z'),
    );
    expect(pin.source).toBe('registry');
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('pinned');
    expect(verdict.expected).toBe(pin.digest);
  });

  it('lives outside the folder it protects', async () => {
    // A pin inside the adapter can be deleted by whoever edited the adapter,
    // and the tamper would come back as merely `unpinned` — a legitimate
    // state. Removing this pin means editing a different file, one level up.
    const fs = installedAdapter();
    await pinAdapter(ROOT, 'acme-java-developer', DIR, 'registry', fs);
    const inside = [...fs.files.keys()].filter((key) => key.startsWith(`${DIR}/`));
    expect(inside).toEqual([`${DIR}/manifest.yaml`, `${DIR}/README.md`]);
    expect(fs.files.has(`${ROOT}/.pins.json`)).toBe(true);
  });

  it('refuses a one-byte mutation and names both digests', async () => {
    // SEC-33, and the negative control the plan asks for. "Integrity check
    // failed" cannot tell an operator whether they did this themselves;
    // two hashes and a path can.
    const fs = installedAdapter();
    const pin = await pinAdapter(ROOT, 'acme-java-developer', DIR, 'registry', fs);
    fs.files.set(`${DIR}/manifest.yaml`, new TextEncoder().encode(
      MANIFEST.replace('@acme/java-developer@2.3.0', '@evil/java-developer@9.9.9'),
    ));

    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('drifted');
    expect(verdict.expected).toBe(pin.digest);
    expect(verdict.actual).not.toBe(pin.digest);
    expect(verdict.detail).toContain(pin.digest);
    expect(verdict.detail).toContain(verdict.actual!);
    expect(verdict.detail).toContain('will not be loaded');
  });

  it('says so when files were removed, not only when they changed', async () => {
    const fs = installedAdapter();
    await pinAdapter(ROOT, 'acme-java-developer', DIR, 'registry', fs);
    fs.files.delete(`${DIR}/README.md`);
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('drifted');
    expect(verdict.expectedFiles).toBe(2);
    expect(verdict.actualFiles).toBe(1);
    expect(verdict.detail).toContain('2 files at install, 1 now');
  });
});

describe('the states that are not failures', () => {
  it('an adapter nobody installed is unpinned, not drifted', async () => {
    // Hot plug (FR-M31-04) is a supported way to get an adapter. Refusing a
    // hand-placed folder would break it; calling it `pinned` would claim a
    // check nobody made.
    const fs = installedAdapter();
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('unpinned');
    expect(verdict.detail).toContain('not vouched for');
  });

  it('a builtin adapter says which check covers it', async () => {
    const fs = installedAdapter();
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, {
      fs,
      tier: 'builtin',
    });
    expect(verdict.state).toBe('builtin');
    expect(verdict.detail).toContain('release package digest');
  });

  it('a vanished folder is unreadable, not drifted', async () => {
    // A deletion is absence, not tampering. Digesting a missing folder as
    // "zero files" would produce a confident mismatch and accuse somebody.
    const fs = installedAdapter();
    await pinAdapter(ROOT, 'acme-java-developer', DIR, 'registry', fs);
    fs.files.delete(`${DIR}/manifest.yaml`);
    fs.files.delete(`${DIR}/README.md`);
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('unreadable');
  });
});

describe('the index is untrusted input', () => {
  it('a malformed index is discarded rather than thrown', async () => {
    const fs = installedAdapter({ [`${ROOT}/.pins.json`]: '{ not json' });
    await expect(readPinIndex(ROOT, fs)).resolves.toEqual({});
    const verdict = await verifyAdapterPin(ROOT, 'acme-java-developer', DIR, { fs });
    expect(verdict.state).toBe('unpinned');
  });

  it('an entry missing its algorithm or digest is dropped', async () => {
    const fs = installedAdapter({
      [`${ROOT}/.pins.json`]: JSON.stringify({
        'acme-java-developer': { digest: 'sha256:abc' },
        other: { algorithm: 'sha256', digest: 'sha256:def', pinnedAt: 'now' },
      }),
    });
    const index = await readPinIndex(ROOT, fs);
    expect(Object.keys(index)).toEqual(['other']);
  });

  it('round-trips a written index', async () => {
    const fs = installedAdapter();
    await writePinIndex(
      ROOT,
      {
        'acme-java-developer': {
          algorithm: 'sha256',
          digest: 'sha256:abc',
          pinnedAt: '2026-09-13T10:00:00.000Z',
          files: 2,
          source: 'sideload',
        },
      },
      fs,
    );
    const index = await readPinIndex(ROOT, fs);
    expect(index['acme-java-developer'].source).toBe('sideload');
  });
});

describe('discovery refuses what drifted', () => {
  const roots = { workspaceDir: 'ws' };

  /** The text slice discovery walks; separate from the byte slice pinning uses. */
  function discoveryFs(files: Record<string, string>) {
    const fs = memoryFs(files);
    return {
      readdir: fs.readdir,
      readFile: fs.readFileText,
      stat: fs.stat,
    };
  }

  it('admits a pinned adapter and carries its verdict', async () => {
    const result = await discoverAdapters(
      roots,
      discoveryFs({ [`${DIR}/manifest.yaml`]: MANIFEST }),
      {
        verifyPin: async () => ({ state: 'pinned', detail: 'unchanged' }),
      },
    );
    expect(result.adapters.map((a) => a.id)).toEqual(['acme-java-developer']);
    expect(result.adapters[0].pin.state).toBe('pinned');
    expect(result.invalid).toEqual([]);
  });

  it('does not load a drifted adapter, and reports why', async () => {
    const result = await discoverAdapters(
      roots,
      discoveryFs({ [`${DIR}/manifest.yaml`]: MANIFEST }),
      {
        verifyPin: async () => ({
          state: 'drifted',
          expected: 'sha256:aaa',
          actual: 'sha256:bbb',
          detail: "Adapter 'acme-java-developer' has changed: sha256:aaa vs sha256:bbb",
        }),
      },
    );
    expect(result.adapters).toEqual([]);
    expect(result.invalid).toHaveLength(1);
    expect(result.invalid[0].pin?.state).toBe('drifted');
    expect(result.invalid[0].errors[0]).toContain('sha256:aaa');
    expect(result.invalid[0].errors[0]).toContain('sha256:bbb');
  });

  it('still loads an adapter nobody pinned', async () => {
    const result = await discoverAdapters(
      roots,
      discoveryFs({ [`${DIR}/manifest.yaml`]: MANIFEST }),
      {
        verifyPin: async () => ({ state: 'unpinned', detail: 'no baseline' }),
      },
    );
    expect(result.adapters).toHaveLength(1);
    expect(result.adapters[0].pin.state).toBe('unpinned');
  });
});
