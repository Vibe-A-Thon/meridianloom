import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { VendorTag } from './VendorTag';
import { CONFIDENCE_META, vendorGlyphPath, vendorLabel } from './vendors';

describe('X-27 VendorTag invariant', () => {
  it('composes vendor name, glyph and confidence mark — none is optional', () => {
    render(<VendorTag vendor="claude-code" confidence="direct" />);
    const tag = screen.getByTestId('vendor-tag');
    expect(tag).toHaveTextContent('Claude Code');
    // Two SVGs: the vendor glyph and the confidence mark.
    expect(tag.querySelectorAll('svg')).toHaveLength(2);
    expect(tag.querySelectorAll('svg path')).toHaveLength(2);
  });

  it.each(['direct', 'telemetry', 'inferred'] as const)(
    'accessible name carries the A-09 meaning for %s, not a bare symbol',
    (confidence) => {
      render(<VendorTag vendor="copilot" confidence={confidence} />);
      const tag = screen.getByTestId('vendor-tag');
      expect(tag).toHaveAccessibleName(`Copilot, ${CONFIDENCE_META[confidence].meaning}`);
    },
  );

  it('the three confidence marks are different shapes, never colour alone', () => {
    const paths: string[] = [];
    for (const confidence of ['direct', 'telemetry', 'inferred'] as const) {
      const { unmount } = render(<VendorTag vendor="cursor" confidence={confidence} />);
      const mark = screen
        .getByTestId('vendor-tag')
        .querySelector('[data-confidence] svg path');
      paths.push(mark?.getAttribute('d') ?? '');
      unmount();
    }
    expect(new Set(paths).size).toBe(3);
  });

  it('CSS encodes the confidence in both shape and hue (A-02)', () => {
    const css = readFileSync(path.join(__dirname, 'vendor-tag.module.css'), 'utf8');
    for (const cls of [
      '.confidenceDirect',
      '.confidenceTelemetry',
      '.confidenceInferred',
    ]) {
      expect(css).toContain(cls);
    }
    const rules = [
      css.split('.confidenceDirect')[1]?.split('}')[0],
      css.split('.confidenceTelemetry')[1]?.split('}')[0],
      css.split('.confidenceInferred')[1]?.split('}')[0],
    ];
    expect(new Set(rules).size).toBe(3);
  });

  it('unknown vendors render honestly instead of vanishing (G3)', () => {
    render(<VendorTag vendor="some-future-vendor" confidence="inferred" />);
    const tag = screen.getByTestId('vendor-tag');
    expect(tag).toHaveTextContent('Unknown vendor');
    expect(tag).toHaveAccessibleName(
      `Unknown vendor, ${CONFIDENCE_META.inferred.meaning}`,
    );
  });

  it('every known vendor has a distinct glyph path and a label', () => {
    const paths = new Map<string, string>();
    for (const vendor of [
      'meridian',
      'claude-code',
      'copilot',
      'cursor',
      'codex',
      'devin',
      'gemini',
    ] as const) {
      const path = vendorGlyphPath(vendor);
      expect(path.length, `${vendor} glyph missing`).toBeGreaterThan(0);
      expect(vendorLabel(vendor)).not.toContain('Unknown');
      if (paths.has(path)) {
        throw new Error(`${vendor} and ${paths.get(path)} share a glyph`);
      }
      paths.set(path, vendor);
    }
  });
});
