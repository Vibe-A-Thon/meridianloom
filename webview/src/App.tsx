import { Component, useEffect, useRef, useState, type ReactNode } from 'react';
import { WEBVIEW_PROTOCOL_VERSION, type HostInitPayload } from '../../shared/ts/webview-messages';
import { ErrorState, LoadingState } from './components/AsyncState';
import { useInterval, useLedgerQuery, useObserveSessions } from './hooks/recorder-hooks';
import { getVsCodeApi, readUiState, writeUiState } from './host/vscode-api';
import { RpcProtocolError, type WebviewRpcClient } from './rpc/client';
import { FirstRunScreen } from './screens/FirstRunScreen';
import { DEFAULT_DENSITY, DEFAULT_THEME, applyTheme, detectHighContrast, resolveDensity, resolveTheme, type Density, type ThemeName } from './theme/themes';
import { Home } from './workbench/Home';
import { AgentStudio } from './workbench/AgentStudio';
import { LearningStudio } from './workbench/LearningStudio';
import { DeliveryStudio } from './workbench/DeliveryStudio';
import { EvidenceStudio } from './workbench/EvidenceStudio';
import { RuntimeStudio } from './workbench/RuntimeStudio';
import { SettingsStudio } from './workbench/SettingsStudio';
import { GuideStudio } from './workbench/GuideStudio';
import { useWorkbench } from './workbench/useWorkbench';
import { WORKBENCH_ROUTES, routeLabel } from './workbench/routes';
import { Dialog } from './workbench/Dialog';
import { Icon } from './workbench/Icon';
import s from './workbench/workbench.module.css';

function useUiTheme() {
  const api = getVsCodeApi();
  const [theme, setTheme] = useState<ThemeName>(() => readUiState(api) ? resolveTheme(readUiState(api)?.theme) : DEFAULT_THEME);
  const [density, setDensity] = useState<Density>(() => readUiState(api) ? resolveDensity(readUiState(api)?.density) : DEFAULT_DENSITY);
  useEffect(() => {
    const sync = () => { applyTheme(document.documentElement, theme, density, detectHighContrast(document)); writeUiState(api, { ...readUiState(api), theme, density }); };
    sync(); const observer = new MutationObserver(sync);
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, [api, theme, density]);
  return { theme, density, setTheme, setDensity };
}

export function App({ client, preview = false }: { client: WebviewRpcClient; preview?: boolean }) {
  const appearance = useUiTheme();
  const [init, setInit] = useState<HostInitPayload>();
  const [protocolError, setProtocolError] = useState<RpcProtocolError>();
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const api = getVsCodeApi();
  const [route, setRoute] = useState(() => String(readUiState(api)?.view?.screen ?? 'overview'));
  const [focused, setFocused] = useState(() => readUiState(api)?.view?.focused === true);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [palette, setPalette] = useState(false);
  const [activity, setActivity] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string>();
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const unsubscribe = client.addListener(message => {
      if (message.type === 'init') {
        if (message.init.protocolVersion !== WEBVIEW_PROTOCOL_VERSION) setProtocolError(new RpcProtocolError(WEBVIEW_PROTOCOL_VERSION, message.init.protocolVersion));
        else { setInit(message.init); setProtocolError(undefined); }
      }
      if (message.type === 'event') {
        if (message.event.kind === 'sessions/changed') setSessionEpoch(epoch => epoch + 1);
        if (message.event.kind === 'tiers/changed') { const enabledTiers = message.event.enabledTiers; setInit(previous => previous ? { ...previous, enabledTiers } : previous); }
      }
    });
    client.notify({ type: 'ready', protocolVersion: client.protocolVersion });
    return unsubscribe;
  }, [client]);
  const ready = Boolean(init) && !protocolError;
  const controller = useWorkbench(client, ready);
  const sessions = useObserveSessions(ready ? client : undefined, true, sessionEpoch);
  useInterval(() => sessions.refresh(), ready ? 2000 : null);
  const ledgerTip = useLedgerQuery(ready ? client : undefined, { limit: 1 }, true);
  useInterval(() => ledgerTip.refresh(), ready ? 4000 : null);
  const navigate = (id: string) => { setRoute(id); setMobileMenu(false); setPalette(false); mainRef.current?.focus(); };
  useEffect(() => { writeUiState(api, { theme: appearance.theme, density: appearance.density, view: { ...readUiState(api)?.view, screen: route, focused } }); }, [api, route, focused, appearance.theme, appearance.density]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(value => !value); }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'f') { event.preventDefault(); setFocused(value => !value); }
      if (event.key === 'Escape') setMobileMenu(false);
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, []);
  const workspaceName = init?.workspaceDir?.split(/[\\/]/).filter(Boolean).at(-1) ?? 'No workspace';
  const screenProps = { client, ready, sessions, workspaceDir: init?.workspaceDir, enabledTiers: init?.enabledTiers ?? [] };
  const data = controller.snapshot;
  const running = data?.runs.filter(run => run.state === 'running' || run.state === 'queued') ?? [];
  const pending = data?.learning.filter(note => note.state === 'pending').length ?? 0;
  const knownRoute = WORKBENCH_ROUTES.some(item => item.id === route) || ['setup', 'flight-recorder', 'external-agents', 'ledger'].includes(route) ? route : 'overview';
  const navigationRoute = ['flight-recorder', 'external-agents', 'ledger'].includes(knownRoute) ? 'evidence' : knownRoute;
  if (protocolError) return <ErrorState error={protocolError} />;
  const body = knownRoute === 'agents' ? <AgentStudio controller={controller} onNavigate={navigate} />
    : knownRoute === 'learning' ? <LearningStudio controller={controller} onNavigate={navigate} />
    : knownRoute === 'deliverables' ? <DeliveryStudio controller={controller} onNavigate={navigate} />
    : navigationRoute === 'evidence' ? <EvidenceStudio {...screenProps} initialTab={knownRoute === 'ledger' ? 'ledger' : knownRoute === 'external-agents' ? 'sessions' : 'recorder'} />
    : knownRoute === 'runtime' ? <RuntimeStudio {...screenProps} controller={controller} />
    : knownRoute === 'settings' ? <SettingsStudio {...appearance} controller={controller} workspaceDir={init?.workspaceDir} openSettings={() => client.notify({ type: 'host/action', action: 'open-settings' })} />
    : knownRoute === 'guide' ? <GuideStudio onNavigate={navigate} />
    : knownRoute === 'setup' ? <FirstRunScreen {...screenProps} ledgerTip={ledgerTip} />
    : <Home controller={controller} sessions={sessions} onNavigate={navigate} />;
  return <div className={`${s.shell} ${focused ? s.focused : ''}`}><a className={s.skip} href="#workspace-content">Skip to workspace</a><aside className={s.sidebar} data-open={mobileMenu} aria-label="Workspace sidebar"><div className={s.brand}><svg className={s.brandMark} viewBox="0 0 32 34" fill="none" aria-hidden="true"><path d="M4 28V6l8 9 8-9v22 M12 15v13 M28 6v22 M4 22h24" stroke="currentColor" strokeWidth="2" /></svg><div>meridian loom<small>WEAVE WHAT’S NEXT</small></div></div><button className={s.workspacePicker} onClick={() => navigate('settings')}><Icon name="layers" size={19} /><span><strong>{workspaceName}</strong><small>Local workspace</small></span><Icon name="chevron" size={12} /></button><nav aria-label="Workspace navigation">{(['Workspace', 'Intelligence', 'System'] as const).map(group => <div className={s.navGroup} key={group}><p>{group}</p>{WORKBENCH_ROUTES.filter(item => item.group === group).map(item => <button key={item.id} className={s.navButton} title={item.label} aria-label={item.label} aria-current={navigationRoute === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><Icon name={item.icon} size={17} /><span>{item.label}</span>{item.id === 'agents' && Boolean(data?.agents.length) && <span className={s.navCount}>{data?.agents.length}</span>}{item.id === 'learning' && pending > 0 && <span className={s.navCount}>{pending}</span>}</button>)}</div>)}</nav><div className={s.sidebarBottom}><div className={s.localNote}><span><Icon name="check" size={12} /> Your workspace. Your control.</span><p>Portable agents.<br />Reviewable learning.<br />Evidence you can take with you.</p></div><div className={s.profile}><span>ML</span><div><strong>Meridian workbench</strong><small>Local extension · v0.0.1</small></div></div></div></aside><div className={s.workspace}><header className={s.topbar}><div className={s.breadcrumb}><button className={`${s.iconButton} ${s.mobileMenu}`} aria-label="Toggle navigation" aria-expanded={mobileMenu} onClick={() => setMobileMenu(value => !value)}><Icon name="menu" size={17} /></button><span>Workspace</span><Icon name="chevron" size={11} /><strong>{routeLabel(knownRoute)}</strong></div><div className={s.topActions}><button className={s.searchButton} onClick={() => setPalette(true)} aria-label="Search workspace and commands"><Icon name="search" size={14} /><span>Search anything…</span><kbd>⌘ K</kbd></button><button className={s.iconButton} aria-label="Toggle focus mode" aria-pressed={focused} onClick={() => setFocused(value => !value)}><Icon name="focus" size={17} /></button><button className={s.iconButton} aria-label="Open activity" onClick={() => setActivity(true)}><Icon name="bell" size={17} />{Boolean(pending || running.length) && <span className={s.notificationDot} />}</button><span className={s.connection} data-testid="crown-indicator"><span className={s.dot} />{!ready ? 'Connecting to host' : sessions.status === 'error' ? 'Observer unavailable' : sessions.status === 'ready' && sessions.data.sessions.length ? `${sessions.data.sessions.length} sessions observed` : 'Watching for agent sessions'}</span></div></header>
    {preview && <div className={`${s.banner} ${s.preview}`} role="note">PREVIEW WORKSPACE · Sample data · Changes stay in this tab · No agents are executed</div>}
    {controller.error && <div className={s.banner} role="alert"><span>{controller.error}</span><button className={s.textButton} onClick={() => void controller.refresh()}>Reconnect</button></div>}
    {!init?.workspaceDir && ready && <div className={s.banner}><span>Open a workspace folder in VS Code to save agents and deliverables.</span><button className={s.textButton} onClick={() => client.notify({ type: 'host/action', action: 'open-folder' })}>Open folder</button></div>}
    <main id="workspace-content" ref={mainRef} tabIndex={-1} className={s.main}>{!data && !controller.error && <LoadingState label="Connecting to your workspace…" />}<ScreenBoundary key={knownRoute} onReset={() => navigate('overview')}>{body}</ScreenBoundary></main><footer className={s.footer}><span>MERIDIAN LOOM / INDEPENDENT BY DESIGN</span><span>{data ? `${data.agents.filter(agent => agent.mode === 'active').length} ACTIVE · ${data.agents.filter(agent => agent.mode === 'learning').length} LEARNING` : 'WAITING FOR WORKSPACE'} · <button className={s.textButton} onClick={() => navigate('setup')}>Guided setup</button></span></footer></div>
    {palette && <CommandPalette onNavigate={navigate} onClose={() => setPalette(false)} agents={data?.agents.map(agent => ({ name: agent.name, role: agent.role })) ?? []} />}
    {activity && <Dialog title="Your workspace activity" description="Actual run history and learning reviews from this workspace." wide onClose={() => setActivity(false)}>{pending > 0 && <div className={s.settingRow}><div><h3>{pending} learning notes need your review</h3><p>Decide which lessons belong in your agents’ memory.</p></div><button className={s.secondary} onClick={() => { setActivity(false); navigate('learning'); }}>Review notes</button></div>}{running.length > 0 && <div className={s.settingRow}><div><h3>{running.length} queued or running tasks</h3><p>Stopping affects only tasks launched by this workbench.</p></div><button className={s.secondary} disabled={stopping} onClick={async () => { setStopping(true); setStopError(undefined); try { for (const run of running) await controller.execute('run/cancel', { id: run.id }); } catch (cause) { setStopError((cause as Error).message); } finally { setStopping(false); } }}><Icon name="stop" size={13} /> Stop workbench tasks</button></div>}{stopError && <p role="alert">{stopError}</p>}{data?.runs.length ? [...data.runs].reverse().slice(0, 30).map(run => <div className={s.checkRow} key={run.id}><Icon name={run.state === 'completed' ? 'check' : 'runtime'} size={18} /><div><strong>{run.agentName} · {run.state}</strong><p>{run.prompt.slice(0, 200)}</p><p>{new Date(run.startedAt).toLocaleString()}</p>{run.error && <p>{run.error}</p>}</div><button className={s.textButton} onClick={() => { setActivity(false); navigate(run.deliverableId ? 'deliverables' : 'agents'); }}>Inspect</button></div>) : <div className={s.empty}><Icon name="bell" size={30} /><h3>Room for what comes next.</h3><p>Runs and learning reviews will appear here as you use the workbench.</p></div>}</Dialog>}
  </div>;
}

function CommandPalette({ onNavigate, onClose, agents }: { onNavigate: (route: string) => void; onClose: () => void; agents: { name: string; role: string }[] }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const commands = [...WORKBENCH_ROUTES, ...agents.map((agent, index) => ({ id: `agent-${index}`, label: agent.name, description: agent.role, icon: 'agents' as const, route: 'agents' })), { id: 'setup', label: 'Guided setup', description: 'Connect, observe, inspect, export', icon: 'guide' as const }].filter(item => `${item.label} ${item.description}`.toLowerCase().includes(query.toLowerCase()));
  const choose = (index: number) => { const item = commands[index]; if (item) onNavigate('route' in item ? item.route : item.id); };
  return <Dialog title="Find your next step" onClose={onClose}><div className={s.commandSearch}><Icon name="search" /><input autoFocus aria-label="Search commands" placeholder="Search screens, agents, and actions…" value={query} onChange={event => { setQuery(event.target.value); setSelected(0); }} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setSelected(value => Math.min(value + 1, commands.length - 1)); } if (event.key === 'ArrowUp') { event.preventDefault(); setSelected(value => Math.max(value - 1, 0)); } if (event.key === 'Enter') { event.preventDefault(); choose(selected); } }} /></div><div className={s.commandList}>{commands.map((item, index) => <button key={item.id} className={s.command} data-selected={selected === index} onClick={() => choose(index)}><Icon name={item.icon} size={18} /><span><strong>{item.label}</strong><small>{item.description}</small></span><Icon name="arrow" size={14} /></button>)}{commands.length === 0 && <p>No matches. Try “agents”, “learning”, or “evidence”.</p>}</div></Dialog>;
}

class ScreenBoundary extends Component<{ children: ReactNode; onReset: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div className={s.empty} role="alert"><h2>This view could not be displayed.</h2><p>Your saved workspace data remains available. Reopen the view or return to Overview.</p><button className={s.secondary} onClick={this.props.onReset}>Return to Overview</button></div> : this.props.children; }
}
