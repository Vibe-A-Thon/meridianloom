# Meridian Loom

A VS Code extension that runs a governed, self-improving organisation of AI agents against a real codebase.

Specifications (read-only, in precedence order):

1. `docs/spec/Requirements-implementation.md` — build order
2. `docs/spec/Requirements_Final.md` — what to build
3. `docs/spec/viguix-implementation.md` — GUI build order
4. `docs/spec/VIGUIX_Final.md` — interface specification
5. `docs/spec/vision.md` — architecture rationale
6. `docs/spec/sample-meridian-loom-gui.html` — visual reference

Build progress is tracked in `BUILD_STATE.md`; decisions in `DECISIONS.md`.

## Recovering from a webview protocol mismatch

Run **Developer: Reload Window** from the VS Code command palette (`Ctrl+Shift+P`).
An extension host already running in memory can still speak the previous protocol
after its files have been rebuilt or updated. Closing and reopening the Meridian
panel does not restart that host.

For development, run `npm run build` at the repository root, then start **Run
Meridian Loom** with F5. The launch task builds both components and verifies their
protocol versions. Development uses `webview/dist`; installed extensions use their
packaged `webview-dist`. A build manifest prevents loading a mismatched webview.
If an installed extension still reports a mismatch after reloading, install a
fresh VSIX created with `npm run package`, then reload the window once more.

## Layout

The new [agent workbench](docs/gui-implementation.md) opens with **Meridian: Open
Recorder**. It includes Overview, Deliverables, Agent studio, Learning dojo,
Evidence, Runtime, Workspace guide, and Settings. The sample HTML informed the
visual direction; the shipped interface is React code connected to the host.

- Create, edit, remove, import, and export independent ACP agent profiles.
- Activate agents for delivery work; deactivate them into **Learning**. New and
  imported profiles start in Learning. Activation does not start a process.
- Run an active agent independently, or explicitly dispatch a brief to the active
  roster. Runs execute sequentially in the open workspace and expose output and
  stop controls. Review results before completing a deliverable.
- Completion feedback creates proposed memory notes for eligible Learning agents.
  Accepted notes become context for their next task. This does not train model
  weights or automatically promote skills and policy.
- Inspect provenance, sessions, ledger verification, and signed exports in
  Evidence. Choose seven themes, three densities, keyboard search, and focus mode.

Hosted execution requires a trusted workspace, the Governor tier, a connected
sidecar, and an installed ACP-compatible executable with its own credentials.
The bundled policy permits read/search on probation; participation marked Active
does not change permission policy. Overrides live in
`.meridian/policy/acp-permissions.yaml`; permitted tools still require approval.
Workbench data is saved in `.meridian/workbench/state.json`. Portable exports
carry configuration and reviewed memory, not the executable or credentials.

For a browser-only design preview:

```bash
npm run dev --workspace=webview -- --host 127.0.0.1 --port 5179
```

The preview is visibly labelled, uses temporary sample data, and executes no
agents. Its fixture transport is excluded from production builds. Launch the
extension using the VS Code development configuration or install the VSIX for
real use. The Workspace guide maps all 51 specified surfaces and describes their
remaining scope; a connected entry point can implement only part of a surface.

## Project directories

- `extension/` — VS Code extension host (TypeScript, esbuild)
- `webview/` — React dashboard (Vite, CSS modules, tokens)
- `shared/` — generated message-bus types (single source for extension, webview, core, simulation)
- `core/` — Python sidecar (`meridian_core` package)
- `extension/library/` — the shipped roster: 22 agents, the 10-pack skill catalogue,
  instruction documents and ACP runtime presets, seeded into a workspace on first open
- `simulation/scenarios/` — scripted scenarios (FR-M32-04)
- `golden/` — golden story corpus
- `policy/` — default policy packs incl. phase set and action-class catalogue
- `samples/` — reference repository and stories
- `examples/bridged/` — example bridged agents
- `docs/spec/` — the specification (read-only)

## Build, run, test, package

**Prereqs:** Node 22 + npm 10, Python 3.11+ (`python` on PATH), Rust 1.97+ (optional — only for verifier tests; they skip-and-notice without it), Git 2.40+. No model credentials anywhere — the Flight Recorder makes zero model calls.

```bash
npm install                      # workspaces: extension + webview
node scripts/generate-bus-types.mjs   # regenerate shared bus types (also runs in build)
npm test                         # pytest (core) + vitest (extension + webview) + typecheck
npm run build                    # bus types + webview (Vite) + extension (esbuild)
npm run check:contracts          # fails if generated bus types are stale vs shared/schema
npm run package                  # dist/meridian-loom-<ver>.vsix
cd core && python -m pytest -q   # core-only, targeted runs
cd verifier && cargo test        # Rust open verifier (optional)
```

**What works now (F0 — Flight Recorder):** installable VS Code extension with a Python sidecar over framed JSON-RPC stdio; append-only SQLite ledger (hash-chained, Merkle-indexed, signed tree heads, encrypted content-addressed blobs, per-subject keys); chain verification (~3s/100k) with first-divergent-sequence; deterministic attribution (git blame/diff, tree-sitter symbols, human-vs-agent heuristics, all confidence-labelled); Claude Code and Copilot observers with a degradation fallback chain; external-session detection; rejection capture + greenfield/brownfield trust metrics; opt-in `commit-msg` provenance hook (`Meridian-Ledger:` trailers); signed audit bundles with NIST SSDF / ISO 42001 / EU AI Act mapping; open reference verifier (Python single-file + Rust binary) and the open ledger spec under `docs/open-ledger-spec/`; the three GF0 screens (10.45 Flight Recorder, 10.46 External Agents, 10.7 Ledger, 10.40 First-Run) running on real sidecar data; tiering scaffold (Flight Recorder base tier; Governor/Orchestra refused until enabled).

**What works now (F1 — Governor, in addition to F0):** ACP host — install adapters from the ACP Registry, probation with policy-checked permissions (FR-M34-04 wraps the approver), hosted sessions with steer & clarify (observed agents get honest "not hosted" controls, never fake ones); external-agent PR ingest with Security/Review gates — merge requires a recorded approver identity and a changed head invalidates the approval; roles and approval hygiene; trust analytics derived on demand from the ledger (rejection rate and reason distribution split greenfield/brownfield, trust-score decomposition, agent-vs-agent comparison with unknown-labelled components, adoption J-curve, tokenmaxxing detector, DORA four-keys export in OTLP JSON); cross-vendor spend by vendor/model/agent/story/team/cost-centre with predictable pricing packs, monthly forecast + budget alerts, and spend ceilings that pause hosted agents at the next checkpoint (advisory-only for observed agents); Cursor, Codex and Devin observers (telemetry/inferred, never direct). Every new surface is ledger-reconciled and makes zero model calls.

**Try it:** `npm run package`, install the .vsix, run `Meridian: Open Recorder` (command palette) — the panel opens against a real sidecar; run `Meridian: Doctor` for the health report; enable the provenance hook via `Meridian: Install Git Hook`. With Claude Code or Copilot active in the workspace, sessions and provenance appear on the real-data screens.

Build progress is tracked in `BUILD_STATE.md`; decisions in `DECISIONS.md`.
