/**
 * X-08 / VIGUIX_Final §17: all agent-produced text is untrusted content.
 * React renders text nodes escaped, and this module is the single funnel
 * every agent-sourced string passes through first — it guarantees a plain
 * string (never markup, never null-prototype surprises) and strips control
 * characters that have no business in prose. It never returns HTML, and no
 * render path in this app injects raw HTML — the guard test in
 * security-guards.test.ts fails the build if one appears.
 */

/** Control chars except tab/newline — invisible text is how prompts hide. */
const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

/** Bidi overrides and isolates — trojan-source vectors in agent text. */
const BIDI = /[\u202A-\u202E\u2066-\u2069]/g;

export function toSafeText(value: unknown): string {
  if (typeof value !== 'string') {
    return '';
  }
  return value.replace(CONTROL_CHARS, '').replace(BIDI, '');
}

/**
 * One-sided clamp for percentages/fractions coming off the bus; agents do
 * not get to supply NaN, Infinity or out-of-range numbers to layout.
 */
export function toSafeFraction(value: unknown, fallback = 0): number {
  const n = typeof value === 'number' ? value : Number.NaN;
  if (!Number.isFinite(n)) {
    return fallback;
  }
  return Math.min(1, Math.max(0, n));
}
