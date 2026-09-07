/**
 * FR-M12-06 host half: the sidecar's `gate/halt` notification routes to the
 * hosted-session registry (which owns the process kill), and the halt is
 * always surfaced as a visible warning — never silent governance.
 */
import { describe, expect, it } from 'vitest';
import {
  asGateHaltNotification,
  handleGateHaltNotification,
} from '../src/governance/gate-halt';
import { HostedSessionRegistry } from '../src/governance/session-registry';

const HALT = { sequence: 42, sessionId: 'acp-session-7', reason: 'credential leak' };

function fixture() {
  const registry = new HostedSessionRegistry();
  const warnings: string[] = [];
  return { registry, warnings, deps: { registry, warn: (m: string) => warnings.push(m) } };
}

describe('gate/halt notification routing (FR-M12-06)', () => {
  it('halts a registered session and warns with the reason', () => {
    const { registry, warnings, deps } = fixture();
    let haltedWith: string | undefined;
    registry.register(HALT.sessionId, { halt: (reason) => (haltedWith = reason) });

    const handled = handleGateHaltNotification('gate/halt', HALT, deps);

    expect(handled).toBe(true);
    expect(haltedWith).toBe('credential leak');
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('acp-session-7');
    expect(warnings[0]).toContain('seq 42');
    expect(warnings[0]).toContain('credential leak');
  });

  it('a session is halted exactly once even if the notification repeats', () => {
    const { registry, deps } = fixture();
    let calls = 0;
    registry.register(HALT.sessionId, { halt: () => calls++ });
    handleGateHaltNotification('gate/halt', HALT, deps);
    handleGateHaltNotification('gate/halt', HALT, deps);
    expect(calls).toBe(1);
  });

  it('warns plainly when no such session is running', () => {
    const { warnings, deps } = fixture();
    const handled = handleGateHaltNotification('gate/halt', HALT, deps);
    expect(handled).toBe(true);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('no such session');
  });

  it('does not claim other notifications', () => {
    const { registry, warnings, deps } = fixture();
    expect(handleGateHaltNotification('tiers/set', { tiers: [] }, deps)).toBe(false);
    expect(handleGateHaltNotification('gate/halt', { nope: true }, deps)).toBe(false);
    expect(warnings).toHaveLength(0);
    expect(registry.ids()).toHaveLength(0);
  });

  it('asGateHaltNotification validates the wire shape', () => {
    expect(asGateHaltNotification('gate/halt', HALT)).toEqual(HALT);
    expect(asGateHaltNotification('gate/halt', { sequence: 'x', sessionId: 's', reason: 'r' })).toBeUndefined();
    expect(asGateHaltNotification('other', HALT)).toBeUndefined();
  });
});

describe('HostedSessionRegistry', () => {
  it('register/unregister lifecycle', () => {
    const registry = new HostedSessionRegistry();
    const unregister = registry.register('s1', { halt: () => undefined });
    expect(registry.ids()).toEqual(['s1']);
    unregister();
    expect(registry.ids()).toEqual([]);
    expect(registry.halt('s1', 'r')).toBe(false);
  });

  it('a second register of the same id replaces the first', () => {
    const registry = new HostedSessionRegistry();
    let first = 0;
    let second = 0;
    const unregisterFirst = registry.register('s1', { halt: () => first++ });
    registry.register('s1', { halt: () => second++ });
    // Unregistering the FIRST session's handle must not drop the second.
    unregisterFirst();
    expect(registry.halt('s1', 'r')).toBe(true);
    expect(first).toBe(0);
    expect(second).toBe(1);
    // A halt consumes the session: the next one is unknown.
    expect(registry.halt('s1', 'r')).toBe(false);
  });
});
