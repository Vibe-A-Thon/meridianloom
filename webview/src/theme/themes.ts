/**
 * Theme and density resolution (VIGUIX_Final §4.4, §5).
 *
 * Resolution order (§5):
 *   1. user explicit choice (persisted UI state)
 *   2. Follow VS Code (the default on first run)
 *   3. Indigo Vat fallback
 * High contrast: VS Code reports it via a `vscode-high-contrast` class on
 * <body>; Iron Gall is then forced regardless of choice, with decorative
 * motion halted and hairlines thickened (§5).
 */

export const THEMES = [
  'indigo-vat',
  'sized-linen',
  'iron-gall',
  'madder-dusk',
  'weld-dawn',
  'loom-ghost',
  'follow-vscode',
] as const;
export type ThemeName = (typeof THEMES)[number];

export const DENSITIES = ['comfortable', 'compact', 'dense'] as const;
export type Density = (typeof DENSITIES)[number];

/** Step 2 of the resolution order — default on first run. */
export const DEFAULT_THEME: ThemeName = 'follow-vscode';
/** Step 3 — used when a persisted choice names a theme that no longer exists. */
export const FALLBACK_THEME: ThemeName = 'indigo-vat';
/** V7 (DECISIONS.md): comfortable is the default density. */
export const DEFAULT_DENSITY: Density = 'comfortable';

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

export function isDensity(value: unknown): value is Density {
  return typeof value === 'string' && (DENSITIES as readonly string[]).includes(value);
}

/** Coerce an untrusted persisted value into a valid theme name. */
export function resolveTheme(value: unknown): ThemeName {
  return isThemeName(value) ? value : FALLBACK_THEME;
}

export function resolveDensity(value: unknown): Density {
  return isDensity(value) ? value : DEFAULT_DENSITY;
}

/**
 * Effective theme under high contrast: Iron Gall always wins (§5). Pure so
 * the rule is unit-testable without a DOM.
 */
export function effectiveTheme(theme: ThemeName, highContrast: boolean): ThemeName {
  return highContrast ? 'iron-gall' : theme;
}

export interface AppliedTheme {
  themeAttr: ThemeName;
  highContrast: boolean;
}

/**
 * Apply the resolved theme to the document. This is the only place that
 * writes the data attributes the token layers in tokens.css key on.
 */
export function applyTheme(
  root: HTMLElement,
  theme: ThemeName,
  density: Density,
  highContrast: boolean,
): AppliedTheme {
  const themeAttr = effectiveTheme(theme, highContrast);
  root.setAttribute('data-ml-theme', themeAttr);
  root.setAttribute('data-ml-density', density);
  root.setAttribute('data-ml-high-contrast', String(highContrast));
  return { themeAttr, highContrast };
}

/**
 * Detect high-contrast mode the way the VS Code webview signals it: a
 * `vscode-high-contrast` class on body. Returns a stable getter the caller
 * can re-run; a MutationObserver subscription is the host's job.
 */
export function detectHighContrast(doc: Document): boolean {
  return doc.body?.classList.contains('vscode-high-contrast') ?? false;
}
