import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  WorkbenchExecute,
  WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import { WebviewRpcClient } from "../../rpc/client";
import { makeHost } from "../../test/host-harness";
import { AgentOperations } from "./AgentOperations";
import { WorkspaceOperations } from "./WorkspaceOperations";
import { csv, type OperationsProps } from "./shared";
import { AgentStudio } from "../AgentStudio";
import { DeliveryStudio } from "../DeliveryStudio";

function harness(view: string, overrides: Partial<WorkbenchSnapshot> = {}) {
  const now = "2026-09-09T00:00:00Z";
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    skills: [],
    instructions: [],
    integrations: [],
    agents: ["atlas", "sage"].map((id) => ({
      id,
      name: id === "atlas" ? "Atlas" : "Sage",
      role: "Developer",
      vendor: "Custom",
      description: "Independent ACP profile",
      version: "1",
      command: "acp",
      args: [],
      permissions: ["read"],
      instructions: "",
      trainable: ["memory"],
      phases: [],
      skillIds: [],
      instructionIds: [],
      integrationIds: [],
      mode: id === "atlas" ? "active" : "learning",
      runtime: "idle",
      learningState: "waiting",
      createdAt: now,
      updatedAt: now,
    })),
    deliverables: [
      {
        id: "brief",
        title: "Keyboard access",
        brief: "Check focus and labels.",
        state: "draft",
        agentIds: [],
        createdAt: now,
        updatedAt: now,
      },
    ],
    learning: [],
    runs: [],
    documents: [],
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: true,
      executionReady: true,
    },
    ...overrides,
  };
  const host = makeHost({
    "ledger.query": { entries: [] },
    "worktree/conflicts": { blocked: false, conflicts: [] },
  });
  const execute = vi.fn(async () => snapshot);
  const props: OperationsProps = {
    view,
    controller: {
      snapshot,
      execute: execute as WorkbenchExecute,
      busy: false,
      error: null,
      refresh: async () => {},
    },
    client: new WebviewRpcClient(host.transport),
    ready: true,
    enabledTiers: ["flight-recorder", "governor"],
    workspaceDir: "/workspace",
    onNavigate: vi.fn(),
  };
  return { props, execute, host, snapshot };
}

describe("agent operations", () => {
  it("changes participation only after displaying the selected profiles for confirmation", async () => {
    const h = harness("watch");
    render(<AgentOperations {...h.props} />);
    fireEvent.click(screen.getByLabelText("Select Atlas"));
    fireEvent.click(
      screen.getByRole("button", { name: "Deactivate selected" }),
    );
    expect(h.execute).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Atlas (atlas)")).toBeInTheDocument();
    expect(within(dialog).queryByText("Sage (sage)")).not.toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "Confirm participation change",
      }),
    );
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/mode", {
        id: "atlas",
        mode: "learning",
      }),
    );
  });
  it("keeps inactive profiles in the Learning room and provides a list alternative", () => {
    const h = harness("floor");
    render(<AgentOperations {...h.props} />);
    expect(
      screen.getByRole("heading", { name: /Learning dojo/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Waiting for reviewed feedback"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /list/i })).toBeInTheDocument();
  });
  it("opens the requested profile and delivery from contextual navigation", () => {
    const h = harness("watch");
    const view = render(
      <AgentStudio controller={h.props.controller} initialSelection="sage" />,
    );
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Sage");
    view.unmount();
    render(
      <DeliveryStudio
        controller={h.props.controller}
        initialSelection="brief"
      />,
    );
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Keyboard access");
  });
});

describe("launch and activity operations", () => {
  it("requires preflight then checks again and sends the exact reviewed team and brief", async () => {
    const h = harness("launch");
    render(<WorkspaceOperations {...h.props} />);
    fireEvent.change(screen.getByLabelText("Draft deliverable"), {
      target: { value: "brief" },
    });
    expect(
      screen.getByRole("button", { name: "Review launch" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Check workspace" }));
    await h.host.settle();
    fireEvent.click(screen.getByRole("button", { name: "Review launch" }));
    expect(h.execute).not.toHaveBeenCalled();
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Confirm dispatch",
      }),
    );
    await h.host.settle();
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("deliverable/dispatch", {
        id: "brief",
        expectedBriefUpdatedAt: h.snapshot.deliverables[0].updatedAt,
        expectedTeam: [
          { id: "atlas", updatedAt: h.snapshot.agents[0].updatedAt },
        ],
      }),
    );
    expect(
      h.host.requests.filter(
        (request) => request.method === "worktree/conflicts",
      ),
    ).toHaveLength(2);
  });
  it("invalidates the launch review after participation changes", async () => {
    const h = harness("launch");
    const ui = render(<WorkspaceOperations {...h.props} />);
    fireEvent.change(screen.getByLabelText("Draft deliverable"), {
      target: { value: "brief" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check workspace" }));
    await h.host.settle();
    fireEvent.click(screen.getByRole("button", { name: "Review launch" }));
    ui.rerender(
      <WorkspaceOperations
        {...h.props}
        controller={{
          ...h.props.controller,
          snapshot: {
            ...h.snapshot,
            agents: h.snapshot.agents.map((agent) => ({
              ...agent,
              mode: "active",
            })),
          },
        }}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Confirm dispatch" }),
    ).toBeDisabled();
    expect(h.execute).not.toHaveBeenCalled();
  });
  it("records guidance only after reviewing its content", async () => {
    const h = harness("steer", {
      runs: [
        {
          id: "run",
          agentId: "atlas",
          agentName: "Atlas",
          sessionId: "wire",
          prompt: "Inspect UI",
          state: "running",
          startedAt: "2026-09-09",
          output: "",
        },
      ],
    });
    render(<WorkspaceOperations {...h.props} />);
    fireEvent.change(screen.getByLabelText("Running session"), {
      target: { value: "run" },
    });
    fireEvent.change(screen.getByLabelText("Guidance or clarification"), {
      target: { value: "Check focus restoration." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review guidance" }));
    expect(h.execute).not.toHaveBeenCalled();
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Confirm guidance",
      }),
    );
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("run/steer", {
        id: "run",
        message: "Check focus restoration.",
      }),
    );
  });
  it("exports spreadsheet-safe CSV values", () => {
    expect(csv([["=2+3", "plain, value", 'a"b']])).toBe(
      '"\'=2+3","plain, value","a""b"',
    );
  });
});
