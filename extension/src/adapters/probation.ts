/**
 * Probation state machine (FR-M31-07, FR-M15-03/04/05): every adapter —
 * prebuilt, custom, bridged or registry-installed — enters through
 * probation at the `suggest` autonomy tier, no exceptions. Graduation
 * requires a passing probation result; a failing agent is NOT admitted
 * (FR-M15-04). Admitted adapters still enter at `suggest` (FR-M15-05).
 * Suspension is reasoned; resume returns to probation for re-verification.
 * Removal (unplug, FR-M31-04) deletes the record entirely — no scar.
 *
 * State is session-scoped: the durable record of what an adapter learned
 * is its `learned/` folder (FR-M31-12, D18 handles persistence).
 */
import { EventEmitter } from 'node:events';
import type { AutonomyTier } from './manifest';

export type AdapterState = 'probation' | 'active' | 'suspended';

export interface ProbationResult {
  passed: boolean;
  /** Fraction of the probation task set answered correctly (0..1). */
  score?: number;
}

export interface ProbationRecord {
  id: string;
  state: AdapterState;
  /** The autonomy tier the adapter operates at in this state. */
  autonomyTier: AutonomyTier;
  probationScore?: number;
  suspensionReason?: string;
  /** FR-M31-07: a shipped pre-recorded result, re-verified before admission. */
  preRecorded?: ProbationResult;
}

export class ProbationTracker extends EventEmitter {
  private readonly records = new Map<string, ProbationRecord>();

  /** Admission is always probation at `suggest` — no manifest can skip it. */
  admit(id: string, options?: { preRecorded?: ProbationResult }): ProbationRecord {
    const record: ProbationRecord = {
      id,
      state: 'probation',
      autonomyTier: 'suggest',
      ...(options?.preRecorded ? { preRecorded: options.preRecorded } : {}),
    };
    this.records.set(id, record);
    this.emit('transition', record);
    return { ...record };
  }

  graduate(id: string, result: ProbationResult): ProbationRecord {
    const record = this.mustGet(id, 'graduate');
    if (!result.passed) {
      // FR-M15-04: a failing agent is not admitted; it stays on probation
      // with its score recorded for the human decision.
      const kept: ProbationRecord = { ...record, probationScore: result.score };
      this.records.set(id, kept);
      this.emit('transition', { ...kept });
      return { ...kept };
    }
    // FR-M15-05: admission lands at `suggest` regardless of the score.
    const next: ProbationRecord = {
      ...record,
      state: 'active',
      autonomyTier: 'suggest',
      probationScore: result.score,
      preRecorded: undefined,
    };
    this.records.set(id, next);
    this.emit('transition', { ...next });
    return { ...next };
  }

  suspend(id: string, reason: string): ProbationRecord {
    const record = this.mustGet(id, 'suspend');
    const next: ProbationRecord = { ...record, state: 'suspended', suspensionReason: reason };
    this.records.set(id, next);
    this.emit('transition', { ...next });
    return { ...next };
  }

  resume(id: string): ProbationRecord {
    const record = this.mustGet(id, 'resume');
    if (record.state !== 'suspended') {
      throw new Error(`adapter '${id}' is not suspended (state: ${record.state})`);
    }
    const next: ProbationRecord = {
      ...record,
      state: 'probation',
      autonomyTier: 'suggest',
      suspensionReason: undefined,
    };
    this.records.set(id, next);
    this.emit('transition', { ...next });
    return { ...next };
  }

  /** Unplug: the record is gone entirely (FR-M31-04, G5 — no scar). */
  remove(id: string): void {
    this.records.delete(id);
  }

  stateOf(id: string): AdapterState | undefined {
    return this.records.get(id)?.state;
  }

  recordOf(id: string): ProbationRecord | undefined {
    const record = this.records.get(id);
    return record ? { ...record } : undefined;
  }

  private mustGet(id: string, action: string): ProbationRecord {
    const record = this.records.get(id);
    if (!record) {
      throw new Error(`cannot ${action} adapter '${id}': it has not been admitted`);
    }
    return record;
  }
}
