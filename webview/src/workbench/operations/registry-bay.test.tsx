import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  RegistryBrowseResult,
  WorkbenchExecute,
} from "../../../../shared/ts/workbench";
import { RegistryBay } from "./RegistryBay";

/**
 * The ACP Registry in the Adapter Bay — `FR-M34-03`, `B2`, `G4` (MV3-T02).
 *
 * The surface half of the wiring. Three properties it must not lose:
 *
 *  - **Mounting fetches nothing.** The whole feature is subordinate to the
 *    no-phone-home statement in `docs/SECURITY-AND-DATA.md` §2, and a
 *    `useEffect` that loads on mount is how that gets broken by someone
 *    being helpful.
 *  - **Five states, five different things to do.** `B2`.
 *  - **A listing is not an endorsement**, said on the surface and not only
 *    in documentation, because the documentation is not open while somebody
 *    is choosing what to install.
 */

const ENTRY = {
  id: "acme-java-developer",
  name: "Acme Java Developer",
  version: "2.3.0",
  description: "A Java agent.",
  authors: ["Acme"],
  license: "MIT",
  website: "https://example.invalid/acme",
  distributions: ["npx"],
  identityVerifiable: false,
};

function harness(
  browse: RegistryBrowseResult = {
    state: "fresh",
    entries: [ENTRY],
    registryUrl: "https://registry.invalid/index.json",
    fetchedAt: "2026-09-13T10:00:00Z",
  },
) {
  const execute = vi.fn(async (action: string) => {
    if (action === "registry/browse") return browse;
    return {
      ok: true,
      errors: [],
      installed: {
        id: ENTRY.id,
        dir: "/ws/.meridian/adapters/acme-java-developer",
        pinDigest: `sha256:${"a".repeat(64)}`,
        permissions: ["read", "search", "think"],
      },
      snapshot: {},
    };
  });
  const controller = {
    snapshot: {} as never,
    execute: execute as unknown as WorkbenchExecute,
    busy: false,
    error: null,
    refresh: async () => {},
  };
  return { execute, controller };
}

describe("the registry is browsed on request, never on arrival", () => {
  it("renders without reaching the network", async () => {
    // If this fails, SECURITY-AND-DATA.md §2 is false and the feature comes
    // out, not the sentence.
    const h = harness();
    render(<RegistryBay controller={h.controller} />);
    await waitFor(() => expect(screen.getByTestId("registry-bay")).toBeInTheDocument());
    expect(h.execute).not.toHaveBeenCalled();
  });

  it("fetches when a person presses the button", async () => {
    const h = harness();
    render(<RegistryBay controller={h.controller} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() => expect(h.execute).toHaveBeenCalledWith("registry/browse", {}));
  });
});

describe("what the bay says before anything is installed", () => {
  it("says what a listing proves, and then what it does not", async () => {
    // G4/MP5, in the register of the release `.sha256` paragraph. A browse
    // surface that omits this invites the reader to supply the missing
    // reassurance themselves.
    const h = harness();
    render(<RegistryBay controller={h.controller} />);
    const disclaimer = screen.getByTestId("registry-disclaimer");
    expect(disclaimer).toHaveTextContent("not a review");
    expect(disclaimer).toHaveTextContent("not an endorsement");
    expect(disclaimer).toHaveTextContent(
      "says nothing about whether the original contents were safe",
    );
  });

  it("warns before the install that an npx entry cannot be identified", async () => {
    // FR-M44-01 read forward. Learning this after installing is learning it
    // too late to have chosen differently.
    const h = harness();
    render(<RegistryBay controller={h.controller} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() =>
      expect(screen.getByTestId(`registry-identity-${ENTRY.id}`)).toHaveTextContent(
        "cannot identify which build runs",
      ),
    );
  });

  it("says the opposite for an entry that ships a binary", async () => {
    const h = harness({
      state: "fresh",
      entries: [{ ...ENTRY, distributions: ["binary"], identityVerifiable: true }],
      registryUrl: "https://registry.invalid/index.json",
    });
    render(<RegistryBay controller={h.controller} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() =>
      expect(screen.getByTestId(`registry-identity-${ENTRY.id}`)).toHaveTextContent(
        "identified by digest",
      ),
    );
  });
});

describe("B2: five states, five things to do", () => {
  it.each([
    ["unreachable", "could not be reached, and nothing was cached"],
    ["malformed", "index could not be read"],
    ["cached-stale", "Showing a cached copy"],
  ] as const)("%s reads as itself", async (state, text) => {
    const h = harness({
      state,
      entries: [],
      registryUrl: "https://registry.invalid/index.json",
      notice: "the sidecar's sentence",
    } as RegistryBrowseResult);
    render(<RegistryBay controller={h.controller} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() =>
      expect(screen.getByTestId("registry-state")).toHaveTextContent(text),
    );
    expect(screen.getByTestId("registry-notice")).toHaveTextContent(
      "the sidecar's sentence",
    );
  });

  it("an empty list points at the reason rather than claiming an empty registry", async () => {
    // P26: "nothing there" and "we could not look" are different facts.
    const h = harness({
      state: "unreachable",
      entries: [],
      registryUrl: "https://registry.invalid/index.json",
      notice: "offline",
    } as RegistryBrowseResult);
    render(<RegistryBay controller={h.controller} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() =>
      expect(screen.getByTestId("registry-empty")).toHaveTextContent(
        "See the state above for why",
      ),
    );
  });
});

describe("installing", () => {
  it("reports the floor and the pin it landed with", async () => {
    const h = harness();
    const onInstalled = vi.fn();
    render(<RegistryBay controller={h.controller} onInstalled={onInstalled} />);
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() => screen.getByTestId(`registry-install-${ENTRY.id}`));
    fireEvent.click(screen.getByTestId(`registry-install-${ENTRY.id}`));

    await waitFor(() =>
      expect(screen.getByTestId("registry-installed")).toHaveTextContent(
        "read, search, think",
      ),
    );
    expect(screen.getByTestId("registry-installed")).toHaveTextContent("Pinned as sha256:");
    // The reassurance that matters most: it is on the machine and it is inert.
    expect(screen.getByTestId("registry-installed")).toHaveTextContent(
      "cannot run until you bind and activate it",
    );
    expect(onInstalled).toHaveBeenCalledTimes(1);
  });

  it("shows a refused install instead of pretending it worked", async () => {
    const execute = vi.fn(async (action: string) => {
      if (action === "registry/browse")
        return {
          state: "fresh",
          entries: [ENTRY],
          registryUrl: "https://registry.invalid/index.json",
        };
      return { ok: false, errors: ["archive digest mismatch"], snapshot: {} };
    });
    render(
      <RegistryBay
        controller={{
          snapshot: {} as never,
          execute: execute as unknown as WorkbenchExecute,
          busy: false,
          error: null,
          refresh: async () => {},
        }}
      />,
    );
    fireEvent.click(screen.getByTestId("registry-browse"));
    await waitFor(() => screen.getByTestId(`registry-install-${ENTRY.id}`));
    fireEvent.click(screen.getByTestId(`registry-install-${ENTRY.id}`));
    await waitFor(() =>
      expect(screen.getByText(/archive digest mismatch/)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("registry-installed")).toBeNull();
  });
});
