import type { ObservationConfidence } from '../../../shared/ts/bus-types';
import { ProvenanceTag, type AgentProvenance } from './ProvenanceTag';
import { VendorTag } from './VendorTag';
import styles from './agent-token.module.css';

/**
 * §9.1 AgentToken: circular identity + state, sizes 20/28/40/64.
 *
 * Composed invariants (component-tested, X-27 / H2 / v2.1):
 *  - a VendorTag with confidence renders at every size (all are ≥ 20px);
 *  - at 28px and larger a ProvenanceTag renders — never below;
 *  - the hit area is padded to 28px even at the 20px visual size (A-03);
 *  - the token is always circular (§4.3).
 *
 * Identity art is the T9 geometric fallback — a two-colour thread pattern
 * derived from the agent id — until the V1 sprite decision lands.
 */

export const AGENT_TOKEN_SIZES = [20, 28, 40, 64] as const;
export type AgentTokenSize = (typeof AGENT_TOKEN_SIZES)[number];

export interface AgentTokenProps {
  /** Stable agent identifier (Commit Mono per §6.2) or display name. */
  agentId: string;
  size?: AgentTokenSize;
  vendor: string;
  confidence: ObservationConfidence | string;
  provenance: AgentProvenance;
  /** Optional short label; the identifier itself renders when absent. */
  label?: string;
}

/** Token colour pairs — all dye tokens, so theming and CVD checks hold. */
const THREAD_COLOURS: Array<[string, string]> = [
  ['var(--ml-dye-working)', 'var(--ml-dye-idle)'],
  ['var(--ml-dye-approved)', 'var(--ml-dye-idle)'],
  ['var(--ml-dye-attention)', 'var(--ml-dye-idle)'],
  ['var(--ml-dye-meta)', 'var(--ml-dye-idle)'],
  ['var(--ml-dye-working)', 'var(--ml-dye-approved)'],
  ['var(--ml-dye-meta)', 'var(--ml-dye-working)'],
];

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function ThreadPattern({ agentId }: { agentId: string }) {
  const [primary, secondary] = THREAD_COLOURS[hashString(agentId) % THREAD_COLOURS.length]!;
  const arc = (hashString(agentId) % 3) + 2; // 2–4 thread bands
  return (
    <svg className={styles.pattern} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" fill={secondary} />
      {Array.from({ length: arc }, (_, i) => {
        const y = 6 + (i * 28) / Math.max(1, arc - 1);
        return (
          <path
            key={i}
            d={`M-2 ${y} Q 20 ${y - 6 + ((i * 5) % 12)}, 42 ${y}`}
            stroke={primary}
            strokeWidth="3"
            fill="none"
          />
        );
      })}
    </svg>
  );
}

export function AgentToken({
  agentId,
  size = 28,
  vendor,
  confidence,
  provenance,
  label,
}: AgentTokenProps) {
  const showProvenance = size >= 28;
  return (
    <span className={styles.hit} data-testid="agent-token" title={agentId}>
      <span className={`${styles.token} ${styles[`size${size}`]}`} data-ml-size={size}>
        <ThreadPattern agentId={agentId} />
      </span>
      <span className={styles.meta}>
        <span className={styles.identity}>{label ?? agentId}</span>
        <VendorTag vendor={vendor} confidence={confidence} />
        {showProvenance && (
          <span className={styles.provenance}>
            <ProvenanceTag provenance={provenance} />
          </span>
        )}
      </span>
    </span>
  );
}
