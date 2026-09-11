import { readFile } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { resolveWorkspaceSource } from './editor-surfaces';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { dispatchWebviewMessage, type ProxyContext } from './webview/webview-rpc-proxy';
import { WEBVIEW_PROTOCOL_VERSION, type HostEvent } from '../../shared/ts/webview-messages';
import type { WorkbenchService } from './workbench';

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
export const RECORDER_TITLE = 'Meridian Loom';

export interface RecorderPanelDeps {
  workbench?: WorkbenchService;
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
  return randomBytes(32).toString('hex');
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
    `default-src 'none'; script-src 'nonce-${nonce}' ${cspSource}; ` +
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
 * Resolve one install shape, then validate its build contract before serving it.
 *  - packaged VSIX: <extensionPath>/webview-dist (populated by
 *    scripts/package-extension.mjs);
 *  - verified development checkout: <repoRoot>/webview/dist only. Packaging
 *    leaves a staging copy inside extension/, which must not shadow a new build.
 */
export async function resolveWebviewDist(extensionPath: string): Promise<string> {
  const repositoryRoot = path.resolve(extensionPath, '..');
  let development = false;
  try {
    const [rootPackage, webviewPackage] = await Promise.all([
      readFile(path.join(repositoryRoot, 'package.json'), 'utf8'),
      readFile(path.join(repositoryRoot, 'webview', 'package.json'), 'utf8'),
    ]);
    development =
      JSON.parse(rootPackage)?.name === 'meridian-loom-root' &&
      JSON.parse(webviewPackage)?.name === 'meridian-loom-webview';
  } catch {
    // Installed extensions do not have the two repository workspace manifests.
  }
  const distDir = development
    ? path.join(repositoryRoot, 'webview', 'dist')
    : path.join(extensionPath, 'webview-dist');
  const recovery = development
    ? 'Run `npm run build` from the repository root, then run Developer: Reload Window.'
    : 'Reinstall the complete Meridian Loom VSIX, then run Developer: Reload Window. For a source checkout, run `npm run build` from its repository root.';
  const { access } = await import('node:fs/promises');
  try {
    await access(path.join(distDir, 'index.html'));
  } catch {
    throw new Error(`The recorder webview bundle is missing at ${distDir}. ${recovery}`);
  }
  const manifestPath = path.join(distDir, 'meridian-webview.json');
  let manifest: unknown;
  try {
    manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  } catch {
    throw new Error(`The recorder webview build manifest is missing or unreadable at ${manifestPath}. ${recovery}`);
  }
  if (
    typeof manifest !== 'object' || manifest === null || Array.isArray(manifest) ||
    !('formatVersion' in manifest) || manifest.formatVersion !== 1 ||
    !('protocolVersion' in manifest) ||
    typeof manifest.protocolVersion !== 'number' || !Number.isSafeInteger(manifest.protocolVersion)
  ) {
    throw new Error(`The recorder webview build manifest is invalid at ${manifestPath}. ${recovery}`);
  }
  if (manifest.protocolVersion !== WEBVIEW_PROTOCOL_VERSION) {
    throw new Error(
      `Meridian webview build mismatch: the running host uses protocol v${WEBVIEW_PROTOCOL_VERSION}, ` +
      `but ${manifestPath} declares v${manifest.protocolVersion}. ${recovery}`,
    );
  }
  return distDir;
}

export class RecorderPanel {
  private static current: RecorderPanel | undefined;
  static broadcast(event: HostEvent): void {
    if (RecorderPanel.current && !RecorderPanel.current.disposed) void RecorderPanel.current.panel.webview.postMessage({ type: 'event', event });
  }

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
        // True now that the editor area is the workbench's primary home
        // rather than a secondary dashboard. An editor tab is backgrounded
        // every time the user looks at a file, and rebuilding the whole
        // interface on the way back — losing scroll position, open panels
        // and in-progress form state — is the wrong trade for a tool people
        // keep open all day. Correctness still does not depend on it: the
        // webview restores from getState() and re-issues its RPCs on boot,
        // which is what the serializer path below continues to exercise.
        retainContextWhenHidden: true,
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
      openEditor: async (file, line) => {
        const root = deps.workspaceDir?.();
        if (!root) throw new Error('Open a workspace before opening a source file.');
        const target = await resolveWorkspaceSource(root, file);
        const editor = await vscode.window.showTextDocument(vscode.Uri.file(target), { preview: true });
        const position = new vscode.Position(Math.min((line ?? 1) - 1, editor.document.lineCount - 1), 0);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(new vscode.Range(position, position));
      },
      workbench: deps.workbench ? request => deps.workbench!.request(request) : undefined,
      hostAction: async action => {
        if (action === 'open-settings') await vscode.commands.executeCommand('workbench.action.openSettings', 'meridian');
        if (action === 'open-folder') await vscode.commands.executeCommand('vscode.openFolder');
      },
      enabledTiers: deps.enabledTiers,
      get sidecar() {
        return deps.sidecar();
      },
      workspaceDir: deps.workspaceDir,
      saveFile: (fileName, content, mimeType) =>
        deps.onDownload?.({ fileName, mimeType: mimeType ?? 'application/json', content }),
    };
    // localResourceRoots must pin exactly what the webview may load: the
    // built bundle directory — nothing else on the extension host's disk.
    void RecorderPanel.configure(panel, deps).catch((error) => {
      deps.onError?.(error instanceof Error ? error.message : String(error));
    });
    panel.onDidDispose(() => {
      workbenchSubscription?.dispose();
      this.disposed = true;
      if (RecorderPanel.current === this) {
        RecorderPanel.current = undefined;
      }
    });
    const workbenchSubscription = deps.workbench?.onDidChange(() => {
      if (!this.disposed) void panel.webview.postMessage({ type: 'event', event: { kind: 'workbench/changed' } });
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
