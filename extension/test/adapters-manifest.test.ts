/**
 * Adapter governance manifest (FR-M34-02, FR-M31-03): an adapter is an ACP
 * agent plus a Meridian governance manifest (Requirements_Final.md §7.9,
 * re-based on ACP). Validation is fail-closed: an invalid manifest makes the
 * adapter unavailable with an actionable error, never a silent skip.
 */
import { describe, expect, it } from 'vitest';
import { parseAdapterManifest, validateAdapterManifest } from '../src/adapters/manifest';

const VALID_YAML = `
adapter:
  id: acme-java-developer
  version: 2.3.0
  provenance: custom
  vendor: acme
acp:
  command: npx
  args: ["-y", "@acme/java-developer@2.3.0", "--acp"]
  env:
    ACME_DISABLE_AUTO_UPDATE: "1"
role:
  fills: [Developer]
  tier: L2
permissions:
  allow: [read, edit, execute]
learning:
  trainable: [policy, rules, memory, calibration]
  frozen: [skills]
governance:
  autonomy_tier: suggest
  probation:
    task_set: probation/
    pass_threshold: 0.85
`;

describe('adapter manifest validation (FR-M31-03, fail-closed)', () => {
  it('accepts a complete manifest', () => {
    const result = parseAdapterManifest(VALID_YAML, 'acme-java-developer/manifest.yaml');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.id).toBe('acme-java-developer');
    expect(result.manifest.version).toBe('2.3.0');
    expect(result.manifest.provenance).toBe('custom');
    expect(result.manifest.vendor).toBe('acme');
    expect(result.manifest.acp).toEqual({
      command: 'npx',
      args: ['-y', '@acme/java-developer@2.3.0', '--acp'],
      env: { ACME_DISABLE_AUTO_UPDATE: '1' },
    });
    expect(result.manifest.roles).toEqual(['Developer']);
    expect(result.manifest.permissions.allow).toEqual(['read', 'edit', 'execute']);
    expect(result.manifest.learning.trainable).toEqual(['policy', 'rules', 'memory', 'calibration']);
    expect(result.manifest.learning.frozen).toEqual(['skills']);
    expect(result.manifest.governance.autonomyTier).toBe('suggest');
    expect(result.manifest.governance.probation).toEqual({
      taskSet: 'probation/',
      passThreshold: 0.85,
    });
  });

  it('applies defaults for optional sections (env, learning, probation)', () => {
    const result = parseAdapterManifest(
      `
adapter: { id: minimal-agent, version: 1.0.0, provenance: prebuilt }
acp: { command: ./agent, args: [acp] }
role: { fills: [Reviewer] }
permissions: { allow: [read] }
`,
      'minimal-agent/manifest.yaml',
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.manifest.acp.env).toEqual({});
    expect(result.manifest.learning).toEqual({ trainable: [], frozen: [] });
    expect(result.manifest.governance.autonomyTier).toBe('suggest');
    expect(result.manifest.governance.probation).toEqual({});
    expect(result.manifest.vendor).toBeUndefined();
  });

  it('rejects unparseable YAML with the source named', () => {
    const result = parseAdapterManifest('adapter: [unclosed', 'broken/manifest.yaml');
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]).toContain('broken/manifest.yaml');
  });

  it.each([
    ['missing adapter section', `acp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /adapter/],
    ['missing acp section', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /acp\.command/],
    ['missing role section', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\npermissions: { allow: [read] }\n`, /role: missing section|role\.fills/],
    ['missing permissions section', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\n`, /permissions: missing section|permissions\.allow/],
    ['bad id shape', `adapter: { id: Not Valid!, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /adapter\.id/],
    ['bad version', `adapter: { id: a-b, version: two, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /adapter\.version/],
    ['bad provenance', `adapter: { id: a-b, version: 1.0.0, provenance: warez }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /adapter\.provenance/],
    ['empty command', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: "" }\nrole: { fills: [A] }\npermissions: { allow: [read] }\n`, /acp\.command/],
    ['unknown permission kind', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [rm-rf] }\n`, /permissions\.allow/],
    ['trainable/frozen overlap', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\nlearning: { trainable: [skills], frozen: [skills] }\n`, /learning/],
    ['bad autonomy tier', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\ngovernance: { autonomy_tier: supreme }\n`, /governance\.autonomy_tier/],
    ['bad pass threshold', `adapter: { id: a-b, version: 1.0.0, provenance: custom }\nacp: { command: x }\nrole: { fills: [A] }\npermissions: { allow: [read] }\ngovernance: { probation: { pass_threshold: 1.7 } }\n`, /pass_threshold/],
  ])('rejects %s with an actionable error', (name, yaml, pattern) => {
    const result = parseAdapterManifest(yaml, `case/${name}/manifest.yaml`);
    expect(result.ok, name).toBe(false);
    if (result.ok) return;
    expect(result.errors.join('\n')).toMatch(pattern);
    expect(result.errors.join('\n')).toContain('manifest.yaml');
  });

  it('collects every error, not just the first', () => {
    const result = parseAdapterManifest(
      `adapter: { version: nope }\nacp: {}\n`,
      'multi/manifest.yaml',
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.errors.length).toBeGreaterThanOrEqual(3);
  });

  it('validateAdapterManifest type-narrows non-objects', () => {
    for (const raw of [null, 42, 'string', [1, 2, 3]]) {
      const result = validateAdapterManifest(raw, 'inline');
      expect(result.ok).toBe(false);
    }
  });
});
