import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AttribDiffResult, LedgerEntry } from '../../../../shared/ts/bus-types';
import type { WorkbenchExecute, WorkbenchSnapshot } from '../../../../shared/ts/workbench';
import type { WebviewRpcClient } from '../../rpc/client';
import { ModelingStudio } from './ModelingStudio';
import { attributionModel } from './CodeMapStudio';
import { layoutModel, mermaidExport, parseModel, svgExport, template, tracePath } from './model';
import type { ModelingStudioProps, ModelingView } from './types';

function harness(view:ModelingView, responses:Record<string,unknown>={}){
  const snapshot:WorkbenchSnapshot={revision:1,agents:[],deliverables:[],runs:[],learning:[],documents:[],capabilities:{workspaceOpen:true,trusted:true,governorEnabled:true,executionReady:true}};
  const execute=vi.fn(async(action:string,params:{document?:{id?:string;kind:string;title:string;body:string;tags:string[];expectedVersion?:number}})=>{
    if(action==='document/save'&&params.document){const input=params.document; return {...snapshot,documents:[{...input,id:input.id??'saved-1',version:(input.expectedVersion??0)+1,createdAt:'2026-09-08T10:00:00Z',updatedAt:'2026-09-08T10:00:00Z'}]};}return snapshot;
  });
  const request=vi.fn(async(method:string)=>{const response=responses[method];if(response instanceof Error)throw response;return response;});
  const notify=vi.fn();
  const props:ModelingStudioProps={view,client:{request,notify} as unknown as WebviewRpcClient,ready:true,workspaceDir:'C:/repo',enabledTiers:['flight-recorder'],controller:{snapshot,execute:execute as WorkbenchExecute,busy:false,error:null,refresh:async()=>{}},onNavigate:vi.fn()};
  return {props,execute,request,notify};
}

describe('Diagram schema and exports',()=>{
  it('rejects duplicate IDs, dangling relationships, unknown coordinate values, and oversized graphs',()=>{
    const model=template('Class');
    expect(()=>parseModel(JSON.stringify({...model,nodes:[model.nodes[0],model.nodes[0]]}))).toThrow('unique ID');
    expect(()=>parseModel(JSON.stringify({...model,edges:[{...model.edges[0],to:'missing'}]}))).toThrow('existing nodes');
    expect(()=>parseModel(JSON.stringify({...model,nodes:[{...model.nodes[0],x:'20'}]}))).toThrow('coordinates');
    expect(()=>parseModel(JSON.stringify({...model,nodes:Array.from({length:301},(_,index)=>({...model.nodes[0],id:String(index)}))}))).toThrow('300 nodes');
  });
  it('escapes hostile labels in SVG and never exports unknown imported markup',()=>{
    const model=template('Class'); model.nodes[0].label='<script>alert("x")</script>'; const parsed=parseModel(JSON.stringify({...model,html:'<script>bad</script>'}));const svg=svgExport(parsed);
    expect(svg).not.toContain('<script>');expect(svg).toContain('&lt;script&gt;');expect(parsed).not.toHaveProperty('html');
    model.nodes[0].label='Thing\nclick n0 "https://example.com"';expect(mermaidExport(model).split('\n').some(line=>line.trim().startsWith('click '))).toBe(false);
  });
  it('traces directed paths and preserves data while arranging nodes',()=>{
    const model=template('System context');expect([...tracePath(model,'node-1','node-3')]).toEqual(['node-1','node-2','node-3']);expect(tracePath(model,'node-3','node-1').size).toBe(0);
    const arranged=layoutModel(model,'vertical');expect(arranged.edges).toEqual(model.edges);expect(arranged.nodes[1].x).toBe(arranged.nodes[0].x);expect(arranged.nodes[1].y).toBeGreaterThan(arranged.nodes[0].y);
  });
});

describe('Modeling documents',()=>{
  it('edits, persists and subsequently updates a source-linked architecture node with version checks',async()=>{
    const h=harness('architecture');render(<ModelingStudio {...h.props}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect Your system'}));
    fireEvent.change(screen.getByLabelText('Node label'),{target:{value:'Checkout service'}});
    fireEvent.change(screen.getByLabelText('Source path or ADR'),{target:{value:'src/checkout.ts'}});
    fireEvent.change(screen.getByLabelText('Model title'),{target:{value:'Checkout context'}});
    fireEvent.click(screen.getByRole('button',{name:'Save model'}));
    await waitFor(()=>expect(h.execute).toHaveBeenCalledTimes(1));
    const saved=h.execute.mock.calls[0][1].document!;expect(saved.kind).toBe('architecture');expect(JSON.parse(saved.body).nodes[1]).toMatchObject({label:'Checkout service',source:'src/checkout.ts'});
    await screen.findByText('Model saved to this workspace.');
    fireEvent.change(screen.getByLabelText('Model notes and review context'),{target:{value:'ADR #7 reviewed.'}});
    fireEvent.click(screen.getByRole('button',{name:'Save model'}));await waitFor(()=>expect(h.execute).toHaveBeenCalledTimes(2));expect(h.execute.mock.calls[1][1].document).toMatchObject({id:'saved-1',expectedVersion:1});
  });
  it('removes incident edges when deleting a node and exposes an accessible alternative',()=>{
    const h=harness('flows');render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Inspect When action'}));fireEvent.click(screen.getByRole('button',{name:'Remove node and its relationships'}));
    expect(screen.queryByRole('button',{name:'Inspect When action'})).not.toBeInTheDocument();expect(screen.getByText(/2 nodes · 0 relationships/)).toBeInTheDocument();
  });
  it('refuses invalid diagram imports without replacing the authored model',()=>{
    const h=harness('uml');render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Import JSON'}));fireEvent.change(screen.getByLabelText('Diagram JSON'),{target:{value:'{"schemaVersion":1,"type":"Class","nodes":[],"edges":[{"from":"missing"}]}'}});fireEvent.click(screen.getByRole('button',{name:'Import model'}));expect(screen.getByRole('dialog')).toBeInTheDocument();expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent('existing nodes');expect(h.execute).not.toHaveBeenCalled();
  });
  it('exports escaped vector content through the host download channel',()=>{
    const h=harness('uml');render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Export SVG'}));expect(h.notify).toHaveBeenCalledWith(expect.objectContaining({type:'download',mimeType:'image/svg+xml',content:expect.stringContaining('<svg')}));
  });
  it('keeps loop planning explicitly separate from unavailable execution',()=>{
    const h=harness('loops');render(<ModelingStudio {...h.props}/>);expect(screen.getByText(/Loop runtime endpoints are not implemented/)).toBeInTheDocument();expect(screen.getByRole('button',{name:'Inspect L6 · Organisation'})).toBeInTheDocument();expect(h.request).not.toHaveBeenCalled();
  });
});

describe('Repository evidence surfaces',()=>{
  it('builds only factual directory membership from blame and looks up the selected current symbol',async()=>{
    const blame={repoPath:'C:/repo',ref:'HEAD',lines:[{path:'src/service.ts',line:1,commit:'abc123',authorName:'Alex',authorEmail:'a@example.com',authorTime:'2026-09-08T10:00:00Z',content:'export function checkout() {}'}]};
    const map=attributionModel(blame,'files','');expect(map.edges).toEqual([expect.objectContaining({from:'folder:src',to:'file:src/service.ts',label:'contains'})]);
    const h=harness('codemap',{'attrib/blame':blame,'attrib/symbol':{path:'src/service.ts',line:1,language:'typescript',symbol:'checkout'}});render(<ModelingStudio {...h.props}/>);fireEvent.change(screen.getByLabelText('Source paths'),{target:{value:'src/service.ts'}});fireEvent.click(screen.getByRole('button',{name:'Load repository map'}));await screen.findByRole('button',{name:'Inspect src/service.ts'});expect(h.request).toHaveBeenCalledWith('attrib/blame',{repoPath:'C:/repo',ref:'HEAD',paths:['src/service.ts']});fireEvent.click(screen.getByRole('button',{name:'Inspect src/service.ts'}));fireEvent.click(screen.getByRole('button',{name:'Inspect current symbol'}));await screen.findByText('checkout');expect(h.request).toHaveBeenCalledWith('attrib/symbol',{repoPath:'C:/repo',path:'src/service.ts',line:1});
  });
  it('captures hunk rework with a reason as a document, without applying source edits',async()=>{
    const diff:AttribDiffResult={repoPath:'C:/repo',base:'HEAD',compare:null,staged:false,files:[{path:'src/a.ts',oldPath:null,status:'modified',hunks:[{oldStart:1,oldCount:1,newStart:1,newCount:1,lines:[{kind:'removed',oldLine:1,newLine:null,content:'const value = 1;'},{kind:'added',oldLine:null,newLine:1,content:'const value = 2;'}]}]}]};
    const h=harness('diff',{'attrib/diff':diff});render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Load changes'}));await screen.findByText('src/a.ts');fireEvent.click(screen.getByRole('button',{name:'Request rework for hunk 1'}));fireEvent.change(screen.getByLabelText('Reason (required)'),{target:{value:'The acceptance criterion requires one.'}});fireEvent.change(screen.getByLabelText('Prompt, test, and ledger references'),{target:{value:'Ledger #42; tests/a.test.ts'}});fireEvent.click(screen.getByRole('button',{name:'Record review decision'}));fireEvent.click(screen.getByRole('button',{name:'Save review'}));await waitFor(()=>expect(h.execute).toHaveBeenCalledTimes(1));const body=JSON.parse(h.execute.mock.calls[0][1].document!.body);expect(body.hunks['src/a.ts:0']).toMatchObject({state:'rework',reason:'The acceptance criterion requires one.',evidence:'Ledger #42; tests/a.test.ts'});expect(h.request).toHaveBeenCalledTimes(1);
  });
  it('scrubs real ledger sequences, loads payloads, and verifies the selected prefix',async()=>{
    const make=(sequence:number)=>({sequence,timestamp:'2026-09-08T10:00:00Z',storyId:'s1',phase:'review',loopId:'l1',loopIteration:1,actorId:'agent-a',actorVersion:'1',actorKind:'role',policyVersion:'1',actionType:'review',vendor:'Custom',observationConfidence:'hosted',simulated:false,entryHash:'abcdef',previousHash:'123456',hasInputBlob:true,hasOutputBlob:true}) satisfies LedgerEntry;
    const h=harness('replay',{'ledger.query':{entries:[make(10),make(12)]},'ledger.getEntry':{...make(12),inputAvailable:true,outputAvailable:false,input:'Review the boundary.'},'ledger.verify':{ok:true,entriesChecked:12,firstDivergentSequence:null,detail:'Valid prefix',verifiedAt:'now'}});render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Load timeline'}));await screen.findByRole('slider',{name:'Recorded event'});fireEvent.change(screen.getByRole('slider'),{target:{value:'1'}});fireEvent.click(screen.getByRole('button',{name:'Inspect recorded payloads'}));await screen.findByText('Review the boundary.');expect(h.request).toHaveBeenCalledWith('ledger.getEntry',{sequence:12});fireEvent.click(screen.getByRole('button',{name:'Verify chain to this event'}));await screen.findByText('Chain verified');expect(h.request).toHaveBeenCalledWith('ledger.verify',{upTo:12});
  });
  it('requires cited evidence before saving a reviewed comprehension note',async()=>{
    const h=harness('comprehension');render(<ModelingStudio {...h.props}/>);fireEvent.change(screen.getByLabelText('Handover title'),{target:{value:'Checkout invariants'}});fireEvent.change(screen.getByLabelText('Purpose and behavior'),{target:{value:'Idempotent charging.'}});fireEvent.change(screen.getByLabelText('Human review state'),{target:{value:'reviewed'}});fireEvent.click(screen.getByRole('button',{name:'Save handover'}));await screen.findByText('A reviewed note needs explicit evidence references.');expect(h.execute).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('Evidence references'),{target:{value:'src/checkout.ts @ abc123; tests/checkout.test.ts'}});fireEvent.click(screen.getByRole('button',{name:'Save handover'}));await waitFor(()=>expect(h.execute).toHaveBeenCalledTimes(1));expect(JSON.parse(h.execute.mock.calls[0][1].document!.body)).toMatchObject({review:'reviewed',purpose:'Idempotent charging.'});
  });
  it('surfaces attribution failures instead of drawing an invented map',async()=>{
    const h=harness('codemap',{'attrib/blame':new Error('Reference does not exist')});render(<ModelingStudio {...h.props}/>);fireEvent.click(screen.getByRole('button',{name:'Load repository map'}));expect(await screen.findByRole('alert')).toHaveTextContent('Reference does not exist');expect(screen.queryByRole('group',{name:/Repository attribution map/})).not.toBeInTheDocument();
  });
});
