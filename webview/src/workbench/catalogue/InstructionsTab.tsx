import { useState } from "react";
import type {
  WorkbenchInstruction,
  WorkbenchInstructionInput,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import type { WebviewRpcClient } from "../../rpc/client";
import { getVsCodeApi } from "../../host/vscode-api";
import {
  Button,
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
 * The Instructions tab.
 *
 * Instruction files — `AGENTS.md`, `CONVENTIONS.md` and their kin — are how
 * an organisation tells an agent how it works here. They are first-class
 * artefacts: versioned, human-editable, exported in the open Markdown shape,
 * and bound to agents explicitly rather than injected invisibly.
 *
 * Scope is the precedence tier. Where two instructions disagree, the more
 * specific one wins: adapter over workspace over user over organisation. The
 * order is stated on the page rather than left for the user to infer, because
 * a precedence rule nobody can see is a precedence rule nobody can rely on.
 */

const SCOPES: readonly {
  value: WorkbenchInstructionInput["scope"];
  label: string;
  hint: string;
}[] = [
  {
    value: "adapter",
    label: "Adapter",
    hint: "Ships with one agent. Most specific — wins over everything else.",
  },
  {
    value: "workspace",
    label: "Workspace",
    hint: "This repository's conventions.",
  },
  { value: "user", label: "User", hint: "Your own preferences." },
  {
    value: "organisation",
    label: "Organisation",
    hint: "House standards. Least specific — the baseline everything else refines.",
  },
];

const BLANK: WorkbenchInstructionInput = {
  id: "",
  name: "",
  summary: "",
  scope: "workspace",
  body:
    "# How we work here\n\n" +
    "## Conventions\n\n## Definition of done\n\n## What to ask about rather than assume\n",
};

export interface InstructionsTabProps {
  controller: WorkbenchController;
  client: WebviewRpcClient;
}

export function InstructionsTab({ controller, client }: InstructionsTabProps) {
  const snapshot = controller.snapshot;
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<
    WorkbenchInstructionInput | undefined
  >();
  const [isNew, setIsNew] = useState(false);
  const [removing, setRemoving] = useState<WorkbenchInstruction | undefined>();
  const action = useAction();

  const instructions = snapshot?.instructions ?? [];
  const agents = snapshot?.agents ?? [];
  const filtered = useFilter(instructions, query, (entry) => [
    entry.name,
    entry.id,
    entry.summary,
    entry.scope,
  ]);
  const boundAgents = (id: string) =>
    agents.filter((agent) => agent.instructionIds.includes(id));

  const save = async (input: WorkbenchInstructionInput) => {
    const ok = await action.run(
      () => controller.execute("instruction/save", { instruction: input }),
      `Saved ${input.name}.`,
    );
    if (ok) setEditing(undefined);
  };

  const importPackage = () =>
    action.run(async () => {
      const picked = await client.pickFile();
      if (!picked) {
        action.setNotice("Nothing selected.");
        return;
      }
      const { report } = await controller.execute("agent/importPackage", picked);
      action.setNotice(
        report.instructions.length
          ? `Imported ${report.instructions.length} instruction file(s).`
          : "That package carried no instruction files. Check the Agents tab for what it did contain.",
      );
    });

  const exportInstruction = (entry: WorkbenchInstruction) =>
    action.run(async () => {
      const file = await controller.execute("instruction/export", {
        id: entry.id,
      });
      getVsCodeApi().postMessage({
        type: "download",
        fileName: file.fileName,
        mimeType: "text/markdown",
        content: file.content,
      });
    }, `Exported ${entry.name} as Markdown.`);

  return (
    <Page
      title="Instructions"
      blurb="Versioned files your agents work from. A bound file is written into the agent\u2019s briefing on every run, ordered so the most specific scope wins."
      actions={
        <>
          <Button
            icon="plus"
            variant="primary"
            onClick={() => {
              setEditing({ ...BLANK });
              setIsNew(true);
            }}
          >
            New instruction
          </Button>
          <Button
            icon="external"
            onClick={() => void importPackage()}
            disabled={action.busy}
          >
            Import
          </Button>
        </>
      }
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      <Notice tone="info">
        Precedence, most specific first: adapter → workspace → user →
        organisation. Where two instructions disagree, the more specific one
        wins.
      </Notice>

      <Panel
        title="Library"
        hint="Only enabled instructions can be bound to an agent."
      >
        <Toolbar
          value={query}
          onChange={setQuery}
          placeholder="Search instructions by name, scope or summary"
        />
        {!instructions.length ? (
          <Empty
            title="No instruction files yet."
            action={
              <Button
                variant="primary"
                icon="plus"
                onClick={() => {
                  setEditing({ ...BLANK });
                  setIsNew(true);
                }}
              >
                Write your first instructions
              </Button>
            }
          >
            Write down how your organisation works — conventions, definition of
            done, what an agent should ask about rather than assume — and bind
            it to the agents that need it. Or import an existing{" "}
            <code>AGENTS.md</code>.
          </Empty>
        ) : !filtered.length ? (
          <Empty title="No instruction matches that search.">
            Clear the search to see all {instructions.length} files.
          </Empty>
        ) : (
          <div className={s.grid}>
            {filtered.map((entry) => {
              const bound = boundAgents(entry.id);
              return (
                <article key={entry.id} className={s.card}>
                  <div className={s.cardHead}>
                    <div style={{ minWidth: 0 }}>
                      <h3 className={s.cardName}>{entry.name}</h3>
                      <p className={s.cardMeta}>{entry.id}</p>
                    </div>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <Tag>{entry.scope}</Tag>
                      <Tag tone={entry.enabled ? "active" : "neutral"}>
                        {entry.enabled ? "Enabled" : "Disabled"}
                      </Tag>
                      {entry.source === "imported" ? <Tag>Imported</Tag> : null}
                      {entry.source === "builtin" ? <Tag>Built-in</Tag> : null}
                    </div>
                  </div>
                  {entry.summary ? (
                    <p className={s.cardBody}>{entry.summary}</p>
                  ) : null}
                  <p className={s.cardBody}>
                    {bound.length
                      ? `Bound to ${bound.map((agent) => agent.name).join(", ")}.`
                      : "Not bound to any agent yet."}
                  </p>
                  <div className={s.cardActions}>
                    <Button
                      icon="settings"
                      disabled={action.busy}
                      onClick={() => {
                        setEditing({
                          id: entry.id,
                          name: entry.name,
                          summary: entry.summary,
                          scope: entry.scope,
                          body: entry.body,
                        });
                        setIsNew(false);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      disabled={action.busy}
                      onClick={() =>
                        void action.run(
                          () =>
                            controller.execute("instruction/toggle", {
                              id: entry.id,
                              enabled: !entry.enabled,
                            }),
                          entry.enabled
                            ? `${entry.name} disabled.`
                            : `${entry.name} enabled.`,
                        )
                      }
                    >
                      {entry.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      icon="external"
                      disabled={action.busy}
                      onClick={() => void exportInstruction(entry)}
                    >
                      Export
                    </Button>
                    <Button
                      variant="danger"
                      disabled={action.busy}
                      onClick={() => setRemoving(entry)}
                    >
                      Remove
                    </Button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Panel>

      {editing ? (
        <InstructionEditor
          value={editing}
          isNew={isNew}
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
              <p>The instruction file is deleted from this workspace.</p>
              {boundAgents(removing.id).length ? (
                <p>
                  It is currently bound to{" "}
                  {boundAgents(removing.id)
                    .map((agent) => agent.name)
                    .join(", ")}
                  . Those bindings are removed too.
                </p>
              ) : (
                <p>No agent is bound to it.</p>
              )}
            </>
          }
          confirmLabel="Remove instructions"
          busy={action.busy}
          error={action.error}
          onCancel={() => setRemoving(undefined)}
          onConfirm={() =>
            void action
              .run(
                () =>
                  controller.execute("instruction/remove", { id: removing.id }),
                `Removed ${removing.name}.`,
              )
              .then((ok) => ok && setRemoving(undefined))
          }
        />
      ) : null}
    </Page>
  );
}

function InstructionEditor({
  value,
  isNew,
  busy,
  error,
  onCancel,
  onSave,
}: {
  value: WorkbenchInstructionInput;
  isNew: boolean;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (input: WorkbenchInstructionInput) => void;
}) {
  const [draft, setDraft] = useState(value);
  const set = <K extends keyof WorkbenchInstructionInput>(
    key: K,
    next: WorkbenchInstructionInput[K],
  ) => setDraft((current) => ({ ...current, [key]: next }));
  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <form
        className={`${s.dialog} ${s.dialogWide}`}
        role="dialog"
        aria-modal="true"
        aria-label={isNew ? "New instructions" : `Edit ${value.name}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSave(draft);
        }}
      >
        <h2 className={s.dialogTitle}>
          {isNew ? "New instruction file" : `Edit ${value.name}`}
        </h2>
        <div className={s.split}>
          <Field label="Identifier" hint="Lower-case, stable. Cannot change later.">
            <input
              required
              value={draft.id}
              disabled={!isNew}
              pattern="[a-z0-9][a-z0-9-]*"
              placeholder="house-conventions"
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
        </div>
        <Field
          label="Scope"
          hint={
            SCOPES.find((scope) => scope.value === draft.scope)?.hint ?? ""
          }
        >
          <select
            value={draft.scope}
            onChange={(event) =>
              set("scope", event.target.value as WorkbenchInstructionInput["scope"])
            }
          >
            {SCOPES.map((scope) => (
              <option key={scope.value} value={scope.value}>
                {scope.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Summary" hint="One line. Shown wherever the file is offered.">
          <input
            value={draft.summary}
            onChange={(event) => set("summary", event.target.value)}
          />
        </Field>
        <Field
          label="Instructions (Markdown)"
          hint="Exported as a Markdown file with frontmatter, readable by anything."
        >
          <textarea
            value={draft.body}
            style={{ minHeight: 280 }}
            onChange={(event) => set("body", event.target.value)}
          />
        </Field>
        <Notice tone="error">{error}</Notice>
        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {isNew ? "Create instructions" : "Save changes"}
          </Button>
        </div>
      </form>
    </div>
  );
}
