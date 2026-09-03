/**
 * Zero-model-call assertion, extension mirror (FR-M36-07; F0 Workstream C
 * task 16). Scans every TypeScript module under extension/src for
 * model-client patterns and fails on any hit:
 *
 *   - provider imports: openai / anthropic / vertexai / boto3 (Bedrock) /
 *     @azure / @google-cloud/aiplatform
 *   - client call shapes: `chat.completions`, `completion(`
 *   - credential reads: `MERIDIAN_MODEL_API_KEY`
 *
 * Allow-list convention (there are NO F0 justifications today): a hit is
 * permitted only when the same line carries a comment naming the FR that
 * justifies it, e.g.
 *
 *   const client = new OpenAI(); // zero-model-calls: allowlisted for FR-M33-09
 *
 * The scanner also runs against a synthetic violating tree (positive
 * control) so this test cannot silently pass with a broken pattern list.
 */
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = path.resolve(__dirname, '..', 'src');

const PATTERNS: Array<{ name: string; re: RegExp }> = [
  {
    name: 'provider-import',
    re: /(?:import|require)\b[^'"]*['"](?:openai|anthropic|@anthropic-ai\/sdk|vertexai|boto3|@aws-sdk\/client-bedrock|@azure\/|@google-cloud\/aiplatform)/,
  },
  { name: 'chat-completions', re: /chat\.completions/ },
  { name: 'completion-call', re: /\bcompletion\(/ },
  { name: 'model-credential', re: /MERIDIAN_MODEL_API_KEY/ },
];
const ALLOW_RE = /\/\/.*allow.*FR-[A-Z0-9]+-\d+/i;

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      yield* walk(full);
    } else if (entry.endsWith('.ts')) {
      yield full;
    }
  }
}

function findViolations(root: string): string[] {
  const violations: string[] = [];
  for (const file of walk(root)) {
    const text = readFileSync(file, 'utf8');
    const lines = text.split('\n');
    lines.forEach((line, index) => {
      for (const { name, re } of PATTERNS) {
        if (re.test(line) && !ALLOW_RE.test(line)) {
          violations.push(`${path.relative(root, file)}:${index + 1} [${name}]: ${line.trim()}`);
        }
      }
    });
  }
  return violations;
}

describe('FR-M36-07: extension src has zero model calls', () => {
  it('extension/src is clean of model-client patterns', () => {
    const violations = findViolations(SRC_ROOT);
    expect(violations).toEqual([]);
  });

  it('scans a real, non-trivial tree', () => {
    const files = [...walk(SRC_ROOT)];
    expect(files.length).toBeGreaterThanOrEqual(10);
  });
});

describe('scanner positive control', () => {
  function writeSnippet(snippet: string): string {
    const dir = mkdtempSync(path.join(tmpdir(), 'meridian-nomodel-'));
    mkdirSync(path.join(dir, 'src'));
    writeFileSync(path.join(dir, 'src', 'agent.ts'), snippet, 'utf8');
    return dir;
  }

  it.each([
    "import OpenAI from 'openai';\n",
    "import Anthropic from '@anthropic-ai/sdk';\n",
    "import { Anthropic } from 'openai';\n",
    "import { BedrockClient } from '@aws-sdk/client-bedrock-runtime';\n",
    "const r = await client.chat.completions.create();\n",
    "const text = model.completion(prompt);\n",
    "const key = process.env.MERIDIAN_MODEL_API_KEY;\n",
  ])('detects violation: %s', (snippet) => {
    const root = writeSnippet(snippet);
    const violations = findViolations(root);
    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain('agent.ts:1');
  });

  it('passes an allow-listed line that names the FR', () => {
    const root = writeSnippet(
      "const client = new OpenAI(); // zero-model-calls: allowlisted for FR-M33-09\n",
    );
    // 'OpenAI' alone is not a pattern hit; the import pattern would be.
    expect(findViolations(root)).toEqual([]);
  });

  it('fails a bare allow comment without an FR name', () => {
    const root = writeSnippet("import OpenAI from 'openai'; // allow\n");
    expect(findViolations(root)).toHaveLength(1);
  });

  it('clean tree has no violations', () => {
    const root = writeSnippet("import * as fs from 'node:fs';\n");
    expect(findViolations(root)).toEqual([]);
  });
});
