import { useMemo } from "react";
import type React from "react";
import {
  SDLC_PHASES,
  SDLC_PHASE_LABELS,
  type SdlcPhase,
  type WorkbenchAgent,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import { Ring, StackedBar, Stat } from "../../components/viz/Viz";
import {
  Button,
  Empty,
  Notice,
  Page,
  Panel,
  Tag,
  useAction,
} from "./common";
import s from "./catalogue.module.css";

/**
 * A phase's identity colour, defined once in tokens.css and used wherever the
 * phase appears so the hue becomes something the reader learns rather than
 * decodes. It always sits beside the phase's name — never alone.
 */
const phaseColor = (phase: SdlcPhase) => `var(--ml-phase-${phase})`;

/**
 * The SDLC Phases board.
 *
 * Nine phases, and for each one the agents that will be convened when a
 * deliverable is dispatched. This is the tagging surface *and* the coverage
 * report: a phase with no active agent is a hole in the delivery chain, and
 * the board says so rather than leaving the user to notice.
 *
 * Tagging is reversible and immediate — one click on the agent chip under a
 * phase adds or removes it. That is deliberately lighter than the agent
 * editor: assigning a roster to phases is something you do repeatedly while
 * shaping a team, and a modal per change would make it tedious.
 *
 * What is shown is only what will actually happen: an agent in Learning is
 * listed under the phases it is tagged with, but greyed and labelled, because
 * it is tagged and *will not be convened*. Both facts matter.
 */

const PHASE_PURPOSE: Readonly<Record<SdlcPhase, string>> = {
  intake: "Clarify the request, find the ambiguities, agree it is ready.",
  design: "Decide the shape, record the decisions, allocate the constraints.",
  plan: "Break it into work packets with acceptance tests contracted first.",
  build: "Implement, with the repository's conventions outranking defaults.",
  verify: "Prove the acceptance criteria are covered and passing.",
  security: "Scan, check the threat surface, clear or waive the findings.",
  review: "Critique adversarially, then a human approves before merge.",
  release: "Produce the artefact and the rollback plan.",
  operate: "Watch the SLOs, triage regressions, feed what is learned back.",
};

export interface PhasesTabProps {
  controller: WorkbenchController;
}

export function PhasesTab({ controller }: PhasesTabProps) {
  const snapshot = controller.snapshot;
  const agents = snapshot?.agents ?? [];
  const action = useAction();

  const byPhase = useMemo(() => {
    const map = new Map<SdlcPhase, WorkbenchAgent[]>();
    for (const phase of SDLC_PHASES)
      map.set(
        phase,
        agents.filter((agent) => agent.phases.includes(phase)),
      );
    return map;
  }, [agents]);

  const covered = SDLC_PHASES.filter((phase) =>
    (byPhase.get(phase) ?? []).some((agent) => agent.mode === "active"),
  );
  const gaps = SDLC_PHASES.filter((phase) => !covered.includes(phase));

  const toggle = (agent: WorkbenchAgent, phase: SdlcPhase) => {
    const has = agent.phases.includes(phase);
    const next = has
      ? agent.phases.filter((entry) => entry !== phase)
      : [...agent.phases, phase];
    return action.run(
      () => controller.execute("agent/assign", { id: agent.id, phases: next }),
      has
        ? `${agent.name} removed from ${SDLC_PHASE_LABELS[phase]}.`
        : `${agent.name} added to ${SDLC_PHASE_LABELS[phase]}.`,
    );
  };

  if (!agents.length)
    return (
      <Page
        title="SDLC phases"
        blurb="Which agents are convened for each phase of the delivery chain."
      >
        <Empty title="No agents to assign yet.">
          Add agents on the Agents tab first, then tag them to the phases they
          should take part in.
        </Empty>
      </Page>
    );

  return (
    <Page
      title="SDLC phases"
      blurb="Tag agents to the phases they take part in. Dispatching a deliverable convenes them phase by phase, in this order, and an agent tagged for two phases is convened twice."
    >
      <Notice tone="error">{action.error ?? controller.error}</Notice>
      <Notice tone="success">{action.notice}</Notice>

      {agents.some((agent) => agent.mode === "active") &&
      !agents.some((agent) => agent.phases.length) ? (
        <Notice tone="info">
          No agent is tagged yet, so a dispatch currently convenes every active
          agent once, without phases. Tag one agent below and phase order
          becomes the contract — untagged agents stop being convened.
        </Notice>
      ) : null}

      <div className={s.three}>
        <Stat
          label="Phases covered"
          value={`${covered.length} / ${SDLC_PHASES.length}`}
          hint="by at least one active agent"
          accent="var(--ml-accent)"
          visual={
            <Ring
              value={covered.length}
              total={SDLC_PHASES.length}
              label="Phases covered by an active agent"
              caption={`${Math.round((covered.length / SDLC_PHASES.length) * 100)}%`}
            />
          }
        />
        <Stat
          label="Active agents"
          value={agents.filter((agent) => agent.mode === "active").length}
          hint="eligible to be convened"
          accent="var(--ml-signal-ok)"
          visual={
            <StackedBar
              label="Roster by participation"
              segments={[
                {
                  label: "Active",
                  value: agents.filter((agent) => agent.mode === "active").length,
                  signal: "ok",
                },
                {
                  label: "Learning",
                  value: agents.filter((agent) => agent.mode !== "active").length,
                  signal: "idle",
                },
              ]}
            />
          }
        />
        <Stat
          label="Untagged agents"
          value={agents.filter((agent) => !agent.phases.length).length}
          hint="will not be convened for anything"
          accent="var(--ml-signal-warn)"
        />
      </div>

      {gaps.length ? (
        <Notice tone="info">
          No active agent covers{" "}
          {gaps.map((phase) => SDLC_PHASE_LABELS[phase]).join(", ")}. Those
          phases are skipped when a deliverable is dispatched. That is a
          legitimate choice — say, if your team handles review itself — but it
          should be a choice, not an accident.
        </Notice>
      ) : (
        <Notice tone="success">
          Every phase has at least one active agent.
        </Notice>
      )}

      {SDLC_PHASES.map((phase, index) => {
        const tagged = byPhase.get(phase) ?? [];
        const activeHere = tagged.filter((agent) => agent.mode === "active");
        return (
          <Panel
            key={phase}
            accent={phaseColor(phase)}
            title={`${index + 1}. ${SDLC_PHASE_LABELS[phase]}`}
            hint={PHASE_PURPOSE[phase]}
            action={
              <Tag tone={activeHere.length ? "active" : "warn"}>
                {activeHere.length
                  ? `${activeHere.length} active`
                  : "No active agent"}
              </Tag>
            }
          >
            <div className={s.chipRow}>
              {agents.map((agent) => {
                const on = agent.phases.includes(phase);
                const inactive = agent.mode !== "active";
                return (
                  <button
                    key={agent.id}
                    type="button"
                    className={s.chip}
                    aria-pressed={on}
                    disabled={action.busy || controller.busy}
                    style={{
                      ...(on
                        ? ({ ["--chip-accent"]: phaseColor(phase) } as React.CSSProperties)
                        : {}),
                      ...(on && inactive ? { opacity: 0.62 } : {}),
                    }}
                    title={
                      inactive
                        ? `${agent.name} is in Learning and will not be convened even when tagged`
                        : on
                          ? `Remove ${agent.name} from this phase`
                          : `Add ${agent.name} to this phase`
                    }
                    onClick={() => void toggle(agent, phase)}
                  >
                    <span className={s.chipMark} aria-hidden="true">
                      {on ? "✓" : "+"}
                    </span>
                    {agent.name}
                    {on && inactive ? (
                      <span className={s.cardMeta}> · Learning</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </Panel>
        );
      })}

      <Panel
        title="Bulk actions"
        hint="Shortcuts for shaping a roster quickly. Each is one recorded change per agent."
      >
        <div className={s.chipRow}>
          <Button
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                for (const agent of agents.filter(
                  (entry) => entry.mode === "active" && !entry.phases.length,
                ))
                  await controller.execute("agent/assign", {
                    id: agent.id,
                    phases: [...SDLC_PHASES],
                  });
              }, "Every untagged active agent is now tagged for all nine phases.")
            }
          >
            Tag untagged active agents for all phases
          </Button>
          <Button
            variant="danger"
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                for (const agent of agents.filter(
                  (entry) => entry.phases.length,
                ))
                  await controller.execute("agent/assign", {
                    id: agent.id,
                    phases: [],
                  });
              }, "All phase tags cleared.")
            }
          >
            Clear all phase tags
          </Button>
        </div>
      </Panel>
    </Page>
  );
}
