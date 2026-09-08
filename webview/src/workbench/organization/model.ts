import type { StudioDocument, StudioDocumentKind } from '../../../../shared/ts/studio';
import type { LedgerEntry } from '../../../../shared/ts/bus-types';
import type { WorkbenchSnapshot } from '../../../../shared/ts/workbench';

export type OrganizationView = 'stories' | 'portfolio' | 'specifications' | 'skills' | 'instructions' | 'connectors' | 'routing' | 'exchange' | 'reports';
export type OrganizationKind = 'story' | 'portfolio' | 'specification' | 'skill' | 'instruction' | 'connector' | 'routing' | 'report';
export interface Criterion { id: string; requirement: string; acceptance: string; evidence: string; state: 'unverified' | 'verified' | 'blocked' }
export interface RouteRule { phase: string; task: string; mode: 'deterministic' | 'assisted' | 'generative'; engine: string; fallback: string; ceiling: number }
export interface OrganizationContent {
  format: 'meridian.organization.v1'; kind: OrganizationKind;
  fields: Record<string, string>;
  links: string[];
  criteria: Criterion[];
  rules: RouteRule[];
}
export const VIEW_META: Record<Exclude<OrganizationView, 'exchange'>, { kind: OrganizationKind; title: string; headline: string; summary: string; add: string }> = {
  stories: { kind: 'story', title: 'Story Hub', headline: 'Keep the outcome in sight.', summary: 'Connect the story, its acceptance criteria, and the delivery work that makes it real.', add: 'New story' },
  portfolio: { kind: 'portfolio', title: 'Portfolio', headline: 'See the work as a whole.', summary: 'Prioritise linked stories, set a work-in-progress limit, and follow actual delivery progress.', add: 'New portfolio' },
  specifications: { kind: 'specification', title: 'Spec Studio', headline: 'Give every requirement a thread.', summary: 'Write explicit requirements, resolve ambiguity, and trace acceptance criteria to reviewable evidence.', add: 'New specification' },
  skills: { kind: 'skill', title: 'Skill Forge', headline: 'Craft expertise worth sharing.', summary: 'Author versioned skill instructions, inspect their scope, and apply a reviewed version to an agent.', add: 'New skill' },
  instructions: { kind: 'instruction', title: 'Instruction Library', headline: 'Make your standards explicit.', summary: 'Organise instruction drafts by scope. Review changes before updating an agent’s next-task context.', add: 'New instruction' },
  connectors: { kind: 'connector', title: 'Connectors & Write-back', headline: 'Keep the handoff deliberate.', summary: 'Design credential-free connections and field mappings, then preview the exact write-back content.', add: 'New connector' },
  routing: { kind: 'routing', title: 'Model Routing Observatory', headline: 'A reason for every route.', summary: 'Draft action-class routing rules, simulate a selection, and inspect recorded model-call evidence.', add: 'New routing policy' },
  reports: { kind: 'report', title: 'Documentation & Journey Report', headline: 'Tell the story with evidence.', summary: 'Build a report from the current workspace, select its sections, and export a reviewable Markdown document.', add: 'New report' },
};

export function emptyContent(kind: OrganizationKind): OrganizationContent {
  const fields: Record<string, string> = { summary: '', state: 'draft' };
  if (kind === 'story') Object.assign(fields, { source: 'Workspace', externalId: '', priority: 'normal', owner: '', complexity: 'standard', branch: '', due: '' });
  if (kind === 'portfolio') Object.assign(fields, { owner: '', client: '', wip: '3', budget: '', due: '' });
  if (kind === 'specification') Object.assign(fields, { complexity: 'standard', ambiguities: '', resolution: 'open' });
  if (kind === 'skill') Object.assign(fields, { packageVersion: '1.0.0', stack: '', tools: '', content: '---\nname: new-skill\ndescription: Describe when to use this skill.\n---\n\n# Instructions\n\n', source: 'Workspace author', scope: 'adapter' });
  if (kind === 'instruction') Object.assign(fields, { scope: 'workspace', path: 'AGENTS.md', content: '', rationale: '' });
  if (kind === 'connector') Object.assign(fields, { provider: 'Jira Cloud', endpoint: '', project: '', titleField: 'summary', bodyField: 'description', stateField: 'status', transition: 'In review', template: 'Delivery: {{title}}\nStatus: {{state}}\n\n{{brief}}', writeback: 'review-only' });
  if (kind === 'routing') Object.assign(fields, { region: '', note: '', state: 'draft' });
  if (kind === 'report') Object.assign(fields, { content: '', sections: 'summary,stories,deliverables,runs,learning,ledger' });
  return { format: 'meridian.organization.v1', kind, fields, links: [], criteria: [], rules: [] };
}
export function parseContent(document: StudioDocument): OrganizationContent {
  try {
    const value = JSON.parse(document.body) as Partial<OrganizationContent>;
    if (value.format === 'meridian.organization.v1' && value.kind === document.kind && value.fields && typeof value.fields === 'object' && !Array.isArray(value.fields)
      && Object.values(value.fields).every(v => typeof v === 'string') && Array.isArray(value.links) && value.links.every(v => typeof v === 'string')
      && Array.isArray(value.criteria) && value.criteria.every(v => v && typeof v.id === 'string' && typeof v.requirement === 'string' && typeof v.acceptance === 'string' && typeof v.evidence === 'string' && ['unverified', 'verified', 'blocked'].includes(v.state))
      && Array.isArray(value.rules) && value.rules.every(v => v && typeof v.phase === 'string' && typeof v.task === 'string' && ['deterministic', 'assisted', 'generative'].includes(v.mode) && typeof v.engine === 'string' && typeof v.fallback === 'string' && typeof v.ceiling === 'number')) return value as OrganizationContent;
  } catch { /* Plain Markdown remains editable and portable. */ }
  const fallback = emptyContent(document.kind as OrganizationKind);
  fallback.fields.summary = document.body;
  if (['skill', 'instruction', 'report'].includes(document.kind)) fallback.fields.content = document.body;
  return fallback;
}
export function validateContent(content: OrganizationContent): string | undefined {
  const { kind, fields, criteria, rules } = content;
  if (criteria.some(c => !c.id.trim() || !c.requirement.trim() || !c.acceptance.trim())) return 'Each criterion needs an ID, a requirement, and an acceptance condition.';
  if (new Set(criteria.map(c => c.id.trim().toLowerCase())).size !== criteria.length) return 'Criterion IDs must be unique.';
  if (criteria.some(c => c.state === 'verified' && !c.evidence.trim())) return 'A verified criterion needs an evidence reference. This is an author assertion, not an automated test verdict.';
  if (kind === 'skill') {
    if (!/^\d+\.\d+\.\d+$/.test(fields.packageVersion)) return 'Use a semantic package version, such as 1.0.0.';
    if (!/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/.test(fields.content) || !/^name:\s*\S.+$/m.test(fields.content) || !/^description:\s*\S.+$/m.test(fields.content)) return 'SKILL.md needs frontmatter with a name and description.';
  }
  if (kind === 'instruction' && !fields.content.trim()) return 'Write the instruction content before saving.';
  if (kind === 'portfolio' && (!Number.isInteger(Number(fields.wip)) || Number(fields.wip) < 1 || Number(fields.wip) > 100)) return 'Work-in-progress limit must be an integer from 1 to 100.';
  if (kind === 'connector') {
    try { const url = new URL(fields.endpoint); if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) return 'Use an HTTPS endpoint without credentials, query parameters, or fragments.'; } catch { return 'Enter a valid HTTPS connector endpoint.'; }
    if (Object.values(fields).some(value => /(?:api[_-]?key|access[_-]?token|authorization|password)\s*[:=]\s*\S+|\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,})/.test(value))) return 'Remove credentials from this configuration. Use your provider’s credential store.';
    if (!fields.project.trim() || !fields.titleField.trim() || !fields.bodyField.trim() || !fields.stateField.trim()) return 'Project and all field mappings are required.';
  }
  if (kind === 'routing') {
    if (!rules.length) return 'Add at least one routing rule.';
    if (rules.some(r => !r.phase.trim() || !r.task.trim() || !r.engine.trim() || !Number.isInteger(r.ceiling) || r.ceiling < 0)) return 'Every routing rule needs a phase, task class, engine, and nonnegative integer call ceiling.';
    if (rules.some(r => r.mode === 'deterministic' && r.ceiling !== 0)) return 'A deterministic route must have a zero model-call ceiling.';
    if (new Set(rules.map(r => `${r.phase.toLowerCase()}/${r.task.toLowerCase()}`)).size !== rules.length) return 'Phase and task-class combinations must be unique.';
  }
  return undefined;
}
export function matchRoute(rules: RouteRule[], phase: string, task: string): RouteRule | undefined {
  const normalized = (v: string) => v.trim().toLowerCase();
  return rules.map((rule, index) => ({ rule, index, score: Number(normalized(rule.phase) === normalized(phase)) * 2 + Number(normalized(rule.task) === normalized(task)) }))
    .filter(({ rule }) => (rule.phase === '*' || normalized(rule.phase) === normalized(phase)) && (rule.task === '*' || normalized(rule.task) === normalized(task)))
    .sort((a, b) => b.score - a.score || a.index - b.index)[0]?.rule;
}
export function writebackPreview(content: OrganizationContent, delivery?: { title: string; brief: string; state: string }): Record<string, string> {
  if (!delivery) return {};
  const { fields } = content;
  return { [fields.titleField]: delivery.title, [fields.bodyField]: fields.template.replace(/\{\{(title|brief|state)\}\}/g, (_, field: 'title' | 'brief' | 'state') => delivery[field]), [fields.stateField]: fields.transition };
}
export function buildJourney(snapshot: WorkbenchSnapshot, title: string, sections: string[], ledger: LedgerEntry[] | undefined, workspaceDir?: string): string {
  const lines = [`# ${title}`, '', `Generated: ${new Date().toISOString()}`, `Workspace: ${workspaceDir || 'Current workspace'}`, `Snapshot revision: ${snapshot.revision}`, '', 'This report combines local workspace records and a bounded ledger sample. It is not a signed audit bundle or a verification verdict.', ''];
  const include = (name: string, heading: string, body: string[]) => { if (sections.includes(name)) lines.push(`## ${heading}`, '', ...body, ''); };
  include('summary', 'Summary', [`${snapshot.agents.length} agents · ${snapshot.agents.filter(a => a.mode === 'active').length} active · ${snapshot.agents.filter(a => a.mode === 'learning').length} Learning`, `${snapshot.deliverables.length} deliverables · ${snapshot.deliverables.filter(d => d.state === 'completed').length} completed`]);
  include('stories', 'Stories and specifications', (snapshot.documents ?? []).filter(d => d.kind === 'story' || d.kind === 'specification').flatMap(d => { const c = parseContent(d); return [`### ${d.title} (v${d.version})`, c.fields.summary, ...c.criteria.map(row => `- ${row.id}: ${row.requirement} — ${row.acceptance} [${row.state}; evidence: ${row.evidence || 'none'}]`), '']; }));
  include('deliverables', 'Deliverables', snapshot.deliverables.flatMap(d => [`### ${d.title}`, `ID: ${d.id} · State: ${d.state} · Updated: ${d.updatedAt}`, d.brief, d.feedback ? `Review: ${d.feedback}` : 'No completion feedback recorded.', '']));
  include('runs', 'Agent run history', snapshot.runs.map(r => `- ${r.id}: ${r.agentName} — ${r.state} (${r.startedAt})${r.error ? ` · ${r.error}` : ''}`));
  include('learning', 'Learning review', snapshot.learning.map(n => `- ${n.title}: ${n.state} · Agent ${n.agentId} · Source ${n.deliverableId}`));
  include('ledger', 'Recorded evidence sample', ledger ? [`Sample: ${ledger.length} entries, limited to the latest query of up to 200 entries.`, ...ledger.map(e => `- #${e.sequence}: ${e.timestamp} · ${e.actorId} · ${e.actionType} · ${e.decision || 'no decision field'} · ${e.entryHash}`)] : ['Ledger was unavailable when this report was generated. No evidence or cost totals have been inferred.']);
  return lines.join('\n');
}
export const isOrganizationKind = (kind: StudioDocumentKind): kind is OrganizationKind => ['story', 'portfolio', 'specification', 'skill', 'instruction', 'connector', 'routing', 'report'].includes(kind);
