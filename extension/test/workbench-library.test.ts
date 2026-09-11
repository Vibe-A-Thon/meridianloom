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

  it('ships a real library with the extension, covering every SDLC phase', async () => {
    // Not a fixture — the actual shipped files. A library that parses in a
    // unit test and not in the box would be the same empty-catalogue problem
    // wearing a passing test.
    const library = await loadBuiltinLibrary(path.resolve(__dirname, '..'));
    expect(library.agents.length).toBeGreaterThanOrEqual(9);
    expect(library.skills.length).toBeGreaterThan(0);
    expect(library.instructions.length).toBeGreaterThan(0);
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
    // Nothing shipped may arrive able to change anything.
    for (const agent of library.agents) {
      expect(agent.permissions.sort()).toEqual(['read', 'search', 'think']);
      expect(agent.command).toBe('');
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
