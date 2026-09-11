---
kind: instruction
id: definition-of-done
name: Definition of Done
description: What has to be true before work is reported as finished.
scope: workspace
---

# Definition of Done

Work is done when all of these are true. Not most.

1. **It does what was asked**, including the parts that were tedious.
2. **It builds**, from clean, the way CI builds it.
3. **The tests pass, and you ran them.** Not "should pass". A test run you did
   not observe is not a result.
4. **New behaviour has a test that fails without the change.** If you could
   not make it fail against the old code, the test is not testing the change.
5. **The failure paths are handled**, or it is stated that they are not and
   why that is acceptable.
6. **Nothing is half-migrated.** Every call site updated, or none.
7. **The diff reads as intentional** to someone who was not involved.
8. **What is not covered is stated.** Known gaps, skipped checks, assumptions
   that were not verified.

## Reporting

State completion plainly when it is true. When it is not, say which of the
above is missing rather than describing the work as done with caveats
attached at the end.
