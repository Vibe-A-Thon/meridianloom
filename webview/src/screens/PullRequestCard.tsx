import { useState } from 'react';
import type {
  PrConflictsResult,
  PrStatusResult,
  SpendSeriesResult,
} from '../../../shared/ts/bus-types';
import { EnforcementBadge } from '../components/EnforcementBadge';
import { useEnforcementPoints } from '../hooks/useEnforcementPoints';
import { RpcError, type WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import styles from './pull-request-card.module.css';

/**
 * The pull-request evidence card — `FR-M46-03`, `MVP-R2.5`, `J2`, `H7`
 * (MV3-T04).
 *
 * One card for a pull request under gate, answering the six things a
 * reviewer has to know before they merge somebody else's agent's work:
 *
 *   what changed and how risky · **the revision actually tested** ·
 *   where the evidence runs out · what failed · what it cost ·
 *   and what a human has to do next.
 *
 * The second of those is the one nobody else shows, and it is the one that
 * bites. A checks-passed badge means the checks passed on **some** revision.
 * If the head has moved since, the badge is describing code that is no longer
 * the code being merged — and every interface that renders a green tick
 * beside a stale commit is asserting something it never checked.
 *
 * `H7`: the finding is stated in words. A card that shows six numbers and no
 * sentence leaves the reader to do the synthesis, and the reader is the
 * person least equipped to do it — they are looking at this precisely
 * because they did not watch the work happen.
 *
 * `J2`: a figure Meridian could not compute says so. There is no rung
 * between "measured" and "unknown", and a blank cell gets read as a zero.
 */

/** The control this card's verdict comes from (MV1-T02). */
const MERGE_CONTROL = 'merge_gate';

export interface PullRequestCardProps {
  client: WebviewRpcClient;
  ready: boolean;
}

interface Loaded {
  status: PrStatusResult;
  conflicts?: PrConflictsResult;
  conflictsError?: string;
  spend?: SpendSeriesResult;
  spendError?: string;
}

type State =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'loaded'; data: Loaded }
  | { kind: 'error'; message: string };

function describe(error: unknown): string {
  if (error instanceof RpcError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function money(value: unknown): string {
  // P26: `null`/absent is unknown. "$0.00" would tell a reviewer this run
  // was free, which is a different claim from "nobody recorded a cost".
  return typeof value === 'number' ? `$${value.toFixed(2)}` : 'not recorded';
}

/**
 * Agent-vs-agent conflicts are the distinct rework class `FR-M35-07` names,
 * and they are the strongest risk signal on this card: two agents editing
 * the same region is work nobody reviewed as a whole.
 */
function riskOf(data: Loaded): { level: 'unknown' | 'low' | 'raised' | 'high'; why: string } {
  const failed = data.status.gates.filter((gate) => gate.decision === 'block');
  if (!data.conflicts) {
    return {
      level: 'unknown',
      why:
        data.conflictsError ??
        'Conflict analysis did not run, so how much of this change overlaps between agents is unknown.',
    };
  }
  const conflicts = data.conflicts.conflicts.length;
  if (conflicts > 0)
    return {
      level: 'high',
      why: `${conflicts} region(s) were edited by more than one agent. Work that no single agent — and no single review — saw as a whole.`,
    };
  if (failed.length > 0)
    return {
      level: 'raised',
      why: `${failed.length} gate(s) blocked this change.`,
    };
  return {
    level: 'low',
    why: 'No agent-vs-agent overlap, and no gate blocked it.',
  };
}

/**
 * The sentence. `H7` — and it has to name the *action*, not the state: a
 * reviewer reading "blocked" still has to work out what to do about it.
 */
function actionRequired(data: Loaded, staleHead: boolean): string {
  const merge = data.status.merge;
  if (!data.status.ingested)
    return 'Nothing has been ingested for this pull request yet. Ingest it to gate it.';
  if (merge?.halted)
    return 'A governance halt is active. Nothing merges until it is lifted — find out what stopped, and why, before doing anything here.';
  if (staleHead)
    return 'Re-run the gates against the current head. What passed was a different revision, so the recorded verdicts do not describe the code you would merge.';
  const failed = data.status.gates.filter((gate) => gate.decision === 'block');
  if (failed.length)
    return `Fix what ${failed.map((gate) => gate.gate).join(', ')} blocked, then re-run the gates. Approving over a block is possible and is recorded as such.`;
  if (merge?.status === 'blocked') {
    const missing = merge.missing ?? [];
    return missing.length
      ? `An approval is still required: ${missing.join('; ')}.`
      : 'The merge gate is blocked. Its criteria report is empty, which is itself worth asking about before overriding.';
  }
  if (data.conflicts && data.conflicts.conflicts.length)
    return 'Review the regions two agents both edited before approving. The gates pass; the overlap is the part nobody saw as a whole.';
  return 'The gates pass on the current head. Approving is a decision you are recorded as having made.';
}

export function PullRequestCard({ client, ready }: PullRequestCardProps) {
  const [subject, setSubject] = useState('');
  const [state, setState] = useState<State>({ kind: 'idle' });
  const enforcement = useEnforcementPoints(ready ? client : undefined);
  const declaration = enforcement.lookup(MERGE_CONTROL);

  async function load(event: React.FormEvent) {
    event.preventDefault();
    if (!subject.trim()) return;
    setState({ kind: 'busy' });
    try {
      const status = await client.request('pr/status', { subject: subject.trim() });
      const data: Loaded = { status };

      // The two supporting figures are fetched separately and each is allowed
      // to fail on its own. A card that refuses to render because the cost
      // query timed out would withhold the gate verdict, which is the part
      // that matters most.
      try {
        data.conflicts = await client.request('pr/conflicts', {
          ...(status.storyId ? { storyId: status.storyId } : {}),
          ...(status.baseBranch ? { base: status.baseBranch } : {}),
          record: false,
        } as never);
      } catch (error) {
        data.conflictsError = describe(error);
      }
      if (status.storyId) {
        try {
          data.spend = await client.request('spend/series', {
            dimension: 'story',
            storyId: status.storyId,
          });
        } catch (error) {
          data.spendError = describe(error);
        }
      }
      setState({ kind: 'loaded', data });
    } catch (error) {
      setState({ kind: 'error', message: describe(error) });
    }
  }

  return (
    <section className={styles.card} aria-label="Pull request evidence">
      <header className={styles.head}>
        <div>
          <h2>Pull request evidence</h2>
          <p className={styles.muted}>
            What a reviewer needs before merging somebody else's agent's work.
          </p>
        </div>
        {/*
          MV1-T02: the verdict on this card comes from a control, and the
          control's real boundary travels with it. A merge verdict rendered
          without saying where it binds is the overclaim SEC-32 forbids.

          Rendered only once the declaration has arrived. `EnforcementBadge`
          refuses to render without one — deliberately, so a surface cannot
          ship looking complete — and passing it the `null` of a query that
          has not answered yet would turn a slow fetch into a crash.
        */}
        {declaration ? (
          <EnforcementBadge declaration={declaration} />
        ) : (
          <span className={styles.muted} data-testid="pr-enforcement-pending">
            {enforcement.status === 'error'
              ? 'Where the merge gate binds could not be read, so treat its verdict as advisory.'
              : 'Reading where the merge gate binds…'}
          </span>
        )}
      </header>

      <form className={styles.form} onSubmit={load}>
        <label className={styles.label} htmlFor="pr-subject">
          Pull request
        </label>
        <input
          id="pr-subject"
          className={styles.input}
          value={subject}
          placeholder="pr:acme/payments-service#4417"
          onChange={(event) => setSubject(event.target.value)}
          data-testid="pr-subject"
        />
        <button
          type="submit"
          className={styles.primary}
          disabled={!ready || !subject.trim() || state.kind === 'busy'}
          data-testid="pr-load"
        >
          {state.kind === 'busy' ? 'Reading…' : 'Show the evidence'}
        </button>
      </form>

      {state.kind === 'error' && (
        <p className={styles.error} role="alert" data-testid="pr-error">
          {state.message}
        </p>
      )}

      {state.kind === 'loaded' && <Card data={state.data} />}
    </section>
  );
}

function Card({ data }: { data: Loaded }) {
  const { status } = data;
  const failed = status.gates.filter((gate) => gate.decision === 'block');
  const risk = riskOf(data);

  // `FR-M46-03`'s hardest field. The gates recorded a verdict against a head;
  // if the head has moved, the verdict describes code that is not what would
  // merge. Nothing else on this card matters if this is true.
  const testedHead = status.headCommit ?? null;
  const currentHead = data.conflicts?.ref ?? null;
  const staleHead = Boolean(
    testedHead && currentHead && currentHead !== testedHead && !currentHead.startsWith(testedHead),
  );

  const agents = new Set(
    (data.conflicts?.hunks ?? [])
      .map((hunk) => hunk.agent?.agentId)
      .filter((id): id is string => Boolean(id)),
  );

  return (
    <div className={styles.body} data-testid="pr-card">
      {/*
        H7: the finding, in words, first. Everything below it is the working.
      */}
      <p className={styles.finding} data-testid="pr-action">
        {actionRequired(data, staleHead)}
      </p>

      <dl className={styles.facts}>
        <dt>Change risk</dt>
        <dd data-testid="pr-risk">
          <span className={styles.risk} data-level={risk.level}>
            {risk.level}
          </span>{' '}
          {risk.why}
        </dd>

        <dt>Revision actually tested</dt>
        <dd data-testid="pr-revision">
          {testedHead ? (
            <>
              <code>{toSafeText(testedHead.slice(0, 12))}</code>
              {staleHead ? (
                <strong className={styles.stale}>
                  {' '}
                  — the branch has moved to{' '}
                  <code>{toSafeText((currentHead ?? '').slice(0, 12))}</code> since.
                  The recorded verdicts describe a different revision from the
                  one you would merge.
                </strong>
              ) : currentHead ? (
                ' — still the head of the branch.'
              ) : (
                // J2/P26: not a tick. Nothing was compared.
                ' — Meridian could not read the branch to check whether this is still its head.'
              )}
            </>
          ) : (
            'Not recorded. Without it there is nothing to check the gate verdicts against.'
          )}
        </dd>

        <dt>Attribution coverage</dt>
        <dd data-testid="pr-coverage">
          {data.conflicts ? (
            <>
              {data.conflicts.hunks.length} attributed hunk(s) across {agents.size}{' '}
              agent(s).
              {data.conflicts.hunks.length === 0
                ? ' No hunk in this range carried agent evidence, so "no agent conflict" here means "nothing to compare", not "checked and clear".'
                : ''}
            </>
          ) : (
            <>Not measured. {data.conflictsError ?? 'Conflict analysis did not run.'}</>
          )}
        </dd>

        <dt>Failed checks</dt>
        <dd data-testid="pr-failed">
          {status.gates.length === 0
            ? 'No gate has run against this pull request.'
            : failed.length === 0
              ? `All ${status.gates.length} recorded gate(s) passed.`
              : failed.map((gate) => toSafeText(gate.gate)).join(', ')}
        </dd>

        <dt>Cost</dt>
        <dd data-testid="pr-cost">
          {data.spend
            ? `${money((data.spend.totals as Record<string, unknown>)?.costUsd)} recorded against ${toSafeText(status.storyId ?? 'this story')}`
            : `Not measured. ${data.spendError ?? 'No story id, so spend could not be scoped to this pull request.'}`}
        </dd>
      </dl>

      {/*
        The card reports a verdict; it does not offer to act on it. Approving
        a merge is a governed action with its own surface and its own
        recorded identity, and an approve button here would make this card a
        second, quieter route to the same decision.
      */}
      <p className={styles.muted} data-testid="pr-footnote">
        This card reads the record. Approving or halting happens in the Gate
        Room, where the decision is bound to your identity.
      </p>
    </div>
  );
}
