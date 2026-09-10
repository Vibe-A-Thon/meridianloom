import { useState } from "react";
import { useRpcQuery } from "../../hooks/useRpcQuery";
import { getVsCodeApi } from "../../host/vscode-api";
import { Meter, Ring, Stat, type Signal } from "../../components/viz/Viz";
import {
  Field,
  Notice,
  Page,
  Panel,
  QueryFeedback,
  number,
  object,
  type GovernanceProps,
} from "./common";
import s from "./governance.module.css";

/**
 * F2 — the evidence gate.
 *
 * `gaps_implementation.md` §F2 is a decision phase, not a build phase: twenty
 * real stories from the team's own backlog, through F0 + F1, with the team's
 * own agents, and then a written decision — GO to F3, STOP and ship the
 * recorder, PIVOT to analytics, or KILL — with the raw ledger slice attached.
 *
 * Every measure it names was already computable, and computable in seven
 * different places. A team finishing twenty stories had to assemble the
 * verdict by hand from seven panels, which is exactly the manual step this
 * project has repeatedly got wrong: each part true, the whole unverified.
 *
 * What this screen is careful about is the shape of the answer. Two of the
 * seven measures cannot be recorded at all — nothing counts provenance reads,
 * and the product deliberately does not phone home to learn who is still using
 * it at week eight. Those read *unavailable with the reason*, never zero, and
 * a GO verdict says out loud that query usage is unevidenced even when
 * everything else lines up. §F2 requires it for GO; the honest move is to
 * flag the gap rather than let a green verdict imply it was met.
 *
 * STOP is drawn as a success, because it is one (R29). "Ship the Flight
 * Recorder" is a real outcome of this gate, not a failure of it.
 */

const VERDICT: Readonly<
  Record<string, { label: string; signal: Signal; meaning: string }>
> = {
  go: {
    label: "GO",
    signal: "ok",
    meaning:
      "Gating measurably helped and stability held. §F2 says build the Orchestra.",
  },
  stop: {
    label: "STOP — and ship",
    signal: "warn",
    meaning:
      "The recorder and gates are used and valued, but the evidence does not justify building Meridian's own agents. Ship Flight Recorder + Governor as the product. This is a success, not a failure (R29).",
  },
  pivot: {
    label: "PIVOT",
    signal: "warn",
    meaning:
      "Provenance queries are not run and gates are ceremony, but the trust analytics are used. Narrow to the analytics product and drop the gating.",
  },
  kill: {
    label: "KILL",
    signal: "fail",
    meaning: "None of it is used. §15 applies.",
  },
  insufficient_evidence: {
    label: "Not yet decidable",
    signal: "idle",
    meaning:
      "The evidence does not reach the gate's own thresholds. This is a real outcome, and a far cheaper one than a GO that starts the Orchestra build on a thin sample.",
  },
};

const MEASURE_LABELS: Record<string, string> = {
  rejectionRate: "Rejection rate, gated vs ungated",
  gateCatches: "Defects the gates caught",
  changeFailureRate: "Change failure rate vs baseline",
  approvalHygiene: "Approval hygiene (FR-M20-06)",
  timeCostPerGatedChange: "Time the layer costs",
  provenanceQueriesRun: "Provenance queries actually run",
  firstValueRetention: "First-value retention at week 8",
};

export function EvidenceGate(props: GovernanceProps) {
  const [baseline, setBaseline] = useState("");
  const [applied, setApplied] = useState<number | undefined>();
  const report = useRpcQuery(
    props.ready ? props.client : undefined,
    "evidence/gate",
    applied === undefined ? {} : { baselineChangeFailureRate: applied },
  );
  const data = report.data;
  const stories = object(data?.stories);
  const total = number(stories.total) ?? 0;
  const required = number(stories.required) ?? 20;
  const recommendation = object(data?.recommendation);
  const verdictKey = String(recommendation.verdict ?? "insufficient_evidence");
  const verdict = VERDICT[verdictKey] ?? VERDICT.insufficient_evidence;
  const reasons = Array.isArray(recommendation.reasons)
    ? (recommendation.reasons as string[])
    : [];
  const measures = object(data?.measures);
  const unavailable = Object.entries(measures).filter(
    ([, value]) => object(value).status !== "ok",
  );

  return (
    <Page
      title="Twenty stories, then a decision."
      eyebrow="EVIDENCE / F2 GATE"
      description="The gate computed from this workspace's own ledger rather than argued from impressions. Every measure that cannot be evidenced says so; a verdict over too few stories says that too."
      actions={
        <button
          disabled={!data}
          onClick={() =>
            getVsCodeApi().postMessage({
              type: "download",
              fileName: "meridian-f2-evidence.json",
              mimeType: "application/json",
              content: JSON.stringify(data ?? {}, null, 2),
            })
          }
        >
          Export the report
        </button>
      }
    >
      <Panel
        title="Your baseline"
        description="The team's own change failure rate before Meridian. The ledger cannot know it — without it, that comparison reads unavailable rather than inventing a number to beat."
      >
        <form
          className={s.form}
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = Number(baseline);
            if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1)
              setApplied(parsed);
          }}
        >
          <Field
            label="Change failure rate (0–1)"
            hint="For example 0.15 for 15%. Leave empty to compute everything else."
          >
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={baseline}
              placeholder="0.15"
              onChange={(event) => setBaseline(event.target.value)}
            />
          </Field>
          <div className={s.actions}>
            <button className={s.primary} disabled={!props.ready}>
              Recompute with this baseline
            </button>
          </div>
        </form>
      </Panel>

      <QueryFeedback query={report} connected={props.ready} />

      {data ? (
        <>
          <Panel title={verdict.label}>
            <div className={s.three}>
              <Stat
                label="Stories in scope"
                value={`${total} / ${required}`}
                accent={
                  total >= required
                    ? "var(--ml-signal-ok)"
                    : "var(--ml-signal-idle)"
                }
                hint={
                  total >= required
                    ? "the gate is defined over twenty"
                    : "fewer than twenty is not a smaller answer, it is no answer"
                }
                visual={
                  <Ring
                    value={Math.min(total, required)}
                    total={required}
                    label="Stories toward the F2 gate"
                    caption={`${total}`}
                  />
                }
              />
              <Stat
                label="Gated"
                value={number(stories.gated) ?? 0}
                accent="var(--ml-phase-review)"
                hint="stories that passed through the governance layer"
              />
              <Stat
                label="Ungated"
                value={number(stories.ungated) ?? 0}
                accent="var(--ml-phase-build)"
                hint="the comparison group — without it there is nothing to compare"
              />
            </div>

            <p className={s.finding} role="note">
              <strong>What this verdict means.</strong> {verdict.meaning}
            </p>

            {reasons.length ? (
              <ul>
                {reasons.map((reason) => (
                  <li key={reason} className={s.muted}>
                    {reason}
                  </li>
                ))}
              </ul>
            ) : null}

            <Meter
              value={Math.min(1, total / Math.max(1, required))}
              label="Evidence collected"
              caption={`${total} of ${required} stories`}
              signal={verdict.signal}
            />
          </Panel>

          <Panel
            title="The seven measures"
            description="§F2 names these. Two of them the product cannot record, and they say so here rather than reading as zero."
          >
            <div className={s.tableWrap} tabIndex={0} aria-label="Scrollable data table">
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col">Status</th>
                    <th scope="col">Value</th>
                    <th scope="col">What it says</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(measures).map(([key, raw]) => {
                    const measure = object(raw);
                    const value = number(measure.value);
                    return (
                      <tr key={key}>
                        <th scope="row">{MEASURE_LABELS[key] ?? key}</th>
                        <td>{String(measure.status)}</td>
                        <td>
                          {measure.status === "ok" && value !== undefined ? (
                            value.toFixed(3)
                          ) : (
                            <span className={s.absent}>Not evidenced</span>
                          )}
                        </td>
                        <td>{String(measure.note ?? "")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {unavailable.length ? (
              <Notice>
                {unavailable.length} of {Object.keys(measures).length} measures
                are not evidenced. Two of those — provenance queries run, and
                week-8 retention — cannot be recorded by a tool that does not
                watch you or phone home. Answer those by asking your testers,
                and record the answers beside this report.
              </Notice>
            ) : null}
          </Panel>

          <Panel
            title="The exit criterion"
            description="§F2 closes on a written decision recording the measurements and the path chosen, with the raw ledger slice attached."
          >
            <p className={s.muted}>
              Export above gives you the computed half: every measure, its
              status, and the coverage envelope over the rows it read. The
              written half is yours — the decision, the two measures only your
              testers can answer, and why you chose the path you chose.
            </p>
          </Panel>
        </>
      ) : null}
    </Page>
  );
}
