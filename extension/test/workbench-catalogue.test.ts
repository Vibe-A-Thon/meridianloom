import { mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { deflateRawSync } from 'node:zlib';
import { afterEach, describe, expect, it } from 'vitest';
import { WorkbenchService } from '../src/workbench/service';
import type {
  ImportReport,
  WorkbenchAgentInput,
  WorkbenchSnapshot,
} from '../../shared/ts/workbench';

/**
 * Skills, instructions, SDLC phase tagging and package import, at the
 * service boundary.
 *
 * These four together are what make an agent in Meridian a *portable* thing
 * rather than a row in a database: what it knows (skills), how the house
 * works (instructions), where it is allowed to take part (phases), and how it
 * arrives and leaves (import/export). Each is asserted here as the GUI uses
 * it, because the GUI is the only way a user reaches any of them.
 */

const agent = (id: string): WorkbenchAgentInput => ({
  id,
  name: id.toUpperCase(),
  role: 'developer',
  description: 'Portable specialist',
  vendor: 'custom',
  version: '1.0.0',
  command: 'test-acp-agent',
  args: [],
  instructions: 'Inspect and explain.',
  permissions: ['read', 'search', 'think'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
});

const skill = (id: string) => ({
  id,
  name: id.toUpperCase(),
  summary: 'A stack pack.',
  version: '1.0.0',
  tags: ['stack'],
  body: '# Overview\n\nGradle, not Maven.\n',
});

const instruction = (id: string) => ({
  id,
  name: id.toUpperCase(),
  summary: 'How we work.',
  scope: 'workspace' as const,
  body: '# House rules\n\nSmall commits.\n',
});

const services: WorkbenchService[] = [];
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
});

async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'meridian-catalogue-'));
  const service = new WorkbenchService({
    workspaceDir: () => root,
    trusted: () => true,
    enabledTiers: () => ['flight-recorder', 'governor'],
    sidecar: () => ({ request: async () => ({ entries: [] }) }),
    humanApprover: async () => ({ outcome: 'cancelled' }),
  });
  services.push(service);
  const snapshot = async () =>
    (await service.request({ action: 'snapshot' })) as WorkbenchSnapshot;
  return { root, service, snapshot };
}

// --- skills -------------------------------------------------------------

describe('skills', () => {
  it('saves, lists, disables and removes a skill pack', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'skill/save', params: { skill: skill('java') } });

    let state = await snapshot();
    expect(state.skills).toHaveLength(1);
    expect(state.skills[0].enabled).toBe(true);
    expect(state.skills[0].source).toBe('authored');

    await service.request({
      action: 'skill/toggle',
      params: { id: 'java', enabled: false },
    });
    expect((await snapshot()).skills[0].enabled).toBe(false);

    await service.request({ action: 'skill/remove', params: { id: 'java' } });
    state = await snapshot();
    expect(state.skills).toEqual([]);
  });

  it('exports a skill in the open SKILL.md shape, readable without Meridian', async () => {
    const { service } = await setup();
    await service.request({ action: 'skill/save', params: { skill: skill('java') } });
    const file = (await service.request({
      action: 'skill/export',
      params: { id: 'java' },
    })) as { fileName: string; content: string };
    expect(file.fileName).toBe('java.SKILL.md');
    expect(file.content).toMatch(/^---\n/);
    expect(file.content).toContain('name: "JAVA"');
    expect(file.content).toContain('Gradle, not Maven.');
  });

  it('removing a skill strips the binding from every agent that carried it', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'skill/save', params: { skill: skill('java') } });
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', skillIds: ['java'] },
    });
    expect((await snapshot()).agents[0].skillIds).toEqual(['java']);

    await service.request({ action: 'skill/remove', params: { id: 'java' } });
    // A dangling binding would make an agent claim a specialisation it no
    // longer has, so the removal reaches into the agents too.
    expect((await snapshot()).agents[0].skillIds).toEqual([]);
  });
});

// --- instructions -------------------------------------------------------

describe('instructions', () => {
  it('keeps the precedence scope it was given', async () => {
    const { service, snapshot } = await setup();
    await service.request({
      action: 'instruction/save',
      params: { instruction: { ...instruction('house'), scope: 'organisation' } },
    });
    expect((await snapshot()).instructions[0].scope).toBe('organisation');
  });

  it('exports as a Markdown instruction file', async () => {
    const { service } = await setup();
    await service.request({
      action: 'instruction/save',
      params: { instruction: instruction('house') },
    });
    const file = (await service.request({
      action: 'instruction/export',
      params: { id: 'house' },
    })) as { fileName: string; content: string };
    expect(file.fileName).toBe('house.AGENTS.md');
    expect(file.content).toContain('Small commits.');
  });

  it('removing an instruction unbinds it from agents', async () => {
    const { service, snapshot } = await setup();
    await service.request({
      action: 'instruction/save',
      params: { instruction: instruction('house') },
    });
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', instructionIds: ['house'] },
    });
    await service.request({ action: 'instruction/remove', params: { id: 'house' } });
    expect((await snapshot()).agents[0].instructionIds).toEqual([]);
  });
});

// --- SDLC phase tagging -------------------------------------------------

describe('SDLC phase tagging', () => {
  it('tags an agent to phases and leaves the other bindings alone', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    await service.request({ action: 'skill/save', params: { skill: skill('java') } });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', skillIds: ['java'] },
    });
    await service.request({
      action: 'agent/assign',
      params: { id: 'atlas', phases: ['design', 'review'] },
    });
    const saved = (await snapshot()).agents[0];
    expect(saved.phases).toEqual(['design', 'review']);
    // Assigning phases must not silently drop the skill binding.
    expect(saved.skillIds).toEqual(['java']);
  });

  it('refuses a phase outside the nine', async () => {
    const { service } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    await expect(
      service.request({
        action: 'agent/assign',
        params: { id: 'atlas', phases: ['deployment-ish'] },
      }),
    ).rejects.toThrow();
  });

  it('an agent saved before phases existed still loads, tagged with none', async () => {
    const { service, snapshot } = await setup();
    const legacy = { ...agent('legacy') } as Record<string, unknown>;
    delete legacy.phases;
    delete legacy.skillIds;
    delete legacy.instructionIds;
    await service.request({ action: 'agent/save', params: { agent: legacy } });
    const saved = (await snapshot()).agents[0];
    expect(saved.phases).toEqual([]);
    expect(saved.skillIds).toEqual([]);
    expect(saved.instructionIds).toEqual([]);
  });
});

// --- package import -----------------------------------------------------

function zip(members: { name: string; body: string }[]): string {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  const crc32 = (buffer: Buffer) => {
    let crc = ~0;
    for (const byte of buffer) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit += 1)
        crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
    return ~crc >>> 0;
  };
  for (const member of members) {
    const nameBytes = Buffer.from(member.name, 'utf8');
    const raw = Buffer.from(member.body, 'utf8');
    const data = deflateRawSync(raw);
    const crc = crc32(raw);
    const local = Buffer.alloc(30 + nameBytes.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(8, 8);
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
    central.writeUInt16LE(8, 10);
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
  return Buffer.concat([...locals, centralBytes, eocd]).toString('base64');
}

describe('importing an agent package', () => {
  it('imports a Markdown agent card into Learning, never straight into service', async () => {
    const { service, snapshot } = await setup();
    const result = (await service.request({
      action: 'agent/importPackage',
      params: {
        fileName: 'atlas.md',
        content:
          '---\nkind: agent\nname: Atlas\nrole: Architect\ncommand: claude\n---\n# Atlas\n',
      },
    })) as { snapshot: WorkbenchSnapshot; report: ImportReport };

    expect(result.report.format).toBe('markdown');
    expect(result.report.agents).toEqual(['atlas']);
    // An imported agent has not been reviewed by anyone here yet, so it
    // arrives in Learning and takes part in nothing until a human says so.
    expect(result.snapshot.agents[0].mode).toBe('learning');
    // An import is not consent to write files or run commands: a package
    // that named no permissions gets only the three that change nothing.
    expect(result.snapshot.agents[0].permissions).toEqual(['read', 'search', 'think']);
    expect((await snapshot()).agents).toHaveLength(1);
  });

  it('imports an adapter folder from a ZIP, binding its skills and instructions', async () => {
    const { service } = await setup();
    const result = (await service.request({
      action: 'agent/importPackage',
      params: {
        fileName: 'atlas.zip',
        contentBase64: zip([
          {
            name: 'atlas/adapter.yaml',
            body: 'id: atlas\nname: Atlas\nrole: Architect\ncommand: claude\n',
          },
          {
            name: 'atlas/skills/java/SKILL.md',
            body: '---\nname: Java\nversion: 1.0.0\n---\n# Java\n',
          },
          {
            name: 'atlas/instructions/house.md',
            body: '---\nname: House\n---\n# House\n',
          },
        ]),
      },
    })) as { snapshot: WorkbenchSnapshot; report: ImportReport };

    expect(result.report.format).toBe('zip');
    expect(result.report.agents).toHaveLength(1);
    expect(result.report.skills).toHaveLength(1);
    expect(result.report.instructions).toHaveLength(1);
    const imported = result.snapshot.agents[0];
    expect(imported.skillIds).toEqual(result.report.skills);
    expect(imported.instructionIds).toEqual(result.report.instructions);
  });

  it('never overwrites an existing agent; the import lands beside it', async () => {
    const { service, snapshot } = await setup();
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    const result = (await service.request({
      action: 'agent/importPackage',
      params: {
        fileName: 'atlas.md',
        content: '---\nkind: agent\nname: Atlas\ncommand: claude\n---\n# Atlas\n',
      },
    })) as { snapshot: WorkbenchSnapshot; report: ImportReport };

    expect(result.report.agents).toEqual(['atlas-2']);
    const ids = (await snapshot()).agents.map((entry) => entry.id).sort();
    expect(ids).toEqual(['atlas', 'atlas-2']);
    // The agent the user already had is untouched, including its mode.
    expect((await snapshot()).agents.find((a) => a.id === 'atlas')!.name).toBe('ATLAS');
  });

  it('persists an import to the workspace so it survives a reload', async () => {
    const { service, root } = await setup();
    await service.request({
      action: 'agent/importPackage',
      params: {
        fileName: 'SKILL.md',
        content: '---\nname: Go\nversion: 1.0.0\n---\n# Go\n',
      },
    });
    const stored = JSON.parse(
      await readFile(path.join(root, '.meridian/workbench/state.json'), 'utf8'),
    );
    expect(stored.skills).toHaveLength(1);
    expect(stored.skills[0].source).toBe('imported');
  });

  it('reports a refusal in a sentence rather than a silent no-op', async () => {
    const { service } = await setup();
    await expect(
      service.request({
        action: 'agent/importPackage',
        params: { fileName: 'empty.md', content: '' },
      }),
    ).rejects.toThrow(/empty/i);
  });
});

// --- export round trip --------------------------------------------------

describe('exporting an agent', () => {
  it('carries its skills and instructions, so the agent travels whole', async () => {
    const { service } = await setup();
    await service.request({ action: 'skill/save', params: { skill: skill('java') } });
    await service.request({
      action: 'instruction/save',
      params: { instruction: instruction('house') },
    });
    await service.request({ action: 'agent/save', params: { agent: agent('atlas') } });
    await service.request({
      action: 'agent/assign',
      params: {
        id: 'atlas',
        skillIds: ['java'],
        instructionIds: ['house'],
        phases: ['design'],
      },
    });
    const file = (await service.request({
      action: 'agent/export',
      params: { id: 'atlas' },
    })) as { fileName: string; content: string };
    const document = JSON.parse(file.content);
    expect(document.kind).toBe('meridian-portable-agent');
    expect(document.agent.phases).toEqual(['design']);
    expect(document.skills.map((s: { id: string }) => s.id)).toEqual(['java']);
    expect(document.instructions.map((i: { id: string }) => i.id)).toEqual(['house']);
    // Credentials never travel with an agent.
    expect(file.content).not.toMatch(/api[-_]?key|token|password/i);
  });
});
