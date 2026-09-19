import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import { activate } from '../src/extension';

const SRC_DIR = path.resolve(__dirname, '..', 'src');

const BANNED_SYNC_APIS = [
  'readFileSync',
  'writeFileSync',
  'appendFileSync',
  'readdirSync',
  'statSync',
  'lstatSync',
  'existsSync',
  'mkdirSync',
  'rmSync',
  'execSync',
  'execFileSync',
  'spawnSync',
];

function listSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return listSourceFiles(full);
    }
    return entry.name.endsWith('.ts') ? [full] : [];
  });
}

describe('host thread discipline (FR-M1-04)', () => {
  it('host-side sources contain no blocking synchronous I/O or process APIs', () => {
    const offenders: string[] = [];
    for (const file of listSourceFiles(SRC_DIR)) {
      const source = readFileSync(file, 'utf8');
      for (const api of BANNED_SYNC_APIS) {
        if (new RegExp(`\\b${api}\\s*\\(`).test(source)) {
          offenders.push(`${path.relative(SRC_DIR, file)}: ${api}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('activate() is synchronous and returns nothing to await', () => {
    (vscode as unknown as { __reset(): void }).__reset();
    const context = {
      subscriptions: [],
      secrets: new vscode.MemorySecretStorage(),
    } as vscode.ExtensionContext;
    const result = activate(context);
    expect(result).toBeUndefined();
    expect(result).not.toBeInstanceOf(Promise);
  });

  it('activation stays well under the 50 ms host-thread budget', () => {
    (vscode as unknown as { __reset(): void }).__reset();
    const context = {
      subscriptions: [],
      secrets: new vscode.MemorySecretStorage(),
    } as vscode.ExtensionContext;
    const start = performance.now();
    activate(context);
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(50);
  });
});
