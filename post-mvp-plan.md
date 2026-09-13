# Meridian Loom — POST-MVP build plan

| | |
|---|---|
| **Governs** | Everything `mvp-req-final.md` dispositions `POST-MVP`, in the order below |
| **Authority** | `DECISIONS.md` `D56` — the user's direction of 13 September 2026 to build `POST-MVP` before `MV5` has run |
| **Does not supersede** | `mvp-req-final.md`, `mvp-impl-plan.md`, or any source plan. Their requirement text, principles and kill criteria stand; this document orders the work and tracks it |
| **Baseline** | `e4ce221` on `dev_local` — MV0–MV5 committed; `npm test` green (extension 613, core 1829, webview 347) |

---

## 0. The rules this build keeps

1. **`MV5` is not pre-empted.** Nothing built here counts toward `docs/evidence-gate.md`'s thresholds. The Orchestra tier stays **absent** unless a workspace enables it (`G5`), so a study can still keep Meridian's own agents out of its arms. `FR-M46-17`'s commitment is not rewritten (`D56`).
2. **`MP1`–`MP9` apply unchanged.** Every test demonstrated failing first, and the demonstration recorded (`MP2`). Every shipped claim bound to a test in `docs/claims.md` (`MP5`). Packaging-sensitive behaviour verified from the package (`MP7`). Nothing reachable only from a test (`MP4`). One tree, one sequential suite, one commit per task (`MP3`).
3. **Decisions that belong to someone else are not made by building.** §3 lists them and what each blocks. A track reaching one stops at it, records why, and continues with everything that does not depend on it.
4. **Corrections before construction.** Where a document describes something as existing that does not, the document is corrected first (§1), so no task is planned on a foundation that is not there.

## 1. Corrections found while planning

| Found | Correction |
|---|---|
| `mvp-req-final.md` §3.1 says `core/meridian_core/runtime/` "exists as substrate", `router/` "exists", and the Simulation Core is "Partly `BUILT`" in `simulation/` | All of `runtime/`, `router/`, `simulation/`, `memory/`, `replay/`, `tools/`, `adapters/` and `connectors/` are **empty, untracked directories**. `M4`, `M8` and `M32` start from nothing |
| `mvp-impl-plan.md` §8 names `J-1` "the first candidate after the MVP" | `jit-impl.md` §0.2 places `J1` inside `F3`: harness resolution happens at packet start in the loop runtime, which is absent. `J1` and `J2` are built inside `F3` |
| `FR-M52-01` reads other tools' notes by a closed ref vocabulary | The competitor `§16.1` names first, `CMP-01`, writes to `refs/notes/exceeds-ink`, which the vocabulary does not recognise; its notes are read as `unknown-tool`. Fixed in `CP1-T01` |

## 2. Order, by dependency

Each track depends only on what exists or on the tracks above it.

| # | Track | Scope | Why here | Status |
|---|---|---|---|---|
| **1** | **CP1** Notary, completed | `FR-M52-04`/`05`, `AC-60`, `NFR-53`, screen 10.54 | Extends `MVP-R7.1`, which is built. Cheapest | **In progress** |
| **2** | **CP2** Attested identity | `FR-M49-01`…`05`, `AC-66`, `NFR-50`, `SEC-46`/`47` | Extends `MV3-T01b`'s executable identity. A gateway that cannot say *which* agent called is a log (`mvp-impl-plan.md` §16) | Not started |
| **3** | **CP3** The tool-call boundary | `FR-M48-02`…`05`, `AC-65`, `NFR-49`; `FR-M48-01`, `AC-64`, `SEC-45` wait on `D48` | Needs CP2's identity for lineage | Not started |
| **4** | **CP4** Outcomes and standard envelopes | `FR-M51-01`…`04`, `AC-67`, `NFR-51`, screen 10.55; `FR-M50-05`…`08`, `FR-M43-09`/`10`, `AC-68`, `NFR-52`, `SEC-48` | Needs ledger history, which exists; DSSE wraps the bundle, which exists | Not started |
| **5** | **G** Governor completions | `FR-M41-16`/`17` backfill (`NFR-35`); `SEC-38` append-only corrections; `NFR-41` reconciliation; `AMD-M20` expansion signal; `AMD-M39`/`FR-M45` merge binding (`AC-51`); `FR-M40-04`/`06`/`07`/`08`/`10`; `NFR-36`/`SEC-31`/`AC-46` revocation seam; `ECO-01`/`02` internal registry; the 100-fixture adversarial corpus (`SEC-34`, wide) | Each extends a built tier and depends on no Orchestra component | Not started |
| **6** | **F3** Orchestra | In `gaps_implementation.md` §F3 order: `M33` full (gated, see §3) → `M8` router → `M4` loop runtime and `L1`–`L6` → `M9`, `M28` → `M7` → `M38` (`AC-35`, `AMD-M38`) → `M31` roster as ACP agents → **`J1`**, **`J2`** → `M5`, `M6`, `M13`, `M26` → `FR-P1`…`P7` agent-side → `M32` Simulation Core as regression harness → `AC-01`…`AC-29` | The largest investment; built on a tier that must stay absent until enabled | Not started |
| **7** | **F4+** Learning, scale, compliance | `C3` (`M12` full) · `C4` (`M14` Trainer, `M15` wizard, `M16`) · `C5` (`M21`, `M22`, `ECO-04`/`05`/`07`) · `C6` (`ECO-06`, `ECO-08`) · `M29` · `FR-P8`/`P9` (plans only, `D7`) · `J3`/`J4` (`D44`) | Needs F3's runtime, roster and evaluation machinery | Not started |
| **8** | **GF3** Screens | The 35 `POST-MVP` screens of `mvp-req-final.md` §9.1, including 10.52 Harness Bench and 10.53–10.55 | Each screen is built with the capability it shows, not ahead of it (`H1`) | Not started |

## 3. Decisions this build does not make

| Decision | Owner | What it blocks | What proceeds without it |
|---|---|---|---|
| `D19` licence · marketplace listing · open-core split · licence-key enforcement | Owner, deferred 10 Sept 2026 | All of it | Everything else. `private: true` and no `license` field stay correct |
| `D48` ship an MCP gateway, or stay the notary | Owner with a platform team | `FR-M48-01`, `AC-64`, `SEC-45`, `NFR-49` | `FR-M48-02`…`05`, `AC-65` — lineage, observing an existing gateway, the declaration, the bundle predicate |
| `D44` adopt harness synthesis | Product, at `J2` exit | `FR-M47-09`…`26`, `J3`, `J4` | `J1`, `J2` |
| `D42` / `FR-M46-16` deterministic-engine investment gate | Answered in `G-1`: binding | `M33` growth beyond the structural set until per-class value is measured on a real corpus | The measurement itself (`FR-M33-07` exists); `F3` tracks that do not grow `M33` |
| `D49` SPIFFE: consume-if-present or bundle | Architecture | Bundling a SPIRE agent | Consuming an existing SPIRE workload API where present (`FR-M49-02`) |
| `D51` witness interoperability target | Owner | Choosing a transparency service | Shaping the seam so the choice stays the customer's (`FR-M50-07`) |
| `D53` longitudinal outcomes before `MV5` | Owner | — | Answered for *building* by `D56`. No longitudinal figure is presented as an effectiveness claim (`P27`, `FR-M51-04`) |
| `D14` security phase scope · `D7` release execution | Product | Deployment execution (`D7`: plans only) | Everything else in `FR-P6`, `FR-P8`, `FR-P9` |

## 4. CP1 — Notary, completed

**Exit:** a disagreement between two provenance tools is reported, never silently resolved (`AC-60`), within one session (`NFR-53`); Meridian's attributions export to formats other tools consume without stranding them (`FR-M52-04`); screen 10.54 shows records, notarisation status and disagreements.

| Task | What | Requirement | Status |
|---|---|---|---|
| `CP1-T01` | Recognise `refs/notes/exceeds-ink` as `exceeds-ink`, in core and in the vendor vocabulary | `FR-M52-01` correction | Not started |
| `CP1-T02` | Commit-level disagreement: every positive claim on a commit — Meridian's own ledger observation through its `Meridian-Ledger` trailer, its span classification, each foreign note or trailer that names an agent — compared, and two claims naming different agents reported side by side with no winner. Optionally recorded in the signed ledger as digests | `FR-M52-05`, `AC-60`, `NFR-53` | Not started |
| `CP1-T03` | Export: Meridian's attributions as JSON git notes under its own ref, and a line-level three-state attribution export in a documented schema. No compatibility with a named third party's schema is claimed that has not been verified | `FR-M52-04` | Not started |
| `CP1-T04` | Screen 10.54 Provenance Reconciliation: records, notarisation state, disagreements, export | `M52`, §9.1 | Not started |

*Limit stated in advance.* Other tools' records are commit-level unless their format carries line spans, and none in the vocabulary is specified in this repository. Disagreement is therefore reported per commit; a disagreement confined to some lines of a commit is reported as a disagreement about the commit.

## 5. Tracking

Each task, when done, records here: the commit, the tests added and the red demonstration, the claims bound, and anything found. A track's status changes only on a sequential green suite.
