import { Approvals, Gates } from './Gates';
import { Calibration, Trust } from './Analytics';
import { Pipeline, Security, Verification } from './DeliveryEvidence';
import { Repositories } from './Repositories';
import { EvidenceGate } from './EvidenceGate';
import {
  CompareAgents,
  DoraExport,
  Jcurve,
  ReasonDistribution,
  SpendObservatory,
  Tokenmaxxing,
  TrustScore,
} from './Observatory';
import { Notice, Page, type GovernanceProps } from './common';

export type { GovernanceProps, GovernanceView } from './common';
export function GovernanceStudio({ view, ...props }: GovernanceProps & { view: string }) {
  switch (view) {
    case 'gates': return <Gates {...props} />;
    case 'approvals': return <Approvals {...props} />;
    case 'verification': return <Verification {...props} />;
    case 'security': return <Security {...props} />;
    case 'pipeline': return <Pipeline {...props} />;
    case 'repositories': return <Repositories {...props} />;
    case 'trust': return <Trust {...props} />;
    case 'calibration': return <Calibration {...props} />;
    // N1-T25: the Cross-Vendor Spend panel now consumes spend/series,
    // spend/pricing and spend/forecast rather than recomputing a simpler
    // view from ledger.query with a local 1,000-row truncation guess.
    case 'spend': return <SpendObservatory {...props} />;
    case 'f2-gate': return <EvidenceGate {...props} />;
    case 'trust-score': return <TrustScore {...props} />;
    case 'rejection-reasons': return <ReasonDistribution {...props} />;
    case 'agent-comparison': return <CompareAgents {...props} />;
    case 'jcurve': return <Jcurve {...props} />;
    case 'tokenmaxxing': return <Tokenmaxxing {...props} />;
    case 'dora': return <DoraExport {...props} />;
    case 'spend-observatory': return <SpendObservatory {...props} />;
    default: return <Page title="Governance view unavailable" eyebrow="GOVERNANCE" description="This saved route is not recognized."><Notice>Open a governance view from the workspace navigation.</Notice></Page>;
  }
}
