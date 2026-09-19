import type { Density, ThemeName } from '../theme/themes';

/**
 * VS Code's webview state API — acquireVsCodeApi() is injected by the host
 * and is available exactly once per session. Typed here so the app compiles
 * outside VS Code (tests, Storybook) where the bridge below substitutes it.
 */
export interface VsCodeApi {
  postMessage(message: unknown): void;
  getState<T>(): T | undefined;
  setState<T>(state: T): T;
}

let cached: VsCodeApi | undefined;

/**
 * The real bridge when running inside the extension host's webview; a
 * same-window stub otherwise. State set on the stub is session-only, which
 * is exactly the failure mode the webview is specified to tolerate
 * (VIGUIX_Final §17: the webview may be destroyed at any time).
 */
function createStubApi(): VsCodeApi {
  let state: unknown;
  return {
    postMessage() {
      // Outside VS Code there is no host; messages are dropped, the data
      // layer surfaces the resulting load failure honestly.
    },
    getState<T>(): T | undefined {
      return state as T | undefined;
    },
    setState<T>(next: T): T {
      state = next;
      return next;
    },
  };
}

export function getVsCodeApi(): VsCodeApi {
  if (cached) {
    return cached;
  }
  const injected = (window as { acquireVsCodeApi?: () => VsCodeApi }).acquireVsCodeApi;
  cached = injected ? injected() : createStubApi();
  return cached;
}

export interface PersistedUiState {
  theme: ThemeName;
  density: Density;
  /** Screen-local state (filters, selection) — schema-versioned on write. */
  view?: Record<string, unknown>;
}

export const UI_STATE_VERSION = 1;

/**
 * Panel revival (VIGUIX_Final §17): the only persistence the webview has is
 * getState/setState. The version field guards against a stale shape after
 * an upgrade; an unversioned or future state is discarded, never trusted.
 */
export function readUiState(api: VsCodeApi): PersistedUiState | undefined {
  const raw = api.getState<unknown>();
  if (typeof raw !== 'object' || raw === null) {
    return undefined;
  }
  const candidate = raw as { version?: unknown; theme?: unknown; density?: unknown };
  if (candidate.version !== UI_STATE_VERSION) {
    return undefined;
  }
  return {
    theme: candidate.theme as ThemeName,
    density: candidate.density as Density,
    view: (candidate as { view?: Record<string, unknown> }).view,
  };
}

export function writeUiState(api: VsCodeApi, state: PersistedUiState): void {
  api.setState({ ...state, version: UI_STATE_VERSION });
}
