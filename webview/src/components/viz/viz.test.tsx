import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Dot, HeatStrip, Meter, Ring, Sparkline, StackedBar, Stat } from "./Viz";

/**
 * The visualisation primitives.
 *
 * A chart that only exists as a picture is decoration. Every one of these is
 * asserted to carry the same fact in text that it carries in geometry, and
 * none of them may lean on hue alone — the two things that separate a
 * data display from a colourful one.
 */

describe("Sparkline", () => {
  it("states the direction and the range it is drawing", () => {
    render(<Sparkline values={[1, 4, 2, 9]} label="Throughput" />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Throughput: rising, from 1 to 9, low 1, high 9",
    );
  });

  it("says so rather than drawing a line through one point", () => {
    render(<Sparkline values={[3]} label="Throughput" />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Throughput: not enough data to plot",
    );
  });

  it("does not clip a flat series against the top of the box", () => {
    const { container } = render(<Sparkline values={[5, 5, 5]} label="Flat" />);
    const path = container.querySelector("path[stroke]")!;
    // A zero range must not divide by zero or leave the line on the edge.
    expect(path.getAttribute("d")).not.toContain("NaN");
    expect(path.getAttribute("d")).toContain("25.00");
  });
});

describe("Ring", () => {
  it("names the fraction, not just the fill", () => {
    render(<Ring value={4} total={9} label="Phases covered" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Phases covered: 4 of 9");
  });

  it("treats a zero total as empty rather than dividing by it", () => {
    const { container } = render(<Ring value={0} total={0} label="Nothing" />);
    for (const circle of container.querySelectorAll("circle"))
      expect(circle.getAttribute("stroke-dashoffset") ?? "0").not.toContain("NaN");
  });
});

describe("StackedBar", () => {
  it("lists every segment with its number, so the legend is the accessible copy", () => {
    render(
      <StackedBar
        label="Roster"
        segments={[
          { label: "Active", value: 3, signal: "ok" },
          { label: "Learning", value: 1, signal: "idle" },
        ]}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Roster: Active 3, Learning 1",
    );
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("says nothing is recorded rather than drawing an empty bar", () => {
    render(<StackedBar label="Roster" segments={[{ label: "Active", value: 0 }]} />);
    expect(screen.getByText("Nothing recorded yet.")).toBeInTheDocument();
  });
});

describe("HeatStrip", () => {
  it("summarises the run of states in its accessible name", () => {
    render(
      <HeatStrip
        label="Runs"
        cells={[
          { id: "a", signal: "ok", title: "a" },
          { id: "b", signal: "ok", title: "b" },
          { id: "c", signal: "fail", title: "c" },
        ]}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName("Runs: 2 ok, 1 fail");
  });
});

describe("Dot", () => {
  it("uses a different glyph per state, so greyscale still reads", () => {
    const glyphs = (["ok", "warn", "fail", "idle"] as const).map((signal) => {
      const { container, unmount } = render(<Dot signal={signal} title={signal} />);
      const text = container.textContent;
      unmount();
      return text;
    });
    // Four states, four distinct shapes — hue is the second signal, not the only one.
    expect(new Set(glyphs).size).toBe(4);
  });

  it("says the state in words to assistive technology", () => {
    render(<Dot signal="fail" title="Unreachable" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Unreachable");
  });
});

describe("Meter", () => {
  it("is a meter with real bounds, not a coloured div", () => {
    render(<Meter value={0.42} label="Coverage" />);
    const meter = screen.getByRole("meter", { name: "Coverage" });
    expect(meter).toHaveAttribute("aria-valuenow", "42");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps a value outside 0–1 instead of overflowing its track", () => {
    render(<Meter value={2.5} label="Coverage" />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "100");
  });
});

describe("Stat", () => {
  it("is a button only when it goes somewhere", () => {
    const { unmount } = render(<Stat label="Agents" value={3} />);
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    render(<Stat label="Agents" value={3} onClick={() => {}} />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});
