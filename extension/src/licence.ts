import * as vscode from 'vscode';
import {
  ErrorCode,
  type LicenceInstallParams,
  type LicenceRemoveParams,
  type LicenceRemoveResult,
  type LicenceStatusParams,
  type LicenceStatusResult,
} from '../../shared/ts/bus-types';

/**
 * Meridian Loom licensing, host half. The sidecar is the single authority: it
 * verifies signatures, evaluates the licence against this machine and the
 * developer's git identity, and refuses Premium RPCs without one. Everything
 * here is presentation — show the state, install a file, explain a refusal.
 *
 * Nothing in this module makes a network request. A licence is verified
 * offline against a public key inside the product (see LICENSING.md).
 */

export interface LicenceDeps {
  licenceStatus?: (params?: LicenceStatusParams) => Promise<LicenceStatusResult>;
  licenceInstall?: (params: LicenceInstallParams) => Promise<LicenceStatusResult>;
  licenceRemove?: (params: LicenceRemoveParams) => Promise<LicenceRemoveResult>;
  /** Ask the user for a .mlic file. Defaults to the VS Code open dialog. */
  pickLicenceFile?: () => Promise<string | undefined>;
  /** Put text on the clipboard. Defaults to vscode.env.clipboard. */
  copyText?: (text: string) => Promise<void>;
  /** Open the bundled LICENSING.md (or its web home). */
  openLicensingGuide?: () => Promise<void>;
}

export function isLicenceRequired(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { code?: unknown }).code === ErrorCode.LICENCE_REQUIRED
  );
}

/** One-line, plain-language summary for the status bar and pick titles. */
export function describeEdition(status: LicenceStatusResult): string {
  if (status.premiumActive) {
    const licensee = status.licence?.licensee;
    const trial = status.licence?.trial ? ' trial' : '';
    const suffix =
      status.state === 'grace'
        ? ' — expired, in grace period'
        : status.daysRemaining !== undefined && status.daysRemaining <= 30
          ? ` — ${status.daysRemaining} day(s) left`
          : '';
    return `Premium${trial}${licensee ? ` · ${licensee}` : ''}${suffix}`;
  }
  return status.state === 'none' ? 'Community (free)' : `Community — ${status.state}`;
}

/** The status text shown when the user asks "what edition am I on?". */
export function statusLines(status: LicenceStatusResult): string[] {
  const lines = [`Edition: ${status.edition === 'premium' ? 'Premium' : 'Community (free)'} (${status.state})`];
  const licence = status.licence;
  if (licence) {
    lines.push(`Licensee: ${licence.licensee}`);
    lines.push(`Licence: ${licence.licenceId} · ${licence.kind}-bound · ${licence.seats} seat(s)`);
    lines.push(`Expires: ${licence.expiresAt ?? 'never (perpetual)'}`);
    lines.push(`Features: ${licence.features.includes('*') ? 'all Premium features' : licence.features.join(', ')}`);
  }
  lines.push(status.reason);
  return lines;
}

const STATE_HINTS: Record<string, string> = {
  none: "You're on the free Community edition.",
  expired: 'Your Premium licence has expired.',
  'not-yet-valid': "The installed licence isn't valid yet.",
  'wrong-machine': 'The installed licence is for a different machine.',
  'wrong-developer': "The installed licence is for different developers than the git identity in use.",
  invalid: "The installed licence file couldn't be verified.",
  'untrusted-key': 'The installed licence was signed with a key this version does not trust.',
};

/**
 * Once per session per feature: when a Premium RPC is refused, say why and
 * offer the two useful actions. Never a modal, never repeated — a locked
 * feature should explain itself, not nag.
 */
export function createLicenceNotifier(actions: {
  install: () => Promise<void>;
  openGuide: () => Promise<void>;
}): (data: unknown) => void {
  const seen = new Set<string>();
  return (data) => {
    const detail = (data ?? {}) as { feature?: string; licenceState?: string };
    const feature = detail.feature ?? 'premium';
    if (seen.has(feature)) return;
    seen.add(feature);
    const INSTALL = 'Install licence…';
    const GUIDE = 'About licensing';
    const hint = STATE_HINTS[detail.licenceState ?? 'none'] ?? STATE_HINTS.none;
    void Promise.resolve(
      vscode.window.showInformationMessage(
        `Meridian Loom: the "${feature}" features are part of Meridian Loom Premium. ${hint}`,
        INSTALL,
        GUIDE,
      ),
    ).then(async (choice) => {
      if (choice === INSTALL) await actions.install();
      else if (choice === GUIDE) await actions.openGuide();
    });
  };
}

async function defaultPickFile(): Promise<string | undefined> {
  const picked = await vscode.window.showOpenDialog({
    canSelectMany: false,
    openLabel: 'Install licence',
    filters: { 'Meridian Loom licence': ['mlic'], 'All files': ['*'] },
  });
  return picked?.[0]?.fsPath;
}

async function defaultCopy(text: string): Promise<void> {
  await vscode.env.clipboard.writeText(text);
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

type LicenceAction = 'install' | 'installMachine' | 'fingerprint' | 'remove' | 'guide';
interface LicencePick extends vscode.QuickPickItem {
  action: LicenceAction;
}

/** Install a licence file; shared by the command and the notifier action. */
export async function installLicenceFlow(
  deps: LicenceDeps,
  scope: 'user' | 'machine' = 'user',
): Promise<void> {
  if (!deps.licenceInstall) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: installing a licence needs the extension runtime, which is not started yet.",
    );
    return;
  }
  const file = await (deps.pickLicenceFile ?? defaultPickFile)();
  if (!file) return;
  try {
    const status = await deps.licenceInstall({ path: file, scope });
    await vscode.window.showInformationMessage(
      status.premiumActive
        ? `Meridian Loom Premium is now active — ${describeEdition(status)}.`
        : `Licence stored, but Premium is not active yet: ${status.reason}`,
    );
  } catch (error) {
    await vscode.window.showErrorMessage(`Meridian Loom could not install that licence. ${message(error)}`);
  }
}

/** `meridian.licence`: status, install, fingerprint, remove — one door. */
export async function runLicenceCommand(deps: LicenceDeps): Promise<void> {
  if (!deps.licenceStatus) {
    await vscode.window.showWarningMessage(
      "Meridian Loom: 'meridian.licence' needs the extension runtime, which is not started yet.",
    );
    return;
  }
  let status: LicenceStatusResult;
  try {
    status = await deps.licenceStatus({ reload: true, includeFingerprint: true });
  } catch (error) {
    await vscode.window.showErrorMessage(`Meridian Loom could not read the licence status: ${message(error)}`);
    return;
  }

  const items: LicencePick[] = [
    {
      label: 'Install licence file…',
      description: 'For you (per-developer) — a .mlic file from your licensor',
      action: 'install',
    },
    {
      label: 'Install licence for all users on this machine…',
      description: 'Per-machine licence; needs administrator (or root) rights',
      action: 'installMachine',
    },
  ];
  if (status.machineFingerprint) {
    items.push({
      label: "Copy this machine's fingerprint",
      description: `${status.machineFingerprint} — send it to your licensor to order a per-machine licence`,
      action: 'fingerprint',
    });
  }
  if (status.state !== 'none') {
    items.push({ label: 'Remove installed licence', description: 'Return to the free Community edition', action: 'remove' });
  }
  items.push({ label: 'About licensing', description: 'Editions, what is free, how to buy', action: 'guide' });

  const pick = await vscode.window.showQuickPick<LicencePick>(items, {
    placeHolder: `${describeEdition(status)} — ${status.reason}`,
  });
  if (!pick) return;

  switch (pick.action) {
    case 'install':
      await installLicenceFlow(deps, 'user');
      return;
    case 'installMachine':
      await installLicenceFlow(deps, 'machine');
      return;
    case 'fingerprint':
      await (deps.copyText ?? defaultCopy)(status.machineFingerprint ?? '');
      await vscode.window.showInformationMessage(
        'Machine fingerprint copied. It is a one-way hash of this machine\'s identifier: it identifies the ' +
          'machine for licensing and reveals nothing else. Nothing was sent anywhere.',
      );
      return;
    case 'remove': {
      if (!deps.licenceRemove) return;
      const REMOVE = 'Remove licence';
      const confirmed = await vscode.window.showWarningMessage(
        'Remove the installed Meridian Loom licence? Premium features will stop working; your recorded evidence is untouched.',
        { modal: true },
        REMOVE,
      );
      if (confirmed !== REMOVE) return;
      try {
        const result = await deps.licenceRemove({ scope: 'user' });
        await vscode.window.showInformationMessage(
          result.removed.length
            ? `Licence removed. Meridian Loom is now on the ${describeEdition(result.status)} edition.`
            : 'No licence file was installed for this user.',
        );
      } catch (error) {
        await vscode.window.showErrorMessage(`Meridian Loom could not remove the licence: ${message(error)}`);
      }
      return;
    }
    case 'guide':
      if (deps.openLicensingGuide) await deps.openLicensingGuide();
      return;
  }
}
