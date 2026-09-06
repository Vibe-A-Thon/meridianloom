import type { ObserveSession } from '../../../shared/ts/bus-types';
import { EmptyState } from '../components/AsyncState';
import { ProvenanceHover } from '../components/ProvenanceHover';
import { VendorTag } from '../components/VendorTag';
import { CONFIDENCE_META } from '../components/vendors';
import type { RpcQueryState } from '../hooks/useRpcQuery';
import { toSafeText } from '../security/sanitize';
import styles from './this-session-panel.module.css';

/**
 * 10.45 This Session (gaps_guix §3): live external-agent sessions with
 * their observation source and confidence — Meridian observes; it does not
 * host or drive (FR-M35-06), and the provenance card says so (X-30).
 */

function sessionCard(session: ObserveSession) {
  return {
    vendor: session.vendor,
    confidence: session.confidence,
    subject: `observed via ${toSafeText(session.source)}${
      session.startedAt ? ` · started ${toSafeText(session.startedAt)}` : ''
    }`,
    note: 'Observing only — Meridian records this session; it cannot steer or stop it (FR-M35-06).',
  };
}

export function ThisSessionPanel({ sessions }: { sessions: RpcQueryState<'observe/sessions'> }) {
  const { status, data } = sessions;
  return (
    <section aria-labelledby="this-session-heading" className={styles.panel}>
      <h2 className={styles.heading} id="this-session-heading">
        This session
      </h2>
      {status === 'ready' && data.warnings.length > 0 && (
        <div className={styles.warnings} role="status" data-testid="observer-warnings">
          <ul>
            {data.warnings.map((warning, i) => (
              <li key={i}>{toSafeText(warning)}</li>
            ))}
          </ul>
        </div>
      )}
      {status === 'ready' && data.sessions.length === 0 && (
        <EmptyState
          title="Nothing recorded yet"
          invitation="Run the agent you already use — Claude Code, Cursor, Copilot — in this workspace and the cloth will start."
        />
      )}
      {status === 'ready' && data.sessions.length > 0 && (
        <ul className={styles.rows}>
          {data.sessions.map((session) => (
            <li key={session.sessionId}>
              <ProvenanceHover card={sessionCard(session)}>
                <div className={styles.row}>
                  <VendorTag vendor={session.vendor} confidence={session.confidence} />
                  <span className={styles.rowDetail}>{toSafeText(session.detail)}</span>
                  <span className={styles.rowMeta}>
                    {toSafeText(session.source)} ·{' '}
                    {CONFIDENCE_META[
                      session.confidence === 'direct' || session.confidence === 'telemetry'
                        ? session.confidence
                        : 'inferred'
                    ].shortLabel}
                  </span>
                </div>
              </ProvenanceHover>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
