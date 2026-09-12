/**
 * Agent, skill and instruction package ingestion.
 *
 * A user supplies an agent as a Markdown document or a ZIP archive and the
 * workbench works out the rest. Three shapes are recognised:
 *
 *  - **Markdown** — a `SKILL.md`, `AGENTS.md`, `CONVENTIONS.md` or an agent
 *    card, with optional YAML frontmatter. The frontmatter names what it is;
 *    where it does not, the filename and the heading decide.
 *  - **ZIP** — the adapter folder of `vision.md` §2.8: `adapter.yaml`,
 *    `skills/**​/SKILL.md`, `instructions/*.md`. Every recognised member is
 *    imported and everything else is reported as skipped, never silently
 *    dropped.
 *  - **JSON** — a `meridian-portable-agent` document exported by this tool.
 *
 * The ZIP reader is deliberately dependency-free: it parses the central
 * directory and inflates with Node's own `zlib`. Adding a third-party archive
 * library to the production bundle is an owner decision, and a bounded reader
 * that only understands stored and deflated members is easier to reason about
 * than a general one.
 *
 * Nothing here executes anything it reads. A package contributes declarative
 * configuration — launch command, instructions, skills — and the existing
 * validation in `service.ts` still applies to every agent produced.
 */
import { inflateRawSync } from 'node:zlib';
import { parse as parseYaml } from 'yaml';
import type {
  AgentPermission,
  LearningSurface,
  SdlcPhase,
  WorkbenchAgentInput,
  WorkbenchInstructionInput,
  WorkbenchSkillInput,
} from '../../../shared/ts/workbench';
import { SDLC_PHASES } from '../../../shared/ts/workbench';

/** A member of an opened archive. Directories are dropped by the reader. */
export interface ArchiveEntry {
  path: string;
  text: string;
}

export interface ParsedPackage {
  agents: WorkbenchAgentInput[];
  skills: WorkbenchSkillInput[];
  instructions: WorkbenchInstructionInput[];
  skipped: { path: string; reason: string }[];
  format: 'markdown' | 'zip' | 'json';
}

/** Archive members above this size are skipped rather than inflated. */
const MAX_MEMBER_BYTES = 4_000_000;
/** Total inflated bytes accepted from one archive. */
const MAX_ARCHIVE_BYTES = 40_000_000;
/** Members considered before the reader stops, so a zip bomb cannot spin. */
const MAX_MEMBERS = 2_000;

const PERMISSIONS: readonly AgentPermission[] = [
  'read',
  'edit',
  'delete',
  'move',
  'execute',
  'search',
  'think',
  'unknown',
  'other',
];
/**
 * What an imported agent may do when its package says nothing. Deliberately
 * the three that cannot alter the workspace: an import is not consent to
 * write files or run commands.
 */
export const DEFAULT_IMPORT_PERMISSIONS: readonly AgentPermission[] = [
  'read',
  'search',
  'think',
];

const SURFACES: readonly LearningSurface[] = [
  'policy',
  'rules',
  'memory',
  'skills',
  'calibration',
];

// ---------------------------------------------------------------------------
// slug + small coercions
// ---------------------------------------------------------------------------

/** Stable identifier from a human name; the service validates the result. */
export function slugify(value: string, fallback: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return /^[a-z0-9]/.test(slug) ? slug : fallback;
}

function asStringArray(value: unknown, allowed?: readonly string[]): string[] {
  const raw = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(/[,\s]+/)
      : [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (typeof item !== 'string') continue;
    const trimmed = item.trim().toLowerCase();
    if (!trimmed) continue;
    if (allowed && !allowed.includes(trimmed)) continue;
    seen.add(trimmed);
  }
  return [...seen];
}

function asText(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value.trim() : fallback;
}

// ---------------------------------------------------------------------------
// Markdown with optional YAML frontmatter
// ---------------------------------------------------------------------------

export interface Frontmatter {
  data: Record<string, unknown>;
  body: string;
  /**
   * Why the frontmatter did not parse, when it did not. Present means every
   * declared field was lost and the record fell back to filename and
   * heading — which looks like a successful import unless somebody says so.
   */
  error?: string;
}

/**
 * Split `---\n…\n---\n` frontmatter from the body. Malformed YAML is not an
 * error: the document is still importable as a body, because refusing a
 * user's instruction file over a stray colon is worse than importing it
 * without its metadata.
 *
 * It is, however, *reported* — see `error`. Silently importing a package
 * stripped of its id, name, tags and phase tags is a worse outcome than
 * either refusing it or importing it, because the user cannot tell which
 * happened.
 */
export function parseFrontmatter(text: string): Frontmatter {
  const normalised = text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
  const match = /^---\n([\s\S]*?)\n---\n?/.exec(normalised);
  if (!match) return { data: {}, body: normalised.trim() };
  let data: Record<string, unknown> = {};
  let error: string | undefined;
  try {
    const parsed: unknown = parseYaml(match[1]);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      data = parsed as Record<string, unknown>;
    }
  } catch (caught) {
    // Keep the body and fall back to filename and heading — a document with
    // broken frontmatter is still a document, and refusing the whole import
    // over it would be worse.
    //
    // But report it. This used to be a bare `catch {}`, and the failure it
    // hides is quiet and plausible: `description: Node services: strictness`
    // is invalid YAML (a plain scalar cannot contain ": "), so the *entire*
    // block is discarded and the record silently arrives with a
    // filename-derived id, no declared name, no tags and no phases. Nothing
    // said so. It happened to a skill pack shipped in this repository, and a
    // test noticing the missing tags is what found it.
    error = caught instanceof Error ? caught.message : String(caught);
  }
  return { data, body: normalised.slice(match[0].length).trim(), error };
}

/** The first ATX heading, used as a name when frontmatter gives none. */
function firstHeading(body: string): string | undefined {
  const match = /^#\s+(.+)$/m.exec(body);
  return match ? match[1].trim() : undefined;
}

type MarkdownKind = 'agent' | 'skill' | 'instruction';

/**
 * Decide what a Markdown document is. Frontmatter wins; then the filename
 * convention (`SKILL.md`, `AGENTS.md`, `CONVENTIONS.md`, `adapter.*`); then
 * the presence of a launch command, which only an agent card carries.
 */
export function classifyMarkdown(
  fileName: string,
  data: Record<string, unknown>,
): MarkdownKind {
  const declared = asText(data.kind ?? data.type).toLowerCase();
  if (declared.includes('agent') || declared.includes('adapter')) return 'agent';
  if (declared.includes('skill')) return 'skill';
  if (declared.includes('instruction') || declared.includes('convention'))
    return 'instruction';

  const base = fileName.split(/[\\/]/).pop()?.toLowerCase() ?? '';
  if (base.startsWith('skill')) return 'skill';
  if (base.startsWith('agents.') || base.startsWith('conventions'))
    return 'instruction';
  if (base.startsWith('adapter') || base.startsWith('agent.')) return 'agent';

  if (data.command !== undefined || data.executable !== undefined) return 'agent';
  return 'instruction';
}

export function agentFromMarkdown(
  fileName: string,
  { data, body }: Frontmatter,
): WorkbenchAgentInput {
  const name =
    asText(data.name) || firstHeading(body) || baseName(fileName) || 'Imported agent';
  const rawCommand = asText(data.command ?? data.executable);
  const args = asStringArray(data.args ?? data.arguments).length
    ? (Array.isArray(data.args ?? data.arguments)
        ? ((data.args ?? data.arguments) as unknown[])
        : asText(data.args ?? data.arguments).split(/\s+/)
      )
        .map((item) => String(item).trim())
        .filter(Boolean)
    : [];
  return {
    id: slugify(asText(data.id) || name, `agent-${Date.now().toString(36)}`),
    name: name.slice(0, 120),
    role: (asText(data.role) || 'Imported').slice(0, 120),
    description: (asText(data.description ?? data.summary) || body.slice(0, 500)).slice(
      0,
      2_000,
    ),
    vendor: asText(data.vendor ?? data.publisher).slice(0, 120),
    version: (asText(data.version) || '0.1.0').slice(0, 40),
    // A package that declares no executable is imported as a draft. The user
    // supplies the command in the Agent tab before it can run; the service
    // refuses to launch an agent without one.
    command: rawCommand.slice(0, 2_000),
    args,
    instructions: body.slice(0, 40_000),
    // A package that names no permissions gets the least-privileged set that
    // still lets an agent do something observable. Read, search and think can
    // change nothing; edit, execute and delete are never granted by an import,
    // only by a person widening them in the Agents tab afterwards.
    permissions: (asStringArray(data.permissions ?? data.tools, PERMISSIONS).length
      ? asStringArray(data.permissions ?? data.tools, PERMISSIONS)
      : DEFAULT_IMPORT_PERMISSIONS) as AgentPermission[],
    trainable: asStringArray(
      data.trainable ?? data.learning,
      SURFACES,
    ) as LearningSurface[],
    phases: asStringArray(data.phases ?? data.sdlc, SDLC_PHASES) as SdlcPhase[],
    // A package may declare which skills it expects to be bound to. This is
    // what makes a *stack* agent expressible as data — "Developer bound to
    // java-spring-gradle" is a Java engineer, and that binding is the whole
    // L3 mechanic. Unlike integrations below, a skill id is a reference into
    // this workspace's own catalogue, not a credential the package brings: an
    // id naming a skill that is not here binds to nothing, and the caller
    // filters to what exists.
    skillIds: asStringArray(data.skills ?? data.skillIds).slice(0, 50),
    instructionIds: [],
    // A package cannot bring its own tool connections: those are the user's
    // credentials and endpoints, bound deliberately after the import.
    integrationIds: [],
  };
}

export function skillFromMarkdown(
  fileName: string,
  { data, body }: Frontmatter,
): WorkbenchSkillInput {
  const name =
    asText(data.name) || firstHeading(body) || baseName(fileName) || 'Imported skill';
  return {
    id: slugify(asText(data.id) || name, `skill-${Date.now().toString(36)}`),
    name: name.slice(0, 120),
    summary: (asText(data.description ?? data.summary) || firstParagraph(body)).slice(
      0,
      500,
    ),
    version: (asText(data.version) || '0.1.0').slice(0, 40),
    tags: asStringArray(data.tags ?? data.stacks).slice(0, 20),
    body: body.slice(0, 200_000),
  };
}

export function instructionFromMarkdown(
  fileName: string,
  { data, body }: Frontmatter,
): WorkbenchInstructionInput {
  const name =
    asText(data.name) ||
    firstHeading(body) ||
    baseName(fileName) ||
    'Imported instructions';
  const declaredScope = asText(data.scope).toLowerCase();
  const scope: WorkbenchInstructionInput['scope'] =
    declaredScope === 'adapter' ||
    declaredScope === 'workspace' ||
    declaredScope === 'user' ||
    declaredScope === 'organisation'
      ? declaredScope
      : 'workspace';
  return {
    id: slugify(
      asText(data.id) || name,
      `instruction-${Date.now().toString(36)}`,
    ),
    name: name.slice(0, 120),
    summary: (asText(data.description ?? data.summary) || firstParagraph(body)).slice(
      0,
      500,
    ),
    scope,
    body: body.slice(0, 200_000),
  };
}

function baseName(fileName: string): string {
  const base = fileName.split(/[\\/]/).pop() ?? '';
  return base.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim();
}

function firstParagraph(body: string): string {
  for (const block of body.split(/\n\s*\n/)) {
    const text = block.replace(/^#+\s*/, '').trim();
    if (text) return text;
  }
  return '';
}

// ---------------------------------------------------------------------------
// ZIP
// ---------------------------------------------------------------------------

const SIG_EOCD = 0x06054b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_LOCAL = 0x04034b50;

/**
 * Read a ZIP archive's members via its central directory. Only stored (0) and
 * deflated (8) members are understood; anything else is reported as skipped.
 *
 * Traversal-unsafe names (`..`, absolute paths, drive letters) are rejected —
 * nothing here writes to disk, but a member that pretends to be `../../x` must
 * never be presented to the user as though it were part of the package.
 */
export function readZip(buffer: Buffer): {
  entries: ArchiveEntry[];
  skipped: { path: string; reason: string }[];
} {
  const entries: ArchiveEntry[] = [];
  const skipped: { path: string; reason: string }[] = [];

  const eocd = findEndOfCentralDirectory(buffer);
  if (eocd < 0) {
    throw new Error(
      'That file is not a readable ZIP archive: no end-of-central-directory record was found.',
    );
  }
  const total = buffer.readUInt16LE(eocd + 10);
  let offset = buffer.readUInt32LE(eocd + 16);
  let inflated = 0;

  for (let index = 0; index < Math.min(total, MAX_MEMBERS); index += 1) {
    if (offset + 46 > buffer.length) break;
    if (buffer.readUInt32LE(offset) !== SIG_CENTRAL) break;

    const method = buffer.readUInt16LE(offset + 10);
    const compressedSize = buffer.readUInt32LE(offset + 20);
    const uncompressedSize = buffer.readUInt32LE(offset + 24);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    const localOffset = buffer.readUInt32LE(offset + 42);
    const name = buffer
      .subarray(offset + 46, offset + 46 + nameLength)
      .toString('utf8');
    offset += 46 + nameLength + extraLength + commentLength;

    if (name.endsWith('/')) continue; // directory
    if (!isSafeMemberPath(name)) {
      skipped.push({ path: name, reason: 'unsafe path' });
      continue;
    }
    if (method !== 0 && method !== 8) {
      skipped.push({ path: name, reason: `unsupported compression method ${method}` });
      continue;
    }
    if (uncompressedSize > MAX_MEMBER_BYTES) {
      skipped.push({ path: name, reason: 'larger than the 4 MB member limit' });
      continue;
    }
    if (inflated + uncompressedSize > MAX_ARCHIVE_BYTES) {
      skipped.push({ path: name, reason: 'archive exceeds the 40 MB total limit' });
      continue;
    }

    try {
      const data = readLocalMember(buffer, localOffset, method, compressedSize);
      inflated += data.length;
      entries.push({ path: name, text: data.toString('utf8') });
    } catch (error) {
      skipped.push({
        path: name,
        reason: error instanceof Error ? error.message : 'could not be read',
      });
    }
  }
  return { entries, skipped };
}

function isSafeMemberPath(name: string): boolean {
  if (!name || name.length > 400) return false;
  if (name.startsWith('/') || name.startsWith('\\')) return false;
  if (/^[a-zA-Z]:/.test(name)) return false;
  return !name.split(/[\\/]/).includes('..');
}

function readLocalMember(
  buffer: Buffer,
  localOffset: number,
  method: number,
  compressedSize: number,
): Buffer {
  if (localOffset + 30 > buffer.length) throw new Error('truncated local header');
  if (buffer.readUInt32LE(localOffset) !== SIG_LOCAL)
    throw new Error('bad local header signature');
  const nameLength = buffer.readUInt16LE(localOffset + 26);
  const extraLength = buffer.readUInt16LE(localOffset + 28);
  const start = localOffset + 30 + nameLength + extraLength;
  const end = start + compressedSize;
  if (end > buffer.length) throw new Error('truncated member data');
  const raw = buffer.subarray(start, end);
  return method === 0 ? Buffer.from(raw) : inflateRawSync(raw);
}

function findEndOfCentralDirectory(buffer: Buffer): number {
  const earliest = Math.max(0, buffer.length - 0xffff - 22);
  for (let index = buffer.length - 22; index >= earliest; index -= 1) {
    if (buffer.readUInt32LE(index) === SIG_EOCD) return index;
  }
  return -1;
}

// ---------------------------------------------------------------------------
// package assembly
// ---------------------------------------------------------------------------

/** `adapter.yaml` / `adapter.yml` / `agent.yaml` at any depth. */
function isAdapterManifest(path: string): boolean {
  const base = path.split('/').pop()?.toLowerCase() ?? '';
  return /^(adapter|agent)\.(ya?ml|json)$/.test(base);
}

function isMarkdown(path: string): boolean {
  return /\.(md|markdown)$/i.test(path);
}

/**
 * Turn an opened archive into agents, skills and instructions.
 *
 * Directory position decides the kind where it is unambiguous — `skills/` and
 * `instructions/` are the adapter-folder convention — and the Markdown
 * classifier decides the rest.
 */
export function assembleFromArchive(entries: ArchiveEntry[]): {
  agents: WorkbenchAgentInput[];
  skills: WorkbenchSkillInput[];
  instructions: WorkbenchInstructionInput[];
  skipped: { path: string; reason: string }[];
} {
  const agents: WorkbenchAgentInput[] = [];
  const skills: WorkbenchSkillInput[] = [];
  const instructions: WorkbenchInstructionInput[] = [];
  const skipped: { path: string; reason: string }[] = [];

  for (const entry of entries) {
    const lower = entry.path.toLowerCase();
    try {
      if (isAdapterManifest(entry.path)) {
        const data = lower.endsWith('.json')
          ? (JSON.parse(entry.text) as Record<string, unknown>)
          : ((parseYaml(entry.text) ?? {}) as Record<string, unknown>);
        agents.push(agentFromMarkdown(entry.path, { data, body: '' }));
        continue;
      }
      if (!isMarkdown(entry.path)) {
        skipped.push({ path: entry.path, reason: 'not a Markdown or manifest file' });
        continue;
      }
      const parsed = parseFrontmatter(entry.text);
      if (parsed.error)
        // Imported, not skipped — the body is still useful — but the user is
        // told, because every declared field was dropped and the result
        // otherwise looks like a clean import of a differently-named thing.
        skipped.push({
          path: entry.path,
          reason: `imported without its frontmatter (${parsed.error.split('\n')[0]}); id, name and tags fell back to the filename`,
        });
      const inSkills = /(^|\/)skills\//.test(lower);
      const inInstructions = /(^|\/)instructions\//.test(lower);
      const kind = inSkills
        ? 'skill'
        : inInstructions
          ? 'instruction'
          : classifyMarkdown(entry.path, parsed.data);
      if (kind === 'agent') agents.push(agentFromMarkdown(entry.path, parsed));
      else if (kind === 'skill') skills.push(skillFromMarkdown(entry.path, parsed));
      else instructions.push(instructionFromMarkdown(entry.path, parsed));
    } catch (error) {
      skipped.push({
        path: entry.path,
        reason: error instanceof Error ? error.message : 'could not be parsed',
      });
    }
  }

  // An adapter folder names its skills and instructions by living beside
  // them: bind everything the archive carried to the agents it carried.
  if (agents.length) {
    const skillIds = skills.map((skill) => skill.id);
    const instructionIds = instructions.map((instruction) => instruction.id);
    for (const agent of agents) {
      agent.skillIds = [...skillIds];
      agent.instructionIds = [...instructionIds];
    }
  }
  return { agents, skills, instructions, skipped };
}

/**
 * The single entry point the service calls. `content` is text (Markdown or
 * JSON); `contentBase64` is archive bytes. Exactly one must be supplied.
 */
export function parsePackage(input: {
  fileName: string;
  content?: string;
  contentBase64?: string;
}): ParsedPackage {
  const name = input.fileName || 'package';
  const empty = { agents: [], skills: [], instructions: [], skipped: [] };

  if (input.contentBase64 !== undefined) {
    const buffer = Buffer.from(input.contentBase64, 'base64');
    if (!buffer.length) throw new Error('That archive is empty.');
    const { entries, skipped } = readZip(buffer);
    const assembled = assembleFromArchive(entries);
    const result: ParsedPackage = {
      ...empty,
      ...assembled,
      skipped: [...skipped, ...assembled.skipped],
      format: 'zip',
    };
    if (!result.agents.length && !result.skills.length && !result.instructions.length) {
      throw new Error(
        'That archive contained no agent manifest, skill or instruction file. ' +
          'Expected adapter.yaml, skills/**/SKILL.md or instructions/*.md.',
      );
    }
    return result;
  }

  const text = input.content ?? '';
  if (!text.trim()) throw new Error('That file is empty.');

  const trimmed = text.trimStart();
  if (trimmed.startsWith('{')) {
    const parsed: unknown = JSON.parse(text);
    return { ...empty, ...fromPortableJson(parsed), format: 'json' };
  }

  const parsed = parseFrontmatter(text);
  const kind = classifyMarkdown(name, parsed.data);
  if (kind === 'agent')
    return { ...empty, agents: [agentFromMarkdown(name, parsed)], format: 'markdown' };
  if (kind === 'skill')
    return { ...empty, skills: [skillFromMarkdown(name, parsed)], format: 'markdown' };
  return {
    ...empty,
    instructions: [instructionFromMarkdown(name, parsed)],
    format: 'markdown',
  };
}

function fromPortableJson(parsed: unknown): {
  agents: WorkbenchAgentInput[];
  skills: WorkbenchSkillInput[];
  instructions: WorkbenchInstructionInput[];
  skipped: { path: string; reason: string }[];
} {
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('That JSON file is not a portable agent document.');
  }
  const document = parsed as Record<string, unknown>;
  if (document.kind !== 'meridian-portable-agent') {
    throw new Error(
      'That JSON file is not a portable agent document (expected kind "meridian-portable-agent").',
    );
  }
  const agent = document.agent as WorkbenchAgentInput | undefined;
  if (!agent) throw new Error('That portable agent document carries no agent.');
  const skills = Array.isArray(document.skills)
    ? (document.skills as WorkbenchSkillInput[])
    : [];
  const instructions = Array.isArray(document.instructions)
    ? (document.instructions as WorkbenchInstructionInput[])
    : [];
  return {
    agents: [
      {
        ...agent,
        phases: Array.isArray(agent.phases) ? agent.phases : [],
        skillIds: skills.map((skill) => skill.id),
        instructionIds: instructions.map((instruction) => instruction.id),
      },
    ],
    skills,
    instructions,
    skipped: [],
  };
}
