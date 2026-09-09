import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  WorkbenchAgent,
  WorkbenchExecute,
  WorkbenchSnapshot,
} from '../../../shared/ts/workbench';
import { AgentStudio } from './AgentStudio';
import { LearningStudio } from './LearningStudio';
import { DeliveryStudio } from './DeliveryStudio';
import { GuideStudio, SURFACE_COVERAGE } from './GuideStudio';
import type { WorkbenchController } from './useWorkbench';

const agent: WorkbenchAgent = {
  id: 'atlas',
  name: 'Atlas',
  role: 'Developer',
  description: 'Portable ACP agent',
  vendor: 'Custom',
  version: '1.0.0',
  command: 'atlas-acp',
  args: ['--stdio'],
  instructions: 'Explain verification.',
  permissions: ['read'],
  trainable: ['memory'],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
  mode: 'active',
  runtime: 'idle',
  learningState: 'waiting',
  createdAt: '2026-09-08T00:00:00Z',
  updatedAt: '2026-09-08T00:00:00Z',
};
function controller(overrides: Partial<WorkbenchSnapshot> = {}) {
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    skills: [],
    instructions: [],
    integrations: [],
    agents: [agent],
    deliverables: [],
    runs: [],
    learning: [],
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: true,
      executionReady: true,
    },
    ...overrides,
  };
  const execute = vi.fn(async () => snapshot);
  return {
    controller: {
      snapshot,
      execute: execute as WorkbenchExecute,
      busy: false,
      error: null,
      refresh: async () => {},
    } satisfies WorkbenchController,
    execute,
  };
}

describe('Agent studio', () => {
  it('sends a validated portable profile from the add form without activation or execution', async () => {
    const h = controller();
    render(<AgentStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Add agent' }));
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'Sage' } });
    fireEvent.change(screen.getByLabelText('Executable', { exact: false }), {
      target: { value: 'sage-acp' },
    });
    fireEvent.change(screen.getByLabelText('Arguments (JSON array)', { exact: false }), {
      target: { value: '["--stdio"]' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create agent' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledTimes(1));
    expect(h.execute).toHaveBeenCalledWith('agent/save', {
      agent: expect.objectContaining({
        id: 'sage',
        name: 'Sage',
        command: 'sage-acp',
        args: ['--stdio'],
        trainable: ['memory'],
      }),
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
  it('invalid argument JSON stays in the form and never crosses the host boundary', async () => {
    const h = controller();
    render(<AgentStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Add agent' }));
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'Sage' } });
    fireEvent.change(screen.getByLabelText('Executable', { exact: false }), {
      target: { value: 'sage-acp' },
    });
    fireEvent.change(screen.getByLabelText('Arguments (JSON array)', { exact: false }), {
      target: { value: '{"secret":"oops"}' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create agent' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('array of strings');
    expect(h.execute).not.toHaveBeenCalled();
  });
  it('deactivation requests Learning mode, and host results update the status', async () => {
    const h = controller();
    const view = render(<AgentStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate Atlas' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('agent/mode', { id: 'atlas', mode: 'learning' }),
    );
    view.rerender(
      <AgentStudio
        controller={{
          ...h.controller,
          snapshot: { ...h.controller.snapshot!, agents: [{ ...agent, mode: 'learning' }] },
        }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Activate Atlas' })).toBeInTheDocument();
    expect(screen.getByText('Waiting for reviewed feedback')).toBeInTheDocument();
  });
  it('edits an existing identity and requires a concrete removal dialog', async () => {
    const h = controller();
    render(<AgentStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Atlas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Edit agent' }));
    expect(screen.getByLabelText('Portable ID')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'Atlas 2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('agent/save', {
        agent: expect.objectContaining({ id: 'atlas', name: 'Atlas 2' }),
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Atlas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Remove Atlas?');
    expect(h.execute).not.toHaveBeenCalledWith('agent/remove', expect.anything());
    fireEvent.click(screen.getByRole('button', { name: 'Remove agent' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('agent/remove', { id: 'atlas' }));
  });
  it('keeps host failures visible in the add form', async () => {
    const h = controller();
    h.execute.mockRejectedValue(new Error('State could not be saved.'));
    render(<AgentStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Add agent' }));
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'Sage' } });
    fireEvent.change(screen.getByLabelText('Executable', { exact: false }), {
      target: { value: 'sage-acp' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create agent' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('State could not be saved.');
    expect(screen.getByLabelText('Agent name')).toHaveValue('Sage');
  });
});
describe('Delivery and Learning studios', () => {
  it('draft creation does not dispatch and shows only the active roster', async () => {
    const h = controller({
      agents: [agent, { ...agent, id: 'sage', name: 'Sage', mode: 'learning' }],
    });
    render(<DeliveryStudio controller={h.controller} />);
    expect(screen.getByText('1 active agents in your delivery team')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'New deliverable' }));
    fireEvent.change(screen.getByLabelText('Deliverable title'), {
      target: { value: 'Accessible dialog' },
    });
    fireEvent.change(screen.getByLabelText('Brief and acceptance criteria'), {
      target: { value: 'Verify focus restoration.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('deliverable/save', {
        title: 'Accessible dialog',
        brief: 'Verify focus restoration.',
      }),
    );
    expect(h.execute).toHaveBeenCalledTimes(1);
  });
  it('dispatch is disabled when execution is unavailable, with the reason shown', () => {
    const h = controller({
      capabilities: {
        workspaceOpen: true,
        trusted: false,
        governorEnabled: true,
        executionReady: false,
        executionBlockedReason: 'Trust the workspace first.',
      },
      deliverables: [
        {
          id: 'brief-1',
          title: 'Test brief',
          brief: 'Do the work.',
          state: 'draft',
          agentIds: [],
          createdAt: agent.createdAt,
          updatedAt: agent.updatedAt,
        },
      ],
    });
    render(<DeliveryStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: /Test brief/ }));
    expect(screen.getByRole('button', { name: 'Dispatch active team' })).toBeDisabled();
    expect(screen.getByText('Trust the workspace first.')).toBeInTheDocument();
  });
  it('learning review states its source and only sends the explicit accept decision', async () => {
    const h = controller({
      agents: [{ ...agent, mode: 'learning', learningState: 'review' }],
      learning: [
        {
          id: 'note-1',
          agentId: 'atlas',
          deliverableId: 'brief-1',
          title: 'Remember focus',
          content: 'Return focus after closing.',
          state: 'pending',
          createdAt: agent.createdAt,
          surface: 'memory',
        },
      ],
    });
    render(<LearningStudio controller={h.controller} />);
    fireEvent.click(screen.getByRole('button', { name: 'Review note' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('brief-1');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept memory' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('learning/review', {
        id: 'note-1',
        decision: 'accepted',
      }),
    );
  });
  it('connects all 51 catalogued surfaces to a dedicated interface', () => {
    expect(SURFACE_COVERAGE.map(([id]) => id)).toEqual(Array.from({ length: 51 }, (_, i) => i + 1));
    render(<GuideStudio onNavigate={() => {}} />);
    fireEvent.change(screen.getByLabelText('Search capability coverage'), {
      target: { value: 'UML Studio' },
    });
    expect(screen.queryByText('Pending')).toBeNull();
    expect(screen.getByRole('button', { name: 'Explore' })).toBeInTheDocument();
  });
});
