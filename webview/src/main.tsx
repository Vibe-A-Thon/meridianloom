import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/archivo/400.css';
import '@fontsource/archivo/500.css';
import '@fontsource/archivo/600.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './theme/tokens.css';
import './global.css';
import { App } from './App';
import { getVsCodeApi } from './host/vscode-api';
import { isHostMessage } from '../../shared/ts/webview-messages';
import { RpcTransport, WebviewRpcClient } from './rpc/client';

/**
 * Transport over the injected VS Code API: outbound through postMessage,
 * inbound via the window 'message' event the host fires.
 */
function createHostTransport(): RpcTransport {
  const api = getVsCodeApi();
  return {
    postMessage(message) {
      api.postMessage(message);
    },
    onMessage(handler) {
      const listener = (event: MessageEvent) => {
        if (isHostMessage(event.data)) {
          handler(event.data);
        }
      };
      window.addEventListener('message', listener);
      return () => window.removeEventListener('message', listener);
    },
  };
}

async function mount() {
  const preview = import.meta.env.DEV && !(window as { acquireVsCodeApi?: unknown }).acquireVsCodeApi;
  const transport = preview ? (await import('./workbench/preview')).createPreviewTransport() : createHostTransport();
  const client = new WebviewRpcClient(transport, { timeoutMs: 30_000 });
  if (preview) getVsCodeApi().setState({ version: 1, theme: 'indigo-vat', density: 'comfortable' });
  createRoot(document.getElementById('root')!).render(<StrictMode><App client={client} preview={preview} /></StrictMode>);
}
void mount();
