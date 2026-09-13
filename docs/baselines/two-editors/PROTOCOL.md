# Two editors, two SCM providers, one evidence shape — protocol

`MV5`, `MVP-R5.4` (`AC-50`, `FR-M43-15`).

> One customer SHALL reproduce the same signed change evidence from two supported
> editors and two SCM providers with no Orchestra tier installed, and SHALL verify
> both bundles with the open verifier on a clean machine. This SHALL be performed
> **before** any external material makes the vendor-independence claim.

## Precondition: two *supported* editors

**This cannot be performed today.** `shared/schema/compatibility.json` claims one
editor, VS Code at API level 1.95. Running the protocol with an editor the
matrix does not claim would prove something about an unsupported configuration,
and `MK5` forbids counting it.

Before this runs, a second editor must be **claimed in the matrix, with a smoke
test that passes on it** (`MV4-T01`'s runner). Until then, this protocol can be
rehearsed but not passed. No external material may claim vendor independence
across editors or SCM providers in the meantime (`FR-M43-15`).

## Who

One pilot customer, their repository and two SCM providers they actually use.
Record the customer by role, never by name.

## Steps

1. **Install** Meridian Loom with the Flight Recorder and Governor tiers. **No
   Orchestra tier.**
2. **Editor one, SCM one.** Work the change, record it, merge it through the
   first provider's pull request, then export:

   ```console
   python -m meridian_core.cli export --workspace <workspace> \
       --out bundle-editor1-scm1.json --signing-key-file ledger.key
   ```

3. **Editor two, SCM two.** Work **the same change** from the same starting
   commit, merge it through the second provider, and export
   `bundle-editor2-scm2.json`.
4. **Verify on a clean machine** that has never had Meridian installed. Copy both
   bundles and `verify.py`, the one file shipped inside the VSIX at
   `extension/sidecar/verify.py` using only the Python standard library:

   ```console
   python verify.py bundle-editor1-scm1.json
   python verify.py bundle-editor2-scm2.json
   ```

   Both must print `OK`. Keep the output.
5. **Compare the evidence shape.** This step reads JSON and proves nothing about
   the machine, so run it wherever Meridian's CLI is available:

   ```console
   python -m meridian_core.cli compare-evidence \
       bundle-editor1-scm1.json bundle-editor2-scm2.json
   ```

   Exit 0 means both verified and the shapes agree: the same format and schema
   versions, the same sections, the same entry fields with compatible types,
   and the same redaction, enforcement and compliance structure. Any
   difference is listed. Values (timestamps, keys, vendors, who approved) are
   expected to differ and are not compared.

## Pass condition

- Both bundles print `OK` from `verify.py` on the clean machine.
- `compare-evidence` exits 0.
- Both editors are claimed in the compatibility matrix with passing smoke tests.

## Where the result goes

`docs/baselines/two-editors/<date>-<customer-role>.md`, containing:

- both bundles' sha256 digests;
- the verifier output from the clean machine, and that machine's operating
  system;
- the `compare-evidence` output;
- the editors and versions, and the SCM providers.

Then update `MVP-R5.4` in `mvp-req-final.md` and `MV5` in `mvp-impl-plan.md`.
