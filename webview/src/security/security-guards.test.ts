/**
 * Static guards for VIGUIX_Final §17 / §18 — the bans that are mechanisable
 * are mechanised here. Scans every source file under webview/src (except
 * this guard file itself) and fails on:
 *
 *   - localStorage / sessionStorage / indexedDB — all persistence goes
 *     through getState/setState and the extension host (§17, absolute)
 *   - dangerouslySetInnerHTML — agent output renders as text only (X-08)
 *   - eval( — no eval, ever (CSP forbids it; the source must not need it)
 *
 * The scanner runs against a synthetic violating tree (positive control) so
 * this test cannot silently pass with a broken pattern list. Same pattern
 * as extension/test/no-model-calls.test.ts.
 */
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = path.resolve(__dirname, '..');
const SELF = path.resolve(__filename);

const PATTERNS: Array<{ name: string; re: RegExp }> = [
  { name: 'localStorage', re: /\blocalStorage\b/ },
  { name: 'sessionStorage', re: /\bsessionStorage\b/ },
  { name: 'indexedDB', re: /\bindexedDB\b|\bIndexedDB\b/ },
  { name: 'dangerouslySetInnerHTML', re: /dangerouslySetInnerHTML/ },
  { name: 'eval', re: /\beval\s*\(/ },
];

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== 'node_modules' && entry !== 'dist' && !entry.startsWith('.')) {
        yield* walk(full);
      }
    } else if (/\.(ts|tsx)$/.test(entry) && full !== SELF) {
      yield full;
    }
  }
}

function findViolations(root: string): string[] {
  const violations: string[] = [];
  for (const file of walk(root)) {
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, index) => {
      for (const { name, re } of PATTERNS) {
        if (re.test(line)) {
          violations.push(`${path.relative(root, file)}:${index + 1} [${name}]: ${line.trim()}`);
        }
      }
    });
  }
  return violations;
}

describe('VIGUIX_Final §17: webview src is free of web storage and raw HTML', () => {
  it('webview/src has zero violations', () => {
    expect(findViolations(SRC_ROOT)).toEqual([]);
  });

  it('scans a real, non-trivial tree', () => {
    expect([...walk(SRC_ROOT)].length).toBeGreaterThanOrEqual(15);
  });
});

describe('scanner positive control', () => {
  function writeSnippet(snippet: string): string {
    const dir = mkdtempSync(path.join(tmpdir(), 'meridian-webview-guard-'));
    mkdirSync(path.join(dir, 'src'));
    writeFileSync(path.join(dir, 'src', 'evil.ts'), snippet, 'utf8');
    return dir;
  }

  it.each([
    'localStorage.setItem("k", "v");\n',
    'sessionStorage.getItem("k");\n',
    'const db = indexedDB.open("x");\n',
    'const db = window.IndexedDB;\n',
    'element.dangerouslySetInnerHTML = html;\n',
    'const x = eval("1+1");\n',
  ])('detects violation: %s', (snippet) => {
    const violations = findViolations(writeSnippet(snippet));
    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain('evil.ts:1');
  });

  it('clean tree has no violations', () => {
    expect(findViolations(writeSnippet('const fine = 1 + 1;\n'))).toEqual([]);
  });
});
