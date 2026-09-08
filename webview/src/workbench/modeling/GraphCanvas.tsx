import { useId, useRef, useState } from 'react';
import type { DiagramModel, ModelNode } from './model';
import s from './modeling.module.css';

export function GraphCanvas({ model, selected, onSelect, onChange, highlighted, routing = 'curved' }: {
  model: DiagramModel; selected: string | null; onSelect: (id: string) => void;
  onChange?: (model: DiagramModel) => void; highlighted?: Set<string>; routing?: 'curved' | 'orthogonal';
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const svg = useRef<SVGSVGElement>(null);
  const marker = useId().replace(/:/g, '');
  const drag = useRef<{ id?: string; clientX: number; clientY: number; x: number; y: number }>();
  const moveNode = (node: ModelNode, x: number, y: number) => onChange?.({ ...model, nodes: model.nodes.map(item => item.id === node.id ? { ...item, x: Math.max(-9000, Math.min(9000, x)), y: Math.max(-9000, Math.min(9000, y)) } : item) });
  function frame() {
    if (!model.nodes.length) return;
    const minX = Math.min(...model.nodes.map(node=>node.x)); const minY = Math.min(...model.nodes.map(node=>node.y));
    const width = Math.max(...model.nodes.map(node=>node.x + 190)) - minX; const height = Math.max(...model.nodes.map(node=>node.y + (model.type === 'Sequence' ? 320 : 100))) - minY;
    const scale = Math.max(.15, Math.min(1.5, 730 / width, 400 / height));
    setZoom(scale); setPan({x:35-minX*scale,y:25-minY*scale});
  }
  return <div className={s.canvasWrap}>
    <svg ref={svg} className={s.canvas} viewBox="0 0 800 450" role="group" aria-label={`${model.type} diagram. Select a node to inspect it. Use the list below for a text equivalent.`}
      onPointerDown={event=>{ if (event.target !== svg.current) return; event.currentTarget.setPointerCapture(event.pointerId); drag.current={clientX:event.clientX,clientY:event.clientY,x:pan.x,y:pan.y}; }}
      onPointerMove={event=>{ if(!drag.current) return; const current=drag.current; const scale=800/(svg.current?.getBoundingClientRect().width || 800); const dx=(event.clientX-current.clientX)*scale; const dy=(event.clientY-current.clientY)*scale; if(current.id){const node=model.nodes.find(item=>item.id===current.id); if(node)moveNode(node,current.x+dx/zoom,current.y+dy/zoom);}else setPan({x:current.x+dx,y:current.y+dy}); }}
      onPointerUp={()=>{drag.current=undefined;}} onPointerCancel={()=>{drag.current=undefined;}}>
      <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="var(--ml-text-tertiary)" /></marker></defs>
      <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
        {model.type === 'Sequence' && model.nodes.map(node=><line key={`life-${node.id}`} x1={node.x+90} x2={node.x+90} y1={node.y+80} y2={node.y+320} className={s.edge} strokeDasharray="4 4"/>)}
        {model.edges.map((edge,index)=>{const from=model.nodes.find(node=>node.id===edge.from);const to=model.nodes.find(node=>node.id===edge.to);if(!from||!to)return null;const sequence=model.type==='Sequence';const x1=from.x+(sequence?90:180), y1=sequence?from.y+120+index*38:from.y+40, x2=to.x+(sequence?90:0),y2=sequence?y1:to.y+40; const d=sequence?`M${x1} ${y1} L${x2} ${y2}`:routing==='orthogonal'?`M${x1} ${y1} H${(x1+x2)/2} V${y2} H${x2}`:`M${x1} ${y1} C${x1+70} ${y1}, ${x2-70} ${y2}, ${x2} ${y2}`; return <g key={edge.id} opacity={highlighted?.size && (!highlighted.has(edge.from)||!highlighted.has(edge.to))?.2:1}><path d={d} className={s.edge} data-kind={edge.kind} markerEnd={`url(#${marker})`}/><text x={(x1+x2)/2} y={(y1+y2)/2-8} textAnchor="middle" className={s.edgeLabel}>{edge.label.slice(0,40)}</text></g>;})}
        {model.nodes.map(node=><g key={node.id} className={s.node} role="button" tabIndex={0} aria-label={`${node.label}, ${node.kind}${node.coverage ? `, coverage ${node.coverage}` : ''}`} data-selected={selected===node.id} data-coverage={node.coverage} opacity={highlighted?.size&&!highlighted.has(node.id)?.25:1} transform={`translate(${node.x} ${node.y})`}
          onClick={()=>onSelect(node.id)} onPointerDown={event=>{event.stopPropagation(); onSelect(node.id); if(onChange){svg.current?.setPointerCapture(event.pointerId); drag.current={id:node.id,clientX:event.clientX,clientY:event.clientY,x:node.x,y:node.y};}}}
          onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(node.id);} if(onChange&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const step=event.shiftKey?40:10;moveNode(node,node.x+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0),node.y+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0));}}}>
          <title>{node.label}{node.detail?` — ${node.detail}`:''}</title>
          {node.kind==='decision'?<polygon points="90,-10 190,40 90,90 -10,40"/>:<rect width="180" height="80" rx={node.kind==='state'?32:12}/>}
          <text x="12" y="26">{node.label.length>24?`${node.label.slice(0,23)}…`:node.label}</text><text className={s.kind} x="12" y="47">{node.kind.slice(0,25)}</text>
          {node.owner&&<text className={s.kind} x="12" y="65">{node.owner.slice(0,25)}</text>}
          {(model.type==='Class'||model.type==='Entity relationship')&&<line x1="0" x2="180" y1="32" y2="32" className={s.edge}/>}
        </g>)}
      </g>
    </svg>
    <div className={s.canvasFooter}><span>{model.nodes.length} nodes · {model.edges.length} relationships · Drag background to pan</span><div className={s.toolbar}><button className={s.button} aria-label="Zoom out" onClick={()=>setZoom(value=>Math.max(.15,value-.15))}>−</button><span aria-live="polite">{Math.round(zoom*100)}%</span><button className={s.button} aria-label="Zoom in" onClick={()=>setZoom(value=>Math.min(3,value+.15))}>+</button><button className={s.button} onClick={frame}>Fit diagram</button><button className={s.button} onClick={()=>{setZoom(1);setPan({x:0,y:0});}}>Reset view</button></div></div>
  </div>;
}
