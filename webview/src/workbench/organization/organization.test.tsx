import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { StudioDocument } from '../../../../shared/ts/studio';
import type {
  WorkbenchAgent,
  WorkbenchExecute,
  WorkbenchSnapshot,
} from '../../../../shared/ts/workbench';
import type { WorkbenchController } from '../useWorkbench';
import { OrganizationStudio } from './OrganizationStudio';
import {
  emptyContent,
  parseContent,
  validateContent,
  matchRoute,
  buildJourney,
  type OrganizationKind,
} from './model';
import { inspectImport } from './ExchangeStudio';
import { getVsCodeApi } from '../../host/vscode-api';

const at = '2026-09-08T00:00:00Z';
const agent: WorkbenchAgent = {
  id: 'atlas',
  name: 'Atlas',
  role: 'Developer',
  description: '',
  vendor: '',
  version: '1.0.0',
  command: 'atlas-acp',
  args: [],
  instructions: 'Keep existing guidance.',
  permissions: ['read'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
  mode: 'learning',
  runtime: 'idle',
  learningState: 'waiting',
  createdAt: at,
  updatedAt: at,
};
const delivery = {
  id: 'delivery-1',
  title: 'Accessible editor',
  brief: 'Keyboard operation is required.',
  state: 'review' as const,
  agentIds: ['atlas'],
  createdAt: at,
  updatedAt: at,
};
function doc(
  kind: OrganizationKind,
  title = 'Test document',
  fields: Record<string, string> = {},
  extra: Partial<StudioDocument> = {},
): StudioDocument {
  const value = emptyContent(kind);
  Object.assign(value.fields, fields);
  return {
    id: `doc-${kind}`,
    kind,
    title,
    body: JSON.stringify(value),
    tags: [],
    version: 2,
    createdAt: at,
    updatedAt: at,
    ...extra,
  };
}
function harness(
  documents: StudioDocument[] = [],
  extra: Partial<WorkbenchSnapshot> = {},
) {
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    agents: [agent],
    skills: [],
    instructions: [],
    integrations: [],
    deliverables: [delivery],
    runs: [],
    learning: [],
    documents,
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: false,
      executionReady: false,
    },
    ...extra,
  };
  const execute = vi.fn(async () => snapshot);
  const controller: WorkbenchController = {
    snapshot,
    busy: false,
    error: null,
    execute: execute as WorkbenchExecute,
    refresh: async () => {},
  };
  const onNavigate = vi.fn();
  return { snapshot, execute, props: { controller, ready: true, onNavigate } };
}

describe('Organization authoring and version control', () => {
  it('authors a traceable specification and refuses unsupported verification claims', async () => {
    const h = harness();
    render(<OrganizationStudio view="specifications" {...h.props} />);
    fireEvent.click(
      screen.getAllByRole('button', { name: 'New specification' })[0],
    );
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Keyboard access' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Add acceptance criterion' }),
    );
    fireEvent.change(screen.getByLabelText('Requirement 1'), {
      target: { value: 'Dialog supports keyboard input.' },
    });
    fireEvent.change(screen.getByLabelText('Acceptance condition 1'), {
      target: { value: 'Escape closes and restores focus.' },
    });
    fireEvent.change(screen.getByLabelText('Evidence status 1'), {
      target: { value: 'verified' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save document' }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'verified criterion needs an evidence',
    );
    expect(h.execute).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Evidence reference 1'), {
      target: { value: 'dialog.test.tsx:18' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save document' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    const [action, params] = h.execute.mock.calls[0] as unknown as [
      string,
      { document: StudioDocument },
    ];
    expect(action).toBe('document/save');
    expect(JSON.parse(params.document.body).criteria[0]).toMatchObject({
      id: 'AC-1',
      evidence: 'dialog.test.tsx:18',
      state: 'verified',
    });
  });
  it('links a story to an actual deliverable without dispatching it', async () => {
    const h = harness();
    render(<OrganizationStudio view="stories" {...h.props} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'New story' })[0]);
    fireEvent.change(screen.getByLabelText('Title'), {
      target: { value: 'Ship accessible UI' },
    });
    fireEvent.click(screen.getByLabelText('Accessible editor'));
    fireEvent.click(screen.getByRole('button', { name: 'Save document' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    const [action, params] = h.execute.mock.calls[0] as unknown as [
      string,
      { document: StudioDocument },
    ];
    expect(action).toBe('document/save');
    expect(JSON.parse(params.document.body).links).toEqual(['delivery-1']);
  });
  it('preserves edited content when an optimistic version conflict is returned', async () => {
    const h = harness([
      doc('instruction', 'Team rules', { content: 'Review all changes.' }),
    ]);
    h.execute.mockRejectedValue(
      new Error('Version conflict: reload the current document.'),
    );
    render(<OrganizationStudio view="instructions" {...h.props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit Team rules' }));
    fireEvent.change(screen.getByLabelText('Instruction content'), {
      target: { value: 'Review every public API.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save new version' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Version conflict',
    );
    expect(screen.getByLabelText('Instruction content')).toHaveValue(
      'Review every public API.',
    );
    expect(h.execute).toHaveBeenCalledWith('document/save', {
      document: expect.objectContaining({
        id: 'doc-instruction',
        expectedVersion: 2,
      }),
    });
  });
  it('requires review before applying an instruction and preserves the agent configuration', async () => {
    const h = harness([
      doc('instruction', 'Team rules', { content: 'Write meaningful tests.' }),
    ]);
    render(<OrganizationStudio view="instructions" {...h.props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Team rules' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Review agent application' }),
    );
    fireEvent.change(screen.getByLabelText('Target agent'), {
      target: { value: 'atlas' },
    });
    expect(
      screen.getByRole('button', { name: 'Apply reviewed version' }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByLabelText('I reviewed the instruction changes for Atlas'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Apply reviewed version' }),
    );
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    expect(h.execute).toHaveBeenCalledWith('agent/save', {
      agent: expect.objectContaining({
        id: 'atlas',
        permissions: ['read'],
        command: 'atlas-acp',
        trainable: ['memory'],
        phases: [],
        skillIds: [],
        instructionIds: [],
  integrationIds: [],
        instructions: expect.stringContaining('Keep existing guidance.'),
      }),
    });
    const [, params] = h.execute.mock.calls[0] as unknown as [
      string,
      { agent: WorkbenchAgent },
    ];
    expect(params.agent.instructions).toContain('Write meaningful tests.');
    expect(params.agent).not.toHaveProperty('mode');
  });
  it('reviews revision content before restoring it with the current version check', async () => {
    const current = doc('instruction', 'Team rules', { content: 'Current.' });
    const older = doc(
      'instruction',
      'Team rules',
      { content: 'Previous.' },
      { version: 1 },
    );
    const h = harness([current], { documentRevisions: [older] });
    render(<OrganizationStudio view="instructions" {...h.props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Team rules' }));
    fireEvent.click(
      screen.getByText('Revision history · 1 retained revisions'),
    );
    fireEvent.change(screen.getByLabelText('Saved revision'), {
      target: { value: '1' },
    });
    expect(
      screen.getByRole('button', { name: 'Restore as new version' }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByLabelText('I reviewed the revision to restore'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Restore as new version' }),
    );
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('document/restore', {
        id: current.id,
        version: 1,
        expectedVersion: 2,
      }),
    );
  });
  it('keeps removal separate from inspection and sends an optimistic version', async () => {
    const h = harness([doc('portfolio', 'Delivery programme')]);
    render(<OrganizationStudio view="portfolio" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Inspect Delivery programme' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Remove document' }));
    expect(h.execute).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('document/remove', {
        id: 'doc-portfolio',
        expectedVersion: 2,
      }),
    );
  });
});

describe('Routing, connectors, exchange, and reporting', () => {
  it('selects the most specific route locally without sending a model request', () => {
    const policy = doc('routing', 'Python first');
    const c = parseContent(policy);
    c.rules = [
      {
        phase: '*',
        task: '*',
        mode: 'assisted',
        engine: 'general',
        fallback: '',
        ceiling: 1,
      },
      {
        phase: 'implementation',
        task: 'code-search',
        mode: 'deterministic',
        engine: 'ripgrep',
        fallback: '',
        ceiling: 0,
      },
    ];
    policy.body = JSON.stringify(c);
    const h = harness([policy]);
    render(<OrganizationStudio view="routing" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Inspect Python first' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Simulate selection' }));
    expect(
      within(screen.getByRole('dialog')).getByRole('status'),
    ).toHaveTextContent('ripgrep');
    expect(h.execute).not.toHaveBeenCalled();
  });
  it('previews mapped real delivery content while making no external write', () => {
    const h = harness([
      doc('connector', 'Project tracker', {
        endpoint: 'https://example.atlassian.net',
        project: 'DEMO',
      }),
    ]);
    render(<OrganizationStudio view="connectors" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Inspect Project tracker' }),
    );
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Keyboard operation is required.',
    );
    expect(screen.getByRole('dialog')).toHaveTextContent('has not been sent');
    expect(h.execute).not.toHaveBeenCalled();
  });
  it('requires inspection and review before an agent import', async () => {
    const h = harness();
    render(<OrganizationStudio view="exchange" {...h.props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Import package' }));
    const value = { kind: 'meridian-portable-agent', schemaVersion: 1, agent };
    fireEvent.change(screen.getByLabelText('Package JSON'), {
      target: { value: JSON.stringify(value) },
    });
    expect(
      screen.getByRole('button', { name: 'Import reviewed package' }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect package' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Starts in Learning');
    fireEvent.click(
      screen.getByLabelText('I reviewed this package and its source'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Import reviewed package' }),
    );
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('agent/import', {
        content: JSON.stringify(value),
      }),
    );
  });
  it('builds a report from actual records and states missing ledger evidence', async () => {
    const h = harness();
    render(<OrganizationStudio view="reports" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Build journey report' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Generate report preview' }),
    );
    expect(screen.getByRole('dialog')).toHaveTextContent('Accessible editor');
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Ledger was unavailable',
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Save report to workspace' }),
    );
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    const [, params] = h.execute.mock.calls[0] as unknown as [
      string,
      { document: StudioDocument },
    ];
    expect(params.document.kind).toBe('report');
    expect(parseContent(params.document).fields.content).toContain(
      'Keyboard operation is required.',
    );
  });
  it('does not issue a download before export review', async () => {
    const h = harness();
    const post = vi.spyOn(getVsCodeApi(), 'postMessage');
    h.execute.mockResolvedValue({
      fileName: 'atlas.json',
      content: '{"kind":"meridian-portable-agent"}',
    } as unknown as WorkbenchSnapshot);
    render(<OrganizationStudio view="exchange" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Review export Atlas' }),
    );
    await screen.findByRole('dialog');
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('I reviewed the outgoing content'));
    fireEvent.click(
      screen.getByRole('button', { name: 'Export reviewed package' }),
    );
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'download', fileName: 'atlas.json' }),
    );
    post.mockRestore();
  });
});

describe('Organization data validation', () => {
  it('rejects credential-bearing connector endpoints and deterministic model calls', () => {
    const c = emptyContent('connector');
    c.fields.endpoint = 'https://token:secret@example.com';
    c.fields.project = 'DEMO';
    expect(validateContent(c)).toContain('without credentials');
    c.fields.endpoint = 'https://example.com?token=abc';
    expect(validateContent(c)).toContain('query parameters');
    const routing = emptyContent('routing');
    routing.rules = [
      {
        phase: '*',
        task: 'test',
        mode: 'deterministic',
        engine: 'pytest',
        fallback: '',
        ceiling: 1,
      },
    ];
    expect(validateContent(routing)).toContain('zero model-call ceiling');
  });
  it('rejects duplicate criterion IDs and imports of unsupported packages', () => {
    const c = emptyContent('specification');
    c.criteria = [
      {
        id: 'AC-1',
        requirement: 'A',
        acceptance: 'B',
        evidence: '',
        state: 'unverified',
      },
      {
        id: 'ac-1',
        requirement: 'C',
        acceptance: 'D',
        evidence: '',
        state: 'unverified',
      },
    ];
    expect(validateContent(c)).toContain('unique');
    expect(() => inspectImport('{"kind":"random","schemaVersion":1}')).toThrow(
      'portable agent or studio document',
    );
  });
  it('prefers exact phase and distinguishes a missing route or absent evidence', () => {
    const rules = [
      {
        phase: '*',
        task: 'search',
        mode: 'assisted' as const,
        engine: 'general',
        fallback: '',
        ceiling: 1,
      },
      {
        phase: 'review',
        task: '*',
        mode: 'deterministic' as const,
        engine: 'lint',
        fallback: '',
        ceiling: 0,
      },
    ];
    expect(matchRoute(rules, 'review', 'search')?.engine).toBe('lint');
    expect(matchRoute(rules, 'deploy', 'build')).toBeUndefined();
    const h = harness();
    expect(buildJourney(h.snapshot, 'Report', ['ledger'], undefined)).toContain(
      'Ledger was unavailable',
    );
  });
});

describe('Review freshness and source integrity', () => {
  it('requires another review if target agent instructions change during application', () => {
    const h = harness([
      doc('instruction', 'Team rules', { content: 'Write meaningful tests.' }),
    ]);
    const view = render(
      <OrganizationStudio view="instructions" {...h.props} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Team rules' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Review agent application' }),
    );
    fireEvent.change(screen.getByLabelText('Target agent'), {
      target: { value: 'atlas' },
    });
    fireEvent.click(
      screen.getByLabelText('I reviewed the instruction changes for Atlas'),
    );
    expect(
      screen.getByRole('button', { name: 'Apply reviewed version' }),
    ).toBeEnabled();
    view.rerender(
      <OrganizationStudio
        view="instructions"
        {...h.props}
        controller={{
          ...h.props.controller,
          snapshot: {
            ...h.snapshot,
            agents: [
              { ...agent, instructions: 'New guidance from another editor.' },
            ],
          },
        }}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Apply reviewed version' }),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('I reviewed the instruction changes for Atlas'),
    ).not.toBeChecked();
    expect(h.execute).not.toHaveBeenCalled();
  });
  it('requires another revision review when the current document version changes', () => {
    const current = doc('instruction', 'Team rules', { content: 'Current.' });
    const older = doc(
      'instruction',
      'Team rules',
      { content: 'Previous.' },
      { version: 1 },
    );
    const h = harness([current], { documentRevisions: [older] });
    const view = render(
      <OrganizationStudio view="instructions" {...h.props} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Team rules' }));
    fireEvent.click(
      screen.getByText('Revision history · 1 retained revisions'),
    );
    fireEvent.change(screen.getByLabelText('Saved revision'), {
      target: { value: '1' },
    });
    fireEvent.click(
      screen.getByLabelText('I reviewed the revision to restore'),
    );
    expect(
      screen.getByRole('button', { name: 'Restore as new version' }),
    ).toBeEnabled();
    view.rerender(
      <OrganizationStudio
        view="instructions"
        {...h.props}
        controller={{
          ...h.props.controller,
          snapshot: { ...h.snapshot, documents: [{ ...current, version: 3 }] },
        }}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Restore as new version' }),
    ).toBeDisabled();
    expect(h.execute).not.toHaveBeenCalled();
  });
  it('saves the snapshot revision used to generate the report preview', async () => {
    const h = harness();
    const view = render(<OrganizationStudio view="reports" {...h.props} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Build journey report' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Generate report preview' }),
    );
    view.rerender(
      <OrganizationStudio
        view="reports"
        {...h.props}
        controller={{
          ...h.props.controller,
          snapshot: { ...h.snapshot, revision: 5, deliverables: [] },
        }}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Save report to workspace' }),
    );
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    const [, params] = h.execute.mock.calls[0] as unknown as [
      string,
      { document: StudioDocument },
    ];
    expect(parseContent(params.document).fields.summary).toContain(
      'revision 1; 1 deliverables',
    );
    expect(parseContent(params.document).fields.content).toContain(
      'Snapshot revision: 1',
    );
  });
  it('validates frontmatter fields and distinct connector destinations', () => {
    const skill = emptyContent('skill');
    skill.fields.content =
      '---\nversion: 1\n---\nname: misleading\ndescription: outside frontmatter';
    expect(validateContent(skill)).toContain('frontmatter');
    skill.fields.content =
      '---\nname: a\ndescription: A\n---\nReview the changes.';
    expect(validateContent(skill)).toBeUndefined();
    const connector = emptyContent('connector');
    connector.fields.endpoint = 'https://example.com';
    connector.fields.project = 'DEMO';
    connector.fields.bodyField = connector.fields.titleField;
    expect(validateContent(connector)).toContain(
      'different destination fields',
    );
  });
});
