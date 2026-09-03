import * as vscode from 'vscode';
import type { DoctorRunResult, TierName } from '../../shared/ts/bus-types';
import { isCommandEnabled, tierLockMessage } from '../../shared/ts/tiers';
import { renderDoctorReport } from './doctor';

/**
 * FR-M1-03: exactly these twelve commands. Ids here are the single source
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
