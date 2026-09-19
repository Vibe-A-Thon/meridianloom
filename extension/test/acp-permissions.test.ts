/**
 * The production permission path (FR-M34-01): the vscode window prompt the
 * hosted agent's session/request_permission is put to. Uses the headless
 * vscode mock (vitest alias); the approver itself runs the host function
 * unmodified.
 */
import { describe, expect, it, beforeEach } from 'vitest';
import * as vscode from 'vscode';
import { createVscodePermissionApprover } from '../src/acp/permissions';
import type { RequestPermissionRequest } from '../src/acp/protocol';

const mock = vscode as unknown as {
  __reset(): void;
  __shownWarnings: string[];
  __messageChoices: string[];
};

const REQUEST: RequestPermissionRequest = {
  sessionId: 'sess-1',
  toolCall: { toolCallId: 'tc-1', title: 'Run the test suite', kind: 'execute' },
  options: [
    { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
    { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
  ],
};

describe('vscode permission approver (FR-M34-01)', () => {
  beforeEach(() => {
    mock.__reset();
  });

  it('maps the user choice to the selected option id', async () => {
    mock.__messageChoices.push('Allow once');
    const decision = await createVscodePermissionApprover()(REQUEST, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'allow-once' });
    expect(mock.__shownWarnings).toHaveLength(1);
    expect(mock.__shownWarnings[0]).toContain('Run the test suite');
  });

  it('maps dismissal to the ACP cancelled outcome', async () => {
    const decision = await createVscodePermissionApprover()(REQUEST, {});
    expect(decision).toEqual({ outcome: 'cancelled' });
  });

  it('maps a reject choice to the reject option id', async () => {
    mock.__messageChoices.push('Reject');
    const decision = await createVscodePermissionApprover()(REQUEST, {});
    expect(decision).toEqual({ outcome: 'selected', optionId: 'reject-once' });
  });
});
