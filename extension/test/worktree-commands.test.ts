/**
 * Worktree isolation commands (FR-M18-04/08; F1 Workstream A task 5).
 *
 * - meridian.abortStory: confirms, then drives the sidecar worktree/abortStory
 *   RPC (worktree + never-pushed branch removal, ledger-recorded, primary
 *   tree byte-identical — AC-14).
 * - meridian.openWorktree (FR-M18-08): resolves the story worktree path via
 *   the worktree/list RPC and opens it in a new window through
 *   `vscode.openFolder` with `{ forceNewWindow: true }` — the headless mock
 *   records the invocation so the test asserts exactly that.
 *
 * Both are governor tier: with only flight-recorder enabled they disclose
 * the lock instead of acting (FR-M36-05 / X-28 / G5).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as vscode from 'vscode';
import type {
  WorktreeAbortStoryResult,
  WorktreeInfo,
  WorktreeListResult,
} from '../../shared/ts/bus-types';
import { COMMAND_TIERS } from '../../shared/ts/tiers';
import { registerCommands, type CommandDeps } from '../src/commands';

const mock = vscode as unknown as {
  __reset(): void;
  __registeredCommands: Map<string, (...args: unknown[]) => unknown>;
  __executedCommands: Array<{ command: string; args: unknown[] }>;
  __shownErrors: string[];
  __shownWarnings: string[];
  __shownInfos: string[];
  __messageChoices: string[];
};

const WORKTREE: WorktreeInfo = {
  storyId: 'story-1',
  branch: 'meridian/story-1',
  path: '/repo/.meridian/worktrees/story-1',
  worktreeRef: '.meridian/worktrees/story-1',
  baseBranch: 'main',
  baseCommit: 'abc123',
  headCommit: 'def456',
  adapterId: 'gemini',
  dirty: false,
  unpushedCommits: 1,
};

function abortResult(overrides: Partial<WorktreeAbortStoryResult> = {}): WorktreeAbortStoryResult {
  return {
    removed: true,
    storyId: 'story-1',
    branch: 'meridian/story-1',
    branchDeleted: true,
    worktreeRef: '.meridian/worktrees/story-1',
    ...overrides,
  };
}

function worktreeDeps(overrides: Partial<CommandDeps> = {}): CommandDeps {
  return {
    abortStory: () => Promise.resolve(abortResult()),
    listWorktrees: () =>
      Promise.resolve<WorktreeListResult>({ worktrees: [WORKTREE] }),
    ...overrides,
  };
}

async function runAbort(deps: CommandDeps, ...args: unknown[]): Promise<void> {
  registerCommands(deps);
  const handler = mock.__registeredCommands.get('meridian.abortStory');
  expect(handler).toBeDefined();
  await (handler as (...a: unknown[]) => Promise<void>)(...args);
}

async function runOpen(deps: CommandDeps, ...args: unknown[]): Promise<void> {
  registerCommands(deps);
  const handler = mock.__registeredCommands.get('meridian.openWorktree');
  expect(handler).toBeDefined();
  await (handler as (...a: unknown[]) => Promise<void>)(...args);
}

describe('worktree command registration', () => {
  beforeEach(() => mock.__reset());

  it('registers meridian.abortStory and meridian.openWorktree', () => {
    registerCommands(worktreeDeps());
    expect(mock.__registeredCommands.has('meridian.abortStory')).toBe(true);
    expect(mock.__registeredCommands.has('meridian.openWorktree')).toBe(true);
  });

  it('maps both commands to the governor tier (FR-M36-05)', () => {
    expect(COMMAND_TIERS['meridian.abortStory']).toBe('governor');
    expect(COMMAND_TIERS['meridian.openWorktree']).toBe('governor');
  });
});

describe('meridian.abortStory (FR-M18-04, AC-14)', () => {
  beforeEach(() => mock.__reset());

  it('reports instead of acting when the runtime is not wired', async () => {
    await runAbort({}, 'story-1');
    expect(mock.__shownWarnings.some((m) => m.includes('abortStory'))).toBe(true);
  });

  it('needs a story id', async () => {
    const abort = vi.fn(() => Promise.resolve(abortResult()));
    await runAbort(worktreeDeps({ abortStory: abort }));
    expect(abort).not.toHaveBeenCalled();
    expect(mock.__shownWarnings.some((m) => m.includes('story id'))).toBe(true);
  });

  it('confirms before aborting; the sidecar does the removal', async () => {
    const abort = vi.fn(() => Promise.resolve(abortResult()));
    mock.__messageChoices.push('Abort Story');
    await runAbort(worktreeDeps({ abortStory: abort }), 'story-1');
    expect(abort).toHaveBeenCalledTimes(1);
    expect(abort).toHaveBeenCalledWith('story-1');
    expect(
      mock.__shownInfos.some((m) => m.includes("branch 'meridian/story-1' deleted")),
    ).toBe(true);
  });

  it('does nothing when the confirmation is declined', async () => {
    const abort = vi.fn(() => Promise.resolve(abortResult()));
    await runAbort(worktreeDeps({ abortStory: abort }), 'story-1');
    expect(abort).not.toHaveBeenCalled();
  });

  it('says when a pushed branch is kept for the record', async () => {
    const abort = vi.fn(() =>
      Promise.resolve(
        abortResult({
          branchDeleted: false,
          branchKeptReason: "branch 'meridian/story-1' exists on remote 'origin'",
        }),
      ),
    );
    mock.__messageChoices.push('Abort Story');
    await runAbort(worktreeDeps({ abortStory: abort }), 'story-1');
    expect(mock.__shownInfos.some((m) => m.includes('kept'))).toBe(true);
  });

  it('surfaces sidecar failures as an error message', async () => {
    const abort = vi.fn(() => Promise.reject(new Error('worktree is locked')));
    mock.__messageChoices.push('Abort Story');
    await runAbort(worktreeDeps({ abortStory: abort }), 'story-1');
    expect(mock.__shownErrors.some((m) => m.includes('worktree is locked'))).toBe(true);
  });

  it('discloses the tier lock when the governor tier is disabled (G5)', async () => {
    const abort = vi.fn(() => Promise.resolve(abortResult()));
    mock.__messageChoices.push('Abort Story');
    await runAbort(
      worktreeDeps({ abortStory: abort, enabledTiers: () => ['flight-recorder'] }),
      'story-1',
    );
    expect(abort).not.toHaveBeenCalled();
    expect(mock.__shownInfos.some((m) => m.includes('governor'))).toBe(true);
  });
});

describe('meridian.openWorktree (FR-M18-08)', () => {
  beforeEach(() => mock.__reset());

  it('reports instead of acting when the runtime is not wired', async () => {
    await runOpen({}, 'story-1');
    expect(mock.__shownWarnings.some((m) => m.includes('openWorktree'))).toBe(true);
  });

  it('opens the story worktree in a NEW window via vscode.openFolder', async () => {
    const listWorktrees = vi.fn(() =>
      Promise.resolve<WorktreeListResult>({ worktrees: [WORKTREE] }),
    );
    await runOpen(worktreeDeps({ listWorktrees }), 'story-1');
    expect(listWorktrees).toHaveBeenCalledTimes(1);
    const open = mock.__executedCommands.filter((c) => c.command === 'vscode.openFolder');
    expect(open).toHaveLength(1);
    const [uri, options] = open[0].args as [{ fsPath: string }, { forceNewWindow: boolean }];
    expect(uri.fsPath).toBe('/repo/.meridian/worktrees/story-1');
    expect(options).toEqual({ forceNewWindow: true });
  });

  it('warns when the story has no worktree', async () => {
    await runOpen(worktreeDeps({ listWorktrees: () => Promise.resolve({ worktrees: [] }) }), 'story-9');
    expect(
      mock.__shownWarnings.some((m) => m.includes("no worktree for story 'story-9'")),
    ).toBe(true);
    expect(
      mock.__executedCommands.filter((c) => c.command === 'vscode.openFolder'),
    ).toHaveLength(0);
  });

  it('surfaces sidecar failures as an error message', async () => {
    await runOpen(
      worktreeDeps({ listWorktrees: () => Promise.reject(new Error('sidecar down')) }),
      'story-1',
    );
    expect(mock.__shownErrors.some((m) => m.includes('sidecar down'))).toBe(true);
  });

  it('discloses the tier lock when the governor tier is disabled (G5)', async () => {
    const listWorktrees = vi.fn(() =>
      Promise.resolve<WorktreeListResult>({ worktrees: [WORKTREE] }),
    );
    await runOpen(
      worktreeDeps({ listWorktrees, enabledTiers: () => ['flight-recorder'] }),
      'story-1',
    );
    expect(listWorktrees).not.toHaveBeenCalled();
    expect(mock.__shownInfos.some((m) => m.includes('governor'))).toBe(true);
  });
});
