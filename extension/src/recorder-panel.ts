import { readFile } from 'node:fs/promises';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { dispatchWebviewMessage, type ProxyContext } from './webview/webview-rpc-proxy';

/**
 * G0c — the Flight Recorder dashboard webview host (VIGUIX_Final §17):
 *
 *  - CSP with a fresh nonce on every panel creation; default-src 'none';
 *    no inline handlers, no eval, no CDN.
 *  - Every static resource through asWebviewUri, with localResourceRoots
 *    pinned to the built webview bundle directory.
 *  - No retainContextWhenHidden for correctness; revival after reload goes
 *    through WebviewPanelSerializer — the webview restores its own state
 *    from getState() on boot and re-issues its RPCs.
 *  - The panel registers itself under meridian.openRecorder (FR-M1-03 F0
 *    subset per gaps_implementation.md §F0); data flows only through
 *    dispatchWebviewMessage, which applies the tier gate.
 */

export const RECORDER_VIEW_TYPE = 'meridian.recorder';
export const RECORDER_TITLE = 'Meridian Loom Recorder';

export interface RecorderPanelDeps {
  extensionPath: string;
  enabledTiers: ProxyContext['enabledTiers'];
  /** Resolved lazily: the panel outlives individual sidecar connections. */
  sidecar: () => ProxyContext['sidecar'];
  /** Workspace folder handed to the webview in `init` (attrib/hook RPCs). */
  workspaceDir?: () => string | undefined;
  /** 10.45/10.7 Export: the webview asks the host to save a signed bundle
   *  (it has no filesystem of its own, VIGUIX_Final §17). */
  onDownload?: (request: {
    fileName: string;
    mimeType: string;
    content: string;
  }) => Promise<void>;
  onError?: (message: string) => void;
}

/** 256-bit nonce, base64 — CSP nonce plus script-tag nonce must match. */
export function getNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  for (let i = 0; i < 64; i++) {
    nonce += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return nonce;
}

/**
 * Build the served HTML from the Vite bundle's index.html: inject the CSP
 * meta and rewrite every asset URL to its asWebviewUri form with the nonce
 * on the script tag. Pure — the tests assert the security properties of
 * exactly this string.
 */
export function buildPanelHtml(options: {
  indexHtml: string;
  resolveUri: (relativeAssetPath: string) => string;
  cspSource: string;
  nonce: string;
}): string {
  const { indexHtml, resolveUri, cspSource, nonce } = options;
  const csp =
    `default-src 'none'; script-src 'nonce-${nonce}'; ` +
    `style-src ${cspSource}; img-src ${cspSource} data:; font-src ${cspSource};`;

  let html = indexHtml.replace(
    /<head>/i,
    `<head>\n<meta http-equiv="Content-Security-Policy" content="${csp}">`,
  );
  // Rewrite asset references (src/href on script/link) to webview URIs and
  // pin the nonce on the script tag.
  html = html.replace(
    /(<script[^>]*?\s)src="(\.?\/[^"]+)"/i,
    (_match, head: string, asset: string) => `${head}nonce="${nonce}" src="${resolveUri(asset)}"`,
  );
  html = html.replace(
    /(<link[^>]*?\s)href="(\.?\/[^"]+)"/i,
    (_match, head: string, asset: string) => `${head}href="${resolveUri(asset)}"`,
  );
  return html;
}

/**
 * Where the built webview bundle lives, in both install shapes (same
 * two-shape pattern as resolveCoreDir):
 *  - packaged VSIX: <extensionPath>/webview-dist (populated by
 *    scripts/package-extension.mjs);
 *  - development checkout: <repoRoot>/webview/dist.
 */
export async function resolveWebviewDist(extensionPath: string): Promise<string> {
  const candidates = [
    path.join(extensionPath, 'webview-dist'),
    path.resolve(extensionPath, '..', 'webview', 'dist'),
  ];
  const { access } = await import('node:fs/promises');
  for (const candidate of candidates) {
    try {
      await access(path.join(candidate, 'index.html'));
      return candidate;
    } catch {
      // try the next shape
    }
  }
  throw new Error(
    'The recorder webview bundle is missing. Built assets were not found in: ' +
      candidates.join(', ') +
      '. Run `npm run build` from the repository root, or reinstall the extension.',
  );
}

export class RecorderPanel {
  private static current: RecorderPanel | undefined;

  static createOrShow(deps: RecorderPanelDeps): RecorderPanel {
    if (RecorderPanel.current) {
      RecorderPanel.current.panel.reveal();
      return RecorderPanel.current;
    }
    const panel = vscode.window.createWebviewPanel(
      RECORDER_VIEW_TYPE,
      RECORDER_TITLE,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: false,
        localResourceRoots: [],
      },
    );
    RecorderPanel.current = new RecorderPanel(panel, deps);
    return RecorderPanel.current;
  }

  /**
   * Revival after window reload (VIGUIX_Final §17): VS Code hands us the
   * resurrected panel; rebind the document and the message bus. The
   * webview's own script restores its UI from getState() and re-issues its
   * RPCs against this fresh message channel.
   */
  static registerSerializer(
    context: vscode.ExtensionContext,
    deps: RecorderPanelDeps,
  ): vscode.Disposable {
    return vscode.window.registerWebviewPanelSerializer(RECORDER_VIEW_TYPE, {
      deserializeWebviewPanel: async (panel) => {
        RecorderPanel.current = new RecorderPanel(panel, deps);
      },
    });
  }

  private readonly context: ProxyContext;
  private disposed = false;

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    deps: RecorderPanelDeps,
  ) {
    this.context = {
      enabledTiers: deps.enabledTiers,
      get sidecar() {
        return deps.sidecar();
      },
      workspaceDir: deps.workspaceDir,
      saveFile: (fileName, content) =>
        deps.onDownload?.({ fileName, mimeType: 'application/json', content }),
    };
    // localResourceRoots must pin exactly what the webview may load: the
    // built bundle directory — nothing else on the extension host's disk.
    void RecorderPanel.configure(panel, deps).catch((error) => {
      deps.onError?.(error instanceof Error ? error.message : String(error));
    });
    panel.onDidDispose(() => {
      this.disposed = true;
      if (RecorderPanel.current === this) {
        RecorderPanel.current = undefined;
      }
    });
    panel.webview.onDidReceiveMessage((message: unknown) => {
      void dispatchWebviewMessage(message, this.context)
        .then((reply) => {
          if (reply && !this.disposed) {
            return panel.webview.postMessage(reply);
          }
        })
        .catch((error) => {
          deps.onError?.(
            `recorder webview message failed: ${error instanceof Error ? error.message : String(error)}`,
          );
        });
    });
  }

  /** Explicit close (the webview's own chrome also fires onDidDispose). */
  dispose(): void {
    this.panel.dispose();
  }

  private static async configure(panel: vscode.WebviewPanel, deps: RecorderPanelDeps) {
    const distDir = await resolveWebviewDist(deps.extensionPath);
    // Note: retainContextWhenHidden belongs to WebviewPanelOptions
    // (creation-time, set above) — correctness never relies on it
    // (VIGUIX_Final §17); revival goes through the serializer.
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(distDir)],
    };
    const indexHtml = await readFile(path.join(distDir, 'index.html'), 'utf8');
    const nonce = getNonce();
    panel.webview.html = buildPanelHtml({
      indexHtml,
      resolveUri: (asset) => {
        const relative = asset.replace(/^\.\//, '').replace(/^\//, '');
        return panel.webview.asWebviewUri(vscode.Uri.file(path.join(distDir, relative))).toString();
      },
      cspSource: panel.webview.cspSource,
      nonce,
    });
  }
}
