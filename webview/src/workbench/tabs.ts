import type { IconName } from "./Icon";

/**
 * The tab set of the single-page workbench.
 *
 * One page, one row of tabs, Dashboard first. Every capability the plugin
 * offers is reachable from here without a command, a palette entry or a
 * second window — selecting Meridian Loom in the Activity Bar lands on
 * Dashboard and everything else is one click away.
 *
 * A tab owns a list of `views`. The first is what the tab opens on; the rest
 * appear as a secondary row beneath the tab bar. That two-level shape is what
 * lets fourteen tabs carry fifty-odd surfaces without either a scrolling wall
 * of tabs or a surface that can only be reached by guessing a URL — and it
 * keeps `onNavigate("trust")` working from deep inside a studio, because the
 * shell derives the tab from the view rather than the other way round.
 *
 * `tier` gates a tab the way X-28 requires: a tab whose tier is not enabled
 * is **absent** from the bar, never present-but-disabled. Disabled entries
 * advertise what the user cannot have and teach them to distrust the rest of
 * the bar. Discovery is handled instead by the single unlock affordance —
 * the Selvage strip, and the Dashboard's tier note — which states in one line
 * what the tier adds.
 */
export type TabTier = "flight-recorder" | "governor" | "orchestra";

export interface WorkbenchTab {
  id: string;
  label: string;
  icon: IconName;
  /** One line, shown under the tab title as the page's subject. */
  blurb: string;
  tier: TabTier;
  /** Grouped in the tab bar so a long row still reads as sections. */
  group: "Work" | "Team" | "Insight" | "System";
  /** Views this tab owns. `views[0]` is what the tab opens on. */
  views: readonly string[];
}

export const WORKBENCH_TABS: readonly WorkbenchTab[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: "overview",
    blurb: "Everything at a glance: your team, your work, and what needs you",
    tier: "flight-recorder",
    group: "Work",
    views: ["dashboard"],
  },
  {
    id: "deliverables",
    label: "Deliverables",
    icon: "delivery",
    blurb: "Write a brief, dispatch the active team, review what came back",
    tier: "flight-recorder",
    group: "Work",
    views: ["deliverables", "packets"],
  },
  {
    id: "runs",
    label: "Runs",
    icon: "runtime",
    blurb: "Live and past agent runs, with output, steering and stop controls",
    tier: "flight-recorder",
    group: "Work",
    views: ["runs", "launch", "steer", "weave"],
  },
  {
    id: "agents",
    label: "Agents",
    icon: "agents",
    blurb:
      "Add, import, tag, activate and run portable agents — yours or anyone's",
    tier: "flight-recorder",
    group: "Team",
    views: ["agents", "floor", "watch", "inspector", "onboarding", "adapters"],
  },
  {
    id: "skills",
    label: "Skills",
    icon: "skills",
    blurb: "Skill packs that turn a role agent into a stack specialist",
    tier: "flight-recorder",
    group: "Team",
    views: ["skills"],
  },
  {
    id: "instructions",
    label: "Instructions",
    icon: "instructions",
    blurb: "How this organisation works, in files your agents read",
    tier: "flight-recorder",
    group: "Team",
    views: ["instructions"],
  },
  {
    id: "phases",
    label: "SDLC phases",
    icon: "phases",
    blurb: "Which agents are convened for each phase, and where the gaps are",
    tier: "flight-recorder",
    group: "Team",
    views: ["phases"],
  },
  {
    id: "learning",
    label: "Learning",
    icon: "learning",
    blurb: "Inactive agents and the memory they propose from your feedback",
    tier: "flight-recorder",
    group: "Team",
    views: ["learning", "memory"],
  },
  {
    id: "integrations",
    label: "Integrations",
    icon: "connectors",
    blurb:
      "GitLab, Jira, Kubernetes, Datadog and the rest of the estate — read-only",
    tier: "flight-recorder",
    group: "Insight",
    views: ["integrations"],
  },
  {
    id: "portfolio",
    label: "Portfolio",
    icon: "layers",
    blurb: "Stories, specifications, connectors, routing and reports",
    tier: "flight-recorder",
    group: "Insight",
    views: [
      "portfolio",
      "stories",
      "specifications",
      "connectors",
      "routing",
      "exchange",
      "reports",
    ],
  },
  {
    id: "modeling",
    label: "Modeling",
    icon: "layers",
    blurb: "Code maps, architecture, UML, flows, loops, diffs and replay",
    tier: "flight-recorder",
    group: "Insight",
    views: [
      "codemap",
      "architecture",
      "uml",
      "flows",
      "loops",
      "diff",
      "replay",
      "comprehension",
    ],
  },
  {
    id: "evidence",
    label: "Evidence",
    icon: "evidence",
    blurb: "Provenance, external sessions, the ledger and signed export",
    tier: "flight-recorder",
    group: "Insight",
    views: [
      "evidence",
      "flight-recorder",
      "external-agents",
      "ledger",
      "decisions",
      "kpi",
    ],
  },
  {
    id: "governance",
    label: "Governance",
    icon: "governance",
    blurb: "Gates, roles, approvals, trust measures and recorded spend",
    tier: "governor",
    group: "Insight",
    views: [
      "gates",
      "approvals",
      "verification",
      "security",
      "pipeline",
      "repositories",
      "trust",
      "calibration",
      "spend",
      "trust-score",
      "rejection-reasons",
      "agent-comparison",
      "jcurve",
      "tokenmaxxing",
      "dora",
    ],
  },
  {
    id: "runtime",
    label: "Runtime",
    icon: "runtime",
    blurb: "Connection health, execution readiness and host diagnostics",
    tier: "flight-recorder",
    group: "System",
    views: ["runtime", "notifications", "editor", "unlock"],
  },
  {
    id: "settings",
    label: "Settings",
    icon: "settings",
    blurb: "Appearance, density, tiers, guided setup and workspace config",
    tier: "flight-recorder",
    group: "System",
    views: ["settings", "configuration", "shortcuts", "focus", "guide", "setup"],
  },
];

export const DEFAULT_TAB = "dashboard";
export const DEFAULT_VIEW = "dashboard";

export const TAB_GROUPS = ["Work", "Team", "Insight", "System"] as const;

/**
 * Legacy route ids that predate the tab shell, mapped onto the view that
 * replaced them. Kept so a persisted UI state — or an `onNavigate` call still
 * living inside a studio — lands somewhere real instead of falling back to
 * the Dashboard and silently losing the user's place.
 */
const VIEW_ALIASES: Readonly<Record<string, string>> = {
  overview: "dashboard",
  home: "dashboard",
};

export function normaliseView(view: string): string {
  const base = view.split("/")[0];
  return VIEW_ALIASES[base] ?? base;
}

/** The tab that owns a view, or the Dashboard when nothing claims it. */
export function tabForView(view: string): WorkbenchTab {
  const base = normaliseView(view);
  return (
    WORKBENCH_TABS.find((tab) => tab.views.includes(base)) ?? WORKBENCH_TABS[0]
  );
}

export function tabById(id: string): WorkbenchTab {
  return WORKBENCH_TABS.find((tab) => tab.id === id) ?? WORKBENCH_TABS[0];
}

/** Whether a view id is one this shell knows how to render. */
export function isKnownView(view: string): boolean {
  const base = normaliseView(view);
  return WORKBENCH_TABS.some((tab) => tab.views.includes(base));
}

/** Whether the active tier set permits a tab's own surface to operate. */
export function isTabUnlocked(
  tab: WorkbenchTab,
  enabledTiers: readonly string[],
): boolean {
  return tab.tier === "flight-recorder" || enabledTiers.includes(tab.tier);
}

/** What a locked tab is waiting for, in the user's terms rather than ours. */
export const TIER_EXPLANATION: Readonly<Record<TabTier, string>> = {
  "flight-recorder": "Always available.",
  governor:
    "The Governor tier adds gates, roles and approvals, trust measures, recorded spend, and the ability to run hosted agents. Turn it on in the extension settings.",
  orchestra:
    "The Orchestra tier adds multi-agent orchestration, autonomous loops and cross-repository delivery. Turn it on in the extension settings.",
};
