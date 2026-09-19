/**
 * One Meridian suite runs at a time, across languages.
 *
 * The extension suite spawns the real Python sidecar and real ACP agent
 * subprocesses. So does the core pytest suite. Run them together and both
 * starve: startups time out, `waitFor` deadlines expire, and the result is a
 * page of failures that describe the machine rather than the code. That has
 * happened here more than once, and each time the wreckage was read as signal
 * before anyone noticed the two runs.
 *
 * `core/tests/conftest.py` already refused a second *pytest* run. It could
 * not see vitest, so a Python measurement taken beside the extension suite
 * still came back with eleven failures and twice the runtime. The lock is now
 * suite-agnostic — the same file, from both sides — so neither can be started
 * underneath the other by accident.
 *
 * Set `MERIDIAN_ALLOW_CONCURRENT_SUITE=1` to proceed anyway. It is there for
 * the case where someone genuinely means to accept the interference, and for
 * CI, where each job owns its runner and the lock would only be overhead.
 */
import { openSync, closeSync, readFileSync, unlinkSync, writeSync } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

/** Must match `_LOCK` in core/tests/conftest.py. */
const LOCK = path.join(os.tmpdir(), 'meridian-suite.lock');

/**
 * Whether the recorded pid is still running.
 *
 * A crashed run leaves its lock behind, and a stale lock that blocked every
 * future run would be a worse failure than the one being guarded against.
 * `process.kill(pid, 0)` signals nothing and throws if the process is gone;
 * EPERM means it exists and belongs to someone else, which still counts as
 * held.
 */
function holderIsAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

function takeLock(): boolean {
  let handle: number;
  try {
    handle = openSync(LOCK, 'wx');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
    let holder = 0;
    try {
      holder = Number.parseInt(readFileSync(LOCK, 'utf8').trim(), 10);
    } catch {
      holder = 0;
    }
    if (holderIsAlive(holder)) {
      throw new Error(
        // ASCII only: this reaches a console, and on Windows the default code
        // page renders an em-dash as a replacement character.
        `Another Meridian suite run is already going (pid ${holder}); it may ` +
          'be the core pytest suite or another vitest run. Both spawn real ' +
          'sidecar and ACP subprocesses, and two at once starve each other ' +
          'into failures that are not regressions. Wait for it, or set ' +
          'MERIDIAN_ALLOW_CONCURRENT_SUITE=1 if you mean to accept the ' +
          'interference.',
      );
    }
    // The holder is gone; the lock is stale. Take it over.
    try {
      unlinkSync(LOCK);
    } catch {
      /* someone else got there first; the open below decides it */
    }
    handle = openSync(LOCK, 'wx');
  }
  try {
    writeSync(handle, String(process.pid));
  } finally {
    closeSync(handle);
  }
  return true;
}

export default function setup(): () => void {
  if (process.env.MERIDIAN_ALLOW_CONCURRENT_SUITE === '1') return () => {};
  // CI gives each job its own runner, so the lock would only add a way for a
  // crashed run to wedge the next one.
  if (process.env.CI) return () => {};
  takeLock();
  return () => {
    try {
      // Only drop it if it is still ours: a stale-takeover by another run
      // would otherwise be deleted out from under it.
      const holder = Number.parseInt(readFileSync(LOCK, 'utf8').trim(), 10);
      if (holder === process.pid) unlinkSync(LOCK);
    } catch {
      /* already gone */
    }
  };
}
