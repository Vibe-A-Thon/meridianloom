import { useState } from 'react';
import type { ObserveSession } from '../../../shared/ts/bus-types';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { ProvenanceHover } from '../components/ProvenanceHover';
import { VendorTag } from '../components/VendorTag';
import { CONFIDENCE_META, vendorLabel } from '../components/vendors';
import { useObserveHealth } from '../hooks/recorder-hooks';
import { useRpcQuery } from '../hooks/useRpcQuery';
import type { WebviewRpcClient } from '../rpc/client';
import { toSafeText } from '../security/sanitize';
import type { ScreenProps } from './registry';
import styles from './external-agents-screen.module.css';

/**
 * 10.46 External Agents (gaps_guix §3): every non-Meridian agent seen in
 * the workspace as a first-class citizen. The screen watches and gates; it
 * never drives — there is deliberately no control to modify, steer or stop
 * an external agent (FR-M35-06). Sessions arrive from the App-level X-29
 * query (push events + 2s backstop); observer health surfaces NFR-32
 * degradation prominently, and the Claude-without-OTel warning renders
 * verbatim from the sidecar payload (F0-D).
 */

export function ExternalAgentsScreen({
  client,
  ready,
  sessions,
  workspaceDir,
}: ScreenProps) {
  const health = useObserveHealth(ready ? client : undefined);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = sessions.status === 'ready'
    ? sessions.data.sessions.find((s) => s.sessionId === selectedId)
    : undefined;

  return (
    <div className={styles.screen}>
      <div className={styles.columns}>
        <section aria-labelledby="agent-sessions-heading" className={styles.listColumn}>
          <h2 className={styles.heading} id="agent-sessions-heading">
            External agent sessions
          </h2>
          <p className={styles.copy}>
            Meridian observes these sessions; hosting arrives with Governor. Nothing here can
            steer, pause or reconfigure an agent (FR-M35-06).
          </p>
          {sessions.status === 'loading' && <LoadingState label="Watching for agent sessions…" />}
          {sessions.status === 'error' && (
            <>
              <ErrorState error={sessions.error} />
              <button type="button" onClick={sessions.refresh}>Retry</button>
            </>
          )}
          {sessions.status === 'ready' && sessions.data.warnings.length > 0 && (
            <div className={styles.warnings} role="status" data-testid="observer-warnings">
              <ul>
                {sessions.data.warnings.map((warning, i) => (
                  <li key={i}>{toSafeText(warning)}</li>
                ))}
              </ul>
            </div>
          )}
          {sessions.status === 'ready' && sessions.data.sessions.length === 0 && (
            <EmptyState
              title="No external agents seen yet"
              invitation="Run the agent you already use in this workspace — Claude Code, Cursor, Copilot — and it appears here within seconds of the recorder noticing it."
            />
          )}
          {sessions.status === 'ready' && sessions.data.sessions.length > 0 && (
            <ul className={styles.rows}>
              {sessions.data.sessions.map((session) => (
                <li key={session.sessionId}>
                  <div className={styles.rowWrap}>
                    <ProvenanceHover
                      card={{
                        vendor: session.vendor,
                        confidence: session.confidence,
                        subject: `observed via ${toSafeText(session.source)}`,
                        note: 'Observing only — this session is the vendor’s own process.',
                      }}
                    >
                      <button
                        type="button"
                        className={`${styles.row} ${
                          selectedId === session.sessionId ? styles.rowSelected : ''
                        }`}
                        aria-expanded={selectedId === session.sessionId}
                        onClick={() =>
                          setSelectedId((current) =>
                            current === session.sessionId ? null : session.sessionId,
                          )
                        }
                      >
                        <VendorTag vendor={session.vendor} confidence={session.confidence} />
                        <span className={styles.rowDetail}>{toSafeText(session.detail)}</span>
                        <span className={styles.rowMeta}>
                          {toSafeText(session.source)} ·{' '}
                          {session.startedAt ? toSafeText(session.startedAt) : 'active now'}
                        </span>
                      </button>
                    </ProvenanceHover>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="session-detail-heading" className={styles.detailColumn}>
          <h2 className={styles.heading} id="session-detail-heading">
            Session detail
          </h2>
          {selected ? (
            <SessionDetail client={client} session={selected} workspaceDir={workspaceDir} />
          ) : (
            <p className={styles.copy}>Select a session to see its attributed hunks and trailers.</p>
          )}
        </section>
      </div>

      <ObserverHealthPanel health={health} />
    </div>
  );
}

function SessionDetail({
  client,
  session,
  workspaceDir,
}: {
  client: WebviewRpcClient;
  session: ObserveSession;
  workspaceDir: string | undefined;
}) {
  const canQuery = workspaceDir !== undefined;
  const diff = useRpcQuery(
    canQuery ? client : undefined,
    'attrib/diff',
    { repoPath: workspaceDir ?? '' },
    canQuery,
  );
  const classify = useRpcQuery(
    canQuery ? client : undefined,
    'attrib/classify',
    {
      repoPath: workspaceDir ?? '',
      observedSessions: [
        {
          sessionId: session.sessionId,
          vendor: session.vendor,
          ...(session.startedAt ? { startedAt: session.startedAt } : {}),
        },
      ],
    },
    canQuery,
  );
  const trailers = useRpcQuery(
    canQuery ? client : undefined,
    'trailers/parse',
    {
      repoPath: workspaceDir ?? '',
      ...(session.startedAt ? { since: session.startedAt } : {}),
    },
    canQuery,
  );

  if (!canQuery) {
    return (
      <p className={styles.noRepo} role="note">
        Open a folder in this window to attribute this session’s hunks — attribution comes from
        the repository, and there is none connected.
      </p>
    );
  }

  const classificationByPath = new Map(
    classify.status === 'ready' ? classify.data.files.map((f) => [f.path, f]) : [],
  );

  return (
    <div className={styles.detail} data-testid="session-detail">
      <p className={styles.detailIntro}>
        {vendorLabel(session.vendor)} · observed via {toSafeText(session.source)} ·{' '}
        {CONFIDENCE_META[
          session.confidence === 'direct' || session.confidence === 'telemetry'
            ? session.confidence
            : 'inferred'
        ].meaning}
      </p>

      <h3 className={styles.detailHeading}>Attributed hunks</h3>
      {diff.status === 'loading' && <LoadingState label="Diffing the worktree…" />}
      {diff.status === 'error' && <ErrorState error={diff.error} />}
      {diff.status === 'ready' && diff.data.files.length === 0 && (
        <p className={styles.copy}>No uncommitted changes in the worktree right now.</p>
      )}
      {diff.status === 'ready' && diff.data.files.length > 0 && (
        <ul className={styles.fileList}>
          {diff.data.files.map((file) => {
            const classification = classificationByPath.get(file.path);
            const adds = file.hunks
              .flatMap((h) => h.lines)
              .filter((l) => l.kind === 'added').length;
            const removes = file.hunks
              .flatMap((h) => h.lines)
              .filter((l) => l.kind === 'removed').length;
            return (
              <li key={file.path} className={styles.fileRow}>
                <span className={styles.filePath}>{toSafeText(file.path)}</span>
                <span className={styles.fileStats}>
                  +{adds} −{removes}
                </span>
                {classification ? (
                  <span
                    className={styles.attribution}
                    data-confidence={classification.observationConfidence}
                  >
                    {classification.attribution} · {classification.observationConfidence}
                  </span>
                ) : (
                  classify.status === 'loading' && <span className={styles.fileStats}>…</span>
                )}
                {classification && classification.rationale.length > 0 && (
                  <ul className={styles.rationale}>
                    {classification.rationale.map((reason, i) => (
                      <li key={i}>{toSafeText(reason)}</li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <h3 className={styles.detailHeading}>Trailers found</h3>
      {trailers.status === 'loading' && <LoadingState label="Reading commit trailers…" />}
      {trailers.status === 'error' && <ErrorState error={trailers.error} />}
      {trailers.status === 'ready' && trailers.data.commits.length === 0 && (
        <p className={styles.copy}>
          No Co-Authored-By or Meridian-Ledger trailers in this window — nothing claimed these
          commits.
        </p>
      )}
      {trailers.status === 'ready' && trailers.data.commits.length > 0 && (
        <ul className={styles.trailerList}>
          {trailers.data.commits.map((commit, i) => (
            <li key={i} className={styles.trailerRow}>
              <span className={styles.fileStats}>
                {commit.commit ? commit.commit.slice(0, 12) : 'message parse'}
              </span>
              {commit.attributions.length > 0 ? (
                <span>
                  {commit.attributions
                    .map((a) => `${toSafeText(a.name)} (${toSafeText(a.vendor)})`)
                    .join(', ')}
                </span>
              ) : (
                <span>no agent trailer</span>
              )}
              {commit.meridianLedger.map((range, j) => (
                <span key={j} className={styles.ledgerRange}>
                  Meridian-Ledger: {toSafeText(range)}
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ObserverHealthPanel({
  health,
}: {
  health: ReturnType<typeof useObserveHealth>;
}) {
  return (
    <section aria-labelledby="observer-health-heading" className={styles.health}>
      <h2 className={styles.heading} id="observer-health-heading">
        Observer health
      </h2>
      {health.status === 'loading' && <LoadingState label="Checking observer adapters…" />}
      {health.status === 'error' && (
        <>
          <ErrorState error={health.error} />
          <button type="button" onClick={health.refresh}>Retry</button>
        </>
      )}
      {health.status === 'ready' && (
        <>
          <p className={styles.copy} role="status">
            Session monitor {health.data.monitorRunning ? 'is polling (X-29)' : 'is not running — sessions may lag'}
          </p>
          <ul className={styles.healthList}>
            {health.data.observers.map((observer) => (
              <li
                key={observer.name}
                className={`${styles.healthRow} ${
                  observer.status === 'degraded' ? styles.healthDegraded : ''
                }`}
                data-status={observer.status}
              >
                <span className={styles.healthName}>
                  {observer.status === 'degraded' ? '⚠' : '✓'} {toSafeText(observer.name)}
                </span>
                <span className={styles.fileStats}>
                  {observer.adapterVersion ? `adapter ${toSafeText(observer.adapterVersion)}` : ''}
                  {observer.vendorRelease
                    ? ` · targets vendor release ${toSafeText(observer.vendorRelease)}`
                    : ''}
                </span>
                {/* Verbatim from the sidecar payload — the F0-D mandate text
                    (NO_OTEL_DIRECT_WARNING) reaches the user unedited. */}
                <span className={styles.healthDetail}>{toSafeText(observer.detail)}</span>
                {observer.warnings.map((warning, i) => (
                  <span key={i} className={styles.healthWarning} role="alert">
                    {toSafeText(warning)}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
