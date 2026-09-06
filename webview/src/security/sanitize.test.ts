import { describe, expect, it } from 'vitest';
import { toSafeFraction, toSafeText } from './sanitize';

describe('X-08 sanitise: agent output is untrusted content', () => {
  it('passes ordinary prose through unchanged', () => {
    expect(toSafeText('I refactored the adapter because…')).toBe(
      'I refactored the adapter because…',
    );
  });

  it('keeps markup as inert text — it is the render layer that escapes it', () => {
    expect(toSafeText('<b>bold claim</b>')).toBe('<b>bold claim</b>');
  });

  it('strips control characters and bidi overrides', () => {
    expect(toSafeText('a\u0000b\u0007c')).toBe('abc');
    expect(toSafeText('left\u202Eright')).toBe('leftright');
    expect(toSafeText('ok\u2066nested')).toBe('oknested');
  });

  it('non-strings become empty text, never undefined crashing the tree', () => {
    expect(toSafeText(undefined)).toBe('');
    expect(toSafeText(null)).toBe('');
    expect(toSafeText(42)).toBe('');
    expect(toSafeText({})).toBe('');
  });

  it('toSafeFraction clamps to 0..1 and rejects NaN/Infinity', () => {
    expect(toSafeFraction(0.5)).toBe(0.5);
    expect(toSafeFraction(4)).toBe(1);
    expect(toSafeFraction(-2)).toBe(0);
    expect(toSafeFraction(Number.NaN, 0.3)).toBe(0.3);
    expect(toSafeFraction(Number.POSITIVE_INFINITY)).toBe(0);
    expect(toSafeFraction('nonsense', 0.1)).toBe(0.1);
  });
});
