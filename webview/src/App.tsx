import { useEffect, useState } from 'react';
import {
  WEBVIEW_PROTOCOL_VERSION,
  type HostInitPayload,
} from '../../shared/ts/webview-messages';
import { ErrorState } from './components/AsyncState';
import { useInterval, useLedgerQuery, useObserveSessions } from './hooks/recorder-hooks';
import {
  getVsCodeApi,
  readUiState,
  writeUiState,
  type PersistedUiState,
} from './host/vscode-api';
import { RpcProtocolError, type WebviewRpcClient } from './rpc/client';
import { visibleScreens } from './screens/registry';
import { FirstRunScreen } from './screens/FirstRunScreen';
import {
  DEFAULT_DENSITY,
  DEFAULT_THEME,
  applyTheme,
  detectHighContrast,
  resolveDensity,
  resolveTheme,
  type Density,
  type ThemeName,
} from './theme/themes';
import { vendorLabel } from './components/vendors';
import styles from './app.module.css';

/**
 * The GF0 shell (VIGUIX_Final §7.2, F0 shape): a Crown carrying the X-29
 * external-session indicator, a Loom Bar generated from the screen
 * registry filtered by enabled tiers (X-28), the active screen, and no
 * Orchestra chrome — F0 screens are DOM-first and complete alone.
 */

function useUiTheme(): [ThemeName, Density] {
  const api = getVsCodeApi();
  const [theme, setTheme] = useState<ThemeName>(
    () => readUiState(api)?.theme ?? DEFAULT_THEME,
  );
  const [density, setDensity] = useState<Density>(
    () => readUiState(api)?.density ?? DEFAULT_DENSITY,
  );

  useEffect(() => {
    const sync = () => {
      const highContrast = detectHighContrast(document);
      applyTheme(document.documentElement, theme, density, highContrast);
      writeUiState(api, { theme, density });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, [api, theme, density]);

  return [resolveTheme(theme), resolveDensity(density)];
}

function useHostInit(client: WebviewRpcClient): {
  init: HostInitPayload | undefined;
  protocolError: string | null;
} {
  const [init, setInit] = useState<HostInitPayload | undefined>();
  const [protocolError, setProtocolError] = useState<string | null>(null);

  useEffect(() => {
    return client.addListener((message) => {
      if (message.type !== 'init') {
        return;
      }
      if (message.init.protocolVersion !== WEBVIEW_PROTOCOL_VERSION) {
        setProtocolError(
          new RpcProtocolError(
            WEBVIEW_PROTOCOL_VERSION,
            message.init.protocolVersion,
          ).message,
        );
        return;
      }
      setInit(message.init);
    });
  }, [client]);

  return { init, protocolError };
}

function Crown({
  ready,
  sessionCount,
  firstVendor,
}: {
  ready: boolean;
  sessionCount: number;
  firstVendor: string | undefined;
}) {
  return (
    <header className={styles.crown}>
      <h1 className={styles.title}>Flight Recorder</h1>
      <p className={styles.subtitle} role="status" data-testid="crown-indicator">
        {!ready
          ? 'Connecting to the recorder…'
          : sessionCount > 0
            ? `● Recording · ${vendorLabel(firstVendor ?? 'unknown')} active · ` +
              `${sessionCount} ${sessionCount === 1 ? 'session' : 'sessions'} · ` +
              '0 model calls by Meridian'
            : 'Watching for agent sessions · 0 model calls by Meridian'}
      </p>
    </header>
  );
}

export function App({ client }: { client: WebviewRpcClient }) {
  useUiTheme();
  const { init, protocolError } = useHostInit(client);
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const api = getVsCodeApi();
  const [activeScreen, setActiveScreen] = useState<string | undefined>(
    () => readUiState(api)?.view?.screen as string | undefined,
  );

  const ready = init !== undefined && protocolError === null;

  // Handshake (§17: version checked on handshake): the host answers `ready`
  // with `init`, carrying its protocol version and enabled tiers.
  useEffect(() => {
    client.notify({ type: 'ready', protocolVersion: client.protocolVersion });
  }, [client]);

  useEffect(() => {
    return client.addListener((message) => {
      if (message.type === 'event' && message.event.kind === 'sessions/changed') {
        setSessionEpoch((n) => n + 1);
      }
    });
  }, [client]);

  // X-29: sessions are App-level state — the Crown indicator must reflect a
  // session within two seconds of the sidecar knowing it. Host push events
  // re-arm the query instantly; the 2s interval is the backstop.
  const sessions = useObserveSessions(ready ? client : undefined, true, sessionEpoch);
  useInterval(() => sessions.refresh(), ready ? 2000 : null);

  // 10.40 first-run detection: nothing observed AND nothing recorded.
  // Small poll — ledger appends carry no push event in F0.
  const ledgerTip = useLedgerQuery(ready ? client : undefined, { limit: 1 }, true);
  useInterval(() => ledgerTip.refresh(), ready ? 4000 : null);
  const firstRun =
    sessions.status === 'ready' &&
    ledgerTip.status === 'ready' &&
    sessions.data.sessions.length === 0 &&
    ledgerTip.data.entries.length === 0;

  if (protocolError) {
    return (
      <div className={styles.app}>
        <ErrorState error={new RpcProtocolError(WEBVIEW_PROTOCOL_VERSION, -1)} />
        <p role="note">{protocolError}</p>
      </div>
    );
  }

  const screens = visibleScreens(init?.enabledTiers ?? []);
  const active =
    screens.find((screen) => screen.id === activeScreen) ?? screens[0];

  const selectScreen = (id: string) => {
    setActiveScreen(id);
    const persisted: PersistedUiState = {
      ...(readUiState(api) ?? {
        theme: resolveTheme(undefined),
        density: resolveDensity(undefined),
      }),
      view: { ...(readUiState(api)?.view ?? {}), screen: id },
    };
    writeUiState(api, persisted);
  };

  return (
    <div className={styles.app}>
      <Crown
        ready={ready}
        sessionCount={sessions.status === 'ready' ? sessions.data.sessions.length : 0}
        firstVendor={
          sessions.status === 'ready' ? sessions.data.sessions[0]?.vendor : undefined
        }
      />
      {firstRun ? (
        <main className={styles.main}>
          <FirstRunScreen
            client={client}
            ready={ready}
            workspaceDir={init?.workspaceDir}
            sessions={sessions}
            ledgerTip={ledgerTip}
          />
        </main>
      ) : (
        <>
          <nav className={styles.loomBar} aria-label="Screens">
            {screens.map((screen) => (
              <button
                key={screen.id}
                type="button"
                className={`${styles.loomTab} ${
                  active?.id === screen.id ? styles.loomTabActive : ''
                }`}
                aria-current={active?.id === screen.id ? 'page' : undefined}
                onClick={() => selectScreen(screen.id)}
              >
                {screen.title}
              </button>
            ))}
          </nav>
          <main className={styles.main}>
            {active && (
              <active.component
                client={client}
                ready={ready}
                sessions={sessions}
                workspaceDir={init?.workspaceDir}
                enabledTiers={init?.enabledTiers ?? []}
              />
            )}
          </main>
        </>
      )}
    </div>
  );
}
