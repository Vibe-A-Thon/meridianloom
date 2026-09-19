import { ExportPanel } from '../components/ExportPanel';
import { SelvageStrip } from '../components/SelvageStrip';
import { useLedgerVerify } from '../hooks/recorder-hooks';
import { AnyLinePanel } from './AnyLinePanel';
import { ThisSessionPanel } from './ThisSessionPanel';
import { WeavePanel } from './WeavePanel';
import type { ScreenProps } from './registry';
import styles from './flight-recorder-screen.module.css';

/**
 * 10.45 Flight Recorder (gaps_guix §3) — the product's front door. Zero
 * Meridian agents required: the Weave of recorded passes, the live
 * sessions, the Any Line provenance answer, the bundle export, and the
 * Selvage chain verdict along the bottom. What it deliberately does not
 * have: a roster, a Floor, loops, a Dojo — the screen is complete alone.
 */

export function FlightRecorderScreen({
  client,
  ready,
  sessions,
  workspaceDir,
  enabledTiers,
}: ScreenProps) {
  const verify = useLedgerVerify(ready ? client : undefined);
  return (
    <div className={styles.screen}>
      <div className={styles.grid}>
        <WeavePanel client={client} ready={ready} />
        <ThisSessionPanel sessions={sessions} />
        <AnyLinePanel client={client} ready={ready} workspaceDir={workspaceDir} />
        <ExportPanel client={client} ready={ready} />
      </div>
      <SelvageStrip verify={verify} enabledTiers={enabledTiers} />
    </div>
  );
}
