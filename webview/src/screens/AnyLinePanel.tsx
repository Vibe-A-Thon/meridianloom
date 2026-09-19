import { useState } from 'react';
import type {
  AttribBlameResult,
  LedgerGetEntryResult,
  LedgerQueryResult,
  TrailerCommit,
} from '../../../shared/ts/bus-types';
import { ErrorState, LoadingState } from '../components/AsyncState';
import { VendorTag } from '../components/VendorTag';
import { VENDOR_IDS } from '../components/vendors';
import type { WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './any-line-panel.module.css';

/**
 * 10.45 Any Line — the provenance question: pick a file and line, get
 * "which agent wrote this line, what was it told, how confident, who
 * approved" (AC-30). Every answer is labelled with where it came from and
 * its observation confidence (G3/B12); when the only signal is git
 * authorship the answer is visibly labelled `inferred`, never presented
 * with the weight of a direct observation (banned 31).
 *
 * The answer is assembled from real RPCs only: attrib/blame (the line's
 * commit), attrib/symbol (the enclosing definition), trailers/parse (the
 * commit's Co-Authored-By / Meridian-Ledger trailers) and the ledger
 * entries the trailer range names (input blob = "told", approval entries =
 * "who approved").
 */

/** Bus trailer vendor ids → VendorTag ids (vendors.ts). */
const TRAILER_VENDOR_MAP: Record<string, string> = {
  claude: 'claude-code',
  'github-copilot': 'copilot',
};

interface AnyLineAnswer {
  path: string;
  line: number;
  content: string | null;
  commit: string;
  authorTime: string;
  symbol: string | null;
  vendor: string;
  /** telemetry when a trailer named the agent; inferred otherwise. */
  confidence: 'telemetry' | 'inferred';
  ledgerRange: string | null;
  seq: number | null;
  told: string | null;
  toldState: 'recorded' | 'shredded' | 'none';
  approvedBy: string | null;
  approvedRole: string | null;
}

function shortSha(sha: string): string {
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

function shortTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime())
    ? toSafeText(iso)
    : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** "4398-4402" / "4402" trailer values → sequence span. */
function rangesSpan(ranges: string[]): { min: number; max: number } | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const range of ranges) {
    for (const part of range.split('-')) {
      const value = Number(part.trim());
      if (Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  }
  return min <= max ? { min, max } : null;
}

function trailerVendor(commit: TrailerCommit | undefined): string | null {
  const attribution = commit?.attributions.find(
    (a) => a.vendor !== 'unknown' && a.vendor !== 'generic',
  );
  if (!attribution) {
    return null;
  }
  const mapped = TRAILER_VENDOR_MAP[attribution.vendor] ?? attribution.vendor;
  return (VENDOR_IDS as readonly string[]).includes(mapped) ? mapped : 'unknown';
}

async function assembleAnswer(
  client: WebviewRpcClient,
  repoPath: string,
  path: string,
  line: number,
): Promise<AnyLineAnswer> {
  const blame: AttribBlameResult = await client.request('attrib/blame', {
    repoPath,
    paths: [path],
  });
  const hit = blame.lines.find((entry) => entry.line === line);
  if (!hit) {
    throw new LineNotFoundError(path, line);
  }

  const [symbol, trailers] = await Promise.all([
    client
      .request('attrib/symbol', { repoPath, path, line })
      .then((result: { symbol: string | null }) => result.symbol)
      .catch(() => null),
    client
      .request('trailers/parse', { repoPath, ref: hit.commit })
      .catch(() => ({ commits: [] as TrailerCommit[] })),
  ]);

  const commit = trailers.commits[0];
  const attributedVendor = trailerVendor(commit);
  const vendor = attributedVendor ?? 'unknown';
  // Telemetry only when a trailer actually named the agent; a bare commit
  // (or none) is inference from git authorship, labelled as such (G3/B12).
  const confidence: AnyLineAnswer['confidence'] = attributedVendor ? 'telemetry' : 'inferred';

  const answer: AnyLineAnswer = {
    path,
    line,
    content: hit.content ?? null,
    commit: hit.commit,
    authorTime: hit.authorTime,
    symbol,
    vendor,
    confidence,
    ledgerRange: commit?.meridianLedger[0] ?? null,
    seq: null,
    told: null,
    toldState: 'none',
    approvedBy: null,
    approvedRole: null,
  };

  const span = rangesSpan(commit?.meridianLedger ?? []);
  if (span) {
    const query: LedgerQueryResult | null = await client
      .request('ledger.query', { fromSequence: span.min, toSequence: span.max })
      .catch(() => null);
    if (query && query.entries.length > 0) {
      const approval = query.entries.find((entry) => entry.actionType === 'approval');
      if (approval) {
        answer.approvedBy = approval.humanActor ?? null;
        answer.approvedRole = approval.humanRole ?? null;
      }
      const pass =
        [...query.entries].reverse().find((entry) => entry.actionType === 'diff') ??
        query.entries[query.entries.length - 1];
      answer.seq = pass.sequence;
      const detail: LedgerGetEntryResult | null = await client
        .request('ledger.getEntry', { sequence: pass.sequence })
        .catch(() => null);
      if (detail) {
        if (detail.inputAvailable && detail.input) {
          answer.told = detail.input;
          answer.toldState = 'recorded';
        } else if (detail.inputDigest) {
          answer.toldState = 'shredded';
        }
      }
    }
  }
  return answer;
}

class LineNotFoundError extends Error {
  constructor(
    readonly path: string,
    readonly line: number,
  ) {
    super(`Line ${line} was not found in ${path} at HEAD.`);
    this.name = 'LineNotFoundError';
  }
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'answer'; answer: AnyLineAnswer }
  | { kind: 'error'; error: unknown };

export function AnyLinePanel({
  client,
  ready,
  workspaceDir,
}: {
  client: WebviewRpcClient;
  ready: boolean;
  workspaceDir: string | undefined;
}) {
  const [path, setPath] = useState('');
  const [line, setLine] = useState('');
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });

  const ask = async () => {
    const lineNumber = Number(line);
    setPhase({ kind: 'loading' });
    try {
      const answer = await assembleAnswer(client, workspaceDir!, path.trim(), lineNumber);
      setPhase({ kind: 'answer', answer });
    } catch (error) {
      setPhase({ kind: 'error', error });
    }
  };

  const inputValid = path.trim() !== '' && Number.isInteger(Number(line)) && Number(line) > 0;

  return (
    <section aria-labelledby="any-line-heading" className={styles.panel}>
      <h2 className={styles.heading} id="any-line-heading">
        Any line
      </h2>
      {!workspaceDir && (
        <p className={styles.noRepo} role="note">
          Open a folder in this window to ask about a line — provenance answers come from the
          repository, and there is none connected.
        </p>
      )}
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (inputValid && workspaceDir) {
            void ask();
          }
        }}
      >
        <label className={styles.field}>
          <span className={styles.label}>File</span>
          <input
            className={styles.input}
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="src/PaymentController.java"
            disabled={!workspaceDir}
          />
        </label>
        <label className={`${styles.field} ${styles.lineField}`}>
          <span className={styles.label}>Line</span>
          <input
            className={styles.input}
            inputMode="numeric"
            value={line}
            onChange={(event) => setLine(event.target.value)}
            placeholder="47"
            disabled={!workspaceDir}
          />
        </label>
        <button
          type="submit"
          className={styles.button}
          disabled={!ready || !workspaceDir || !inputValid || phase.kind === 'loading'}
        >
          Answer
        </button>
      </form>

      {phase.kind === 'loading' && <LoadingState label="Tracing the line through git and the ledger…" />}
      {phase.kind === 'error' && (
        <>
          <ErrorState error={phase.error} />
          <button type="button" onClick={() => void ask()}>Retry</button>
        </>
      )}
      {phase.kind === 'answer' && <AnswerCard answer={phase.answer} />}
    </section>
  );
}

function AnswerCard({ answer }: { answer: AnyLineAnswer }) {
  return (
    <div className={styles.answer} data-testid="any-line-answer">
      <h3 className={styles.answerTitle}>
        {toSafeText(answer.path)}:{answer.line}
        {answer.content ? <span className={styles.answerLine}> {toSafeText(answer.content)}</span> : null}
      </h3>
      {answer.confidence === 'inferred' && (
        <p className={styles.inferredBadge} data-testid="inferred-label">
          inferred — no agent trailer on this commit; the attribution below is Meridian’s best
          inference from git history, not a reported identity.
        </p>
      )}
      <dl className={styles.facts}>
        <dt>Agent</dt>
        <dd>
          <VendorTag vendor={answer.vendor} confidence={answer.confidence} />
        </dd>
        <dt>Recorded</dt>
        <dd>
          {shortTime(answer.authorTime)} · commit {shortSha(answer.commit)} ·{' '}
          <span className={styles.factSource}>recorded in git</span>
        </dd>
        <dt>Symbol</dt>
        <dd>{answer.symbol ? toSafeText(answer.symbol) : '—'}</dd>
        {answer.seq !== null && (
          <>
            <dt>Sequence</dt>
            <dd>
              seq {answer.seq}
              {answer.ledgerRange ? ` (Meridian-Ledger: ${toSafeText(answer.ledgerRange)})` : ''} ·{' '}
              <span className={styles.factSource}>recorded in the ledger</span>
            </dd>
          </>
        )}
        <dt>Told</dt>
        <dd>
          {answer.toldState === 'recorded' && answer.told ? (
            <>
              “{toSafeText(answer.told)}” ·{' '}
              <span className={styles.factSource}>recorded in the ledger</span>
            </>
          ) : answer.toldState === 'shredded' ? (
            'encrypted under a key that has been shredded — the chain still verifies, the content is gone'
          ) : (
            'not recorded'
          )}
        </dd>
        <dt>Approved</dt>
        <dd>
          {answer.approvedBy ? (
            <>
              {toSafeText(answer.approvedBy)}
              {answer.approvedRole ? ` (${toSafeText(answer.approvedRole)})` : ''} ·{' '}
              <span className={styles.factSource}>recorded in the ledger</span>
            </>
          ) : (
            '— (not yet gated)'
          )}
        </dd>
      </dl>
    </div>
  );
}
