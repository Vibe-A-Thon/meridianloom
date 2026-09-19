/**
 * Wire framing for sidecar JSON-RPC 2.0 (FR-M3-01).
 *
 * Framing decision: newline-delimited JSON (NDJSON). Each message is one
 * complete JSON value serialised by JSON.stringify — which never emits a raw
 * newline — followed by a single "\n". The Python sidecar implements the
 * identical codec in core/meridian_core/rpc.py; both sides must change
 * together. Chosen over Content-Length headers for debuggability (a session
 * can be replayed with `cat`) and because stdio pipes are already
 * byte-stream reliable.
 *
 * FR-M3-09: this encoder is the ONLY writer to the child's stdin and the
 * only consumer of its stdout; stderr is logged, never parsed.
 */

export const MAX_FRAME_BYTES = 16 * 1024 * 1024;

export function encodeFrame(message: unknown): string {
  return JSON.stringify(message) + '\n';
}

export interface FrameDecoder {
  push(chunk: string): unknown[];
}

/**
 * Incremental NDJSON decoder. `push` accepts arbitrary chunks (pipe reads
 * split anywhere) and returns every message completed by this chunk.
 */
export function createFrameDecoder(): FrameDecoder {
  let buffer = '';
  return {
    push(chunk: string): unknown[] {
      buffer += chunk;
      if (buffer.length > MAX_FRAME_BYTES) {
        buffer = '';
        throw new Error(`sidecar frame exceeds ${MAX_FRAME_BYTES} bytes`);
      }
      const messages: unknown[] = [];
      let newline: number;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (line.trim().length === 0) {
          continue;
        }
        messages.push(JSON.parse(line));
      }
      return messages;
    },
  };
}
