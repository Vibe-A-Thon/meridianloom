# Changelog

All notable changes to Meridian Loom.

## [Unreleased]

Pre-release. Not published to the Marketplace: the licence is an open decision
(`DECISIONS.md`, D22) and the package stays `private` until it closes.

### Added — single-page workbench

- The workbench is contributed as an Activity Bar **view**, so selecting
  Meridian Loom opens it with no command in between.
- One page, fifteen tabs in four groups, Dashboard first. A tab owns a list of
  views, so the fifty-odd existing surfaces stay reachable as sub-views rather
  than being orphaned by the new shell.
- **Agents** — add, edit, remove, activate/deactivate, run, export, and import
  from a Markdown card, an adapter folder in a ZIP, or a portable JSON export.
  An imported agent always enters Learning, and a package that names no
  permissions gets only `read`, `search` and `think`: an import is not consent
  to write files or run commands.
- **Skills**, **Instructions** and **SDLC phases** as first-class catalogues.
- **Runs** — live and past runs with the exact briefing that was sent,
  streamed output, queued steering and a scoped stop.
- **Integrations** — seventeen systems, read-only, credentials in the OS
  keychain. A connection is proved by reaching it; a green probe older than
  thirty minutes reads *Stale*.
- **Trust & Spend Observatory** — trust score and decomposition, rejection
  reasons, agent comparison, adoption J-curve, tokenmaxxing, DORA four keys,
  spend series, forecast and pricing.

### Added — visual system

- Phase, signal, glass and motion token layers across all seven themes.
- SVG visualisation primitives (sparkline, ring, stacked bar, heat strip,
  meter, state dot) with a text alternative on every one and no reliance on
  colour alone.
- All motion is transform/opacity only and collapses to zero under
  `prefers-reduced-motion`.

### Fixed

- **Bindings now reach the agent.** Skills, instruction files, phase tags and
  connected systems were catalogued, bound, displayed and exported, and none of
  them reached the running agent while the interface said they did. The agent
  received only the title, the brief and its role. `composeBriefing` now
  assembles the whole document and `convene` selects agents phase by phase in
  SDLC order.
- **One prompt composer.** The launch path built a second prompt, duplicating
  the agent's instructions and memory and making the recorded run prompt differ
  from what the agent received. The briefing is now composed once, recorded,
  and sent verbatim.
- **One steering implementation** (AMD-M25 / G-03). The workbench called
  `steer.send` and injected the turn itself, so the clarifying-question
  protocol, uncertainty escalation and partial acceptance existed on one path
  and not the other. `HostedSteerController` is now the only caller of any
  `steer/*` RPC; delivery timing is an explicit policy on it.
- **Spend no longer guesses at truncation.** The Cross-Vendor Spend panel
  consumed `ledger.query` and inferred truncation from `entries.length === 1000`,
  which understates cost silently at the ceiling. It now reads the coverage
  envelope and disables the forecast when the sample is partial.
- `trust/rejectionRate` returning `null` under the attribution floor rendered
  as a percentage of an absent value; it now reads "Not measurable" with the
  suppression reason beside it.
- An imported agent with no declared permissions was rejected outright, which
  broke the primary drop-in-a-file flow.

### Verification

- **Continuous integration** (`.github/workflows/verify.yml`). 2,121 tests
  existed and none ran automatically; every "green" in this repository was a
  green somebody ran by hand, once, on one machine. Contracts and the
  surface-coverage gate run first, then the TypeScript suites on Linux, Windows
  and macOS — the product is cross-platform and had only ever been verified on
  Windows — then the Python core including the 50k performance budgets, then a
  real package build. Budgets are reported on every run, not only when they
  break, and re-checked weekly on a schedule.
- **NFR-33 performance budgets were failing while recorded as PASS.**
  `BUILD_STATE.md` cited figures measured at `45928f1`; two commits later the
  attribution-coverage floor and the per-bucket greenfield/brownfield split
  both landed and nobody re-measured. `trust/rejectionRate` had reached 5.81s
  and `trust/doraExport` 7.34s against a 5s budget. Fixed: a redundant full
  ledger scan removed from `compute_rejection_rate` (the diff population is a
  subset of a scope already read, and its COUNT was discarded), and the DORA
  time-to-restore linear tail scan replaced with a bisect over already-sorted
  stamps. Now 3.90s and 3.74s, with all eight budgets re-measured and recorded.
- **Correctness and budgets are now separate jobs.** The 50k tests asserted
  both an AC-41 full-scan equality (true on any machine) and a 5-second budget
  (not true on a machine running three other suites) in the same test, so a
  busy runner reported a correctness failure and a real regression looked like
  noise. `MERIDIAN_PERF_REPORT_ONLY` keeps every equality assertion live and
  prints the timings without enforcing them; a dedicated CI job enforces the
  budgets alone on a fresh runner, and enforcement stays on by default locally.
- `core/tests/test_nfr33_budgets_are_current.py` fails if a budgeted metric is
  missing from the recorded figures, or if the record cites a commit without
  saying when it was measured — the exact shape the stale claim had.

### Support

- **Doctor → Copy diagnostics** produces a paste-ready report: the doctor's
  findings plus extension, VS Code, platform and tier versions. No credentials,
  no ledger contents, no workspace path, and it says so before copying.
- A missing agent executable used to surface as `spawn claude ENOENT`. It now
  says the command is not on PATH and what to do about it — the most common
  first-run failure, since Meridian runs agents you install rather than
  bundling them.
- A GitHub issue template that asks for the diagnostics blob first.

### Security

- Integration credentials go to the OS keychain, namespaced per connection.
  They are never written to the workspace, never included in an export, and
  never shown back — not even masked, because a mask leaks the length. Where no
  keychain is available the save is refused rather than falling back to a file.
- Errors from HTTP clients and CLIs are redacted before display or storage.
- Archive members with traversal-unsafe paths are reported as skipped rather
  than surfaced; the ZIP reader accepts stored and deflate members only, with
  member, archive and count limits.
- `identity.revoke` is surfaced as a confirmed operator control stating both
  consequences: it binds immediately, and approvals the identity already gave
  stop counting at the next gate execution.
