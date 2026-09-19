export interface ModelNode {
  id: string;
  label: string;
  kind: string;
  detail: string;
  x: number;
  y: number;
  source?: string;
  owner?: string;
  level?: string;
  coverage?: 'unknown' | 'covered' | 'gap';
}
export interface ModelEdge { id: string; from: string; to: string; label: string; kind: 'relation' | 'rework' | 'contract' }
export interface DiagramModel { schemaVersion: 1; type: string; nodes: ModelNode[]; edges: ModelEdge[]; notes: string }
export const DIAGRAM_TYPES = {
  architecture: ['System context', 'Container', 'Component', 'Threat model'],
  uml: ['Sequence', 'Class', 'Entity relationship', 'Component', 'State machine', 'Activity', 'Deployment'],
  flow: ['Acceptance flow', 'Data flow', 'Delivery pipeline', 'Escalation'],
  loop: ['Six canonical loops'],
} as const;
export type DiagramKind = keyof typeof DIAGRAM_TYPES;
export function template(type: string): DiagramModel {
  const labels: Record<string, string[]> = {
    'System context': ['Person', 'Your system', 'External system'],
    Container: ['Web application', 'Application service', 'Data store'],
    Component: ['Interface', 'Domain service', 'Repository'],
    'Threat model': ['External actor', 'Trust boundary', 'Protected service'],
    Sequence: ['Caller', 'Service', 'Store'],
    Class: ['Entity', 'Service', 'Repository'],
    'Entity relationship': ['Account', 'Order', 'Order item'],
    'State machine': ['Draft', 'In review', 'Approved'],
    Activity: ['Request', 'Process', 'Review'],
    Deployment: ['Client', 'Application host', 'Database host'],
    'Acceptance flow': ['Given precondition', 'When action', 'Then outcome'],
    'Data flow': ['Source', 'Transformation', 'Destination'],
    'Delivery pipeline': ['Build', 'Verify', 'Human release approval'],
    Escalation: ['Bound reached', 'Pause work', 'Human decision'],
    'Six canonical loops': ['L1 · Micro', 'L2 · Task', 'L3 · Phase', 'L4 · Delivery', 'L5 · Learning', 'L6 · Organisation'],
  };
  const nodes = (labels[type] ?? ['Start', 'Work', 'Finish']).map((label, index) => ({
    id: `node-${index + 1}`, label, kind: type === 'Class' ? 'class' : type === 'Entity relationship' ? 'entity' : type === 'Sequence' ? 'participant' : 'component',
    detail: '', x: 40 + (index % 3) * 240, y: 60 + Math.floor(index / 3) * 160, coverage: 'unknown' as const,
  }));
  return { schemaVersion: 1, type, nodes, edges: nodes.slice(1).map((node, index) => ({ id: `edge-${index + 1}`, from: nodes[index].id, to: node.id, label: type === 'Sequence' ? 'Message' : 'relates to', kind: 'relation' as const })), notes: 'Authored model. Replace template labels and attach source evidence before review.' };
}
export function parseModel(body: string): DiagramModel {
  const value = JSON.parse(body) as Partial<DiagramModel>;
  if (value.schemaVersion !== 1 || typeof value.type !== 'string' || !Array.isArray(value.nodes) || !Array.isArray(value.edges) || value.nodes.length > 300 || value.edges.length > 1200) throw new Error('Use a version 1 diagram with up to 300 nodes and 1,200 relationships.');
  const ids = new Set<string>();
  for (const node of value.nodes) {
    if (!node || typeof node.id !== 'string' || !node.id || ids.has(node.id) || typeof node.label !== 'string' || typeof node.kind !== 'string' || typeof node.detail !== 'string' || !Number.isFinite(node.x) || !Number.isFinite(node.y) || Math.abs(node.x) > 10000 || Math.abs(node.y) > 10000) throw new Error('Every node needs a unique ID, label, kind, detail, and valid coordinates.');
    for (const key of ['source', 'owner', 'level'] as const) if (node[key] !== undefined && typeof node[key] !== 'string') throw new Error(`Invalid node ${key}.`);
    if (node.coverage !== undefined && !['unknown', 'covered', 'gap'].includes(node.coverage)) throw new Error('Invalid coverage state.');
    ids.add(node.id);
  }
  const edges = new Set<string>();
  for (const edge of value.edges) {
    if (!edge || typeof edge.id !== 'string' || edges.has(edge.id) || !ids.has(edge.from) || !ids.has(edge.to) || typeof edge.label !== 'string' || !['relation', 'rework', 'contract'].includes(edge.kind)) throw new Error('Relationships must have unique IDs and reference existing nodes.');
    edges.add(edge.id);
  }
  if (value.notes !== undefined && typeof value.notes !== 'string') throw new Error('Model notes must be text.');
  // Copy an explicit schema. Unknown properties never enter rendered markup.
  return { schemaVersion: 1, type: value.type, notes: value.notes ?? '', nodes: value.nodes.map(({id,label,kind,detail,x,y,source,owner,level,coverage})=>({id,label,kind,detail,x,y,source,owner,level,coverage})), edges: value.edges.map(({id,from,to,label,kind})=>({id,from,to,label,kind})) };
}
export function layoutModel(model: DiagramModel, layout: 'grid' | 'circle' | 'vertical'): DiagramModel {
  return { ...model, nodes: model.nodes.map((node, index) => ({ ...node,
    x: layout === 'circle' ? 400 + Math.cos(index / model.nodes.length * Math.PI * 2) * 300 : layout === 'vertical' ? 220 : 40 + index % 3 * 240,
    y: layout === 'circle' ? 330 + Math.sin(index / model.nodes.length * Math.PI * 2) * 260 : layout === 'vertical' ? 40 + index * 150 : 60 + Math.floor(index / 3) * 160,
  })) };
}
export function tracePath(model: DiagramModel, from: string, to: string): Set<string> {
  const queue = [[from]]; const visited = new Set([from]);
  while (queue.length) {
    const current = queue.shift()!; const tail = current.at(-1)!;
    if (tail === to) return new Set(current);
    for (const edge of model.edges) if (edge.from === tail && !visited.has(edge.to)) { visited.add(edge.to); queue.push([...current, edge.to]); }
  }
  return new Set();
}
const xml = (text: string) => text.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[character]!);
/** Only escaped schema text enters exports; imported markup is never used. */
export function svgExport(model: DiagramModel): string {
  const minX = Math.min(0, ...model.nodes.map(node => node.x - 30));
  const minY = Math.min(0, ...model.nodes.map(node => node.y - 40));
  const width = Math.max(800, ...model.nodes.map(node => node.x + 230)) - minX;
  const height = Math.max(450, ...model.nodes.map(node => node.y + 160)) - minY;
  const edges = model.edges.map(edge => { const a = model.nodes.find(node=>node.id===edge.from)!; const b = model.nodes.find(node=>node.id===edge.to)!; return `<path d="M${a.x + 90},${a.y + 40} L${b.x + 90},${b.y + 40}" fill="none" stroke="#626875"/><text x="${(a.x + b.x) / 2 + 90}" y="${(a.y + b.y) / 2 + 30}" font-size="11" fill="#464b56">${xml(edge.label)}</text>`; }).join('');
  const nodes = model.nodes.map(node=>`<g><rect x="${node.x}" y="${node.y}" width="180" height="80" rx="12" fill="#f2f4f7" stroke="#505866"/><text x="${node.x + 12}" y="${node.y + 26}" font-family="sans-serif" font-size="13" fill="#151923">${xml(node.label.slice(0, 25))}</text><text x="${node.x + 12}" y="${node.y + 50}" font-family="sans-serif" font-size="11" fill="#464b56">${xml(node.kind)}</text></g>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX} ${minY} ${width} ${height}" role="img"><title>${xml(model.type)}</title><rect x="${minX}" y="${minY}" width="${width}" height="${height}" fill="#ffffff"/>${edges}${nodes}</svg>`;
}
export function mermaidExport(model: DiagramModel): string {
  const clean = (text: string) => text.replace(/["\n\r<>`]/g, ' ').replace(/\[/g, '(').replace(/\]/g, ')');
  const ids = new Map(model.nodes.map((node,index)=>[node.id, `n${index}`]));
  if (model.type === 'Sequence') return ['sequenceDiagram', ...model.nodes.map(node => `  participant ${ids.get(node.id)} as ${clean(node.label)}`), ...model.edges.map(edge=>`  ${ids.get(edge.from)}->>${ids.get(edge.to)}: ${clean(edge.label)}`)].join('\n');
  return ['flowchart LR', ...model.nodes.map(node=>`  ${ids.get(node.id)}["${clean(node.label)}"]`), ...model.edges.map(edge=>`  ${ids.get(edge.from)} -->|"${clean(edge.label)}"| ${ids.get(edge.to)}`)].join('\n');
}
