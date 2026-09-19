/**
 * Adapter registry panel (audit TASK-305): discovery, hot-plug actions,
 * and probation promotion for the sidecar's adapter registry (FR-M31).
 * Fetches only when asked; renders errors as errors; every action is a
 * pass-through to the sidecar, which records evidence.
 */

import { useState } from 'react';
import type { WorkbenchExecute } from '../../../../shared/ts/workbench';
import s from './operations.module.css';

interface AdapterWire {
  id: string;
  version: string;
  valid: boolean;
  errors: string[];
}

export function AdapterRegistryPanel({ controller }: { controller: { execute: WorkbenchExecute; busy: boolean } }) {
  const [adapters, setAdapters] = useState<AdapterWire[] | undefined>();
  const [states, setStates] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError(undefined);
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function discover() {
    const result = await run(() =>
      controller.execute('adapters/discover', {}) as Promise<{ adapters: AdapterWire[]; states: Record<string, string> }>,
    );
    if (result) {
      setAdapters(result.adapters);
      setStates(result.states);
    }
  }

  async function act(
    method: 'adapters/plug' | 'adapters/unplug' | 'adapters/promote',
    params: { folder: string } | { id: string; inflight?: Record<string, unknown> } | { id: string },
  ) {
    const ok = await run(() => controller.execute(method, params));
    if (ok !== undefined) await discover();
  }

  return (
    <section className={s.panel}>
      <div className={s.panelHeader}>
        <h2>Adapter registry</h2>
        <button className={s.textButton} disabled={controller.busy || busy} onClick={() => void discover()}>
          Discover
        </button>
      </div>
      <p>
        Hot-plugged adapters the sidecar discovered (FR-M31). Invalid adapters are
        listed with their errors and never loaded.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {adapters === undefined ? (
        <p>Nothing discovered yet — press Discover.</p>
      ) : adapters.length === 0 ? (
        <p>No adapters found in the configured roots.</p>
      ) : (
        <ul>
          {adapters.map((adapter) => (
            <li key={adapter.id} data-testid={`adapter-${adapter.id}`}>
              <strong>{adapter.id}</strong> v{adapter.version} ·{' '}
              <span>{states[adapter.id] ?? 'unknown'}</span>
              {!adapter.valid ? (
                <ul>
                  {adapter.errors.map((e) => (
                    <li key={e} role="alert">{e}</li>
                  ))}
                </ul>
              ) : (
                <span>
                  {' '}
                  {states[adapter.id] === 'probation' ? (
                    <button
                      disabled={controller.busy || busy}
                      onClick={() => void act('adapters/promote', { id: adapter.id })}
                    >
                      Promote
                    </button>
                  ) : null}{' '}
                  {states[adapter.id] !== 'retired' ? (
                    <button
                      disabled={controller.busy || busy}
                      onClick={() => void act('adapters/unplug', { id: adapter.id })}
                    >
                      Unplug
                    </button>
                  ) : null}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
