import { useMemo, useState } from "react";
import {
  SDLC_PHASE_LABELS,
  type WorkbenchRun,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import { Dot, HeatStrip, Stat, type Signal } from "../../components/viz/Viz";
import {
  Button,
  Confirm,
  Empty,
  Notice,
  Page,
  Panel,
  Tag,
  Toolbar,
  useAction,
  useFilter,
} from "./common";
import s from "./catalogue.module.css";

/**
 * The Runs tab.
 *
 * Every execution the workbench started, live and past, with the three things
 * a person actually wants while one is in flight: what it is saying, a way to
 * redirect it, and a way to stop it.
 *
 * Two honesty rules govern this surface. Steering is queued, not delivered —
 * the row says `queued` until the adapter accepts it, because claiming a
 * message landed when it has not is worse than saying nothing. And stopping
 * is scoped: it ends runs this workbench launched, and says so, because an
 * agent is portable and may well be running elsewhere too.
 */

const STATES = [
  { value: "live", label: "Live" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
] as const;

type StateFilter = (typeof STATES)[number]["value"];

function isLive(run: WorkbenchRun) {
  return run.state === "running" || run.state === "queued";
}

/** Tag tones and viz signals are different vocabularies; keep them separate
    rather than casting one into the other and hoping the cases line up. */
function tone(run: WorkbenchRun): "active" | "warn" | "neutral" | "learning" {
  if (run.state === "completed") return "active";
  if (run.state === "failed") return "warn";
  if (isLive(run)) return "learning";
  return "neutral";
}

function runSignal(run: WorkbenchRun): Signal {
  if (run.state === "completed") return "ok";
  if (run.state === "failed") return "fail";
  if (isLive(run)) return "warn";
  return "idle";
}

function when(value: string | undefined) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function elapsed(run: WorkbenchRun) {
  const start = new Date(run.startedAt).getTime();
  const end = run.finishedAt ? new Date(run.finishedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60
    ? `${minutes}m ${seconds % 60}s`
    : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export interface RunsTabProps {
  controller: WorkbenchController;
  onNavigate: (tab: string) => void;
}

export function RunsTab({ controller, onNavigate }: RunsTabProps) {
  const snapshot = controller.snapshot;
  const runs = snapshot?.runs ?? [];
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<StateFilter>("all");
  const [selectedId, setSelectedId] = useState<string>();
  const [steer, setSteer] = useState("");
  const [stoppingAll, setStoppingAll] = useState(false);
  const action = useAction();

  // Newest first: the run you care about is almost always the last one started.
  const ordered = useMemo(
    () =>
      [...runs].sort(
        (a, b) =>
          new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
      ),
    [runs],
  );
  const live = ordered.filter(isLive);
  const byState = ordered.filter((run) =>
    filter === "all"
      ? true
      : filter === "live"
        ? isLive(run)
        : run.state === filter,
  );
  const filtered = useFilter(byState, query, (run) => [
    run.agentName,
    run.prompt,
    run.state,
    run.error,
  ]);

  // Follow the newest live run unless the user has picked something else.
  const selected =
    ordered.find((run) => run.id === selectedId) ?? live[0] ?? ordered[0];

  const stop = (run: WorkbenchRun) =>
    action.run(
      () => controller.execute("run/cancel", { id: run.id }),
      `Asked ${run.agentName} to stop. Only this workbench's run is affected.`,
    );

  const sendSteer = async (run: WorkbenchRun) => {
    const message = steer.trim();
    if (!message) return;
    const ok = await action.run(
      () => controller.execute("run/steer", { id: run.id, message }),
      "Steering message queued. It is delivered when the adapter accepts it.",
    );
    if (ok) setSteer("");
  };

  return (
    <Page
      title="Runs"
      blurb="Every execution this workbench started — what it is doing, what it said, and how to redirect or stop it."
      actions={
        live.length ? (
          <Button variant="danger" icon="stop" onClick={() => setStoppingAll(true)}>
            Stop all {live.length} live run{live.length === 1 ? "" : "s"}
          </Button>
        ) : undefined
      }
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      <div className={s.three}>
        <Stat
          label="Live"
          value={live.length}
          hint="running or queued"
          accent="var(--ml-signal-warn)"
          visual={
            ordered.length ? (
              <HeatStrip
                label="Run outcomes, newest first"
                cells={ordered.slice(0, 32).map((entry) => ({
                  id: entry.id,
                  signal: runSignal(entry),
                  title: `${entry.agentName}: ${entry.state}`,
                }))}
              />
            ) : undefined
          }
        />
        <Stat
          label="Completed"
          value={ordered.filter((run) => run.state === "completed").length}
          hint="finished without error"
          accent="var(--ml-signal-ok)"
        />
        <Stat
          label="Failed"
          value={ordered.filter((run) => run.state === "failed").length}
          hint="ended with an error to read"
          accent="var(--ml-signal-fail)"
        />
        <Stat
          label="Cancelled"
          value={ordered.filter((run) => run.state === "cancelled").length}
          hint="stopped from here"
          accent="var(--ml-signal-idle)"
        />
      </div>

      {!runs.length ? (
        <Empty
          title="No runs yet."
          action={
            <Button variant="primary" onClick={() => onNavigate("agents")}>
              Go to Agents
            </Button>
          }
        >
          Run an agent directly from the Agents tab, or write a deliverable and
          dispatch it to the whole active team.
        </Empty>
      ) : (
        <div className={s.split}>
          <Panel title="History" hint="Newest first.">
            <Toolbar
              value={query}
              onChange={setQuery}
              placeholder="Search runs by agent, prompt or error"
            />
            <div className={s.chipRow}>
              {STATES.map((state) => (
                <button
                  key={state.value}
                  type="button"
                  className={s.chip}
                  aria-pressed={filter === state.value}
                  onClick={() => setFilter(state.value)}
                >
                  <span className={s.chipMark} aria-hidden="true">
                    {filter === state.value ? "✓" : "+"}
                  </span>
                  {state.label}
                </button>
              ))}
            </div>
            {!filtered.length ? (
              <Empty title="No run matches that filter.">
                Clear the search or choose All to see every one of the{" "}
                {runs.length} recorded runs.
              </Empty>
            ) : (
              <div className={s.runList}>
                {filtered.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    className={s.runItem}
                    aria-current={run.id === selected?.id ? "true" : undefined}
                    onClick={() => setSelectedId(run.id)}
                  >
                    <span className={s.runItemHead}>
                      <strong className={s.cardName}>
                        <Dot signal={runSignal(run)} title={run.state} />{" "}
                        {run.agentName}
                      </strong>
                      <Tag tone={tone(run)}>{run.state}</Tag>
                    </span>
                    <span className={s.cardBody}>
                      {run.phase
                        ? SDLC_PHASE_LABELS[run.phase]
                        : run.prompt.slice(0, 120) || "(no briefing recorded)"}
                    </span>
                    <span className={s.cardMeta}>
                      {when(run.startedAt)} · {elapsed(run)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {selected ? (
            <Panel
              title={selected.agentName}
              hint={`${
                selected.phase
                  ? `Convened for ${SDLC_PHASE_LABELS[selected.phase]} · `
                  : ""
              }Started ${when(selected.startedAt)} · ${elapsed(selected)}${
                selected.finishedAt ? ` · finished ${when(selected.finishedAt)}` : ""
              }`}
              action={<Tag tone={tone(selected)}>{selected.state}</Tag>}
            >
              <p className={s.cardMeta}>
                Briefing sent to the agent — brief, role, phase, instruction
                files, skills, connected systems and accepted memory, exactly
                as it was received
              </p>
              <pre className={s.code}>{selected.prompt || "(none)"}</pre>

              {selected.error ? (
                <Notice tone="error">{selected.error}</Notice>
              ) : null}
              {selected.stopReason ? (
                <Notice tone="info">Stopped: {selected.stopReason}</Notice>
              ) : null}

              <p className={s.cardMeta}>Output</p>
              {selected.output ? (
                <pre className={s.code}>{selected.output}</pre>
              ) : (
                <p className={s.cardBody}>
                  {isLive(selected)
                    ? "No output recorded yet. It appears here as the adapter reports it."
                    : "This run recorded no output."}
                </p>
              )}

              {selected.steering?.length ? (
                <>
                  <p className={s.cardMeta}>Steering</p>
                  <div className={s.runList}>
                    {selected.steering.map((message) => (
                      <div key={message.sequence} className={s.runItemStatic}>
                        <span className={s.runItemHead}>
                          <span className={s.cardBody}>{message.message}</span>
                          <Tag
                            tone={message.state === "sent" ? "active" : "learning"}
                          >
                            {message.state}
                          </Tag>
                        </span>
                        <span className={s.cardMeta}>
                          {when(message.submittedAt)}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}

              {isLive(selected) ? (
                <form
                  className={s.toolbar}
                  onSubmit={(event) => {
                    event.preventDefault();
                    void sendSteer(selected);
                  }}
                >
                  <div className={s.search} style={{ flex: 1 }}>
                    <input
                      value={steer}
                      placeholder="Send a steering message to this run…"
                      aria-label="Steering message"
                      onChange={(event) => setSteer(event.target.value)}
                    />
                  </div>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={action.busy || !steer.trim()}
                  >
                    Steer
                  </Button>
                  <Button
                    variant="danger"
                    icon="stop"
                    disabled={action.busy}
                    onClick={() => void stop(selected)}
                  >
                    Stop
                  </Button>
                </form>
              ) : null}

              {selected.deliverableId ? (
                <div className={s.cardActions}>
                  <Button onClick={() => onNavigate("deliverables")}>
                    Open the deliverable this run belongs to
                  </Button>
                </div>
              ) : null}

              {selected.sessionId ? (
                <p className={s.cardMeta}>Session {selected.sessionId}</p>
              ) : null}
            </Panel>
          ) : null}
        </div>
      )}

      {stoppingAll ? (
        <Confirm
          title={`Stop ${live.length} live run${live.length === 1 ? "" : "s"}?`}
          detail={
            <>
              <p>
                Each run this workbench launched is asked to stop. Work already
                written to disk by an agent is not undone.
              </p>
              <p>
                Agents are portable: a session the same agent is running outside
                Meridian Loom is untouched by this.
              </p>
            </>
          }
          confirmLabel="Stop the live runs"
          busy={action.busy}
          error={action.error}
          onCancel={() => setStoppingAll(false)}
          onConfirm={() =>
            void action
              .run(async () => {
                for (const run of live)
                  await controller.execute("run/cancel", { id: run.id });
              }, `Stop requested for ${live.length} run(s).`)
              .then((ok) => ok && setStoppingAll(false))
          }
        />
      ) : null}
    </Page>
  );
}
