import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * FR-M42-11/12, SEC-32, AC-45 extended — MV1-T03.
 *
 * Two properties, checked over the source of every control surface rather
 * than by rendering each one, because the failure being guarded is a
 * *sentence*: a surface that describes a boundary in its own words drifts
 * from the code that implements that boundary, and nothing notices. Two
 * screens carried exactly such sentences before this phase, and both
 * happened to be right — which is worse, because it proved nothing.
 *
 *   1. A control surface that renders a control renders its declaration.
 *   2. No surface calls anything "enforced" without saying where it binds.
 */

const SURFACES = path.resolve(__dirname);
const REPO = path.resolve(__dirname, '..', '..', '..', '..');

/** Every .tsx under the governance surfaces, excluding tests. */
function surfaceFiles(): string[] {
  return readdirSync(SURFACES)
    .filter((name) => name.endsWith('.tsx') && !name.includes('.test.'))
    .map((name) => path.join(SURFACES, name))
    .filter((file) => statSync(file).isFile());
}

/**
 * Prose with the code stripped out: JSX text and string literals are where
 * a claim about a boundary actually reaches a reader. Comments are removed
 * first — a comment explaining why something is *not* enforced must not
 * trip a check about what the screen says.
 */
function visibleProse(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:])\/\/.*$/gm, '$1 ');
}

describe('AC-45 extended: a control states where it binds', () => {
  it('never presents something as enforced without naming the boundary', () => {
    // The exact failure: a surface that says "enforced" full stop. SEC-32
    // forbids presenting a control as enforced at a boundary where it is
    // not, and an unqualified word is that presentation — the reader
    // supplies the strongest boundary they can imagine.
    //
    // Qualified uses are fine and expected: "not an enforced ceiling",
    // "enforced at the SCM", "cannot be enforced". What is not fine is the
    // bare adjective attached to a control with nothing beside it.
    const offenders: string[] = [];
    for (const file of surfaceFiles()) {
      const prose = visibleProse(readFileSync(file, 'utf8'));
      // Find each occurrence and look at the words around it.
      for (const match of prose.matchAll(/\benforced\b/gi)) {
        const from = Math.max(0, match.index - 60);
        const window = prose.slice(from, match.index + 60).toLowerCase();
        const qualified =
          /\bnot\b|\bcannot\b|\bbefore\b|\bat the\b|\bin the\b|\bin meridian\b|\buntil\b|\brequire/.test(
            window,
          );
        if (!qualified) {
          offenders.push(`${path.basename(file)}: …${prose.slice(from, match.index + 60).trim()}…`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('renders the declaration on the surfaces that carry controls', () => {
    // Gate Room and Cross-Vendor Spend are the two surfaces a buyer uses to
    // decide whether to rely on a control. Both must compose the badge, and
    // the badge itself refuses to render without a declaration — so this
    // assertion plus that invariant is the whole chain.
    for (const name of ['Gates.tsx', 'Analytics.tsx']) {
      const source = readFileSync(path.join(SURFACES, name), 'utf8');
      expect(source, `${name} must render EnforcementBadge`).toContain(
        '<EnforcementBadge',
      );
      expect(source, `${name} must take its declaration from the sidecar`).toContain(
        'useEnforcementPoints',
      );
    }
  });

  it('takes the declaration from the sidecar, never from the markup', () => {
    // The regression this prevents: someone writes the enforcement point as
    // a literal because the RPC is inconvenient in a test. The declaration
    // then stops tracking the code, which is the exact defect MV1-T03 was
    // written to remove.
    for (const file of surfaceFiles()) {
      const source = readFileSync(file, 'utf8');
      if (!source.includes('<EnforcementBadge')) continue;
      expect(
        source,
        `${path.basename(file)} builds a declaration inline instead of fetching it`,
      ).not.toMatch(/declaration=\{\{/);
    }
  });
});

describe('the vocabulary the surfaces render matches the sidecar', () => {
  it('uses exactly the closed FR-M42-11 vocabulary', () => {
    // A point the sidecar can emit and the badge cannot label would render
    // as "Enforcement point unrecognised" in front of a customer. The two
    // lists are in different languages, so nothing but a test holds them
    // together.
    const badge = readFileSync(
      path.join(REPO, 'webview', 'src', 'components', 'EnforcementBadge.tsx'),
      'utf8',
    );
    const sidecar = readFileSync(
      path.join(REPO, 'core', 'meridian_core', 'governance', 'enforcement_points.py'),
      'utf8',
    );
    const vocabulary = [...sidecar.matchAll(/^\s{4}"([a-z_]+)",$/gm)].map((m) => m[1]);
    expect(vocabulary.length).toBeGreaterThanOrEqual(6);

    // Each map is checked on its own. A first version of this test searched
    // the whole file for "<point>:" and passed after a label was deleted,
    // because the same key still existed in the other map — a test that
    // could not fail for the reason it was written. Found by removing a
    // label and watching it stay green.
    const mapBody = (name: string) => {
      const start = badge.indexOf(`const ${name}`);
      expect(start, `${name} not found in EnforcementBadge`).toBeGreaterThan(-1);
      const open = badge.indexOf('{', start);
      const close = badge.indexOf('};', open);
      return badge.slice(open, close);
    };

    for (const name of ['POINT_LABEL', 'POINT_MEANING']) {
      const body = mapBody(name);
      for (const point of vocabulary) {
        expect(body, `${name} has no entry for "${point}"`).toContain(`${point}:`);
      }
    }
  });
});
