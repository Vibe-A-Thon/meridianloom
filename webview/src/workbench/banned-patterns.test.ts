import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  WORKBENCH_TABS,
  isTabUnlocked,
  type TabTier,
  type WorkbenchTab,
} from './tabs';

/**
 * Banned patterns 28 and 30 — MV1-T13, MVP-R3.7.
 *
 * `mvp-req-final.md` §9.3 used to claim patterns 28–32 were "enforced by
 * component tests". The freeze audit checked and found that true of 29, 31
 * and 32 and false of these two: both were referenced in source comments
 * and nothing asserted them. A document overstating its own enforcement is
 * the same defect as a product overstating its controls (P27), pointed
 * inward — so the claim was narrowed and this file is what makes it true
 * again.
 *
 *   28  an agent-attributed element rendering without its vendor tag
 *   30  an Orchestra surface rendering below the Orchestra tier, *including*
 *       as an empty state
 *
 * Pattern 30's sidecar half is already enforced by a real-sidecar e2e that
 * proves governor and orchestra RPCs are refused at the base tier. That is
 * RPC absence. This is surface absence, and they are different claims: a
 * screen can be in the route table while every call it makes is refused,
 * which is exactly the "empty orchestra" the pattern forbids.
 */

const COMPONENTS = path.resolve(__dirname, '..', 'components');

describe('banned pattern 28: agent attribution always carries its vendor', () => {
  it('AgentToken cannot be constructed without a vendor', () => {
    // Structural, not stylistic: `vendor` is a required prop, so a caller
    // that omits it fails to typecheck rather than rendering an unattributed
    // token. This test pins the requiredness — an optional marker or a
    // default would silently reopen the pattern.
    const source = readFileSync(path.join(COMPONENTS, 'AgentToken.tsx'), 'utf8');
    expect(source).toMatch(/\bvendor:\s*string;/);
    expect(source, 'vendor must not be optional').not.toMatch(/\bvendor\?:/);
    expect(source, 'vendor must not have a default').not.toMatch(
      /vendor\s*=\s*['"`]/,
    );
  });

  it('AgentToken renders the VendorTag rather than reimplementing it', () => {
    // One primitive, composed. Two renderings of a vendor drift, and the
    // drifting one is always the copy nobody remembered existed (J7).
    const source = readFileSync(path.join(COMPONENTS, 'AgentToken.tsx'), 'utf8');
    expect(source).toContain('<VendorTag');
  });

  it('VendorTag cannot be constructed without a vendor or a confidence', () => {
    // The tag is where pattern 28 and pattern 31 meet: a vendor with no
    // confidence reads as a fact, and an `inferred` observation presented
    // as a bare vendor name is the overclaim 31 forbids.
    const source = readFileSync(path.join(COMPONENTS, 'VendorTag.tsx'), 'utf8');
    expect(source).toMatch(/\bvendor:\s*string;/);
    expect(source, 'vendor must not be optional').not.toMatch(/\bvendor\?:/);
    expect(source, 'confidence must be carried').toMatch(/confidence/);
  });
});

describe('banned pattern 30: no Orchestra surface below the Orchestra tier', () => {
  const tiers = (enabled: readonly string[]) =>
    WORKBENCH_TABS.filter((tab) => isTabUnlocked(tab, enabled));

  it('the base tier registers no governor or orchestra surface', () => {
    // "Not registered" is the requirement, not "registered and disabled".
    // A disabled affordance is the scar G5 exists to prevent: it tells the
    // user a thing exists and refuses it, which is worse than not offering
    // it at all.
    const visible = tiers([]);
    const leaked = visible.filter((tab) => tab.tier !== 'flight-recorder');
    expect(leaked.map((t) => t.id)).toEqual([]);
  });

  it('enabling Governor does not enable Orchestra', () => {
    // The tiers are a ladder, not a switch. Turning one on must not carry
    // the next one with it.
    const visible = tiers(['governor']);
    const orchestra = visible.filter((tab) => tab.tier === 'orchestra');
    expect(orchestra.map((t) => t.id)).toEqual([]);
  });

  it.each(['governor', 'orchestra'] as const)(
    'a %s tab is absent, not merely locked, when its tier is off',
    (tier: TabTier) => {
      const gated = WORKBENCH_TABS.filter((tab: WorkbenchTab) => tab.tier === tier);
      if (gated.length === 0) {
        // No tab at this tier yet. The assertion below still has to hold
        // when one is added, which is why the loop is over the registry
        // rather than over a hard-coded list.
        return;
      }
      for (const tab of gated) {
        expect(isTabUnlocked(tab, [])).toBe(false);
        expect(isTabUnlocked(tab, [tier])).toBe(true);
      }
    },
  );

  it('every tab declares a tier, so none can default into the base', () => {
    // The failure this catches is a new tab added without a tier: a missing
    // field would make `isTabUnlocked` compare against undefined and the tab
    // would be locked everywhere, or — worse, depending on the comparison —
    // visible everywhere. Neither is a decision anyone made.
    const known: TabTier[] = ['flight-recorder', 'governor', 'orchestra'];
    for (const tab of WORKBENCH_TABS) {
      expect(known, `${tab.id} declares an unknown tier "${tab.tier}"`).toContain(
        tab.tier,
      );
    }
  });
});
