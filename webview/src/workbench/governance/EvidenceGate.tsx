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
 * The evidence gate (MV5), scored against `docs/evidence-gate.md`.
 *
 * The thresholds were written before any study data existed, and the
 * instrument behind this screen applies them: ten measures, each met, not met
 * or unmeasured, with §4's outcomes tried in order. This screen's job is to
 * keep the shape of that answer intact on its way to a person.
 *
 * Three things it is careful about.
 *
 * - **Unmeasured never looks like a pass.** It is spelled out in the status
 *   column, and a status the screen does not recognise reads as unmeasured.
 *   The first version of this screen showed "unavailable" beside a verdict
 *   that could still be GO.
 * - **An unknown verdict is not decidable, never GO.**
 * - **A broken preregistration is announced.** If the thresholds applied are
 *   not the ones the study registered, §5 says the result is published as
 *   invalidated, and the screen raises that as an alert rather than a footnote.
 *
 * From the editor, only this workspace's ledger is read. The measures that need
 * people (adjudications, the baseline arm's figures, retention) come from a
 * study record scored with `python -m meridian_core.cli evidence-gate`.
 *
 * STOP is drawn as a success, because it is one (R29).
 */

const VERDICT: Readonly<
  Record<string, { label: string; signal: Signal; meaning: string }>
> = {
  go: {
    label: "GO",
    signal: "ok",
    meaning:
      "Every preregistered threshold holds, and a task class exists where a Meridian agent would plausibly do better (O1). §4 says build the Orchestra.",
  },
  stop: {
    label: "STOP — and ship",
    signal: "warn",
    meaning:
      "The governance layer holds, but O1 is not satisfied. Ship the Flight Recorder and Governor as the product. This is a success, not a failure (R29).",
  },
  pivot: {
    label: "PIVOT",
    signal: "warn",
    meaning:
      "Nobody queries provenance (P4 fails), but the trust instruments change decisions (P5 holds). Drop the gating and keep the measurement.",
  },
  kill: {
    label: "KILL",
    signal: "fail",
    meaning:
      "Retention failed, stability failed, or review cost rose while the gates caught nothing. The layer costs more than it returns.",
  },
  unclassified: {
    label: "No outcome applies",
    signal: "warn",
    meaning:
      "§4 names no outcome for this combination of results. It is reported as it is, not rounded to the nearest outcome.",
  },
  insufficient_evidence: {
    label: "Not yet decidable",
    signal: "idle",
    meaning:
      "The evidence does not reach the preregistered thresholds: too few stories, no study record, or an outcome that depends on a threshold nobody measured. This is a real outcome, and a far cheaper one than a GO on a thin sample.",
  },
};

const UNMEASURED = "Unmeasured — never counted as met";

const STATUS: Readonly<Record<string, string>> = {
  met: "Met",
  not_met: "Not met",
  unmeasured: UNMEASURED,
};

const REGISTRATION: Readonly<Record<string, string>> = {
  not_registered:
    "No study record is scored on this screen, so nothing is registered here. A study registers its thresholds digest before its first story.",
  intact: "The thresholds applied are the ones this study registered.",
  digest_mismatch:
    "The thresholds applied are not the ones this study registered. Publish this result as invalidated (§5).",
  registered_after_data:
    "This study registered its thresholds after its first story was measured. Publish this result as invalidated (§5).",
};

function shownValue(status: unknown, value: unknown) {
  if (status !== "met" && status !== "not_met") return undefined;
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "string" && value) return value;
  return undefined;
}

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
  const arms = object(stories.byArm);
  const recommendation = object(data?.recommendation);
  const verdictKey = String(recommendation.verdict ?? "insufficient_evidence");
  const verdict = VERDICT[verdictKey] ?? VERDICT.insufficient_evidence;
  const reasons = Array.isArray(recommendation.reasons)
    ? recommendation.reasons.map(String)
    : [];
  const registration = object(data?.preregistration);
  const registrationState = String(registration.state ?? "not_registered");
  const invalidated =
    registration.invalidated === true || recommendation.invalidated === true;
  const measures = Object.entries(object(data?.measures));
  const unmeasured = measures.filter(([, raw]) => {
    const status = object(raw).status;
    return status !== "met" && status !== "not_met";
  });

  return (
    <Page
      title="Twenty stories, then a decision."
      eyebrow="EVIDENCE GATE / MV5"
      description="Scored against docs/evidence-gate.md, the thresholds written before any study data existed. A threshold nobody measured is never counted as met, and an outcome that depends on one is not reached."
      actions={
        <button
          disabled={!data}
          onClick={() =>
            getVsCodeApi().postMessage({
              type: "download",
              fileName: "meridian-evidence-gate.json",
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
        description="The team's own change failure rate before Meridian, for P3. The ledger cannot know it; without it, P3 reads unmeasured rather than inventing a number to beat."
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
            {invalidated ? (
              <p className={s.finding} role="alert">
                <strong>The preregistration is not intact.</strong>{" "}
                {REGISTRATION[registrationState] ??
                  "Publish this result as invalidated (§5)."}
              </p>
            ) : null}
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
                    label="Stories toward the evidence gate"
                    caption={`${total}`}
                  />
                }
              />
              <Stat
                label="Arm C, Governor"
                value={number(arms.C) ?? 0}
                accent="var(--ml-phase-review)"
                hint="the arm the ledger measures are read from"
              />
              <Stat
                label="Arms A and B"
                value={`${number(arms.A) ?? 0} · ${number(arms.B) ?? 0}`}
                accent="var(--ml-phase-build)"
                hint="baseline tools, and tools with the recorder"
              />
            </div>

            <p className={s.finding} role="note">
              <strong>What this outcome means.</strong> {verdict.meaning}
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
            title="The ten preregistered measures"
            description="docs/evidence-gate.md §3, written before any data existed."
          >
            <div
              className={s.tableWrap}
              tabIndex={0}
              aria-label="Scrollable data table"
            >
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col">Status</th>
                    <th scope="col">Value</th>
                    <th scope="col">Source</th>
                    <th scope="col">What it says</th>
                  </tr>
                </thead>
                <tbody>
                  {measures.map(([key, raw]) => {
                    const measure = object(raw);
                    const threshold = object(measure.threshold);
                    const value = shownValue(measure.status, measure.value);
                    return (
                      <tr key={key}>
                        <th scope="row">
                          {key}
                          {threshold.measure ? ` · ${String(threshold.measure)}` : ""}
                        </th>
                        <td>{STATUS[String(measure.status)] ?? UNMEASURED}</td>
                        <td>
                          {value ?? (
                            <span className={s.absent}>Not evidenced</span>
                          )}
                        </td>
                        <td>{String(measure.source ?? "")}</td>
                        <td>{String(measure.note ?? "")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {unmeasured.length ? (
              <Notice>
                {unmeasured.length} of {measures.length} measures are
                unmeasured. This screen reads this workspace&apos;s ledger only.
                The measures that need people come from a study record, scored
                with python -m meridian_core.cli evidence-gate --study.
              </Notice>
            ) : null}
          </Panel>

          <Panel
            title="The preregistration"
            description="§5: once the first story is measured, a changed threshold invalidates the result."
          >
            <p className={s.muted}>
              {REGISTRATION[registrationState] ?? REGISTRATION.not_registered}
            </p>
            {registration.thresholdsDigest ? (
              <p className={s.muted}>
                Applied: <code>{String(registration.thresholdsDigest)}</code>
              </p>
            ) : null}
          </Panel>

          <Panel
            title="The exit criterion"
            description="A written go / stop / pivot / kill decision, with the raw ledger slice attached."
          >
            <p className={s.muted}>
              The command-line scorer writes the computed report, the ledger
              slice as a signed bundle, and a draft of the decision carrying
              both files&apos; digests. The decision itself is written by a
              person, and if it departs from the computed outcome it says why.
            </p>
          </Panel>
        </>
      ) : null}
    </Page>
  );
}
