import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { COMMANDS } from '../src/commands';
import { TREE_VIEWS } from '../src/views';

const manifestPath = path.resolve(__dirname, '..', 'package.json');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));

describe('extension manifest', () => {
  it('declares granular activation events and never "*" (FR-M1-01)', () => {
    const events: string[] = manifest.activationEvents;
    expect(Array.isArray(events)).toBe(true);
    expect(events.length).toBeGreaterThan(0);
    expect(events).not.toContain('*');
    for (const event of events) {
      expect(event).not.toBe('*');
      expect(event).not.toMatch(/^onLanguage$/);
    }
    expect(events).toContain('onStartupFinished');
    for (const view of TREE_VIEWS) {
      expect(events).toContain(`onView:${view.id}`);
    }
  });

  it('contributes one Activity Bar container (FR-M1-02)', () => {
    const containers = manifest.contributes.viewsContainers.activitybar;
    expect(containers).toHaveLength(1);
    expect(containers[0].id).toBe('meridian-loom');
  });

  it('contributes exactly the five tree views (FR-M1-02)', () => {
    const views = manifest.contributes.views['meridian-loom'];
    expect(views).toHaveLength(5);
    expect(views.map((v: { id: string }) => v.id)).toEqual(
      TREE_VIEWS.map((v) => v.id),
    );
    expect(views.map((v: { name: string }) => v.name)).toEqual(
      ['Agents', 'Stories', 'Loops', 'Skills', 'Ledger'],
    );
  });

  it('contributes exactly the twelve FR-M1-03 commands', () => {
    const expected = [
      'meridian.ingestStory',
      'meridian.openDashboard',
      'meridian.installSkill',
      'meridian.onboardAgent',
      'meridian.exportAgent',
      'meridian.importAgent',
      'meridian.verifyChain',
      'meridian.haltAll',
      'meridian.steer',
      'meridian.dryRun',
      'meridian.abortStory',
      'meridian.doctor',
    ];
    const contributed = manifest.contributes.commands.map(
      (c: { command: string }) => c.command,
    );
    expect(contributed).toHaveLength(12);
    expect([...contributed].sort()).toEqual([...expected].sort());
    // Code and manifest share one source of truth.
    expect(COMMANDS.map((c) => c.id)).toEqual(contributed);
  });
});
