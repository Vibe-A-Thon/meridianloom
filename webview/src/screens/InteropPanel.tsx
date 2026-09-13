import { useState } from 'react';
import type {
  ForeignRecord,
  InteropConflictsResult,
  InteropVerifyResult,
} from '../../../shared/ts/bus-types';
import { VendorTag } from '../components/VendorTag';
import { RpcError, type WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './interop-panel.module.css';

/**
 * Other tools' provenance records, in the Ledger — `M52`, `FR-M52-01`…`03`,
 * `SEC-42`/`43`, `AC-59` (MV3-T06).
 *
 * The surface for the one thing no reviewed competitor does: take the record
 * another tool wrote into this repository and make it **tamper-evident**, by
 * putting its digest in the signed ledger.
 *
 * What this panel must never do is let the reader come away thinking Meridian
 * vouched for what the record says. It signs a digest. It did not watch the
 * work happen — it read a file claiming the work happened — so every record
 * here is at `inferred` and attributed to the tool that wrote it, and the
 * panel says in words what the signature covers and what it does not
 * (`SEC-43`).
 *
 * Reading is separate from notarising, deliberately. Looking at what is in
 * your own repository should not write anything.
 */

const NOT_ENDORSED_HEADLINE =
  'Meridian signs the digest, not the claim.';

/**
 * FR-M52-05 (CP1-T02). Two labels, and neither says which record is right:
 * the panel describes the shape of a disagreement, never its answer.
 */
const KIND_LABEL: Record<string, string> = {
  conflicting: 'Records name different agents',
  incomplete: 'Records overlap but differ',
};

export interface InteropPanelProps {
  client: WebviewRpcClient;
  ready: boolean;
}

type State =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'read'; records: ForeignRecord[] }
  | { kind: 'verified'; records: ForeignRecord[]; verification: InteropVerifyResult }
  | { kind: 'error'; message: string };

function describe(error: unknown): string {
  if (error instanceof RpcError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function InteropPanel({ client, ready }: InteropPanelProps) {
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [notarised, setNotarised] = useState<string | undefined>();
  const [conflicts, setConflicts] = useState<InteropConflictsResult | undefined>();
  const [conflictsBusy, setConflictsBusy] = useState(false);
  const [conflictsError, setConflictsError] = useState<string | undefined>();
  const [recordedNote, setRecordedNote] = useState<string | undefined>();

  /**
   * Finding disagreements reads. Recording them is a separate, explicit
   * action, for the same reason reading records is separate from notarising.
   */
  async function findConflicts(record: boolean) {
    setConflictsBusy(true);
    setConflictsError(undefined);
    if (!record) setRecordedNote(undefined);
    try {
      const result = await client.request('interop/conflicts', record ? { record: true } : {});
      setConflicts(result);
      if (record) {
        setRecordedNote(
          result.recorded === 0
            ? 'Nothing new to record — every disagreement shown was already in the signed ledger.'
            : `Recorded ${result.recorded} disagreement(s) in the signed ledger, as digests.`,
        );
      }
    } catch (error) {
      setConflictsError(describe(error));
    } finally {
      setConflictsBusy(false);
    }
  }

  async function read() {
    setState({ kind: 'busy' });
    setNotarised(undefined);
    try {
      const result = await client.request('interop/records', {});
      setState({ kind: 'read', records: result.records });
    } catch (error) {
      setState({ kind: 'error', message: describe(error) });
    }
  }

  async function notarise() {
    setState({ kind: 'busy' });
    try {
      const result = await client.request('interop/notarise', {});
      setNotarised(
        result.notarised === 0
          ? `Nothing new to record — ${result.alreadyNotarised} record(s) were already notarised and are unchanged.`
          : `Recorded the digest of ${result.notarised} record(s) in the signed ledger.`,
      );
      setState({ kind: 'read', records: result.records });
    } catch (error) {
      setState({ kind: 'error', message: describe(error) });
    }
  }

  async function verify() {
    setState({ kind: 'busy' });
    try {
      const [records, verification] = await Promise.all([
        client.request('interop/records', {}),
        client.request('interop/verify', {}),
      ]);
      setState({ kind: 'verified', records: records.records, verification });
    } catch (error) {
      setState({ kind: 'error', message: describe(error) });
    }
  }

  const records = state.kind === 'read' || state.kind === 'verified' ? state.records : [];
  const verification = state.kind === 'verified' ? state.verification : undefined;

  return (
    <section className={styles.panel} aria-label="Other tools' records">
      <header className={styles.head}>
        <h2>Other tools' records</h2>
        <p className={styles.muted}>
          Provenance another tool wrote into this repository — its own git
          notes, session trailers, co-author lines.
        </p>
      </header>

      {/*
        SEC-43. A signature beside somebody else's claim is read as a
        signature ON the claim unless something stops it being read that way,
        and the documentation is not open while somebody is looking at this.
      */}
      <p className={styles.boundary} data-testid="interop-boundary">
        <strong>{NOT_ENDORSED_HEADLINE}</strong> Notarising records what a
        file said when Meridian read it, so a third party can later prove it
        has not been altered. Meridian did not observe the work these records
        describe and does not vouch for them — which is why every one is
        attributed to the tool that wrote it and none of them rises above{' '}
        <em>inferred</em>.
      </p>

      <div className={styles.actions}>
        <button disabled={!ready || state.kind === 'busy'} onClick={() => void read()} data-testid="interop-read">
          Show what is here
        </button>
        <button disabled={!ready || state.kind === 'busy'} onClick={() => void notarise()} data-testid="interop-notarise">
          Notarise their digests
        </button>
        <button disabled={!ready || state.kind === 'busy'} onClick={() => void verify()} data-testid="interop-verify">
          Check for alteration
        </button>
        <button
          disabled={!ready || conflictsBusy}
          onClick={() => void findConflicts(false)}
          data-testid="interop-conflicts"
        >
          Find disagreements
        </button>
      </div>

      {state.kind === 'busy' && <p className={styles.muted}>Reading the repository…</p>}

      {state.kind === 'error' && (
        <p className={styles.error} role="alert" data-testid="interop-error">
          {state.message}
        </p>
      )}

      {notarised && (
        <p className={styles.muted} data-testid="interop-notarised">
          {notarised}
        </p>
      )}

      {verification && (
        <p
          className={verification.altered > 0 ? styles.altered : styles.muted}
          data-testid="interop-verification"
        >
          {verification.altered > 0
            ? `${verification.altered} notarised record(s) have been ALTERED since Meridian read them.`
            : 'No notarised record has been altered since Meridian read it.'}
          {verification.missing > 0
            ? ` ${verification.missing} have been removed from the repository — gone, which is not the same as altered.`
            : ''}
          {verification.unreadable > 0
            ? ` ${verification.unreadable} notarisation entries could not be read back, so they were not checked.`
            : ''}
        </p>
      )}

      {(state.kind === 'read' || state.kind === 'verified') && records.length === 0 && (
        <p className={styles.muted} data-testid="interop-empty">
          No other provenance tool has written to this repository. That is the
          usual case, and it is not a fault.
        </p>
      )}

      {records.length > 0 && (
        <ul className={styles.list} data-testid="interop-records">
          {records.map((record) => {
            const verdict = verification?.verdicts.find(
              (entry) => entry.source === record.source && entry.commit === record.commit,
            );
            return (
              <li className={styles.row} key={`${record.source}:${record.commit}`}>
                <div className={styles.rowHead}>
                  {/*
                    X-27: an agent-attributed element cannot render without
                    its vendor tag and the confidence behind it. The tool that
                    wrote the record IS the vendor here.
                  */}
                  <VendorTag vendor={record.tool} confidence={record.confidence} />
                  <span className={styles.muted}>
                    {toSafeText(record.kind)} · {toSafeText(record.source)}
                  </span>
                </div>
                <p className={styles.muted}>
                  commit {toSafeText(record.commit.slice(0, 12))} · read{' '}
                  {toSafeText(record.observedAt)}
                </p>
                <p className={styles.digest}>{toSafeText(record.digest)}</p>
                {record.truncated && (
                  <p className={styles.muted}>
                    This record was larger than Meridian reads and was truncated;
                    the digest covers what was read.
                  </p>
                )}
                {verdict && !verdict.ok && (
                  <p className={styles.altered} data-testid={`interop-verdict-${record.commit}`}>
                    {toSafeText(verdict.detail)}
                  </p>
                )}
                {verdict && verdict.ok && (
                  <p className={styles.muted} data-testid={`interop-verdict-${record.commit}`}>
                    Unchanged since Meridian notarised it.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {conflictsError && (
        <p className={styles.error} role="alert" data-testid="interop-conflicts-error">
          {conflictsError}
        </p>
      )}

      {conflicts && (
        <div data-testid="interop-conflicts-result">
          <p className={styles.muted} data-testid="interop-conflicts-summary">
            {`Compared the provenance records on ${conflicts.examined} commit(s).`}
            {conflicts.disagreements.length === 0
              ? ' No two records disagree about who produced a commit.'
              : ` ${conflicts.disagreements.length} commit(s) have records that disagree.`}
            {conflicts.truncated
              ? ' The walk stopped at its limit and older history was not compared, so this is not a clean report for it.'
              : ''}
          </p>
          {conflicts.disagreements.length > 0 && (
            <>
              <ul className={styles.list} data-testid="interop-disagreements">
                {conflicts.disagreements.map((item) => (
                  <li className={styles.row} key={item.digest}>
                    <div className={styles.rowHead}>
                      <strong>{KIND_LABEL[item.kind] ?? 'Records differ'}</strong>
                      <span className={styles.muted}>
                        commit {toSafeText(item.commit.slice(0, 12))}
                      </span>
                    </div>
                    {/*
                      FR-M52-05: every claim, in the order it was read, and none
                      marked as the answer. Meridian's own ledger claim is one of
                      them, not the tie-breaker.
                    */}
                    <ul className={styles.list}>
                      {item.claims.map((claim) => (
                        <li key={`${claim.claimant}:${claim.evidence}`}>
                          <VendorTag vendor={claim.tool} confidence={claim.confidence} />{' '}
                          <span className={styles.muted}>{toSafeText(claim.claimant)}</span> says{' '}
                          {toSafeText(claim.agents.join(', '))}
                          <p className={styles.digest}>{toSafeText(claim.evidence)}</p>
                        </li>
                      ))}
                    </ul>
                    <p className={styles.boundary} data-testid="interop-not-resolved">
                      {toSafeText(item.notResolved)}
                    </p>
                  </li>
                ))}
              </ul>
              <div className={styles.actions}>
                <button
                  disabled={!ready || conflictsBusy}
                  onClick={() => void findConflicts(true)}
                  data-testid="interop-conflicts-record"
                >
                  Record these disagreements
                </button>
              </div>
            </>
          )}
          {recordedNote && (
            <p className={styles.muted} data-testid="interop-conflicts-recorded">
              {recordedNote}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
