import { access } from 'node:fs/promises';
import path from 'node:path';

/**
 * Where the meridian_core package lives, in both install shapes:
 *
 * - Packaged VSIX: the packaging script copies the Python sources to
 *   `<extensionPath>/sidecar/`, so the sidecar ships with the extension and
 *   is found on the (possibly remote) extension host (FR-M3-11).
 * - Development checkout: `<extensionPath>/../core` inside this repository.
 *
 * Returns the directory that is used as the child process cwd and must
 * contain the `meridian_core` package directory. Async: existence checks
 * must not block the extension host thread (FR-M1-04).
 */
export async function resolveCoreDir(extensionPath: string): Promise<string> {
  const candidates = [
    path.join(extensionPath, 'sidecar'),
    path.resolve(extensionPath, '..', 'core'),
  ];
  for (const candidate of candidates) {
    try {
      await access(path.join(candidate, 'meridian_core', '__main__.py'));
      return candidate;
    } catch {
      // try the next shape
    }
  }
  throw new Error(
    'Meridian Core sidecar sources not found. Looked in: ' +
      candidates.join(', ') +
      '. If you installed from a VSIX, reinstall the extension; in a ' +
      'development checkout, run from the repository root.',
  );
}
