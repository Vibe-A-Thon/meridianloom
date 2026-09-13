/**
 * Reading the built VSIX — shared by the demo-package check (MV3-T05) and the
 * AI-BOM generator (MV4-T08).
 *
 * One reader, because two would drift and the one that drifted would be the
 * one nobody was watching. That is the same argument `J7` makes about install
 * paths and `trailers.py` makes about trailer parsing.
 *
 * Dependency-free and without shelling out. The first version of the demo
 * check used `tar`, which reads zips on every platform in the matrix — and
 * GNU tar in Git Bash parses a `F:\path` argument as a remote host and tries
 * to *connect* to `F`. A check that fails on the maintainer's own machine
 * over a drive letter is a check that gets skipped.
 *
 * Stored and deflated members only: that is what `vsce` writes, and a bounded
 * reader is easier to reason about than a general one — the same posture
 * `extension/src/workbench/packages.ts` takes with agent archives.
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { inflateRawSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/** `[major, minor, patch]` and any pre-release tag from `name-1.2.3[-tag].vsix`. */
function versionOf(fileName) {
  const match = /-(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\.vsix$/.exec(fileName);
  return match
    ? { triple: match.slice(1, 4).map(Number), prerelease: match[4] }
    : undefined;
}

/**
 * The newest VSIX in `dist/`, or the one named.
 *
 * Newest by **version**, not by name. The first version sorted file names,
 * which picks `0.9.0` over `0.10.0` — and `dist/` routinely keeps an old build
 * beside the new one, so every check reading the package would have validated
 * the wrong artefact and said nothing. When newest genuinely cannot be decided
 * it refuses and asks for the path, rather than guessing: a package check that
 * silently examines some other package is worse than one that stops.
 */
export function findVsix(explicit) {
  if (explicit) return path.resolve(explicit);
  const dist = path.join(root, 'dist');
  if (!existsSync(dist)) return undefined;
  const names = readdirSync(dist).filter((name) => name.endsWith('.vsix'));
  if (names.length === 0) return undefined;
  if (names.length === 1) return path.join(dist, names[0]);

  const candidates = names.map((name) => ({ name, version: versionOf(name) }));
  const unversioned = candidates.filter((candidate) => !candidate.version);
  if (unversioned.length) {
    throw new Error(
      `cannot tell which VSIX in dist/ is newest: ${unversioned
        .map((candidate) => candidate.name)
        .join(', ')} carry no version. Pass the package path explicitly.`,
    );
  }

  const compare = (a, b) => {
    for (let index = 0; index < 3; index += 1) {
      const difference = a.version.triple[index] - b.version.triple[index];
      if (difference !== 0) return difference;
    }
    // Same version: a release outranks its own pre-release.
    if (!a.version.prerelease !== !b.version.prerelease) return a.version.prerelease ? -1 : 1;
    return 0;
  };
  candidates.sort(compare);
  const newest = candidates[candidates.length - 1];
  const tied = candidates.filter((candidate) => compare(candidate, newest) === 0);
  if (tied.length > 1) {
    throw new Error(
      `cannot tell which VSIX in dist/ is newest: ${tied
        .map((candidate) => candidate.name)
        .join(', ')} share a version. Pass the package path explicitly.`,
    );
  }
  return path.join(dist, newest.name);
}

export function openZip(file) {
  const buffer = readFileSync(file);
  // End of central directory: scan back for the signature, tolerating the
  // trailing comment field.
  let eocd = -1;
  for (let at = buffer.length - 22; at >= 0 && at > buffer.length - 22 - 0xffff; at -= 1) {
    if (buffer.readUInt32LE(at) === 0x06054b50) {
      eocd = at;
      break;
    }
  }
  if (eocd < 0) throw new Error(`${path.basename(file)} is not a zip archive`);

  const count = buffer.readUInt16LE(eocd + 10);
  let at = buffer.readUInt32LE(eocd + 16);
  const entries = new Map();
  for (let index = 0; index < count; index += 1) {
    if (buffer.readUInt32LE(at) !== 0x02014b50) break;
    const method = buffer.readUInt16LE(at + 10);
    const compressedSize = buffer.readUInt32LE(at + 20);
    const uncompressedSize = buffer.readUInt32LE(at + 24);
    const nameLength = buffer.readUInt16LE(at + 28);
    const extraLength = buffer.readUInt16LE(at + 30);
    const commentLength = buffer.readUInt16LE(at + 32);
    const localOffset = buffer.readUInt32LE(at + 42);
    const name = buffer.toString('utf8', at + 46, at + 46 + nameLength);
    if (!name.endsWith('/')) {
      entries.set(name, { method, compressedSize, uncompressedSize, localOffset });
    }
    at += 46 + nameLength + extraLength + commentLength;
  }

  /** The member's bytes, exactly as stored. */
  function bytes(name) {
    const entry = entries.get(name);
    if (!entry) throw new Error(`no such member: ${name}`);
    const header = entry.localOffset;
    if (buffer.readUInt32LE(header) !== 0x04034b50) {
      throw new Error(`corrupt local header for ${name}`);
    }
    const nameLength = buffer.readUInt16LE(header + 26);
    const extraLength = buffer.readUInt16LE(header + 28);
    const start = header + 30 + nameLength + extraLength;
    const raw = buffer.subarray(start, start + entry.compressedSize);
    if (entry.method === 0) return raw;
    if (entry.method === 8) return inflateRawSync(raw);
    throw new Error(
      `${name} uses compression method ${entry.method}, which this reader does not accept`,
    );
  }

  /**
   * Write every member under `prefix` into `target`, with the prefix removed.
   *
   * This is how a check runs **the package** rather than the checkout
   * (`MP7`): the soak and the package validation both extract the shipped
   * sidecar and execute that copy. Member names are refused if they would
   * escape `target` — an archive is input, and a `..` in a member name is how
   * an extraction writes somewhere nobody asked it to.
   */
  function extract(prefix, target) {
    const base = path.resolve(target);
    let written = 0;
    for (const name of entries.keys()) {
      if (!name.startsWith(prefix)) continue;
      const out = path.resolve(base, name.slice(prefix.length));
      if (out !== base && !out.startsWith(base + path.sep)) {
        throw new Error(`refusing to extract ${name}: it would land outside ${base}`);
      }
      mkdirSync(path.dirname(out), { recursive: true });
      writeFileSync(out, bytes(name));
      written += 1;
    }
    return written;
  }

  return {
    names: [...entries.keys()],
    extract,
    bytes,
    read: (name) => bytes(name).toString('utf8'),
    /**
     * `sha256:…` of the member's uncompressed bytes. This is what a BOM
     * consumer can re-derive after extracting the package, which is the only
     * digest worth publishing.
     */
    digest: (name) => `sha256:${createHash('sha256').update(bytes(name)).digest('hex')}`,
  };
}
