import { useState } from 'react';
import type { LedgerExportBundleResult } from '../../../shared/ts/bus-types';
import { ErrorState, LoadingState } from './AsyncState';
import type { WebviewRpcClient } from '../rpc/client';
import { RpcError } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './export-panel.module.css';

/**
 * 10.45/10.7 Export (FR-M36-04): a signed audit bundle for a sequence
 * range. The webview cannot write files (VIGUIX_Final §17) — the bundle
 * JSON crosses the bus as a `download` message and the extension host
 * offers the save dialog. The compliance mapping and the "verifies
 * without Meridian" promise come from the real payload, never copy.
 */

type ExportPhase =
  | { kind: 'idle' }
  | { kind: 'working' }
  | { kind: 'done'; bundle: LedgerExportBundleResult }
  | { kind: 'error'; error: unknown };

export function ExportPanel({
  client,
  ready,
}: {
  client: WebviewRpcClient;
  ready: boolean;
}) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [phase, setPhase] = useState<ExportPhase>({ kind: 'idle' });

  const runExport = async () => {
    setPhase({ kind: 'working' });
    try {
      const params: Record<string, number> = {};
      if (from.trim() !== '') {
        params.fromSequence = Number(from);
      }
      if (to.trim() !== '') {
        params.toSequence = Number(to);
      }
      const bundle = await client.request('ledger.exportBundle', params);
      const fileName = `meridian-bundle-${bundle.range.fromSequence}-${bundle.range.toSequence}.json`;
      // §17: no filesystem in the webview — the host saves.
      client.notify({
        type: 'download',
        fileName,
        mimeType: 'application/json',
        content: JSON.stringify(bundle, null, 2),
      });
      setPhase({ kind: 'done', bundle });
    } catch (error) {
      setPhase({ kind: 'error', error });
    }
  };

  return (
    <section aria-labelledby="export-heading" className={styles.panel}>
      <h2 className={styles.heading} id="export-heading">
        Export
      </h2>
      <p className={styles.copy}>Audit bundle, signed · verifies without Meridian installed.</p>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          void runExport();
        }}
      >
        <label className={styles.field}>
          <span className={styles.label}>From sequence</span>
          <input
            className={styles.input}
            inputMode="numeric"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            placeholder="1"
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>To sequence</span>
          <input
            className={styles.input}
            inputMode="numeric"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            placeholder="ledger tip"
          />
        </label>
        <button type="submit" className={styles.button} disabled={!ready || phase.kind === 'working'}>
          Export audit bundle
        </button>
      </form>
      {phase.kind === 'working' && <LoadingState label="Building the signed bundle…" />}
      {phase.kind === 'error' && <ErrorState error={phase.error} />}
      {phase.kind === 'done' && (
        <div className={styles.done} role="status" data-testid="export-done">
          <p className={styles.doneLine}>
            Bundle signed{' '}
            {toSafeText(phase.bundle.signature?.signedAt ?? 'at export')} ·{' '}
            {phase.bundle.entries.length}{' '}
            {phase.bundle.entries.length === 1 ? 'entry' : 'entries'} · verifies without
            Meridian installed
          </p>
          {phase.bundle.compliance?.standards.length ? (
            <p className={styles.doneMeta}>
              Maps to {toSafeText(phase.bundle.compliance.standards.join(', '))}
            </p>
          ) : null}
          {phase.bundle.entries.length === 0 && (
            <p className={styles.doneMeta}>The range is empty — nothing recorded yet.</p>
          )}
        </div>
      )}
      {phase.kind === 'error' && phase.error instanceof RpcError && phase.error.code === -32004 && (
        <p className={styles.doneMeta}>The ledger is not available in this workspace yet.</p>
      )}
    </section>
  );
}
