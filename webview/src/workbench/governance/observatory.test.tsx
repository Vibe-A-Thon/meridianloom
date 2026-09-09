import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  WorkbenchExecute,
  WorkbenchSnapshot,
} from "../../../../shared/ts/workbench";
import type { WorkbenchController } from "../useWorkbench";
import { WebviewRpcClient } from "../../rpc/client";
import { makeHost } from "../../test/host-harness";
import {
  CompareAgents,
  DoraExport,
  Jcurve,
  ReasonDistribution,
  SpendObservatory,
  Tokenmaxxing,
  TrustScore,
} from "./Observatory";

/**
 * The Trust & Spend Observatory.
 *
 * These instruments exist to be believed, so the tests are almost entirely
 * about what the surface refuses to say: it never renders a null as zero, it
 * never shows a figure without its coverage, and it never projects from a
 * truncated sample. A dashboard that quietly rounds "we don't know" down to
 * "nothing" is worse than no dashboard, because someone will make a staffing
 * decision on it.
 */

const envelope = (over: Record<string, unknown> = {}) => ({
  value: null,
  rowsConsidered: 400,
  rowsAvailable: 400,
  truncated: false,
  sequenceRange: [1, 400],
  coverage: 1,
  label: "complete",
  ...over,
});

function harness(responses: Record<string, unknown>) {
  const host = makeHost(responses);
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
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
      governorEnabled: true,
      executionReady: true,
    },
  };
  const controller: WorkbenchController = {
    snapshot,
    busy: false,
    error: null,
    execute: vi.fn(async () => snapshot) as unknown as WorkbenchExecute,
    refresh: async () => {},
  };
  return {
    host,
    client,
    props: {
      client,
      ready: true,
      workspaceDir: "/repo",
      enabledTiers: ["flight-recorder", "governor"] as const,
      controller,
      onNavigate: vi.fn(),
    },
  };
}

// --- the central claim ---------------------------------------------------

describe("an unevidenced figure", () => {
  it("reads as insufficient evidence, never as zero", async () => {
    const h = harness({
      "trust/score": {
        scope: {},
        agentId: "claude-code",
        taskClass: "all",
        // The sidecar's honest answer when nothing can be evidenced.
        score: null,
        status: "insufficient_evidence",
        coverage: [],
        components: {
          firstPassYield: { status: "insufficient_evidence", value: null, sampleSize: 0 },
        },
        split: {},
        coverageEnvelope: envelope({ label: "complete" }),
        cacheHit: false,
      },
      "trust/scoreDecomposition": {
        scope: {},
        agentId: "claude-code",
        taskClass: "all",
        score: null,
        status: "insufficient_evidence",
        coverage: [],
        components: {
          firstPassYield: { status: "insufficient_evidence", value: null, sampleSize: 0 },
        },
        split: {},
        coverageEnvelope: envelope(),
        cacheHit: false,
      },
    });
    render(<TrustScore {...h.props} />);
    fireEvent.change(screen.getByLabelText("Agent ID"), {
      target: { value: "claude-code" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Compute score" }));
    await act(async () => {});
    await h.host.settle();

    const figure = await screen.findByTestId("trust-score");
    expect(figure).toHaveTextContent("Insufficient evidence");
    // The thing that must never happen.
    expect(figure).not.toHaveTextContent("0.00");
    expect(
      screen.getByText(/absent measurement, not a score of zero/),
    ).toBeInTheDocument();
    h.client.dispose();
  });

  it("reads as not measurable when the attribution floor was breached", async () => {
    const result = {
      scope: {},
      agentId: "a",
      taskClass: "all",
      score: null,
      status: "insufficient_coverage",
      coverage: [],
      components: {},
      split: {},
      coverageEnvelope: envelope({
        attribution: { belowFloor: true, attributedShare: 0.4 },
      }),
      cacheHit: false,
    };
    const h = harness({ "trust/score": result, "trust/scoreDecomposition": result });
    render(<TrustScore {...h.props} />);
    fireEvent.change(screen.getByLabelText("Agent ID"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Compute score" }));
    await act(async () => {});
    await h.host.settle();

    expect(await screen.findByTestId("trust-score")).toHaveTextContent("Not measurable");
    // Score and decomposition each carry their own coverage, so the
    // disclosure legitimately appears once per figure.
    expect(
      screen.getAllByText(/Attribution coverage fell below the configured floor/).length,
    ).toBeGreaterThan(0);
    h.client.dispose();
  });
});

// --- coverage disclosure -------------------------------------------------

describe("coverage disclosure", () => {
  it("states how many rows the figure was computed over", async () => {
    const result = {
      scope: {},
      agentId: "a",
      taskClass: "all",
      score: 0.82,
      status: "ok",
      coverage: ["firstPassYield"],
      components: { firstPassYield: { status: "ok", value: 0.82, sampleSize: 40 } },
      split: {},
      coverageEnvelope: envelope({ rowsConsidered: 400, rowsAvailable: 4402 }),
      cacheHit: false,
    };
    const h = harness({ "trust/score": result, "trust/scoreDecomposition": result });
    render(<TrustScore {...h.props} />);
    fireEvent.change(screen.getByLabelText("Agent ID"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Compute score" }));
    await act(async () => {});
    await h.host.settle();

    await waitFor(() =>
      expect(
        screen.getAllByText(/Computed over 400 of 4,402 ledger rows/).length,
      ).toBeGreaterThan(0),
    );
    h.client.dispose();
  });

  it("says an empty sample is empty, not a result", async () => {
    const result = {
      scope: {},
      agentId: "a",
      taskClass: "all",
      score: null,
      status: "insufficient_evidence",
      coverage: [],
      components: {},
      split: {},
      coverageEnvelope: envelope({ label: "empty", rowsConsidered: 0 }),
      cacheHit: false,
    };
    const h = harness({ "trust/score": result, "trust/scoreDecomposition": result });
    render(<TrustScore {...h.props} />);
    fireEvent.change(screen.getByLabelText("Agent ID"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Compute score" }));
    await act(async () => {});
    await h.host.settle();

    await waitFor(() =>
      expect(
        screen.getAllByText(/empty sample, not a result of zero/).length,
      ).toBeGreaterThan(0),
    );
    h.client.dispose();
  });
});

// --- derived figures over a partial sample -------------------------------

describe("spend", () => {
  it("refuses to forecast from a truncated sample, and says why", async () => {
    const h = harness({
      "spend/series": {
        scope: {},
        dimension: "agent",
        totals: { cost: 12.5, tokens: 900_000, calls: 300 },
        byValue: { "claude-code": { cost: 12.5 } },
        spendSeries: {},
        coverage: envelope({ truncated: true, rowsConsidered: 1000, rowsAvailable: 8000 }),
        cacheHit: false,
      },
      "spend/forecast": {
        scope: {},
        team: null,
        months: {},
        forecast: { projected: 40 },
        budget: { amount: 100 },
        status: "truncated",
        coverage: envelope({ truncated: true }),
        cacheHit: false,
      },
      "spend/pricing": {
        source: "policy/pricing.yaml",
        version: 3,
        currency: "USD",
        models: [{ id: "claude-opus", inputPer1k: 0.015, outputPer1k: 0.075 }],
        errors: [],
        sequence: 1,
      },
    });
    render(<SpendObservatory {...h.props} />);
    await act(async () => {});
    await h.host.settle();

    expect(
      await screen.findByText(/no forecast is projected from it/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/hit the row ceiling/).length).toBeGreaterThan(0);
    h.client.dispose();
  });

  it("shows the rate card every cost was computed from", async () => {
    const h = harness({
      "spend/series": {
        scope: {},
        dimension: "agent",
        totals: { cost: 3, tokens: 100, calls: 5 },
        byValue: { "claude-code": { cost: 3 } },
        spendSeries: {},
        coverage: envelope(),
        cacheHit: false,
      },
      "spend/forecast": {
        scope: {},
        team: null,
        months: {},
        forecast: { projected: 10 },
        budget: { amount: 100 },
        status: "ok",
        coverage: envelope(),
        cacheHit: false,
      },
      "spend/pricing": {
        source: "policy/pricing.yaml",
        version: 3,
        currency: "USD",
        models: [{ id: "claude-opus", inputPer1k: 0.015, outputPer1k: 0.075 }],
        errors: ["gpt-legacy"],
        sequence: 1,
      },
    });
    render(<SpendObservatory {...h.props} />);
    await act(async () => {});
    await h.host.settle();

    expect(await screen.findByText("claude-opus")).toBeInTheDocument();
    // A model with no rate card is counted but not costed, and says so.
    expect(screen.getByText(/counted but not costed: gpt-legacy/)).toBeInTheDocument();
    h.client.dispose();
  });
});

// --- DORA ----------------------------------------------------------------

describe("the DORA export", () => {
  it("shows an unevidenced key as unknown rather than inventing a number", async () => {
    const h = harness({
      "trust/doraExport": {
        status: {
          deploymentFrequency: "ok",
          leadTime: "unknown",
          changeFailureRate: "unknown",
          timeToRestore: "insufficient_coverage",
        },
        metrics: { deploymentFrequency: 3.5 },
        split: {},
        export: { schema: "otlp" },
        coverage: envelope(),
        storyId: "",
      },
    });
    render(<DoraExport {...h.props} />);
    await act(async () => {});
    await h.host.settle();

    expect(await screen.findByText("3.50")).toBeInTheDocument();
    expect(screen.getAllByText("Insufficient evidence").length).toBeGreaterThan(0);
    expect(screen.getByText("Not measurable")).toBeInTheDocument();
    expect(
      screen.getByText(/1 of four keys are evidenced/),
    ).toBeInTheDocument();
    h.client.dispose();
  });
});

// --- findings ------------------------------------------------------------

describe("every chart states its finding in words (A-10 / H7)", () => {
  it("names the leading rejection cause rather than leaving it to the bar", async () => {
    const h = harness({
      "trust/reasonDistribution": {
        scope: {},
        total: 10,
        byClass: { "missed-requirement": { count: 7 }, "style": { count: 3 } },
        byShape: {},
        byAgent: { "claude-code": { count: 10, leading: "missed-requirement" } },
        split: {},
        coverage: envelope(),
        cacheHit: false,
      },
    });
    render(<ReasonDistribution {...h.props} />);
    await act(async () => {});
    await h.host.settle();

    expect(
      await screen.findByText(/missed-requirement is the largest single cause, at 7 of 10/),
    ).toBeInTheDocument();
    h.client.dispose();
  });

  it("refuses to rank agents from a single-agent comparison", async () => {
    const h = harness({
      "trust/compareAgents": {
        scope: {},
        storyId: "edb-1",
        storyClassification: "brownfield",
        agents: { "claude-code": { proposed: 4, rejected: 1, score: 0.7, status: "ok" } },
        coverage: envelope(),
      },
    });
    render(<CompareAgents {...h.props} />);
    fireEvent.change(screen.getByLabelText("Story ID"), { target: { value: "edb-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    await act(async () => {});
    await h.host.settle();

    expect(
      await screen.findByText(/Only 1 agent worked this story, so there is nothing to compare/),
    ).toBeInTheDocument();
    h.client.dispose();
  });

  it("treats an unrecovered J-curve dip as expected, not as an alarm", async () => {
    const h = harness({
      "trust/jcurve": {
        scope: {},
        adoptionDate: "2026-06-01T00:00:00Z",
        status: "ok",
        baseline: 12,
        dip: { depth: 4, recovered: false },
        phases: { "w1": { value: 12 }, "w2": { value: 8 }, "w3": { value: 10 } },
        split: {},
        coverage: envelope(),
      },
    });
    render(<Jcurve {...h.props} />);
    fireEvent.change(screen.getByLabelText("Adoption date"), {
      target: { value: "2026-06-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Draw the curve" }));
    await act(async () => {});
    await h.host.settle();

    expect(
      await screen.findByText(/expected shape during adoption/),
    ).toBeInTheDocument();
    h.client.dispose();
  });

  it("says a tokenmaxxing flag is a prompt to look, not a verdict", async () => {
    const h = harness({
      "spend/series": {
        scope: {},
        dimension: "agent",
        totals: {},
        byValue: {},
        spendSeries: { "claude-code": [{ period: "2026-W01", tokens: 100 }] },
        coverage: envelope(),
        cacheHit: false,
      },
      "trust/tokenmaxxing": {
        scope: {},
        byAgent: {
          "claude-code": { tokens: 900_000, merged: 2, tokensPerMerge: 450_000, flagged: true },
        },
        team: {},
        coverage: envelope(),
      },
    });
    render(<Tokenmaxxing {...h.props} />);
    await act(async () => {});
    await h.host.settle();

    await waitFor(() =>
      expect(screen.getByText(/prompt to look, not a verdict/)).toBeInTheDocument(),
    );
    h.client.dispose();
  });
});
