/**
 * MCP server exposure of Meridian's governed surfaces (FR-M34-06; F1
 * Workstream A task 6).
 *
 * VS Code's native agent mode standardises on MCP; this module is the
 * minimal, real MCP server that lets any MCP client (native agent mode
 * included) reach Meridian's ledger and gates. The protocol is implemented
 * directly — JSON-RPC 2.0 over newline-delimited stdio, the MCP 2025-03-26
 * surface (initialize, ping, tools/list, tools/call, resources/list,
 * resources/read) — with no protocol dependency beyond Node's streams.
 *
 * Governance is not re-implemented here: every tools/call is forwarded to
 * the sidecar as one `mcp/invoke`, where the governor tier gate is the
 * permission gate (disabled => TIER_DISABLED, mirrored verbatim to the MCP
 * client, G5) and the call is ledger-recorded before it executes. The tool
 * set is exactly the sidecar's read-only governed surfaces:
 *
 *   ledger_query            -> ledger.query
 *   ledger_export_bundle    -> ledger.exportBundle
 *   ledger_verify           -> ledger.verify
 *   trust_rejection_rate    -> trust/rejectionRate
 *
 * Zero model calls (FR-M36-07): this module only frames JSON.
 */

import { createFrameDecoder, encodeFrame } from '../framing';

/** The newest MCP protocol revision this server implements. */
export const MCP_PROTOCOL_VERSION = '2025-03-26';

export const MCP_SERVER_NAME = 'meridian-loom';
export const MCP_SERVER_VERSION = '0.0.1';

// JSON-RPC 2.0 standard error codes (MCP rides on JSON-RPC).
const PARSE_ERROR = -32700;
const INVALID_REQUEST = -32600;
const METHOD_NOT_FOUND = -32601;
const INVALID_PARAMS = -32602;
const INTERNAL_ERROR = -32603;

/** The backend seam: one sidecar connection, two governed entry points. */
export interface McpServerBackend {
  /** Forward one MCP tool call as a sidecar `mcp/invoke`. */
  invoke(tool: string, args: Record<string, unknown>): Promise<unknown>;
  /** The live doctor report behind the meridian://doctor-report resource. */
  doctorRun(): Promise<unknown>;
}

export interface McpToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

const PASSTHROUGH_SCHEMA: Record<string, unknown> = {
  type: 'object',
  additionalProperties: true,
};

/**
 * The governed tool set, in tools/list order. Tool names are MCP-shaped
 * (no slashes); the sidecar's `mcp/invoke` remains the authority for what
 * exists and what each call did.
 */
export const MCP_TOOLS: readonly McpToolDefinition[] = [
  {
    name: 'ledger_query',
    description:
      'Query the open provenance ledger (passthrough of the sidecar ledger.query shape: ' +
      'storyId, actorId, vendor, actionType, sequence/time ranges, limit). Read-only.',
    inputSchema: PASSTHROUGH_SCHEMA,
  },
  {
    name: 'ledger_export_bundle',
    description:
      'Export the signed audit bundle for a sequence/date range, agent or story — ' +
      'entries with hash preimages, Merkle inclusion proofs, an Ed25519 signature over the ' +
      'bundle and the SSDF/ISO 42001/EU AI Act compliance section (passthrough of ' +
      'ledger.exportBundle). Read-only.',
    inputSchema: PASSTHROUGH_SCHEMA,
  },
  {
    name: 'ledger_verify',
    description:
      'Chain integrity verdict for the open ledger: verified through sequence N, or a ' +
      'tamper indication naming the first divergent sequence (passthrough of ledger.verify). ' +
      'Read-only.',
    inputSchema: PASSTHROUGH_SCHEMA,
  },
  {
    name: 'trust_rejection_rate',
    description:
      'Rejection rate per agent and repository, split greenfield/brownfield, derived from ' +
      'the ledger (passthrough of trust/rejectionRate). Read-only; zero model calls.',
    inputSchema: PASSTHROUGH_SCHEMA,
  },
];

const OPEN_LEDGER_SPEC_TEXT = [
  'Meridian Loom — open ledger specification pointer',
  '',
  'The open ledger specification lives in the Meridian Loom repository at',
  'docs/open-ledger-spec/ (a copy is kept alongside the requirement sources',
  'in docs/spec/). It defines the append-only provenance ledger this MCP',
  'server exposes: entry schema, hash chain, Merkle tree heads, Ed25519',
  'signing, the signed bundle format and the open reference verifier.',
  '',
  'Every tool call through this server is itself recorded in the ledger as a',
  'tool_call entry (vendor mcp) before it executes — the specification is',
  'also the audit trail of this surface.',
].join('\n');

interface McpResourceDefinition {
  uri: string;
  name: string;
  description: string;
  mimeType: string;
}

export const MCP_RESOURCES: readonly McpResourceDefinition[] = [
  {
    uri: 'meridian://open-ledger-spec',
    name: 'Open Ledger specification',
    description: 'Where the open ledger specification lives and what it defines.',
    mimeType: 'text/plain',
  },
  {
    uri: 'meridian://doctor-report',
    name: 'Meridian doctor report',
    description:
      'The live self-diagnostic report of the Meridian sidecar serving this workspace ' +
      '(fetched from doctor/run at read time).',
    mimeType: 'application/json',
  },
];

interface JsonRpcRequest {
  jsonrpc?: string;
  id?: number | string;
  method?: string;
  params?: unknown;
}

function errorResponse(
  id: number | string | undefined,
  code: number,
  message: string,
  data?: unknown,
): Record<string, unknown> {
  const error: Record<string, unknown> = { code, message };
  if (data !== undefined) {
    error.data = data;
  }
  return { jsonrpc: '2.0', id: id ?? null, error };
}

/** Backend errors carry the sidecar's structured error (code/data) on them. */
function backendErrorFields(error: unknown): { code: number; message: string; data?: unknown } {
  const structured = error as { code?: number; message?: string; data?: unknown };
  return {
    code: typeof structured?.code === 'number' ? structured.code : INTERNAL_ERROR,
    message: structured?.message ?? String(error),
    ...(structured?.data !== undefined ? { data: structured.data } : {}),
  };
}

/**
 * One MCP server instance bound to one backend. `handleMessage` maps one
 * decoded JSON-RPC message to its response (or null for notifications);
 * `serve` runs the stdio loop until the input stream ends.
 */
export class McpServer {
  constructor(
    private readonly backend: McpServerBackend,
    private readonly options: { serverVersion?: string } = {},
  ) {}

  async handleMessage(message: unknown): Promise<unknown | null> {
    const request = message as JsonRpcRequest;
    if (
      !request ||
      typeof request !== 'object' ||
      request.jsonrpc !== '2.0' ||
      typeof request.method !== 'string'
    ) {
      return errorResponse(
        (request as JsonRpcRequest | null)?.id,
        INVALID_REQUEST,
        'not a well-formed JSON-RPC 2.0 request',
      );
    }
    // Notifications (no id) never produce a response; the MCP lifecycle
    // notification notifications/initialized is the one every client sends.
    const isNotification = request.id === undefined;
    const routed = await this.route(request);
    if (routed === null) {
      return null;
    }
    if (isNotification) {
      return null;
    }
    if ('error' in routed) {
      // route() already shaped a JSON-RPC error; stamp the request id.
      return { jsonrpc: '2.0', id: request.id ?? null, error: routed.error };
    }
    return { jsonrpc: '2.0', id: request.id, result: routed.result };
  }

  private async route(
    request: JsonRpcRequest,
  ): Promise<{ result: unknown } | { error: unknown } | null> {
    switch (request.method) {
      case 'initialize':
        return { result: this.handleInitialize(request.params) };
      case 'ping':
        return { result: {} };
      case 'tools/list':
        return { result: { tools: MCP_TOOLS.map((tool) => ({ ...tool })) } };
      case 'tools/call':
        return this.handleToolsCall(request.params);
      case 'resources/list':
        return { result: { resources: MCP_RESOURCES.map((resource) => ({ ...resource })) } };
      case 'resources/read':
        return this.handleResourcesRead(request.params);
      default:
        // Notifications with unknown methods are ignored per JSON-RPC;
        // requests get METHOD_NOT_FOUND.
        if (request.id === undefined) {
          return null;
        }
        return {
          error: { code: METHOD_NOT_FOUND, message: `unknown method: ${request.method}` },
        };
    }
  }

  private handleInitialize(params: unknown): unknown {
    const requested =
      params && typeof params === 'object'
        ? (params as { protocolVersion?: unknown }).protocolVersion
        : undefined;
    // Negotiation per the MCP spec: honour a supported client revision,
    // otherwise answer with the newest revision this server implements.
    const protocolVersion =
      typeof requested === 'string' && requested === MCP_PROTOCOL_VERSION
        ? requested
        : MCP_PROTOCOL_VERSION;
    return {
      protocolVersion,
      capabilities: {
        tools: { listChanged: false },
        resources: { subscribe: false, listChanged: false },
      },
      serverInfo: {
        name: MCP_SERVER_NAME,
        version: this.options.serverVersion ?? MCP_SERVER_VERSION,
      },
    };
  }

  private async handleToolsCall(params: unknown): Promise<{ result: unknown } | { error: unknown }> {
    const call = (params ?? {}) as { name?: unknown; arguments?: unknown };
    const name = call.name;
    const tool = MCP_TOOLS.find((candidate) => candidate.name === name);
    if (!tool) {
      return {
        error: {
          code: INVALID_PARAMS,
          message: `unknown tool: ${String(name)}`,
          data: { tool: name, availableTools: MCP_TOOLS.map((candidate) => candidate.name) },
        },
      };
    }
    const args = call.arguments ?? {};
    if (typeof args !== 'object' || args === null || Array.isArray(args)) {
      return {
        error: { code: INVALID_PARAMS, message: 'arguments must be an object', data: { tool: name } },
      };
    }
    try {
      // The sidecar's mcp/invoke answers {tool, result}; the MCP client
      // gets the unwrapped tool result.
      const envelope = (await this.backend.invoke(tool.name, args as Record<string, unknown>)) as {
        result?: unknown;
      };
      return {
        result: {
          content: [
            {
              type: 'text',
              text: JSON.stringify(envelope?.result ?? envelope, null, 2),
            },
          ],
        },
      };
    } catch (error) {
      // The tier refusal and every other structured sidecar error are
      // mirrored verbatim — the MCP client sees the same code and data
      // (TIER_DISABLED's capability/tier/remediation payload included).
      return { error: backendErrorFields(error) };
    }
  }

  private async handleResourcesRead(
    params: unknown,
  ): Promise<{ result: unknown } | { error: unknown }> {
    const uri = (params as { uri?: unknown } | undefined)?.uri;
    const resource = MCP_RESOURCES.find((candidate) => candidate.uri === uri);
    if (!resource) {
      return {
        error: {
          code: INVALID_PARAMS,
          message: `unknown resource: ${String(uri)}`,
          data: { uri, availableResources: MCP_RESOURCES.map((candidate) => candidate.uri) },
        },
      };
    }
    if (resource.uri === 'meridian://open-ledger-spec') {
      return {
        result: {
          contents: [
            { uri: resource.uri, mimeType: resource.mimeType, text: OPEN_LEDGER_SPEC_TEXT },
          ],
        },
      };
    }
    try {
      const report = await this.backend.doctorRun();
      return {
        result: {
          contents: [
            {
              uri: resource.uri,
              mimeType: resource.mimeType,
              text: JSON.stringify(report, null, 2),
            },
          ],
        },
      };
    } catch (error) {
      return { error: backendErrorFields(error) };
    }
  }

  /**
   * The production stdio loop: NDJSON frames on stdin, responses on stdout
   * (MCP's stdio transport). A malformed frame or a failing request never
   * kills the loop; the loop ends when the client closes stdin.
   */
  async serve(input: NodeJS.ReadableStream, output: NodeJS.WritableStream): Promise<void> {
    const decoder = createFrameDecoder();
    input.on('data', (chunk: Buffer | string) => {
      let messages: unknown[];
      try {
        messages = decoder.push(chunk.toString());
      } catch {
        output.write(
          encodeFrame(errorResponse(undefined, PARSE_ERROR, 'parse error: frame too large')),
        );
        return;
      }
      for (const message of messages) {
        void this.handleMessage(message).then((response) => {
          if (response !== null) {
            output.write(encodeFrame(response));
          }
        });
      }
    });
    await new Promise<void>((resolve) => {
      input.on('end', resolve);
      input.on('close', resolve);
    });
  }
}
