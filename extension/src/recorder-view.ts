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

export class RecorderViewProvider implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  private readonly context: ProxyContext;
  private workbenchSubscription: vscode.Disposable | undefined;

  constructor(private readonly deps: RecorderPanelDeps) {
    this.context = createProxyContext(deps);
  }

  /** Push a host event to the view, if one is currently resolved. */
  broadcast(event: HostEvent): void {
    void this.view?.webview.postMessage({ type: 'event', event });
  }

  async resolveWebviewView(view: vscode.WebviewView): Promise<void> {
    this.view = view;
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
