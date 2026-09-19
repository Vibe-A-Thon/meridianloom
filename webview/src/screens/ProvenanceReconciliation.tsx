import { useState } from 'react';
import type { InteropNotesExport } from '../../../shared/ts/bus-types';
import { getVsCodeApi } from '../host/vscode-api';
import { RpcError, type WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import { InteropPanel } from './InteropPanel';
import styles from './interop-panel.module.css';

/**
 * 10.54 Provenance Reconciliation — `M52`, `FR-M52-04`/`05`, `AC-60` (CP1-T04).
 *
 * The fuller view the MVP deferred. It shows every provenance record in this
 * repository, whether each is notarised and unchanged, where two records
 * disagree about who produced a commit, and Meridian's own attribution in
 * formats other tools read.
 *
 * The records half is `InteropPanel`, the same component the Ledger screen
 * carries for `MVP-R7.1`. Two copies of that surface would drift, and the one
 * that drifted would be the one saying something false about somebody else's
 * record.
 *
 * The export half keeps one rule: nothing is written into the repository
 * unless the person asks, knowing what will be written and where. A download
 * writes nothing. Notes are planned first; writing them needs a confirmation
 * that names the ref and the count.
 */

export interface ProvenanceReconciliationProps {
  client: WebviewRpcClient;
  ready: boolean;
}

function describe(error: unknown): string {
  if (error instanceof RpcError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function ProvenanceReconciliation({ client, ready }: ProvenanceReconciliationProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [downloaded, setDownloaded] = useState<string | undefined>();
  const [plan, setPlan] = useState<InteropNotesExport | undefined>();
  const [confirmed, setConfirmed] = useState(false);
  const [written, setWritten] = useState<string | undefined>();

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setBusy(false);
    }
  }

  const download = () =>
    run(async () => {
      const result = await client.request('interop/export', { format: 'attribution-json' });
      const document = result.document ?? {};
      getVsCodeApi().postMessage({
        type: 'download',
        fileName: 'meridian-attribution-export.json',
        mimeType: 'application/json',
        content: JSON.stringify(document, null, 2),
      });
      const totals = ((document as { totals?: Record<string, number> }).totals ?? {});
      setDownloaded(
        `Exported ${totals.agent ?? 0} agent, ${totals.human ?? 0} human and ` +
          `${totals.unattributed ?? 0} unattributed line(s). Nothing was written to the repository.`,
      );
    });

  const planNotes = () =>
    run(async () => {
      const result = await client.request('interop/export', { format: 'git-notes' });
      setPlan(result.notes);
      setConfirmed(false);
      setWritten(undefined);
    });

  const writeNotes = () =>
    run(async () => {
      if (!confirmed) return;
      const result = await client.request('interop/export', { format: 'git-notes', write: true });
      const notes = result.notes;
      setPlan(notes);
      setConfirmed(false);
      if (notes) {
        setWritten(
          `Wrote ${notes.written} note(s) under ${notes.ref}; ${notes.unchanged} already said the same thing.`,
        );
      }
    });

  return (
    <section aria-label="Provenance reconciliation" data-testid="provenance-reconciliation">
      <InteropPanel client={client} ready={ready} />

      <section className={styles.panel} aria-label="Export for other tools">
        <header className={styles.head}>
          <h2>Export for other tools</h2>
          <p className={styles.muted}>
            Meridian&apos;s attribution, readable without Meridian. It is not another tool&apos;s
            format, and where another record disagrees about a commit, the disagreement travels
            with the export, unresolved.
          </p>
        </header>

        <div className={styles.actions}>
          <button
            disabled={!ready || busy}
            onClick={() => void download()}
            data-testid="reconciliation-download"
          >
            Download the attribution export
          </button>
          <button
            disabled={!ready || busy}
            onClick={() => void planNotes()}
            data-testid="reconciliation-plan-notes"
          >
            Plan git notes
          </button>
        </div>

        {error && (
          <p className={styles.error} role="alert" data-testid="reconciliation-error">
            {error}
          </p>
        )}
        {downloaded && (
          <p className={styles.muted} data-testid="reconciliation-downloaded">
            {downloaded}
          </p>
        )}

        {plan && (
          <div data-testid="reconciliation-plan">
            <p className={styles.muted}>
              {`${plan.toWrite} note(s) would be written under ${toSafeText(plan.ref)}; ${plan.unchanged} already say the same thing.`}
              {plan.truncated ? ' Only the most recent commits were considered.' : ''}
            </p>
            {plan.toWrite > 0 && (
              <div className={styles.actions}>
                <label>
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                    data-testid="reconciliation-confirm"
                  />{' '}
                  {`I understand this writes ${plan.toWrite} note(s) under ${toSafeText(plan.ref)} in this repository.`}
                </label>
                <button
                  disabled={!ready || busy || !confirmed}
                  onClick={() => void writeNotes()}
                  data-testid="reconciliation-write-notes"
                >
                  Write the notes
                </button>
              </div>
            )}
          </div>
        )}
        {written && (
          <p className={styles.muted} data-testid="reconciliation-written">
            {written}
          </p>
        )}
      </section>
    </section>
  );
}
