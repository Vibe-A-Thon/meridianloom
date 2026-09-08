import { CodeMapStudio } from './CodeMapStudio';
import { ComprehensionStudio } from './ComprehensionStudio';
import { DiagramStudio } from './DiagramStudio';
import { DiffStudio } from './DiffStudio';
import { ReplayStudio } from './ReplayStudio';
import type { ModelingStudioProps } from './types';
export type { ModelingStudioProps, ModelingView } from './types';
export function ModelingStudio(props:ModelingStudioProps){
  switch(props.view){
    case 'codemap':return <CodeMapStudio {...props}/>;
    case 'comprehension':return <ComprehensionStudio {...props}/>;
    case 'diff':return <DiffStudio {...props}/>;
    case 'replay':return <ReplayStudio {...props}/>;
    case 'architecture':return <DiagramStudio key="architecture" {...props} kind="architecture"/>;
    case 'uml':return <DiagramStudio key="uml" {...props} kind="uml"/>;
    case 'flows':return <DiagramStudio key="flow" {...props} kind="flow"/>;
    case 'loops':return <DiagramStudio key="loop" {...props} kind="loop"/>;
    default:return <div role="alert">This modeling view is not registered.</div>;
  }
}
