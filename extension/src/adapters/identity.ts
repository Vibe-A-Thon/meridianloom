import { createHash } from 'node:crypto';
import { promises as fsp } from 'node:fs';
import path from 'node:path';

/**
 * Verifiable agent identity — `FR-M44-01`/`02`, `AC-52` (MV3-T01b).
 *
 * Pinning the adapter folder answers *is this the configuration that was
 * installed?* It does not answer *which binary just ran?* — and those are
 * different questions with the same consequence. An adapter folder can be
 * byte-identical while `claude` on `PATH` is a different build than it was
 * yesterday, and every attribution recorded in between names an agent that
 * is not the one that acted.
 *
 * So identity is bound to what was actually executed: the absolute path
 * resolved from `PATH`, and the digest of the file at it. Never to the name
 * the agent gives for itself, which is a claim and costs an attacker
 * nothing.
 *
 * ## The honest limit, which is most of the value here
 *
 * The common launch command is a run-time package fetcher —
 * `npx -y @acme/java-developer@2.3.0 --acp`, `uvx`, `pipx run`, `bunx`. The
 * file on `PATH` is then the *fetcher*, not the agent, and digesting it
 * proves nothing about the code that will run. This module says so:
 * assurance is `unverified` and the reason names the fetcher. It does not
 * quietly report the npx shim's digest as the agent's identity, which would
 * be the overclaim `P27` forbids and would be worse than reporting nothing,
 * because it would look like a check.
 *
 * Nothing here executes anything. Asking a binary its version means running
 * it before any permission gate has been consulted, so the version and
 * publisher come from what was declared and are labelled as declared.
 */

export type IdentityAssurance = 'verified' | 'unverified';

export interface AgentIdentity {
  /** The command as configured, before resolution. */
  command: string;
  /** The absolute path that `PATH` resolution actually landed on. */
  resolvedPath?: string;
  /** `sha256:…` of the bytes at `resolvedPath`. */
  executableDigest?: string;
  /** Declared by the manifest or the agent record — a claim, not a check. */
  declaredVersion?: string;
  declaredPublisher?: string;
  assurance: IdentityAssurance;
  /** Why `unverified`. Always present when assurance is `unverified`. */
  unverifiedReason?: string;
  /** ISO-8601 UTC. */
  resolvedAt: string;
}

/**
 * Launchers that fetch and run someone else's package at run time. Digesting
 * one of these tells you about the launcher and nothing about the agent.
 */
export const RUNTIME_FETCHERS: readonly string[] = [
  'npx',
  'bunx',
  'pnpx',
  'pnpm',
  'uvx',
  'dlx',
  'yarn',
  'deno',
];

/** `pipx run …` and `pip … run` fetch at run time; plain `pipx` may not. */
const FETCHER_SUBCOMMANDS: Record<string, readonly string[]> = {
  pipx: ['run'],
  pnpm: ['dlx'],
  yarn: ['dlx'],
  deno: ['run'],
};

export interface IdentityFs {
  readFileBytes(file: string): Promise<Uint8Array>;
  readFileText(file: string): Promise<string>;
  writeFileText(file: string, contents: string): Promise<void>;
  stat(file: string): Promise<{ isFile(): boolean }>;
  mkdirp(dir: string): Promise<void>;
}

export const nodeIdentityFs: IdentityFs = {
  readFileBytes: (file) => fsp.readFile(file),
  readFileText: (file) => fsp.readFile(file, 'utf8'),
  writeFileText: (file, contents) => fsp.writeFile(file, contents, 'utf8'),
  stat: (file) => fsp.stat(file),
  mkdirp: async (dir) => {
    await fsp.mkdir(dir, { recursive: true });
  },
};

export interface ResolveOptions {
  fs?: IdentityFs;
  /** `process.env` by default; injected so PATH behaviour is testable. */
  env?: NodeJS.ProcessEnv;
  /** `process.platform` by default. */
  platform?: NodeJS.Platform;
  declaredVersion?: string;
  declaredPublisher?: string;
  now?: () => Date;
}

function isFetcher(command: string, args: readonly string[]): string | undefined {
  const base = path.basename(command).replace(/\.(exe|cmd|bat|ps1)$/i, '').toLowerCase();
  const sub = FETCHER_SUBCOMMANDS[base];
  if (sub) {
    return args.some((arg) => sub.includes(arg.toLowerCase())) ? base : undefined;
  }
  return RUNTIME_FETCHERS.includes(base) ? base : undefined;
}

/**
 * Find the file `PATH` would execute for `command`.
 *
 * Windows needs `PATHEXT`: `claude` on PATH is `claude.cmd`, and resolving
 * to the extensionless name would come back empty on the platform this is
 * most often run on.
 */
export async function resolveExecutable(
  command: string,
  options: { fs?: IdentityFs; env?: NodeJS.ProcessEnv; platform?: NodeJS.Platform } = {},
): Promise<string | undefined> {
  const fs = options.fs ?? nodeIdentityFs;
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const windows = platform === 'win32';

  // Join with the TARGET platform's rules, not the host's. `path.join` on a
  // Windows host turns a posix PATH entry into a backslash path, which
  // resolves nothing and then reports "not on PATH" — an unverified identity
  // produced by a bug rather than by the world, which is the worst kind
  // because it looks like an honest answer.
  const join = windows ? path.win32.join : path.posix.join;

  const candidates: string[] = [];
  if (command.includes('/') || command.includes('\\')) {
    candidates.push(command);
  } else {
    const dirs = (env.PATH ?? env.Path ?? '').split(windows ? ';' : ':').filter(Boolean);
    for (const dir of dirs) {
      candidates.push(join(dir, command));
    }
  }

  const extensions = windows
    ? ['', ...(env.PATHEXT ?? '.COM;.EXE;.BAT;.CMD').split(';').filter(Boolean)]
    : [''];

  for (const candidate of candidates) {
    for (const extension of extensions) {
      const full = `${candidate}${extension}`;
      try {
        const stats = await fs.stat(full);
        if (stats.isFile()) return full;
      } catch {
        // Not there, or not readable. Keep looking; a PATH entry that does
        // not exist is ordinary, not an error.
      }
    }
  }
  return undefined;
}

/**
 * The identity of whatever this command will actually run (`FR-M44-01`).
 *
 * Never throws: identity resolution runs on the launch path, and a launch
 * that fails because the integrity check could not read a file has turned a
 * provenance feature into an outage. An identity that could not be
 * established comes back `unverified` with the reason.
 */
export async function resolveAgentIdentity(
  command: string,
  args: readonly string[] = [],
  options: ResolveOptions = {},
): Promise<AgentIdentity> {
  const fs = options.fs ?? nodeIdentityFs;
  const now = options.now ?? (() => new Date());
  const base: AgentIdentity = {
    command,
    declaredVersion: options.declaredVersion,
    declaredPublisher: options.declaredPublisher,
    assurance: 'unverified',
    resolvedAt: now().toISOString(),
  };

  const fetcher = isFetcher(command, args);
  const resolved = await resolveExecutable(command, options).catch(() => undefined);

  if (!resolved) {
    return {
      ...base,
      unverifiedReason:
        `'${command}' was not found on PATH, so there is no file to identify. ` +
        `The agent may still launch through a shell alias or a shim, and if it ` +
        `does, Meridian cannot say what ran.`,
    };
  }

  let digest: string | undefined;
  try {
    const bytes = await fs.readFileBytes(resolved);
    digest = `sha256:${createHash('sha256').update(bytes).digest('hex')}`;
  } catch (error) {
    return {
      ...base,
      resolvedPath: resolved,
      unverifiedReason:
        `'${resolved}' could not be read, so its contents cannot be identified: ` +
        `${error instanceof Error ? error.message : String(error)}`,
    };
  }

  if (fetcher) {
    // The digest is real and it is the digest of the wrong thing. Recording
    // it as the agent's identity would be a check in appearance only.
    return {
      ...base,
      resolvedPath: resolved,
      executableDigest: digest,
      unverifiedReason:
        `'${fetcher}' fetches and runs the agent package at launch, so this ` +
        `digest identifies ${fetcher} and not the agent. To get a verifiable ` +
        `identity, point the command at an installed executable rather than ` +
        `at a run-time package fetcher.`,
    };
  }

  return {
    ...base,
    resolvedPath: resolved,
    executableDigest: digest,
    assurance: 'verified',
  };
}

// -- remembering an identity, so a swap is visible (AC-52) -------------------

export const IDENTITIES_FILE = 'agent-identities.json';

export interface RememberedIdentity {
  agentId: string;
  command: string;
  resolvedPath?: string;
  executableDigest?: string;
  assurance: IdentityAssurance;
  firstSeenAt: string;
  lastSeenAt: string;
}

export type IdentityLedger = Record<string, RememberedIdentity>;

export type IdentityChange = 'first-seen' | 'unchanged' | 'changed' | 'became-unverifiable';

export interface IdentityComparison {
  change: IdentityChange;
  identity: AgentIdentity;
  previous?: RememberedIdentity;
  /** Set when a human should be told. Absent when nothing happened. */
  warning?: string;
}

function identitiesPath(meridianDir: string): string {
  return path.join(meridianDir, IDENTITIES_FILE);
}

export async function readIdentityLedger(
  meridianDir: string,
  fs: IdentityFs = nodeIdentityFs,
): Promise<IdentityLedger> {
  let text: string;
  try {
    text = await fs.readFileText(identitiesPath(meridianDir));
  } catch {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const ledger: IdentityLedger = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      const row = value as Partial<RememberedIdentity>;
      if (row && typeof row.command === 'string' && typeof row.firstSeenAt === 'string') {
        ledger[id] = {
          agentId: id,
          command: row.command,
          resolvedPath: typeof row.resolvedPath === 'string' ? row.resolvedPath : undefined,
          executableDigest:
            typeof row.executableDigest === 'string' ? row.executableDigest : undefined,
          assurance: row.assurance === 'verified' ? 'verified' : 'unverified',
          firstSeenAt: row.firstSeenAt,
          lastSeenAt: typeof row.lastSeenAt === 'string' ? row.lastSeenAt : row.firstSeenAt,
        };
      }
    }
    return ledger;
  } catch {
    // Untrusted input, read as data. A corrupt file makes every agent
    // first-seen again, which warns nobody falsely.
    return {};
  }
}

/**
 * `AC-52`: has the binary behind this agent changed?
 *
 * The comparison is on the digest, not the name and not the path — a swap
 * that keeps both is exactly the case this exists for. The new identity is
 * always recorded: refusing to update would mean warning on every launch
 * forever after one legitimate upgrade, and a warning that never clears is
 * one people learn to scroll past.
 */
export async function noteAgentIdentity(
  meridianDir: string,
  agentId: string,
  identity: AgentIdentity,
  fs: IdentityFs = nodeIdentityFs,
): Promise<IdentityComparison> {
  const ledger = await readIdentityLedger(meridianDir, fs);
  const previous = ledger[agentId];

  let change: IdentityChange = 'first-seen';
  let warning: string | undefined;

  if (previous) {
    if (previous.executableDigest === identity.executableDigest) {
      change = 'unchanged';
    } else if (
      previous.assurance === 'verified' &&
      identity.assurance === 'unverified'
    ) {
      change = 'became-unverifiable';
      warning =
        `The binary behind '${agentId}' can no longer be identified. It was ` +
        `${previous.executableDigest} at ${previous.resolvedPath}; now: ` +
        `${identity.unverifiedReason ?? 'no digest could be taken'}. ` +
        `Attribution recorded from here on is labelled unverified.`;
    } else {
      change = 'changed';
      warning =
        `The binary behind '${agentId}' changed under an unchanged name. ` +
        `Was ${previous.executableDigest ?? 'unidentified'} ` +
        `(${previous.resolvedPath ?? previous.command}, first seen ${previous.firstSeenAt}); ` +
        `now ${identity.executableDigest ?? 'unidentified'} ` +
        `(${identity.resolvedPath ?? identity.command}). If you upgraded it, this ` +
        `is expected; if you did not, work recorded against this agent was done ` +
        `by something you have not reviewed.`;
    }
  }

  const updated: RememberedIdentity = {
    agentId,
    command: identity.command,
    resolvedPath: identity.resolvedPath,
    executableDigest: identity.executableDigest,
    assurance: identity.assurance,
    firstSeenAt: previous?.firstSeenAt ?? identity.resolvedAt,
    lastSeenAt: identity.resolvedAt,
  };
  await fs.mkdirp(meridianDir);
  await fs.writeFileText(
    identitiesPath(meridianDir),
    `${JSON.stringify({ ...ledger, [agentId]: updated }, null, 2)}\n`,
  );

  return { change, identity, previous, warning };
}

/**
 * How this identity should be described wherever attribution is shown.
 *
 * One function so the ledger, the surface and any future export agree. An
 * unverified identity that renders as a bare agent name somewhere is the
 * failure `FR-M44-02` is about.
 */
export function describeIdentity(identity: AgentIdentity): string {
  if (identity.assurance === 'verified') {
    return `${identity.resolvedPath} (${identity.executableDigest})`;
  }
  return `${identity.command} — unverified: ${identity.unverifiedReason ?? 'no digest'}`;
}
