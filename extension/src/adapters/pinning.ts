import { createHash } from 'node:crypto';
import { promises as fsp } from 'node:fs';
import path from 'node:path';

/**
 * Adapter digest pinning — `FR-M44-03`…`05`, `SEC-24`, `SEC-33` (MV3-T01).
 *
 * An adapter is a folder, and a folder is mutable. Once Meridian has put one
 * there — from the registry, from a sideloaded package — the question that
 * matters on every subsequent load is *is this still the thing that was
 * installed?* Without an answer, a supply-chain attack is one file write and
 * nobody sees anything: the manifest still parses, the id is unchanged, and
 * the launch command now points somewhere else.
 *
 * So: a content digest at install, stored, and checked at load. A mismatch
 * **refuses the load and names both digests** — naming them matters, because
 * "integrity check failed" tells an operator nothing they can act on, while
 * two hashes and a path tell them exactly what to compare.
 *
 * ## Where the pin lives, and why not in the adapter folder
 *
 * In an index beside the root (`.meridian/adapters/.pins.json`), not inside
 * the adapter. A pin file within the folder it protects can be deleted by
 * whoever edited the folder, and the adapter would come back as merely
 * *unpinned* — which is a legitimate state, so the tamper would read as a
 * hand-placed adapter rather than as an alarm. Keeping the index one level up
 * means removing a pin is itself an edit to a different file.
 *
 * ## What is not pinned, and why that is not a hole
 *
 * `learned/` is excluded. `FR-M31-12` makes it the adapter's own durable
 * state, so pinning it would make every adapter drift the moment it learned
 * anything, and a check that always fires is a check people turn off. Nothing
 * executes from `learned/`: the launch command comes from `manifest.yaml`,
 * which is pinned, and the package reader executes nothing it reads.
 *
 * Builtin adapters are not pinned here. They ship inside the VSIX and their
 * integrity is the package digest's job; reporting them as `builtin` rather
 * than as `pinned` keeps this module from claiming a check it did not make.
 *
 * ## What a pin proves
 *
 * That the bytes on disk are the bytes that were there at install. It says
 * nothing about whether those bytes were trustworthy to begin with — see
 * `docs/SECURITY-AND-DATA.md` §7, which draws the same line for the release
 * `.sha256`.
 */

export const PINS_FILE = '.pins.json';

/** The adapter's own state directory, excluded from the digest (FR-M31-12). */
export const UNPINNED_SUBTREE = 'learned';

export const PIN_ALGORITHM = 'sha256';

/** How an adapter came to be installed. Recorded so a refusal can say. */
export type PinSource = 'registry' | 'sideload' | 'manual';

export interface AdapterPin {
  algorithm: typeof PIN_ALGORITHM;
  digest: string;
  /** ISO-8601 UTC. When the bytes on disk were accepted as the baseline. */
  pinnedAt: string;
  /** How many files the digest covers; a drop is as suspicious as a change. */
  files: number;
  source: PinSource;
}

export type PinIndex = Record<string, AdapterPin>;

/**
 * The three honest answers, plus the two that are not about this adapter's
 * bytes at all. `unpinned` is deliberately distinct from `pinned`: an adapter
 * a person dropped into the folder themselves was never installed by
 * Meridian and has no baseline to compare against, and reporting that as a
 * pass would be the overclaim `P27` forbids (`P26`: the unknown is reported).
 */
export type PinState = 'pinned' | 'drifted' | 'unpinned' | 'builtin' | 'unreadable';

export interface PinVerdict {
  state: PinState;
  /** The digest recorded at install, when there is one. */
  expected?: string;
  /** The digest of what is on disk now. */
  actual?: string;
  /** File counts either side, so a deletion reads as clearly as an edit. */
  expectedFiles?: number;
  actualFiles?: number;
  /** One sentence an operator can act on. Always present. */
  detail: string;
}

/** The filesystem slice pinning needs; injectable so tests stay headless. */
export interface PinFs {
  readdir(dir: string): Promise<string[]>;
  /** Bytes, not text: a digest over decoded UTF-8 would miss a binary edit. */
  readFileBytes(file: string): Promise<Uint8Array>;
  readFileText(file: string): Promise<string>;
  writeFileText(file: string, contents: string): Promise<void>;
  stat(file: string): Promise<{ isDirectory(): boolean }>;
  mkdirp(dir: string): Promise<void>;
}

export const nodePinFs: PinFs = {
  readdir: (dir) => fsp.readdir(dir),
  readFileBytes: (file) => fsp.readFile(file),
  readFileText: (file) => fsp.readFile(file, 'utf8'),
  writeFileText: (file, contents) => fsp.writeFile(file, contents, 'utf8'),
  stat: (file) => fsp.stat(file),
  mkdirp: async (dir) => {
    await fsp.mkdir(dir, { recursive: true });
  },
};

function isEnoent(error: unknown): boolean {
  return (error as NodeJS.ErrnoException)?.code === 'ENOENT';
}

/** Posix separators so a folder digests identically wherever it is read. */
function posix(relative: string): string {
  return relative.split(path.sep).join('/');
}

/**
 * Every file under `dir`, posix-relative, `learned/` excluded.
 *
 * A missing directory throws rather than digesting as empty. An adapter
 * folder that has vanished is not an adapter with no files in it — treating
 * it as one would let a deletion produce a clean, confident digest that
 * simply did not match, which reads as tampering rather than as absence.
 * `verifyAdapterPin` turns the throw into `unreadable`.
 */
async function walk(dir: string, fs: PinFs, base = dir): Promise<string[]> {
  const found: string[] = [];
  const entries = await fs.readdir(dir);
  for (const entry of entries.sort()) {
    const full = path.join(dir, entry);
    const relative = posix(path.relative(base, full));
    if (relative === UNPINNED_SUBTREE || relative.startsWith(`${UNPINNED_SUBTREE}/`)) {
      continue;
    }
    const stats = await fs.stat(full);
    if (stats.isDirectory()) {
      found.push(...(await walk(full, fs, base)));
    } else {
      found.push(relative);
    }
  }
  return found;
}

export interface AdapterDigest {
  digest: string;
  files: number;
}

/**
 * The digest of an adapter folder as it is on disk.
 *
 * Each file contributes its posix-relative path, its byte length and its
 * bytes. The length is in there so that a path and the content after it
 * cannot be shuffled across the boundary between them to collide — the
 * classic framing mistake when concatenating variable-length fields.
 *
 * Byte-exact, which means a folder digested on Windows after a CRLF checkout
 * and the same folder on Linux do not agree. That is correct for what this
 * checks: the pin is written and read on one machine, and normalising line
 * endings would blind it to a real one-byte edit.
 */
export async function computeAdapterDigest(
  dir: string,
  fs: PinFs = nodePinFs,
): Promise<AdapterDigest> {
  const files = await walk(dir, fs);
  const hash = createHash(PIN_ALGORITHM);
  for (const relative of files.sort()) {
    const bytes = await fs.readFileBytes(path.join(dir, relative));
    hash.update(`${relative}\n${bytes.byteLength}\n`);
    hash.update(bytes);
    hash.update('\n');
  }
  return { digest: `${PIN_ALGORITHM}:${hash.digest('hex')}`, files: files.length };
}

function indexPath(root: string): string {
  return path.join(root, PINS_FILE);
}

/** The pins recorded for one adapter root. A missing or unreadable index is
 *  an empty one: adapters then read as `unpinned`, which is honest, rather
 *  than as drifted, which would accuse them of something. */
export async function readPinIndex(root: string, fs: PinFs = nodePinFs): Promise<PinIndex> {
  let text: string;
  try {
    text = await fs.readFileText(indexPath(root));
  } catch (error) {
    if (isEnoent(error)) return {};
    throw error;
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const index: PinIndex = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      const pin = value as Partial<AdapterPin>;
      if (
        pin &&
        pin.algorithm === PIN_ALGORITHM &&
        typeof pin.digest === 'string' &&
        typeof pin.pinnedAt === 'string'
      ) {
        index[id] = {
          algorithm: PIN_ALGORITHM,
          digest: pin.digest,
          pinnedAt: pin.pinnedAt,
          files: typeof pin.files === 'number' ? pin.files : 0,
          source: pin.source === 'registry' || pin.source === 'sideload' ? pin.source : 'manual',
        };
      }
    }
    return index;
  } catch {
    // Untrusted input: a malformed index is discarded, never thrown from a
    // discovery walk. It is read as data and nothing in it is executed.
    return {};
  }
}

export async function writePinIndex(
  root: string,
  index: PinIndex,
  fs: PinFs = nodePinFs,
): Promise<void> {
  await fs.mkdirp(root);
  await fs.writeFileText(indexPath(root), `${JSON.stringify(index, null, 2)}\n`);
}

/**
 * Record what is on disk now as this adapter's baseline (`FR-M44-03`).
 *
 * One function for every install path — registry and sideload alike (`J7`).
 * Two pinning paths would drift, and the one that drifted would be the one
 * nobody was looking at.
 */
export async function pinAdapter(
  root: string,
  id: string,
  dir: string,
  source: PinSource,
  fs: PinFs = nodePinFs,
  now: () => Date = () => new Date(),
): Promise<AdapterPin> {
  const { digest, files } = await computeAdapterDigest(dir, fs);
  const pin: AdapterPin = {
    algorithm: PIN_ALGORITHM,
    digest,
    pinnedAt: now().toISOString(),
    files,
    source,
  };
  const index = await readPinIndex(root, fs);
  await writePinIndex(root, { ...index, [id]: pin }, fs);
  return pin;
}

/**
 * Is this adapter still what was installed (`FR-M44-04`)?
 *
 * Never throws. This runs inside the discovery walk, and a walk that throws
 * on one unreadable folder takes every other adapter down with it — turning
 * an integrity check into an outage.
 */
export async function verifyAdapterPin(
  root: string,
  id: string,
  dir: string,
  options: { tier?: string; index?: PinIndex; fs?: PinFs } = {},
): Promise<PinVerdict> {
  const fs = options.fs ?? nodePinFs;
  if (options.tier === 'builtin') {
    return {
      state: 'builtin',
      detail:
        'Bundled with the extension; its integrity is covered by the release ' +
        'package digest rather than by an install-time pin.',
    };
  }
  const index = options.index ?? (await readPinIndex(root, fs));
  const pin = index[id];

  let actual: AdapterDigest;
  try {
    actual = await computeAdapterDigest(dir, fs);
  } catch (error) {
    return {
      state: 'unreadable',
      expected: pin?.digest,
      detail:
        `The adapter folder could not be read, so its integrity is unknown: ` +
        `${error instanceof Error ? error.message : String(error)}`,
    };
  }

  if (!pin) {
    return {
      state: 'unpinned',
      actual: actual.digest,
      actualFiles: actual.files,
      detail:
        'Placed here directly rather than installed by Meridian, so there is ' +
        'no recorded baseline to compare against. Its contents are not vouched for.',
    };
  }

  if (pin.digest === actual.digest) {
    return {
      state: 'pinned',
      expected: pin.digest,
      actual: actual.digest,
      expectedFiles: pin.files,
      actualFiles: actual.files,
      detail: `Unchanged since it was installed on ${pin.pinnedAt}.`,
    };
  }

  return {
    state: 'drifted',
    expected: pin.digest,
    actual: actual.digest,
    expectedFiles: pin.files,
    actualFiles: actual.files,
    detail: driftDetail(id, dir, pin, actual),
  };
}

/**
 * SEC-33: the refusal names both digests.
 *
 * An operator reading this has to be able to decide whether they did this
 * themselves. "Integrity check failed" cannot answer that; the installed
 * digest, the current one, the file counts and the install date can.
 */
export function driftDetail(
  id: string,
  dir: string,
  pin: AdapterPin,
  actual: AdapterDigest,
): string {
  const counts =
    pin.files === actual.files
      ? `${actual.files} files, unchanged in number`
      : `${pin.files} files at install, ${actual.files} now`;
  return (
    `Adapter '${id}' has changed since it was installed and will not be loaded. ` +
    `Installed ${pin.pinnedAt} as ${pin.digest}; on disk now ${actual.digest} ` +
    `(${counts}). Folder: ${dir}. If you changed it yourself, reinstall it to ` +
    `re-pin; if you did not, treat the current contents as untrusted.`
  );
}
