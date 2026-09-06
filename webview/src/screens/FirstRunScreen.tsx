import { useState } from 'react';
import type { LedgerExportBundleResult } from '../../../shared/ts/bus-types';
import { ExportPanel } from '../components/ExportPanel';
import { vendorLabel } from '../components/vendors';
import type { RpcQueryState } from '../hooks/useRpcQuery';
import type { WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './first-run-screen.module.css';

/**
 * 10.40 First-Run, rewritten for Flight Recorder (gaps_guix §4 amendment):
 * connect a repository → run your existing agent → see the Weave → export
 * a bundle. Four steps, no credential, no Meridian agent, no mock data —
 * every step state is computed from real RPC results (banned 32). Step 2
 * completes when observe/sessions actually reports a session (X-29); step
 * 3 when the ledger holds entries; step 4 only when a signed bundle
 * export really succeeded. Empty states are honest copy, not fake rows.
 */

export interface FirstRunProps {
  client: WebviewRpcClient;
  ready: boolean;
  workspaceDir: string | undefined;
  sessions: RpcQueryState<'observe/sessions'>;
  ledgerTip: RpcQueryState<'ledger.query'>;
}

type StepState = 'done' | 'current' | 'waiting';

export function FirstRunScreen({
  client,
  ready,
  workspaceDir,
  sessions,
  ledgerTip,
}: FirstRunProps) {
  const [exported, setExported] = useState<LedgerExportBundleResult | null>(null);

  const sessionCount = sessions.status === 'ready' ? sessions.data.sessions.length : 0;
  const firstVendor = sessions.status === 'ready' ? sessions.data.sessions[0]?.vendor : undefined;
  const entryCount = ledgerTip.status === 'ready' ? ledgerTip.data.entries.length : 0;

  const steps: Array<{ title: string; state: StepState; detail: string }> = [
    {
      title: 'Connect a repository',
      state: workspaceDir ? 'done' : 'current',
      detail: workspaceDir
        ? `Watching ${toSafeText(workspaceDir)}`
        : 'Open a folder in this window — the recorder watches that repository.',
    },
    {
      title: 'Run your existing agent',
      state: workspaceDir ? (sessionCount > 0 ? 'done' : 'current') : 'waiting',
      detail:
        sessionCount > 0
          ? `${vendorLabel(firstVendor ?? 'unknown')} observed · ` +
            `${sessions.status === 'ready' ? sessions.data.sessions[0]?.source ?? '' : ''} — recording, no credential given`
          : 'Run Claude Code, Cursor or Copilot in this workspace. Meridian records what it does — no model credential, no Meridian agent.',
    },
    {
      title: 'See the Weave',
      state: entryCount > 0 ? 'done' : sessionCount > 0 ? 'current' : 'waiting',
      detail:
        entryCount > 0
          ? `${entryCount} recorded ${entryCount === 1 ? 'pass' : 'passes'} in the cloth`
          : 'Passes appear here as recorded work lands — commits with provenance trailers, ledger entries.',
    },
    {
      title: 'Export a bundle',
      state: exported ? 'done' : workspaceDir ? 'current' : 'waiting',
      detail: exported
        ? `Bundle signed · ${exported.entries.length} ${exported.entries.length === 1 ? 'entry' : 'entries'} · verifies without Meridian installed`
        : 'A signed audit bundle — proof that survives Meridian being uninstalled.',
    },
  ];

  return (
    <div className={styles.screen} data-testid="first-run">
      <section aria-labelledby="first-run-heading" className={styles.intro}>
        <h2 className={styles.heading} id="first-run-heading">
          Start recording in four steps
        </h2>
        <p className={styles.copy}>
          Meridian Loom is a flight recorder for the agents you already run. It observes, records
          and proves — it never needs a model credential and never runs an agent of its own.
        </p>
      </section>

      <ol className={styles.steps}>
        {steps.map((step) => (
          <li
            key={step.title}
            className={`${styles.step} ${styles[step.state]}`}
            data-step-state={step.state}
          >
            <span className={styles.stepMark} aria-hidden="true">
              {step.state === 'done' ? '✓' : step.state === 'current' ? '●' : '○'}
            </span>
            <div className={styles.stepBody}>
              <h3 className={styles.stepTitle}>{step.title}</h3>
              <p className={styles.stepDetail}>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>

      {workspaceDir && !exported && (
        <div className={styles.exportArea}>
          <ExportPanel client={client} ready={ready} onExported={setExported} />
        </div>
      )}
    </div>
  );
}
