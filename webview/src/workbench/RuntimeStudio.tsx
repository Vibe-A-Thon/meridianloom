import { useState } from 'react';
import { useRpcQuery } from '../hooks/useRpcQuery';
import type { WorkbenchExecute } from '../../../shared/ts/workbench';
import { ErrorState, LoadingState } from '../components/AsyncState';
import type { ScreenProps } from '../screens/registry';
import type { WorkbenchController } from './useWorkbench';
import { Icon } from './Icon';
import s from './workbench.module.css';
export function RuntimeStudio({
  client,
  ready,
  workspaceDir,
  enabledTiers,
  controller,
}: ScreenProps & { controller: WorkbenchController }) {
  const [diagnose, setDiagnose] = useState(false);
  const [loopId, setLoopId] = useState('');
  const [storyId, setStoryId] = useState('');
  const [loopKind, setLoopKind] = useState('L2-task');
  const [loopResult, setLoopResult] = useState<Record<string, unknown> | null>(null);
  const [loopError, setLoopError] = useState<string | null>(null);
  const [loopBusy, setLoopBusy] = useState(false);

  // FR-M4: the loop surfaces dispatch through the governor/orchestra tiers
  // (shared/schema/tiers.json). Every action is ledger-recorded; replay
  // overrides are the FR-M4-07 modified-state fork.
  async function runLoopAction(action: 'start' | 'status' | 'stop' | 'resume' | 'replay', execute: WorkbenchExecute) {
    setLoopError(null);
    setLoopBusy(true);
    try {
      const id = loopId.trim();
      if (!id) {
        setLoopError('A loop id is required.');
        return;
      }
      // Narrowed per action: the action map types each params shape.
      let result: unknown;
      if (action === 'start') {
        result = await execute('loop.start', {
          loopId: id,
          storyId: storyId.trim(),
          kind: loopKind as 'L1-micro' | 'L2-task' | 'L3-phase' | 'L4-delivery' | 'L5-learning' | 'L6-organisation',
        });
      } else if (action === 'status') {
        result = await execute('loop.status', { loopId: id });
      } else if (action === 'stop') {
        result = await execute('loop.stop', { loopId: id, reason: 'operator' });
      } else if (action === 'resume') {
        result = await execute('loop.resume', { loopId: id });
      } else {
        let stateOverrides: Record<string, unknown>;
        try {
          stateOverrides = JSON.parse(
            (document.getElementById('loop-replay-overrides') as HTMLTextAreaElement | null)?.value || '{}',
          ) as Record<string, unknown>;
        } catch {
          setLoopError('Replay overrides must be valid JSON.');
          return;
        }
        result = await execute('loop.replay', { loopId: id, stateOverrides });
      }
      setLoopResult(result as Record<string, unknown>);
    } catch (error) {
      setLoopError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoopBusy(false);
    }
  }

  const health = useRpcQuery(ready ? client : undefined, 'health', {});
  const doctor = useRpcQuery(
    ready ? client : undefined,
    'doctor/run',
    { ...(workspaceDir ? { workspaceDir } : {}) },
    diagnose,
  );
  const capabilities = controller.snapshot?.capabilities;
  return (
    <div className={s.page}>
      <header className={s.pageHeading}>
        <div>
          <p className={s.eyebrow}>SYSTEM / RUNTIME</p>
          <h1>Know where things stand.</h1>
          <p>Actual connection health, execution readiness, and actionable diagnostics.</p>
        </div>
        <button
          className={s.primary}
          disabled={!ready || (diagnose && doctor.status === 'loading')}
          onClick={() => {
            if (diagnose) doctor.refresh();
            else setDiagnose(true);
          }}
        >
          <Icon name="runtime" size={16} />{' '}
          {diagnose && doctor.status === 'loading' ? 'Checking…' : 'Run diagnostics'}
        </button>
      </header>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Execution readiness</h2>
          <button
            className={s.textButton}
            onClick={() => {
              health.refresh();
              void controller.refresh();
            }}
          >
            Refresh <Icon name="arrow" size={14} />
          </button>
        </div>
        {[
          [
            'Workspace',
            capabilities?.workspaceOpen,
            workspaceDir ?? 'Open a folder to persist workbench state.',
          ],
          [
            'Workspace trust',
            capabilities?.trusted,
            capabilities?.trusted
              ? 'VS Code workspace trust is granted.'
              : 'Configured executables require a trusted workspace.',
          ],
          [
            'Governor tier',
            capabilities?.governorEnabled,
            `Enabled tiers: ${enabledTiers.join(', ') || 'waiting for host'}`,
          ],
          [
            'ACP execution',
            capabilities?.executionReady,
            capabilities?.executionBlockedReason ??
              (capabilities
                ? 'Explicit runs can begin. Workspace policy and tool approval apply.'
                : 'Waiting for workspace state.'),
          ],
        ].map(([label, pass, detail]) => (
          <div className={s.checkRow} key={String(label)} data-state={pass ? 'pass' : 'warn'}>
            <Icon name={pass ? 'check' : 'runtime'} size={18} />
            <div>
              <strong>{String(label)}</strong>
              <p>{String(detail)}</p>
            </div>
            <span className={s.statusBadge}>
              {pass === undefined ? 'Unknown' : pass ? 'Ready' : 'Required'}
            </span>
          </div>
        ))}
      </section>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Sidecar health</h2>
        </div>
        {health.status === 'error' ? (
          <ErrorState error={health.error} onRetry={health.refresh} />
        ) : health.status === 'loading' ? (
          <LoadingState label="Checking runtime health…" />
        ) : (
          <div className={s.settingRow}>
            <div>
              <h3>{health.data.status === 'ok' ? 'Responding normally' : health.data.status}</h3>
              <p>
                Process {health.data.pid} · {Math.floor(health.data.uptimeSeconds)} seconds uptime ·{' '}
                {health.data.activeLoops} active loops
              </p>
            </div>
            <span className={s.statusBadge}>{health.data.status}</span>
          </div>
        )}
      </section>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Loop control</h2>
          <span className={s.statusBadge}>Orchestra tier</span>
        </div>
        <div className={s.settingRow}>
          <label className={s.field}>
            <span className={s.fieldLabel}>Loop id</span>
            <input
              value={loopId}
              onChange={(e) => setLoopId(e.target.value)}
              placeholder="L-task-1"
              disabled={!ready || loopBusy}
            />
          </label>
          <label className={s.field}>
            <span className={s.fieldLabel}>Story id (start)</span>
            <input
              value={storyId}
              onChange={(e) => setStoryId(e.target.value)}
              placeholder="EDB-12345"
              disabled={!ready || loopBusy}
            />
          </label>
          <label className={s.field}>
            <span className={s.fieldLabel}>Kind</span>
            <select
              value={loopKind}
              onChange={(e) => setLoopKind(e.target.value)}
              disabled={!ready || loopBusy}
            >
              {['L1-micro', 'L2-task', 'L3-phase', 'L4-delivery', 'L5-learning', 'L6-organisation'].map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </label>
        </div>
        <div className={s.buttonRow}>
          {(['start', 'status', 'stop', 'resume', 'replay'] as const).map((action) => (
            <button
              key={action}
              className={action === 'start' ? s.primary : s.textButton}
              disabled={!ready || loopBusy}
              onClick={() => void runLoopAction(action, controller.execute)}
            >
              {action === 'start' ? 'Start' : action === 'status' ? 'Status' : action === 'stop' ? 'Stop' : action === 'resume' ? 'Resume at gate' : 'Replay with overrides'}
            </button>
          ))}
        </div>
        <label className={s.field}>
          <span className={s.fieldLabel}>Replay overrides (JSON)</span>
          <textarea
            id="loop-replay-overrides"
            rows={3}
            placeholder='{"approved": true}'
            disabled={!ready || loopBusy}
          />
        </label>
        {loopError ? <p role="alert">{loopError}</p> : null}
        {loopResult ? (
          <pre data-testid="loop-result">{JSON.stringify(loopResult, null, 2)}</pre>
        ) : null}
      </section>
      {diagnose && (
        <section className={s.panel}>
          <div className={s.panelHeader}>
            <h2>Diagnostic report</h2>
          </div>
          {doctor.status === 'loading' ? (
            <LoadingState label="Running diagnostic checks…" />
          ) : doctor.status === 'error' ? (
            <ErrorState error={doctor.error} onRetry={doctor.refresh} />
          ) : (
            doctor.data.checks.map((check) => (
              <div className={s.checkRow} key={check.id} data-state={check.status}>
                <Icon name={check.status === 'pass' ? 'check' : 'runtime'} size={18} />
                <div>
                  <strong>{check.name}</strong>
                  <p>{check.detail}</p>
                  {check.remediation && <p>{check.remediation}</p>}
                </div>
                <span className={s.statusBadge}>{check.status}</span>
              </div>
            ))
          )}
        </section>
      )}
    </div>
  );
}
