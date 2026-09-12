# Claims inventory

**Every capability this product asserts in text a customer reads, bound to the test that makes it true.**

Created by `MV0-T03`. Enforced by `scripts/check-claims.mjs`, which fails the build on a row naming a test that does not exist.

Why this exists: the freeze audit found a requirements document asserting a green suite that was not green, and a README asserting two project directories that were not there. Neither was caught by a test, because neither was bound to one. `MP5` — *the claim ships with the control* — is the rule; this table is the mechanism.

## How to read a row

| Column | Meaning |
|---|---|
| **Claim** | The assertion, in the words a reader encounters |
| **Where** | The shipped text it appears in |
| **Backing test** | `path::name` for Python, `path > name` for vitest. **Must resolve**: the file exists and contains that name |
| **Disposition** | `backed` · `limitation` · `withdrawn` |

**`backed`** — a capability claim with a test that fails if the claim stops being true.
**`limitation`** — a disclosure, not a capability claim. It needs to be *true*, not *tested*; a test asserting we still cannot do something is theatre. `docs/SECURITY-AND-DATA.md` §6 is the model.
**`withdrawn`** — asserted once, found false, removed from the text. Recorded so the removal is visible rather than silent.

**A capability claim with no test is not allowed to ship.** It gets a test or it comes out of the text — `MV0-T03` closes the general form of the defect behind `MVP-R3.3`.

---

## The record

| Claim | Where | Backing test | Disposition |
|---|---|---|---|
| It contains no AI model and makes no model calls | `docs/SECURITY-AND-DATA.md` §1 | `core/tests/test_no_model_calls.py::test_meridian_core_package_is_clean` | backed |
| The zero-model-call guarantee is enforced across every module, not sampled | `docs/SECURITY-AND-DATA.md` §1 | `core/tests/test_no_model_calls.py::test_every_module_is_reachable_and_scanned` | backed |
| The guard detects a real violation rather than passing vacuously | `docs/SECURITY-AND-DATA.md` §1 | `core/tests/test_no_model_calls.py::test_violation_detected` | backed |
| The Flight Recorder tier makes zero model calls | `README.md` · `DEMO.md` | `extension/test/no-model-calls.test.ts` | backed |
| No `MERIDIAN_*` environment variable is inherited by any process the sidecar starts | `docs/SECURITY-AND-DATA.md` §3 | `core/tests/test_childenv.py::test_meridian_variables_never_cross` | backed |
| Scrubbing removes the secrets without emptying the child's environment | `docs/SECURITY-AND-DATA.md` §3 | `core/tests/test_childenv.py::test_scrubbing_is_not_emptying` | backed |
| A secret cannot be smuggled back in through the extra-values path | `docs/SECURITY-AND-DATA.md` §3 | `core/tests/test_childenv.py::test_extra_cannot_smuggle_a_secret_back_in` | backed |
| Credentials are never placed in process arguments; the service refuses credential-shaped arguments | `docs/SECURITY-AND-DATA.md` §3 · `DEMO.md` | `extension/test/workbench.test.ts > rejects invalid manifests and unsafe IDs without changing the saved state` | backed |
| An export verifies without Meridian installed | `docs/SECURITY-AND-DATA.md` §5 · `DEMO.md` §9 | `core/tests/test_headless_cli.py::test_export_then_verify` | backed |
| A bundle exported beforehand still verifies after Meridian is removed | `docs/SECURITY-AND-DATA.md` §8 | `core/tests/test_headless_cli.py::test_an_exported_bundle_still_verifies_after_uninstalling` | backed |
| Tamper with a field of the exported JSON and the verifier fails and names it | `DEMO.md` §9 | `core/tests/test_headless_cli.py::test_verify_rejects_a_tampered_bundle` | backed |
| Export refuses rather than producing an unsigned bundle when no key is available | `docs/SECURITY-AND-DATA.md` §5 | `core/tests/test_headless_cli.py::test_export_without_a_key_refuses_and_says_why` | backed |
| Uninstall tells you what it will delete before deleting anything | `docs/SECURITY-AND-DATA.md` §8 | `core/tests/test_headless_cli.py::test_uninstall_deletes_nothing_without_being_told_twice` | backed |
| The `Meridian-Ledger:` trailer is a published, versioned specification | `docs/SECURITY-AND-DATA.md` §5 | `core/tests/test_trailer_spec.py::test_the_document_exists_and_is_versioned` | backed |
| A reference parser ships inside the package | `docs/SECURITY-AND-DATA.md` §5 | `core/tests/test_trailer_spec.py::test_the_reference_parser_ships_inside_the_extension` | backed |
| A third party can go from `git log` to verified evidence with nothing installed | `docs/SECURITY-AND-DATA.md` §5 | `core/tests/test_trailer_spec.py::test_it_needs_nothing_installed` | backed |
| The open verifier ships inside the VSIX | `README.md` · `docs/SECURITY-AND-DATA.md` §5 | `extension/test/manifest.test.ts > stages the open verifier into the VSIX (FR-M36-06 / SEC-29)` | backed |
| A digest is published beside the artefact as `.vsix.sha256` | `docs/SECURITY-AND-DATA.md` §7 | `extension/test/manifest.test.ts > publishes a checksum, because the security document says it does` | backed |
| The documents an organisation reviews before installing ship in the package | `docs/DEPLOYMENT.md` §1 | `extension/test/manifest.test.ts > stages the documents an organisation reviews before installing` | backed |
| The shipped library is in the package, so a new workspace seeds | `README.md` · `docs/DEPLOYMENT.md` | `extension/test/manifest.test.ts > does not exclude the shipped library from the package` | backed |
| The library ships once, not twice | *(package integrity)* | `extension/test/manifest.test.ts > has no forbidden path tracked in git, not merely absent from this checkout` | backed |
| The extension declares granular activation events and never `*` | `docs/SECURITY-AND-DATA.md` §2 | `extension/test/manifest.test.ts > declares granular activation events and never "*" (FR-M1-01)` | backed |
| Six named themes plus follow-VS-Code | `README.md` | `webview/src/theme/theme.test.ts > ships exactly the six named themes plus follow-vscode (§5)` | backed |
| Governor and Orchestra are refused until enabled; a disabled tier is absent | `README.md` · `docs/DEPLOYMENT.md` §5 | `extension/test/tiers-e2e.test.ts` | backed |
| Every figure carries its coverage envelope and survives a round trip | `docs/DEPLOYMENT.md` | `core/tests/test_coverage_envelope.py::test_envelope_survives_json_round_trip` | backed |
| No runtime dependency is copyleft; all are Apache-2.0, MIT, BSD or ISC, with fonts SIL OFL-1.1 | `docs/SECURITY-AND-DATA.md` §7 | `scripts/check-licences.mjs` | backed |
| The evidence bundle maps to the `ISO/IEC 24970` AI-system-logging information model | evidence bundle · `docs/SECURITY-AND-DATA.md` §5 | `core/tests/test_compliance_mapping.py::test_the_new_instruments_appear` | backed |
| Every compliance mapping states what it is **not** — evidence with a scope, never a certification, and no presumption of conformity | evidence bundle | `core/tests/test_compliance_mapping.py::test_the_section_says_what_it_is_not` | backed |
| The bundle states the retention available against the AI Act Article 26 six-month deployer obligation | evidence bundle | `core/tests/test_compliance_mapping.py::test_it_states_the_obligation_and_the_margin` | backed |
| A retention target below the obligation reports a negative margin rather than a clamped zero | evidence bundle | `core/tests/test_compliance_mapping.py::test_a_target_below_the_floor_reports_a_negative_margin` | backed |
| An agent-attributed element cannot render without its vendor tag | interface, every surface | `webview/src/workbench/banned-patterns.test.ts > AgentToken cannot be constructed without a vendor` | backed |
| A tier that is off is absent, not disabled — no Orchestra surface renders below Orchestra | interface, every surface | `webview/src/workbench/banned-patterns.test.ts > the base tier registers no governor or orchestra surface` | backed |
| Every control on a governance surface declares where it binds | interface · Gate Room · Cross-Vendor Spend | `webview/src/workbench/governance/enforcement-surfaces.test.tsx > never presents something as enforced without naming the boundary` | backed |
| A forged trailer gains nothing from being forged, and can never reach `direct` | `docs/SECURITY-AND-DATA.md` §6 | `core/tests/test_forged_signals.py::test_a_fabricated_trailer_gains_nothing_from_being_fabricated` | backed |
| The published platform support table is generated from a source every row of which names a passing test | `docs/DEPLOYMENT.md` | `scripts/check-compatibility.mjs` | backed |
| **Without a witness, a re-signed fork of the whole ledger still verifies** | `docs/SECURITY-AND-DATA.md` §6 | — | limitation |
| **The commit trailer is editable; it is a pointer, not a proof** | `docs/SECURITY-AND-DATA.md` §6 | — | limitation |
| **Enforcement is in the editor, not the SCM** | `docs/SECURITY-AND-DATA.md` §6 | — | limitation |
| **Identity is asserted, not verified, by default** | `docs/SECURITY-AND-DATA.md` §6 | — | limitation |
| **Effectiveness is unmeasured; no productivity, quality or ROI claim is made** | `docs/SECURITY-AND-DATA.md` §6 | — | limitation |
| **The package is unsigned; the digest proves transit, not authorship** | `docs/SECURITY-AND-DATA.md` §7 | — | limitation |
| **Flight Recorder observes; it does not protect the working tree** | `docs/DEPLOYMENT.md` §10 | — | limitation |
| ~~`adapters/` — prebuilt agent roster, each a full adapter folder~~ | `README.md` project directories | — | withdrawn |
| ~~`sdk/` — `meridian-adapter`: protocol, scaffold, local harness, conformance suite~~ | `README.md` project directories | — | withdrawn |

---

## Withdrawn claims, and why

Recorded rather than deleted, so a reader can see what stopped being true (`§19.3` of `mvp-req-final.md` — the freeze does not freeze the truth).

| Claim | Found | Disposition |
|---|---|---|
| `adapters/` — prebuilt agent roster | `MV0-T03`, 12 Sept 2026. **The directory does not exist.** The 22 shipped agents live in `extension/library/agents/`, seeded into a workspace on first open | Removed from `README.md`. The capability is real; the path was stale from the pre-ACP architecture (`FR-M34-02` re-based adapters on ACP) |
| `sdk/` — `meridian-adapter` package | `MV0-T03`, 12 Sept 2026. **The directory exists and is empty.** `FR-M31-11` (SDK conformance suite) is superseded by ACP conformance per `gaps_implementation.md` §19 | Removed from `README.md`. Listing an empty directory as a project component is a claim with nothing behind it |

## Claims deliberately not in this table

- **The specification documents themselves.** `mvp-req-final.md` and its sixteen sources describe what is intended; they are not shipped to a customer and are not claims about what the software does today. §4 of the requirements carries the measured baseline and is re-measured, not tested.
- **Performance figures quoted in `README.md`** (chain verification ~3 s per 100k). `futures.md` `N0-T03` requires this to be restated against a measured figure on named reference hardware or withdrawn. It is tracked there, not here, and does not appear in `docs/SECURITY-AND-DATA.md` or `docs/DEPLOYMENT.md` — the two documents a buyer actually reviews.
- **Anything in `§16` of the requirements** — the competitive review. `NFR-54` re-verifies it per release and `§18` forbids it becoming marketing material.
