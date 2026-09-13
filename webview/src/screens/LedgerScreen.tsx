import { useState } from 'react';
import type {
  LedgerEntry,
  LedgerProofParams,
  LedgerQueryParams,
} from '../../../shared/ts/bus-types';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { ConfidenceBar } from '../components/ConfidenceBar';
import { ExportPanel } from '../components/ExportPanel';
import { InteropPanel } from './InteropPanel';
import { ProvenanceHover } from '../components/ProvenanceHover';
import { SelvageStrip } from '../components/SelvageStrip';
import { VendorTag } from '../components/VendorTag';
import { useLedgerProof, useLedgerQuery, useLedgerEntry, useLedgerVerify } from '../hooks/recorder-hooks';
import type { WebviewRpcClient } from '../rpc/client';
import { toSafeFraction, toSafeText } from '../security/sanitize';
import type { ScreenProps } from './registry';
import styles from './ledger-screen.module.css';

/**
 * 10.7 Ledger / Selvage Viewer (VIGUIX_Final §10.7, gaps_guix amendment):
 * the audit record as a woven, locked edge. The Selvage verdict is always
 * visible (FR-M11-01); the entry stream filters over FR-M10-12 (E-LG-01);
 * the drawer shows the full record with the decrypted blob when the
 * sidecar holds the key and says so honestly when the key was shredded;
 * proofs (FR-M10-02/03) render readably; export reuses the signed-bundle
 * panel (FR-M36-04). Verification verdicts are displayed, not recomputed
 * (§12.4).
 */

interface FilterState {
  storyId: string;
  actorId: string;
  vendor: string;
  actionType: string;
  fromSequence: string;
  toSequence: string;
  fromTimestamp: string;
  toTimestamp: string;
}

const EMPTY_FILTERS: FilterState = {
  storyId: '',
  actorId: '',
  vendor: '',
  actionType: '',
  fromSequence: '',
  toSequence: '',
  fromTimestamp: '',
  toTimestamp: '',
};

function buildParams(filters: FilterState): LedgerQueryParams {
  const params: LedgerQueryParams = { limit: 200 };
  if (filters.storyId.trim()) params.storyId = filters.storyId.trim();
  if (filters.actorId.trim()) params.actorId = filters.actorId.trim();
  if (filters.vendor.trim()) params.vendor = filters.vendor.trim();
  if (filters.actionType.trim()) params.actionType = filters.actionType.trim();
  if (filters.fromSequence.trim()) params.fromSequence = Number(filters.fromSequence);
  if (filters.toSequence.trim()) params.toSequence = Number(filters.toSequence);
  if (filters.fromTimestamp.trim()) params.fromTimestamp = filters.fromTimestamp.trim();
  if (filters.toTimestamp.trim()) params.toTimestamp = filters.toTimestamp.trim();
  return params;
}

const FILTER_FIELDS: Array<{ key: keyof FilterState; label: string; placeholder: string }> = [
  { key: 'storyId', label: 'Story', placeholder: 'edb-12345' },
  { key: 'actorId', label: 'Agent', placeholder: 'claude-code' },
  { key: 'vendor', label: 'Vendor', placeholder: 'claude-code' },
  { key: 'actionType', label: 'Action', placeholder: 'diff' },
  { key: 'fromSequence', label: 'From seq', placeholder: '1' },
  { key: 'toSequence', label: 'To seq', placeholder: '4417' },
  { key: 'fromTimestamp', label: 'From time', placeholder: '2026-09-20T00:00:00Z' },
  { key: 'toTimestamp', label: 'To time', placeholder: '2026-09-21T00:00:00Z' },
];

export function LedgerScreen({ client, ready, enabledTiers }: ScreenProps) {
  const verify = useLedgerVerify(ready ? client : undefined);
  const [draft, setDraft] = useState<FilterState>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<LedgerQueryParams>({ limit: 200 });
  const stream = useLedgerQuery(ready ? client : undefined, applied, true);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  return (
    <div className={styles.screen}>
      <SelvageStrip verify={verify} enabledTiers={enabledTiers} />

      <section aria-labelledby="ledger-stream-heading" className={styles.stream}>
        <h2 className={styles.heading} id="ledger-stream-heading">
          Entry stream
        </h2>
        <form
          className={styles.filters}
          onSubmit={(event) => {
            event.preventDefault();
            setApplied(buildParams(draft));
          }}
        >
          {FILTER_FIELDS.map((field) => (
            <label key={field.key} className={styles.field}>
              <span className={styles.label}>{field.label}</span>
              <input
                className={styles.input}
                value={draft[field.key]}
                placeholder={field.placeholder}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                }
              />
            </label>
          ))}
          <button type="submit" className={styles.button} disabled={!ready}>
            Apply filters
          </button>
          <button
            type="button"
            className={styles.clearButton}
            onClick={() => {
              setDraft(EMPTY_FILTERS);
              setApplied({ limit: 200 });
            }}
          >
            Clear
          </button>
        </form>

        {stream.status === 'loading' && <LoadingState label="Reading the ledger…" />}
        {stream.status === 'error' && (
          <>
            <ErrorState error={stream.error} />
            <button type="button" onClick={stream.refresh}>Retry</button>
          </>
        )}
        {stream.status === 'ready' && stream.data.entries.length === 0 && (
          <EmptyState
            title={
              applied.storyId || applied.vendor || applied.actionType
                ? 'No entries match these filters'
                : 'No ledger entries yet'
            }
            invitation="Entries appear when recorded work lands. Adjust the filters, or record something first."
          />
        )}
        {stream.status === 'ready' && stream.data.entries.length > 0 && (
          <ul className={styles.rows}>
            {stream.data.entries.map((entry) => (
              <li key={entry.sequence}>
                <EntryRow
                  entry={entry}
                  selected={selectedSeq === entry.sequence}
                  onSelect={() =>
                    setSelectedSeq((current) =>
                      current === entry.sequence ? null : entry.sequence,
                    )
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      {selectedSeq !== null && (
        <EntryDrawer client={client} sequence={selectedSeq} onClose={() => setSelectedSeq(null)} />
      )}

      {/* M52 (MV3-T06): another tool's record, made tamper-evident. */}
      <InteropPanel client={client} ready={ready} />
      <ExportPanel client={client} ready={ready} />
    </div>
  );
}

function EntryRow({
  entry,
  selected,
  onSelect,
}: {
  entry: LedgerEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <ProvenanceHover
      card={{
        vendor: entry.vendor,
        confidence: entry.observationConfidence,
        subject: `entry · seq ${entry.sequence} · ${entry.actionType}`,
        approvedBy: entry.actionType === 'approval' ? (entry.humanActor ?? null) : null,
      }}
    >
      <button
        type="button"
        className={`${styles.row} ${selected ? styles.rowSelected : ''}`}
        aria-expanded={selected}
        onClick={onSelect}
      >
        <span className={styles.rowMeta}>#{entry.sequence}</span>
        <VendorTag vendor={entry.vendor} confidence={entry.observationConfidence} />
        <span className={styles.rowDetail}>
          {toSafeText(entry.actionType)} — {toSafeText(entry.actorId)}
          {entry.decision ? ` · ${toSafeText(entry.decision)}` : ''}
        </span>
        <span className={styles.rowMeta}>{toSafeText(entry.timestamp)}</span>
      </button>
    </ProvenanceHover>
  );
}

function EntryDrawer({
  client,
  sequence,
  onClose,
}: {
  client: WebviewRpcClient;
  sequence: number;
  onClose: () => void;
}) {
  const detail = useLedgerEntry(client, { sequence });
  const [proofParams, setProofParams] = useState<LedgerProofParams | null>(null);
  const proof = useLedgerProof(proofParams !== null ? client : undefined, proofParams ?? {});

  return (
    <section aria-labelledby="entry-drawer-heading" className={styles.drawer}>
      <div className={styles.drawerHead}>
        <h2 className={styles.heading} id="entry-drawer-heading">
          Entry #{sequence}
        </h2>
        <button type="button" className={styles.clearButton} onClick={onClose}>
          Close
        </button>
      </div>

      {detail.status === 'loading' && <LoadingState label="Fetching the full record…" />}
      {detail.status === 'error' && (
        <>
          <ErrorState error={detail.error} />
          <button type="button" onClick={detail.refresh}>Retry</button>
        </>
      )}
      {detail.status === 'ready' && (
        <>
          <dl className={styles.facts}>
            <dt>Time</dt>
            <dd>{toSafeText(detail.data.timestamp)}</dd>
            <dt>Actor</dt>
            <dd>
              {toSafeText(detail.data.actorId)} · {toSafeText(detail.data.actorVersion)} (
              {toSafeText(detail.data.actorKind)})
            </dd>
            <dt>Observed as</dt>
            <dd>
              <VendorTag
                vendor={detail.data.vendor}
                confidence={detail.data.observationConfidence}
              />
            </dd>
            <dt>Story / phase</dt>
            <dd>
              {toSafeText(detail.data.storyId)} · {toSafeText(detail.data.phase)}
            </dd>
            {detail.data.runId ? (
              <>
                {/*
                  FR-M40-02 (MV2): the run and the door it came through. The
                  ledger has carried these since schema v2 and this drawer
                  did not show them, which made "how did this run start?"
                  answerable only by reading the database — the one question
                  the origin vocabulary exists to answer.
                */}
                <dt>Run / origin</dt>
                <dd data-testid="entry-origin">
                  {toSafeText(detail.data.runId)}
                  {detail.data.origin ? ` · via ${toSafeText(detail.data.origin)}` : ''}
                </dd>
              </>
            ) : null}
            {detail.data.decision ? (
              <>
                <dt>Decision</dt>
                <dd>{toSafeText(detail.data.decision)}</dd>
              </>
            ) : null}
            {detail.data.humanActor ? (
              <>
                <dt>Approver</dt>
                <dd>
                  {toSafeText(detail.data.humanActor)}
                  {detail.data.humanRole ? ` (${toSafeText(detail.data.humanRole)})` : ''}
                </dd>
              </>
            ) : null}
            {typeof detail.data.tokensIn === 'number' ? (
              <>
                <dt>Tokens</dt>
                <dd>
                  {detail.data.tokensIn} in · {detail.data.tokensOut ?? 0} out
                </dd>
              </>
            ) : null}
            {typeof detail.data.costUsd === 'number' ? (
              <>
                <dt>Cost</dt>
                <dd>${detail.data.costUsd.toFixed(4)} (vendor-estimated)</dd>
              </>
            ) : null}
            {typeof detail.data.latencyMs === 'number' ? (
              <>
                <dt>Latency</dt>
                <dd>{detail.data.latencyMs} ms</dd>
              </>
            ) : null}
          </dl>

          {typeof detail.data.confidence === 'number' && (
            <div className={styles.confidenceBlock}>
              {/* Banned 18: confidence never renders without calibration
                  context; the bar says when there is no history. */}
              <ConfidenceBar confidence={toSafeFraction(detail.data.confidence)} calibrationError={null} />
            </div>
          )}

          <BlobBlock
            label="Input — what it was told"
            available={detail.data.inputAvailable}
            digest={detail.data.inputDigest}
            text={detail.data.input}
          />
          <BlobBlock
            label="Output"
            available={detail.data.outputAvailable}
            digest={detail.data.outputDigest}
            text={detail.data.output}
          />

          <div className={styles.proofControls}>
            <button
              type="button"
              className={styles.button}
              onClick={() => setProofParams({ sequence })}
            >
              Inspect inclusion proof
            </button>
            <form
              className={styles.consistencyForm}
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                setProofParams({
                  fromSize: Number(data.get('fromSize')),
                  toSize: Number(data.get('toSize')),
                });
              }}
            >
              <label className={styles.field}>
                <span className={styles.label}>From size</span>
                <input name="fromSize" className={styles.inputSmall} inputMode="numeric" placeholder="4400" />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>To size</span>
                <input name="toSize" className={styles.inputSmall} inputMode="numeric" placeholder="4417" />
              </label>
              <button type="submit" className={styles.button}>
                Consistency proof
              </button>
            </form>
          </div>

          {proofParams !== null && (
            <>
              {proof.status === 'loading' && <LoadingState label="Fetching the proof…" />}
              {proof.status === 'error' && <ErrorState error={proof.error} />}
              {proof.status === 'ready' && <ProofView params={proofParams} data={proof.data} />}
            </>
          )}
        </>
      )}
    </section>
  );
}

function BlobBlock({
  label,
  available,
  digest,
  text,
}: {
  label: string;
  available: boolean;
  digest: string | undefined;
  text: string | undefined;
}) {
  return (
    <div className={styles.blobBlock}>
      <h3 className={styles.blobLabel}>{label}</h3>
      {available && text ? (
        <pre className={styles.blob}>{toSafeText(text)}</pre>
      ) : digest ? (
        <p className={styles.shredded} role="note">
          Encrypted under a key that has been shredded — the chain still verifies, the content is
          gone. Digest {toSafeText(digest)}.
        </p>
      ) : (
        <p className={styles.noBlob}>Nothing recorded for this field.</p>
      )}
    </div>
  );
}

function ProofView({
  params,
  data,
}: {
  params: LedgerProofParams;
  data: { inclusion?: unknown; consistency?: unknown };
}) {
  const inclusion = data.inclusion as
    | { treeSize: number; leafIndex: number; leafHash: string; rootHash: string; path: string[] }
    | undefined;
  const consistency = data.consistency as
    | { fromSize: number; toSize: number; fromRootHash: string; toRootHash: string; path: string[] }
    | undefined;
  return (
    <div className={styles.proof} data-testid="proof-view">
      {params.sequence !== undefined && inclusion && (
        <>
          <h3 className={styles.blobLabel}>
            Inclusion proof — entry {params.sequence} is leaf {inclusion.leafIndex} of a tree of{' '}
            {inclusion.treeSize}
          </h3>
          <dl className={styles.facts}>
            <dt>Leaf hash</dt>
            <dd className={styles.hash}>{inclusion.leafHash}</dd>
            <dt>Root hash</dt>
            <dd className={styles.hash}>{inclusion.rootHash}</dd>
            <dt>Audit path</dt>
            <dd>
              {inclusion.path.length === 0 ? (
                'empty — the leaf is the root'
              ) : (
                <ol className={styles.pathList}>
                  {inclusion.path.map((step, i) => (
                    <li key={i} className={styles.hash}>
                      {step}
                    </li>
                  ))}
                </ol>
              )}
            </dd>
          </dl>
        </>
      )}
      {params.fromSize !== undefined && consistency && (
        <>
          <h3 className={styles.blobLabel}>
            Consistency proof — tree of {consistency.fromSize} extends to {consistency.toSize}
          </h3>
          <dl className={styles.facts}>
            <dt>From root</dt>
            <dd className={styles.hash}>{consistency.fromRootHash}</dd>
            <dt>To root</dt>
            <dd className={styles.hash}>{consistency.toRootHash}</dd>
            <dt>Path</dt>
            <dd>
              {consistency.path.length === 0 ? (
                'empty — same tree size'
              ) : (
                <ol className={styles.pathList}>
                  {consistency.path.map((step, i) => (
                    <li key={i} className={styles.hash}>
                      {step}
                    </li>
                  ))}
                </ol>
              )}
            </dd>
          </dl>
        </>
      )}
    </div>
  );
}
