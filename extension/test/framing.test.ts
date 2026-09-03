import { describe, expect, it } from 'vitest';
import { createFrameDecoder, encodeFrame } from '../src/framing';

describe('NDJSON framing (FR-M3-01)', () => {
  it('encodes one message per line', () => {
    expect(encodeFrame({ jsonrpc: '2.0', id: 1, method: 'ping' })).toBe(
      '{"jsonrpc":"2.0","id":1,"method":"ping"}\n',
    );
  });

  it('never emits a raw newline inside a message', () => {
    const frame = encodeFrame({ text: 'line1\nline2' });
    expect(frame.indexOf('\n')).toBe(frame.length - 1);
  });

  it('decodes frames split across arbitrary chunk boundaries', () => {
    const decoder = createFrameDecoder();
    const whole = encodeFrame({ a: 1 }) + encodeFrame({ b: 2 });
    const seen: unknown[] = [];
    for (let i = 0; i < whole.length; i += 3) {
      seen.push(...decoder.push(whole.slice(i, i + 3)));
    }
    expect(seen).toEqual([{ a: 1 }, { b: 2 }]);
  });

  it('decodes multiple frames arriving in one chunk', () => {
    const decoder = createFrameDecoder();
    expect(decoder.push(encodeFrame({ a: 1 }) + encodeFrame({ b: 2 }))).toEqual([
      { a: 1 },
      { b: 2 },
    ]);
  });

  it('ignores blank lines', () => {
    const decoder = createFrameDecoder();
    expect(decoder.push('\n\n' + encodeFrame({ a: 1 }))).toEqual([{ a: 1 }]);
  });

  it('rejects frames larger than the guard limit', () => {
    const decoder = createFrameDecoder();
    expect(() => decoder.push('x'.repeat(17 * 1024 * 1024))).toThrow(/exceeds/);
  });
});
