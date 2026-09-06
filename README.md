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

## Layout

- `extension/` — VS Code extension host (TypeScript, esbuild)
- `webview/` — React dashboard (Vite, CSS modules, tokens)
- `shared/` — generated message-bus types (single source for extension, webview, core, simulation)
- `core/` — Python sidecar (`meridian_core` package)
- `adapters/` — prebuilt agent roster, each a full adapter folder
- `sdk/` — `meridian-adapter`: protocol, scaffold, local harness, conformance suite
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

**Try it:** `npm run package`, install the .vsix, run `Meridian: Open Recorder` (command palette) — the panel opens against a real sidecar; run `Meridian: Doctor` for the health report; enable the provenance hook via `Meridian: Install Git Hook`. With Claude Code or Copilot active in the workspace, sessions and provenance appear on the real-data screens.

Build progress is tracked in `BUILD_STATE.md`; decisions in `DECISIONS.md`.
