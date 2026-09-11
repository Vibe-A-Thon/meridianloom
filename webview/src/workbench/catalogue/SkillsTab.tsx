import { useState } from "react";
import type {
  WorkbenchSkill,
  WorkbenchSkillInput,
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
 * The Skills tab.
 *
 * A skill pack is the mechanic that makes an agent's identity data rather
 * than code: bind `java-spring-gradle` to a Developer and it is a Java
 * developer; bind `golang-service` and it is a Go developer. Nothing about
 * the agent's executable changes.
 *
 * A pack is authored here or imported, and exported in the open `SKILL.md`
 * shape — YAML frontmatter plus a Markdown body — so it is useful outside
 * Meridian as well as inside it.
 *
 * Disabling a skill keeps it in the catalogue but takes it out of service: it
 * can no longer be bound, and the agents already bound to it are named here
 * so the consequence is visible before the switch is thrown.
 */

const BLANK: WorkbenchSkillInput = {
  id: "",
  name: "",
  summary: "",
  version: "1.0.0",
  tags: [],
  body:
    "# Overview\n\nWhat this skill teaches an agent.\n\n" +
    "## Project layout\n\n## Build and test\n\n" +
    "```\n# the commands an agent should run\n```\n\n" +
    "## Conventions\n\n## Review checklist\n",
};

export interface SkillsTabProps {
  controller: WorkbenchController;
  client: WebviewRpcClient;
}

export function SkillsTab({ controller, client }: SkillsTabProps) {
  const snapshot = controller.snapshot;
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<WorkbenchSkillInput | undefined>();
  const [isNew, setIsNew] = useState(false);
  const [removing, setRemoving] = useState<WorkbenchSkill | undefined>();
  const action = useAction();

  const skills = snapshot?.skills ?? [];
  const agents = snapshot?.agents ?? [];
  const filtered = useFilter(skills, query, (skill) => [
    skill.name,
    skill.id,
    skill.summary,
    skill.tags.join(" "),
  ]);

  const boundAgents = (skillId: string) =>
    agents.filter((agent) => agent.skillIds.includes(skillId));

  const save = async (input: WorkbenchSkillInput) => {
    const ok = await action.run(
      () => controller.execute("skill/save", { skill: input }),
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
        report.skills.length
          ? `Imported ${report.skills.length} skill(s).`
          : "That package carried no skills. Check the Agents tab for what it did contain.",
      );
    });

  const exportSkill = (skill: WorkbenchSkill) =>
    action.run(async () => {
      const file = await controller.execute("skill/export", { id: skill.id });
      getVsCodeApi().postMessage({
        type: "download",
        fileName: file.fileName,
        mimeType: "text/markdown",
        content: file.content,
      });
    }, `Exported ${skill.name} as SKILL.md.`);

  return (
    <Page
      title="Skills"
      blurb="A bound skill is written into the agent\u2019s briefing every time it runs, so the same Developer becomes a Java or a Go specialist depending on what you bind. Identity is data, not code."
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
            New skill
          </Button>
          <Button icon="external" onClick={() => void importPackage()} disabled={action.busy}>
            Import
          </Button>
        </>
      }
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      <Panel
        title="Catalogue"
        hint="Only enabled skills can be bound to an agent."
      >
        <Toolbar
          value={query}
          onChange={setQuery}
          placeholder="Search skills by name, tag or summary"
        />
        {!skills.length ? (
          <Empty
            title="No skills yet."
            action={
              <Button
                variant="primary"
                icon="plus"
                onClick={() => {
                  setEditing({ ...BLANK });
                  setIsNew(true);
                }}
              >
                Create a skill pack
              </Button>
            }
          >
            A skill pack carries the conventions, project layout, build and
            test commands and review checklist for one stack or domain. Write
            one here, or import a <code>SKILL.md</code> or a ZIP of them.
          </Empty>
        ) : !filtered.length ? (
          <Empty title="No skill matches that search.">
            Clear the search to see all {skills.length} skills.
          </Empty>
        ) : (
          <div className={s.grid}>
            {filtered.map((skill) => {
              const bound = boundAgents(skill.id);
              return (
                <article key={skill.id} className={s.card}>
                  <div className={s.cardHead}>
                    <div style={{ minWidth: 0 }}>
                      <h3 className={s.cardName}>{skill.name}</h3>
                      <p className={s.cardMeta}>
                        {skill.id} · v{skill.version}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <Tag tone={skill.enabled ? "active" : "neutral"}>
                        {skill.enabled ? "Enabled" : "Disabled"}
                      </Tag>
                      {skill.source === "imported" ? <Tag>Imported</Tag> : null}
                      {/* Shipped with the extension. Worth showing for the
                          same reason "Imported" is: a user deciding whether
                          to trust or edit something should be able to see
                          where it came from without opening it. */}
                      {skill.source === "builtin" ? <Tag>Built-in</Tag> : null}
                    </div>
                  </div>
                  {skill.summary ? (
                    <p className={s.cardBody}>{skill.summary}</p>
                  ) : null}
                  {skill.tags.length ? (
                    <div className={s.chipRow}>
                      {skill.tags.map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </div>
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
                          id: skill.id,
                          name: skill.name,
                          summary: skill.summary,
                          version: skill.version,
                          tags: skill.tags,
                          body: skill.body,
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
                            controller.execute("skill/toggle", {
                              id: skill.id,
                              enabled: !skill.enabled,
                            }),
                          skill.enabled
                            ? `${skill.name} disabled. It can no longer be bound.`
                            : `${skill.name} enabled.`,
                        )
                      }
                    >
                      {skill.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      icon="external"
                      disabled={action.busy}
                      onClick={() => void exportSkill(skill)}
                    >
                      Export
                    </Button>
                    <Button
                      variant="danger"
                      disabled={action.busy}
                      onClick={() => setRemoving(skill)}
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
        <SkillEditor
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
              <p>The skill pack is deleted from this workspace.</p>
              {boundAgents(removing.id).length ? (
                <p>
                  It is currently bound to{" "}
                  {boundAgents(removing.id)
                    .map((agent) => agent.name)
                    .join(", ")}
                  . Those bindings are removed too, and those agents lose this
                  specialisation.
                </p>
              ) : (
                <p>No agent is bound to it.</p>
              )}
            </>
          }
          confirmLabel="Remove skill"
          busy={action.busy}
          error={action.error}
          onCancel={() => setRemoving(undefined)}
          onConfirm={() =>
            void action
              .run(
                () => controller.execute("skill/remove", { id: removing.id }),
                `Removed ${removing.name}.`,
              )
              .then((ok) => ok && setRemoving(undefined))
          }
        />
      ) : null}
    </Page>
  );
}

function SkillEditor({
  value,
  isNew,
  busy,
  error,
  onCancel,
  onSave,
}: {
  value: WorkbenchSkillInput;
  isNew: boolean;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (input: WorkbenchSkillInput) => void;
}) {
  const [draft, setDraft] = useState(value);
  const set = <K extends keyof WorkbenchSkillInput>(
    key: K,
    next: WorkbenchSkillInput[K],
  ) => setDraft((current) => ({ ...current, [key]: next }));
  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <form
        className={`${s.dialog} ${s.dialogWide}`}
        role="dialog"
        aria-modal="true"
        aria-label={isNew ? "New skill" : `Edit ${value.name}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSave(draft);
        }}
      >
        <h2 className={s.dialogTitle}>
          {isNew ? "New skill pack" : `Edit ${value.name}`}
        </h2>
        <div className={s.split}>
          <Field label="Identifier" hint="Lower-case, stable. Cannot change later.">
            <input
              required
              value={draft.id}
              disabled={!isNew}
              pattern="[a-z0-9][a-z0-9-]*"
              placeholder="java-spring-gradle"
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
          <Field label="Version">
            <input
              required
              value={draft.version}
              onChange={(event) => set("version", event.target.value)}
            />
          </Field>
          <Field label="Tags" hint="Comma-separated stack or domain tags.">
            <input
              value={draft.tags.join(", ")}
              placeholder="java, spring, gradle"
              onChange={(event) =>
                set(
                  "tags",
                  event.target.value
                    .split(",")
                    .map((tag) => tag.trim().toLowerCase())
                    .filter(Boolean),
                )
              }
            />
          </Field>
        </div>
        <Field label="Summary" hint="One line. Shown wherever the skill is offered.">
          <input
            value={draft.summary}
            onChange={(event) => set("summary", event.target.value)}
          />
        </Field>
        <Field
          label="Skill body (Markdown)"
          hint="Conventions, layout, build and test commands, review checklist. Exported as SKILL.md."
        >
          <textarea
            value={draft.body}
            style={{ minHeight: 260 }}
            onChange={(event) => set("body", event.target.value)}
          />
        </Field>
        <Notice tone="error">{error}</Notice>
        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {isNew ? "Create skill" : "Save changes"}
          </Button>
        </div>
      </form>
    </div>
  );
}
