import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(path.join(root, 'shared/ts/webview-messages.ts'), 'utf8');
const expected = Number(source.match(/WEBVIEW_PROTOCOL_VERSION\s*=\s*(\d+)/)?.[1]);
const host = readFileSync(path.join(root, 'extension/dist/extension.js'), 'utf8');
const actual = Number(host.match(/WEBVIEW_PROTOCOL_VERSION\s*=\s*(\d+)/)?.[1]);
const manifest = JSON.parse(readFileSync(path.join(root, 'webview/dist/meridian-webview.json'), 'utf8'));
if (!Number.isSafeInteger(expected) || expected < 1 || actual !== expected || manifest.formatVersion !== 1 || manifest.protocolVersion !== expected) {
  throw new Error(`Meridian build mismatch: source v${expected}, host v${actual}, webview v${manifest.protocolVersion}. Run npm run build at the repository root.`);
}
console.log(`Meridian host and webview are both protocol v${expected}. Reload the Extension Development Host after rebuilding.`);
