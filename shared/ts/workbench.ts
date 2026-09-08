/** Extension-host workbench state. This channel does not require the Python sidecar. */
export type AgentMode = 'active' | 'learning';
export type AgentPermission =
  | 'read'
  | 'edit'
  | 'delete'
  | 'move'
  | 'execute'
  | 'search'
  | 'think'
  | 'unknown'
  | 'other';
export type LearningSurface = 'policy' | 'rules' | 'memory' | 'skills' | 'calibration';

export interface WorkbenchAgentInput {
  id: string;
  name: string;
  role: string;
  description: string;
  vendor: string;
  version: string;
  command: string;
  args: string[];
  instructions: string;
  permissions: AgentPermission[];
  trainable: LearningSurface[];
}

export interface WorkbenchAgent extends WorkbenchAgentInput {
  mode: AgentMode;
  runtime: 'idle' | 'running';
  learningState: 'waiting' | 'review';
  createdAt: string;
  updatedAt: string;
  lastRunAt?: string;
}

export interface WorkbenchRun {
  id: string;
  agentId: string;
  agentName: string;
  deliverableId?: string;
  prompt: string;
  state: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  startedAt: string;
  finishedAt?: string;
  stopReason?: string;
  error?: string;
  output?: string;
}

export interface WorkbenchDeliverable {
  id: string;
  title: string;
  brief: string;
  state: 'draft' | 'running' | 'review' | 'completed' | 'failed';
  agentIds: string[];
  createdAt: string;
  updatedAt: string;
  feedback?: string;
}

export interface LearningArtifact {
  id: string;
  agentId: string;
  deliverableId: string;
  title: string;
  content: string;
  state: 'pending' | 'accepted' | 'dismissed';
  createdAt: string;
  reviewedAt?: string;
  /** These are reviewable memory notes, never model-weight training. */
  surface: 'memory';
}

export interface WorkbenchSnapshot {
  revision: number;
  agents: WorkbenchAgent[];
  deliverables: WorkbenchDeliverable[];
  runs: WorkbenchRun[];
  learning: LearningArtifact[];
  capabilities: {
    workspaceOpen: boolean;
    trusted: boolean;
    governorEnabled: boolean;
    executionReady: boolean;
    executionBlockedReason?: string;
  };
}

/** Portable declared launch configuration; credentials and run history are excluded. */
export interface PortableAgentDocument {
  kind: 'meridian-portable-agent';
  schemaVersion: 1;
  agent: WorkbenchAgentInput;
  memory?: { title: string; content: string }[];
}

export interface WorkbenchActionMap {
  snapshot: { params: Record<string, never>; result: WorkbenchSnapshot };
  'agent/save': { params: { agent: WorkbenchAgentInput }; result: WorkbenchSnapshot };
  'agent/remove': { params: { id: string }; result: WorkbenchSnapshot };
  'agent/mode': { params: { id: string; mode: AgentMode }; result: WorkbenchSnapshot };
  'agent/import': { params: { content: string }; result: WorkbenchSnapshot };
  'agent/export': { params: { id: string }; result: { fileName: string; content: string } };
  'agent/run': { params: { id: string; prompt: string }; result: WorkbenchSnapshot };
  'run/cancel': { params: { id: string }; result: WorkbenchSnapshot };
  'deliverable/save': {
    params: { id?: string; title: string; brief: string };
    result: WorkbenchSnapshot;
  };
  'deliverable/dispatch': { params: { id: string }; result: WorkbenchSnapshot };
  'deliverable/complete': { params: { id: string; feedback: string }; result: WorkbenchSnapshot };
  'learning/review': {
    params: { id: string; decision: 'accepted' | 'dismissed' };
    result: WorkbenchSnapshot;
  };
}

export type WorkbenchAction = keyof WorkbenchActionMap;
export interface WorkbenchRequest {
  action: WorkbenchAction;
  params?: unknown;
}
export type WorkbenchExecute = <A extends WorkbenchAction>(
  action: A,
  params: WorkbenchActionMap[A]['params'],
) => Promise<WorkbenchActionMap[A]['result']>;
