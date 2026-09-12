import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { launchAdapter, type LaunchTarget } from '../src/adapters/launch';
import {
  describeIdentity,
  noteAgentIdentity,
  readIdentityLedger,
  resolveAgentIdentity,
  resolveExecutable,
  type AgentIdentity,
  type IdentityFs,
} from '../src/adapters/identity';

/**
 * Verifiable agent identity — `FR-M44-01`/`02`, `AC-52` (MV3-T01b).
 *
 * The claim is narrow and it has to stay narrow: Meridian can identify the
 * **file it resolved from `PATH`**. When the launch command is a run-time
 * package fetcher — `npx`, `uvx`, `pipx run` — that file is the fetcher and
 * the agent is downloaded afterwards, so there is nothing to identify and
 * the identity must say so.
 *
 * The failure this guards against is not an absent check. It is a check that
 * reports the npx shim's digest as the agent's identity, looks like
 * verification, and is worth nothing.
 */

const encoder = new TextEncoder();

function memoryFs(files: Record<string, string>): IdentityFs & {
  files: Map<string, string>;
} {
  const store = new Map(Object.entries(files));
  const missing = (p: string) => {
    const error = new Error(`ENOENT: ${p}`) as NodeJS.ErrnoException;
    error.code = 'ENOENT';
    return error;
  };
  return {
    files: store,
    async readFileBytes(file) {
      const text = store.get(file);
      if (text === undefined) throw missing(file);
      return encoder.encode(text);
    },
    async readFileText(file) {
      const text = store.get(file);
      if (text === undefined) throw missing(file);
      return text;
    },
    async writeFileText(file, contents) {
      store.set(file, contents);
    },
    async stat(file) {
      if (!store.has(file)) throw missing(file);
      return { isFile: () => true };
    },
    async mkdirp() {
      /* directories are implied */
    },
  };
}

const POSIX = { platform: 'linux' as NodeJS.Platform, env: { PATH: '/usr/bin:/usr/local/bin' } };
const WINDOWS = {
  platform: 'win32' as NodeJS.Platform,
  env: { PATH: 'C:\\bin;C:\\tools', PATHEXT: '.COM;.EXE;.CMD' },
};

function sha256(text: string): string {
  return `sha256:${createHash('sha256').update(encoder.encode(text)).digest('hex')}`;
}

describe('finding the file that will actually run', () => {
  it('resolves a bare command against PATH', async () => {
    const fs = memoryFs({ '/usr/local/bin/claude': 'ELF…' });
    await expect(resolveExecutable('claude', { ...POSIX, fs })).resolves.toBe(
      '/usr/local/bin/claude',
    );
  });

  it('takes the first PATH entry that has it, as the shell would', async () => {
    const fs = memoryFs({ '/usr/bin/claude': 'first', '/usr/local/bin/claude': 'second' });
    await expect(resolveExecutable('claude', { ...POSIX, fs })).resolves.toBe(
      '/usr/bin/claude',
    );
  });

  it('honours PATHEXT on Windows', async () => {
    // `claude` on PATH is `claude.cmd`. Resolving only the extensionless name
    // would come back empty on the platform this runs on most.
    const fs = memoryFs({ 'C:\\tools\\claude.CMD': '@echo off' });
    await expect(resolveExecutable('claude', { ...WINDOWS, fs })).resolves.toBe(
      'C:\\tools\\claude.CMD',
    );
  });

  it('uses a path-shaped command directly', async () => {
    const fs = memoryFs({ '/opt/agents/claude': 'ELF…' });
    await expect(
      resolveExecutable('/opt/agents/claude', { ...POSIX, fs }),
    ).resolves.toBe('/opt/agents/claude');
  });

  it('is undefined rather than throwing when nothing is there', async () => {
    const fs = memoryFs({});
    await expect(resolveExecutable('claude', { ...POSIX, fs })).resolves.toBeUndefined();
  });
});

describe('what the identity claims', () => {
  it('an installed executable is verified, by the digest of its bytes', async () => {
    const fs = memoryFs({ '/usr/bin/claude': 'ELF version one' });
    const identity = await resolveAgentIdentity('claude', ['--acp'], { ...POSIX, fs });
    expect(identity.assurance).toBe('verified');
    expect(identity.resolvedPath).toBe('/usr/bin/claude');
    expect(identity.executableDigest).toBe(sha256('ELF version one'));
    expect(identity.unverifiedReason).toBeUndefined();
  });

  it('a run-time package fetcher is NOT verified, and says which', async () => {
    // The load-bearing test. `npx -y @acme/java-developer@2.3.0 --acp` has a
    // real, stable digest — of npx. Reporting that as the agent's identity
    // would look exactly like a check and prove nothing about the code that
    // runs.
    const fs = memoryFs({ '/usr/bin/npx': 'the npm package runner' });
    const identity = await resolveAgentIdentity(
      'npx',
      ['-y', '@acme/java-developer@2.3.0', '--acp'],
      { ...POSIX, fs },
    );
    expect(identity.assurance).toBe('unverified');
    expect(identity.unverifiedReason).toContain('npx');
    expect(identity.unverifiedReason).toContain('not the agent');
    // The digest is still reported — it is true, and it is about npx.
    expect(identity.executableDigest).toBe(sha256('the npm package runner'));
  });

  it.each([
    ['uvx', ['acme-agent']],
    ['bunx', ['acme-agent']],
    ['pipx', ['run', 'acme-agent']],
    ['pnpm', ['dlx', 'acme-agent']],
  ])('%s is a fetcher too', async (command, args) => {
    const fs = memoryFs({ [`/usr/bin/${command}`]: 'runner' });
    const identity = await resolveAgentIdentity(command, args, { ...POSIX, fs });
    expect(identity.assurance).toBe('unverified');
  });

  it('a subcommand that does not fetch is not treated as one', async () => {
    // `pipx` alone installs; `pipx run` fetches. Calling every pipx
    // invocation unverifiable would cry wolf on a legitimate install.
    const fs = memoryFs({ '/usr/bin/pipx': 'installer' });
    const identity = await resolveAgentIdentity('pipx', ['--version'], { ...POSIX, fs });
    expect(identity.assurance).toBe('verified');
  });

  it('a command that is not on PATH is unverified, not an error', async () => {
    const fs = memoryFs({});
    const identity = await resolveAgentIdentity('claude', [], { ...POSIX, fs });
    expect(identity.assurance).toBe('unverified');
    expect(identity.unverifiedReason).toContain('not found on PATH');
  });

  it('never describes an unverified identity as a bare name', async () => {
    // FR-M44-02: attribution under an unverified identity is labelled
    // unverified wherever it is shown.
    const fs = memoryFs({ '/usr/bin/npx': 'runner' });
    const identity = await resolveAgentIdentity('npx', ['-y', 'x'], { ...POSIX, fs });
    expect(describeIdentity(identity)).toContain('unverified');
  });
});

describe('AC-52: a binary swap under an unchanged name', () => {
  const DIR = '/ws/.meridian';

  function identity(digest: string, over: Partial<AgentIdentity> = {}): AgentIdentity {
    return {
      command: 'claude',
      resolvedPath: '/usr/bin/claude',
      executableDigest: digest,
      assurance: 'verified',
      resolvedAt: '2026-09-13T10:00:00.000Z',
      ...over,
    };
  }

  it('the first sighting is not a warning', async () => {
    const fs = memoryFs({});
    const result = await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    expect(result.change).toBe('first-seen');
    expect(result.warning).toBeUndefined();
  });

  it('the same binary twice says nothing', async () => {
    const fs = memoryFs({});
    await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    const again = await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    expect(again.change).toBe('unchanged');
    expect(again.warning).toBeUndefined();
  });

  it('a different binary at the same name warns and names both digests', async () => {
    // The negative control the plan asks for: same declared name, same path,
    // different build. If this does not fire, every attribution recorded
    // afterwards names an agent that did not do the work.
    const fs = memoryFs({});
    await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    const swapped = await noteAgentIdentity(DIR, 'claude-code', identity('sha256:bbb'), fs);
    expect(swapped.change).toBe('changed');
    expect(swapped.warning).toContain('sha256:aaa');
    expect(swapped.warning).toContain('sha256:bbb');
    expect(swapped.warning).toContain('under an unchanged name');
  });

  it('losing the ability to identify it is its own warning', async () => {
    // Replacing an installed binary with an `npx` command is a downgrade in
    // what can be proved, and it would otherwise read as an ordinary change.
    const fs = memoryFs({});
    await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    const lost = await noteAgentIdentity(
      DIR,
      'claude-code',
      identity('sha256:ccc', {
        assurance: 'unverified',
        unverifiedReason: 'npx fetches the agent at launch',
      }),
      fs,
    );
    expect(lost.change).toBe('became-unverifiable');
    expect(lost.warning).toContain('labelled unverified');
  });

  it('records the new identity so the warning does not repeat forever', async () => {
    // A legitimate upgrade must warn once. A warning that never clears is
    // one people learn to scroll past.
    const fs = memoryFs({});
    await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    await noteAgentIdentity(DIR, 'claude-code', identity('sha256:bbb'), fs);
    const third = await noteAgentIdentity(DIR, 'claude-code', identity('sha256:bbb'), fs);
    expect(third.change).toBe('unchanged');
    const ledger = await readIdentityLedger(DIR, fs);
    expect(ledger['claude-code'].executableDigest).toBe('sha256:bbb');
    // The first sighting is kept: "since when" is the question that follows.
    expect(ledger['claude-code'].firstSeenAt).toBe('2026-09-13T10:00:00.000Z');
  });

  it('a corrupt ledger makes an agent first-seen, never falsely swapped', async () => {
    const fs = memoryFs({ '/ws/.meridian/agent-identities.json': '{ not json' });
    const result = await noteAgentIdentity(DIR, 'claude-code', identity('sha256:aaa'), fs);
    expect(result.change).toBe('first-seen');
  });
});

describe('the identity is taken before the agent is spawned', () => {
  const target: LaunchTarget = {
    id: 'acme-java-developer',
    tier: 'workspace',
    dir: '/ws/.meridian/adapters/acme-java-developer',
    manifest: {
      id: 'acme-java-developer',
      version: '1.0.0',
      provenance: 'prebuilt',
      vendor: 'acme',
      roles: ['Developer'],
      acp: { command: 'claude', args: ['--acp'] },
      permissions: ['read'],
    } as LaunchTarget['manifest'],
  };

  it('resolves and reports identity before the process starts', async () => {
    // Ordering is the point. An identity taken after the spawn describes a
    // process that may already be acting, which makes the record a
    // description rather than a check.
    const order: string[] = [];
    const session = launchAdapter(target, {
      workspaceDir: '/ws',
      enabledTiers: ['flight-recorder', 'governor'],
      resolveIdentity: async () => {
        order.push('identify');
        return {
          command: 'claude',
          resolvedPath: '/usr/bin/claude',
          executableDigest: 'sha256:aaa',
          assurance: 'verified',
          resolvedAt: '2026-09-13T10:00:00.000Z',
        };
      },
      onIdentity: async () => {
        order.push('record');
      },
      spawner: () => {
        order.push('spawn');
        throw Object.assign(new Error('spawn refused by the test'), { code: 'ENOENT' });
      },
    });

    expect(session.identity).toBeUndefined(); // nothing claimed before start
    await session.start().catch(() => undefined);
    expect(order).toEqual(['identify', 'record', 'spawn']);
    expect(session.identity?.executableDigest).toBe('sha256:aaa');
  });

  it('a refusal from the identity hook stops the launch', async () => {
    // The hook is awaited so a caller can make a swap fatal. If it were
    // fire-and-forget, the warning would arrive after the agent had work.
    let spawned = false;
    const session = launchAdapter(target, {
      workspaceDir: '/ws',
      enabledTiers: ['flight-recorder', 'governor'],
      resolveIdentity: async () => ({
        command: 'claude',
        assurance: 'unverified',
        unverifiedReason: 'not on PATH',
        resolvedAt: '2026-09-13T10:00:00.000Z',
      }),
      onIdentity: async () => {
        throw new Error('this workspace requires a verified agent identity');
      },
      spawner: () => {
        spawned = true;
        throw new Error('unreachable');
      },
    });

    await expect(session.start()).rejects.toThrow('requires a verified agent identity');
    expect(spawned).toBe(false);
  });
});
