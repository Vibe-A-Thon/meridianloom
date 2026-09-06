import * as vscode from 'vscode';
import type {
  DoctorRunResult,
  HookInstallResult,
  HookRemoveResult,
  HookStatusResult,
  TierName,
} from '../../shared/ts/bus-types';
import { isCommandEnabled, tierLockMessage } from '../../shared/ts/tiers';
import { renderDoctorReport } from './doctor';

/**
 * FR-M1-03: exactly these twelve commands, plus the F0 Workstream E
 * provenance-hook command (FR-M36-03, D23). Ids here are the single source
 * of truth; the manifest test asserts package.json matches them.
 */
export const COMMANDS = [
  { id: 'meridian.ingestStory', title: 'Ingest Story' },
  { id: 'meridian.openDashboard', title: 'Open Dashboard' },
  { id: 'meridian.installSkill', title: 'Install Skill' },
  { id: 'meridian.onboardAgent', title: 'Onboard Agent' },
  { id: 'meridian.exportAgent', title: 'Export Agent' },
  { id: 'meridian.importAgent', title: 'Import Agent' },
  { id: 'meridian.verifyChain', title: 'Verify Chain' },
  { id: 'meridian.haltAll', title: 'Halt All' },
  { id: 'meridian.steer', title: 'Steer' },
  { id: 'meridian.dryRun', title: 'Dry Run' },
  { id: 'meridian.abortStory', title: 'Abort Story' },
  { id: 'meridian.doctor', title: 'Doctor' },
  { id: 'meridian.installHook', title: 'Provenance Hook (Install / Remove)' },
] as const;

export type CommandId = (typeof COMMANDS)[number]['id'];

export interface CommandDeps {
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
   * FR-M36-05: the workspace's enabled tiers, read lazily so a settings
   * change takes effect without re-registration. Absent means "all tiers"
   * so tests that do not care about tiering see the unfiltered behaviour.
   */
  enabledTiers?: () => readonly TierName[];
}

export function registerCommands(deps: CommandDeps = {}): vscode.Disposable[] {
  return COMMANDS.map(({ id }) =>
    vscode.commands.registerCommand(id, () => runCommand(id, deps)),
  );
}

/**
 * All real work is delegated to the sidecar (Workstream B). Until a client
 * is connected, a command reports instead of silently succeeding.
 */
async function runCommand(id: CommandId, deps: CommandDeps): Promise<void> {
  // FR-M36-05 / X-28: a command whose tier is disabled discloses the lock
  // instead of acting. The palette entry is hidden via `when` clauses; this
  // guard is the programmatic backstop so a disabled tier leaves no scar.
  const enabled = deps.enabledTiers?.();
  if (enabled && !isCommandEnabled(id, enabled)) {
    await vscode.window.showInformationMessage(tierLockMessage(id));
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
