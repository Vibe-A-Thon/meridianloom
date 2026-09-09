import {
  SDLC_PHASES,
  SDLC_PHASE_LABELS,
  type LearningArtifact,
  type SdlcPhase,
  type WorkbenchAgent,
  type WorkbenchInstruction,
  type WorkbenchSkill,
} from '../../../shared/ts/workbench';
import {
  integrationById,
  type IntegrationConnection,
} from '../../../shared/ts/integrations';

/**
 * What an agent actually receives.
 *
 * Everything the workbench catalogues — skills, instruction files, tool
 * connections, accepted memory, the phase it was convened for — is only real
 * if it reaches the agent's prompt. This module is that reaching. Before it
 * existed the catalogue was decorative: bindings were stored, displayed and
 * exported, and the agent was handed the brief and its own role and nothing
 * else. Any binding that does not appear here does not exist as far as the
 * work is concerned.
 *
 * Two rules govern the composition.
 *
 * **Precedence is explicit and ordered.** Instruction files are rendered
 * least-specific first — organisation, then user, then workspace, then
 * adapter — so the most specific instruction is the last thing the agent
 * reads, and the document says so in words rather than relying on position.
 *
 * **Nothing here is a credential.** A connection contributes its system, its
 * name, its endpoint and what Meridian can read from it. The secret that
 * makes the connection work stays in the OS keychain, and the briefing says
 * plainly that the agent must use its own credentials.
 */

/** What the whole briefing may weigh, so a large skill cannot blow a context window. */
export const BRIEFING_BUDGET = 60_000;
/** No single skill or instruction may take more than this share of the budget. */
const SECTION_BUDGET = 12_000;

export interface BriefingInput {
  agent: WorkbenchAgent;
  /** The request: a deliverable brief, or an ad-hoc prompt. */
  task: { title?: string; body: string };
  /** The phase this agent was convened for, when dispatch convened by phase. */
  phase?: SdlcPhase;
  /** Enabled skills bound to this agent, in catalogue order. */
  skills: readonly WorkbenchSkill[];
  /** Enabled instruction files bound to this agent. */
  instructions: readonly WorkbenchInstruction[];
  /** Enabled tool connections bound to this agent. */
  integrations: readonly IntegrationConnection[];
  /** Memory notes a human has accepted for this agent. */
  memory: readonly LearningArtifact[];
}

/** Least specific first: the last thing read is the most specific. */
const SCOPE_ORDER: readonly WorkbenchInstruction['scope'][] = [
  'organisation',
  'user',
  'workspace',
  'adapter',
];

const PHASE_PURPOSE: Readonly<Record<SdlcPhase, string>> = {
  intake: 'Clarify the request and surface the ambiguities before anything is designed.',
  design: 'Decide the shape, record the decisions, and allocate the constraints.',
  plan: 'Break the work into packets, with acceptance tests contracted first.',
  build: "Implement it, with this repository's conventions outranking your defaults.",
  verify: 'Prove the acceptance criteria are covered and passing.',
  security: 'Check the threat surface and clear or explicitly waive the findings.',
  review: 'Critique adversarially; a human approves before anything merges.',
  release: 'Produce the artefact and state the rollback plan.',
  operate: 'Watch the measures, triage regressions, and feed back what was learned.',
};

function truncate(text: string, limit: number, what: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= limit) return trimmed;
  return (
    `${trimmed.slice(0, limit)}\n\n` +
    `[Meridian truncated this ${what} at ${limit.toLocaleString()} characters. ` +
    `The full text is in the workbench.]`
  );
}

/**
 * Render the connection facts an agent may act on. Deliberately not the
 * credential, and deliberately not a promise that the agent can query it:
 * the agent is a separate process with its own credentials, and saying
 * otherwise would be the same class of lie as a green light on an untested
 * connection.
 */
function renderIntegrations(connections: readonly IntegrationConnection[]): string {
  const lines: string[] = [];
  for (const connection of connections) {
    const definition = integrationById(connection.integrationId);
    if (!definition) continue;
    const endpoint = connection.config.baseUrl ?? '';
    const detail = Object.entries(connection.config)
      .filter(([key, value]) => key !== 'baseUrl' && value)
      .map(([key, value]) => `${key}=${value}`)
      .join(', ');
    const reach = connection.lastProbe
      ? connection.lastProbe.ok
        ? `last reached ${connection.lastProbe.at}`
        : `NOT reachable at ${connection.lastProbe.at}: ${connection.lastProbe.detail}`
      : 'never tested by Meridian';
    lines.push(
      `- **${definition.name}** — "${connection.name}"` +
        `${endpoint ? ` at ${endpoint}` : ''}${detail ? ` (${detail})` : ''}. ` +
        `Meridian can read: ${definition.operations.map((op) => op.label).join(', ')}. ` +
        `Status: ${reach}.`,
    );
  }
  return lines.join('\n');
}

/**
 * Compose the briefing. Deterministic: the same inputs always produce the
 * same document, so a run is reproducible and a diff between two briefings
 * is meaningful.
 */
export function composeBriefing(input: BriefingInput): string {
  const { agent, task, phase } = input;
  const parts: string[] = [];

  parts.push(
    task.title ? `# ${task.title}\n\n${task.body.trim()}` : task.body.trim(),
  );

  const roleLine = phase
    ? `You are **${agent.name}**, acting as ${agent.role}, convened for the ` +
      `**${SDLC_PHASE_LABELS[phase]}** phase of this delivery.\n\n${PHASE_PURPOSE[phase]}`
    : `You are **${agent.name}**, acting as ${agent.role}.`;
  parts.push(`## Your role\n\n${roleLine}`);

  if (agent.instructions.trim())
    parts.push(`## Your standing instructions\n\n${truncate(agent.instructions, SECTION_BUDGET, 'instruction')}`);

  const ordered = SCOPE_ORDER.flatMap((scope) =>
    input.instructions.filter((entry) => entry.scope === scope),
  );
  if (ordered.length) {
    const rendered = ordered
      .map(
        (entry) =>
          `### ${entry.name} — ${entry.scope} scope\n\n${truncate(entry.body, SECTION_BUDGET, 'instruction file')}`,
      )
      .join('\n\n');
    parts.push(
      '## How this organisation works\n\n' +
        'These are ordered from least specific to most specific. Where two of ' +
        'them disagree, the later one wins: adapter over workspace over user ' +
        'over organisation.\n\n' +
        rendered,
    );
  }

  if (input.skills.length) {
    const rendered = input.skills
      .map(
        (skill) =>
          `### ${skill.name} (v${skill.version})` +
          `${skill.summary ? `\n\n${skill.summary}` : ''}\n\n${truncate(skill.body, SECTION_BUDGET, 'skill')}`,
      )
      .join('\n\n');
    parts.push(
      '## Skills you are working with\n\n' +
        'These describe how work is done on this stack. Follow them over your ' +
        'own defaults.\n\n' +
        rendered,
    );
  }

  if (input.integrations.length) {
    parts.push(
      '## Systems this workspace is connected to\n\n' +
        renderIntegrations(input.integrations) +
        '\n\nThese are facts about the estate, not access. Meridian holds those ' +
        'credentials in the OS keychain and does not pass them to you. If you ' +
        'need to reach one of these systems, use your own configured ' +
        'credentials and say what you did.',
    );
  }

  if (input.memory.length) {
    const rendered = input.memory
      .map((note) => `- **${note.title}**: ${note.content.trim()}`)
      .join('\n');
    parts.push(
      '## What you have been taught here\n\n' +
        'A human reviewed and accepted each of these.\n\n' +
        rendered,
    );
  }

  parts.push(
    '## What to do\n\n' +
      'Work only within this brief. State what you changed and what you ' +
      'verified. If the brief is ambiguous in a way that changes the outcome, ' +
      'say so rather than guessing.',
  );

  const document = parts.join('\n\n');
  return document.length <= BRIEFING_BUDGET
    ? document
    : truncate(document, BRIEFING_BUDGET, 'briefing');
}

/**
 * Which agents are convened, in which order, for a deliverable.
 *
 * Phase tagging is the delivery chain: for each of the nine phases in order,
 * the active agents tagged for it. An agent tagged for three phases is
 * convened three times, once per phase, because a designer reviewing their
 * own build is a different act from designing.
 *
 * The fallback matters as much as the rule. If **no** active agent carries a
 * single phase tag, the roster has not been shaped yet, and refusing to run
 * would punish a user who never opened the Phases tab. In that case every
 * active agent is convened once, unphased. As soon as one agent is tagged,
 * tagging is the contract and untagged agents are not convened — which is
 * what the Phases board tells the user.
 */
export function convene(
  agents: readonly WorkbenchAgent[],
): { agent: WorkbenchAgent; phase?: SdlcPhase }[] {
  const active = agents.filter((agent) => agent.mode === 'active');
  const anyTagged = active.some((agent) => agent.phases.length > 0);
  if (!anyTagged) return active.map((agent) => ({ agent }));
  return SDLC_PHASES.flatMap((phase) =>
    active
      .filter((agent) => agent.phases.includes(phase))
      .map((agent) => ({ agent, phase })),
  );
}
