import * as vscode from 'vscode';

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

export function registerCommands(): vscode.Disposable[] {
  return COMMANDS.map(({ id }) =>
    vscode.commands.registerCommand(id, () => runCommand(id)),
  );
}

/**
 * All real work is delegated to the sidecar (Workstream B). Until a client
 * is connected, a command reports instead of silently succeeding.
 */
async function runCommand(id: CommandId): Promise<void> {
  await vscode.window.showWarningMessage(
    `Meridian Loom: '${id}' needs the sidecar, which is not connected yet.`,
  );
}
