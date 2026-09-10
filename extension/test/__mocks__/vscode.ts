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
export const __executedCommands: Array<{ command: string; args: unknown[] }> = [];
export const __registeredTreeProviders = new Map<string, unknown>();
export const __registeredWebviewViewProviders = new Map<string, unknown>();
export const __shownErrors: string[] = [];
export const __shownWarnings: string[] = [];
export const __shownInfos: string[] = [];
export const __quickPickCalls: Array<{ items: unknown[]; options?: unknown }> = [];
/**
 * Choices consumed by show*Message calls that pass button items: the first
 * entry is returned by the next such call (modal confirmation, action pick).
 */
export const __messageChoices: string[] = [];
export const __progressCalls: ProgressOptions[] = [];
export const __statusBarItems: Array<{ text: string; tooltip: unknown; shown: boolean }> = [];
export const __configuration = new Map<string, unknown>();
export const __extensions = new Map<string, unknown>();
export const __outputChannels = new Map<
  string,
  { lines: string[]; shown: boolean; disposed: boolean }
>();
export const __workspaceFolders: Array<{ uri: Uri; name: string }> = [];
export const __contextKeys = new Map<string, unknown>();
export const __createdWebviewPanels: MockWebviewPanel[] = [];
export const __webviewSerializers = new Map<string, { deserializeWebviewPanel(panel: unknown): Promise<void> }>();

export enum ViewColumn {
  One = 1,
  Two = 2,
  Three = 3,
  Beside = -2,
  Active = -1,
}

/** Headless WebviewPanel/Webview pair with the surface the panel host uses. */
export class MockWebviewPanel {
  readonly webview = new MockWebview();
  revealed = false;
  disposed = false;
  private readonly disposeListeners = new Set<() => void>();

  constructor(
    readonly viewType: string,
    readonly title: string,
  ) {}

  reveal(): void {
    this.revealed = true;
  }

  onDidDispose(listener: () => void): Disposable {
    this.disposeListeners.add(listener);
    return new Disposable(() => this.disposeListeners.delete(listener));
  }

  dispose(): void {
    if (!this.disposed) {
      this.disposed = true;
      for (const listener of [...this.disposeListeners]) {
        listener();
      }
    }
  }
}

export class MockWebview {
  html = '';
  options: WebviewOptions = { enableScripts: false };
  readonly cspSource = 'https://webview.vscode-cdn.net';
  readonly localResourceRoots: Uri[] = [];
  readonly postedMessages: unknown[] = [];
  private readonly messageListeners = new Set<(message: unknown) => void>();

  asWebviewUri(uri: Uri): { toString(): string } {
    return { toString: () => `vscode-resource://webview${uri.fsPath}` };
  }

  onDidReceiveMessage(listener: (message: unknown) => void): Disposable {
    this.messageListeners.add(listener);
    return new Disposable(() => this.messageListeners.delete(listener));
  }

  async postMessage(message: unknown): Promise<boolean> {
    this.postedMessages.push(message);
    return true;
  }

  /** Test hook: a webview → host message, as the real runtime delivers it. */
  async receiveMessage(message: unknown): Promise<void> {
    for (const listener of [...this.messageListeners]) {
      await listener(message);
    }
  }
}

export interface WebviewOptions {
  enableScripts?: boolean;
  retainContextWhenHidden?: boolean;
  localResourceRoots?: Uri[];
}

const __configChangeEmitter = new EventEmitter<{ affectsConfiguration(section: string): boolean }>();

/** Fire a configuration-change event; affectsConfiguration matches the given sections. */
export function __fireConfigurationChange(...sections: string[]): void {
  __configChangeEmitter.fire({
    affectsConfiguration: (section: string) => sections.includes(section),
  });
}

let __lastProgressToken: ManualCancellationToken | undefined;

export function __lastToken(): ManualCancellationToken {
  if (!__lastProgressToken) {
    throw new Error('withProgress has not been called yet');
  }
  return __lastProgressToken;
}

export function __reset(): void {
  __registeredCommands.clear();
  __executedCommands.length = 0;
  __registeredTreeProviders.clear();
  __registeredWebviewViewProviders.clear();
  __shownErrors.length = 0;
  __shownWarnings.length = 0;
  __shownInfos.length = 0;
  __quickPickCalls.length = 0;
  __messageChoices.length = 0;
  __progressCalls.length = 0;
  __statusBarItems.length = 0;
  __configuration.clear();
  __extensions.clear();
  __outputChannels.clear();
  __workspaceFolders.length = 0;
  __contextKeys.clear();
  __createdWebviewPanels.length = 0;
  __webviewSerializers.clear();
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

  async setContext(key: string, value: unknown): Promise<void> {
    __contextKeys.set(key, value);
  },

  async executeCommand(command: string, ...args: unknown[]): Promise<unknown> {
    __executedCommands.push({ command, args });
    // The real API exposes context keys only via `executeCommand('setContext', …)`.
    if (command === 'setContext') {
      __contextKeys.set(args[0] as string, args[1]);
      return undefined;
    }
    // Built-in window management command: VS Code owns it, so the mock
    // records the invocation (tests assert it) and succeeds silently.
    if (command === 'vscode.openFolder') {
      return undefined;
    }
    const handler = __registeredCommands.get(command);
    if (handler) {
      return handler(...args);
    }
    throw new Error(`unknown command: ${command}`);
  },
};

export const window = {
  registerTreeDataProvider(viewId: string, provider: unknown): Disposable {
    __registeredTreeProviders.set(viewId, provider);
    return new Disposable(() => {
      __registeredTreeProviders.delete(viewId);
    });
  },

  createWebviewPanel(
    viewType: string,
    title: string,
    _column: unknown,
    options?: WebviewOptions,
  ): MockWebviewPanel {
    const panel = new MockWebviewPanel(viewType, title);
    if (options) {
      panel.webview.options = options;
      if (options.localResourceRoots) {
        panel.webview.localResourceRoots.push(...options.localResourceRoots);
      }
    }
    __createdWebviewPanels.push(panel);
    return panel;
  },

  /**
   * The Activity Bar surface: a webview-typed view resolved on container
   * reveal. The mock records the provider so activation can assert that
   * selecting the plugin opens the workbench with no command in between.
   */
  registerWebviewViewProvider(
    viewId: string,
    provider: unknown,
    _options?: { webviewOptions?: { retainContextWhenHidden?: boolean } },
  ): Disposable {
    __registeredWebviewViewProviders.set(viewId, provider);
    return new Disposable(() => {
      __registeredWebviewViewProviders.delete(viewId);
    });
  },

  registerWebviewPanelSerializer(
    viewType: string,
    serializer: { deserializeWebviewPanel(panel: unknown): Promise<void> },
  ): Disposable {
    __webviewSerializers.set(viewType, serializer);
    return new Disposable(() => {
      __webviewSerializers.delete(viewType);
    });
  },

  async showErrorMessage(
    message: string,
    ...items: Array<string | { modal: boolean }>
  ): Promise<string | undefined> {
    __shownErrors.push(message);
    return items.some((i) => typeof i === 'string') ? __messageChoices.shift() : undefined;
  },

  async showWarningMessage(
    message: string,
    ...items: Array<string | { modal: boolean }>
  ): Promise<string | undefined> {
    __shownWarnings.push(message);
    return items.some((i) => typeof i === 'string') ? __messageChoices.shift() : undefined;
  },

  async showInformationMessage(
    message: string,
    ...items: Array<string | { modal: boolean }>
  ): Promise<string | undefined> {
    __shownInfos.push(message);
    return items.some((i) => typeof i === 'string') ? __messageChoices.shift() : undefined;
  },

  async showQuickPick<T>(items: T[] | Thenable<T[]>, options?: unknown): Promise<T | undefined> {
    const resolved = await items;
    __quickPickCalls.push({ items: [...resolved], options });
    if (__messageChoices.length === 0) {
      return undefined;
    }
    const wanted = __messageChoices.shift();
    return resolved.find((item) => {
      const label = typeof item === 'string' ? item : (item as { label?: string }).label;
      return label === wanted;
    });
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

  createStatusBarItem(): StatusBarItem {
    const item = {
      text: '',
      tooltip: undefined as unknown,
      shown: false,
      show() {
        item.shown = true;
      },
      hide() {
        item.shown = false;
      },
      dispose() {
        item.shown = false;
      },
    };
    __statusBarItems.push(item);
    return item;
  },

  createOutputChannel(name: string): OutputChannel {
    let record = __outputChannels.get(name);
    if (!record) {
      record = { lines: [], shown: false, disposed: false };
      __outputChannels.set(name, record);
    }
    const channel: OutputChannel = {
      name,
      appendLine(line: string) {
        record.lines.push(line);
      },
      append(text: string) {
        record.lines.push(text);
      },
      show() {
        record.shown = true;
      },
      hide() {
        record.shown = false;
      },
      dispose() {
        record.disposed = true;
      },
    };
    return channel;
  },
};

export interface OutputChannel {
  readonly name: string;
  appendLine(line: string): void;
  append(text: string): void;
  show(): void;
  hide(): void;
  dispose(): void;
}

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export interface StatusBarItem {
  text: string;
  tooltip: unknown;
  show(): void;
  hide(): void;
  dispose(): void;
}

export const workspace = {
  get isTrusted(): boolean { return true; },
  get workspaceFolders(): Array<{ uri: Uri; name: string }> | undefined {
    return __workspaceFolders.length > 0 ? [...__workspaceFolders] : undefined;
  },

  onDidChangeConfiguration(
    listener: (event: { affectsConfiguration(section: string): boolean }) => void,
  ): Disposable {
    return __configChangeEmitter.event(listener);
  },

  getConfiguration(section?: string) {
    const prefix = section ? `${section}.` : '';
    return {
      get<T>(key: string, defaultValue?: T): T | undefined {
        const full = `${prefix}${key}`;
        return __configuration.has(full)
          ? (__configuration.get(full) as T)
          : defaultValue;
      },
    };
  },
};

export const extensions = {
  getExtension(id: string): { activate(): Promise<unknown> } | undefined {
    const api = __extensions.get(id);
    if (api === undefined) {
      return undefined;
    }
    return { activate: () => Promise.resolve(api) };
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
  extensionPath: string;
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
