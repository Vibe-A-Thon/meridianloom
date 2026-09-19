import {
  DENSITIES,
  THEMES,
  type Density,
  type ThemeName,
} from "../theme/themes";
import type { WorkbenchController } from "./useWorkbench";
import { Icon } from "./Icon";
import s from "./workbench.module.css";
import { useViewState } from "./operations/shared";
import { useEffect } from "react";
export const THEME_LABELS: Record<ThemeName, string> = {
  "follow-vscode": "Follow VS Code",
  "indigo-vat": "Indigo Vat",
  "sized-linen": "Sized Linen",
  "iron-gall": "Iron Gall",
  "madder-dusk": "Madder Dusk",
  "weld-dawn": "Weld Dawn",
  "loom-ghost": "Loom Ghost",
};
export function SettingsStudio({
  theme,
  density,
  setTheme,
  setDensity,
  controller,
  workspaceDir,
  openSettings,
}: {
  theme: ThemeName;
  density: Density;
  setTheme: (theme: ThemeName) => void;
  setDensity: (density: Density) => void;
  controller: WorkbenchController;
  workspaceDir?: string;
  openSettings: () => void;
}) {
  const [motion, setMotion] = useViewState("motionPreference", "system");
  const [reading, setReading] = useViewState("readingPreference", "standard");
  useEffect(() => {
    document.documentElement.dataset.mlMotion = motion;
    document.documentElement.dataset.mlReading = reading;
  }, [motion, reading]);
  return (
    <div className={s.page}>
      <header className={s.pageHeading}>
        <div>
          <p className={s.eyebrow}>SYSTEM / SETTINGS</p>
          <h1>A workspace that feels like you.</h1>
          <p>Make room for the way you think and work.</p>
        </div>
      </header>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <div>
            <p className={s.eyebrow}>APPEARANCE</p>
            <h2>Find your atmosphere</h2>
          </div>
          <Icon name="settings" />
        </div>
        <div className={s.settingsGrid}>
          {THEMES.map((name) => (
            <button
              className={s.themeOption}
              key={name}
              aria-pressed={theme === name}
              onClick={() => setTheme(name)}
            >
              <div className={s.swatch} data-ml-theme={name} aria-hidden="true">
                <span />
                <span />
                <i />
              </div>
              {THEME_LABELS[name]}
            </button>
          ))}
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Information density</h3>
            <p>Adjust spacing and data rows without losing context.</p>
          </div>
          <select
            className={s.select}
            aria-label="Information density"
            value={density}
            onChange={(event) => setDensity(event.target.value as Density)}
          >
            {DENSITIES.map((value) => (
              <option key={value} value={value}>
                {value[0].toUpperCase() + value.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </section>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Reading and motion</h2>
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Text presentation</h3>
            <p>Give prose, forms and evidence tables more room.</p>
          </div>
          <select
            className={s.select}
            aria-label="Reading size"
            value={reading}
            onChange={(event) => setReading(event.target.value)}
          >
            <option value="standard">Standard</option>
            <option value="large">Larger text</option>
          </select>
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Motion preference</h3>
            <p>System reduced-motion preferences are always respected.</p>
          </div>
          <select
            className={s.select}
            aria-label="Motion preference"
            value={motion}
            onChange={(event) => setMotion(event.target.value)}
          >
            <option value="system">Follow system</option>
            <option value="reduce">Reduce motion</option>
          </select>
        </div>
      </section>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Local and deliberate</h2>
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Repository</h3>
            <p>
              <code>
                {workspaceDir ??
                  "Open a folder in VS Code to save agent profiles and deliverables."}
              </code>
            </p>
          </div>
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Agent execution</h3>
            <p>
              {controller.snapshot?.capabilities.executionReady
                ? "Ready for explicit ACP task dispatch. Permission policy applies to every tool request."
                : (controller.snapshot?.capabilities.executionBlockedReason ??
                  "Waiting for the extension host.")}
            </p>
          </div>
          <button className={s.secondary} onClick={openSettings}>
            Extension settings <Icon name="external" size={14} />
          </button>
        </div>
        <div className={s.settingRow}>
          <div>
            <h3>Persistence</h3>
            <p>
              Profiles, briefs, runs, and reviewed notes are stored in{" "}
              <code>.meridian/workbench/state.json</code>. Appearance and
              navigation restore with the panel.
            </p>
          </div>
        </div>
      </section>
      <section className={s.panel}>
        <div className={s.panelHeader}>
          <h2>Stay in flow</h2>
        </div>
        {[
          ["Command palette", "Ctrl / ⌘ K"],
          ["Toggle focus mode", "Ctrl / ⌘ Shift F"],
          ["Close a dialog", "Esc"],
          ["Move between evidence tabs", "← / →"],
          ["Navigate controls", "Tab / Shift Tab"],
        ].map(([action, shortcut]) => (
          <div className={s.settingRow} key={action}>
            <h3>{action}</h3>
            <kbd>{shortcut}</kbd>
          </div>
        ))}
      </section>
    </div>
  );
}
