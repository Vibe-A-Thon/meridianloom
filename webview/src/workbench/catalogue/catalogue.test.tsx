import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  WorkbenchAgent,
  WorkbenchExecute,
  WorkbenchInstruction,
  WorkbenchSkill,
  WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import type { WebviewRpcClient } from "../../rpc/client";
import { AgentsTab } from "./AgentsTab";
import { SkillsTab } from "./SkillsTab";
import { InstructionsTab } from "./InstructionsTab";
import { PhasesTab } from "./PhasesTab";
import { RunsTab } from "./RunsTab";
import { Dashboard } from "./Dashboard";

/**
 * The catalogue tabs, tested the way the user reaches them.
 *
 * Everything here is a claim about what a person can do from the GUI alone:
 * add an agent, activate or deactivate it, see honestly which of the two it
 * is, bind skills and instructions to it, tag it to SDLC phases, and bring an
 * agent in from a Markdown file or a ZIP. If any of these stops working the
 * plugin stops being operable without commands, which is the whole point.
 */

const at = "2026-09-08T00:00:00Z";

const makeAgent = (over: Partial<WorkbenchAgent> = {}): WorkbenchAgent => ({
  id: "atlas",
  name: "Atlas",
  role: "Architect",
  description: "Designs the shape.",
  vendor: "acme",
  version: "1.0.0",
  command: "claude",
  args: [],
  instructions: "",
  permissions: ["read"],
  trainable: ["memory"],
  phases: [],
  skillIds: [],
  instructionIds: [],
  integrationIds: [],
  mode: "learning",
  runtime: "idle",
  learningState: "waiting",
  createdAt: at,
  updatedAt: at,
  ...over,
});

const makeSkill = (over: Partial<WorkbenchSkill> = {}): WorkbenchSkill => ({
  id: "java",
  name: "Java Spring",
  summary: "Gradle, not Maven.",
  version: "1.0.0",
  tags: ["java"],
  body: "# Java",
  enabled: true,
  source: "authored",
  createdAt: at,
  updatedAt: at,
  ...over,
});

const makeInstruction = (
  over: Partial<WorkbenchInstruction> = {},
): WorkbenchInstruction => ({
  id: "house",
  name: "House rules",
  summary: "How we work.",
  scope: "workspace",
  body: "# House rules",
  enabled: true,
  source: "authored",
  createdAt: at,
  updatedAt: at,
  ...over,
});

function harness(over: Partial<WorkbenchSnapshot> = {}) {
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    agents: [],
    skills: [],
    instructions: [],
    integrations: [],
    deliverables: [],
    runs: [],
    learning: [],
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: false,
      executionReady: true,
    },
    ...over,
  };
  const execute = vi.fn(async () => snapshot);
  const controller: WorkbenchController = {
    snapshot,
    busy: false,
    error: null,
    execute: execute as unknown as WorkbenchExecute,
    refresh: async () => {},
  };
  const pickFile = vi.fn(async () => undefined as unknown);
  const client = { pickFile } as unknown as WebviewRpcClient;
  return { snapshot, execute, controller, client, pickFile };
}

// --- agents -------------------------------------------------------------

describe("the Agents tab", () => {
  it("states an agent's participation as Active or Learning, in words", () => {
    const h = harness({
      agents: [
        makeAgent({ id: "atlas", name: "Atlas", mode: "active" }),
        makeAgent({ id: "vale", name: "Vale", mode: "learning" }),
      ],
    });
    render(<AgentsTab controller={h.controller} client={h.client} />);
    // The status is a word, not only a colour: an inactive agent reads
    // "Learning", which is what it is actually doing. Scoped to the cards,
    // because the stat row above uses the same two words as labels.
    const atlas = screen.getByText("Atlas").closest("article")!;
    const vale = screen.getByText("Vale").closest("article")!;
    expect(within(atlas).getByText("Active")).toBeInTheDocument();
    expect(within(vale).getByText("Learning")).toBeInTheDocument();
  });

  it("activates a Learning agent so it can take part in deliverables", async () => {
    const h = harness({ agents: [makeAgent({ mode: "learning" })] });
    render(<AgentsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getByRole("button", { name: /Activate/ }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/mode", {
        id: "atlas",
        mode: "active",
      }),
    );
  });

  it("deactivates an active agent, sending it to learning", async () => {
    const h = harness({ agents: [makeAgent({ mode: "active" })] });
    render(<AgentsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getByRole("button", { name: /Deactivate/ }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/mode", {
        id: "atlas",
        mode: "learning",
      }),
    );
  });

  it("imports an agent from a file the host picked, never from the webview's own reach", async () => {
    const h = harness();
    h.pickFile.mockResolvedValue({
      fileName: "atlas.md",
      content: "---\nkind: agent\nname: Atlas\ncommand: claude\n---\n# Atlas\n",
    });
    h.execute.mockResolvedValue({
      snapshot: h.snapshot,
      report: {
        agents: ["atlas"],
        skills: [],
        instructions: [],
        skipped: [],
        format: "markdown",
      },
    } as never);
    render(<AgentsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Import/ })[0]);
    await waitFor(() => expect(h.pickFile).toHaveBeenCalled());
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/importPackage", {
        fileName: "atlas.md",
        content: expect.stringContaining("kind: agent"),
      }),
    );
  });

  it("treats a cancelled file dialog as a result, not an error", async () => {
    const h = harness();
    h.pickFile.mockResolvedValue(undefined);
    render(<AgentsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Import/ })[0]);
    await waitFor(() => expect(screen.getByText(/Nothing selected/)).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers only enabled skills for binding", () => {
    const h = harness({
      agents: [makeAgent()],
      skills: [
        makeSkill({ id: "java", name: "Java Spring", enabled: true }),
        makeSkill({ id: "go", name: "Go Service", enabled: false }),
      ],
    });
    render(<AgentsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getByRole("button", { name: /^Edit/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Java Spring")).toBeInTheDocument();
    // A disabled skill is out of service; offering it would let a user bind
    // something that will not be applied.
    expect(within(dialog).queryByText("Go Service")).toBeNull();
  });
});

// --- skills -------------------------------------------------------------

describe("the Skills tab", () => {
  it("names the agents a skill is bound to, so disabling is an informed act", () => {
    const h = harness({
      agents: [makeAgent({ skillIds: ["java"] })],
      skills: [makeSkill()],
    });
    render(<SkillsTab controller={h.controller} client={h.client} />);
    expect(screen.getByText(/Bound to Atlas/)).toBeInTheDocument();
  });

  it("disables a skill without deleting it", async () => {
    const h = harness({ skills: [makeSkill()] });
    render(<SkillsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getByRole("button", { name: "Disable" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("skill/toggle", {
        id: "java",
        enabled: false,
      }),
    );
  });

  it("asks before removing, and says which agents lose the skill", () => {
    const h = harness({
      agents: [makeAgent({ skillIds: ["java"] })],
      skills: [makeSkill()],
    });
    render(<SkillsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Atlas");
    expect(dialog).toHaveTextContent(/lose this specialisation/);
    // Nothing has been removed merely by asking.
    expect(h.execute).not.toHaveBeenCalled();
  });
});

// --- instructions -------------------------------------------------------

describe("the Instructions tab", () => {
  it("states the precedence order on the page rather than leaving it to be inferred", () => {
    const h = harness({ instructions: [makeInstruction()] });
    render(<InstructionsTab controller={h.controller} client={h.client} />);
    expect(
      screen.getByText(/adapter → workspace → user → organisation/),
    ).toBeInTheDocument();
  });

  it("saves a new instruction file with the scope the user chose", async () => {
    const h = harness();
    render(<InstructionsTab controller={h.controller} client={h.client} />);
    fireEvent.click(screen.getAllByRole("button", { name: /New instruction/ })[0]);
    fireEvent.change(screen.getByLabelText(/Identifier/), {
      target: { value: "house" },
    });
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "House rules" },
    });
    fireEvent.change(screen.getByLabelText(/Scope/), {
      target: { value: "organisation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create instructions" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("instruction/save", {
        instruction: expect.objectContaining({
          id: "house",
          name: "House rules",
          scope: "organisation",
        }),
      }),
    );
  });
});

// --- phases -------------------------------------------------------------

describe("the SDLC phases board", () => {
  it("tags an agent to a phase in one click", async () => {
    const h = harness({ agents: [makeAgent({ mode: "active" })] });
    render(<PhasesTab controller={h.controller} />);
    const board = screen.getByText("2. Architecture & Design").closest("section")!;
    fireEvent.click(within(board).getByRole("button", { name: /Atlas/ }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/assign", {
        id: "atlas",
        phases: ["design"],
      }),
    );
  });

  it("removes the tag when the same chip is pressed again", async () => {
    const h = harness({
      agents: [makeAgent({ mode: "active", phases: ["design"] })],
    });
    render(<PhasesTab controller={h.controller} />);
    const board = screen.getByText("2. Architecture & Design").closest("section")!;
    fireEvent.click(within(board).getByRole("button", { name: /Atlas/ }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("agent/assign", {
        id: "atlas",
        phases: [],
      }),
    );
  });

  it("names the phases no active agent covers, because a gap is a skipped phase", () => {
    const h = harness({
      agents: [makeAgent({ mode: "active", phases: ["design"] })],
    });
    render(<PhasesTab controller={h.controller} />);
    expect(screen.getByText(/No active agent covers/)).toHaveTextContent(
      "Verification",
    );
  });

  it("shows a Learning agent under a phase it is tagged with, and says it will not be convened", () => {
    const h = harness({
      agents: [makeAgent({ mode: "learning", phases: ["design"] })],
    });
    render(<PhasesTab controller={h.controller} />);
    const board = screen.getByText("2. Architecture & Design").closest("section")!;
    // Tagged, and honestly labelled as not participating.
    expect(within(board).getByRole("button", { name: /Atlas/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(board).getByText("No active agent")).toBeInTheDocument();
  });
});

// --- runs ---------------------------------------------------------------

const run = (over: Record<string, unknown> = {}) => ({
  id: "run-1",
  agentId: "atlas",
  agentName: "Atlas",
  prompt: "Design the module boundary.",
  state: "running" as const,
  startedAt: at,
  ...over,
});

describe("the Runs tab", () => {
  it("queues a steering message and says it is queued, not delivered", async () => {
    const h = harness({ runs: [run() as never] });
    render(<RunsTab controller={h.controller} onNavigate={() => {}} />);
    fireEvent.change(screen.getByLabelText("Steering message"), {
      target: { value: "Prefer composition." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Steer" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("run/steer", {
        id: "run-1",
        message: "Prefer composition.",
      }),
    );
    expect(
      await screen.findByText(
        "Steering message queued. It is delivered when the adapter accepts it.",
      ),
    ).toBeInTheDocument();
  });

  it("stops a live run, and scopes the claim to this workbench", async () => {
    const h = harness({ runs: [run() as never] });
    render(<RunsTab controller={h.controller} onNavigate={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("run/cancel", { id: "run-1" }),
    );
    expect(
      await screen.findByText(/Only this workbench's run is affected/),
    ).toBeInTheDocument();
  });

  it("shows a failed run's error rather than a bare state word", () => {
    const h = harness({
      runs: [run({ state: "failed", error: "adapter exited with code 2" }) as never],
    });
    render(<RunsTab controller={h.controller} onNavigate={() => {}} />);
    expect(screen.getByText("adapter exited with code 2")).toBeInTheDocument();
  });
});

// --- dashboard ----------------------------------------------------------

const sessions = {
  status: "ready" as const,
  data: { sessions: [], warnings: [] },
  error: undefined,
  refresh: () => {},
};

describe("the Dashboard", () => {
  it("says what is blocking work when every agent is in Learning", () => {
    const h = harness({ agents: [makeAgent({ mode: "learning" })] });
    render(
      <Dashboard
        snapshot={h.snapshot}
        error={null}
        enabledTiers={["flight-recorder"]}
        sessions={sessions as never}
        onNavigate={() => {}}
      />,
    );
    expect(
      screen.getByText(/are in Learning, so no deliverable can be worked/),
    ).toBeInTheDocument();
  });

  it("says nothing is blocked when the roster covers phases", () => {
    const h = harness({
      agents: [makeAgent({ mode: "active", phases: ["design"] })],
    });
    render(
      <Dashboard
        snapshot={h.snapshot}
        error={null}
        enabledTiers={["flight-recorder"]}
        sessions={sessions as never}
        onNavigate={() => {}}
      />,
    );
    expect(screen.getByText(/Nothing is blocked/)).toBeInTheDocument();
  });

  it("navigates to the tab an attention item is about", () => {
    const onNavigate = vi.fn();
    const h = harness({ agents: [] });
    render(
      <Dashboard
        snapshot={h.snapshot}
        error={null}
        enabledTiers={["flight-recorder"]}
        sessions={sessions as never}
        onNavigate={onNavigate}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Add an agent" }));
    expect(onNavigate).toHaveBeenCalledWith("agents");
  });

  it("states what the Governor tier would add rather than hiding the concept", () => {
    const h = harness();
    render(
      <Dashboard
        snapshot={h.snapshot}
        error={null}
        enabledTiers={["flight-recorder"]}
        sessions={sessions as never}
        onNavigate={() => {}}
      />,
    );
    expect(screen.getByText(/Governor tier is off/)).toBeInTheDocument();
  });
});
