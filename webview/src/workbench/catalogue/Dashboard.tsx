import {
  SDLC_PHASES,
  SDLC_PHASE_LABELS,
  type WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import type { ScreenProps } from "../../screens/registry";
import { VendorTag } from "../../components/VendorTag";
import {
  Dot,
  HeatStrip,
  Ring,
  StackedBar,
  Stat,
  type Signal,
} from "../../components/viz/Viz";
import { Button, Empty, Notice, Page, Panel, Tag } from "./common";
import s from "./catalogue.module.css";

const phaseColor = (phase: (typeof SDLC_PHASES)[number]) =>
  `var(--ml-phase-${phase})`;

/** Run state as a health signal, shared by the strip and the recent list. */
function runSignal(state: string): Signal {
  if (state === "completed") return "ok";
  if (state === "failed") return "fail";
  if (state === "running" || state === "queued") return "warn";
  return "idle";
}

/**
 * The Dashboard — the landing tab.
 *
 * This is what the user sees the instant they select Meridian Loom in the
 * Activity Bar, so it answers the questions asked at that moment, in order:
 * is the plugin working, who is on my team, what is running, and what needs
 * me. Everything else is one tab away.
 *
 * It states readiness honestly. Where execution is blocked, it says what is
 * blocking it and offers the action that unblocks it, rather than showing a
 * disabled control with no explanation. Where a count is zero, it says what
 * would make it non-zero.
 */

export interface DashboardProps {
  snapshot: WorkbenchSnapshot | undefined;
  error: string | null;
  enabledTiers: readonly string[];
  /** The live `observe/sessions` query the shell already polls. */
  sessions: ScreenProps["sessions"];
  onNavigate: (tab: string) => void;
}

export function Dashboard({
  snapshot,
  error,
  enabledTiers,
  sessions,
  onNavigate,
}: DashboardProps) {
  const agents = snapshot?.agents ?? [];
  const active = agents.filter((agent) => agent.mode === "active");
  const learning = agents.filter((agent) => agent.mode !== "active");
  const runs = snapshot?.runs ?? [];
  const live = runs.filter(
    (run) => run.state === "running" || run.state === "queued",
  );
  const deliverables = snapshot?.deliverables ?? [];
  const pendingNotes = (snapshot?.learning ?? []).filter(
    (note) => note.state === "pending",
  );
  const skills = snapshot?.skills ?? [];
  const instructions = snapshot?.instructions ?? [];
  const integrations = snapshot?.integrations ?? [];
  const reachable = integrations.filter((entry) => entry.lastProbe?.ok);
  const unreachable = integrations.filter(
    (entry) => entry.lastProbe && !entry.lastProbe.ok,
  );
  const capability = snapshot?.capabilities;

  const coveredPhases = SDLC_PHASES.filter((phase) =>
    active.some((agent) => agent.phases.includes(phase)),
  );

  // Ordered by what most deserves the user's attention next.
  const attention: { text: string; tab: string; cta: string }[] = [];
  if (!capability?.workspaceOpen)
    attention.push({
      text: "No workspace is open, so nothing can be recorded or run.",
      tab: "runtime",
      cta: "Open runtime",
    });
  if (!agents.length)
    attention.push({
      text: "No agents yet. Add one, or import a package as Markdown or ZIP.",
      tab: "agents",
      cta: "Add an agent",
    });
  else if (!active.length)
    attention.push({
      text: `All ${agents.length} agent(s) are in Learning, so no deliverable can be worked.`,
      tab: "agents",
      cta: "Activate an agent",
    });
  if (active.length && !coveredPhases.length)
    attention.push({
      text: "No active agent is tagged to any SDLC phase, so none will be convened.",
      tab: "phases",
      cta: "Tag phases",
    });
  if (unreachable.length)
    attention.push({
      text: `${unreachable.length} connection(s) could not be reached at the last test.`,
      tab: "integrations",
      cta: "See why",
    });
  if (pendingNotes.length)
    attention.push({
      text: `${pendingNotes.length} memory note(s) are waiting for your review.`,
      tab: "learning",
      cta: "Review notes",
    });
  if (capability && !capability.executionReady && capability.executionBlockedReason)
    attention.push({
      text: capability.executionBlockedReason,
      tab: "runtime",
      cta: "See readiness",
    });

  return (
    <Page
      title="Dashboard"
      blurb="Your team, your work, and what needs you — everything else is one tab away."
    >
      <Notice tone="error">{error}</Notice>

      {!snapshot ? (
        <Empty title="Connecting to the workspace…">
          The workbench is loading its state. If this persists, check the
          Runtime tab for diagnostics.
        </Empty>
      ) : null}

      <div className={s.three}>
        <Stat
          label="Active agents"
          value={active.length}
          accent="var(--ml-signal-ok)"
          hint={
            active.length
              ? "taking part in deliverables"
              : "nothing will be convened"
          }
          onClick={() => onNavigate("agents")}
          visual={
            agents.length ? (
              <StackedBar
                label="Roster by participation"
                legend={false}
                segments={[
                  { label: "Active", value: active.length, signal: "ok" },
                  { label: "Learning", value: learning.length, signal: "idle" },
                ]}
              />
            ) : undefined
          }
        />
        <Stat
          label="Learning"
          value={learning.length}
          accent="var(--ml-signal-idle)"
          hint="not convened; collecting memory"
          onClick={() => onNavigate("learning")}
        />
        <Stat
          label="Running now"
          value={live.length}
          accent="var(--ml-signal-warn)"
          hint={live.length ? "with output and stop controls" : "nothing in flight"}
          onClick={() => onNavigate("runs")}
          visual={
            runs.length ? (
              <HeatStrip
                label="Recent run outcomes"
                cells={runs.slice(0, 24).map((run) => ({
                  id: run.id,
                  signal: runSignal(run.state),
                  title: `${run.agentName}: ${run.state}`,
                }))}
              />
            ) : undefined
          }
        />
        <Stat
          label="Phases covered"
          value={`${coveredPhases.length} / ${SDLC_PHASES.length}`}
          accent="var(--ml-accent)"
          hint="by an active agent"
          onClick={() => onNavigate("phases")}
          visual={
            <Ring
              value={coveredPhases.length}
              total={SDLC_PHASES.length}
              label="SDLC phases covered by an active agent"
              caption={`${coveredPhases.length}/${SDLC_PHASES.length}`}
            />
          }
        />
        <Stat
          label="Skills"
          value={skills.filter((skill) => skill.enabled).length}
          accent="var(--ml-phase-build)"
          hint={`${skills.length} in the catalogue, ${instructions.filter((entry) => entry.enabled).length} instruction files enabled`}
          onClick={() => onNavigate("skills")}
        />
        <Stat
          label="Connections"
          value={integrations.filter((entry) => entry.enabled).length}
          accent="var(--ml-phase-operate)"
          hint={
            integrations.length
              ? `${reachable.length} reachable of ${integrations.length}`
              : "no systems connected yet"
          }
          onClick={() => onNavigate("integrations")}
          visual={
            integrations.length ? (
              <HeatStrip
                label="Connection health"
                cells={integrations.map((entry) => ({
                  id: entry.id,
                  signal: entry.lastProbe
                    ? entry.lastProbe.ok
                      ? "ok"
                      : "fail"
                    : "idle",
                  title: `${entry.name}: ${
                    entry.lastProbe
                      ? entry.lastProbe.ok
                        ? "reachable"
                        : "unreachable"
                      : "never tested"
                  }`,
                }))}
              />
            ) : undefined
          }
        />
      </div>

      <Panel
        title="What needs you"
        hint="Ordered by what most affects whether work can proceed."
      >
        {attention.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {attention.map((item) => (
              <div key={item.text} className={s.toolbar}>
                <p className={s.cardBody} style={{ flex: 1, minWidth: 220 }}>
                  {item.text}
                </p>
                <Button onClick={() => onNavigate(item.tab)}>{item.cta}</Button>
              </div>
            ))}
          </div>
        ) : (
          <p className={s.cardBody}>
            Nothing is blocked. {active.length} active agent(s) cover{" "}
            {coveredPhases.length} of {SDLC_PHASES.length} phases, and no
            reviews are outstanding.
          </p>
        )}
      </Panel>

      <div className={s.split}>
        <Panel
          title="Team by phase"
          hint="Which phases your active roster can take on."
          action={<Button onClick={() => onNavigate("phases")}>Manage</Button>}
        >
          {!active.length ? (
            <Empty title="No active agents.">
              Activate an agent on the Agents tab to build a delivery chain.
            </Empty>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {SDLC_PHASES.map((phase) => {
                const here = active.filter((agent) =>
                  agent.phases.includes(phase),
                );
                return (
                  <div key={phase} className={s.toolbar}>
                    <Dot
                      signal={here.length ? "ok" : "idle"}
                      title={
                        here.length
                          ? `${SDLC_PHASE_LABELS[phase]}: covered`
                          : `${SDLC_PHASE_LABELS[phase]}: no active agent`
                      }
                    />
                    <span
                      style={{
                        flex: 1,
                        minWidth: 160,
                        fontSize: "0.8125rem",
                        borderLeft: `2px solid ${phaseColor(phase)}`,
                        paddingLeft: 8,
                      }}
                    >
                      {SDLC_PHASE_LABELS[phase]}
                    </span>
                    {here.length ? (
                      <span className={s.cardMeta}>
                        {here.map((agent) => agent.name).join(", ")}
                      </span>
                    ) : (
                      <Tag tone="warn">No agent</Tag>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel
          title="Recent runs"
          hint="The last few agent runs in this workspace."
          action={<Button onClick={() => onNavigate("runs")}>All runs</Button>}
        >
          {!runs.length ? (
            <Empty title="No runs yet.">
              Run an agent from the Agents tab, or dispatch a deliverable to
              the active team.
            </Empty>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {runs.slice(0, 6).map((run) => (
                <div key={run.id} className={s.toolbar}>
                  <Dot signal={runSignal(run.state)} title={run.state} />
                  <span style={{ flex: 1, minWidth: 160, fontSize: "0.8125rem" }}>
                    {run.agentName}
                    <span className={s.cardMeta}> · {run.prompt.slice(0, 60)}</span>
                  </span>
                  <Tag
                    tone={
                      run.state === "completed"
                        ? "active"
                        : run.state === "failed"
                          ? "warn"
                          : "neutral"
                    }
                  >
                    {run.state}
                  </Tag>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Observed right now"
        hint="Agent sessions running in this workspace, whether or not Meridian started them."
        action={
          <Button onClick={() => onNavigate("evidence")}>Open evidence</Button>
        }
      >
        {sessions.status === "error" ? (
          <Notice tone="error">
            Observation is unavailable. Open Runtime to diagnose the connection.
          </Notice>
        ) : sessions.status !== "ready" ? (
          <p className={s.cardBody}>Waiting for observer data…</p>
        ) : (
          <>
            {sessions.data.warnings.length > 0 ? (
              <p className={s.notice} data-testid="observer-warnings">
                {sessions.data.warnings.join(" · ")}
              </p>
            ) : null}
            {sessions.data.sessions.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {sessions.data.sessions.slice(0, 8).map((session) => (
                  <div key={session.sessionId} className={s.toolbar}>
                    {/* X-27: never a bare vendor name — the tag carries the
                        observation confidence in its accessible name. */}
                    <VendorTag
                      vendor={session.vendor}
                      confidence={session.confidence}
                    />
                    <span className={s.cardMeta} style={{ flex: 1 }}>
                      {session.detail}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className={s.cardBody}>
                No agent sessions observed yet. Meridian records the ones it
                starts and the ones it merely sees.
              </p>
            )}
          </>
        )}
      </Panel>

      <Panel
        title="Deliverables"
        hint="Briefs the active team works on together."
        action={
          <Button onClick={() => onNavigate("deliverables")}>Open board</Button>
        }
      >
        {!deliverables.length ? (
          <Empty title="No deliverables yet.">
            Write a brief with its acceptance criteria, then dispatch it to the
            active roster.
          </Empty>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {deliverables.slice(0, 5).map((item) => (
              <div key={item.id} className={s.toolbar}>
                <span style={{ flex: 1, minWidth: 200, fontSize: "0.8125rem" }}>
                  {item.title}
                </span>
                <Tag
                  tone={
                    item.state === "completed"
                      ? "active"
                      : item.state === "failed"
                        ? "warn"
                        : "neutral"
                  }
                >
                  {item.state}
                </Tag>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {!enabledTiers.includes("governor") ? (
        <Notice tone="info">
          The Governor tier is off, so gates, roles, trust measures and spend
          are unavailable and hosted agents cannot run. Enable it in the
          extension settings from the Settings tab.
        </Notice>
      ) : null}
    </Page>
  );
}
