import { useEffect, useId, useRef, useState } from 'react';
import { ExternalAgentsScreen } from '../screens/ExternalAgentsScreen';
import { FlightRecorderScreen } from '../screens/FlightRecorderScreen';
import { LedgerScreen } from '../screens/LedgerScreen';
import type { ScreenProps } from '../screens/registry';
import styles from './studios.module.css';

export type EvidenceTab = 'recorder' | 'sessions' | 'ledger';

export interface EvidenceStudioProps extends ScreenProps {
  initialTab?: EvidenceTab;
  onNavigate?: (route: string) => void;
}

const TABS: Array<{ id: EvidenceTab; label: string; note: string }> = [
  { id: 'recorder', label: 'Flight recorder', note: 'Trace an edit to its evidence' },
  { id: 'sessions', label: 'External sessions', note: 'Inspect source coverage and attributed changes' },
  { id: 'ledger', label: 'Audit ledger', note: 'Read records, inspect proofs, export a bundle' },
];

/** A single evidence workspace over the existing, real sidecar-backed screens. */
export function EvidenceStudio({ initialTab = 'recorder', onNavigate: _onNavigate, ...screenProps }: EvidenceStudioProps) {
  const [tab, setTab] = useState<EvidenceTab>(initialTab);
  const prefix = useId();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  useEffect(() => setTab(initialTab), [initialTab]);
  const selected = TABS.find((item) => item.id === tab)!;
  const observed = screenProps.sessions.status === 'ready' ? screenProps.sessions.data.sessions : undefined;
  const sources = observed ? new Set(observed.map((session) => session.vendor)).size : undefined;

  return (
    <div className={styles.studio}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Evidence / inspect & understand</p>
          <h1 className={styles.title}>Every change has a story.</h1>
          <p className={styles.intro}>Follow the source, inspect what was recorded, and take the evidence with you.</p>
        </div>
        <span className={styles.connection} data-connected={screenProps.ready}>
          <span aria-hidden="true" className={styles.dot} />
          {screenProps.ready ? 'Recorder connected' : 'Connecting to recorder'}
        </span>
      </header>

      <section className={styles.evidenceSummary} aria-label="Evidence coverage">
        <div className={styles.summaryCell}>
          <span className={styles.label}>Observed sessions</span>
          <strong className={styles.stat}>{observed?.length ?? '—'}</strong>
          <span className={styles.muted}>Detected by the current observers</span>
        </div>
        <div className={styles.summaryCell}>
          <span className={styles.label}>Sources represented</span>
          <strong className={styles.stat}>{sources ?? '—'}</strong>
          <span className={styles.muted}>Vendor names preserved in every record</span>
        </div>
        <div className={styles.assurance}>
          <span className={styles.assuranceIcon} aria-hidden="true">◇</span>
          <div>
            <strong>Evidence before confidence.</strong>
            <p>Detection, attribution, and chain integrity are separate signals. Missing observations stay visible; a valid chain does not establish that an agent’s output is correct.</p>
          </div>
        </div>
      </section>

      <div className={styles.tabBar} role="tablist" aria-label="Evidence views">
        {TABS.map((item, index) => (
          <button
            key={item.id}
            ref={(element) => { buttons.current[index] = element; }}
            id={`${prefix}-${item.id}-tab`}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            aria-controls={`${prefix}-panel`}
            tabIndex={tab === item.id ? 0 : -1}
            className={styles.tab}
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => {
              let next = index;
              if (event.key === 'ArrowRight') next = (index + 1) % TABS.length;
              else if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length;
              else if (event.key === 'Home') next = 0;
              else if (event.key === 'End') next = TABS.length - 1;
              else return;
              event.preventDefault();
              setTab(TABS[next].id);
              buttons.current[next]?.focus();
            }}
          >
            <span>{item.label}</span>
            <span className={styles.tabIndex}>0{index + 1}</span>
          </button>
        ))}
      </div>
      <section
        id={`${prefix}-panel`}
        role="tabpanel"
        aria-labelledby={`${prefix}-${tab}-tab`}
        className={styles.evidencePanel}
      >
        <p className={styles.panelCaption}>{selected.note}</p>
        {tab === 'recorder' && <FlightRecorderScreen {...screenProps} />}
        {tab === 'sessions' && <ExternalAgentsScreen {...screenProps} />}
        {tab === 'ledger' && <LedgerScreen {...screenProps} />}
      </section>
    </div>
  );
}
