/**
 * The hosted-session registry seam (FR-M12-06; F1 Workstream B task 11).
 *
 * Hosted ACP sessions register here while they run. When governance halts
 * a hosted session, the sidecar records the halt in the ledger and
 * dispatches a `gate/halt` bus notification; the extension host routes it
 * here, and the registry owns the actual process kill — killing a real
 * session process is the registry's job, never the sidecar's.
 */

/** What the registry needs from a hosted session: a way to stop it. */
export interface HaltableSession {
  halt(reason: string): void;
}

export class HostedSessionRegistry {
  private readonly sessions = new Map<string, HaltableSession>();

  /** Register a running session; returns the unregister callback. */
  register(id: string, session: HaltableSession): () => void {
    this.sessions.set(id, session);
    return () => {
      if (this.sessions.get(id) === session) {
        this.sessions.delete(id);
      }
    };
  }

  /** Halt one session; true when the id was known (and now halted). */
  halt(id: string, reason: string): boolean {
    const session = this.sessions.get(id);
    if (!session) {
      return false;
    }
    this.sessions.delete(id);
    session.halt(reason);
    return true;
  }

  /** True while this host runs the session (the hosted fact, FR-M35-06). */
  has(id: string): boolean {
    return this.sessions.has(id);
  }

  ids(): string[] {
    return [...this.sessions.keys()];
  }
}

/** The process-wide registry the ACP host wires its sessions into. */
export const hostedSessionRegistry = new HostedSessionRegistry();
