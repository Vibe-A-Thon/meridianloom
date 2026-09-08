/** Development-only UI fixture. Imported behind import.meta.env.DEV and
 * excluded from production bundles. It never starts a process or changes a repo. */
import type { HostMessage } from '../../../shared/ts/webview-messages';
import { WEBVIEW_PROTOCOL_VERSION } from '../../../shared/ts/webview-messages';
import type { WorkbenchAgentInput, WorkbenchSnapshot } from '../../../shared/ts/workbench';
import type { RpcTransport } from '../rpc/client';
import type { StudioDocument, StudioDocumentInput } from '../../../shared/ts/studio';

export function createPreviewTransport(): RpcTransport {
  let previewState: unknown;
  (window as { acquireVsCodeApi?: unknown }).acquireVsCodeApi = () => ({
    getState: () => previewState,
    setState: (value: unknown) => { previewState = value; return value; },
    postMessage: (message: { type?: string; content?: string; mimeType?: string; fileName?: string }) => {
      if (message.type !== 'download' || typeof message.content !== 'string') return;
      const url = URL.createObjectURL(new Blob([message.content], { type: message.mimeType ?? 'text/plain' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = message.fileName ?? 'meridian-export.txt';
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  const now = new Date().toISOString();
  const agents = [
    [
      'atlas',
      'Atlas',
      'Architecture & systems',
      'Maps the bigger picture. Turns complex requirements into thoughtful, maintainable systems.',
      'active',
    ],
    [
      'nova',
      'Nova',
      'Full-stack development',
      'Connects the details. Builds considered interfaces and the services that make them work.',
      'active',
    ],
    [
      'sentinel',
      'Sentinel',
      'Quality & code review',
      'Asks the difficult questions. Reviews changes, explores edge cases, and protects quality.',
      'active',
    ],
    [
      'sage',
      'Sage',
      'Research & documentation',
      'Makes knowledge useful. Learns from delivery feedback and keeps the next handoff clear.',
      'learning',
    ],
    [
      'echo',
      'Echo',
      'Testing & accessibility',
      'Looks for the missing perspective. Builds better checks from the lessons of completed work.',
      'learning',
    ],
    [
      'quill',
      'Quill',
      'Developer experience',
      'Sweats the small things. Helps every tool, instruction, and workflow feel easier to use.',
      'learning',
    ],
  ];
  let state: WorkbenchSnapshot = {
    revision: 1,
    documents: [],
    documentRevisions: [],
    agents: agents.map(([id, name, role, description, mode]) => ({
      id,
      name,
      role,
      description,
      mode: mode as 'active' | 'learning',
      vendor: 'Custom ACP',
      version: '1.0.0',
      command: 'your-acp-agent',
      args: ['--stdio'],
      instructions: 'Stay within the requested scope. Explain changes and verification.',
      permissions: ['read', 'search', 'think'],
      trainable: ['memory'],
      runtime: 'idle',
      learningState: id === 'sage' ? 'review' : 'waiting',
      createdAt: now,
      updatedAt: now,
    })),
    deliverables: [
      {
        id: 'checkout-001',
        title: 'A more accessible checkout',
        brief:
          'Make the checkout work beautifully with a keyboard and screen reader.\n\nAcceptance criteria\n• Every control has an accessible name.\n• Focus returns to the trigger after a dialog closes.\n• Error messages describe how to recover.',
        state: 'review',
        agentIds: ['atlas', 'nova', 'sentinel'],
        createdAt: now,
        updatedAt: now,
      },
      {
        id: 'search-002',
        title: 'Thoughtful search, everywhere',
        brief:
          'Bring fast, contextual search to the workspace. Keep the results useful and the interaction predictable.',
        state: 'draft',
        agentIds: [],
        createdAt: now,
        updatedAt: now,
      },
      {
        id: 'tokens-003',
        title: 'One shared design language',
        brief:
          'Unify the product around reusable design tokens. Verify light, dark, and high contrast themes.',
        state: 'completed',
        agentIds: ['nova', 'sentinel'],
        createdAt: now,
        updatedAt: now,
        feedback:
          'Use semantic tokens. Test both keyboard navigation and screen reader announcements.',
      },
    ],
    runs: [
      {
        id: 'preview-run',
        agentId: 'sentinel',
        agentName: 'Sentinel',
        deliverableId: 'checkout-001',
        prompt: 'Review the checkout keyboard interactions.',
        state: 'completed',
        startedAt: now,
        finishedAt: now,
        stopReason: 'end_turn',
        output:
          'PREVIEW FIXTURE — no code was executed.\n\nThis sample result illustrates where agent output and verification notes appear.',
      },
    ],
    learning: [
      {
        id: 'preview-note',
        agentId: 'sage',
        deliverableId: 'tokens-003',
        title: 'Review: One shared design language',
        content:
          'PREVIEW FIXTURE\n\nSource: the completed design-language deliverable.\n\nHuman feedback: Use semantic tokens and test keyboard navigation.\n\nProposed memory: Include a token and accessibility checklist in future handoff documentation.',
        state: 'pending',
        createdAt: now,
        surface: 'memory',
      },
    ],
    capabilities: {
      workspaceOpen: true,
      trusted: false,
      governorEnabled: false,
      executionReady: false,
      executionBlockedReason:
        'Preview mode does not execute agents. Open Meridian in VS Code with a trusted workspace and Governor enabled to run real tasks.',
    },
  };
  let receive: ((message: HostMessage) => void) | undefined;
  const rpc: Record<string, unknown> = {
    'observe/sessions': { sessions: [], warnings: [] },
    'ledger.query': { entries: [] },
    'observe/health': { monitorRunning: false, observers: [] },
    health: { status: 'degraded', uptimeSeconds: 0, pid: 0, activeLoops: 0 },
    'doctor/run': {
      status: 'warn',
      checks: [
        {
          id: 'preview',
          name: 'Development preview',
          status: 'warn',
          detail: 'The preview has no extension host or sidecar.',
          remediation: 'Launch the extension in VS Code for actual diagnostics.',
        },
      ],
    },
  };
  return {
    onMessage(handler) {
      receive = handler;
      return () => {
        receive = undefined;
      };
    },
    postMessage(message) {
      queueMicrotask(() => {
        if (message.type === 'ready') {
          receive?.({
            type: 'init',
            init: {
              protocolVersion: WEBVIEW_PROTOCOL_VERSION,
              enabledTiers: ['flight-recorder'],
              workspaceDir: '/workspace/meridian-studio',
            },
          });
          return;
        }
        if (message.type === 'rpc/request') {
          if (message.method in rpc)
            receive?.({ type: 'rpc/response', id: message.id, result: rpc[message.method] });
          else
            receive?.({
              type: 'rpc/response',
              id: message.id,
              error: {
                code: -32001,
                message: 'This operation needs the real VS Code extension host.',
              },
            });
          return;
        }
        if (message.type !== 'workbench/request') return;
        try {
          const params = (message.params ?? {}) as Record<string, unknown>;
          let result: unknown;
          const agent = () => {
            const found = state.agents.find((a) => a.id === params.id);
            if (!found) throw new Error('Agent not found.');
            return found;
          };
          switch (message.action) {
            case 'document/save': {
              const input = params.document as StudioDocumentInput;
              const old = state.documents!.find(d => d.id === input.id);
              if (old && old.version !== input.expectedVersion) throw new Error('Document changed. Refresh before saving.');
              if (old) state.documentRevisions!.push(structuredClone(old));
              const next: StudioDocument = { ...input, id: old?.id ?? crypto.randomUUID(), version: (old?.version ?? 0) + 1, createdAt: old?.createdAt ?? now, updatedAt: new Date().toISOString() };
              if (old) state.documents![state.documents!.indexOf(old)] = next; else state.documents!.unshift(next);
              break;
            }
            case 'document/remove': {
              const old = state.documents!.find(d => d.id === params.id);
              if (!old || old.version !== params.expectedVersion) throw new Error('Document changed. Refresh before removing.');
              state.documents = state.documents!.filter(d => d.id !== params.id);
              state.documentRevisions = state.documentRevisions!.filter(d => d.id !== params.id);
              break;
            }
            case 'document/export': {
              const document = state.documents!.find(d => d.id === params.id);
              if (!document) throw new Error('Document not found.');
              result = { fileName: `${document.kind}-${document.id}.meridian-document.json`, content: JSON.stringify({ kind: 'meridian-studio-document', schemaVersion: 1, document }, null, 2) };
              break;
            }
            case 'document/import': {
              const portable = JSON.parse(String(params.content));
              if (portable.kind !== 'meridian-studio-document' || portable.schemaVersion !== 1) throw new Error('Expected a Meridian studio document.');
              state.documents!.unshift({ ...portable.document, id: crypto.randomUUID(), version: 1, createdAt: now, updatedAt: now });
              break;
            }
            case 'document/restore': {
              const old = state.documents!.find(d => d.id === params.id);
              const revision = state.documentRevisions!.find(d => d.id === params.id && d.version === params.version);
              if (!old || !revision || old.version !== params.expectedVersion) throw new Error('Revision unavailable or document changed.');
              state.documentRevisions!.push(structuredClone(old));
              state.documents![state.documents!.indexOf(old)] = { ...revision, version: old.version + 1, updatedAt: new Date().toISOString() };
              break;
            }
            case 'snapshot':
              break;
            case 'agent/save': {
              const input = params.agent as WorkbenchAgentInput;
              const existing = state.agents.find((a) => a.id === input.id);
              if (existing) Object.assign(existing, input);
              else
                state.agents.push({
                  ...input,
                  mode: 'learning',
                  runtime: 'idle',
                  learningState: 'waiting',
                  createdAt: now,
                  updatedAt: now,
                });
              break;
            }
            case 'agent/remove':
              state.agents = state.agents.filter((a) => a.id !== params.id);
              state.learning = state.learning.filter((note) => note.agentId !== params.id);
              break;
            case 'agent/mode':
              agent().mode = params.mode as 'active' | 'learning';
              break;
            case 'agent/export':
              result = {
                fileName: `${agent().id}.meridian-agent.json`,
                content: JSON.stringify(
                  { kind: 'meridian-portable-agent', schemaVersion: 1, agent: agent() },
                  null,
                  2,
                ),
              };
              break;
            case 'agent/import': {
              const document = JSON.parse(String(params.content));
              if (
                document.kind !== 'meridian-portable-agent' ||
                !document.agent?.id ||
                state.agents.some((a) => a.id === document.agent.id)
              )
                throw new Error('Use a portable agent document with a unique ID.');
              state.agents.push({
                ...document.agent,
                mode: 'learning',
                runtime: 'idle',
                learningState: 'waiting',
                createdAt: now,
                updatedAt: now,
              });
              break;
            }
            case 'deliverable/save': {
              const item = state.deliverables.find((d) => d.id === params.id);
              if (item) Object.assign(item, params);
              else
                state.deliverables.unshift({
                  id: crypto.randomUUID(),
                  title: String(params.title),
                  brief: String(params.brief),
                  state: 'draft',
                  agentIds: [],
                  createdAt: now,
                  updatedAt: now,
                });
              break;
            }
            case 'learning/review': {
              const note = state.learning.find((n) => n.id === params.id);
              if (!note) throw new Error('Note not found.');
              note.state = params.decision as 'accepted' | 'dismissed';
              break;
            }
            case 'deliverable/complete': {
              const item = state.deliverables.find((d) => d.id === params.id);
              if (!item || item.state !== 'review')
                throw new Error('The sample deliverable is not ready for review.');
              item.state = 'completed';
              item.feedback = String(params.feedback);
              for (const learner of state.agents.filter(
                (a) => a.mode === 'learning' && a.trainable.includes('memory'),
              ))
                state.learning.push({
                  id: crypto.randomUUID(),
                  agentId: learner.id,
                  deliverableId: item.id,
                  title: `Review: ${item.title}`,
                  content: `PREVIEW FEEDBACK\n\n${item.feedback}`,
                  state: 'pending',
                  createdAt: now,
                  surface: 'memory',
                });
              break;
            }
            default:
              throw new Error(
                'Preview mode does not execute agents. Use the extension for real work.',
              );
          }
          if (message.action !== 'snapshot') state.revision++;
          state.agents.forEach((a) => {
            a.learningState = state.learning.some(
              (n) => n.agentId === a.id && n.state === 'pending',
            )
              ? 'review'
              : 'waiting';
          });
          receive?.({
            type: 'rpc/response',
            id: message.id,
            result: structuredClone(result ?? state),
          });
        } catch (error) {
          receive?.({
            type: 'rpc/response',
            id: message.id,
            error: { code: -32602, message: (error as Error).message },
          });
        }
      });
    },
  };
}
