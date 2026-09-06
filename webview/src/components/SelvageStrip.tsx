import { useState } from 'react';
import type { TierName } from '../../../shared/ts/bus-types';
import type { RpcQueryState } from '../hooks/useRpcQuery';
import { toSafeText } from '../security/sanitize';
import styles from './selvage-strip.module.css';

/**
 * FR-M11-01 — the Selvage strip along the screen's bottom edge: the chain
 * integrity verdict the sidecar computed, displayed, never re-computed
 * (VIGUIX_Final §12.4: the UI shows a verdict it did not compute). On
 * failure the first divergent sequence is named and the failure is
 * impossible to overlook; the tamper state uses the rework dye, not
 * --ml-halt (banned pattern 14 reserves that for Halt All).
 *
 * X-28: a single tier-unlock affordance sits at the strip's right end —
 * higher tiers are ABSENT from the shell, never disabled (banned 30).
 */

const TIER_ORDER: readonly TierName[] = ['governor', 'orchestra'];

const UNLOCK_STATEMENTS: Record<string, string> = {
  governor:
    'Adds gates over external agents’ pull requests, roles, and trust analytics. Flight Recorder never makes model calls; a hosted Governor does.',
  orchestra:
    'Adds Meridian’s own agents, loops and the Floor — the only tier that makes model calls. Everything the Recorder captured stays yours.',
};

/** Rendered stitch count — the strip implies the chain, it does not draw it. */
const STITCHES = 24;

function shortTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? toSafeText(iso) : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function SelvageStrip({
  verify,
  enabledTiers,
}: {
  verify: RpcQueryState<'ledger.verify'>;
  enabledTiers: readonly TierName[];
}) {
  const [unlocked, setUnlocked] = useState(false);
  const nextLocked = TIER_ORDER.find((tier) => !enabledTiers.includes(tier));

  return (
    <footer className={styles.selvage} data-testid="selvage-strip">
      <div
        className={`${styles.verdict} ${
          verify.status === 'ready' && !verify.data.ok ? styles.broken : ''
        }`}
        data-chain-ok={verify.status === 'ready' ? String(verify.data.ok) : undefined}
      >
        {verify.status === 'loading' && (
          <span className={styles.ok}>Checking the chain…</span>
        )}
        {verify.status === 'error' && (
          <span className={styles.brokenText} role="alert">
            Chain state unknown — the verifier did not answer.
          </span>
        )}
        {verify.status === 'ready' && verify.data.ok && (
          <>
            <span className={styles.stitches} aria-hidden="true">
              {Array.from({ length: STITCHES }, (_, i) => (
                <span key={i} className={styles.stitch} />
              ))}
            </span>
            <span className={styles.ok} data-testid="selvage-verified">
              Chain verified to {verify.data.entriesChecked} · {shortTime(verify.data.verifiedAt)}
            </span>
          </>
        )}
        {verify.status === 'ready' && !verify.data.ok && (
          <span className={styles.brokenText} role="alert" data-testid="selvage-broken">
            Chain verification failed — first divergent sequence{' '}
            {verify.data.firstDivergentSequence ?? 'unknown'}. {toSafeText(verify.data.detail)}
          </span>
        )}
      </div>

      {nextLocked && (
        <div className={styles.unlock}>
          {unlocked && (
            <p className={styles.unlockText} role="note">
              {UNLOCK_STATEMENTS[nextLocked]}
            </p>
          )}
          <button
            type="button"
            className={styles.unlockButton}
            aria-expanded={unlocked}
            onClick={() => setUnlocked((was) => !was)}
          >
            Unlock {nextLocked === 'governor' ? 'Governor' : 'Orchestra'}
          </button>
        </div>
      )}
    </footer>
  );
}
