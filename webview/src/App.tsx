import { useEffect, useState } from 'react';
import {
  WEBVIEW_PROTOCOL_VERSION,
  type HostInitPayload,
} from '../../shared/ts/webview-messages';
import { EmptyState, ErrorState, LoadingState } from './components/AsyncState';
import { VendorTag } from './components/VendorTag';
import { useLedgerQuery } from './hooks/recorder-hooks';
import { useRpcQuery } from './hooks/useRpcQuery';
import {
  getVsCodeApi,
  readUiState,
  writeUiState,
  type PersistedUiState,
} from './host/vscode-api';
import { RpcProtocolError, type WebviewRpcClient } from './rpc/client';
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
import styles from './app.module.css';

/**
 * GF0 foundation surface — the shell the 10.45/10.46/10.7 screens land in.
 * It already speaks the real data layer (sessions and ledger through the
 * host proxy) and renders every honest state; screen design is Workstream D.
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

export function App({ client }: { client: WebviewRpcClient }) {
  useUiTheme();
  const { init, protocolError } = useHostInit(client);
  const [sessionEpoch, setSessionEpoch] = useState(0);

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

  if (protocolError) {
    return (
      <div className={styles.app}>
        <ErrorState error={new RpcProtocolError(WEBVIEW_PROTOCOL_VERSION, -1)} />
        <p role="note">{protocolError}</p>
      </div>
    );
  }

  return (
    <div className={styles.app}>
      <header className={styles.crown}>
        <h1 className={styles.title}>Flight Recorder</h1>
        <p className={styles.subtitle}>External agent sessions, recorded as they happen.</p>
      </header>
      <main className={styles.main}>
        <SessionsSection client={client} epoch={sessionEpoch} ready={init !== undefined} />
        <LedgerSection client={client} ready={init !== undefined} />
      </main>
    </div>
  );
}

function SessionsSection({
  client,
  epoch,
  ready,
}: {
  client: WebviewRpcClient;
  epoch: number;
  ready: boolean;
}) {
  // `epoch` re-arms the query when the host pushes a session change; while
  // the handshake has not delivered init the hook stays pending (loading).
  const { status, data, error, refresh } = useRpcQuery(
    ready ? client : undefined,
    'observe/sessions',
    {},
    true,
    epoch,
  );
  return (
    <section aria-labelledby="sessions-heading">
      <h2 className={styles.sectionTitle} id="sessions-heading">
        Observed sessions
      </h2>
      {status === 'loading' && <LoadingState label="Watching for agent sessions…" />}
      {status === 'error' && (
        <>
          <ErrorState error={error} />
          <button type="button" onClick={refresh}>Retry</button>
        </>
      )}
      {status === 'ready' && (
        <>
          {data.warnings.length > 0 && (
            <div className={styles.warnings} role="status" data-testid="observer-warnings">
              <ul>
                {data.warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {data.sessions.length === 0 ? (
            <EmptyState
              title="Nothing recorded yet"
              invitation="Run the agent you already use — Claude Code, Cursor, Copilot — in this workspace and the cloth will start."
            />
          ) : (
            <ul className={styles.rows} style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {data.sessions.map((session) => (
                <li key={session.sessionId} className={styles.row}>
                  <VendorTag vendor={session.vendor} confidence={session.confidence} />
                  <span className={styles.rowDetail}>{session.detail}</span>
                  <span className={styles.rowMeta}>{session.source}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function LedgerSection({
  client,
  ready,
}: {
  client: WebviewRpcClient;
  ready: boolean;
}) {
  const { status, data, error, refresh } = useLedgerQuery(ready ? client : undefined, {
    limit: 100,
  });
  return (
    <section aria-labelledby="ledger-heading">
      <h2 className={styles.sectionTitle} id="ledger-heading">
        Ledger
      </h2>
      {status === 'loading' && <LoadingState label="Reading the ledger…" />}
      {status === 'error' && (
        <>
          <ErrorState error={error} />
          <button type="button" onClick={refresh}>Retry</button>
        </>
      )}
      {status === 'ready' &&
        (data.entries.length === 0 ? (
          <EmptyState
            title="No ledger entries yet"
            invitation="Entries appear when recorded work lands — a commit with provenance trailers, a rejection, an export."
          />
        ) : (
          <ul className={styles.rows} style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {data.entries.map((entry) => (
              <li key={entry.sequence} className={styles.row}>
                <span className={styles.rowMeta}>#{entry.sequence}</span>
                <VendorTag vendor={entry.vendor} confidence={entry.observationConfidence} />
                <span className={styles.rowDetail}>
                  {entry.actionType} — {entry.actorId}
                </span>
                <span className={styles.rowMeta}>{entry.timestamp}</span>
              </li>
            ))}
          </ul>
        ))}
    </section>
  );
}
