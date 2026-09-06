/**
 * Probation state machine (FR-M31-07, FR-M15-03/04/05): every adapter —
 * prebuilt, custom, registry-installed — enters through probation at the
 * `suggest` autonomy tier. Graduation requires a passing probation result
 * (a failing agent is NOT admitted). Suspension is reasoned and resumable;
 * removal (unplug) deletes the record — no scar.
 */
import { describe, expect, it } from 'vitest';
import { ProbationTracker, type ProbationRecord } from '../src/adapters/probation';

describe('probation state machine (FR-M31-07, FR-M15-03/04/05)', () => {
  it('admission always lands in probation at the suggest autonomy tier', () => {
    const tracker = new ProbationTracker();
    const record = tracker.admit('acme-dev');
    expect(record.state).toBe('probation');
    expect(record.autonomyTier).toBe('suggest');
    expect(tracker.stateOf('acme-dev')).toBe('probation');
  });

  it('a passing probation result graduates to active (still suggest)', () => {
    const tracker = new ProbationTracker();
    tracker.admit('acme-dev');
    const record = tracker.graduate('acme-dev', { passed: true, score: 0.92 });
    expect(record.state).toBe('active');
    expect(record.autonomyTier).toBe('suggest'); // FR-M15-05
    expect(record.probationScore).toBe(0.92);
  });

  it('a failing probation result does NOT admit the agent', () => {
    const tracker = new ProbationTracker();
    tracker.admit('acme-dev');
    const record = tracker.graduate('acme-dev', { passed: false, score: 0.4 });
    expect(record.state).toBe('probation');
    expect(tracker.stateOf('acme-dev')).toBe('probation');
  });

  it('a pre-recorded probation result is re-verified on admission (FR-M31-07)', () => {
    const tracker = new ProbationTracker();
    const record = tracker.admit('prebuilt-dev', {
      preRecorded: { passed: true, score: 0.9 },
    });
    // The pre-recorded result is evidence, not a shortcut: the adapter still
    // enters probation and a human/re-verification decides graduation.
    expect(record.state).toBe('probation');
    expect(record.preRecorded).toEqual({ passed: true, score: 0.9 });
  });

  it('suspension records a reason and is allowed from probation or active', () => {
    const tracker = new ProbationTracker();
    tracker.admit('acme-dev');
    expect(tracker.suspend('acme-dev', 'policy violation: undeclared tool use').state).toBe('suspended');
    expect(tracker.recordOf('acme-dev')?.suspensionReason).toBe('policy violation: undeclared tool use');

    const other = new ProbationTracker();
    other.admit('active-dev');
    other.graduate('active-dev', { passed: true, score: 1 });
    expect(other.suspend('active-dev', 'budget ceiling hit').state).toBe('suspended');
  });

  it('resume returns a suspended adapter to probation for re-verification', () => {
    const tracker = new ProbationTracker();
    tracker.admit('acme-dev');
    tracker.graduate('acme-dev', { passed: true, score: 0.9 });
    tracker.suspend('acme-dev', 'reason');
    const record = tracker.resume('acme-dev');
    expect(record.state).toBe('probation');
    expect(record.suspensionReason).toBeUndefined();
  });

  it('unplug (remove) deletes the record entirely — no scar', () => {
    const tracker = new ProbationTracker();
    tracker.admit('gone');
    tracker.suspend('gone', 'whatever');
    tracker.remove('gone');
    expect(tracker.stateOf('gone')).toBeUndefined();
    expect(tracker.recordOf('gone')).toBeUndefined();
  });

  it('unknown ids surface a clear error instead of a silent no-op', () => {
    const tracker = new ProbationTracker();
    expect(() => tracker.graduate('nope', { passed: true })).toThrow(/nope/);
    expect(() => tracker.suspend('nope', 'x')).toThrow(/nope/);
    expect(() => tracker.resume('nope')).toThrow(/nope/);
  });

  it('emits transitions for observers (UI, ledger hooks)', () => {
    const tracker = new ProbationTracker();
    const seen: ProbationRecord[] = [];
    tracker.on('transition', (record: ProbationRecord) => seen.push(record));
    tracker.admit('emit-dev');
    tracker.graduate('emit-dev', { passed: true, score: 0.8 });
    tracker.suspend('emit-dev', 'r');
    expect(seen.map((r) => r.state)).toEqual(['probation', 'active', 'suspended']);
    expect(seen.every((r) => r.id === 'emit-dev')).toBe(true);
  });
});
