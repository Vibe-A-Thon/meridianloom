import type { LedgerEntry } from '../../../shared/ts/bus-types';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { ProvenanceHover } from '../components/ProvenanceHover';
import { VendorTag } from '../components/VendorTag';
import { useLedgerQuery } from '../hooks/recorder-hooks';
import type { WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './weave-panel.module.css';

/**
 * 10.45 The Weave, F0 shape (gaps_guix §3 DS-2): the recorded passes from
 * every agent in one cloth — a row is a row whether Claude Code or a
 * Copilot PR wove it. Rows are ledger entries (the real passes); each
 * carries its VendorTag + confidence glyph (X-27) and the same provenance
 * card as every other surface (X-30).
 */

function shortTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime())
    ? toSafeText(iso)
    : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function rowCard(entry: LedgerEntry) {
  return {
    vendor: entry.vendor,
    confidence: entry.observationConfidence,
    subject: `pass · seq ${entry.sequence} · ${entry.actionType} · ${shortTime(entry.timestamp)}`,
    // Approvals record their approver; any other pass is honestly "not yet
    // gated" until an approval entry exists for it.
    approvedBy: entry.actionType === 'approval' ? (entry.humanActor ?? null) : null,
  };
}

export function WeavePanel({ client, ready }: { client: WebviewRpcClient; ready: boolean }) {
  const { status, data, error, refresh } = useLedgerQuery(
    ready ? client : undefined,
    { limit: 200 },
    true,
  );
  return (
    <section aria-labelledby="weave-heading" className={styles.panel}>
      <h2 className={styles.heading} id="weave-heading">
        The Weave
      </h2>
      {status === 'loading' && <LoadingState label="Reading recorded passes…" />}
      {status === 'error' && (
        <>
          <ErrorState error={error} />
          <button type="button" onClick={refresh}>Retry</button>
        </>
      )}
      {status === 'ready' &&
        (data.entries.length === 0 ? (
          <EmptyState
            title="No ledger entries yet"
            invitation="Entries appear when recorded work lands — a commit with provenance trailers, a rejection, an export."
          />
        ) : (
          <ul className={styles.rows}>
            {data.entries.map((entry) => (
              <li key={entry.sequence}>
                <ProvenanceHover card={rowCard(entry)}>
                  <div className={styles.row}>
                    <VendorTag vendor={entry.vendor} confidence={entry.observationConfidence} />
                    <span className={styles.rowDetail}>
                      {toSafeText(entry.actionType)} — {toSafeText(entry.actorId)}
                    </span>
                    <span className={styles.rowMeta}>
                      #{entry.sequence} · {shortTime(entry.timestamp)}
                    </span>
                  </div>
                </ProvenanceHover>
              </li>
            ))}
          </ul>
        ))}
    </section>
  );
}
