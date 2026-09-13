# Assistive journeys — protocol

`MV4-T07`, `MVP-R6.5`, `FR-M46-05`.

`webview/src/screens/assistive-journeys.test.tsx` checks what a machine can
check honestly: every control on these journeys is a real control with an
accessible name, the preflight is a dialog, cancel precedes confirm, and
refusals are announced. It cannot tell you whether a person can **finish** the
journey. jsdom has no accessibility tree and no real focus model, and a test
passing there is a precondition, not a result.

This protocol is the result half. It needs a person and a real screen reader.

## Configurations

Run every journey in **both** modes:

| Mode | Setup |
| --- | --- |
| Keyboard only | Mouse unplugged or disabled. No trackpad. |
| Screen reader | NVDA (Windows) or VoiceOver (macOS), with the screen visible or not — record which. Keyboard only. |

Record the OS, VS Code version, screen reader and version, and the package
digest.

## The three journeys

Each starts with VS Code open on a git repository and the Governor tier enabled.

### 1. Launch

Open the workbench → Runs → Launch. Enter an intent, run preflight, read the
four answers and where it stops, then **cancel**. Run preflight again and
**confirm** a dry run. Read who authorised it.

### 2. Review

Evidence → Pull request. Enter a pull request subject, load it, and read out
the action required and the revision actually tested.

### 3. Export

Evidence → Audit ledger → Other tools' records → **Check for alteration**. Then
export an evidence bundle and save it.

## What counts as a critical barrier

Any of these ends the journey as **failed**:

- a control that cannot be reached by Tab, or can be reached and not activated;
- focus lost — it moves somewhere invisible, or back to the top of the page,
  after an action;
- a control announced only by its role ("button") with no name;
- a decision the person must make — confirm, cancel, the stale-head warning,
  an alteration — that is shown but not announced;
- a keyboard trap.

Anything else that slows the person down is recorded as a **non-critical
finding**, not a failure.

## Recording sheet

One per journey per mode — six in total.

| Field | Value |
| --- | --- |
| Journey | Launch / Review / Export |
| Mode | Keyboard only / Screen reader |
| Completed | yes / no |
| Critical barriers | (each: where, what happened) |
| Non-critical findings | |
| Alerts announced that should not have been (false alerts) | count, and each one's text |
| Alerts dismissed, and why | |
| Time to complete | |

The plan asks for **the measured false-alert rate and dismissal reasons**, so
the last three rows are not optional.

## Where the result goes

`docs/baselines/assistive/<date>-<os>-<screen-reader>.md`, all six sheets. Any
critical barrier is fixed, and the journey re-run, before `MVP-R6.5` can move
to `BUILT`.
