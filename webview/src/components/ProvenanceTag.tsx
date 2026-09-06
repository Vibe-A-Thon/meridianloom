import styles from './provenance-tag.module.css';

/**
 * ProvenanceTag (v2.1 §9.1): prebuilt / custom / bridged (langgraph) on
 * every agent, everywhere an AgentToken appears at 28px or larger — and on
 * nothing smaller. Governance is identical across the three (banned
 * pattern 26); the tag discloses origin without implying difference.
 */
export type AgentProvenance = 'prebuilt' | 'custom' | 'bridged';

export const PROVENANCE_LABELS: Record<AgentProvenance, string> = {
  prebuilt: 'prebuilt',
  custom: 'custom',
  bridged: 'bridged (langgraph)',
};

export interface ProvenanceTagProps {
  provenance: AgentProvenance;
}

function shapeClass(provenance: AgentProvenance): string {
  switch (provenance) {
    case 'prebuilt':
      return styles.shapePrebuilt;
    case 'custom':
      return styles.shapeCustom;
    default:
      return styles.shapeBridged;
  }
}

export function ProvenanceTag({ provenance }: ProvenanceTagProps) {
  return (
    <span className={styles.tag} data-testid="provenance-tag">
      <span
        className={`${styles.shape} ${shapeClass(provenance)}`}
        aria-hidden="true"
      />
      {PROVENANCE_LABELS[provenance]}
    </span>
  );
}
