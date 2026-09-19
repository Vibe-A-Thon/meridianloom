import * as vscode from 'vscode';
import type {
  DoctorRunResult,
  RunCancelParams,
  RunCancelResult,
  RunPreflightParams,
  RunPreflightResult,
  RunStartParams,
  RunStartResult,
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
  // The palette route to the workbench. The Activity Bar remains the route
  // that needs no command at all; this exists for keybindings and for
  // reopening a closed editor tab.
  { id: 'meridianLoom.open', title: 'Open Workbench' },
  { id: 'meridian.ingestStory', title: 'Ingest Story' },
  { id: 'meridian.openRecorder', title: 'Open Recorder' },
  { id: 'meridian.inspectSource', title: 'Inspect Source Provenance' },
  { id: 'meridian.installSkill', title: 'Install Skill' },
  { id: 'meridian.onboardAgent', title: 'Onboard Agent' },
  { id: 'meridian.exportAgent', title: 'Export Agent' },
  { id: 'meridian.importAgent', title: 'Import Agent' },
  { id: 'meridian.verifyChain', title: 'Verify Chain' },
  { id: 'meridian.haltAll', title: 'Halt All' },
  { id: 'meridian.steer', title: 'Steer' },
  { id: 'meridian.dryRun', title: 'Dry Run' },
  // FR-M40-01/02 (MV2): the command-palette door into run
  // initiation. One of eight; what distinguishes it from the
  // others is the `origin` it records and nothing else (AC-38).
  { id: 'meridian.startRun', title: 'Start Run' },
  { id: 'meridian.abortStory', title: 'Abort Story' },
  // FR-M18-08 (F1 Workstream A task 5): open a story worktree in a new window.
  { id: 'meridian.openWorktree', title: 'Open Story Worktree in New Window' },
  { id: 'meridian.doctor', title: 'Doctor' },
  { id: 'meridian.installHook', title: 'Provenance Hook (Install / Remove)' },
] as const;

export type CommandId = (typeof COMMANDS)[number]['id'];

export interface CommandDeps {
  /**
   * Opens the workbench on its configured surface. The Activity Bar reaches
   * it without a command; this is the palette and keybinding route, and the
   * way back after someone closes the editor tab.
   */
  openWorkbench?: () => Promise<void>;
  inspectSource?: () => Promise<void>;
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
   * FR-M40-03 (MV2): assemble the preflight for a run started from the
   * palette. The six answers are computed in the sidecar, not here — the
   * point of the single contract is that a second door cannot arrive at a
   * different idea of what a run is.
   */
  runPreflight?: (params: RunPreflightParams) => Promise<RunPreflightResult>;
  /** FR-M40-01/05: the single entry point, after the human confirms. */
  runStart?: (params: RunStartParams) => Promise<RunStartResult>;
  /** FR-M40-09: cancel at preflight, recorded, creating nothing. */
  runCancel?: (params: RunCancelParams) => Promise<RunCancelResult>;
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
  if (id === 'meridianLoom.open') {
    if (!deps.openWorkbench) {
      await vscode.window.showWarningMessage(
        "Meridian Loom: 'meridianLoom.open' needs the extension runtime, which is not started yet.",
      );
      return;
    }
    await deps.openWorkbench();
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
  if (id === 'meridian.inspectSource' && deps.inspectSource) {
    await deps.inspectSource();
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
  if (id === 'meridian.startRun') {
    await runStartRunCommand(deps);
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

    // A user hitting a bug in the field needs one thing to send back. The
    // output channel is readable but has to be selected and copied by hand,
    // and it carries none of the environment that makes a report diagnosable
    // — version, platform, tiers. This produces the whole thing in one
    // action, and says what is in it before it goes on the clipboard.
    const COPY = 'Copy diagnostics';
    const summary =
      report.status === 'fail'
        ? 'Meridian doctor found failing checks — details in the "Meridian Loom Doctor" output channel.'
        : report.status === 'warn'
          ? 'Meridian doctor passed with warnings — details in the "Meridian Loom Doctor" output channel.'
          : 'Meridian doctor: all checks passed.';
    const choice =
      report.status === 'fail'
        ? await vscode.window.showErrorMessage(summary, COPY)
        : report.status === 'warn'
          ? await vscode.window.showWarningMessage(summary, COPY)
          : await vscode.window.showInformationMessage(summary, COPY);
    if (choice === COPY) {
      await vscode.env.clipboard.writeText(
        buildDiagnostics(report, deps),
      );
      await vscode.window.showInformationMessage(
        'Diagnostics copied. It contains the doctor report, your VS Code and ' +
          'platform versions, and the enabled tiers — no credentials, no ' +
          'ledger contents, and no workspace path.',
      );
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

/**
 * The paste-ready support report.
 *
 * Deliberately narrow: the doctor's own findings plus the environment facts
 * that change how a failure reproduces. It carries no credential, no ledger
 * content and no workspace path — a support report that leaks the thing the
 * product promises to protect would be a poor trade for a faster fix.
 */
function buildDiagnostics(
  report: { status: string; checks: readonly { id: string; status: string; detail: string; remediation?: string }[] },
  deps: CommandDeps,
): string {
  const extension = vscode.extensions.getExtension('meridianloom.meridian-loom');
  const lines = [
    '### Meridian Loom diagnostics',
    '',
    `- generated: ${new Date().toISOString()}`,
    `- extension: ${String(extension?.packageJSON?.version ?? 'unknown')}`,
    `- vscode: ${vscode.version}`,
    `- platform: ${process.platform} ${process.arch}`,
    `- node: ${process.versions.node}`,
    `- tiers: ${(deps.enabledTiers?.() ?? []).join(', ') || 'none reported'}`,
    `- workspace open: ${Boolean(vscode.workspace.workspaceFolders?.length)}`,
    `- workspace trusted: ${vscode.workspace.isTrusted}`,
    '',
    `### Doctor — ${report.status}`,
    '',
    ...report.checks.map(
      (check) =>
        `- **${check.id}**: ${check.status} — ${check.detail}` +
        (check.remediation ? ` _(${check.remediation})_` : ''),
    ),
  ];
  return lines.join('\n');
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

// -- meridian.startRun (FR-M40-01/02/03/09; MV2) ------------------------------

/**
 * The command-palette door into run initiation.
 *
 * It renders preflight with VS Code's own modal rather than the webview
 * dialog, and that is not a second implementation of anything: the six
 * answers, the completeness rule, the authority check and the origin record
 * all live in the sidecar, and this door calls the same `run/preflight` and
 * `run/start` the workbench does. What differs between doors is presentation
 * and the `origin` recorded — which is exactly the claim AC-38 tests.
 *
 * Never throws. A failure here is a message, because the alternative is an
 * unhandled rejection where a human was expecting either a run or a reason.
 */
async function runStartRunCommand(deps: CommandDeps): Promise<void> {
  if (!deps.runPreflight || !deps.runStart) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.startRun' needs the sidecar, which is not connected yet.",
    );
    return;
  }
  const intent = await vscode.window.showInputBox({
    title: 'Start a run',
    prompt: 'What should this run do?',
    placeHolder: 'Add an idempotency key to the payment submission endpoint',
    ignoreFocusOut: true,
  });
  if (intent === undefined || intent.trim() === '') {
    return;
  }

  let preflight: RunPreflightResult['preflight'];
  try {
    ({ preflight } = await deps.runPreflight({ origin: 'command', intent, repo: '.' }));
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom could not prepare this run: ${message(error)}`,
    );
    return;
  }

  // FR-M40-03: an incomplete preflight is not confirmable, and the palette
  // says which answers are missing rather than offering a button that would
  // collect consent for a run nobody could describe.
  if (!preflight.confirmable) {
    await vscode.window.showWarningMessage(
      `Meridian Loom cannot start this run yet — ${preflight.missing.join(', ')} ` +
        'not settled. Nothing has been created.',
    );
    return;
  }

  const live = preflight.mode === 'live';
  const confirm = await vscode.window.showWarningMessage(
    [
      preflight.intent,
      `Agents: ${Object.entries(preflight.adapters)
        .map(([role, adapter]) => `${role} ${adapter}`)
        .join(', ')}`,
      `Where: ${preflight.repo} · base ${preflight.baseBranch} · branch ${preflight.branch}`,
      `${preflight.worktree} — your working tree is untouched.`,
      `Cost: estimated ${money(preflight.estimateUsd)} · ceiling ${money(preflight.costCeilingUsd)}`,
      `Stops at: ${preflight.gates.join(', ')}`,
      '',
      'Cancelling creates nothing. Nothing exists until you confirm.',
    ].join('\n'),
    { modal: true },
    live ? 'Confirm live run' : 'Start dry run',
  );

  if (confirm === undefined) {
    // FR-M40-09: a cancellation is itself a fact worth keeping. A run that
    // vanished without one is indistinguishable from one that never reached
    // preflight, and the difference matters when someone asks why work was
    // not done. The recording is best-effort *here* only because the user
    // has already left; the guarantee that nothing was created is
    // structural, not dependent on this call.
    try {
      await deps.runCancel?.({ preflight, reason: 'cancelled at preflight' });
    } catch {
      /* the run was never created; losing the note is not worth a dialog */
    }
    return;
  }

  try {
    const started = await deps.runStart({ preflight, confirmed: true });
    await vscode.window.showInformationMessage(
      `Meridian Loom: run ${started.runId} started on ${started.branch} ` +
        `(${started.mode}), authorised by ${started.authorisedBy} ` +
        `at assurance ${started.assurance}.`,
    );
  } catch (error) {
    await vscode.window.showErrorMessage(
      `Meridian Loom did not start this run: ${message(error)}`,
    );
  }
}

/** `null` is unknown, not zero — "$0.00" would say the run is free (P26). */
function money(value: number | null | undefined): string {
  return value === null || value === undefined ? 'not estimated' : `$${value.toFixed(2)}`;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
