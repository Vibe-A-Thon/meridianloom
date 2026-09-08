import { Approvals, Gates } from './Gates';
import { Calibration, Spend, Trust } from './Analytics';
import { Pipeline, Security, Verification } from './DeliveryEvidence';
import { Repositories } from './Repositories';
import type { GovernanceProps, GovernanceView } from './common';

export type { GovernanceProps, GovernanceView } from './common';
export function GovernanceStudio({ view, ...props }: GovernanceProps & { view: GovernanceView }) {
  switch (view) {
    case 'gates': return <Gates {...props} />;
    case 'approvals': return <Approvals {...props} />;
    case 'verification': return <Verification {...props} />;
    case 'security': return <Security {...props} />;
    case 'pipeline': return <Pipeline {...props} />;
    case 'repositories': return <Repositories {...props} />;
    case 'trust': return <Trust {...props} />;
    case 'calibration': return <Calibration {...props} />;
    case 'spend': return <Spend {...props} />;
  }
}
