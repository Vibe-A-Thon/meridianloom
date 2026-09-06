import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';
import * as vscode from 'vscode';
import {
  RECORDER_TITLE,
  RECORDER_VIEW_TYPE,
  RecorderPanel,
  buildPanelHtml,
  getNonce,
  resolveWebviewDist,
} from '../src/recorder-panel';

/**
 * VIGUIX_Final §17 as executable assertions: CSP nonce on every webview,
 * default-src 'none', every resource via asWebviewUri, localResourceRoots
 * pinned to the bundle directory, serializer registered for revival.
 */

const SAMPLE_INDEX = `<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>Meridian Loom</title>
    <script type="module" crossorigin src="./assets/index-BI7uVXe-.js"></script>
    <link rel="stylesheet" href="./assets/index-Cf-NOZyb.css" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
`;

function fakeDist(): { extensionRoot: string; distDir: string } {
  const extensionRoot = mkdtempSync(path.join(tmpdir(), 'meridian-ext-'));
  const distDir = path.join(extensionRoot, 'webview-dist');
  mkdirSync(path.join(distDir, 'assets'), { recursive: true });
  writeFileSync(path.join(distDir, 'index.html'), SAMPLE_INDEX);
  writeFileSync(path.join(distDir, 'assets', 'index-BI7uVXe-.js'), '// bundle');
  writeFileSync(path.join(distDir, 'assets', 'index-Cf-NOZyb.css'), '/* styles */');
  return { extensionRoot, distDir };
}

/** Poll until fn stops throwing (async work landing on the thread pool). */
async function until(fn: () => void, timeoutMs = 2000): Promise<void> {
  const start = Date.now();
  for (;;) {
    try {
      fn();
      return;
    } catch (error) {
      if (Date.now() - start > timeoutMs) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }
}

describe('buildPanelHtml — CSP and resource rules', () => {
  const cspSource = 'https://webview.vscode-cdn.net';

  it("injects CSP with default-src 'none' and a nonce on script-src", () => {
    const html = buildPanelHtml({
      indexHtml: SAMPLE_INDEX,
      resolveUri: (asset) => `vscode-resource://x/${asset}`,
      cspSource,
      nonce: 'NONCE123',
    });
    expect(html).toContain('<meta http-equiv="Content-Security-Policy"');
    expect(html).toMatch(/default-src 'none'/);
    expect(html).toMatch(/script-src 'nonce-NONCE123'/);
    expect(html).toMatch(new RegExp(`style-src ${cspSource.replace(/[/.]/g, '\\$&')}`));
    expect(html).toMatch(/img-src https:\/\/webview\.vscode-cdn\.net data:/);
    expect(html).toMatch(/font-src https:\/\/webview\.vscode-cdn\.net/);
  });

  it('the script tag carries the same nonce as the CSP', () => {
    const nonce = getNonce();
    const html = buildPanelHtml({
      indexHtml: SAMPLE_INDEX,
      resolveUri: (asset) => `vscode-resource://x/${asset}`,
      cspSource,
      nonce,
    });
    expect(html).toContain(`nonce="${nonce}" src=`);
    expect(html).toContain(`script-src 'nonce-${nonce}'`);
  });

  it('rewrites every asset through the resolver (asWebviewUri in production)', () => {
    const resolved: string[] = [];
    const html = buildPanelHtml({
      indexHtml: SAMPLE_INDEX,
      resolveUri: (asset) => {
        resolved.push(asset);
        return `vscode-resource://bundle/${asset}`;
      },
      cspSource,
      nonce: 'N',
    });
    expect(resolved).toEqual(['./assets/index-BI7uVXe-.js', './assets/index-Cf-NOZyb.css']);
    expect(html).not.toContain('src="./assets/');
    expect(html).not.toContain('href="./assets/');
    expect(html).toContain('vscode-resource://bundle/./assets/index-BI7uVXe-.js');
  });

  it('nonces are unique per call', () => {
    expect(getNonce()).not.toBe(getNonce());
  });
});

describe('resolveWebviewDist — both install shapes', () => {
  it('finds a dist directory containing index.html (packaged shape)', async () => {
    const { extensionRoot, distDir } = fakeDist();
    await expect(resolveWebviewDist(extensionRoot)).resolves.toBe(distDir);
  });

  it('throws an actionable error when the bundle is missing', async () => {
    const empty = mkdtempSync(path.join(tmpdir(), 'meridian-empty-'));
    await expect(resolveWebviewDist(empty)).rejects.toThrow(/npm run build/);
  });
});

describe('RecorderPanel — host behaviour under the vscode mock', () => {
  beforeEach(() => {
    // Dispose any singleton left over from a previous test (before __reset
    // clears the inspection array), so each test gets a fresh panel.
    for (const panel of [...vscode.__createdWebviewPanels]) {
      panel.dispose();
    }
    vscode.__reset();
  });

  const deps = (extensionRoot: string) => ({
    extensionPath: extensionRoot,
    enabledTiers: () => ['flight-recorder'] as const,
    sidecar: () => undefined,
    onError: (message: string) => {
      throw new Error(`panel configure failed: ${message}`);
    },
  });

  it('createOrShow builds a panel with pinned localResourceRoots and CSP html', async () => {
    const { extensionRoot, distDir } = fakeDist();
    RecorderPanel.createOrShow(deps(extensionRoot));
    const panel = vscode.__createdWebviewPanels[0]!;
    expect(panel.viewType).toBe(RECORDER_VIEW_TYPE);
    expect(panel.title).toBe(RECORDER_TITLE);
    // configure() is async (fs access): wait for the html to land, then
    // assert every �17 property of it.
    await until(() => expect(panel.webview.html).toContain("default-src 'none'"));
    const roots = panel.webview.options.localResourceRoots ?? [];
    expect(roots).toHaveLength(1);
    expect((roots[0] as unknown as { fsPath: string }).fsPath).toBe(distDir);
    expect(panel.webview.html).toMatch(/nonce="[^"]+" src="vscode-resource:\/\//);
  });

  it('second createOrShow reveals the existing panel instead of duplicating', () => {
    const { extensionRoot } = fakeDist();
    const first = RecorderPanel.createOrShow(deps(extensionRoot));
    const second = RecorderPanel.createOrShow(deps(extensionRoot));
    expect(second).toBe(first);
    expect(vscode.__createdWebviewPanels).toHaveLength(1);
    expect(vscode.__createdWebviewPanels[0]!.revealed).toBe(true);
  });

  it('dispose clears the singleton so the next open builds fresh', () => {
    const { extensionRoot } = fakeDist();
    const panel = RecorderPanel.createOrShow(deps(extensionRoot));
    panel.dispose();
    expect(vscode.__createdWebviewPanels[0]!.disposed).toBe(true);
  });

  it('registers the serializer for panel revival after reload', () => {
    const { extensionRoot } = fakeDist();
    RecorderPanel.registerSerializer(
      { subscriptions: [], secrets: undefined, extensionPath: extensionRoot } as never,
      deps(extensionRoot),
    );
    expect(vscode.__webviewSerializers.has(RECORDER_VIEW_TYPE)).toBe(true);
  });

  it('round-trips a webview RPC through the real dispatch path', async () => {
    const { extensionRoot } = fakeDist();
    RecorderPanel.createOrShow({
      ...deps(extensionRoot),
      sidecar: () => ({
        request: async (method: string) =>
          method === 'observe/sessions' ? { sessions: [], warnings: ['w'] } : {},
      }),
    });
    await new Promise((resolve) => setImmediate(resolve));
    const webview = vscode.__createdWebviewPanels[0]!.webview;
    await webview.receiveMessage({ type: 'rpc/request', id: 1, method: 'observe/sessions', params: {} });
    await until(() => expect(webview.postedMessages.length).toBeGreaterThan(0));
    expect(webview.postedMessages).toEqual([
      {
        type: 'rpc/response',
        id: 1,
        result: { sessions: [], warnings: ['w'] },
      },
    ]);
  });

  it('surfaces the structured tier error without a sidecar call', async () => {
    const { extensionRoot } = fakeDist();
    RecorderPanel.createOrShow(deps(extensionRoot));
    await new Promise((resolve) => setImmediate(resolve));
    const webview = vscode.__createdWebviewPanels[0]!.webview;
    await webview.receiveMessage({
      type: 'rpc/request',
      id: 2,
      method: 'gate.evaluate',
      params: { storyId: 's', gate: 'security' },
    });
    await until(() => expect(webview.postedMessages.length).toBeGreaterThan(0));
    const reply = webview.postedMessages[0] as { error: { code: number; data: { tier: string } } };
    expect(reply.error.code).toBe(-32003);
    expect(reply.error.data.tier).toBe('governor');
  });
});
