import { describe, expect, it } from 'vitest';
import {
  UI_STATE_VERSION,
  readUiState,
  writeUiState,
  type PersistedUiState,
  type VsCodeApi,
} from './vscode-api';

function makeApi(initial?: unknown): VsCodeApi & { state: unknown } {
  const api = {
    state: initial,
    postMessage() {},
    getState<T>() {
      return this.state as T | undefined;
    },
    setState<T>(next: T) {
      this.state = next;
      return next;
    },
  };
  return api;
}

describe('panel revival state (VIGUIX_Final §17)', () => {
  it('round-trips theme and density through setState/getState', () => {
    const api = makeApi();
    const state: PersistedUiState = { theme: 'madder-dusk', density: 'compact' };
    writeUiState(api, state);
    expect(api.state).toEqual({ ...state, version: UI_STATE_VERSION });
    expect(readUiState(api)).toEqual(state);
  });

  it('view-local state survives with the shape it was written in', () => {
    const api = makeApi();
    writeUiState(api, {
      theme: 'follow-vscode',
      density: 'comfortable',
      view: { ledgerFilter: { vendor: 'claude-code' } },
    });
    expect(readUiState(api)?.view).toEqual({ ledgerFilter: { vendor: 'claude-code' } });
  });

  it('a version mismatch discards the stale state instead of trusting it', () => {
    const api = makeApi({ version: UI_STATE_VERSION + 1, theme: 'iron-gall' });
    expect(readUiState(api)).toBeUndefined();
  });

  it('absent or malformed state reads as undefined — the app falls back', () => {
    expect(readUiState(makeApi())).toBeUndefined();
    expect(readUiState(makeApi('garbage'))).toBeUndefined();
    expect(readUiState(makeApi(null))).toBeUndefined();
  });
});
