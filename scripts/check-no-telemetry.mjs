/** No-telemetry guard (audit TASK-104).

Fails the build if an unreviewed network client appears in the extension
host or webview sources. The reviewed, user-configured surfaces are
exactly:

- ``extension/src/adapters/registry-source.ts`` — the adapter/skill
  registry fetch (FR-M16-08); the URL is operator configuration.
- ``extension/src/workbench/integrations.ts`` — connector HTTP transport
  (M19); endpoints are operator configuration.

Everything else must not fetch. The sidecar's only egress is the
configured model provider and the collector's opt-in ``--sink``.

Usage:  node scripts/check-no-telemetry.mjs
*/

import { globSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const REVIEWED = new Map([
  ['extension/src/adapters/registry-source.ts', 'registry fetch (FR-M16-08, operator-configured URL)'],
  ['extension/src/workbench/integrations.ts', 'connector HTTP transport (M19, operator-configured endpoints)'],
]);

const PATTERNS = [
  /\bfetch\s*\(/,
  /new\s+WebSocket\b/,
  /XMLHttpRequest/,
  /sendBeacon/,
  /node:https?['"]/,
  /require\(['"]https?['"]\)/,
  /from\s+['"]https?['"]/,
];

const files = [
  ...globSync('extension/src/**/*.ts', { cwd: root }),
  ...globSync('webview/src/**/*.{ts,tsx}', { cwd: root }),
].filter((f) => !/\.test\.|__mocks__/.test(f));

const problems = [];
for (const file of files) {
  const normalised = file.split(path.sep).join('/');
  const text = readFileSync(path.join(root, file), 'utf8');
  for (const pattern of PATTERNS) {
    if (pattern.test(text) && !REVIEWED.has(normalised)) {
      problems.push(`${file}: matches ${pattern} (not a reviewed network surface)`);
    }
  }
}

if (problems.length) {
  console.error('no-telemetry guard: unreviewed network client found:');
  for (const p of problems) console.error(`  FAIL  ${p}`);
  process.exit(1);
}
console.log(
  `no-telemetry guard: ${files.length} host/webview files clean; ` +
    `reviewed surfaces: ${[...REVIEWED.keys()].join(', ')}`
);
