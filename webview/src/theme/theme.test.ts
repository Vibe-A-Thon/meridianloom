import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import {
  DEFAULT_DENSITY,
  DEFAULT_THEME,
  DENSITIES,
  FALLBACK_THEME,
  THEMES,
  applyTheme,
  detectHighContrast,
  effectiveTheme,
  resolveDensity,
  resolveTheme,
} from './themes';

const TOKENS_CSS = readFileSync(path.join(__dirname, 'tokens.css'), 'utf8');

describe('VIGUIX_Final §4–§6 token layers', () => {
  it('ships exactly the six named themes plus follow-vscode (§5)', () => {
    expect(THEMES).toEqual([
      'indigo-vat',
      'sized-linen',
      'iron-gall',
      'madder-dusk',
      'weld-dawn',
      'loom-ghost',
      'follow-vscode',
    ]);
    for (const theme of THEMES) {
      expect(TOKENS_CSS).toContain(`[data-ml-theme='${theme}']`);
    }
  });

  it('every theme defines the full semantic token set', () => {
    const required = [
      '--ml-ground-canvas',
      '--ml-ground-raised',
      '--ml-ground-card',
      '--ml-hairline',
      '--ml-border',
      '--ml-text-primary',
      '--ml-text-secondary',
      '--ml-text-tertiary',
      '--ml-text-disabled',
      '--ml-dye-working',
      '--ml-dye-attention',
      '--ml-dye-rework',
      '--ml-dye-approved',
      '--ml-dye-meta',
      '--ml-dye-idle',
    ];
    for (const theme of THEMES) {
      const block = TOKENS_CSS.split(`[data-ml-theme='${theme}']`)[1]?.split('}')[0] ?? '';
      for (const token of required) {
        expect(block, `${theme} missing ${token}`).toContain(`${token}:`);
      }
    }
  });

  it('resolution order: follow-vscode default, Indigo Vat fallback (§5)', () => {
    expect(DEFAULT_THEME).toBe('follow-vscode');
    expect(FALLBACK_THEME).toBe('indigo-vat');
    expect(resolveTheme('nonsense')).toBe('indigo-vat');
    expect(resolveTheme('weld-dawn')).toBe('weld-dawn');
    expect(resolveDensity('dense')).toBe('dense');
    expect(resolveDensity(null)).toBe(DEFAULT_DENSITY);
  });

  it('density default is comfortable (V7)', () => {
    expect(DEFAULT_DENSITY).toBe('comfortable');
    expect(DENSITIES).toEqual(['comfortable', 'compact', 'dense']);
  });

  it('§4.4 density deltas are token-layer overrides', () => {
    expect(TOKENS_CSS).toContain("[data-ml-density='compact']");
    expect(TOKENS_CSS).toContain("[data-ml-density='dense']");
    expect(TOKENS_CSS).toMatch(/--ml-row-height:\s*26px/);
    expect(TOKENS_CSS).toMatch(/--ml-row-height:\s*22px/);
    expect(TOKENS_CSS).toMatch(/--ml-weave-row-height:\s*15px/);
    expect(TOKENS_CSS).toMatch(/--ml-weave-row-height:\s*9px/);
    expect(TOKENS_CSS).toMatch(/--ml-body-size:\s*12px/);
  });

  it('§4.3 radius carries meaning: three values only', () => {
    const matches = TOKENS_CSS.match(/--ml-r-[a-z]+:/g) ?? [];
    expect(new Set(matches)).toEqual(
      new Set(['--ml-r-thread:', '--ml-r-panel:', '--ml-r-actor:']),
    );
    expect(TOKENS_CSS).toMatch(/--ml-r-actor:\s*50%/);
  });

  it('§6.1 type ramp is defined with the documented fallback stacks', () => {
    for (const step of [
      '--ml-t-display',
      '--ml-t-h1',
      '--ml-t-h2',
      '--ml-t-h3',
      '--ml-t-body',
      '--ml-t-ui',
      '--ml-t-small',
      '--ml-t-data',
      '--ml-t-data-lg',
      '--ml-t-code',
    ]) {
      expect(TOKENS_CSS).toContain(`${step}:`);
    }
    expect(TOKENS_CSS).toContain("'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif");
    expect(TOKENS_CSS).toContain(
      "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
    );
    expect(TOKENS_CSS).toMatch(/--ml-t-display:\s*600 34px\/1\.05/);
  });

  it('follow-vscode derives ground and linen from --vscode-* variables (§17)', () => {
    const block =
      TOKENS_CSS.split("[data-ml-theme='follow-vscode']")[1]?.split('}')[0] ?? '';
    expect(block).toContain('var(--vscode-editor-background');
    expect(block).toContain('var(--vscode-editor-foreground');
    expect(block).toContain('var(--vscode-descriptionForeground');
  });

  it('--ml-halt is defined exactly once, outside every theme block (§4.1)', () => {
    const occurrences = TOKENS_CSS.match(/--ml-halt:/g) ?? [];
    expect(occurrences).toHaveLength(1);
    const themeBlocks = TOKENS_CSS.split("[data-ml-theme=").slice(1);
    for (const block of themeBlocks) {
      expect(block.split('}')[0]).not.toContain('--ml-halt:');
    }
  });
});

describe('theme application', () => {
  it('applyTheme writes the data attributes the token layers key on', () => {
    const root = document.createElement('html');
    applyTheme(root, 'madder-dusk', 'compact', false);
    expect(root.getAttribute('data-ml-theme')).toBe('madder-dusk');
    expect(root.getAttribute('data-ml-density')).toBe('compact');
    expect(root.getAttribute('data-ml-high-contrast')).toBe('false');
  });

  it('high contrast forces Iron Gall regardless of choice (§5)', () => {
    const root = document.createElement('html');
    expect(effectiveTheme('sized-linen', true)).toBe('iron-gall');
    const applied = applyTheme(root, 'sized-linen', 'comfortable', true);
    expect(applied.themeAttr).toBe('iron-gall');
    expect(root.getAttribute('data-ml-theme')).toBe('iron-gall');
    expect(root.getAttribute('data-ml-high-contrast')).toBe('true');
  });

  it('detectHighContrast reads the vscode-high-contrast body class', () => {
    document.body.classList.add('vscode-high-contrast');
    expect(detectHighContrast(document)).toBe(true);
    document.body.classList.remove('vscode-high-contrast');
    expect(detectHighContrast(document)).toBe(false);
  });
});
