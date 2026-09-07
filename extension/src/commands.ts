import * as vscode from 'vscode';
import type {
  DoctorRunResult,
  HookInstallResult,
  HookRemoveResult,
  HookStatusResult,
  TierName,
  WorktreeAbortStoryResult,
  WorktreeListResult,
} from '../../shared/ts/bus-types';
import { isCommandEnabled, tierLockMessage } from '../../shared/ts/tiers';
import { renderDoctorReport } from './doctor';

/**
 * FR-M1-03 (F0 subset per gaps_implementation.md §F0): `meridian.openRecorder`
 * is the Flight Recorder dashboard command; the remaining ids here are the
 * pre-F0 superset retained until their tiers land. Ids in this file are the
 * single source of truth; the manifest test asserts package.json matches.
 */
export const COMMANDS = [
  { id: 'meridian.ingestStory', title: 'Ingest Story' },
  { id: 'meridian.openRecorder', title: 'Open Recorder' },
  { id: 'meridian.installSkill', title: 'Install Skill' },
  { id: 'meridian.onboardAgent', title: 'Onboard Agent' },
  { id: 'meridian.exportAgent', title: 'Export Agent' },
  { id: 'meridian.importAgent', title: 'Import Agent' },
  { id: 'meridian.verifyChain', title: 'Verify Chain' },
  { id: 'meridian.haltAll', title: 'Halt All' },
  { id: 'meridian.steer', title: 'Steer' },
  { id: 'meridian.dryRun', title: 'Dry Run' },
  { id: 'meridian.abortStory', title: 'Abort Story' },
  // FR-M18-08 (F1 Workstream A task 5): open a story worktree in a new window.
  { id: 'meridian.openWorktree', title: 'Open Story Worktree in New Window' },
  { id: 'meridian.doctor', title: 'Doctor' },
  { id: 'meridian.installHook', title: 'Provenance Hook (Install / Remove)' },
] as const;

export type CommandId = (typeof COMMANDS)[number]['id'];

export interface CommandDeps {
  /**
   * F0 Workstream G: opens the Flight Recorder dashboard webview panel.
   * Tests may omit it to prove the not-wired path reports instead of
   * silently succeeding.
   */
  openRecorder?: () => Promise<void>;
  /**
   * FR-M30-01: runs the full doctor (host + sidecar checks) and returns the
   * structured report. The extension always supplies it; tests may omit it
   * to prove the not-wired path reports instead of silently succeeding.
   */
  runDoctor?: () => Promise<DoctorRunResult>;
  /**
   * FR-M36-03 / D23: the provenance-hook lifecycle over hook/* RPCs. The
   * extension supplies them once the sidecar is up; tests may omit them to
   * prove the not-wired path reports instead of silently succeeding.
   */
  hookStatus?: () => Promise<HookStatusResult>;
  hookInstall?: () => Promise<HookInstallResult>;
  hookRemove?: () => Promise<HookRemoveResult>;
  /**
   * FR-M18-04 (F1 Workstream A task 5): story abort over worktree/abortStory
   * — removes the story worktree and its never-pushed branch, ledger-recorded,
   * leaving the primary working tree byte-identical (AC-14).
   */
  abortStory?: (storyId: string) => Promise<WorktreeAbortStoryResult>;
  /**
   * FR-M18-08: the Meridian-managed worktrees (worktree/list) — the command
   * resolves the story's worktree path and opens it in a new window.
   */
  listWorktrees?: () => Promise<WorktreeListResult>;
  /**
   * FR-M36-05: the workspace's enabled tiers, read lazily so a settings
   * change takes effect without re-registration. Absent means "all tiers"
   * so tests that do not care about tiering see the unfiltered behaviour.
   */
  enabledTiers?: () => readonly TierName[];
}

export function registerCommands(deps: CommandDeps = {}): vscode.Disposable[] {
  return COMMANDS.map(({ id }) =>
    vscode.commands.registerCommand(id, (...args: unknown[]) =>
      runCommand(id, deps, args),
    ),
  );
}

/**
 * All real work is delegated to the sidecar (Workstream B). Until a client
 * is connected, a command reports instead of silently succeeding.
 */
async function runCommand(id: CommandId, deps: CommandDeps, args: unknown[] = []): Promise<void> {
  // FR-M36-05 / X-28: a command whose tier is disabled discloses the lock
  // instead of acting. The palette entry is hidden via `when` clauses; this
  // guard is the programmatic backstop so a disabled tier leaves no scar.
  const enabled = deps.enabledTiers?.();
  if (enabled && !isCommandEnabled(id, enabled)) {
    await vscode.window.showInformationMessage(tierLockMessage(id));
    return;
  }
  if (id === 'meridian.openRecorder') {
    if (!deps.openRecorder) {
      await vscode.window.showWarningMessage(
        "Meridian Loom: 'meridian.openRecorder' needs the extension runtime, which is not started yet.",
      );
      return;
    }
    await deps.openRecorder();
    return;
  }
  if (id === 'meridian.doctor') {
    await runDoctorCommand(deps);
    return;
  }
  if (id === 'meridian.installHook') {
    await runHookCommand(deps);
    return;
  }
  if (id === 'meridian.abortStory') {
    await runAbortStoryCommand(deps, args[0]);
    return;
  }
  if (id === 'meridian.openWorktree') {
    await runOpenWorktreeCommand(deps, args[0]);
    return;
  }
  await vscode.window.showWarningMessage(
    `Meridian Loom: '${id}' needs the sidecar, which is not connected yet.`,
  );
}

let doctorChannel: vscode.OutputChannel | undefined;

/**
 * FR-M30-01: render the structured report into a dedicated output channel
 * and summarise via a notification. The command never throws — doctor is the
 * diagnostic surface, so its own failure is reported, not propagated.
 */
async function runDoctorCommand(deps: CommandDeps): Promise<void> {
  if (!deps.runDoctor) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.doctor' needs the extension runtime, which is not started yet.",
    );
    return;
  }
  doctorChannel ??= vscode.window.createOutputChannel('Meridian Loom Doctor');
  doctorChannel.appendLine(`meridian doctor — ${new Date().toISOString()}`);
  try {
    const report = await deps.runDoctor();
    for (const line of renderDoctorReport(report)) {
      doctorChannel.appendLine(line);
    }
    doctorChannel.appendLine('');
    doctorChannel.show();
    if (report.status === 'fail') {
      await vscode.window.showErrorMessage(
        'Meridian doctor found failing checks — details in the "Meridian Loom Doctor" output channel.',
      );
    } else if (report.status === 'warn') {
      await vscode.window.showWarningMessage(
        'Meridian doctor passed with warnings — details in the "Meridian Loom Doctor" output channel.',
      );
    } else {
      await vscode.window.showInformationMessage('Meridian doctor: all checks passed.');
    }
  } catch (error) {
    doctorChannel.appendLine(
      `doctor itself failed: ${error instanceof Error ? error.message : String(error)}`,
    );
    doctorChannel.show();
    await vscode.window.showErrorMessage(
      'Meridian doctor failed to run — details in the "Meridian Loom Doctor" output channel.',
    );
  }
}

// -- meridian.installHook (FR-M36-03, D23; F0 Workstream E task 23b) ----------

interface HookPick {
  label: string;
  description: string;
  action: 'install' | 'remove';
}

/**
 * The opt-in provenance hook, driven by hook/status. The command shows what
 * is there, offers the one relevant action, always confirms before anything
 * touches the repository's git hooks (a foreign commit-msg is backed up and
 * chained, never overwritten), then surfaces the doctor git-hooks verdict.
 * Never throws: this is a user-facing action, so failures become messages.
 */
async function runHookCommand(deps: CommandDeps): Promise<void> {
  if (!deps.hookStatus || !deps.hookInstall || !deps.hookRemove) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.installHook' needs the extension runtime, which is not started yet.",
    );
    return;
  }
  let status: HookStatusResult;
  try {
    status = await deps.hookStatus();
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom could not read the hook status: ${error instanceof Error ? error.message : String(error)}`,
    );
    return;
  }

  let pick: HookPick | undefined;
  if (status.installed) {
    pick = await vscode.window.showQuickPick<HookPick>(
      [
        {
          label: 'Remove Meridian commit-msg hook',
          description: 'Provenance trailers stop being appended; one action, reversible.',
          action: 'remove',
        },
      ],
      { placeHolder: status.detail },
    );
    if (!pick) {
      return;
    }
  } else {
    const items: HookPick[] = status.foreignHook
      ? [
          {
            label: 'Install and chain onto the existing commit-msg hook',
            description:
              'The existing hook is backed up and still runs first; nothing is overwritten.',
            action: 'install',
          },
        ]
      : [
          {
            label: 'Install commit-msg provenance hook',
            description:
              'Appends "Meridian-Ledger: <seq range>" to commits linked beforehand; opt-in and removable.',
            action: 'install',
          },
        ];
    pick = await vscode.window.showQuickPick<HookPick>(items, { placeHolder: status.detail });
    if (!pick) {
      return;
    }
  }

  const confirmText =
    pick.action === 'install'
      ? 'Install the Meridian commit-msg hook into this repository\'s git hooks directory ' +
        '(honouring core.hooksPath if one is set)? A foreign hook, if present, is backed up and chained — never overwritten.'
      : 'Remove the Meridian commit-msg hook from this repository?';
  const confirmed = await vscode.window.showWarningMessage(confirmText, { modal: true }, 'Confirm');
  if (confirmed === undefined) {
    return;
  }

  try {
    const result =
      pick.action === 'install' ? await deps.hookInstall() : await deps.hookRemove();
    const detail =
      'detail' in result && typeof result.detail === 'string'
        ? result.detail
        : pick.action === 'install'
          ? 'commit-msg hook installed'
          : 'commit-msg hook removed';
    await vscode.window.showInformationMessage(`Meridian Loom: ${detail}`);
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom could not ${pick.action} the hook: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  await showGitHooksDoctorResult(deps);
}

/** After any hook action, prove the new state with the doctor git-hooks check. */
async function showGitHooksDoctorResult(deps: CommandDeps): Promise<void> {
  if (!deps.runDoctor) {
    return;
  }
  try {
    const report = await deps.runDoctor();
    const check = report.checks.find((entry) => entry.id === 'git-hooks');
    if (check) {
      await vscode.window.showInformationMessage(
        `git-hooks (${check.status}): ${check.detail}`,
      );
    }
  } catch {
    // Doctor reports its own failures via meridian.doctor; not duplicated here.
  }
}


// -- meridian.abortStory (FR-M18-04; F1 Workstream A task 5) ------------------

/**
 * Story abort: removes the story worktree and deletes the never-pushed story
 * branch (sidecar worktree/abortStory, ledger-recorded), leaving the primary
 * working tree byte-identical (AC-14). Always confirms — abort discards
 * in-flight agent output. Never throws: failures become messages.
 */
async function runAbortStoryCommand(deps: CommandDeps, rawStoryId: unknown): Promise<void> {
  if (!deps.abortStory) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.abortStory' needs the extension runtime, which is not started yet.",
    );
    return;
  }
  if (typeof rawStoryId !== 'string' || rawStoryId === '') {
    await vscode.window.showWarningMessage(
      'Meridian Loom: abort needs a story id (invoke it with a story selected).',
    );
    return;
  }
  const confirmed = await vscode.window.showWarningMessage(
    `Abort story '${rawStoryId}'? Its worktree and never-pushed branch will be removed; ` +
      'the primary working tree is untouched. The abort is recorded in the ledger.',
    { modal: true },
    'Abort Story',
  );
  if (confirmed === undefined) {
    return;
  }
  try {
    const result = await deps.abortStory(rawStoryId);
    const branchNote = result.branchDeleted
      ? `branch '${result.branch}' deleted`
      : `branch '${result.branch}' kept (${result.branchKeptReason})`;
    await vscode.window.showInformationMessage(
      `Meridian Loom: story '${result.storyId}' aborted — worktree removed, ${branchNote}.`,
    );
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom could not abort story '${rawStoryId}': ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

// -- meridian.openWorktree (FR-M18-08; F1 Workstream A task 5) ----------------

/**
 * Open the story worktree in a new VS Code window. The sidecar resolves the
 * worktree path (worktree/list — the RPC half of FR-M18-08); this command is
 * the window-management half. Never throws: failures become messages.
 */
async function runOpenWorktreeCommand(deps: CommandDeps, rawStoryId: unknown): Promise<void> {
  if (!deps.listWorktrees) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.openWorktree' needs the extension runtime, which is not started yet.",
    );
    return;
  }
  if (typeof rawStoryId !== 'string' || rawStoryId === '') {
    await vscode.window.showWarningMessage(
      'Meridian Loom: open worktree needs a story id (invoke it with a story selected).',
    );
    return;
  }
  let worktrees: WorktreeListResult;
  try {
    worktrees = await deps.listWorktrees();
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom could not list worktrees: ${error instanceof Error ? error.message : String(error)}`,
    );
    return;
  }
  const worktree = worktrees.worktrees.find((entry) => entry.storyId === rawStoryId);
  if (!worktree) {
    await vscode.window.showWarningMessage(
      `Meridian Loom: no worktree for story '${rawStoryId}' — the story may not have started yet.`,
    );
    return;
  }
  await vscode.commands.executeCommand(
    'vscode.openFolder',
    vscode.Uri.file(worktree.path),
    { forceNewWindow: true },
  );
}
