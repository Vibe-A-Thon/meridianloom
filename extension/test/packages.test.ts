import { deflateRawSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import {
  assembleFromArchive,
  classifyMarkdown,
  parseFrontmatter,
  parsePackage,
  readZip,
  slugify,
} from '../src/workbench/packages';

/**
 * Package ingestion (`vision.md` §2.8).
 *
 * A user hands the workbench a Markdown file or a ZIP and expects an agent,
 * a skill or an instruction file to appear. These tests pin the two things
 * that matter about that: it reads the shapes people actually have, and it
 * refuses the shapes that would be unsafe to present as though they were
 * part of the package.
 *
 * Nothing here executes anything it reads. The reader's output is data.
 */

// --- a minimal ZIP writer, so the fixtures are real archives -------------

function zip(members: { name: string; body: string; store?: boolean }[]): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;

  for (const member of members) {
    const nameBytes = Buffer.from(member.name, 'utf8');
    const raw = Buffer.from(member.body, 'utf8');
    const stored = member.store === true;
    const data = stored ? raw : deflateRawSync(raw);
    const crc = crc32(raw);

    const local = Buffer.alloc(30 + nameBytes.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(stored ? 0 : 8, 8);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    nameBytes.copy(local, 30);
    locals.push(local, data);

    const central = Buffer.alloc(46 + nameBytes.length);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(stored ? 0 : 8, 10);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(raw.length, 24);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt32LE(offset, 42);
    nameBytes.copy(central, 46);
    centrals.push(central);

    offset += local.length + data.length;
  }

  const centralBytes = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(members.length, 8);
  eocd.writeUInt16LE(members.length, 10);
  eocd.writeUInt32LE(centralBytes.length, 12);
  eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, centralBytes, eocd]);
}

function crc32(buffer: Buffer): number {
  let crc = ~0;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1)
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return ~crc >>> 0;
}

const base64 = (buffer: Buffer) => buffer.toString('base64');

// --- frontmatter and classification -------------------------------------

describe('frontmatter', () => {
  it('splits YAML frontmatter from the body and keeps the body verbatim', () => {
    const { data, body } = parseFrontmatter(
      '---\nname: Atlas\nversion: 2.1\n---\n# Atlas\n\nDoes the thing.\n',
    );
    expect(data.name).toBe('Atlas');
    expect(body).toBe('# Atlas\n\nDoes the thing.');
  });

  it('survives malformed YAML rather than refusing the document', () => {
    // Refusing a user's instruction file over a stray colon is worse than
    // importing it without its metadata.
    const { data, body } = parseFrontmatter('---\nname: [unclosed\n---\nBody text\n');
    expect(data).toEqual({});
    expect(body).toBe('Body text');
  });

  it('accepts CRLF and a UTF-8 BOM, because real files carry both', () => {
    const { data, body } = parseFrontmatter('﻿---\r\nname: Atlas\r\n---\r\nBody\r\n');
    expect(data.name).toBe('Atlas');
    expect(body).toBe('Body');
  });
});

describe('classifying a Markdown document', () => {
  it('lets declared frontmatter kind win over the filename', () => {
    expect(classifyMarkdown('SKILL.md', { kind: 'agent' })).toBe('agent');
  });
  it('falls back to the filename convention', () => {
    expect(classifyMarkdown('skills/java/SKILL.md', {})).toBe('skill');
    expect(classifyMarkdown('AGENTS.md', {})).toBe('instruction');
    expect(classifyMarkdown('CONVENTIONS.md', {})).toBe('instruction');
    expect(classifyMarkdown('adapter.md', {})).toBe('agent');
  });
  it('treats a launch command as proof of an agent card', () => {
    expect(classifyMarkdown('anything.md', { command: 'claude' })).toBe('agent');
  });
  it('defaults to an instruction file, the least privileged reading', () => {
    expect(classifyMarkdown('notes.md', {})).toBe('instruction');
  });
});

describe('slugify', () => {
  it('produces a stable lower-case id', () => {
    expect(slugify('Atlas the Architect', 'x')).toBe('atlas-the-architect');
  });
  it('falls back when nothing usable survives', () => {
    expect(slugify('!!!', 'fallback')).toBe('fallback');
  });
});

// --- Markdown import ----------------------------------------------------

describe('importing a single Markdown file', () => {
  it('reads an agent card into a launch profile', () => {
    const result = parsePackage({
      fileName: 'atlas.md',
      content: [
        '---',
        'kind: agent',
        'name: Atlas',
        'role: Architect',
        'vendor: acme',
        'command: claude',
        'args: ["--acp"]',
        'permissions: [read, edit]',
        '---',
        '# Atlas',
        '',
        'Designs the shape before anything is built.',
      ].join('\n'),
    });
    expect(result.format).toBe('markdown');
    expect(result.agents).toHaveLength(1);
    const agent = result.agents[0];
    expect(agent.name).toBe('Atlas');
    expect(agent.command).toBe('claude');
    expect(agent.args).toEqual(['--acp']);
    expect(agent.permissions).toEqual(['read', 'edit']);
  });

  it('reads a SKILL.md into a skill pack', () => {
    const result = parsePackage({
      fileName: 'SKILL.md',
      content:
        '---\nname: Java Spring\nversion: 2.0.0\ntags: [java, spring]\n---\n# Overview\n\nGradle, not Maven.\n',
    });
    expect(result.skills).toHaveLength(1);
    expect(result.skills[0].name).toBe('Java Spring');
    expect(result.skills[0].tags).toEqual(['java', 'spring']);
    expect(result.skills[0].body).toContain('Gradle, not Maven.');
  });

  it('reads an AGENTS.md into a workspace-scoped instruction file', () => {
    const result = parsePackage({
      fileName: 'AGENTS.md',
      content: '# How we work here\n\nSmall commits.\n',
    });
    expect(result.instructions).toHaveLength(1);
    expect(result.instructions[0].scope).toBe('workspace');
    expect(result.instructions[0].body).toContain('Small commits.');
  });

  it('refuses an empty file with a sentence the user can act on', () => {
    expect(() => parsePackage({ fileName: 'empty.md', content: '   ' })).toThrow(
      /empty/i,
    );
  });
});

// --- ZIP ----------------------------------------------------------------

describe('reading a ZIP archive', () => {
  it('reads an adapter folder into an agent with its skills and instructions bound', () => {
    const archive = zip([
      {
        name: 'atlas/adapter.yaml',
        body: 'id: atlas\nname: Atlas\nrole: Architect\ncommand: claude\nargs: ["--acp"]\n',
      },
      {
        name: 'atlas/skills/java/SKILL.md',
        body: '---\nname: Java\nversion: 1.0.0\n---\n# Java\n\nGradle.\n',
      },
      {
        name: 'atlas/instructions/house.md',
        body: '---\nname: House rules\nscope: organisation\n---\n# House rules\n',
      },
    ]);
    const result = parsePackage({
      fileName: 'atlas.zip',
      contentBase64: base64(archive),
    });
    expect(result.format).toBe('zip');
    expect(result.agents).toHaveLength(1);
    expect(result.skills).toHaveLength(1);
    expect(result.instructions).toHaveLength(1);
    // The adapter folder names its parts by living beside them.
    expect(result.agents[0].skillIds).toEqual([result.skills[0].id]);
    expect(result.agents[0].instructionIds).toEqual([result.instructions[0].id]);
    expect(result.instructions[0].scope).toBe('organisation');
  });

  it('reads stored members as well as deflated ones', () => {
    const archive = zip([
      { name: 'skills/go/SKILL.md', body: '# Go\n\nModules.\n', store: true },
    ]);
    const { entries, skipped } = readZip(archive);
    expect(skipped).toEqual([]);
    expect(entries[0].text).toContain('Modules.');
  });

  it('reports a traversal-unsafe member as skipped instead of surfacing it', () => {
    const archive = zip([
      { name: '../../escape/SKILL.md', body: '# Escape\n' },
      { name: 'skills/ok/SKILL.md', body: '# Fine\n' },
    ]);
    const { entries, skipped } = readZip(archive);
    expect(entries.map((entry) => entry.path)).toEqual(['skills/ok/SKILL.md']);
    expect(skipped).toEqual([{ path: '../../escape/SKILL.md', reason: 'unsafe path' }]);
  });

  it('rejects a file that is not a ZIP at all, naming what was wrong', () => {
    expect(() =>
      parsePackage({
        fileName: 'not-a.zip',
        contentBase64: base64(Buffer.from('this is plain text')),
      }),
    ).toThrow(/not a readable ZIP/i);
  });

  it('refuses an archive that carried nothing importable, and says what it expected', () => {
    const archive = zip([{ name: 'readme.txt', body: 'hello' }]);
    expect(() =>
      parsePackage({ fileName: 'x.zip', contentBase64: base64(archive) }),
    ).toThrow(/adapter\.yaml/);
  });

  it('skips a non-Markdown member rather than guessing at it', () => {
    const { skipped } = assembleFromArchive([
      { path: 'skills/java/SKILL.md', text: '# Java\n' },
      { path: 'assets/logo.svg', text: '<svg/>' },
    ]);
    expect(skipped).toEqual([
      { path: 'assets/logo.svg', reason: 'not a Markdown or manifest file' },
    ]);
  });

  it('lets directory position decide the kind inside an archive', () => {
    // `notes.md` would classify as an instruction on its own; under
    // `skills/` the adapter-folder convention outranks the filename.
    const assembled = assembleFromArchive([
      { path: 'skills/notes.md', text: '# Notes\n' },
      { path: 'instructions/notes.md', text: '# Notes\n' },
    ]);
    expect(assembled.skills).toHaveLength(1);
    expect(assembled.instructions).toHaveLength(1);
  });
});

// --- portable JSON ------------------------------------------------------

describe('importing the portable JSON document', () => {
  it('round-trips an exported agent with its skills and instructions', () => {
    const result = parsePackage({
      fileName: 'atlas.json',
      content: JSON.stringify({
        kind: 'meridian-portable-agent',
        schemaVersion: 1,
        agent: {
          id: 'atlas',
          name: 'Atlas',
          role: 'Architect',
          description: '',
          vendor: 'acme',
          version: '1.0.0',
          command: 'claude',
          args: [],
          instructions: '',
          permissions: ['read'],
          trainable: ['memory'],
          phases: ['design'],
          skillIds: ['java'],
          instructionIds: [],
        },
        skills: [
          {
            id: 'java',
            name: 'Java',
            summary: '',
            version: '1.0.0',
            tags: [],
            body: '# Java',
          },
        ],
      }),
    });
    expect(result.format).toBe('json');
    expect(result.agents[0].phases).toEqual(['design']);
    expect(result.skills[0].id).toBe('java');
  });
});
