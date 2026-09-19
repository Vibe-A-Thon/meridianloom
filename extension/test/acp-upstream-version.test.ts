/**
 * FR-M34-05 (F1 Workstream A task 7): gentle drift guard for the upstream
 * publication seam.
 *
 * `extension/src/acp/UPSTREAM.md` declares the supported
 * `@zed-industries/agent-client-protocol` version (machine-readable marker:
 * `<!-- supported-acp-sdk: X.Y.Z -->`). This test compares that declaration
 * against the version the extension actually pins (package.json, plus the
 * installed copy when present) and WARNS — never fails — on drift, so a
 * dependabot-style bump cannot silently invalidate the conformance target
 * or the publication plan. A missing declaration or a missing dependency
 * is still a hard failure: those are repo defects, not drift.
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const extensionRoot = path.resolve(__dirname, '..');
const upstreamPath = path.join(extensionRoot, 'src', 'acp', 'UPSTREAM.md');

function declaredSupportedVersion(): string | undefined {
  const text = readFileSync(upstreamPath, 'utf8');
  const match = text.match(/<!--\s*supported-acp-sdk:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*-->/);
  return match?.[1];
}

function pinnedDependencyVersion(): string | undefined {
  const manifest = JSON.parse(
    readFileSync(path.join(extensionRoot, 'package.json'), 'utf8'),
  ) as { dependencies?: Record<string, string> };
  return manifest.dependencies?.['@zed-industries/agent-client-protocol'];
}

function installedVersion(): string | undefined {
  const installedManifest = path.join(
    extensionRoot,
    'node_modules',
    '@zed-industries',
    'agent-client-protocol',
    'package.json',
  );
  if (!existsSync(installedManifest)) {
    return undefined;
  }
  const manifest = JSON.parse(readFileSync(installedManifest, 'utf8')) as {
    version?: string;
  };
  return manifest.version;
}

describe('FR-M34-05: ACP SDK drift guard (warn, never fail)', () => {
  it('declares a supported version in UPSTREAM.md', () => {
    expect(declaredSupportedVersion()).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it('pins the ACP SDK as a dependency', () => {
    expect(pinnedDependencyVersion()).toMatch(/^\^?\d+\.\d+\.\d+$/);
  });

  it('warns on drift between the declared and pinned versions, but stays green', () => {
    const declared = declaredSupportedVersion();
    const pinned = (pinnedDependencyVersion() ?? '').replace(/^\^/, '');
    const installed = installedVersion();
    const participants = [
      ['declared (UPSTREAM.md)', declared],
      ['pinned (package.json)', pinned],
      ['installed (node_modules)', installed],
    ] as const;
    const versions = new Set(participants.filter(([, v]) => v).map(([, v]) => v));
    if (versions.size > 1) {
      // eslint-disable-next-line no-console
      console.warn(
        '[FR-M34-05] @zed-industries/agent-client-protocol version drift:\n' +
          participants.map(([label, v]) => `  ${label}: ${v ?? '(absent)'}`).join('\n') +
          '\nBump the supported-acp-sdk declaration in extension/src/acp/UPSTREAM.md ' +
          'deliberately, with the ACP conformance suite green.',
      );
    }
    // The seam warns; it must never fail the suite on drift alone.
    expect(versions.size).toBeGreaterThanOrEqual(1);
  });

  it('installed copy, when present, matches the pinned major line', () => {
    const pinned = pinnedDependencyVersion();
    const installed = installedVersion();
    if (pinned && installed) {
      expect(installed.split('.')[0]).toBe(pinned.replace(/^\^/, '').split('.')[0]);
    }
  });
});
