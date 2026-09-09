import { useMemo, useState } from "react";
import {
  INTEGRATIONS,
  INTEGRATION_AUTH_LABELS,
  integrationById,
  integrationsByCategory,
  type IntegrationConnection,
  type IntegrationDefinition,
  type IntegrationReadResult,
  type IntegrationRowState,
} from "../../../../shared/ts/integrations";
import { SDLC_PHASE_LABELS } from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import { Dot, HeatStrip, Stat, type Signal } from "../../components/viz/Viz";
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
 * The Integrations tab.
 *
 * Meridian is only as useful as the systems it can see, so this is where a
 * user points it at the estate their delivery actually runs on: source and
 * review, planning, pipelines, runtimes, observability, messaging, cloud and
 * scheduling.
 *
 * The surface is built around one claim it refuses to make cheaply. A
 * connection is never "connected" because it was saved — it is connected
 * because Meridian reached it and something answered, and the card says what
 * answered, how long it took and when. A probe that has gone stale looks
 * stale. A probe that failed shows the reason, not a red dot.
 *
 * Every operation here is a read. Nothing on this page creates an issue,
 * triggers a pipeline, posts a message or restarts a workload, and the page
 * says so rather than leaving the user to hope.
 */

const STATE_SIGNAL: Readonly<Record<IntegrationRowState, Signal>> = {
  ok: "ok",
  warn: "warn",
  fail: "fail",
  idle: "idle",
};

function ago(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86_400)} d ago`;
}

/** A probe older than this is reported as stale rather than as a green light. */
const STALE_AFTER_MS = 30 * 60 * 1000;

function probeSignal(connection: IntegrationConnection): Signal {
  if (!connection.lastProbe) return "idle";
  if (!connection.lastProbe.ok) return "fail";
  return Date.now() - new Date(connection.lastProbe.at).getTime() > STALE_AFTER_MS
    ? "warn"
    : "ok";
}

function probeWord(connection: IntegrationConnection): string {
  if (!connection.lastProbe) return "Never tested";
  if (!connection.lastProbe.ok) return "Unreachable";
  return probeSignal(connection) === "warn" ? "Stale" : "Reachable";
}

export interface IntegrationsTabProps {
  controller: WorkbenchController;
}

export function IntegrationsTab({ controller }: IntegrationsTabProps) {
  const snapshot = controller.snapshot;
  const connections = useMemo(
    () => snapshot?.integrations ?? [],
    [snapshot?.integrations],
  );
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<
    { definition: IntegrationDefinition; connection?: IntegrationConnection } | undefined
  >();
  const [removing, setRemoving] = useState<IntegrationConnection | undefined>();
  const [reading, setReading] = useState<IntegrationReadResult | undefined>();
  const [readingFor, setReadingFor] = useState<string>();
  const action = useAction();

  const filtered = useFilter(connections, query, (connection) => [
    connection.name,
    connection.integrationId,
    integrationById(connection.integrationId)?.name,
  ]);
  const reachable = connections.filter((entry) => probeSignal(entry) === "ok");
  const failing = connections.filter((entry) => probeSignal(entry) === "fail");
  const catalogue = integrationsByCategory();

  const probe = (connection: IntegrationConnection) =>
    action.run(async () => {
      await controller.execute("integration/probe", { id: connection.id });
      // The snapshot that comes back carries the probe result; read it from
      // there rather than restating what we hoped would happen.
      const updated = (
        await controller.execute("snapshot", {})
      ).integrations.find((entry) => entry.id === connection.id);
      action.setNotice(
        updated?.lastProbe
          ? `${connection.name}: ${updated.lastProbe.detail} (${updated.lastProbe.latencyMs} ms)`
          : `${connection.name} was tested.`,
      );
    });

  const read = (connection: IntegrationConnection, operationId: string) =>
    action.run(async () => {
      setReadingFor(`${connection.id}:${operationId}`);
      const result = await controller.execute("integration/read", {
        id: connection.id,
        operationId,
      });
      setReading(result);
      action.setNotice(`${connection.name}: ${result.detail}`);
    });

  return (
    <Page
      title="Integrations"
      blurb="Point Meridian at the systems your delivery runs on. Every connection is proved by reaching it, and every operation here is a read."
      actions={
        connections.length ? (
          <Button
            icon="runtime"
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                for (const connection of connections.filter((entry) => entry.enabled))
                  await controller.execute("integration/probe", { id: connection.id });
              }, "Every enabled connection was tested.")
            }
          >
            Test all
          </Button>
        ) : undefined
      }
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      {connections.length ? (
        <div className={s.three}>
          <Stat
            label="Connections"
            value={connections.length}
            hint={`${connections.filter((entry) => entry.enabled).length} enabled`}
            accent="var(--ml-accent)"
          />
          <Stat
            label="Reachable"
            value={reachable.length}
            hint="answered within the last 30 minutes"
            accent="var(--ml-signal-ok)"
            visual={
              <HeatStrip
                label="Connection health"
                cells={connections.map((entry) => ({
                  id: entry.id,
                  signal: probeSignal(entry),
                  title: `${entry.name}: ${probeWord(entry)}`,
                }))}
              />
            }
          />
          <Stat
            label="Unreachable"
            value={failing.length}
            hint={failing.length ? "open one to read the reason" : "nothing failing"}
            accent="var(--ml-signal-fail)"
          />
        </div>
      ) : null}

      <Panel
        title="Your connections"
        hint="A connection is credentials plus an endpoint. Credentials live in the OS keychain, never in this workspace."
      >
        {!connections.length ? (
          <Empty title="No connections yet.">
            Pick a system from the catalogue below. Meridian stores the endpoint
            in your workspace and the credential in your operating system's
            keychain, then proves the connection by actually reaching it.
          </Empty>
        ) : (
          <>
            <Toolbar
              value={query}
              onChange={setQuery}
              placeholder="Search connections by name or system"
            />
            <div className={s.grid}>
              {filtered.map((connection) => {
                const definition = integrationById(connection.integrationId);
                if (!definition) return null;
                const signal = probeSignal(connection);
                return (
                  <article
                    key={connection.id}
                    className={s.card}
                    style={{ ["--card-accent" as string]: definition.hue }}
                  >
                    <div className={s.cardHead}>
                      <div style={{ minWidth: 0 }}>
                        <h3 className={s.cardName}>{connection.name}</h3>
                        <p className={s.cardMeta}>
                          {definition.name} · {connection.id}
                        </p>
                      </div>
                      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <Dot signal={signal} title={probeWord(connection)} />
                        <Tag
                          tone={
                            signal === "ok" ? "active" : signal === "fail" ? "warn" : "neutral"
                          }
                        >
                          {probeWord(connection)}
                        </Tag>
                        {!connection.enabled ? <Tag>Disabled</Tag> : null}
                      </div>
                    </div>

                    {connection.lastProbe ? (
                      <p className={s.cardBody}>
                        {connection.lastProbe.detail}
                        <span className={s.cardMeta}>
                          {" "}
                          · {ago(connection.lastProbe.at)} · {connection.lastProbe.latencyMs} ms
                          {connection.lastProbe.code !== undefined
                            ? ` · HTTP ${connection.lastProbe.code}`
                            : ""}
                        </span>
                      </p>
                    ) : (
                      <p className={s.cardBody}>
                        Saved but never tested. Test it to find out whether the
                        endpoint and credential actually work.
                      </p>
                    )}

                    {connection.secretKeys.length ? (
                      <p className={s.cardMeta}>
                        Credentials in the keychain: {connection.secretKeys.join(", ")}
                      </p>
                    ) : null}

                    <div className={s.cardActions}>
                      <Button
                        variant="primary"
                        disabled={action.busy}
                        onClick={() => void probe(connection)}
                      >
                        Test connection
                      </Button>
                      <Button
                        icon="settings"
                        disabled={action.busy}
                        onClick={() => setEditing({ definition, connection })}
                      >
                        Edit
                      </Button>
                      <Button
                        disabled={action.busy}
                        onClick={() =>
                          void action.run(
                            () =>
                              controller.execute("integration/toggle", {
                                id: connection.id,
                                enabled: !connection.enabled,
                              }),
                            connection.enabled
                              ? `${connection.name} disabled.`
                              : `${connection.name} enabled.`,
                          )
                        }
                      >
                        {connection.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button
                        variant="danger"
                        disabled={action.busy}
                        onClick={() => setRemoving(connection)}
                      >
                        Remove
                      </Button>
                    </div>

                    <div className={s.chipRow}>
                      {definition.operations.map((operation) => (
                        <button
                          key={operation.id}
                          type="button"
                          className={s.chip}
                          disabled={action.busy || !connection.enabled}
                          title={operation.summary}
                          aria-pressed={
                            readingFor === `${connection.id}:${operation.id}` &&
                            reading?.connectionId === connection.id
                          }
                          onClick={() => void read(connection, operation.id)}
                        >
                          <span className={s.chipMark} aria-hidden="true">
                            ↓
                          </span>
                          {operation.label}
                        </button>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </Panel>

      {reading ? (
        <ReadPanel
          result={reading}
          onClose={() => {
            setReading(undefined);
            setReadingFor(undefined);
          }}
        />
      ) : null}

      <Panel
        title="Catalogue"
        hint={`${INTEGRATIONS.length} systems Meridian can read from. Connecting one never grants it the ability to change anything.`}
      >
        {catalogue.map((group) => (
          <section key={group.category} className={s.catalogueGroup}>
            <h3 className={s.catalogueHeading}>{group.label}</h3>
            <div className={s.grid}>
              {group.items.map((definition) => {
                const existing = connections.filter(
                  (entry) => entry.integrationId === definition.id,
                );
                return (
                  <article
                    key={definition.id}
                    className={`${s.card} ${s.cardCompact}`}
                    style={{ ["--card-accent" as string]: definition.hue }}
                  >
                    <div className={s.cardHead}>
                      <div style={{ minWidth: 0 }}>
                        <h4 className={s.cardName}>{definition.name}</h4>
                        <p className={s.cardMeta}>
                          {INTEGRATION_AUTH_LABELS[definition.auth]}
                          {definition.binary ? ` · needs ${definition.binary}` : ""}
                        </p>
                      </div>
                      {existing.length ? (
                        <Tag tone="active">
                          {existing.length} connected
                        </Tag>
                      ) : null}
                    </div>
                    <p className={s.cardBody}>{definition.blurb}</p>
                    <p className={s.cardMeta}>
                      Informs:{" "}
                      {definition.phases
                        .map((phase) => SDLC_PHASE_LABELS[phase])
                        .join(", ")}
                    </p>
                    <div className={s.cardActions}>
                      <Button
                        icon="plus"
                        onClick={() => setEditing({ definition })}
                        disabled={action.busy}
                      >
                        Connect
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </Panel>

      {editing ? (
        <ConnectionEditor
          definition={editing.definition}
          connection={editing.connection}
          busy={action.busy}
          error={action.error}
          takenIds={connections.map((entry) => entry.id)}
          onCancel={() => setEditing(undefined)}
          onSave={async (input) => {
            const ok = await action.run(
              () => controller.execute("integration/save", { connection: input }),
              `Saved ${input.name}. Test it to prove it works.`,
            );
            if (ok) setEditing(undefined);
          }}
        />
      ) : null}

      {removing ? (
        <Confirm
          title={`Remove ${removing.name}?`}
          detail={
            <>
              <p>
                The endpoint is deleted from this workspace and every credential
                it holds is deleted from your OS keychain.
              </p>
              <p>
                Nothing in the connected system is touched. Any agent bound to
                this connection loses it.
              </p>
            </>
          }
          confirmLabel="Remove connection"
          busy={action.busy}
          error={action.error}
          onCancel={() => setRemoving(undefined)}
          onConfirm={() =>
            void action
              .run(
                () => controller.execute("integration/remove", { id: removing.id }),
                `Removed ${removing.name} and its stored credentials.`,
              )
              .then((ok) => ok && setRemoving(undefined))
          }
        />
      ) : null}
    </Page>
  );
}

/** The result of one read, as a table with a state column that is a shape. */
function ReadPanel({
  result,
  onClose,
}: {
  result: IntegrationReadResult;
  onClose: () => void;
}) {
  return (
    <Panel
      title={`${result.rows.length} row${result.rows.length === 1 ? "" : "s"}`}
      hint={`${result.detail} Read at ${new Date(result.at).toLocaleTimeString()} in ${result.latencyMs} ms.`}
      action={<Button onClick={onClose}>Close</Button>}
    >
      {result.truncated ? (
        <Notice tone="info">
          The system had more rows than Meridian reads in one call; this is the
          first {result.rows.length}.
        </Notice>
      ) : null}
      {!result.rows.length ? (
        <Empty title="That read returned nothing.">
          The call succeeded — the system simply has none of these right now.
        </Empty>
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col" className={s.tableState}>
                  State
                </th>
                {result.columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={row.id}>
                  <td className={s.tableState}>
                    <Dot signal={STATE_SIGNAL[row.state]} title={row.state} />
                  </td>
                  {row.cells.map((cell, index) => (
                    <td key={`${row.id}-${index}`}>
                      {index === 0 && row.href ? (
                        <a href={row.href} target="_blank" rel="noreferrer">
                          {cell}
                        </a>
                      ) : (
                        cell
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function ConnectionEditor({
  definition,
  connection,
  busy,
  error,
  takenIds,
  onCancel,
  onSave,
}: {
  definition: IntegrationDefinition;
  connection?: IntegrationConnection;
  busy: boolean;
  error: string | null;
  takenIds: string[];
  onCancel: () => void;
  onSave: (input: {
    id: string;
    integrationId: string;
    name: string;
    config: Record<string, string>;
    secrets: Record<string, string>;
  }) => void;
}) {
  const isNew = !connection;
  const [id, setId] = useState(
    connection?.id ??
      uniqueId(definition.id, takenIds),
  );
  const [name, setName] = useState(connection?.name ?? definition.name);
  const [config, setConfig] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of definition.fields)
      if (field.kind !== "secret")
        initial[field.key] = connection?.config[field.key] ?? "";
    return initial;
  });
  const [secrets, setSecrets] = useState<Record<string, string>>({});

  return (
    <div className={s.scrim} role="presentation" onClick={onCancel}>
      <form
        className={`${s.dialog} ${s.dialogWide}`}
        role="dialog"
        aria-modal="true"
        aria-label={isNew ? `Connect ${definition.name}` : `Edit ${connection.name}`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSave({ id, integrationId: definition.id, name, config, secrets });
        }}
      >
        <h2 className={s.dialogTitle}>
          {isNew ? `Connect ${definition.name}` : `Edit ${connection.name}`}
        </h2>
        <p className={s.pageBlurb}>{definition.blurb}</p>

        <div className={s.split}>
          <Field label="Connection id" hint="Lower-case, stable. Cannot change later.">
            <input
              required
              value={id}
              disabled={!isNew}
              pattern="[a-z0-9][a-z0-9-]*"
              onChange={(event) => setId(event.target.value)}
            />
          </Field>
          <Field label="Name" hint="What you call this environment, e.g. 'Prod cluster'.">
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
        </div>

        {definition.fields
          .filter((field) => field.kind !== "secret")
          .map((field) => (
            <Field key={field.key} label={field.label} hint={field.hint}>
              <input
                required={field.required}
                value={config[field.key] ?? ""}
                placeholder={field.placeholder}
                onChange={(event) =>
                  setConfig((current) => ({ ...current, [field.key]: event.target.value }))
                }
              />
            </Field>
          ))}

        {definition.fields
          .filter((field) => field.kind === "secret")
          .map((field) => {
            const stored = connection?.secretKeys.includes(field.key);
            return (
              <Field
                key={field.key}
                label={field.label}
                hint={
                  stored
                    ? `${field.hint} One is already stored — leave this empty to keep it.`
                    : field.hint
                }
              >
                <input
                  type="password"
                  autoComplete="off"
                  required={field.required && !stored}
                  value={secrets[field.key] ?? ""}
                  placeholder={stored ? "•••••••• stored in the keychain" : ""}
                  onChange={(event) =>
                    setSecrets((current) => ({ ...current, [field.key]: event.target.value }))
                  }
                />
              </Field>
            );
          })}

        <Notice tone="info">
          Credentials go to your operating system's keychain and are never
          written to this workspace, never included in an export, and never
          shown back to you. Meridian only reads from {definition.name} — this
          connection cannot change anything there.
        </Notice>

        <p className={s.cardMeta}>
          A successful test means: {definition.probeLabel}
        </p>
        <p className={s.cardMeta}>
          An agent bound to this connection is told the system, the endpoint
          and what Meridian can read — never the credential. Agents reach these
          systems with their own credentials, not Meridian\u2019s.
        </p>

        <Notice tone="error">{error}</Notice>
        <div className={s.dialogActions}>
          <Button variant="quiet" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {isNew ? "Save connection" : "Save changes"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function uniqueId(base: string, taken: string[]): string {
  if (!taken.includes(base)) return base;
  for (let index = 2; index < 100; index += 1)
    if (!taken.includes(`${base}-${index}`)) return `${base}-${index}`;
  return `${base}-${Date.now().toString(36)}`;
}
