import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  WEBVIEW_PROTOCOL_VERSION,
  type HostInitPayload,
} from "../../shared/ts/webview-messages";
import { ErrorState, LoadingState } from "./components/AsyncState";
import {
  useInterval,
  useLedgerQuery,
  useObserveSessions,
} from "./hooks/recorder-hooks";
import { getVsCodeApi, readUiState, writeUiState } from "./host/vscode-api";
import { RpcProtocolError, type WebviewRpcClient } from "./rpc/client";
import { FirstRunScreen } from "./screens/FirstRunScreen";
import {
  DEFAULT_DENSITY,
  DEFAULT_THEME,
  applyTheme,
  detectHighContrast,
  resolveDensity,
  resolveTheme,
  type Density,
  type ThemeName,
} from "./theme/themes";
import { LearningStudio } from "./workbench/LearningStudio";
import { DeliveryStudio } from "./workbench/DeliveryStudio";
import { EvidenceStudio } from "./workbench/EvidenceStudio";
import { RuntimeStudio } from "./workbench/RuntimeStudio";
import { SettingsStudio } from "./workbench/SettingsStudio";
import { GuideStudio } from "./workbench/GuideStudio";
import { useWorkbench } from "./workbench/useWorkbench";
import { routeLabel } from "./workbench/routes";
import {
  WORKBENCH_TABS,
  isKnownView,
  isTabUnlocked,
  normaliseView,
  tabForView,
  type WorkbenchTab,
} from "./workbench/tabs";
import { Dialog } from "./workbench/Dialog";
import { Icon } from "./workbench/Icon";
import { Dashboard } from "./workbench/catalogue/Dashboard";
import { AgentsTab } from "./workbench/catalogue/AgentsTab";
import { SkillsTab } from "./workbench/catalogue/SkillsTab";
import { InstructionsTab } from "./workbench/catalogue/InstructionsTab";
import { PhasesTab } from "./workbench/catalogue/PhasesTab";
import { RunsTab } from "./workbench/catalogue/RunsTab";
import { IntegrationsTab } from "./workbench/catalogue/IntegrationsTab";
import s from "./workbench/shell.module.css";
import w from "./workbench/workbench.module.css";

/**
 * The Meridian Loom workbench: one page, one row of tabs.
 *
 * The product requirement this shell exists to satisfy is that selecting
 * Meridian Loom in the Activity Bar *is* opening the product. There is no
 * command to run, no palette entry to find, and no second window: the view
 * resolves, this shell mounts, and the Dashboard is on screen. Everything the
 * plugin can do is then a tab away, and everything a tab can do is a
 * sub-view away.
 *
 * The shell owns exactly three things — which view is showing, the chrome
 * around it, and the two dialogs that are genuinely global (command search
 * and activity). Every surface below it is an independent component that
 * receives the controller and navigates by view id, so a studio never needs
 * to know it lives in a tab.
 *
 * Tier gating is subtractive, per X-28: a tab whose tier is not enabled is
 * absent from the bar rather than present and disabled.
 */

const AgentOperations = lazy(() =>
  import("./workbench/operations/AgentOperations").then((m) => ({
    default: m.AgentOperations,
  })),
);
const WorkspaceOperations = lazy(() =>
  import("./workbench/operations/WorkspaceOperations").then((m) => ({
    default: m.WorkspaceOperations,
  })),
);
const GovernanceStudio = lazy(() =>
  import("./workbench/governance/GovernanceStudio").then((m) => ({
    default: m.GovernanceStudio,
  })),
);
const ModelingStudio = lazy(() =>
  import("./workbench/modeling/ModelingStudio").then((m) => ({
    default: m.ModelingStudio,
  })),
);
const OrganizationStudio = lazy(() =>
  import("./workbench/organization/OrganizationStudio").then((m) => ({
    default: m.OrganizationStudio,
  })),
);

/** Which component renders a given view. Kept flat and explicit on purpose. */
const AGENT_OPERATIONS = ["floor", "watch", "inspector", "onboarding", "adapters"];
const WORKSPACE_OPERATIONS = [
  "launch",
  "steer",
  "weave",
  "decisions",
  "kpi",
  "notifications",
  "editor",
  "unlock",
  "configuration",
  "shortcuts",
];
const GOVERNANCE = [
  "gates",
  "approvals",
  "verification",
  "security",
  "pipeline",
  "repositories",
  "trust",
  "calibration",
  "spend",
  "f2-gate",
  "trust-score",
  "rejection-reasons",
  "agent-comparison",
  "jcurve",
  "tokenmaxxing",
  "dora",
];
const MODELING = [
  "codemap",
  "architecture",
  "uml",
  "flows",
  "loops",
  "diff",
  "replay",
  "comprehension",
];
const ORGANIZATION = [
  "portfolio",
  "stories",
  "specifications",
  "connectors",
  "routing",
  "exchange",
  "reports",
];
const EVIDENCE = [
  "evidence",
  "flight-recorder",
  "external-agents",
  "ledger",
  "reconciliation",
];

function useUiTheme() {
  const api = getVsCodeApi();
  const [theme, setTheme] = useState<ThemeName>(() =>
    readUiState(api) ? resolveTheme(readUiState(api)?.theme) : DEFAULT_THEME,
  );
  const [density, setDensity] = useState<Density>(() =>
    readUiState(api)
      ? resolveDensity(readUiState(api)?.density)
      : DEFAULT_DENSITY,
  );
  useEffect(() => {
    const sync = () => {
      applyTheme(
        document.documentElement,
        theme,
        density,
        detectHighContrast(document),
      );
      document.documentElement.dataset.mlMotion =
        readUiState(api)?.view?.motionPreference === "reduce"
          ? "reduce"
          : "system";
      document.documentElement.dataset.mlReading =
        readUiState(api)?.view?.readingPreference === "large"
          ? "large"
          : "standard";
      writeUiState(api, { ...readUiState(api), theme, density });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, [api, theme, density]);
  return { theme, density, setTheme, setDensity };
}

export function App({
  client,
  preview = false,
}: {
  client: WebviewRpcClient;
  preview?: boolean;
}) {
  const appearance = useUiTheme();
  const [init, setInit] = useState<HostInitPayload>();
  const [protocolError, setProtocolError] = useState<RpcProtocolError>();
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const api = getVsCodeApi();
  const [route, setRoute] = useState(() => {
    const saved = String(readUiState(api)?.view?.screen ?? "dashboard");
    return isKnownView(saved) ? saved : "dashboard";
  });
  const [focused, setFocused] = useState(
    () => readUiState(api)?.view?.focused === true,
  );
  const [palette, setPalette] = useState(false);
  const [activity, setActivity] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string>();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const unsubscribe = client.addListener((message) => {
      if (message.type === "init") {
        if (message.init.protocolVersion !== WEBVIEW_PROTOCOL_VERSION)
          setProtocolError(
            new RpcProtocolError(
              WEBVIEW_PROTOCOL_VERSION,
              message.init.protocolVersion,
            ),
          );
        else {
          setInit(message.init);
          setProtocolError(undefined);
        }
      }
      if (message.type === "event") {
        if (message.event.kind === "sessions/changed")
          setSessionEpoch((epoch) => epoch + 1);
        if (message.event.kind === "tiers/changed") {
          const enabledTiers = message.event.enabledTiers;
          setInit((previous) =>
            previous ? { ...previous, enabledTiers } : previous,
          );
        }
      }
    });
    client.notify({ type: "ready", protocolVersion: client.protocolVersion });
    return unsubscribe;
  }, [client]);

  const ready = Boolean(init) && !protocolError;
  const controller = useWorkbench(client, ready);
  const sessions = useObserveSessions(
    ready ? client : undefined,
    true,
    sessionEpoch,
  );
  useInterval(() => sessions.refresh(), ready ? 2000 : null);
  const ledgerTip = useLedgerQuery(
    ready ? client : undefined,
    { limit: 1 },
    true,
  );
  useInterval(() => ledgerTip.refresh(), ready ? 4000 : null);

  const enabledTiers = useMemo(() => init?.enabledTiers ?? [], [init]);
  const tabs = useMemo(
    () => WORKBENCH_TABS.filter((tab) => isTabUnlocked(tab, enabledTiers)),
    [enabledTiers],
  );

  const navigate = (id: string) => {
    setRoute(isKnownView(id) ? id : "dashboard");
    setPalette(false);
    mainRef.current?.focus({ preventScroll: true });
    if (mainRef.current) mainRef.current.scrollTop = 0;
  };

  useEffect(() => {
    writeUiState(api, {
      theme: appearance.theme,
      density: appearance.density,
      view: { ...readUiState(api)?.view, screen: route, focused },
    });
  }, [api, route, focused, appearance.theme, appearance.density]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((value) => !value);
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey &&
        event.key.toLowerCase() === "f"
      ) {
        event.preventDefault();
        setFocused((value) => !value);
      }
      if (event.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const data = controller.snapshot;
  const running =
    data?.runs.filter(
      (run) => run.state === "running" || run.state === "queued",
    ) ?? [];
  const pending =
    data?.learning.filter((note) => note.state === "pending").length ?? 0;

  const view = normaliseView(route);
  const selection = route.split("/")[1];
  const activeTab = tabForView(view);
  // A view whose tab was tier-filtered away must not leave the bar with
  // nothing marked current; fall back to the Dashboard's tab in that case.
  const currentTabId = tabs.some((tab) => tab.id === activeTab.id)
    ? activeTab.id
    : tabs[0]?.id;
  const workspaceName =
    init?.workspaceDir?.split(/[\\/]/).filter(Boolean).at(-1) ?? "No workspace";

  if (protocolError) return <ErrorState error={protocolError} />;

  const screenProps = {
    client,
    ready,
    sessions,
    workspaceDir: init?.workspaceDir,
    enabledTiers,
  };
  const studioProps = {
    ...screenProps,
    controller,
    view,
    onNavigate: navigate,
  };

  const body = AGENT_OPERATIONS.includes(view) ? (
    <AgentOperations {...studioProps} />
  ) : WORKSPACE_OPERATIONS.includes(view) ? (
    <WorkspaceOperations {...studioProps} />
  ) : GOVERNANCE.includes(view) ? (
    <GovernanceStudio {...studioProps} />
  ) : MODELING.includes(view) ? (
    <ModelingStudio {...studioProps} />
  ) : ORGANIZATION.includes(view) ? (
    <OrganizationStudio {...studioProps} />
  ) : EVIDENCE.includes(view) ? (
    <EvidenceStudio
      {...screenProps}
      initialTab={
        view === "ledger"
          ? "ledger"
          : view === "reconciliation"
            ? "reconciliation"
            : view === "external-agents"
            ? "sessions"
            : "recorder"
      }
    />
  ) : view === "agents" ? (
    <AgentsTab controller={controller} client={client} />
  ) : view === "skills" ? (
    <SkillsTab controller={controller} client={client} />
  ) : view === "instructions" ? (
    <InstructionsTab controller={controller} client={client} />
  ) : view === "phases" ? (
    <PhasesTab controller={controller} />
  ) : view === "runs" ? (
    <RunsTab controller={controller} onNavigate={navigate} />
  ) : view === "integrations" ? (
    <IntegrationsTab controller={controller} />
  ) : ["learning", "memory"].includes(view) ? (
    <LearningStudio controller={controller} onNavigate={navigate} />
  ) : ["deliverables", "packets"].includes(view) ? (
    <DeliveryStudio
      controller={controller}
      onNavigate={navigate}
      initialSelection={selection}
    />
  ) : view === "runtime" ? (
    <RuntimeStudio {...screenProps} controller={controller} />
  ) : view === "guide" ? (
    <GuideStudio onNavigate={navigate} />
  ) : view === "setup" ? (
    <FirstRunScreen {...screenProps} ledgerTip={ledgerTip} />
  ) : ["settings", "focus"].includes(view) ? (
    <>
      {view === "focus" && (
        <section className={w.panel}>
          <h1>A little more room to think.</h1>
          <p>
            Hide the chrome and keep the current task in view. The tab bar and
            command search remain available.
          </p>
          <button
            className={w.secondary}
            aria-pressed={focused}
            onClick={() => setFocused((value) => !value)}
          >
            {focused ? "Leave focus mode" : "Enter focus mode"}
          </button>
        </section>
      )}
      <SettingsStudio
        {...appearance}
        controller={controller}
        workspaceDir={init?.workspaceDir}
        openSettings={() =>
          client.notify({ type: "host/action", action: "open-settings" })
        }
      />
    </>
  ) : (
    <Dashboard
      snapshot={data}
      error={controller.error}
      enabledTiers={enabledTiers}
      sessions={sessions}
      onNavigate={navigate}
    />
  );

  return (
    <div className={s.shell}>
      <a className={s.skip} href="#workspace-content">
        Skip to workspace
      </a>

      <header className={s.masthead}>
        <div className={s.brand}>
          <svg className={s.brandMark} viewBox="0 0 32 34" fill="none" aria-hidden="true">
            <path
              d="M4 28V6l8 9 8-9v22 M12 15v13 M28 6v22 M4 22h24"
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
          <div className={s.brandText}>
            <strong>meridian loom</strong>
            <small title={init?.workspaceDir}>{workspaceName}</small>
          </div>
        </div>
        <div className={s.mastheadActions}>
          <button
            className={s.searchButton}
            onClick={() => setPalette(true)}
            aria-label="Search workspace and commands"
          >
            <Icon name="search" size={14} />
            <span>Search anything…</span>
            <kbd>⌘K</kbd>
          </button>
          <button
            className={s.iconButton}
            aria-label="Toggle focus mode"
            aria-pressed={focused}
            onClick={() => setFocused((value) => !value)}
          >
            <Icon name="focus" size={16} />
          </button>
          <button
            className={`${s.iconButton} ${s.bell}`}
            aria-label="Open activity"
            onClick={() => setActivity(true)}
          >
            <Icon name="bell" size={16} />
            {Boolean(pending || running.length) && (
              <span className={s.notificationDot} />
            )}
          </button>
          <span className={s.status} data-testid="crown-indicator">
            <span
              className={`${s.dot} ${
                !ready
                  ? s.dotWaiting
                  : sessions.status === "error"
                    ? s.dotError
                    : ""
              }`}
            />
            {!ready
              ? "Connecting to host"
              : sessions.status === "error"
                ? "Observer unavailable"
                : sessions.status === "ready" && sessions.data.sessions.length
                  ? `${sessions.data.sessions.length} sessions observed`
                  : "Watching for agent sessions"}
          </span>
        </div>
      </header>

      <nav className={s.tabs} aria-label="Workspace navigation">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            className={`${s.tab} ${
              index > 0 && tabs[index - 1].group !== tab.group ? s.groupEdge : ""
            }`}
            aria-label={tab.label}
            aria-current={currentTabId === tab.id ? "page" : undefined}
            title={tab.blurb}
            onClick={() => navigate(tab.views[0])}
          >
            <Icon name={tab.icon} size={16} />
            <span>{tab.label}</span>
            <TabBadge
              tab={tab}
              agents={data?.agents.length ?? 0}
              pending={pending}
              running={running.length}
            />
          </button>
        ))}
      </nav>

      {activeTab.views.length > 1 && currentTabId === activeTab.id && (
        <nav className={s.subtabs} aria-label={`${activeTab.label} views`}>
          {activeTab.views.map((id) => (
            <button
              key={id}
              className={s.subtab}
              aria-current={view === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              {subViewLabel(id)}
            </button>
          ))}
        </nav>
      )}

      {preview && (
        <div className={`${s.banner} ${s.bannerPreview}`} role="note">
          Preview workspace · sample data · changes stay in this tab · no agents
          are executed
        </div>
      )}
      {controller.error && (
        <div className={`${s.banner} ${s.bannerError}`} role="alert">
          <span>{controller.error}</span>
          <button
            className={s.linkButton}
            onClick={() => void controller.refresh()}
          >
            Reconnect
          </button>
        </div>
      )}
      {!init?.workspaceDir && ready && (
        <div className={s.banner}>
          <span>
            Open a workspace folder in VS Code to save agents, skills and
            deliverables.
          </span>
          <button
            className={s.linkButton}
            onClick={() =>
              client.notify({ type: "host/action", action: "open-folder" })
            }
          >
            Open folder
          </button>
        </div>
      )}

      <main id="workspace-content" ref={mainRef} tabIndex={-1} className={s.main}>
        {!data && !controller.error && (
          <LoadingState label="Connecting to your workspace…" />
        )}
        <ScreenBoundary key={route} onReset={() => navigate("dashboard")}>
          <Suspense fallback={<LoadingState label="Opening workspace view…" />}>
            {body}
          </Suspense>
        </ScreenBoundary>
      </main>

      <footer className={s.footer}>
        <span>Meridian Loom · independent by design</span>
        <span>
          {data
            ? `${data.agents.filter((agent) => agent.mode === "active").length} active · ${data.agents.filter((agent) => agent.mode === "learning").length} learning`
            : "Waiting for workspace"}{" "}
          ·{" "}
          <button className={s.linkButton} onClick={() => navigate("setup")}>
            Guided setup
          </button>
        </span>
      </footer>

      {palette && (
        <CommandPalette
          tabs={tabs}
          onNavigate={navigate}
          onClose={() => setPalette(false)}
          agents={
            data?.agents.map((agent) => ({
              id: agent.id,
              name: agent.name,
              role: agent.role,
            })) ?? []
          }
        />
      )}

      {activity && (
        <Dialog
          title="Your workspace activity"
          description="Actual run history and learning reviews from this workspace."
          wide
          onClose={() => setActivity(false)}
        >
          {pending > 0 && (
            <div className={w.settingRow}>
              <div>
                <h3>{pending} learning notes need your review</h3>
                <p>Decide which lessons belong in your agents’ memory.</p>
              </div>
              <button
                className={w.secondary}
                onClick={() => {
                  setActivity(false);
                  navigate("learning");
                }}
              >
                Review notes
              </button>
            </div>
          )}
          {running.length > 0 && (
            <div className={w.settingRow}>
              <div>
                <h3>{running.length} queued or running tasks</h3>
                <p>Stopping affects only tasks launched by this workbench.</p>
              </div>
              <button
                className={w.secondary}
                disabled={stopping}
                onClick={async () => {
                  setStopping(true);
                  setStopError(undefined);
                  try {
                    for (const run of running)
                      await controller.execute("run/cancel", { id: run.id });
                  } catch (cause) {
                    setStopError((cause as Error).message);
                  } finally {
                    setStopping(false);
                  }
                }}
              >
                <Icon name="stop" size={13} /> Stop workbench tasks
              </button>
            </div>
          )}
          {stopError && <p role="alert">{stopError}</p>}
          {data?.runs.length ? (
            [...data.runs]
              .reverse()
              .slice(0, 30)
              .map((run) => (
                <div className={w.checkRow} key={run.id}>
                  <Icon
                    name={run.state === "completed" ? "check" : "runtime"}
                    size={18}
                  />
                  <div>
                    <strong>
                      {run.agentName} · {run.state}
                    </strong>
                    <p>{run.prompt.slice(0, 200)}</p>
                    <p>{new Date(run.startedAt).toLocaleString()}</p>
                    {run.error && <p>{run.error}</p>}
                  </div>
                  <button
                    className={w.textButton}
                    onClick={() => {
                      setActivity(false);
                      navigate("runs");
                    }}
                  >
                    Inspect
                  </button>
                </div>
              ))
          ) : (
            <div className={w.empty}>
              <Icon name="bell" size={30} />
              <h3>Room for what comes next.</h3>
              <p>
                Runs and learning reviews will appear here as you use the
                workbench.
              </p>
            </div>
          )}
        </Dialog>
      )}
    </div>
  );
}

/**
 * The one number a tab is allowed to carry. Only counts a user acts on:
 * agents they own, notes awaiting review, runs in flight. A badge for
 * anything else is noise that trains people to ignore badges.
 */
function TabBadge({
  tab,
  agents,
  pending,
  running,
}: {
  tab: WorkbenchTab;
  agents: number;
  pending: number;
  running: number;
}) {
  const count =
    tab.id === "agents" ? agents : tab.id === "learning" ? pending : tab.id === "runs" ? running : 0;
  if (!count) return null;
  return <span className={s.tabCount}>{count}</span>;
}

/** Sub-view labels come from the shared surface registry where one exists. */
function subViewLabel(id: string): string {
  const own: Record<string, string> = {
    dashboard: "Dashboard",
    runs: "Runs",
    phases: "SDLC phases",
    agents: "Roster",
    skills: "Skills",
    instructions: "Instructions",
    deliverables: "Deliverables",
    settings: "Settings",
    evidence: "Overview",
    portfolio: "Portfolio",
  };
  return own[id] ?? routeLabel(id);
}

function CommandPalette({
  tabs,
  onNavigate,
  onClose,
  agents,
}: {
  tabs: readonly WorkbenchTab[];
  onNavigate: (route: string) => void;
  onClose: () => void;
  agents: { id: string; name: string; role: string }[];
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  // Every view of every unlocked tab is addressable, so search reaches
  // surfaces that are two clicks deep in the bar.
  const commands = [
    ...tabs.flatMap((tab) =>
      tab.views.map((viewId, index) => ({
        id: `${tab.id}:${viewId}`,
        label: index === 0 ? tab.label : `${tab.label} · ${subViewLabel(viewId)}`,
        description: index === 0 ? tab.blurb : subViewDescription(viewId),
        icon: tab.icon,
        route: viewId,
        group: tab.group as string,
      })),
    ),
    ...agents.map((agent) => ({
      id: `agent-${agent.id}`,
      label: agent.name,
      description: agent.role,
      icon: "agents" as const,
      route: `agents/${agent.id}`,
      group: "Agents",
    })),
  ].filter((item) =>
    `${item.label} ${item.description} ${item.group}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const choose = (index: number) => {
    const item = commands[index];
    if (item) onNavigate(item.route);
  };
  return (
    <Dialog title="Find your next step" onClose={onClose}>
      <div className={w.commandSearch}>
        <Icon name="search" />
        <input
          autoFocus
          aria-label="Search commands"
          placeholder="Search tabs, views, agents and actions…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setSelected((value) => Math.min(value + 1, commands.length - 1));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setSelected((value) => Math.max(value - 1, 0));
            }
            if (event.key === "Enter") {
              event.preventDefault();
              choose(selected);
            }
          }}
        />
      </div>
      <div className={w.commandList}>
        {commands.slice(0, 60).map((item, index) => (
          <button
            key={item.id}
            className={w.command}
            data-selected={selected === index}
            onClick={() => choose(index)}
          >
            <Icon name={item.icon} size={18} />
            <span>
              <strong>{item.label}</strong>
              <small>{item.description}</small>
            </span>
            <Icon name="arrow" size={14} />
          </button>
        ))}
        {commands.length === 0 && (
          <p>No matches. Try “agents”, “skills”, “phases”, or “evidence”.</p>
        )}
      </div>
    </Dialog>
  );
}

function subViewDescription(id: string): string {
  return routeLabel(id) === "Overview" ? "Workspace view" : routeLabel(id);
}

class ScreenBoundary extends Component<
  { children: ReactNode; onReset: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className={w.empty} role="alert">
        <h2>This view could not be displayed.</h2>
        <p>
          Your saved workspace data remains available. Reopen the view or return
          to the Dashboard.
        </p>
        <button className={w.secondary} onClick={this.props.onReset}>
          Return to Dashboard
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
