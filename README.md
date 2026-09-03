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

_(updated as phases land — see BUILD_STATE.md)_
