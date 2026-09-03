import type {
  DoctorCheck,
  DoctorRunParams,
  DoctorRunResult,
} from '../../shared/ts/bus-types';
import {
  InterpreterResolutionError,
  resolveInterpreter,
  type InterpreterResolution,
} from './interpreter';

/**
 * FR-M30-01, host half. The sidecar's check registry (core/meridian_core/
 * doctor.py) covers what it can see — its own interpreter, the signing key,
 * the ledger, git hooks, observers. The host adds the two checks only it can
 * run: the interpreter *resolution chain* (FR-M3-05, which decides what the
 * sidecar would spawn with) and the OS keychain via VS Code SecretStorage
 * (FR-M1-06/07).
 *
 * This module is deliberately vscode-free so the webview's diagnostics
 * surface can reuse it; every dependency is injected.
 */
export interface DoctorDeps {
  /** FR-M3-05 resolution chain; defaults to the real one. */
  probeInterpreter?: () => Promise<InterpreterResolution>;
  /** FR-M1-07 keychain round-trip; defaults are supplied by the caller. */
  verifySecrets?: () => Promise<void>;
  /** Sidecar `doctor/run` RPC; undefined when no sidecar is running. */
  runSidecarDoctor?: (
    params: DoctorRunParams,
    signal: AbortSignal,
  ) => Promise<DoctorRunResult>;
  /** Workspace folder for the sidecar's git-hooks check. */
  workspaceDir?: string;
}

/** Canonical report order; host- and sidecar-produced checks interleave here. */
const CHECK_ORDER = [
  'interpreter',
  'sidecar',
  'keychain',
  'signing-key',
  'ledger',
  'git-hooks',
  'observers',
] as const;

const CHECK_NAMES: Record<string, string> = {
  interpreter: 'Python interpreter',
  sidecar: 'Meridian Core sidecar',
  keychain: 'OS keychain (SecretStorage)',
  'signing-key': 'Ledger signing key',
  ledger: 'Ledger integrity',
  'git-hooks': 'Git provenance hooks',
  observers: 'Observer health',
};

function entry(
  id: string,
  status: DoctorCheck['status'],
  detail: string,
  remediation?: string,
): DoctorCheck {
  const check: DoctorCheck = { id, name: CHECK_NAMES[id] ?? id, status, detail };
  if (remediation !== undefined) {
    check.remediation = remediation;
  }
  return check;
}

async function hostInterpreterCheck(
  probe: () => Promise<InterpreterResolution>,
): Promise<DoctorCheck> {
  try {
    const resolved = await probe();
    return entry(
      'interpreter',
      'pass',
      `Python ${resolved.version.join('.')} at ${resolved.executable} (via ${resolved.source})`,
    );
  } catch (error) {
    if (error instanceof InterpreterResolutionError) {
      return entry(
        'interpreter',
        'fail',
        `no usable interpreter. ${error.attempts.join('; ')}`,
        'Install Python 3.11+ or set meridian.python.interpreterPath to one.',
      );
    }
    return entry(
      'interpreter',
      'fail',
      `interpreter probe failed: ${error instanceof Error ? error.message : String(error)}`,
      'Set meridian.python.interpreterPath to a real Python 3.11+ executable and reload the window.',
    );
  }
}

async function keychainCheck(verify: () => Promise<void>): Promise<DoctorCheck> {
  try {
    await verify();
    return entry('keychain', 'pass', 'SecretStorage round-trip succeeded');
  } catch (error) {
    return entry(
      'keychain',
      'fail',
      'SecretStorage cannot round-trip a value',
      // SecretStorageUnavailableError's message is already the remediation
      // (FR-M1-07); anything else gets a generic pointer.
      error instanceof Error ? error.message : 'Restart VS Code and re-run meridian.doctor.',
    );
  }
}

/** Sidecar unavailable: one fail for the sidecar itself, warns downstream. */
function sidecarDownEntries(error: unknown): DoctorCheck[] {
  const reason =
    error === undefined
      ? 'the sidecar is not running'
      : `the sidecar did not answer: ${error instanceof Error ? error.message : String(error)}`;
  return [
    entry(
      'sidecar',
      'fail',
      reason,
      'Check the Meridian Loom status bar item for the spawn error, then run ' +
        '"Developer: Reload Window". The sidecar stderr is in the Meridian Loom output.',
    ),
    ...(['signing-key', 'ledger', 'git-hooks', 'observers'] as const).map((id) =>
      entry(
        id,
        'warn',
        'not checked — the sidecar is unavailable',
        'Fix the sidecar check above, then re-run meridian.doctor.',
      ),
    ),
  ];
}

/**
 * Run every check and merge host and sidecar results into one ordered
 * report. Never throws: doctor is the tool for a broken install, so its own
 * failures become check entries.
 */
export async function runDoctor(deps: DoctorDeps): Promise<DoctorRunResult> {
  const checks = new Map<string, DoctorCheck>();

  let sidecarReport: DoctorRunResult | undefined;
  let sidecarFailure: unknown;
  if (deps.runSidecarDoctor) {
    try {
      sidecarReport = await deps.runSidecarDoctor(
        { workspaceDir: deps.workspaceDir },
        new AbortController().signal,
      );
    } catch (error) {
      sidecarFailure = error;
    }
  }

  if (sidecarReport) {
    for (const check of sidecarReport.checks) {
      checks.set(check.id, check);
    }
  } else {
    // The sidecar is down or never started: one fail for the sidecar itself,
    // warns for everything only it could check, and the interpreter entry
    // falls back to the host-side resolution chain (FR-M3-05).
    const absent = deps.runSidecarDoctor === undefined && sidecarFailure === undefined;
    for (const down of sidecarDownEntries(absent ? undefined : sidecarFailure)) {
      checks.set(down.id, down);
    }
    checks.set(
      'interpreter',
      await hostInterpreterCheck(deps.probeInterpreter ?? resolveInterpreter),
    );
  }

  if (deps.verifySecrets) {
    checks.set('keychain', await keychainCheck(deps.verifySecrets));
  }

  // A future sidecar might not know a newer host check (or vice versa);
  // unknown slots surface as warns rather than disappearing silently.
  const ordered = CHECK_ORDER.map((id) => {
    const check = checks.get(id);
    return (
      check ??
      entry(id, 'warn', 'not reported by either host or sidecar', 'Re-run meridian.doctor.')
    );
  });

  const status = ordered.some((c) => c.status === 'fail')
    ? ('fail' as const)
    : ordered.some((c) => c.status === 'warn')
      ? ('warn' as const)
      : ('pass' as const);
  return { status, checks: ordered };
}

const SYMBOL: Record<DoctorCheck['status'], string> = {
  pass: '✓',
  warn: '!',
  fail: '✗',
};

/** Render the report for the output channel (one line per call site). */
export function renderDoctorReport(report: DoctorRunResult): string[] {
  const lines: string[] = [];
  for (const check of report.checks) {
    lines.push(`${SYMBOL[check.status]} ${check.name} — ${check.detail}`);
    if (check.remediation) {
      lines.push(`    → ${check.remediation}`);
    }
  }
  const count = (status: DoctorCheck['status']) =>
    report.checks.filter((c) => c.status === status).length;
  lines.push('');
  lines.push(
    `${count('pass')} passed, ${count('warn')} warnings, ${count('fail')} failed ` +
      `— overall: ${report.status.toUpperCase()}`,
  );
  return lines;
}
