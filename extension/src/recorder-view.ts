/**
 * The Meridian Loom workbench as an Activity Bar **view**.
 *
 * The product requirement is that selecting Meridian Loom in the Activity Bar
 * *is* opening the product — no command, no second click, no palette. VS Code
 * gives exactly one mechanism for that: a `WebviewViewProvider` registered
 * against a `webview`-typed view inside the container. When the container is
 * revealed, `resolveWebviewView` runs and the interface is there.
 *
 * Everything else is shared with `RecorderPanel`, deliberately:
 *
 *  - the same `buildPanelHtml` (CSP with a per-resolve nonce, `default-src
 *    'none'`, `asWebviewUri` for every asset, `localResourceRoots` pinned to
 *    the built bundle);
 *  - the same `dispatchWebviewMessage`, so the tier gate applies identically
 *    whichever surface the user came through;
 *  - the same `ProxyContext`, so a capability cannot exist on one surface and
 *    not the other.
 *
 * `retainContextWhenHidden` is set here where it is not on the panel. A view
 * in the side bar is hidden every time the user switches Activity Bar
 * containers, and losing the workbench on a container switch would be a
 * defect rather than a saving. Correctness still does not depend on it: the
 * webview restores from `getState()` and re-issues its RPCs on boot.
 */
import { readFile } from 'node:fs/promises';
import * as path from 'node:path';
import * as vscode from 'vscode';
import {
  buildPanelHtml,
  getNonce,
  resolveWebviewDist,
  type RecorderPanelDeps,
} from './recorder-panel';
import { dispatchWebviewMessage, type ProxyContext } from './webview/webview-rpc-proxy';
import type { HostEvent } from '../../shared/ts/webview-messages';
import { resolveWorkspaceSource } from './editor-surfaces';

/** Must match the view id contributed in package.json. */
export const RECORDER_VIEW_ID = 'meridianLoom.workbench';

/**
 * The host capabilities the webview may reach. Extracted so the panel and the
 * view cannot drift apart — a capability added for one is added for both.
 */
export function createProxyContext(deps: RecorderPanelDeps): ProxyContext {
  return {
    openEditor: async (file, line) => {
      const root = deps.workspaceDir?.();
      if (!root) throw new Error('Open a workspace before opening a source file.');
      const target = await resolveWorkspaceSource(root, file);
      const editor = await vscode.window.showTextDocument(vscode.Uri.file(target), {
        preview: true,
      });
      const position = new vscode.Position(
        Math.min((line ?? 1) - 1, editor.document.lineCount - 1),
        0,
      );
      editor.selection = new vscode.Selection(position, position);
      editor.revealRange(new vscode.Range(position, position));
    },
    workbench: deps.workbench ? (request) => deps.workbench!.request(request) : undefined,
    hostAction: async (action) => {
      if (action === 'open-settings')
        await vscode.commands.executeCommand('workbench.action.openSettings', 'meridian');
      if (action === 'open-folder')
        await vscode.commands.executeCommand('vscode.openFolder');
    },
    enabledTiers: deps.enabledTiers,
    get sidecar() {
      return deps.sidecar();
    },
    workspaceDir: deps.workspaceDir,
    saveFile: (fileName, content, mimeType) =>
      deps.onDownload?.({
        fileName,
        mimeType: mimeType ?? 'application/json',
        content,
      }),
    pickFile: async () => {
      // The webview has no filesystem. Importing an agent package is a host
      // act: the user chooses the file, the host reads it, and the webview
      // only ever sees the bytes it asked for.
      const picked = await vscode.window.showOpenDialog({
        canSelectMany: false,
        openLabel: 'Import',
        title: 'Import an agent, skill or instruction package',
        filters: {
          'Agent packages': ['md', 'markdown', 'zip', 'json'],
          'All files': ['*'],
        },
      });
      const uri = picked?.[0];
      if (!uri) return undefined;
      const bytes = await vscode.workspace.fs.readFile(uri);
      if (bytes.byteLength > 60_000_000)
        throw new Error('That package is larger than the 60 MB import limit.');
      const fileName = path.basename(uri.fsPath);
      const isArchive = /\.zip$/i.test(fileName);
      return isArchive
        ? { fileName, contentBase64: Buffer.from(bytes).toString('base64') }
        : { fileName, content: Buffer.from(bytes).toString('utf8') };
    },
  };
}

/** Where the workbench interface actually renders. */
export type WorkbenchSurface = 'editor' | 'sidebar';

/**
 * The configured home for the interface, defaulting to the editor area.
 *
 * The Activity Bar container is how the product is *entered* — that part of
 * the requirement is unchanged, and is still the thing no command stands in
 * front of. What changed is where the interface then appears. A sidebar view
 * is a column a few hundred pixels wide, and this is a workbench: nine SDLC
 * phases, agent rosters, ledger tables, metric envelopes, diff review. Those
 * are editor-width surfaces, and squeezing them into a rail made the density
 * choices worse everywhere.
 *
 * `sidebar` remains available because a second monitor is not universal and
 * some people genuinely want the rail. Both paths share the same HTML, the
 * same RPC dispatch and the same tier gate, so neither can quietly grow a
 * capability the other lacks.
 */
export function readWorkbenchSurface(): WorkbenchSurface {
  const configured = vscode.workspace
    .getConfiguration('meridianLoom')
    .get<string>('surface');
  return configured === 'sidebar' ? 'sidebar' : 'editor';
}

/** The launcher's request to (re)open the editor-area workbench. */
const OPEN_EDITOR_SURFACE = 'meridian/openEditorSurface';

function isOpenSurfaceRequest(message: unknown): boolean {
  return (
    typeof message === 'object' &&
    message !== null &&
    (message as { type?: unknown }).type === OPEN_EDITOR_SURFACE
  );
}

/**
 * The compact rail placard shown when the workbench lives in the editor.
 *
 * Deliberately not the application: rendering the full interface here as
 * well would mean two live copies of it, two sets of RPCs against one
 * service, and a user editing the same agent in two places. It carries its
 * own CSP with the same `default-src 'none'` posture as the real panel, and
 * no inline handler — the one script is nonced and does nothing but post a
 * message.
 */
function buildLauncherHtml(nonce: string, cspSource: string): string {
  return [
    '<!DOCTYPE html>',
    '<html lang="en"><head><meta charset="utf-8">',
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; ' +
      `style-src ${cspSource} 'nonce-${nonce}'; script-src 'nonce-${nonce}';">`,
    `<style nonce="${nonce}">`,
    ':root{color-scheme:light dark}',
    'body{margin:0;padding:16px;font:13px var(--vscode-font-family,system-ui);',
    'color:var(--vscode-foreground);background:transparent}',
    'h1{font-size:13px;font-weight:600;margin:0 0 6px}',
    'p{margin:0 0 14px;color:var(--vscode-descriptionForeground);line-height:1.5}',
    'button{width:100%;padding:6px 12px;border:0;border-radius:2px;cursor:pointer;',
    'font:inherit;color:var(--vscode-button-foreground);',
    'background:var(--vscode-button-background)}',
    'button:hover{background:var(--vscode-button-hoverBackground)}',
    'code{font-family:var(--vscode-editor-font-family,monospace)}',
    '</style></head><body>',
    '<h1>Meridian Loom</h1>',
    '<p>The workbench opens in the editor area, where there is room for the ',
    'phase board, agent roster and ledger.</p>',
    `<button type="button" id="open">Open workbench</button>`,
    '<p style="margin-top:14px">Prefer it docked here? Set ',
    '<code>meridianLoom.surface</code> to <code>sidebar</code>.</p>',
    `<script nonce="${nonce}">`,
    'const vscode = acquireVsCodeApi();',
    "document.getElementById('open').addEventListener('click', () => " +
      `vscode.postMessage({ type: '${OPEN_EDITOR_SURFACE}' }));`,
    '</script></body></html>',
  ].join('\n');
}

export class RecorderViewProvider implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  private readonly context: ProxyContext;
  private workbenchSubscription: vscode.Disposable | undefined;

  /**
   * @param openEditorSurface Opens the editor-area workbench. Injected
   *   rather than imported so this module does not depend on the panel's
   *   construction, and so tests can observe the call without a window.
   */
  constructor(
    private readonly deps: RecorderPanelDeps,
    private readonly openEditorSurface?: () => void,
  ) {
    this.context = createProxyContext(deps);
  }

  /** Push a host event to the view, if one is currently resolved. */
  broadcast(event: HostEvent): void {
    void this.view?.webview.postMessage({ type: 'event', event });
  }

  async resolveWebviewView(view: vscode.WebviewView): Promise<void> {
    this.view = view;

    // Selecting Meridian Loom in the Activity Bar still *is* opening the
    // product — no command in between. It now opens in the editor area, and
    // the rail keeps a placard so a closed tab can be reopened without the
    // palette (resolveWebviewView does not fire again once resolved).
    if (readWorkbenchSurface() === 'editor') {
      const nonce = getNonce();
      view.webview.options = { enableScripts: true, localResourceRoots: [] };
      view.webview.html = buildLauncherHtml(nonce, view.webview.cspSource);
      view.webview.onDidReceiveMessage((message: unknown) => {
        if (isOpenSurfaceRequest(message)) this.openEditorSurface?.();
      });
      view.onDidDispose(() => {
        if (this.view === view) this.view = undefined;
      });
      this.openEditorSurface?.();
      return;
    }

    const distDir = await resolveWebviewDist(this.deps.extensionPath);
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(distDir)],
    };

    const indexHtml = await readFile(path.join(distDir, 'index.html'), 'utf8');
    const nonce = getNonce();
    view.webview.html = buildPanelHtml({
      indexHtml,
      resolveUri: (asset) => {
        const relative = asset.replace(/^\.\//, '').replace(/^\//, '');
        return view.webview
          .asWebviewUri(vscode.Uri.file(path.join(distDir, relative)))
          .toString();
      },
      cspSource: view.webview.cspSource,
      nonce,
    });

    this.workbenchSubscription?.dispose();
    this.workbenchSubscription = this.deps.workbench?.onDidChange(() => {
      void view.webview.postMessage({
        type: 'event',
        event: { kind: 'workbench/changed' },
      });
    });

    view.onDidDispose(() => {
      this.workbenchSubscription?.dispose();
      this.workbenchSubscription = undefined;
      if (this.view === view) this.view = undefined;
    });

    view.webview.onDidReceiveMessage((message: unknown) => {
      void dispatchWebviewMessage(message, this.context)
        .then((reply) => {
          if (reply) return view.webview.postMessage(reply);
        })
        .catch((error) => {
          this.deps.onError?.(
            `workbench view message failed: ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
        });
    });
  }

  dispose(): void {
    this.workbenchSubscription?.dispose();
    this.workbenchSubscription = undefined;
    this.view = undefined;
  }
}
