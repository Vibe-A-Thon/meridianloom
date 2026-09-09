import type { IconName } from "./Icon";
import { SURFACE_COVERAGE } from "./surfaces";

export interface WorkbenchRoute {
  id: string;
  label: string;
  icon: IconName;
  group: "Workspace" | "Intelligence" | "System";
  description: string;
  pinned?: boolean;
}
export const WORKBENCH_ROUTES: readonly WorkbenchRoute[] = [
  {
    id: "overview",
    label: "Overview",
    icon: "overview",
    group: "Workspace",
    description: "Your delivery pulse, active team, and next steps",
  },
  {
    id: "deliverables",
    label: "Deliverables",
    icon: "delivery",
    group: "Workspace",
    description: "Write a brief, dispatch the active team, review the result",
  },
  {
    id: "agents",
    label: "Agent studio",
    icon: "agents",
    group: "Workspace",
    description: "Add, update, activate, export, and run portable agents",
  },
  {
    id: "learning",
    label: "Learning dojo",
    icon: "learning",
    group: "Intelligence",
    description: "Review memory notes for agents in Learning mode",
  },
  {
    id: "evidence",
    label: "Evidence",
    icon: "evidence",
    group: "Intelligence",
    description: "Flight recorder, external sessions, attribution, and ledger",
  },
  {
    id: "runtime",
    label: "Runtime",
    icon: "runtime",
    group: "System",
    description: "Connection health, diagnostics, and execution readiness",
  },
  {
    id: "guide",
    label: "Workspace guide",
    icon: "guide",
    group: "System",
    description:
      "Explore the full product specification and implementation coverage",
  },
  {
    id: "settings",
    label: "Settings",
    icon: "settings",
    group: "System",
    description: "Appearance, density, shortcuts, and workspace configuration",
  },
  ...SURFACE_COVERAGE.filter(
    ([, , id]) => !["overview", "learning", "runtime"].includes(id),
  ).map(
    ([, label, id, description]): WorkbenchRoute => ({
      id,
      label,
      description,
      group: "Intelligence",
      icon: "layers",
      pinned: false,
    }),
  ),
];
export const routeLabel = (id: string) =>
  WORKBENCH_ROUTES.find((route) => route.id === id.split("/")[0])?.label ??
  {
    setup: "Guided setup",
    "flight-recorder": "Flight recorder",
    "external-agents": "External agents",
    ledger: "Audit ledger",
  }[id] ??
  "Overview";
