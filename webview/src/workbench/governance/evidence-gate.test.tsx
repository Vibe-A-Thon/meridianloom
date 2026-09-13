import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { WorkbenchExecute, WorkbenchSnapshot } from '../../../../shared/ts/workbench';
import { WebviewRpcClient } from '../../rpc/client';
import { makeHost } from '../../test/host-harness';
import { EvidenceGate } from './EvidenceGate';
import type { GovernanceProps } from './common';

/**
 * The evidence gate screen keeps the shape of the preregistered answer: an
 * unmeasured threshold never reads as met, an unrecognised verdict never reads
 * as GO, and a broken preregistration is an alert.
 */

const IDS = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'C1', 'C2', 'C3', 'O1'];

type Measure = { id: string; status: string; value: unknown; threshold: { measure: string }; source: string; note: string };

function gateReport(overrides: {
  measures?: Record<string, Partial<Measure>>;
  verdict?: string;
  preregistration?: Record<string, unknown>;
  stories?: Record<string, unknown>;
} = {}) {
  const measures: Record<string, Measure> = {};
  for (const id of IDS) {
    measures[id] = { id, status: 'unmeasured', value: null, threshold: { measure: `${id} measure` }, source: 'study record', note: `${id} note`, ...(overrides.measures?.[id] ?? {}) };
  }
  return {
    preregistration: { state: 'not_registered', invalidated: false, thresholdsDigest: `sha256:${'a'.repeat(64)}`, ...(overrides.preregistration ?? {}) },
    stories: { total: 0, required: 20, byArm: { A: 0, B: 0, C: 0 }, ...(overrides.stories ?? {}) },
    measures,
    recommendation: { verdict: overrides.verdict ?? 'insufficient_evidence', reasons: ['no study record.'], invalidated: overrides.preregistration?.invalidated === true },
  };
}

async function renderGate(report: unknown) {
  const host = makeHost({ 'evidence/gate': report });
  const snapshot: WorkbenchSnapshot = { revision: 1, agents: [], skills: [], instructions: [], integrations: [], deliverables: [], runs: [], learning: [], documents: [], capabilities: { workspaceOpen: true, trusted: true, governorEnabled: true, executionReady: true } };
  const props: GovernanceProps = { client: new WebviewRpcClient(host.transport), ready: true, enabledTiers: ['flight-recorder', 'governor'], workspaceDir: '/workspace', onNavigate: vi.fn(), controller: { snapshot, busy: false, error: null, execute: vi.fn(async () => snapshot) as WorkbenchExecute, refresh: async () => {} } };
  render(<EvidenceGate {...props} />);
  await host.settle();
  return host;
}

describe('the evidence gate screen', () => {
  it('spells out an unmeasured threshold and never shows it as met', async () => {
    await renderGate(gateReport());
    expect(screen.getAllByText('Unmeasured — never counted as met')).toHaveLength(10);
    expect(screen.queryByText('Met')).toBeNull();
    expect(screen.getAllByText('Not evidenced')).toHaveLength(10);
    expect(screen.getByText('Not yet decidable')).toBeInTheDocument();
  });

  it('distinguishes met, not met and unmeasured', async () => {
    await renderGate(gateReport({ measures: { P1: { status: 'met', value: 3 }, C1: { status: 'not_met', value: 0.25 } } }));
    expect(screen.getByText('Met')).toBeInTheDocument();
    expect(screen.getByText('Not met')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('0.250')).toBeInTheDocument();
    expect(screen.getAllByText('Unmeasured — never counted as met')).toHaveLength(8);
  });

  it('reads a status it does not recognise as unmeasured', async () => {
    await renderGate(gateReport({ measures: { P4: { status: 'probably_fine', value: 1 } } }));
    expect(screen.getAllByText('Unmeasured — never counted as met')).toHaveLength(10);
  });

  it('never shows GO for a verdict it does not recognise', async () => {
    await renderGate(gateReport({ verdict: 'build-everything' }));
    expect(screen.getByText('Not yet decidable')).toBeInTheDocument();
    expect(screen.queryByText('GO')).toBeNull();
  });

  it('announces a preregistration that is not intact as an alert', async () => {
    await renderGate(gateReport({ preregistration: { state: 'digest_mismatch', invalidated: true } }));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('not intact');
    expect(alert).toHaveTextContent('invalidated');
  });

  it('reports a combination no outcome names, instead of rounding it', async () => {
    await renderGate(gateReport({ verdict: 'unclassified' }));
    expect(screen.getByText('No outcome applies')).toBeInTheDocument();
  });

  it('draws STOP as a success', async () => {
    await renderGate(gateReport({ verdict: 'stop' }));
    expect(screen.getByText(/This is a success, not a failure/)).toBeInTheDocument();
  });

  it('counts the stories as the study allocated them', async () => {
    await renderGate(gateReport({ stories: { total: 20, byArm: { A: 6, B: 7, C: 7 } } }));
    expect(screen.getByText('20 / 20')).toBeInTheDocument();
    expect(screen.getByText('6 · 7')).toBeInTheDocument();
  });
});
