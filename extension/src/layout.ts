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
 *
 * **The development checkout is checked first**, and the order matters. The
 * two shapes never legitimately coexist: an installed VSIX has `sidecar/` and
 * no `../core`, and a checkout has `../core`. Both being present means a
 * checkout with a staged `sidecar/` left behind — the packager removes it in a
 * `finally`, but an interrupted run on Windows can die before that executes.
 * With the staged copy checked first, the extension then silently ran a
 * frozen snapshot of the Python sources, and every sidecar change made
 * afterwards simply did not take effect — no error, just old behaviour. The
 * live source is the right answer whenever it exists, so it wins.
 */
export async function resolveCoreDir(extensionPath: string): Promise<string> {
  const candidates = [
    path.resolve(extensionPath, '..', 'core'),
    path.join(extensionPath, 'sidecar'),
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
