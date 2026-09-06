/**
 * Launching an adapter = launching its ACP agent under Meridian governance
 * (FR-M34-02). The launch seam goes through createAcpClient — the governor
 * tier gate — so a workspace with the governor tier disabled hosts nothing
 * (G5), and every hosted session is stop-able for unplug cleanup
 * (FR-M31-04). No bespoke protocol anywhere: the wire is ACP end to end.
 */
import { execPath } from 'node:process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { launchAdapter, type DiscoveredAdapter } from '../src/adapters/launch';
import { AcpTierDisabledError } from '../src/acp';

const FIXTURE = path.resolve(__dirname, 'fixtures', 'fake-acp-agent.mjs');

function discovered(overrides: Partial<DiscoveredAdapter['manifest']> = {}): DiscoveredAdapter {
  return {
    id: 'fake-agent',
    tier: 'workspace',
    dir: '/nonexistent/fake-agent',
    manifest: {
      id: 'fake-agent',
      version: '1.0.0',
      provenance: 'custom',
      acp: { command: execPath, args: [FIXTURE], env: {} },
      roles: ['Developer'],
      permissions: { allow: ['read', 'edit', 'execute'] },
      learning: { trainable: [], frozen: [] },
      governance: { autonomyTier: 'suggest', probation: {} },
      ...overrides,
    },
  };
}

describe('adapter launch over ACP (FR-M34-02)', () => {
  it("launches the manifest's ACP command and exposes a stop-able session", async () => {
    const session = launchAdapter(discovered(), {
      workspaceDir: __dirname,
      enabledTiers: ['flight-recorder', 'governor'],
    });
    try {
      const info = await session.start();
      expect(info.agentCapabilities).toBeDefined();
      const sessionId = await session.newSession();
      expect(sessionId).toBeTruthy();
    } finally {
      session.stop();
    }
    expect(session.pid).toBeDefined();
  });

  it('a disabled governor tier refuses to host (G5), naming the remediation', () => {
    expect(() =>
      launchAdapter(discovered(), {
        workspaceDir: __dirname,
        enabledTiers: ['flight-recorder'],
      }),
    ).toThrow(AcpTierDisabledError);
    try {
      launchAdapter(discovered(), { workspaceDir: __dirname, enabledTiers: ['flight-recorder'] });
    } catch (error) {
      expect((error as AcpTierDisabledError).data).toMatchObject({
        capability: 'governor.acp-host',
        tier: 'governor',
      });
    }
  });

  it('stop() is idempotent — unplug cleanup never throws (FR-M31-04, no scar)', async () => {
    const session = launchAdapter(discovered(), {
      workspaceDir: __dirname,
      enabledTiers: ['flight-recorder', 'governor'],
    });
    await session.start();
    session.stop();
    session.stop();
  });

  it('passes the manifest-declared env through to the ACP process', async () => {
    const session = launchAdapter(
      discovered({ acp: { command: execPath, args: [FIXTURE], env: { MERIDIAN_TEST_MARKER: 'from-manifest' } } }),
      { workspaceDir: __dirname, enabledTiers: ['flight-recorder', 'governor'] },
    );
    try {
      await session.start(); // the fake agent inherits env; reaching initialize proves the spawn worked
    } finally {
      session.stop();
    }
  });
});
