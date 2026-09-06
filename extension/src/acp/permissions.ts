/**
 * The production permission approval path (FR-M34-01): an agent's
 * session/request_permission is put to the user as a vscode window prompt
 * before the agent may proceed. Injectable on AcpClient so tests drive the
 * host headless with a fake approver.
 *
 * Dismissal (Escape / no choice) maps to the ACP `cancelled` outcome —
 * the spec's answer when the client cancels the turn.
 */
import * as vscode from 'vscode';
import type { PermissionApprover } from './client';
import type { RequestPermissionRequest } from './protocol';

export function createVscodePermissionApprover(): PermissionApprover {
  return async (request: RequestPermissionRequest) => {
    const tool = request.toolCall;
    const subject = tool.title ?? tool.kind ?? `tool call ${tool.toolCallId}`;
    const choice = await vscode.window.showWarningMessage(
      `Meridian Loom — the hosted agent requests permission: ${subject}`,
      { modal: false },
      ...request.options.map((option) => option.name),
    );
    if (choice === undefined) {
      return { outcome: 'cancelled' };
    }
    const option =
      request.options.find((candidate) => candidate.name === choice) ?? request.options[0];
    return { outcome: 'selected', optionId: option.optionId };
  };
}
