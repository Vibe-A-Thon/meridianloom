import { useState } from "react";
import {
  SDLC_PHASES,
  SDLC_PHASE_LABELS,
  type AgentPermission,
  type LearningSurface,
  type SdlcPhase,
  type WorkbenchAgent,
  type WorkbenchAgentInput,
  type WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import type { WebviewRpcClient } from "../../rpc/client";
import { getVsCodeApi } from "../../host/vscode-api";
import {
  Button,
  ChipSelect,
  Confirm,
  Empty,
  Field,
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
 * The Agents tab.
 *
 * An agent here is a **portable, independent** launch profile: an executable
 * the user already has, plus the configuration Meridian needs to convene and
 * govern it. Meridian does not own the agent and does not need to — the same
 * profile runs elsewhere, and removing Meridian does not remove the agent.
 *
 * Participation is the product decision this tab exists to express:
 *
 *  - **Active** — takes part in deliverables. Convened for the SDLC phases it
 *    is tagged with, bound to the skills and instructions selected here.
 *  - **Learning** — does not take part. Its status reads *Learning*, and the
 *    feedback from completed deliverables becomes memory notes it can be
 *    given later. Deactivating stops anything it is running.
 *
 * Anything with an ACP-compatible executable can be an adapter, and a package
 * dropped in as Markdown or ZIP becomes one without the user writing a form.
 */

const PERMISSIONS: readonly { value: AgentPermission; label: string }[] = [
  { value: "read", label: "Read" },
  { value: "search", label: "Search" },
  { value: "think", label: "Think" },
  { value: "edit", label: "Edit" },
  { value: "execute", label: "Execute" },
  { value: "move", label: "Move" },
  { value: "delete", label: "Delete" },
];
const SURFACES: readonly { value: LearningSurface; label: string }[] = [
  { value: "memory", label: "Memory" },
  { value: "policy", label: "Policy" },
  { value: "rules", label: "Rules" },
  { value: "skills", label: "Skills" },
  { value: "calibration", label: "Calibration" },
];
const PHASE_OPTIONS = SDLC_PHASES.map((phase) => ({
  value: phase,
  label: SDLC_PHASE_LABELS[phase],
}));

const BLANK: WorkbenchAgentInput = {
  id: "",
  name: "",
  role: "Developer",
  description: "",
  vendor: "",
  version: "1.0.0",
  command: "",
  args: [],
  instructions: "",
  permissions: ["read", "search", "think"],
  trainable: ["memory"],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
};

export interface AgentsTabProps {
  controller: WorkbenchController;
  client: WebviewRpcClient;
}

export function AgentsTab({ controller, client }: AgentsTabProps) {
  const snapshot = controller.snapshot;
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<WorkbenchAgentInput | undefined>();
  const [isNew, setIsNew] = useState(false);
  const [removing, setRemoving] = useState<WorkbenchAgent | undefined>();
  const [running, setRunning] = useState<WorkbenchAgent | undefined>();
  const action = useAction();

  const agents = snapshot?.agents ?? [];
  const filtered = useFilter(agents, query, (agent) => [
    agent.name,
    agent.id,
    agent.role,
    agent.vendor,
    agent.description,
  ]);
  const active = agents.filter((agent) => agent.mode === "active");

  const save = async (input: WorkbenchAgentInput) => {
    const ok = await action.run(
      () => controller.execute("agent/save", { agent: input }),
      `Saved ${input.name}.`,
    );
    if (ok) setEditing(undefined);
  };

  const setMode = (agent: WorkbenchAgent, mode: "active" | "learning") =>
    action.run(
      () => controller.execute("agent/mode", { id: agent.id, mode }),
      mode === "active"
        ? `${agent.name} is active and will take part in deliverables.`
        : `${agent.name} moved to Learning and takes no delivery work.`,
    );

  const importPackage = async () => {
    await action.run(async () => {
      const picked = await client.pickFile();
      // A cancelled dialog is not a failure and must not read as one.
      if (!picked) {
        action.setNotice("Nothing selected.");
        return;
      }
      const { report } = await controller.execute("agent/importPackage", picked);
      const parts = [
        report.agents.length && `${report.agents.length} agent(s)`,
        report.skills.length && `${report.skills.length} skill(s)`,
        report.instructions.length &&
          `${report.instructions.length} instruction(s)`,
      ].filter(Boolean);
      const skipped = report.skipped.length
        ? ` ${report.skipped.length} file(s) skipped: ${report.skipped
            .slice(0, 3)
            .map((entry) => `${entry.path} (${entry.reason})`)
            .join("; ")}${report.skipped.length > 3 ? "…" : ""}`
        : "";
      action.setNotice(
        `Imported ${parts.join(", ")} from the ${report.format} package. ` +
          `New agents start in Learning until you activate them.${skipped}`,
      );
    });
  };

  const exportAgent = (agent: WorkbenchAgent) =>
    action.run(async () => {
      const file = await controller.execute("agent/export", { id: agent.id });
      getVsCodeApi().postMessage({
        type: "download",
        fileName: file.fileName,
        mimeType: "application/json",
        content: file.content,
      });
    }, `Exported ${agent.name}. Its skills and instructions travel with it.`);

  return (
    <Page
      title="Agents"
      blurb="Portable agent profiles. Active agents take part in deliverables; the rest sit in Learning. Any ACP-compatible executable can be an adapter."
      actions={
        <>
          <Button icon="plus" variant="primary" onClick={() => {
            setEditing({ ...BLANK });
            setIsNew(true);
          }}>
            New agent
          </Button>
          <Button icon="external" onClick={importPackage} disabled={action.busy}>
            Import .md or .zip
          </Button>
        </>
      }
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      <div className={s.three}>
        <Stat label="Active" value={active.length} hint="taking delivery work" />
        <Stat
          label="Learning"
          value={agents.length - active.length}
          hint="not convened; collecting memory"
        />
        <Stat
          label="Phases covered"
          value={`${
            new Set(active.flatMap((agent) => agent.phases)).size
          } / ${SDLC_PHASES.length}`}
          hint="by at least one active agent"
        />
      </div>

      <Panel
        title="Roster"
        hint="Activate an agent to convene it for the phases you tag it with."
      >
        <Toolbar
          value={query}
          onChange={setQuery}
          placeholder="Search agents by name, role, vendor or id"
        />
        {!agents.length ? (
          <Empty
            title="No agents yet."
            action={
              <Button variant="primary" icon="plus" onClick={() => {
                setEditing({ ...BLANK });
                setIsNew(true);
              }}>
                Add your first agent
              </Button>
            }
          >
            Add a profile for an agent you already run, or import one as a
            Markdown file or a ZIP archive. Meridian launches the executable
            you name; it never bundles an agent or its credentials.
          </Empty>
        ) : !filtered.length ? (
          <Empty title="No agent matches that search.">
            Clear the search to see all {agents.length} agents.
          </Empty>
        ) : (
          <div className={s.grid}>
            {filtered.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                snapshot={snapshot}
                busy={action.busy || controller.busy}
                onEdit={() => {
                  setEditing(toInput(agent));
                  setIsNew(false);
                }}
                onMode={(mode) => void setMode(agent, mode)}
                onRun={() => setRunning(agent)}
                onExport={() => void exportAgent(agent)}
                onRemove={() => setRemoving(agent)}
              />
            ))}
          </div>
        )}
      </Panel>

      {editing ? (
        <AgentEditor
          value={editing}
          isNew={isNew}
          snapshot={snapshot}
          busy={action.busy}
          error={action.error}
          onCancel={() => setEditing(undefined)}
          onSave={save}
        />
      ) : null}

      {removing ? (
        <Confirm
          title={`Remove ${removing.name}?`}
          detail={
            <>
              <p>
                This removes the profile and its memory notes from this
                workspace. It does not uninstall the agent itself — the
                executable and its credentials are yours and stay where they
                are.
              </p>
              <p>Anything it is running now will be stopped.</p>
            </>
          }
          confirmLabel="Remove profile"
          busy={action.busy}
          error={action.error}
          onCancel={() => setRemoving(undefined)}
          onConfirm={() =>
            void action
              .run(
                () => controller.execute("agent/remove", { id: removing.id }),
                `Removed ${removing.name}.`,
              )
              .then((ok) => ok && setRemoving(undefined))
          }
        />
      ) : null}

      {running ? (
        <RunDialog
          agent={running}
          busy={action.busy}
          error={action.error}
          onCancel={() => setRunning(undefined)}
          onRun={(prompt) =>
            void action
              .run(
                () =>
                  controller.execute("agent/run", { id: running.id, prompt }),
                `${running.name} started. Watch it on the Runs tab.`,
              )
              .then((ok) => ok && setRunning(undefined))
          }
        />
      ) : null}
    </Page>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className={s.card}>
      <p className={s.cardMeta}>{label}</p>
      <p className={s.cardName} style={{ fontSize: "1.6rem" }}>
        {value}
      </p>
      <p className={s.cardBody}>{hint}</p>
    </div>
  );
}

function AgentCard({
  agent,
  snapshot,
  busy,
  onEdit,
  onMode,
  onRun,
  onExport,
  onRemove,
}: {
  agent: WorkbenchAgent;
  snapshot: WorkbenchSnapshot | undefined;
  busy: boolean;
  onEdit: () => void;
  onMode: (mode: "active" | "learning") => void;
  onRun: () => void;
  onExport: () => void;
  onRemove: () => void;
}) {
  const isActive = agent.mode === "active";
  const skillNames = (snapshot?.skills ?? [])
    .filter((skill) => agent.skillIds.includes(skill.id))
    .map((skill) => skill.name);
  const instructionNames = (snapshot?.instructions ?? [])
    .filter((entry) => agent.instructionIds.includes(entry.id))
    .map((entry) => entry.name);

  return (
    <article className={s.card}>
      <div className={s.cardHead}>
        <div style={{ minWidth: 0 }}>
          <h3 className={s.cardName}>{agent.name}</h3>
          <p className={s.cardMeta}>
            {agent.role} · v{agent.version}
            {agent.vendor ? ` · ${agent.vendor}` : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {/* Status is the word the product uses, not a colour: an inactive
              agent reads "Learning", which is what it is doing. */}
          <Tag tone={isActive ? "active" : "learning"}>
            {isActive ? "Active" : "Learning"}
          </Tag>
          {agent.runtime === "running" ? <Tag tone="warn">Running</Tag> : null}
          {agent.source === "builtin" ? <Tag>Built-in</Tag> : null}
          {agent.source === "imported" ? <Tag>Imported</Tag> : null}
          {!isActive && agent.learningState === "review" ? (
            <Tag tone="warn">Notes to review</Tag>
          ) : null}
        </div>
      </div>

      {agent.description ? (
        <p className={s.cardBody}>{agent.description}</p>
      ) : null}

      {!agent.command ? (
        <Notice tone="info">
          No executable set yet. Add one before this agent can run.
        </Notice>
      ) : null}

      <div>
        <p className={s.cardMeta}>SDLC phases</p>
        {agent.phases.length ? (
          <div className={s.chipRow} style={{ marginTop: 4 }}>
            {agent.phases.map((phase) => (
              <Tag key={phase}>{SDLC_PHASE_LABELS[phase]}</Tag>
            ))}
          </div>
        ) : (
          <p className={s.cardBody}>
            Untagged — it will not be convened for any phase.
          </p>
        )}
      </div>

      {skillNames.length || instructionNames.length ? (
        <p className={s.cardBody}>
          {skillNames.length ? <>Skills: {skillNames.join(", ")}. </> : null}
          {instructionNames.length ? (
            <>Instructions: {instructionNames.join(", ")}.</>
          ) : null}
        </p>
      ) : null}

      <div className={s.cardActions}>
        <Button icon="settings" onClick={onEdit} disabled={busy}>
          Edit
        </Button>
        {isActive ? (
          <Button onClick={() => onMode("learning")} disabled={busy}>
            Deactivate
          </Button>
        ) : (
          <Button
            variant="primary"
            icon="check"
            onClick={() => onMode("active")}
            disabled={busy}
          >
            Activate
          </Button>
        )}
        <Button
          icon="play"
          onClick={onRun}
          disabled={busy || !agent.command}
          title={
            agent.command
              ? "Run this agent on its own, independently of a deliverable"
              : "Set an executable first"
          }
        >
          Run
        </Button>
        <Button icon="external" onClick={onExport} disabled={busy}>
          Export
        </Button>
        <Button variant="danger" onClick={onRemove} disabled={busy}>
          Remove
        </Button>
      </div>
    </article>
  );
}

function toInput(agent: WorkbenchAgent): WorkbenchAgentInput {
  return {
    id: agent.id,
    name: agent.name,
    role: agent.role,
    description: agent.description,
    vendor: agent.vendor,
    version: agent.version,
    command: agent.command,
    args: agent.args,
    instructions: agent.instructions,
    permissions: agent.permissions,
    trainable: agent.trainable,
    phases: agent.phases,
    skillIds: agent.skillIds,
    instructionIds: agent.instructionIds,
  integrationIds: agent.integrationIds,
  };
}

function AgentEditor({
  value,
  isNew,
  snapshot,
  busy,
  error,
  onCancel,
  onSave,
}: {
  value: WorkbenchAgentInput;
  isNew: boolean;
  snapshot: WorkbenchSnapshot | undefined;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (input: WorkbenchAgentInput) => void;
}) {
  const [draft, setDraft] = useState(value);
  const set = <K extends keyof WorkbenchAgentInput>(
    key: K,
    next: WorkbenchAgentInput[K],
  ) => setDraft((current) => ({ ...current, [key]: next }));

  // Only enabled skills and instructions can be bound: a disabled one is out
  // of service, and offering it would promise something that will not happen.
  const skillOptions = (snapshot?.skills ?? [])
    .filter((skill) => skill.enabled)
    .map((skill) => ({ value: skill.id, label: skill.name, hint: skill.summary }));
  const instructionOptions = (snapshot?.instructions ?? [])
    .filter((entry) => entry.enabled)
    .map((entry) => ({
      value: entry.id,
      label: entry.name,
      hint: `${entry.scope} · ${entry.summary}`,
    }));

  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <form
        className={`${s.dialog} ${s.dialogWide}`}
        role="dialog"
        aria-modal="true"
        aria-label={isNew ? "New agent" : `Edit ${value.name}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSave(draft);
        }}
      >
        <h2 className={s.dialogTitle}>
          {isNew ? "New agent" : `Edit ${value.name}`}
        </h2>

        <div className={s.split}>
          <Field label="Identifier" hint="Lower-case, stable. Cannot change later.">
            <input
              required
              value={draft.id}
              disabled={!isNew}
              pattern="[a-z0-9][a-z0-9-]*"
              onChange={(event) => set("id", event.target.value)}
            />
          </Field>
          <Field label="Name">
            <input
              required
              value={draft.name}
              onChange={(event) => set("name", event.target.value)}
            />
          </Field>
          <Field label="Role" hint="What this agent does in the organisation.">
            <input
              required
              value={draft.role}
              onChange={(event) => set("role", event.target.value)}
            />
          </Field>
          <Field label="Version">
            <input
              required
              value={draft.version}
              onChange={(event) => set("version", event.target.value)}
            />
          </Field>
          <Field label="Vendor" hint="Who made it. Optional.">
            <input
              value={draft.vendor}
              onChange={(event) => set("vendor", event.target.value)}
            />
          </Field>
          <Field
            label="Executable"
            hint="The ACP-compatible program to launch. Install and authenticate it yourself."
          >
            <input
              value={draft.command}
              placeholder="claude-code-acp"
              onChange={(event) => set("command", event.target.value)}
            />
          </Field>
        </div>

        <Field
          label="Arguments"
          hint="Space-separated. Never put credentials here — use the agent's own credential store."
        >
          <input
            value={draft.args.join(" ")}
            onChange={(event) =>
              set(
                "args",
                event.target.value.split(/\s+/).filter(Boolean),
              )
            }
          />
        </Field>

        <Field label="Description">
          <input
            value={draft.description}
            onChange={(event) => set("description", event.target.value)}
          />
        </Field>

        <Field
          label="SDLC phases"
          hint="Which phases this agent may be convened for when a deliverable is dispatched."
        >
          <ChipSelect<SdlcPhase>
            options={PHASE_OPTIONS}
            selected={draft.phases}
            onChange={(next) => set("phases", next)}
          />
        </Field>

        <Field
          label="Skills"
          hint="Binding a skill is what turns a role agent into a stack specialist."
        >
          <ChipSelect
            options={skillOptions}
            selected={draft.skillIds}
            onChange={(next) => set("skillIds", next)}
            emptyLabel="No enabled skills yet. Create one on the Skills tab."
          />
        </Field>

        <Field
          label="Instructions"
          hint="The files this agent works from — how your organisation does things."
        >
          <ChipSelect
            options={instructionOptions}
            selected={draft.instructionIds}
            onChange={(next) => set("instructionIds", next)}
            emptyLabel="No enabled instructions yet. Create one on the Instructions tab."
          />
        </Field>

        <div className={s.split}>
          <Field
            label="Declared permissions"
            hint="What it may request. Every request is still gated at run time."
          >
            <ChipSelect
              options={PERMISSIONS}
              selected={draft.permissions}
              onChange={(next) => set("permissions", next)}
            />
          </Field>
          <Field
            label="Learning surfaces"
            hint="What it may accumulate. Memory notes always need your review."
          >
            <ChipSelect
              options={SURFACES}
              selected={draft.trainable}
              onChange={(next) => set("trainable", next)}
            />
          </Field>
        </div>

        <Field
          label="Inline instructions"
          hint="Carried with the profile. Longer, shared guidance belongs on the Instructions tab."
        >
          <textarea
            value={draft.instructions}
            onChange={(event) => set("instructions", event.target.value)}
          />
        </Field>

        <Notice tone="error">{error}</Notice>

        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {isNew ? "Create agent" : "Save changes"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function RunDialog({
  agent,
  busy,
  error,
  onCancel,
  onRun,
}: {
  agent: WorkbenchAgent;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onRun: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState("");
  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <form
        className={s.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={`Run ${agent.name}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onRun(prompt);
        }}
      >
        <h2 className={s.dialogTitle}>Run {agent.name}</h2>
        <div className={s.dialogBody}>
          <p>
            This runs {agent.name} on its own, in the open workspace — no other
            agent is involved and no deliverable is required. It launches{" "}
            <code>{agent.command}</code> with your own credentials.
          </p>
          <Field label="Task">
            <textarea
              required
              value={prompt}
              placeholder="Describe what this agent should do."
              onChange={(event) => setPrompt(event.target.value)}
            />
          </Field>
        </div>
        <Notice tone="error">{error}</Notice>
        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={busy || !prompt.trim()}
          >
            Start run
          </Button>
        </div>
      </form>
    </div>
  );
}
