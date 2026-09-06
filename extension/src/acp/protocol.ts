/**
 * ACP (Agent Client Protocol) — the pinned wire contract for Meridian's host.
 *
 * Protocol types come from the official `@zed-industries/agent-client-protocol`
 * npm package (pinned in extension/package.json; FR-M34-01, G2 — where a
 * standard won, implement the standard). Per futures.md, the ACP
 * introduction describes remote-agent support as work in progress, so the
 * host pins a NAMED protocol version and capability set rather than
 * tracking "latest":
 *
 *  - protocol version 1 (the only major version published);
 *  - client capabilities: fs.readTextFile + fs.writeTextFile + terminal/*,
 *    all serviced by the host against the user's workspace root.
 *
 * Version negotiation (agentclientprotocol.com/protocol/initialization):
 * the host sends its supported version; if the agent answers with a
 * different one, the host refuses and closes — see AcpClient.start().
 */

import type { ClientCapabilities } from '@zed-industries/agent-client-protocol';

/** The single ACP major protocol version this host implements. */
export const ACP_PROTOCOL_VERSION = 1;

/** Programmatic client identity sent on the wire. */
export const ACP_CLIENT_NAME = 'meridian-loom';

/**
 * The capability set the host provides, advertised in `initialize`.
 * Everything the agent is told it may use is implemented by AcpClient
 * against the workspace root — never wider.
 */
export const ACP_CLIENT_CAPABILITIES: ClientCapabilities = {
  fs: { readTextFile: true, writeTextFile: true },
  terminal: true,
};

// Re-export the pinned protocol types so consumers of the host depend on
// this module, not on the package path directly.
export type {
  AgentCapabilities,
  ClientCapabilities,
  CreateTerminalRequest,
  CreateTerminalResponse,
  InitializeResponse,
  PromptResponse,
  ReadTextFileRequest,
  ReadTextFileResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionNotification,
  WriteTextFileRequest,
} from '@zed-industries/agent-client-protocol';
