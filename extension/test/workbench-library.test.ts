import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { WorkbenchService } from '../src/workbench/service';
import {
  emptyLibrary,
  loadBuiltinLibrary,
  planSeed,
} from '../src/workbench/library';
import type { WorkbenchSnapshot } from '../../shared/ts/workbench';

/**
 * The library that ships in the box.
 *
 * Meridian shipped with empty catalogues: no agents, no skills, no
 * instruction documents, and no route to a populated workspace except
 * importing a package the user did not have. These pin both halves of the
 * fix — that something ships, and that shipping it never overwrites, resurrects
 * or outranks what the user did themselves.
 */

const services: WorkbenchService[] = [];
const temporary: string[] = [];
afterEach(async () => {
  services.splice(0).forEach((service) => service.dispose());
  for (const dir of temporary.splice(0)) {
    await rm(dir, { recursive: true, force: true }).catch(() => undefined);
  }
});

async function scratch(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(os.tmpdir(), prefix));
  temporary.push(dir);
  return dir;
}

/** An extension directory containing a library of the given files. */
async function extensionWith(files: Record<string, string>): Promise<string> {
  const root = await scratch('meridian-ext-');
  for (const [relative, text] of Object.entries(files)) {
    const target = path.join(root, 'library', relative);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, text, 'utf8');
  }
  return root;
}

const SKILL_MD = [
  '---',
  'kind: skill',
  'id: shipped-skill',
  'name: Shipped Skill',
  'description: Ships in the box.',
  'tags: [testing]',
  '---',
  '',
  '# Shipped Skill',
  '',
  'Conventions that arrived with the extension.',
].join('\n');

const AGENT_MD = [
  '---',
  'kind: agent',
  'id: shipped-agent',
  'name: Shipped Agent',
  'role: Reviewer',
  'description: Ships in the box.',
  'phases: [review]',
  'permissions: [read, search, think]',
  '---',
  '',
  '# Shipped Agent',
  '',
  'Reads diffs.',
].join('\n');

const INSTRUCTION_MD = [
  '---',
  'kind: instruction',
  'id: shipped-instruction',
  'name: Shipped Instruction',
  'description: House rules.',
  'scope: organisation',
  '---',
  '',
  '# Shipped Instruction',
  '',
  'How the house works.',
].join('\n');

async function serviceOn(root: string, extensionPath: string) {
  const service = new WorkbenchService({
    extensionPath,
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ['flight-recorder'],
    sidecar: () => undefined,
  });
  services.push(service);
  return {
    service,
    snapshot: async () =>
      (await service.request({ action: 'snapshot' })) as WorkbenchSnapshot,
  };
}

describe('reading the shipped library', () => {
  it('parses agents, skills and instructions with the import parsers', async () => {
    // The same parsers, deliberately: a built-in is an ordinary record that
    // happened to arrive in the box, not a second kind of thing.
    const extensionPath = await extensionWith({
      'agents/a.md': AGENT_MD,
      'skills/s.md': SKILL_MD,
      'instructions/i.md': INSTRUCTION_MD,
    });
    const library = await loadBuiltinLibrary(extensionPath);
    expect(library.agents.map((a) => a.id)).toEqual(['shipped-agent']);
    expect(library.skills.map((s) => s.id)).toEqual(['shipped-skill']);
    expect(library.instructions.map((i) => i.id)).toEqual([
      'shipped-instruction',
    ]);
    expect(library.agents[0].phases).toEqual(['review']);
    expect(library.instructions[0].scope).toBe('organisation');
  });

  it('returns an empty library rather than throwing when nothing ships', async () => {
    // An unreadable library must never be the reason a workspace will not
    // open. Empty catalogues are exactly the behaviour this replaced.
    const bare = await scratch('meridian-bare-');
    await expect(loadBuiltinLibrary(bare)).resolves.toEqual(emptyLibrary());
    await expect(
      loadBuiltinLibrary(path.join(bare, 'does-not-exist')),
    ).resolves.toEqual(emptyLibrary());
  });

  it('skips a file it cannot parse without losing the rest', async () => {
    const extensionPath = await extensionWith({
      'skills/good.md': SKILL_MD,
      'skills/ignored.txt': 'not markdown, not collected',
    });
    const library = await loadBuiltinLibrary(extensionPath);
    expect(library.skills.map((s) => s.id)).toEqual(['shipped-skill']);
  });

  it('ships the twelve Role Agents vision.md 2.3 names', async () => {
    // Not a fixture — the actual shipped files, checked against the roster
    // the product defines. An earlier pass shipped an invented set of nine
    // roles instead, which is the quiet kind of scope substitution that looks
    // finished and answers a different question.
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    const ids = library.agents.map((agent) => agent.id);
    for (const role of [
      'analyst-agent',
      'architect-agent',
      'developer-agent',
      'frontend-agent',
      'qa-engineer-agent',
      'qa-lead-agent',
      'release-agent',
      'reviewer-agent',
      'scrummaster-agent',
      'security-agent',
      'sre-agent',
      'techlead-agent',
    ]) {
      expect(ids).toContain(role);
    }
    // Every SDLC phase has somebody to convene, or a dispatch falls through
    // to the unphased fallback and the phase tagging means nothing.
    const phases = new Set(library.agents.flatMap((agent) => agent.phases));
    for (const phase of [
      'intake',
      'design',
      'plan',
      'build',
      'verify',
      'security',
      'review',
      'release',
      'operate',
    ]) {
      expect(phases.has(phase as never)).toBe(true);
    }
    // Nothing shipped may arrive able to change anything, and nothing shipped
    // may arrive able to run: the command is bound by a person.
    for (const agent of library.agents) {
      expect([...agent.permissions].sort()).toEqual([
        'read',
        'search',
        'think',
      ]);
      expect(agent.command).toBe('');
    }
  });

  it('ships the GA skill catalogue vision.md 2.4 names', async () => {
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    expect(library.skills.map((skill) => skill.id).sort()).toEqual(
      [
        'api-contract-first',
        'aws-iac',
        'dotnet-service',
        'golang-service',
        'java-fullstack',
        'java-spring-gradle',
        'node-service',
        'python-service',
        'react-frontend',
        'sql-migration',
      ].sort(),
    );
    // 2.4 says what a pack carries. A pack missing its build invocation is a
    // description of a stack rather than something an agent can work from.
    for (const skill of library.skills) {
      expect(skill.body).toContain('## Project layout');
      expect(skill.body).toContain('## Build and test');
      expect(skill.body).toContain('## Review checklist');
      expect(skill.tags.length).toBeGreaterThan(0);
    }
  });

  it('ships stack agents that are a role plus exactly one pack', async () => {
    // vision.md 2.4: a Stack Agent is not a separate hard-coded agent, it is
    // a Role Agent bound to a Skill Pack. These ship the composition made up,
    // because "a Spring Boot agent" is what people look for — but each must
    // still *be* that composition, or the claim is decoration.
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    const packs = new Set(library.skills.map((skill) => skill.id));
    const stack = library.agents.filter((agent) => agent.skillIds.length);
    expect(stack.length).toBeGreaterThanOrEqual(10);
    for (const agent of stack) {
      expect(agent.skillIds).toHaveLength(1);
      // A binding that names a pack this library does not ship would show a
      // specialisation that resolves to nothing in the briefing.
      expect(packs.has(agent.skillIds[0])).toBe(true);
    }
    // Every shipped pack is reachable through at least one ready-made agent.
    const bound = new Set(stack.flatMap((agent) => agent.skillIds));
    for (const pack of packs) expect(bound.has(pack)).toBe(true);
  });

  it('parses every shipped file with its declared frontmatter intact', async () => {
    // The trap this guards: a plain YAML scalar cannot contain ": ", so
    // `description: Node services: strictness` throws, parseFrontmatter
    // discards the WHOLE block, and the record arrives with a
    // filename-derived id and no tags — looking, from the outside, like a
    // perfectly good import. One shipped pack was in exactly that state.
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    for (const skill of library.skills) {
      expect(skill.tags.length).toBeGreaterThan(0);
      expect(skill.version).not.toBe('0.1.0'); // the no-frontmatter default
    }
    for (const agent of library.agents) {
      expect(agent.vendor).toBe('Meridian Loom');
      expect(agent.phases.length).toBeGreaterThan(0);
    }
  });

  it('ships runtime presets so binding an agent is a choice, not a guess', async () => {
    // Meridian does not bundle an AI; it governs one you already have. Until
    // these existed, supplying one meant knowing an executable's name and
    // typing it into a text box.
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    expect(library.runtimes.length).toBeGreaterThan(0);
    for (const runtime of library.runtimes) {
      expect(runtime.command).toBeTruthy();
      expect(runtime.requires).toBeTruthy();
      // Every preset must say how the user authenticates, because Meridian
      // never does it for them and never holds the credential.
      expect(runtime.auth).toBeTruthy();
      const serialised = JSON.stringify(runtime).toLowerCase();
      for (const leak of ['api_key=', 'apikey=', 'token=', 'password='])
        expect(serialised).not.toContain(leak);
    }
  });

  it('ships instruction documents at a declared precedence scope', async () => {
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    expect(library.instructions.length).toBeGreaterThan(0);
    for (const entry of library.instructions) {
      expect(['adapter', 'workspace', 'user', 'organisation']).toContain(
        entry.scope,
      );
    }
  });
});

describe('deciding what to seed', () => {
  const library = {
    agents: [{ id: 'a' }],
    skills: [{ id: 's' }],
    instructions: [{ id: 'i' }],
  } as never as Parameters<typeof planSeed>[0];
  const nothingPresent = { agents: [], skills: [], instructions: [] };

  it('seeds everything into a workspace that has seen nothing', () => {
    const plan = planSeed(library, nothingPresent, []);
    expect(plan.agents).toHaveLength(1);
    expect(plan.skills).toHaveLength(1);
    expect(plan.instructions).toHaveLength(1);
    expect(plan.seeded).toEqual(['agent:a', 'instruction:i', 'skill:s']);
  });

  it('never seeds the same entry twice, so a deletion stays deleted', () => {
    // The important one. "Not present" cannot distinguish never-seeded from
    // seeded-then-deleted, so without the record the delete button would be a
    // suggestion that the next window reload overrules.
    const plan = planSeed(library, nothingPresent, [
      'agent:a',
      'skill:s',
      'instruction:i',
    ]);
    expect(plan.agents).toHaveLength(0);
    expect(plan.skills).toHaveLength(0);
    expect(plan.instructions).toHaveLength(0);
  });

  it('does not land on top of an id the user already has', () => {
    const plan = planSeed(
      library,
      { agents: ['a'], skills: ['s'], instructions: [] },
      [],
    );
    expect(plan.agents).toHaveLength(0);
    expect(plan.skills).toHaveLength(0);
    expect(plan.instructions).toHaveLength(1);
    // Still recorded as offered, so the skipped ones cannot arrive later by
    // another route.
    expect(plan.seeded).toContain('agent:a');
    expect(plan.seeded).toContain('skill:s');
  });

  it('delivers a genuinely new entry from a later version', () => {
    const grown = {
      agents: [{ id: 'a' }, { id: 'b' }],
      skills: [],
      instructions: [],
    } as never as Parameters<typeof planSeed>[0];
    const plan = planSeed(grown, { agents: ['a'], skills: [], instructions: [] }, [
      'agent:a',
    ]);
    expect(plan.agents.map((agent) => agent.id)).toEqual(['b']);
  });
});

describe('seeding a workspace', () => {
  it('populates empty catalogues on first open, marked as shipped', async () => {
    const root = await scratch('meridian-ws-');
    const extensionPath = await extensionWith({
      'agents/a.md': AGENT_MD,
      'skills/s.md': SKILL_MD,
      'instructions/i.md': INSTRUCTION_MD,
    });
    const { snapshot } = await serviceOn(root, extensionPath);
    const state = await snapshot();
    expect(state.skills.map((s) => s.id)).toContain('shipped-skill');
    expect(state.instructions.map((i) => i.id)).toContain('shipped-instruction');
    expect(state.agents.map((a) => a.id)).toContain('shipped-agent');
    expect(state.skills[0].source).toBe('builtin');
    // A shipped agent has earned no more trust than an imported one: Learning
    // mode, and nothing that can change a file.
    const agent = state.agents.find((entry) => entry.id === 'shipped-agent')!;
    expect(agent.mode).toBe('learning');
    expect([...agent.permissions].sort()).toEqual(['read', 'search', 'think']);
    // The shipped instruction documents are bound, or they reach no briefing
    // and the house rules they state apply to nobody.
    expect(agent.instructionIds).toEqual(['shipped-instruction']);
    // Skill packs are not: binding every pack would make one role several
    // contradictory specialists at once.
    expect(agent.skillIds).toEqual([]);
  });

  it('does not resurrect a built-in the user removed', async () => {
    const root = await scratch('meridian-ws-');
    const extensionPath = await extensionWith({ 'skills/s.md': SKILL_MD });
    const first = await serviceOn(root, extensionPath);
    expect((await first.snapshot()).skills.map((s) => s.id)).toContain(
      'shipped-skill',
    );
    await first.service.request({
      action: 'skill/remove',
      params: { id: 'shipped-skill' },
    });
    first.service.dispose();

    // Reopening the workspace is where a naive "seed what is missing" would
    // put it straight back.
    const second = await serviceOn(root, extensionPath);
    expect((await second.snapshot()).skills.map((s) => s.id)).not.toContain(
      'shipped-skill',
    );
  });

  it('leaves an edited built-in alone', async () => {
    const root = await scratch('meridian-ws-');
    const extensionPath = await extensionWith({ 'skills/s.md': SKILL_MD });
    const first = await serviceOn(root, extensionPath);
    const shipped = (await first.snapshot()).skills.find(
      (entry) => entry.id === 'shipped-skill',
    )!;
    await first.service.request({
      action: 'skill/save',
      params: { skill: { ...shipped, body: 'Rewritten by the user.' } },
    });
    first.service.dispose();

    const second = await serviceOn(root, extensionPath);
    const after = (await second.snapshot()).skills.find(
      (entry) => entry.id === 'shipped-skill',
    )!;
    expect(after.body).toBe('Rewritten by the user.');
  });

  it('records the seeding in the state file so it survives a reload', async () => {
    const root = await scratch('meridian-ws-');
    const extensionPath = await extensionWith({ 'skills/s.md': SKILL_MD });
    const { snapshot } = await serviceOn(root, extensionPath);
    await snapshot();
    const stored = JSON.parse(
      await readFile(
        path.join(root, '.meridian/workbench/state.json'),
        'utf8',
      ),
    );
    expect(stored.seededBuiltins).toContain('skill:shipped-skill');
  });

  it('opens normally when no library ships at all', async () => {
    const root = await scratch('meridian-ws-');
    const bare = await scratch('meridian-bare-');
    const { snapshot } = await serviceOn(root, bare);
    const state = await snapshot();
    expect(state.skills).toEqual([]);
    expect(state.agents).toEqual([]);
  });
});
