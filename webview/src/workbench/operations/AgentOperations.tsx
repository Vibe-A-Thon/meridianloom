import { useMemo, useState } from "react";
import type {
  AgentMode,
  WorkbenchAgent,
} from "../../../../shared/ts/workbench";
import { Dialog } from "../Dialog";
import {
  StudioPage,
  Empty,
  ErrorNotice,
  csv,
  exportText,
  stamp,
  useViewState,
  type OperationsProps,
} from "./shared";
import { RegistryBay } from "./RegistryBay";
import s from "./operations.module.css";

const COLUMNS = [
  "Role",
  "Vendor",
  "Participation",
  "Runtime",
  "Queue",
  "Completed turns",
  "Last run",
] as const;
export function AgentOperations(props: OperationsProps) {
  const { view, controller, onNavigate } = props;
  const agents = controller.snapshot?.agents ?? [];
  const runs = controller.snapshot?.runs ?? [];
  const [query, setQuery] = useViewState("rosterSearch", "");
  const [filter, setFilter] = useViewState("rosterFilter", "all");
  const [sort, setSort] = useViewState("rosterSort", "name");
  const [selected, setSelected] = useViewState<string[]>("selectedAgents", []);
  const [columns, setColumns] = useViewState<string[]>("rosterColumns", [
    ...COLUMNS,
  ]);
  const [floorList, setFloorList] = useViewState("floorList", false);
  const [error, setError] = useState<string>();
  const [change, setChange] = useState<{ ids: string[]; mode: AgentMode }>();
  const [compare, setCompare] = useState(false);
  const [columnDialog, setColumnDialog] = useState(false);
  const [inspected, setInspected] = useState<string>();
  const shown = useMemo(
    () =>
      agents
        .filter(
          (a) =>
            `${a.name} ${a.role} ${a.vendor} ${a.id}`
              .toLowerCase()
              .includes(query.toLowerCase()) &&
            (filter === "all" || a.mode === filter),
        )
        .sort((a, b) =>
          sort === "last-run"
            ? (b.lastRunAt ?? "").localeCompare(a.lastRunAt ?? "")
            : sort === "mode"
              ? a.mode.localeCompare(b.mode) || a.name.localeCompare(b.name)
              : a.name.localeCompare(b.name),
        ),
    [agents, query, filter, sort],
  );
  const selectedAgents = agents.filter((a) => selected.includes(a.id));
  const done = (id: string) =>
    runs.filter((run) => run.agentId === id && run.state === "completed")
      .length;
  const queued = (id: string) =>
    runs.filter(
      (run) => run.agentId === id && ["queued", "running"].includes(run.state),
    ).length;
  const describe = (agent: WorkbenchAgent) =>
    agent.runtime === "running"
      ? "Executing an explicit task"
      : agent.mode === "learning"
        ? agent.learningState === "review"
          ? "Memory awaits review"
          : "Waiting for reviewed feedback"
        : "Ready for the next deliverable";
  const exportRoster = () =>
    exportText(
      "meridian-agent-roster.csv",
      csv([
        ["ID", "Name", ...COLUMNS],
        ...shown.map((a) => [
          a.id,
          a.name,
          a.role,
          a.vendor,
          a.mode,
          a.runtime,
          queued(a.id),
          done(a.id),
          a.lastRunAt ?? "",
        ]),
      ]),
      "text/csv",
    );
  const modeChange = async () => {
    if (!change) return;
    setError(undefined);
    try {
      for (const id of change.ids)
        await controller.execute("agent/mode", { id, mode: change.mode });
      setChange(undefined);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };
  const inspect = (id: string) => {
    setInspected(id);
    setSelected([id]);
  };
  const tabs = (
    <div className={s.tabs} aria-label="Agent views">
      {[
        ["floor", "Loom floor"],
        ["watch", "Dense roster"],
        ["inspector", "Agent inspector"],
        ["onboarding", "Onboarding"],
        ["adapters", "Adapter bay"],
      ].map(([route, label]) => (
        <button
          key={route}
          aria-pressed={view === route}
          onClick={() => onNavigate(route)}
        >
          {label}
        </button>
      ))}
    </div>
  );
  const toolbar = (
    <div className={s.toolbar}>
      <div className={s.inline}>
        <input
          aria-label="Search agents"
          placeholder="Search names, roles, vendors…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="Participation filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All agents</option>
          <option value="active">Active</option>
          <option value="learning">Learning</option>
        </select>
      </div>
      <div className={s.actions}>
        <select
          aria-label="Sort agents"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="name">Name</option>
          <option value="mode">Participation</option>
          <option value="last-run">Latest run</option>
        </select>
        <button onClick={exportRoster}>Export CSV</button>
      </div>
    </div>
  );
  const table = (
    <div className={s.tableWrap}>
      <table className={s.table}>
        <caption className="sr-only">
          Agent runtime and participation from the workspace
        </caption>
        <thead>
          <tr>
            <th>Agent</th>
            {COLUMNS.filter((c) => columns.includes(c)).map((c) => (
              <th key={c}>{c}</th>
            ))}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((a) => (
            <tr key={a.id}>
              <td>
                <label className={s.inline}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${a.name}`}
                    checked={selected.includes(a.id)}
                    onChange={(e) =>
                      setSelected((prev) =>
                        e.target.checked
                          ? [...prev, a.id]
                          : prev.filter((id) => id !== a.id),
                      )
                    }
                  />
                  <button onClick={() => inspect(a.id)}>{a.name}</button>
                </label>
                <small>{a.id}</small>
              </td>
              {columns.includes("Role") && <td>{a.role}</td>}
              {columns.includes("Vendor") && (
                <td>{a.vendor || "Custom ACP"}</td>
              )}
              {columns.includes("Participation") && (
                <td>
                  <span className={s.badge} data-state={a.mode}>
                    {a.mode === "active" ? "Active" : "Learning"}
                  </span>
                </td>
              )}
              {columns.includes("Runtime") && <td>{a.runtime}</td>}
              {columns.includes("Queue") && <td>{queued(a.id)}</td>}
              {columns.includes("Completed turns") && <td>{done(a.id)}</td>}
              {columns.includes("Last run") && <td>{stamp(a.lastRunAt)}</td>}
              <td>
                <button
                  onClick={() =>
                    setChange({
                      ids: [a.id],
                      mode: a.mode === "active" ? "learning" : "active",
                    })
                  }
                >
                  {a.mode === "active" ? "Deactivate" : "Activate"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  const rooms = [
    {
      name: "Working",
      detail: "Running ACP tasks",
      list: shown.filter((a) => a.runtime === "running"),
    },
    {
      name: "Ready",
      detail: "Active; waiting for a task",
      list: shown.filter((a) => a.mode === "active" && a.runtime !== "running"),
    },
    {
      name: "Learning dojo",
      detail: "Excluded from delivery",
      list: shown.filter((a) => a.mode === "learning"),
    },
  ];
  const floor = (
    <>
      <div className={s.toolbar}>
        <p className={s.notice}>
          Rooms show observed workbench state. SDLC phase and handoff telemetry
          will appear when supplied by the orchestration service.
        </p>
        <button
          aria-pressed={floorList}
          onClick={() => setFloorList((v) => !v)}
        >
          {floorList ? "Spatial view" : "List view"}
        </button>
      </div>
      <div className={floorList ? s.list : s.floor} aria-label="Agent floor">
        {rooms.map((room) => (
          <section className={s.room} key={room.name} aria-label={room.name}>
            <h2>
              {room.name}
              <small>{room.list.length} agents</small>
            </h2>
            <p className={s.speech}>{room.detail}</p>
            <div className={s.roomList}>
              {room.list.map((a) => (
                <button
                  className={s.agentToken}
                  key={a.id}
                  aria-label={`Inspect ${a.name}, ${a.id}, ${describe(a)}`}
                  onClick={() => inspect(a.id)}
                >
                  <span className={s.avatar} data-mode={a.mode}>
                    {a.name.slice(0, 2).toUpperCase()}
                  </span>
                  <span>
                    <strong>{a.name}</strong>
                    <small>{a.role}</small>
                    <small>{describe(a)}</small>
                  </span>
                </button>
              ))}
              {room.list.length === 0 && (
                <p className={s.speech}>No agents in this room.</p>
              )}
            </div>
          </section>
        ))}
      </div>
      <details>
        <summary>Accessible roster and selection</summary>
        {table}
      </details>
    </>
  );
  const focusedAgent =
    agents.find((a) => a.id === inspected) ?? selectedAgents[0] ?? shown[0];
  const profile = focusedAgent && (
    <div className={s.split}>
      <section className={s.panel}>
        <h2>{focusedAgent.name}</h2>
        <p>{focusedAgent.description || "No description recorded."}</p>
        <dl className={s.details}>
          {Object.entries({
            ID: focusedAgent.id,
            Role: focusedAgent.role,
            Vendor: focusedAgent.vendor || "Custom ACP",
            Participation: focusedAgent.mode,
            Runtime: focusedAgent.runtime,
            Version: focusedAgent.version,
            Executable: focusedAgent.command,
            Arguments: JSON.stringify(focusedAgent.args),
            "Declared permissions": focusedAgent.permissions.join(", "),
            "Trainable surfaces": focusedAgent.trainable.join(", "),
            Created: stamp(focusedAgent.createdAt),
            "Last updated": stamp(focusedAgent.updatedAt),
          }).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <h3>Instructions</h3>
        <pre className={s.code}>
          {focusedAgent.instructions || "No extra instructions."}
        </pre>
        <div className={s.actions}>
          <button onClick={() => onNavigate(`agents/${focusedAgent.id}`)}>
            Edit or run independently
          </button>
          <button
            onClick={() =>
              setChange({
                ids: [focusedAgent.id],
                mode: focusedAgent.mode === "active" ? "learning" : "active",
              })
            }
          >
            {focusedAgent.mode === "active"
              ? "Move to Learning"
              : "Activate for delivery"}
          </button>
        </div>
      </section>
      <aside className={s.panel}>
        <h2>Actual work history</h2>
        <p>
          {done(focusedAgent.id)} completed turns. This is execution history,
          not a quality score.
        </p>
        <div className={s.list}>
          {runs
            .filter((run) => run.agentId === focusedAgent.id)
            .slice()
            .reverse()
            .map((run) => (
              <article className={s.listItem} key={run.id}>
                <span className={s.badge} data-state={run.state}>
                  {run.state}
                </span>
                <p>{run.prompt.slice(0, 180)}</p>
                <small>{stamp(run.startedAt)}</small>
                {run.error && <p>{run.error}</p>}
                <details>
                  <summary>Task output</summary>
                  <pre className={s.code}>
                    {run.output || "No output captured."}
                  </pre>
                </details>
              </article>
            ))}
        </div>
        {runs.every((r) => r.agentId !== focusedAgent.id) && (
          <p>No runs recorded for this profile.</p>
        )}
      </aside>
    </div>
  );
  const wizard = (
    <>
      <div className={s.progress}>
        {[
          "Define identity",
          "Configure ACP runtime",
          "Review permissions",
          "Activate when ready",
        ].map((step, index) => (
          <div
            className={s.step}
            key={step}
            data-done={index < (agents.length ? 3 : 0)}
          >
            {index + 1}. {step}
          </div>
        ))}
      </div>
      <div className={s.grid}>
        <section className={s.panel}>
          <h2>Create an independent specialist</h2>
          <p>
            Choose a stable portable ID, role, vendor, executable and
            instructions. The validated form creates a Learning profile; saving
            never starts the program.
          </p>
          <button
            className={s.primary}
            onClick={() => onNavigate("agents/new")}
          >
            Create agent profile
          </button>
        </section>
        <section className={s.panel}>
          <h2>Bring an existing agent</h2>
          <p>
            Import a Meridian portable profile. Install its ACP runtime on this
            host separately; imported memories require review before use.
          </p>
          <button onClick={() => onNavigate("agents/import")}>
            Import portable agent
          </button>
        </section>
        <section className={s.panel}>
          <h2>Check execution prerequisites</h2>
          <ul className={s.checklist}>
            {Object.entries({
              "Workspace open":
                !!controller.snapshot?.capabilities.workspaceOpen,
              "Workspace trusted": !!controller.snapshot?.capabilities.trusted,
              "Governor enabled":
                !!controller.snapshot?.capabilities.governorEnabled,
              "Execution ready":
                !!controller.snapshot?.capabilities.executionReady,
            }).map(([name, ok]) => (
              <li key={name}>
                {name}
                <strong>{ok ? "Ready" : "Needs attention"}</strong>
              </li>
            ))}
          </ul>
          <button onClick={() => onNavigate("runtime")}>
            Review runtime checks
          </button>
        </section>
      </div>
      <p className={s.notice}>
        Automated probation tests and promotion scores are not available from
        this runtime. Participation is independent of permission autonomy;
        activation does not grant new tool access.
      </p>
    </>
  );
  const adapters = (
    <>
      <section className={s.notice}>
        Every profile targets an installed ACP program. This bay manages
        workspace launch configuration; it does not silently install executables
        or supply provider credentials.
      </section>
      <div className={s.grid}>
        {shown.map((a) => (
          <section className={s.panel} key={a.id}>
            <h2>
              {a.name} <span className={s.badge}>{a.version}</span>
            </h2>
            <p>
              {a.vendor || "Custom ACP"} · {a.mode}
            </p>
            <pre className={s.code}>
              {JSON.stringify({ command: a.command, args: a.args }, null, 2)}
            </pre>
            <p>Declared tools: {a.permissions.join(", ") || "none"}</p>
            <div className={s.actions}>
              <button onClick={() => onNavigate(`agents/${a.id}`)}>
                Configure & inspect
              </button>
              <button
                onClick={async () => {
                  try {
                    const result = await controller.execute("agent/export", {
                      id: a.id,
                    });
                    exportText(result.fileName, result.content);
                  } catch (cause) {
                    setError((cause as Error).message);
                  }
                }}
              >
                Export adapter profile
              </button>
            </div>
          </section>
        ))}
      </div>
      <RegistryBay controller={controller} />
      <section className={s.panel}>
        <h2>Protocol readiness</h2>
        <p>
          ACP initialization is checked on each explicit launch. A handshake
          refusal or executable failure stays visible in the agent's run
          history. Automated adapter graduation still needs its service
          integration; registry installation is above.
        </p>
        <button onClick={() => onNavigate("onboarding")}>Add an adapter</button>
      </section>
    </>
  );
  const titles: Record<string, [string, string]> = {
    floor: [
      "A workshop you can read.",
      "Follow your active team and Learning cohort in one spatial view.",
    ],
    watch: [
      "Every agent. Every state.",
      "Sort, compare and manage your roster using actual runtime records.",
    ],
    inspector: [
      "Know the agent behind the work.",
      "Configuration, participation and execution history in a focused profile.",
    ],
    onboarding: [
      "Give your next agent a clear start.",
      "A guided path from portable identity to deliberate activation.",
    ],
    adapters: [
      "Your runtimes, connected.",
      "Inspect portable ACP configurations and their independent execution history.",
    ],
  };
  const [title, description] = titles[view] ?? titles.watch;
  return (
    <StudioPage
      section="Workspace / agents"
      title={title}
      description={description}
      actions={
        <button onClick={() => onNavigate("agents/new")}>Add agent</button>
      }
    >
      {tabs}
      <ErrorNotice error={error} />
      {view !== "onboarding" && toolbar}
      {view === "watch" && (
        <div className={s.toolbar}>
          <span>{selectedAgents.length} selected</span>
          <div className={s.actions}>
            <button onClick={() => setColumnDialog(true)}>Columns</button>
            <button
              disabled={selectedAgents.length !== 2}
              onClick={() => setCompare(true)}
            >
              Compare two agents
            </button>
            <button
              disabled={!selectedAgents.length}
              onClick={() =>
                setChange({
                  ids: selectedAgents.map((a) => a.id),
                  mode: "active",
                })
              }
            >
              Activate selected
            </button>
            <button
              disabled={!selectedAgents.length}
              onClick={() =>
                setChange({
                  ids: selectedAgents.map((a) => a.id),
                  mode: "learning",
                })
              }
            >
              Deactivate selected
            </button>
          </div>
        </div>
      )}
      {view === "onboarding" ? (
        wizard
      ) : !agents.length ? (
        <Empty title="Your team starts here.">
          Create or import a portable agent to populate this view.
        </Empty>
      ) : view === "floor" ? (
        floor
      ) : view === "watch" ? (
        table
      ) : view === "adapters" ? (
        adapters
      ) : (
        <>
          <label className={s.field}>
            Agent
            <select
              value={focusedAgent?.id ?? ""}
              onChange={(e) => inspect(e.target.value)}
            >
              {shown.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} · {a.id}
                </option>
              ))}
            </select>
          </label>
          {profile}
        </>
      )}
      {inspected && view !== "inspector" && (
        <Dialog
          title={agents.find((a) => a.id === inspected)?.name ?? "Agent"}
          wide
          onClose={() => setInspected(undefined)}
        >
          <div className={s.page}>{profile}</div>
        </Dialog>
      )}
      {change && (
        <Dialog
          title={`${change.mode === "active" ? "Activate" : "Deactivate"} ${change.ids.length} agents?`}
          onClose={() => setChange(undefined)}
        >
          <div className={s.page}>
            <p>
              {change.mode === "learning"
                ? "Their queued and running tasks will stop. They will show Learning and leave the delivery roster."
                : "They will join the delivery roster. This does not launch tasks or change permission policy."}
            </p>
            <ul>
              {agents
                .filter((a) => change.ids.includes(a.id))
                .map((a) => (
                  <li key={a.id}>
                    {a.name} ({a.id})
                  </li>
                ))}
            </ul>
            <ErrorNotice error={error} />
            <button
              className={s.primary}
              disabled={controller.busy}
              onClick={() => void modeChange()}
            >
              Confirm participation change
            </button>
          </div>
        </Dialog>
      )}
      {columnDialog && (
        <Dialog
          title="Visible roster columns"
          onClose={() => setColumnDialog(false)}
        >
          <div className={s.page}>
            {COLUMNS.map((c) => (
              <label className={s.inline} key={c}>
                <input
                  type="checkbox"
                  checked={columns.includes(c)}
                  onChange={(e) =>
                    setColumns((old) =>
                      e.target.checked
                        ? [...old, c]
                        : old.filter((x) => x !== c),
                    )
                  }
                />
                {c}
              </label>
            ))}
          </div>
        </Dialog>
      )}
      {compare && (
        <Dialog title="Agent comparison" wide onClose={() => setCompare(false)}>
          <div className={`${s.page} ${s.grid}`}>
            {selectedAgents.slice(0, 2).map((a) => (
              <section className={s.panel} key={a.id}>
                <h2>{a.name}</h2>
                <p>
                  {a.role} · {a.vendor}
                </p>
                <p>
                  {a.mode} / {a.runtime}
                </p>
                <p>
                  {done(a.id)} completed turns; {queued(a.id)} queued or
                  running.
                </p>
                <p>{a.permissions.join(", ")}</p>
                <pre className={s.code}>{a.instructions}</pre>
              </section>
            ))}
          </div>
        </Dialog>
      )}
    </StudioPage>
  );
}
