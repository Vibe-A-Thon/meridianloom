/**
 * Loop control panel (audit TASK-301, GUI half): the Runtime Studio drives
 * the FR-M4 loop surfaces through the workbench controller, which the host
 * passes through to the sidecar. These tests assert the exact RPC names
 * and params and the result/error rendering.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  WorkbenchExecute,
  WorkbenchSnapshot,
} from '../../../shared/ts/workbench';
import { WebviewRpcClient } from '../rpc/client';
import { makeHost } from '../test/host-harness';
import { RuntimeStudio } from './RuntimeStudio';
import type { WorkbenchController } from './useWorkbench';

function controller(execute: WorkbenchExecute) {
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    skills: [],
    instructions: [],
    integrations: [],
    agents: [],
    deliverables: [],
    runs: [],
    learning: [],
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: true,
      executionReady: true,
    },
  };
  return {
    snapshot,
    execute,
    busy: false,
    error: null,
    refresh: async () => {},
  } satisfies WorkbenchController;
}

function mount(execute: WorkbenchExecute) {
  const host = makeHost({ health: { status: 'ok', pid: 1, uptimeSeconds: 2, activeLoops: 0 } });
  const client = new WebviewRpcClient(host.transport);
  const c = controller(execute);
  const view = render(
    <RuntimeStudio
      client={client}
      ready
      workspaceDir="/repo/ws"
      enabledTiers={['flight-recorder', 'governor', 'orchestra']}
      sessions={{
        status: 'ready',
        data: { sessions: [], warnings: [] },
        error: undefined,
        refresh: () => {},
      }}
      controller={c}
    />,
  );
  return { host, view, execute };
}

describe('RuntimeStudio loop control (FR-M4)', () => {
  it('start calls loop.start with the exact params and renders the result', async () => {
    const execute = vi.fn(async () => ({ runId: 'r1', status: 'completed', iterations: 2, checkpointed: true }));
    const h = mount(execute as WorkbenchExecute);
    fireEvent.change(screen.getByLabelText('Loop id'), { target: { value: 'L-task-1' } });
    fireEvent.change(screen.getByLabelText('Story id (start)'), { target: { value: 'EDB-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('loop.start', {
      loopId: 'L-task-1',
      storyId: 'EDB-1',
      kind: 'L2-task',
    }));
    await waitFor(() =>
      expect(screen.getByTestId('loop-result').textContent).toContain('completed'),
    );
  });

  it('status/stop/resume dispatch their RPCs', async () => {
    const execute = vi.fn(async (method: string) =>
      method === 'loop.status'
        ? { loopId: 'L-task-1', kind: 'L2-task', state: 'completed', iteration: 2 }
        : method === 'loop.stop'
          ? { stopped: true, was: 'completed' }
          : { status: 'completed', iteration: 2 },
    );
    const h = mount(execute as unknown as WorkbenchExecute);
    fireEvent.change(screen.getByLabelText('Loop id'), { target: { value: 'L-task-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Status' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('loop.status', { loopId: 'L-task-1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('loop.stop', { loopId: 'L-task-1', reason: 'operator' }));
    fireEvent.click(screen.getByRole('button', { name: 'Resume at gate' }));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith('loop.resume', { loopId: 'L-task-1' }));
  });

  it('replay parses JSON overrides and calls loop.replay; invalid JSON shows the error', async () => {
    const execute = vi.fn(async () => ({ forkRunId: 'fork-1', status: 'completed' }));
    const h = mount(execute as WorkbenchExecute);
    fireEvent.change(screen.getByLabelText('Loop id'), { target: { value: 'L-task-1' } });
    fireEvent.change(screen.getByLabelText('Replay overrides (JSON)'), {
      target: { value: '{"approved": true}' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Replay with overrides' }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith('loop.replay', {
        loopId: 'L-task-1',
        stateOverrides: { approved: true },
      }),
    );

    fireEvent.change(screen.getByLabelText('Replay overrides (JSON)'), {
      target: { value: '{not json' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Replay with overrides' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('valid JSON'));
  });

  it('a missing loop id refuses client-side before any RPC', async () => {
    const execute = vi.fn(async () => ({}));
    mount(execute as WorkbenchExecute);
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('loop id'));
    expect(execute).not.toHaveBeenCalled();
  });
});
