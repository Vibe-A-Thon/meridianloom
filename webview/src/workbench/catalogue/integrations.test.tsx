import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  IntegrationConnection,
  IntegrationReadResult,
} from "../../../../shared/ts/integrations";
import { INTEGRATIONS } from "../../../../shared/ts/integrations";
import type {
  WorkbenchExecute,
  WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import { IntegrationsTab } from "./IntegrationsTab";

/**
 * The Integrations tab.
 *
 * The assertions here are mostly about restraint: what the page refuses to
 * claim. A saved connection is not a working one, a probe from an hour ago is
 * not a green light, and a credential is never displayed back — not even
 * masked, because the mask still leaks the length.
 */

const at = "2026-09-09T09:00:00Z";
const recent = () => new Date(Date.now() - 60_000).toISOString();
const old = () => new Date(Date.now() - 3 * 3600_000).toISOString();

const connection = (
  over: Partial<IntegrationConnection> = {},
): IntegrationConnection => ({
  id: "gitlab-prod",
  integrationId: "gitlab",
  name: "Production GitLab",
  config: { baseUrl: "https://gitlab.example.com", projectId: "42" },
  enabled: true,
  secretKeys: ["token"],
  createdAt: at,
  updatedAt: at,
  ...over,
});

function harness(integrations: IntegrationConnection[] = []) {
  const snapshot: WorkbenchSnapshot = {
    revision: 1,
    agents: [],
    skills: [],
    instructions: [],
    integrations,
    deliverables: [],
    runs: [],
    learning: [],
    capabilities: {
      workspaceOpen: true,
      trusted: true,
      governorEnabled: false,
      executionReady: true,
    },
  };
  const execute = vi.fn(async () => snapshot);
  const controller: WorkbenchController = {
    snapshot,
    busy: false,
    error: null,
    execute: execute as unknown as WorkbenchExecute,
    refresh: async () => {},
  };
  return { snapshot, execute, controller };
}

describe("the integration catalogue", () => {
  it("offers every system in the registry, grouped by what it is for", () => {
    const h = harness();
    render(<IntegrationsTab controller={h.controller} />);
    for (const definition of INTEGRATIONS)
      expect(
        screen.getAllByText(definition.name).length,
        `${definition.name} is missing from the catalogue`,
      ).toBeGreaterThan(0);
    expect(screen.getByText("Runtimes & containers")).toBeInTheDocument();
    expect(screen.getByText("Observability")).toBeInTheDocument();
  });

  it("says a CLI integration needs its binary before you connect it", () => {
    const h = harness();
    render(<IntegrationsTab controller={h.controller} />);
    expect(screen.getByText(/needs kubectl/)).toBeInTheDocument();
    expect(screen.getByText(/needs docker/)).toBeInTheDocument();
  });
});

describe("connection state", () => {
  it("calls a saved-but-untested connection 'Never tested', not connected", () => {
    const h = harness([connection()]);
    render(<IntegrationsTab controller={h.controller} />);
    expect(screen.getByText("Never tested")).toBeInTheDocument();
    expect(
      screen.getByText(/Saved but never tested/),
    ).toBeInTheDocument();
  });

  it("calls a green probe from three hours ago 'Stale' rather than reachable", () => {
    const h = harness([
      connection({
        lastProbe: { ok: true, at: old(), detail: "GitLab 17 answered.", latencyMs: 90 },
      }),
    ]);
    render(<IntegrationsTab controller={h.controller} />);
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("calls a recent green probe reachable, and shows what answered", () => {
    const h = harness([
      connection({
        lastProbe: { ok: true, at: recent(), detail: "GitLab 17.2.1 answered.", latencyMs: 91 },
      }),
    ]);
    render(<IntegrationsTab controller={h.controller} />);
    // Scoped to the card: the stat row above legitimately uses the same word.
    const card = screen.getByText("Production GitLab").closest("article")!;
    expect(within(card).getByText("Reachable")).toBeInTheDocument();
    expect(within(card).getByText(/GitLab 17\.2\.1 answered/)).toBeInTheDocument();
    expect(within(card).getByText(/91 ms/)).toBeInTheDocument();
  });

  it("shows the reason a failing connection failed, not just a red state", () => {
    const h = harness([
      connection({
        lastProbe: {
          ok: false,
          at: recent(),
          detail: "GET /api/v4/version returned 401.",
          latencyMs: 40,
          code: 401,
        },
      }),
    ]);
    render(<IntegrationsTab controller={h.controller} />);
    const card = screen.getByText("Production GitLab").closest("article")!;
    expect(within(card).getByText("Unreachable")).toBeInTheDocument();
    expect(within(card).getByText(/returned 401/)).toBeInTheDocument();
    expect(within(card).getByText(/HTTP 401/)).toBeInTheDocument();
  });

  it("probes on demand and reports the detail that came back", async () => {
    const h = harness([connection()]);
    h.execute.mockResolvedValue({
      ...h.snapshot,
      integrations: [
        connection({
          lastProbe: { ok: true, at: recent(), detail: "GitLab 17.2.1 answered.", latencyMs: 88 },
        }),
      ],
    });
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("integration/probe", { id: "gitlab-prod" }),
    );
    expect(await screen.findByText(/GitLab 17\.2\.1 answered\. \(88 ms\)/)).toBeInTheDocument();
  });
});

describe("configuring a connection", () => {
  it("never shows a stored credential back, not even masked", () => {
    const h = harness([connection()]);
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getByRole("button", { name: /^Edit/ }));
    const dialog = screen.getByRole("dialog");
    const token = within(dialog).getByLabelText(/Personal access token/);
    // Empty, with a placeholder that says one exists — a masked value would
    // still leak its length.
    expect(token).toHaveValue("");
    expect(token).toHaveAttribute("placeholder", expect.stringContaining("stored"));
  });

  it("states that credentials go to the keychain and that reads cannot write", () => {
    const h = harness();
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/keychain/);
    expect(dialog).toHaveTextContent(/cannot change anything/);
  });

  it("states what a successful test would actually prove", () => {
    const h = harness();
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    expect(
      screen.getByText(/A successful test means:/),
    ).toBeInTheDocument();
  });

  it("sends config and secrets separately on save", async () => {
    const h = harness();
    render(<IntegrationsTab controller={h.controller} />);
    // GitLab is the first card in the Source & review group.
    const card = screen.getAllByText("GitLab")[0].closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "Connect" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Instance URL/), {
      target: { value: "https://gitlab.example.com" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Project/), {
      target: { value: "42" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Personal access token/), {
      target: { value: "glpat-x" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("integration/save", {
        connection: expect.objectContaining({
          integrationId: "gitlab",
          config: expect.objectContaining({ projectId: "42" }),
          secrets: { token: "glpat-x" },
        }),
      }),
    );
  });
});

describe("reading through a connection", () => {
  it("renders the returned rows with a state column", async () => {
    const h = harness([connection()]);
    const result: IntegrationReadResult = {
      connectionId: "gitlab-prod",
      operationId: "pipelines",
      at,
      columns: ["Pipeline", "Ref", "Status", "Updated"],
      rows: [
        { id: "1", cells: ["#1", "main", "success", "now"], state: "ok" },
        { id: "2", cells: ["#2", "fix", "failed", "now"], state: "fail" },
      ],
      detail: "2 pipelines from https://gitlab.example.com.",
      truncated: false,
      latencyMs: 120,
    };
    h.execute.mockResolvedValue(result as never);
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getByRole("button", { name: /Pipelines/ }));
    await waitFor(() =>
      expect(h.execute).toHaveBeenCalledWith("integration/read", {
        id: "gitlab-prod",
        operationId: "pipelines",
      }),
    );
    expect(await screen.findByText("#1")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Ref" })).toBeInTheDocument();
    expect(screen.getByText("2 rows")).toBeInTheDocument();
  });

  it("says a read was capped rather than presenting a partial list as whole", async () => {
    const h = harness([connection()]);
    h.execute.mockResolvedValue({
      connectionId: "gitlab-prod",
      operationId: "pipelines",
      at,
      columns: ["Pipeline"],
      rows: [{ id: "1", cells: ["#1"], state: "ok" }],
      detail: "250 pipelines.",
      truncated: true,
      latencyMs: 300,
    } as never);
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getByRole("button", { name: /Pipelines/ }));
    expect(
      await screen.findByText(/more rows than Meridian reads in one call/),
    ).toBeInTheDocument();
  });

  it("does not offer reads through a disabled connection", () => {
    const h = harness([connection({ enabled: false })]);
    render(<IntegrationsTab controller={h.controller} />);
    expect(screen.getByRole("button", { name: /Pipelines/ })).toBeDisabled();
  });
});

describe("removing a connection", () => {
  it("says the credentials go too, and that nothing in the system is touched", () => {
    const h = harness([connection()]);
    render(<IntegrationsTab controller={h.controller} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(/deleted from your OS keychain/);
    expect(dialog).toHaveTextContent(/Nothing in the connected system is touched/);
    expect(h.execute).not.toHaveBeenCalled();
  });
});
