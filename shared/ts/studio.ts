/** Workspace-authored design and planning documents. These are not execution verdicts. */
export const STUDIO_DOCUMENT_KINDS = [
  'specification', 'story', 'portfolio', 'skill', 'instruction', 'connector',
  'routing', 'report', 'architecture', 'uml', 'flow', 'loop', 'comprehension',
  'steering', 'configuration', 'verification', 'security', 'pipeline',
] as const;
export type StudioDocumentKind = typeof STUDIO_DOCUMENT_KINDS[number];
export interface StudioDocument {
  id: string;
  kind: StudioDocumentKind;
  title: string;
  body: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  version: number;
}
export interface StudioDocumentInput {
  id?: string;
  kind: StudioDocumentKind;
  title: string;
  body: string;
  tags: string[];
  /** Optimistic concurrency: updating a document requires its current version. */
  expectedVersion?: number;
}
