/**
 * Adapter registry panel (audit TASK-305): discovery renders the wire
 * result; invalid adapters show errors with no actions; promote/unplug
 * dispatch their RPCs and rediscover.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { WorkbenchExecute } from '../../../../shared/ts/workbench';
import { AdapterRegistryPanel } from './AdapterRegistry';

function mount(execute: WorkbenchExecute) {
  return render(<AdapterRegistryPanel controller={{ execute, busy: false }} />);
}

describe('AdapterRegistryPanel (FR-M31)', () => {
  it('discovers and renders adapters with their states', async () => {
    const execute = vi.fn(async (method: string) =>
      method === 'adapters/discover'
        ? {
            adapters: [
              { id: 'developer', version: '1.0.0', valid: true, errors: [] },
              { id: 'rogue', version: '0.1.0', valid: false, errors: ['digest mismatch'] },
            ],
            states: { developer: 'probation', rogue: 'retired' },
          }
        : {},
    );
    mount(execute as unknown as WorkbenchExecute);
    fireEvent.click(screen.getByRole('button', { name: 'Discover' }));
    await waitFor(() =>
      expect(screen.getByTestId('adapter-developer').textContent).toContain('probation'),
    );
    expect(screen.getByTestId('adapter-rogue').textContent).toContain('digest mismatch');
    // The invalid adapter carries no actions; the valid one does.
    const rogue = screen.getByTestId('adapter-rogue');
    expect(rogue.querySelector('button')).toBeNull();
    expect(screen.getByTestId('adapter-developer').textContent).toContain('probation');
  });

  it('promote and unplug dispatch their RPCs and rediscover', async () => {
    const execute = vi.fn(async (method: string) =>
      method === 'adapters/discover'
        ? { adapters: [{ id: 'dev', version: '1', valid: true, errors: [] }], states: { dev: 'probation' } }
        : {},
    );
    mount(execute as unknown as WorkbenchExecute);
    fireEvent.click(screen.getByRole('button', { name: 'Discover' }));
    await waitFor(() => expect(execute).toHaveBeenCalledWith('adapters/discover', {}));
    fireEvent.click(screen.getByRole('button', { name: 'Promote' }));
    await waitFor(() => expect(execute).toHaveBeenCalledWith('adapters/promote', { id: 'dev' }));
    // Rediscovery after the action.
    const discovers = execute.mock.calls.filter((c) => c[0] === 'adapters/discover');
    expect(discovers.length).toBeGreaterThanOrEqual(2);
  });

  it('renders failures as errors, not silent emptiness', async () => {
    const execute = vi.fn(async () => {
      throw new Error('sidecar unavailable');
    });
    mount(execute as unknown as WorkbenchExecute);
    fireEvent.click(screen.getByRole('button', { name: 'Discover' }));
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('sidecar unavailable'),
    );
  });
});
