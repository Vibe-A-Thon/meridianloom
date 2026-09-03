/**
 * Minimal headless mock of the `vscode` API surface Meridian Loom uses.
 * Aliased in for the real module by vitest.config.ts.
 *
 * Test-facing hooks are prefixed `__` so tests can inspect registrations,
 * shown messages and progress behaviour without a running VS Code.
 */

export class Disposable {
  constructor(private readonly callOnDispose: () => void) {}

  dispose(): void {
    this.callOnDispose();
  }
}

type Listener<T> = (event: T) => void;

export class EventEmitter<T> {
  private readonly listeners = new Set<Listener<T>>();

  readonly event = (listener: Listener<T>): Disposable => {
    this.listeners.add(listener);
    return new Disposable(() => {
      this.listeners.delete(listener);
    });
  };

  fire(data: T): void {
    for (const listener of [...this.listeners]) {
      listener(data);
    }
  }

  dispose(): void {
    this.listeners.clear();
  }
}

export enum TreeItemCollapsibleState {
  None = 0,
  Collapsed = 1,
  Expanded = 2,
}

export class TreeItem {
  collapsibleState: TreeItemCollapsibleState;

  constructor(
    public label?: string,
    collapsibleState: TreeItemCollapsibleState = TreeItemCollapsibleState.None,
  ) {
    this.collapsibleState = collapsibleState;
  }
}

export class ThemeIcon {
  constructor(public readonly id: string) {}
}

export enum ProgressLocation {
  SourceControl = 1,
  Window = 10,
  Notification = 15,
}

export interface CancellationToken {
  readonly isCancellationRequested: boolean;
  onCancellationRequested(listener: () => void): Disposable;
}

/** A cancellation token tests can cancel by hand. */
export class ManualCancellationToken implements CancellationToken {
  private readonly emitter = new EventEmitter<void>();
  isCancellationRequested = false;

  cancel(): void {
    if (!this.isCancellationRequested) {
      this.isCancellationRequested = true;
      this.emitter.fire();
    }
  }

  onCancellationRequested(listener: () => void): Disposable {
    return this.emitter.event(listener);
  }
}

export interface Progress<T> {
  report(value: T): void;
}

export interface ProgressOptions {
  location: ProgressLocation;
  title?: string;
  cancellable?: boolean;
}

type ProgressTask = (
  progress: Progress<{ message?: string; increment?: number }>,
  token: CancellationToken,
) => Thenable<unknown> | unknown;

// ---- Test inspection hooks ------------------------------------------------

export const __registeredCommands = new Map<string, (...args: unknown[]) => unknown>();
export const __registeredTreeProviders = new Map<string, unknown>();
export const __shownErrors: string[] = [];
export const __shownWarnings: string[] = [];
export const __shownInfos: string[] = [];
export const __progressCalls: ProgressOptions[] = [];

let __lastProgressToken: ManualCancellationToken | undefined;

export function __lastToken(): ManualCancellationToken {
  if (!__lastProgressToken) {
    throw new Error('withProgress has not been called yet');
  }
  return __lastProgressToken;
}

export function __reset(): void {
  __registeredCommands.clear();
  __registeredTreeProviders.clear();
  __shownErrors.length = 0;
  __shownWarnings.length = 0;
  __shownInfos.length = 0;
  __progressCalls.length = 0;
  __lastProgressToken = undefined;
}

// ---- API namespaces --------------------------------------------------------

export const commands = {
  registerCommand(id: string, handler: (...args: unknown[]) => unknown): Disposable {
    __registeredCommands.set(id, handler);
    return new Disposable(() => {
      __registeredCommands.delete(id);
    });
  },
};

export const window = {
  registerTreeDataProvider(viewId: string, provider: unknown): Disposable {
    __registeredTreeProviders.set(viewId, provider);
    return new Disposable(() => {
      __registeredTreeProviders.delete(viewId);
    });
  },

  async showErrorMessage(message: string): Promise<undefined> {
    __shownErrors.push(message);
    return undefined;
  },

  async showWarningMessage(message: string): Promise<undefined> {
    __shownWarnings.push(message);
    return undefined;
  },

  async showInformationMessage(message: string): Promise<undefined> {
    __shownInfos.push(message);
    return undefined;
  },

  withProgress(options: ProgressOptions, task: ProgressTask): Promise<unknown> {
    __progressCalls.push(options);
    const token = new ManualCancellationToken();
    __lastProgressToken = token;
    const reported: Array<{ message?: string; increment?: number }> = [];
    const progress: Progress<{ message?: string; increment?: number }> = {
      report: (value) => {
        reported.push(value);
      },
    };
    return Promise.resolve(task(progress, token));
  },
};

export class Uri {
  private constructor(public readonly fsPath: string) {}

  static file(path: string): Uri {
    return new Uri(path);
  }
}

// ---- Extension context -----------------------------------------------------

export interface SecretStorage {
  get(key: string): Thenable<string | undefined>;
  store(key: string, value: string): Thenable<void>;
  delete(key: string): Thenable<void>;
  onDidChange: (listener: Listener<{ key: string }>) => Disposable;
}

export interface ExtensionContext {
  subscriptions: Array<{ dispose(): unknown }>;
  secrets: SecretStorage;
}

/** In-memory SecretStorage that behaves like a working keyring. */
export class MemorySecretStorage implements SecretStorage {
  private readonly values = new Map<string, string>();
  readonly onDidChange = new EventEmitter<{ key: string }>().event;

  async get(key: string): Promise<string | undefined> {
    return this.values.get(key);
  }

  async store(key: string, value: string): Promise<void> {
    this.values.set(key, value);
  }

  async delete(key: string): Promise<void> {
    this.values.delete(key);
  }
}
