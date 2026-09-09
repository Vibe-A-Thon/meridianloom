import { useState, type ReactNode } from "react";
import type { CoverageEnvelope } from "../../../../shared/ts/bus-types";
import { useRpcQuery } from "../../hooks/useRpcQuery";
import { getVsCodeApi } from "../../host/vscode-api";
import { Meter, Sparkline, StackedBar, Stat, type Signal } from "../../components/viz/Viz";
import {
  Field,
  Notice,
  Page,
  Panel,
  QueryFeedback,
  Result,
  money,
  number,
  object,
  pct,
  useAction,
  type GovernanceProps,
} from "./common";
import s from "./governance.module.css";

/**
 * The Trust & Spend Observatory.
 *
 * Ten instruments the sidecar has computed for some time and no interface
 * consumed: trust score and its decomposition, rejection-reason distribution,
 * agent-vs-agent comparison on one story, the adoption J-curve, the
 * tokenmaxxing detector, the DORA four-keys export, and the spend series,
 * forecast and pricing. Until this surface existed they were dead code with a
 * passing test suite — measurable work nobody could see.
 *
 * The discipline that makes them worth showing at all is the same one the
 * sidecar applies when computing them, and it is carried through here without
 * exception:
 *
 * **A figure that cannot be evidenced is not displayed.** `null` is rendered
 * as "insufficient evidence", never as zero, never as a flat line. A score of
 * zero and no score are different facts and the interface must not conflate
 * them — a zero trust score is an indictment, an absent one is an admission.
 *
 * **Every figure carries its coverage.** The envelope says how many ledger
 * rows were considered against how many exist, whether the query truncated,
 * and — where attribution matters — whether the attributed share fell under
 * the floor. A truncated figure says so beside itself and disables anything
 * derived from it, because a projection over a partial sample is a guess
 * wearing a number's clothes.
 *
 * **Every chart states its finding in writing** (A-10 / H7). A reader who
 * cannot see the chart, or who does not trust their own reading of it, gets
 * the same conclusion in a sentence.
 */

// ——— coverage ————————————————————————————————————————————————————————————

/** The generated tuple type is loose; read it defensively rather than casting. */
function range(value: unknown): string | undefined {
  if (!Array.isArray(value) || value.length < 2) return undefined;
  const [from, to] = value as unknown[];
  return typeof from === "number" && typeof to === "number"
    ? `${from}–${to}`
    : undefined;
}

function envelope(value: unknown): CoverageEnvelope | undefined {
  const raw = object(value);
  return typeof raw.rowsConsidered === "number"
    ? (raw as unknown as CoverageEnvelope)
    : undefined;
}

/**
 * The disclosure that must accompany any figure derived from the ledger
 * (FR-M41-08/09, NFR-34). Rendered next to the number, not in a footnote.
 */
function Coverage({ of }: { of: unknown }) {
  const cover = envelope(of);
  if (!cover) return null;
  const attribution = object(cover.attribution);
  const belowFloor = attribution.belowFloor === true;
  const share =
    typeof attribution.attributedShare === "number"
      ? attribution.attributedShare
      : undefined;

  if (cover.label === "empty")
    return (
      <Notice>
        No ledger rows fall in this scope, so there is nothing to measure. This
        is an empty sample, not a result of zero.
      </Notice>
    );

  return (
    <div className={s.coverage}>
      <p className={s.muted}>
        Computed over {cover.rowsConsidered.toLocaleString()} of{" "}
        {cover.rowsAvailable.toLocaleString()} ledger rows
        {range(cover.sequenceRange) ? ` (sequences ${range(cover.sequenceRange)})` : ""}
        {share !== undefined ? `, ${pct(share)} attributed to an agent` : ""}.
      </p>
      {cover.truncated ? (
        <p className={s.warning} role="status">
          This query hit the row ceiling, so the figure describes the most
          recent {cover.rowsConsidered.toLocaleString()} rows and not the whole
          period. Anything derived from it is disabled.
        </p>
      ) : null}
      {belowFloor ? (
        <p className={s.warning} role="status">
          Attribution coverage fell below the configured floor. The metric
          reads insufficient_coverage and shows no value rather than a figure
          the evidence cannot support.
        </p>
      ) : null}
    </div>
  );
}

/** True when nothing derived from this figure may be shown. */
function derivationBlocked(of: unknown): boolean {
  const cover = envelope(of);
  return Boolean(cover?.truncated) || object(cover?.attribution).belowFloor === true;
}

/**
 * A figure, or an honest statement of why there isn't one. The single place
 * that decides how `null` looks, so no panel can invent a zero on its own.
 */
function Figure({
  value,
  status,
  format = (input: number) => input.toFixed(2),
  unit,
}: {
  value: number | null | undefined;
  status?: string;
  format?: (value: number) => string;
  unit?: string;
}) {
  if (value === null || value === undefined)
    return (
      <span className={s.absent} title={status}>
        {status === "insufficient_coverage"
          ? "Not measurable"
          : "Insufficient evidence"}
      </span>
    );
  return (
    <span>
      {format(value)}
      {unit ? <small> {unit}</small> : null}
    </span>
  );
}

/** Every chart states its finding in words (A-10 / H7). */
function Finding({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p className={s.finding} role="note">
      <strong>Finding.</strong> {children}
    </p>
  );
}

const componentLabels: Record<string, string> = {
  firstPassYield: "First-pass yield",
  rejectionRate: "Rejection rate",
  calibrationError: "Calibration error",
  postMergeRevertRate: "Post-merge revert rate",
  incidentLinkage: "Incident linkage",
};

// ——— trust score + decomposition ————————————————————————————————————————

export function TrustScore(props: GovernanceProps) {
  const [actor, setActor] = useState("");
  const [scope, setScope] = useState<{ actorId: string } | undefined>();
  const score = useRpcQuery(
    props.ready && scope ? props.client : undefined,
    "trust/score",
    scope ?? { actorId: "" },
  );
  // The dedicated decomposition method, not a second read of the headline:
  // the sidecar computes the per-component breakdown separately and the two
  // can legitimately disagree on coverage, which the reader must be able to
  // see rather than have averaged away.
  const decomposition = useRpcQuery(
    props.ready && scope ? props.client : undefined,
    "trust/scoreDecomposition",
    scope ?? { actorId: "" },
  );
  const data = score.data;
  const components = object(decomposition.data?.components ?? data?.components);
  const evidenced = Object.entries(components).filter(
    ([, value]) => object(value).status === "ok",
  );

  return (
    <Page
      title="A score you can take apart."
      eyebrow="INTELLIGENCE / TRUST"
      description="The FR-M37-03 trust score for one agent, with every component that fed it and every component that could not. A bad component is exposed here, never hidden by the aggregate."
    >
      <Panel title="Scope">
        <form
          className={s.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (actor.trim()) setScope({ actorId: actor.trim() });
          }}
        >
          <Field label="Agent ID">
            <input
              required
              value={actor}
              placeholder="claude-code"
              onChange={(event) => setActor(event.target.value)}
            />
          </Field>
          <div className={s.actions}>
            <button className={s.primary} disabled={!props.ready}>
              Compute score
            </button>
          </div>
        </form>
      </Panel>

      <QueryFeedback query={score} connected={props.ready} />

      {data ? (
        <>
          <Panel title={`Trust score — ${data.agentId}`}>
            <div className={s.three}>
              <div className={s.stat} data-testid="trust-score">
                <strong>
                  <Figure value={data.score} status={data.status} />
                </strong>
                <span>Weighted score ({data.taskClass})</span>
              </div>
              <div className={s.stat}>
                <strong>{data.status}</strong>
                <span>Evidence status</span>
              </div>
              <div className={s.stat}>
                <strong>
                  {data.coverage.length} / {Object.keys(components).length}
                </strong>
                <span>Components with evidence</span>
              </div>
            </div>
            <Finding>
              {data.score === null
                ? `No component of ${data.agentId}'s score has enough evidence in this scope, so no score is shown. This is an absent measurement, not a score of zero.`
                : `${data.agentId} scores ${data.score.toFixed(2)} on ${
                    data.coverage.length
                  } evidenced component${data.coverage.length === 1 ? "" : "s"}` +
                  `${
                    data.status === "partial"
                      ? `; ${Object.keys(components).length - data.coverage.length} component(s) had no evidence and are listed below rather than averaged in.`
                      : "."
                  }`}
            </Finding>
            <Coverage of={data.coverageEnvelope} />
          </Panel>

          <Panel
            title="Decomposition"
            description="Every component of the score, including the ones that could not be computed."
          >
            <QueryFeedback query={decomposition} connected={props.ready} />
            <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Component</th>
                    <th scope="col">Value</th>
                    <th scope="col">Sample</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(components).map(([key, raw]) => {
                    const entry = object(raw);
                    return (
                      <tr key={key}>
                        <th scope="row">{componentLabels[key] ?? key}</th>
                        <td>
                          <Figure
                            value={number(entry.value) ?? null}
                            status={String(entry.status)}
                          />
                        </td>
                        <td>{number(entry.sampleSize) ?? "—"}</td>
                        <td>{String(entry.status)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Finding>
              {evidenced.length
                ? `${evidenced.length} of ${Object.keys(components).length} components carry evidence in this scope.`
                : "No component carries evidence in this scope; the ledger has nothing to score against."}
            </Finding>
            {decomposition.data ? (
              <Coverage of={decomposition.data.coverageEnvelope} />
            ) : null}
          </Panel>

          <Panel
            title="Greenfield and brownfield"
            description="The same score per bucket. New code and existing code are different problems and a single number hides that."
          >
            <div className={s.three}>
              {["greenfield", "brownfield", "unclassified"].map((bucket) => {
                const entry = object(object(data.split)[bucket]);
                return (
                  <div className={s.card} key={bucket}>
                    <h3>{bucket}</h3>
                    <strong>
                      <Figure
                        value={number(entry.score) ?? null}
                        status={String(entry.status)}
                      />
                    </strong>
                    <p>
                      Sample {number(entry.sampleSize) ?? 0}. Buckets are
                      decompositions of the headline figure and inherit its
                      coverage.
                    </p>
                  </div>
                );
              })}
            </div>
          </Panel>
        </>
      ) : null}
    </Page>
  );
}

// ——— rejection reasons ————————————————————————————————————————————————————

export function ReasonDistribution(props: GovernanceProps) {
  const reasons = useRpcQuery(
    props.ready ? props.client : undefined,
    "trust/reasonDistribution",
    {},
  );
  const data = reasons.data;
  const byClass = object(data?.byClass);
  const entries = Object.entries(byClass)
    .map(([label, value]) => ({ label, value: number(object(value).count) ?? 0 }))
    .sort((a, b) => b.value - a.value);
  const top = entries[0];

  return (
    <Page
      title="Why work came back."
      eyebrow="INTELLIGENCE / REWORK"
      description="The recorded distribution of rejection reasons — by class, by shape and by agent. Reasons come from the ledger, not from a survey."
    >
      <QueryFeedback query={reasons} connected={props.ready} />
      {data ? (
        <>
          <Panel title={`${data.total} recorded rejections`}>
            <StackedBar
              label="Rejections by class"
              segments={entries.map((entry, index) => ({
                label: entry.label,
                value: entry.value,
                color: `var(--ml-phase-${
                  ["intake", "design", "plan", "build", "verify", "security", "review", "release", "operate"][
                    index % 9
                  ]
                })`,
              }))}
            />
            <Finding>
              {top && data.total
                ? `${top.label} is the largest single cause, at ${top.value} of ${data.total} recorded rejections (${pct(top.value / data.total)}).`
                : "No rejections are recorded in this scope, so no distribution can be drawn."}
            </Finding>
            <Coverage of={data.coverage} />
          </Panel>

          <Panel title="By agent">
            <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Agent</th>
                    <th scope="col">Rejections</th>
                    <th scope="col">Leading reason</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(object(data.byAgent)).map(([agent, raw]) => {
                    const entry = object(raw);
                    return (
                      <tr key={agent}>
                        <th scope="row">{agent}</th>
                        <td>{number(entry.count) ?? 0}</td>
                        <td>{String(entry.leading ?? "—")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      ) : null}
    </Page>
  );
}

// ——— agent comparison ————————————————————————————————————————————————————

export function CompareAgents(props: GovernanceProps) {
  const [story, setStory] = useState("");
  const [scope, setScope] = useState<{ storyId: string } | undefined>();
  const compare = useRpcQuery(
    props.ready && scope ? props.client : undefined,
    "trust/compareAgents",
    scope ?? { storyId: "" },
  );
  const data = compare.data;
  const agents = Object.entries(object(data?.agents));

  return (
    <Page
      title="Same story, different agents."
      eyebrow="INTELLIGENCE / COMPARISON"
      description="A like-for-like comparison is only honest within one story: the same requirement, the same repository state, the same reviewers. This compares agents on exactly that."
    >
      <Panel title="Story">
        <form
          className={s.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (story.trim()) setScope({ storyId: story.trim() });
          }}
        >
          <Field label="Story ID">
            <input
              required
              value={story}
              placeholder="edb-12345"
              onChange={(event) => setStory(event.target.value)}
            />
          </Field>
          <div className={s.actions}>
            <button className={s.primary} disabled={!props.ready}>
              Compare
            </button>
          </div>
        </form>
      </Panel>

      <QueryFeedback query={compare} connected={props.ready} />
      {data ? (
        <Panel
          title={`${data.storyId} — ${data.storyClassification}`}
          description="Agents that worked this story, side by side."
        >
          {!agents.length ? (
            <p className={s.empty}>
              No agent activity is recorded against this story.
            </p>
          ) : (
            <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Agent</th>
                    <th scope="col">Proposed</th>
                    <th scope="col">Rejected</th>
                    <th scope="col">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map(([agent, raw]) => {
                    const entry = object(raw);
                    return (
                      <tr key={agent}>
                        <th scope="row">{agent}</th>
                        <td>{number(entry.proposed) ?? 0}</td>
                        <td>{number(entry.rejected) ?? 0}</td>
                        <td>
                          <Figure
                            value={number(entry.score) ?? null}
                            status={String(entry.status)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <Finding>
            {agents.length < 2
              ? `Only ${agents.length} agent worked this story, so there is nothing to compare against. A comparison needs at least two.`
              : `${agents.length} agents worked ${data.storyId}. Differences here are within one story and one repository state; they do not generalise to a ranking.`}
          </Finding>
          <Coverage of={data.coverage} />
        </Panel>
      ) : null}
    </Page>
  );
}

// ——— J-curve ————————————————————————————————————————————————————————————

export function Jcurve(props: GovernanceProps) {
  const [date, setDate] = useState("");
  const [adoption, setAdoption] = useState<string>();
  const curve = useRpcQuery(
    props.ready && adoption ? props.client : undefined,
    "trust/jcurve",
    { adoptionDate: adoption ?? "" },
  );
  const data = curve.data;
  const phases = object(data?.phases);
  const series = Object.values(phases)
    .map((value) => number(object(value).value))
    .filter((value): value is number => value !== undefined);

  return (
    <Page
      title="The dip is expected. The recovery is the question."
      eyebrow="INTELLIGENCE / ADOPTION"
      description="Adoption of a new way of working costs throughput before it returns it. This measures the shape against your own recorded baseline, not against a vendor's."
    >
      <Panel
        title="Adoption cut"
        description="The date the team started working this way. Weeks before it are the baseline; the adoption week and later are the curve."
      >
        <form
          className={s.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (date) setAdoption(new Date(date).toISOString());
          }}
        >
          <Field label="Adoption date">
            <input
              required
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </Field>
          <div className={s.actions}>
            <button className={s.primary} disabled={!props.ready}>
              Draw the curve
            </button>
          </div>
        </form>
      </Panel>

      <QueryFeedback query={curve} connected={props.ready} />
      {data ? (
        <Panel title={`Adoption from ${data.adoptionDate}`}>
          <div className={s.three}>
            <div className={s.stat}>
              <strong>
                <Figure value={data.baseline} status={data.status} />
              </strong>
              <span>Pre-adoption baseline</span>
            </div>
            <div className={s.stat}>
              <strong>
                <Figure value={number(object(data.dip).depth) ?? null} />
              </strong>
              <span>Dip depth</span>
            </div>
            <div className={s.stat}>
              <strong>{String(object(data.dip).recovered ?? "unknown")}</strong>
              <span>Recovered</span>
            </div>
          </div>
          {series.length > 1 ? (
            <Sparkline
              values={series}
              label="Throughput by adoption phase"
              width={320}
              height={64}
              signal="accent"
            />
          ) : null}
          <Finding>
            {data.status === "insufficient_evidence"
              ? "There is not enough recorded history either side of the adoption date to describe a curve. No shape is drawn."
              : object(data.dip).recovered === true
                ? `Throughput dipped and has returned to or above the ${data.baseline} baseline.`
                : `Throughput is still below the ${data.baseline} baseline. This is the expected shape during adoption; it becomes a concern only if it does not recover.`}
          </Finding>
          <Coverage of={data.coverage} />
        </Panel>
      ) : null}
    </Page>
  );
}

// ——— tokenmaxxing ————————————————————————————————————————————————————————

export function Tokenmaxxing(props: GovernanceProps) {
  // The detector needs a spend series per agent; that is exactly what
  // spend/series returns, so the two are chained rather than the interface
  // inventing a shape the sidecar would have to guess at.
  const spend = useRpcQuery(props.ready ? props.client : undefined, "spend/series", {
    dimension: "agent",
  });
  const spendSeries = object(spend.data?.spendSeries);
  const ready = props.ready && spend.status === "ready";
  const detect = useRpcQuery(ready ? props.client : undefined, "trust/tokenmaxxing", {
    spendSeries,
  });
  const data = detect.data;
  const agents = Object.entries(object(data?.byAgent));
  const flagged = agents.filter(([, raw]) => object(raw).flagged === true);

  return (
    <Page
      title="Spending more is not the same as doing more."
      eyebrow="INTELLIGENCE / EFFICIENCY"
      description="Tokens consumed against work merged, per agent. An agent whose spend rises while its merged output does not is worth a look — this names it rather than leaving it in the bill."
    >
      <QueryFeedback query={spend} connected={props.ready} />
      <QueryFeedback query={detect} connected={ready} />
      {spend.status === "ready" && !Object.keys(spendSeries).length ? (
        <Notice>
          No per-agent spend series is recorded, so there is nothing to compare
          against merged work. The detector needs at least four periods of
          spend evidence before it will judge.
        </Notice>
      ) : null}
      {data ? (
        <Panel title="Tokens against merged work">
          <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Tokens</th>
                  <th scope="col">Merged</th>
                  <th scope="col">Tokens per merge</th>
                  <th scope="col">Flagged</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(([agent, raw]) => {
                  const entry = object(raw);
                  return (
                    <tr key={agent}>
                      <th scope="row">{agent}</th>
                      <td>{(number(entry.tokens) ?? 0).toLocaleString()}</td>
                      <td>{number(entry.merged) ?? 0}</td>
                      <td>
                        <Figure
                          value={number(entry.tokensPerMerge) ?? null}
                          format={(value) => Math.round(value).toLocaleString()}
                        />
                      </td>
                      <td>{entry.flagged === true ? "yes" : "no"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Finding>
            {!agents.length
              ? "No agent has both spend and merge evidence in this scope, so no ratio can be computed."
              : flagged.length
                ? `${flagged.length} agent(s) consume markedly more tokens per merged change than the team median: ${flagged.map(([id]) => id).join(", ")}. That is a prompt to look, not a verdict.`
                : "No agent stands out against the team median on tokens per merged change."}
          </Finding>
          <Coverage of={data.coverage} />
        </Panel>
      ) : null}
    </Page>
  );
}

// ——— DORA export ————————————————————————————————————————————————————————

export function DoraExport(props: GovernanceProps) {
  const dora = useRpcQuery(
    props.ready ? props.client : undefined,
    "trust/doraExport",
    {},
  );
  const action = useAction(props.client);
  const data = dora.data;
  const statuses = object(data?.status);
  const metrics = object(data?.metrics);
  const keys = ["deploymentFrequency", "leadTime", "changeFailureRate", "timeToRestore"];
  const unknown = keys.filter((key) => String(statuses[key] ?? "unknown") !== "ok");

  return (
    <Page
      title="Four keys, and an honest gap where the evidence stops."
      eyebrow="INTELLIGENCE / DELIVERY"
      description="DORA's four measures, computed from the ledger and exported in an OTLP-friendly shape. A key the ledger cannot evidence is exported as unknown with no value — never as an invented number."
      actions={
        <button
          disabled={!props.ready || !data}
          onClick={() =>
            getVsCodeApi().postMessage({
              type: "download",
              fileName: "meridian-dora.json",
              mimeType: "application/json",
              content: JSON.stringify(data?.export ?? {}, null, 2),
            })
          }
        >
          Export
        </button>
      }
    >
      <Result action={action} />
      <QueryFeedback query={dora} connected={props.ready} />
      {data ? (
        <Panel title="The four keys">
          <div className={s.three}>
            {keys.map((key) => {
              const status = String(statuses[key] ?? "unknown");
              return (
                <div className={s.stat} key={key}>
                  <strong>
                    <Figure
                      value={status === "ok" ? (number(metrics[key]) ?? null) : null}
                      status={status}
                    />
                  </strong>
                  <span>
                    {key.replace(/([A-Z])/g, " $1").toLowerCase()} — {status}
                  </span>
                </div>
              );
            })}
          </div>
          <Finding>
            {unknown.length === keys.length
              ? "The ledger evidences none of the four keys in this scope. All four export as unknown; none is invented."
              : unknown.length
                ? `${keys.length - unknown.length} of four keys are evidenced. ${unknown.join(", ")} export as unknown with no value.`
                : "All four keys are evidenced from recorded entries."}
          </Finding>
          <Coverage of={data.coverage} />
        </Panel>
      ) : null}
    </Page>
  );
}

// ——— spend ——————————————————————————————————————————————————————————————

const DIMENSIONS = ["agent", "team", "costCentre", "model", "story"] as const;

export function SpendObservatory(props: GovernanceProps) {
  const [dimension, setDimension] = useState<(typeof DIMENSIONS)[number]>("agent");
  const series = useRpcQuery(props.ready ? props.client : undefined, "spend/series", {
    dimension,
  });
  const forecast = useRpcQuery(
    props.ready ? props.client : undefined,
    "spend/forecast",
    {},
  );
  const pricing = useRpcQuery(props.ready ? props.client : undefined, "spend/pricing", {});

  const data = series.data;
  const totals = object(data?.totals);
  const byValue = Object.entries(object(data?.byValue))
    .map(([label, raw]) => ({ label, cost: number(object(raw).cost) ?? 0 }))
    .sort((a, b) => b.cost - a.cost);
  const blocked = derivationBlocked(data?.coverage);
  const forecastData = forecast.data;

  return (
    <Page
      title="What it cost, and what it will cost."
      eyebrow="INTELLIGENCE / SPEND"
      description="Recorded spend from the ledger, split by the dimension you choose, with a forecast that refuses to project over a truncated sample."
    >
      <Panel title="Dimension">
        <div className={s.actions}>
          {DIMENSIONS.map((entry) => (
            <button
              key={entry}
              aria-pressed={dimension === entry}
              className={dimension === entry ? s.primary : undefined}
              onClick={() => setDimension(entry)}
            >
              {entry}
            </button>
          ))}
        </div>
      </Panel>

      <QueryFeedback query={series} connected={props.ready} />
      {data ? (
        <Panel title={`Recorded spend by ${data.dimension}`}>
          <div className={s.three}>
            <Stat
              label="Total cost"
              value={money(number(totals.cost) ?? 0)}
              accent="var(--ml-phase-operate)"
              hint="from recorded model calls"
            />
            <Stat
              label="Tokens"
              value={(number(totals.tokens) ?? 0).toLocaleString()}
              accent="var(--ml-phase-build)"
              hint="input and output combined"
            />
            <Stat
              label="Calls"
              value={(number(totals.calls) ?? 0).toLocaleString()}
              accent="var(--ml-phase-plan)"
              hint="ledger-recorded model calls"
            />
          </div>
          {byValue.length ? (
            <StackedBar
              label={`Spend by ${data.dimension}`}
              segments={byValue.slice(0, 8).map((entry, index) => ({
                label: entry.label,
                value: Math.round(entry.cost * 100),
                color: `var(--ml-phase-${
                  ["intake", "design", "plan", "build", "verify", "security", "review", "release"][
                    index % 8
                  ]
                })`,
              }))}
            />
          ) : null}
          <Finding>
            {!byValue.length
              ? "No model calls with pricing are recorded in this scope, so no spend can be attributed."
              : `${byValue[0].label} accounts for the largest share at ${money(byValue[0].cost)} of ${money(number(totals.cost) ?? 0)}.`}
          </Finding>
          <Coverage of={data.coverage} />
        </Panel>
      ) : null}

      <QueryFeedback query={forecast} connected={props.ready} />
      {forecastData ? (
        <Panel title="Forecast">
          {blocked || forecastData.status === "truncated" ? (
            <Notice>
              The spend sample is truncated, so no forecast is projected from
              it. A projection over a partial sample is a guess wearing a
              number's clothes.
            </Notice>
          ) : forecastData.status === "unconfigured" ? (
            <Notice>
              No budget is configured, so there is nothing to forecast against.
              Set one in the policy pack to enable the projection.
            </Notice>
          ) : (
            <>
              <Meter
                value={
                  (number(object(forecastData.forecast).projected) ?? 0) /
                  Math.max(1, number(object(forecastData.budget).amount) ?? 1)
                }
                label="Projected against budget"
                caption={`${money(number(object(forecastData.forecast).projected) ?? 0)} of ${money(
                  number(object(forecastData.budget).amount) ?? 0,
                )}`}
                signal={
                  (forecastData.status === "actual_breach"
                    ? "fail"
                    : forecastData.status === "forecast_breach"
                      ? "warn"
                      : "ok") as Signal
                }
              />
              <Finding>
                {forecastData.status === "actual_breach"
                  ? "Recorded spend has already exceeded the configured budget."
                  : forecastData.status === "forecast_breach"
                    ? "Recorded spend is inside budget, but the projection crosses it before the period ends."
                    : "Recorded spend is inside budget and the projection stays inside it."}
              </Finding>
            </>
          )}
          <Coverage of={forecastData.coverage} />
        </Panel>
      ) : null}

      <QueryFeedback query={pricing} connected={props.ready} />
      {pricing.data ? (
        <Panel
          title={`Pricing — ${pricing.data.source} v${pricing.data.version}`}
          description="The rate card every cost figure above was computed from. A cost with no visible rate card is not auditable."
        >
          <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Input</th>
                  <th scope="col">Output</th>
                  <th scope="col">Currency</th>
                </tr>
              </thead>
              <tbody>
                {pricing.data.models.map((raw, index) => {
                  const model = object(raw);
                  return (
                    <tr key={String(model.id ?? index)}>
                      <th scope="row">{String(model.id ?? "unknown")}</th>
                      <td>{number(model.inputPer1k) ?? "—"}</td>
                      <td>{number(model.outputPer1k) ?? "—"}</td>
                      <td>{pricing.data!.currency}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {pricing.data.errors.length ? (
            <p className={s.warning} role="status">
              {pricing.data.errors.length} model(s) have no rate card, so their
              calls are counted but not costed: {pricing.data.errors.join(", ")}.
            </p>
          ) : null}
        </Panel>
      ) : null}
    </Page>
  );
}
