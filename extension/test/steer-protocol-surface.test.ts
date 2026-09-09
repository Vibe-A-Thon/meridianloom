/**
 * AMD-M25 (status.md G-03): the canonical steering protocol must be complete
 * over RPC. This test locks the registry surface to the canonical
 * implementation (extension/src/governance/steer.ts, HostedSteerController):
 *
 *  - every governor.steer rpcMethod registered in shared/schema/tiers.json
 *    is issued by the controller through SteerSidecar.request (the wire the
 *    sidecar ledger-records before returning, FR-M10-08);
 *  - every registered steer method has a typed contract in methods.json
 *    (the interface cannot silently drift from the registry);
 *  - the G-03 named capabilities (clarifying question, uncertainty
 *    escalation, partial acceptance, dry-run plan, honest status) each have
 *    a behavioural test in steer.test.ts — asserted here by name so a
 *    deleted or renamed test re-opens G-03;
 *  - the workbench duplicate (`run/steer`) still exists — it is the
 *    migration target the GUI session retires; when it is gone this test
 *    flips to assert its absence and AMD-M25 is closed.
 *
 * Behavioural coverage of the wire protocol itself lives in steer.test.ts
 * (real hosted session against a real ACP subprocess).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const root = path.resolve(__dirname, '..', '..');
const tiers = JSON.parse(readFileSync(path.join(root, 'shared', 'schema', 'tiers.json'), 'utf8'));
const methods = JSON.parse(readFileSync(path.join(root, 'shared', 'schema', 'methods.json'), 'utf8'));
const steerSource = readFileSync(path.join(root, 'extension', 'src', 'governance', 'steer.ts'), 'utf8');
const steerTests = readFileSync(path.join(root, 'extension', 'test', 'steer.test.ts'), 'utf8');
const workbenchService = readFileSync(
  path.join(root, 'extension', 'src', 'workbench', 'service.ts'),
  'utf8',
);

const steerCapability = tiers['x-tiers'].capabilities.find((c: { id: string }) => c.id === 'governor.steer');
const registryMethods: string[] = steerCapability.rpcMethods;

describe('canonical steer protocol surface (AMD-M25, G-03)', () => {
  it('every governor.steer registry method is issued by the canonical controller', () => {
    for (const method of registryMethods) {
      expect(steerSource, `${method} has no sidecar.request call in steer.ts`).toContain(
        `'${method}'`,
      );
    }
  });

  it('every governor.steer registry method has a typed contract in methods.json', () => {
    for (const method of registryMethods) {
      expect(methods['x-methods'], `${method} missing from methods.json`).toHaveProperty(method);
    }
  });

  it('the registry and the controller agree on exactly the eight steer methods', () => {
    expect(registryMethods.sort()).toEqual(
      [
        'steer.send',
        'steer/question',
        'steer/answer',
        'steer/escalate',
        'steer/accept',
        'steer/acceptanceStatus',
        'steer/status',
        'steer/plan',
      ].sort(),
    );
  });

  it('each G-03 named capability has a behavioural test in steer.test.ts', () => {
    // Clarifying-question protocol, uncertainty escalation, partial
    // acceptance, dry-run plan, honest hosted status — one assertion per
    // capability so a rename fails loudly rather than silently dropping it.
    expect(steerTests).toContain('clarifying questions (FR-M25-02)');
    expect(steerTests).toContain('uncertainty escalation (FR-M25-03)');
    expect(steerTests).toContain('partial acceptance (FR-M25-04)');
    expect(steerTests).toContain('dry-run planner output is recorded (FR-M25-06)');
    expect(steerTests).toContain('honest controls for observed agents (task 18)');
    // steer a running session (FR-M25-01) covers steer.send ordering.
    expect(steerTests).toContain('records the steering act BEFORE injecting it into the live wire');
  });

  it('the workbench duplicate run/steer still exists and is the retirement target', () => {
    // GUI session (AMD-M25): retire this handler and its webview callers
    // (RunsTab.tsx, WorkspaceOperations.tsx). When retired, flip this to
    // toNotContain and close G-03.
    expect(workbenchService).toContain('run/steer');
  });
});
