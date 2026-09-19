# Changelog

All notable changes to Meridian Loom.

## [Unreleased]

**Licensing.** The extension manifest now declares the MIT license matching
the repository LICENSE, and the manifest is no longer marked private — the
distribution-channel decision (audit TASK-100, DECISIONS 18 Sep 2026) is
unblocked. No runtime change.

**Governed initiation, a reachable supply chain, and the release artefacts an
organisation needs to adopt and to leave.**

### What it ships as

Three tiers, and which are enabled is a workspace setting (`meridian.tiers`),
not a reinstall:

- **Flight Recorder** — the base tier, always on. Observes agents you start
  yourself, records provenance, verifies the chain, exports evidence, and now
  reads and notarises other provenance tools' records. It makes no model calls
  at all.
- **Governor** — permission policy, gates, approvals, run initiation, the
  pull-request evidence card, worktrees.
- **Orchestra** — multi-agent loops. Not in this release.

Disabling a tier leaves the tiers below whole, and a disabled tier is absent
rather than greyed out.

### Changed — the evidence gate applies the thresholds written before the study

- **The evidence gate scores against `docs/evidence-gate.md` as written.** Ten
  measures, each met, not met or unmeasured. A threshold nobody measured is
  never counted as met, and an outcome that depends on one is not reached.
  Before this, the gate could return GO on a single unconfirmed block, and it
  read an unmeasured change failure rate as "not worse". On a real ledger it
  counted no gate stop at all, because it looked for a decision the Governor
  never records.
- **A study can be scored without the editor.**
  `python -m meridian_core.cli evidence-gate` reads a study record and writes
  the report, the raw ledger slice as a signed bundle, and a draft of the
  written decision. It writes a draft, never the decision.
- **Two bundles can be compared.** `python -m meridian_core.cli compare-evidence`
  verifies both and reports whether they carry the same evidence shape.

No study has been run. Nothing here is a measurement, and no threshold may be
quoted as one.

### Added — starting work is possible and governed (`M40`)

- **One initiation contract.** Every door into the runtime — the command
  palette and the Launch screen today, six more in the vocabulary — builds one
  `RunRequest` and calls one entry point. Runs started from different doors
  produce ledger records differing only in `origin`.
- **Preflight is mandatory.** Before anything is created you see the intent,
  the agents, the repository and branch, the cost estimate and ceiling, the
  gates, and dry-run or live. There is no skip and no "do not show again". An
  unknown cost reads *not estimated*, never `$0.00`.
- **Cancelling creates nothing.** No worktree, no branch, and one cancellation
  record. That is structural, not a cleanup path: nothing is created before
  you confirm, so nothing needs tidying if you do not.
- **Launch authority is role-checked** and the authorising identity is
  recorded with its assurance level. A read-only role may start a dry run,
  which writes nothing, and may not start a live one.

### Added — supply chain

- **Adapter digest pinning.** Whatever Meridian installs is digested at
  install and checked before its agent launches. A folder that changed does
  not load, and the refusal names the digest recorded at install and the
  digest on disk. The refusal is recorded in the ledger too.
- **Verifiable agent identity.** The binary behind an agent is resolved from
  `PATH` and digested before the process starts; a swap under an unchanged
  name warns. Where the launch command is a run-time package fetcher (`npx`,
  `uvx`, `pipx run`) the agent is downloaded afterwards, so identity is
  recorded as **unverified** naming the fetcher rather than passing the
  fetcher's digest off as the agent's.
- **The ACP Registry is browsable** from the Adapter Bay. The index is fetched
  only when you ask — opening a workspace makes no network call — and an entry
  installs into Learning with `read`, `search` and `think` and nothing else.
  A registry listing is not a review, not a security assessment and not an
  endorsement.
- **A CycloneDX AI-BOM** is generated from the built package and published
  beside the VSIX and its checksum, listing every shipped agent, skill,
  instruction document, runtime preset and runtime dependency with its digest.
  Drift between the BOM and the package fails the build.

### Added — evidence

- **Other tools' records are read and notarised.** If another provenance tool
  writes git notes in your repository, Meridian records the *digest* of each
  in the signed ledger, so a third party can prove the record has not been
  altered since Meridian read it. The content is not copied. Each record is
  attributed to the tool that wrote it, at `inferred` — Meridian did not
  observe the work, it read a file claiming the work happened — and the
  signature covers the digest, not the claim.
- **Disagreements between provenance records are reported, never resolved.**
  When two records name different agents for the same commit — another tool's
  note, a co-author line, a session trailer, or Meridian's own ledger — both
  are shown side by side, and neither is preferred, Meridian's own included.
  Recording a disagreement is a separate action and stores digests, never
  content. The comparison is per commit. Notes under `refs/notes/exceeds-ink`
  are now attributed to Exceeds Ink rather than to an unrecognised tool.
- **Meridian's attributions export to formats other tools read.** You get a
  line-level attribution export, and one JSON git note per commit under
  `refs/notes/meridian-attribution`, written only when you ask. Every line is
  agent, human or unattributed, and unattributed is never counted as human.
  No line content is included. A disagreement another record raises travels
  with its commit, unresolved. Neither format claims to match another tool's
  schema.
- **Provenance reconciliation** has its own tab in Evidence: other tools'
  records, their notarisation, disagreements and export, in one place.
- **A pull-request evidence card**: change risk, coverage gaps, failed checks,
  cost, the human action required, and **the revision actually tested**. A
  gate verdict recorded against a head the branch has moved past is shown as
  stale rather than as a pass.
- **Run and origin** now appear on a ledger entry's full record.

### Added — what an organisation needs to operate it and leave

- **`SECURITY.md`** — where to report a vulnerability, what is in scope, and a
  response commitment one part-time maintainer can actually meet. There is no
  bounty, and saying otherwise would be an unbacked promise.
- **`THIRD-PARTY-NOTICES.md`** — generated from the same licence sweep that
  backs the no-copyleft statement, so that statement is checkable rather than
  asserted. It fails the build when it falls out of date.
- **`docs/SUPPORT.md`** — supported versions, the notice a breaking change
  carries, what survives an upgrade, and the export path on the way out. It
  also says plainly that no paid support offering exists.

All three ship inside the package, because a VSIX sideloaded into an
enterprise arrives without the repository.

### Fixed

- The Launch screen was registered in a screen registry that nothing renders,
  so it never reached the built package. It is now mounted on the route the
  application actually uses.
- Adapter pin *verification* lived only in a code path the extension never
  called, so it was removed from the bundle by tree-shaking and the digest
  recorded at install was never read back. It now runs before an agent
  launches.
- A malformed ACP Registry index was reported as the registry being
  unreachable, sending an operator to check their network over somebody
  else's bad publish.

Both of the first two were found by a new check that reads the built VSIX
rather than the checkout, and neither was visible to any unit test.

### Limitations — unchanged, and stated in full

These are deliberate and documented. See
[`docs/SECURITY-AND-DATA.md`](../docs/SECURITY-AND-DATA.md) §6.

- **Without a witness, a re-signed fork of the whole ledger still verifies.**
  Signature verification detects a changed entry and a broken chain link. It
  does not, on its own, detect wholesale ledger replacement by a machine
  administrator.
- **The commit trailer is editable.** It is a pointer to the record, not a
  proof of it.
- **Enforcement is in the editor, not the SCM.** Every control declares where
  it actually binds, and in this release nothing claims SCM enforcement.
- **Identity is asserted, not verified, by default.** A git name and email is
  a claim, labelled `asserted` wherever it appears.
- **Effectiveness is unmeasured.** The project's own gate — twenty real
  stories through a real team, measured — has not run.

### What this release does not claim

It makes **no claim** that it improves **delivery outcomes**, reduces
**defects**, saves **cost** or raises **productivity**. Those require evidence
this project has not collected, and when it is collected the rule is that
unfavourable results are published too.

Not yet done, and recorded as such in `docs/claims.md`: the demonstration has
not been walked end to end on a clean machine by someone who did not build it,
and the pull-request card has not been run against a live gated pull request.

## [0.1.0] — 2026-09-12

**First distributable release.** Installed by sideloading the VSIX
(`code --install-extension meridian-loom-0.1.0.vsix`), not from the
Marketplace. That is a deliberate choice, not an unfinished step: `D19` in
`DECISIONS.md` records the owner deferring the licence question in order to
distribute privately to pilot organisations first. `private: true` and the
absent `license` field are the correct state for that path, and the
missing-LICENSE warning `vsce package` prints is expected.

**Why this is 0.1.0 and not 1.0.0.** The project's own gate — `F2`, twenty
real stories through a real team, measured over weeks — has not run. Every
measure it needs is computable from shipped surfaces, but the evidence does
not exist yet, and a 1.0 that asserted proven value ahead of it would
contradict the rule this product exists to enforce. 1.0.0 is gated on that
evidence.

For evaluators: [`docs/SECURITY-AND-DATA.md`](../docs/SECURITY-AND-DATA.md)
and [`docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

### Added — release readiness

- An extension icon, so the entry in the Extensions view is identifiable.
- A headless `doctor` command, so a rollout can be validated in CI without
  opening an editor.
- Security, data-handling and deployment documentation written for an
  organisation's review rather than for a user.

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
