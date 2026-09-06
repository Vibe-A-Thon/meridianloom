import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from '../App';
import { getVsCodeApi } from '../host/vscode-api';
import { WebviewRpcClient } from '../rpc/client';
import type { Density, ThemeName } from '../theme/themes';
import { DEFAULT_DENSITY, THEMES } from '../theme/themes';
import { makeHost } from '../test/host-harness';

/**
 * Close-out: every named theme and every density renders the GF0 screens
 * correctly. Theme/density arrive as persisted UI state (VIGUIX_Final §5,
 * §17) and App applies them through the single applyTheme seam, so these
 * tests seed the stub vscode-api state and assert the data attributes the
 * token layers in tokens.css key on — the same attributes theme.test.ts
 * proves the CSS side honours.
 */

const okVerify = () => ({
  ok: true,
  entriesChecked: 4402,
  firstDivergentSequence: null,
  detail: 'chain intact',
  verifiedAt: '2026-09-20T14:22:00Z',
});

const ledgerEntries = () => ({
  entries: [
    {
      sequence: 4402,
      timestamp: '2026-09-20T14:05:00Z',
      storyId: 'edb-12345',
      phase: 'build',
      loopId: 'L2-task',
      loopIteration: 1,
      actorId: 'claude-code',
      actorVersion: '1.0',
      actorKind: 'external',
      policyVersion: 'f0',
      actionType: 'diff',
      confidence: 0.87,
      vendor: 'claude-code',
      observationConfidence: 'telemetry',
      simulated: false,
      entryHash: 'aa'.repeat(32),
      previousHash: 'bb'.repeat(32),
      hasInputBlob: true,
      hasOutputBlob: true,
    },
  ],
});

function seedUiState(theme: ThemeName, density: Density = DEFAULT_DENSITY) {
  getVsCodeApi().setState({ version: 1, theme, density });
}

async function renderScreen() {
  const host = makeHost({
    'observe/sessions': { sessions: [], warnings: [] },
    'ledger.query': ledgerEntries(),
    'ledger.verify': okVerify(),
  });
  const client = new WebviewRpcClient(host.transport, { timeoutMs: 1000 });
  render(<App client={client} />);
  await act(async () => {});
  await host.settle();
  return client;
}

afterEach(() => {
  document.body.classList.remove('vscode-high-contrast');
});

const NAMED_THEMES = THEMES.filter((t) => t !== 'follow-vscode');

describe('screens render under every named theme (§5)', () => {
  it.each(NAMED_THEMES)('renders the recorder under %s', async (theme) => {
    seedUiState(theme);
    const client = await renderScreen();

    expect(document.documentElement.getAttribute('data-ml-theme')).toBe(theme);
    expect(document.documentElement.getAttribute('data-ml-density')).toBe(
      DEFAULT_DENSITY,
    );
    // The weave really renders, tags and Selvage included.
    expect(screen.getAllByTestId('vendor-tag').length).toBeGreaterThan(0);
    expect(screen.getByTestId('selvage-verified')).toBeInTheDocument();
    client.dispose();
  });

  it('high contrast forces Iron Gall regardless of the persisted choice (§5)', async () => {
    seedUiState('madder-dusk');
    document.body.classList.add('vscode-high-contrast');
    const client = await renderScreen();

    expect(document.documentElement.getAttribute('data-ml-theme')).toBe('iron-gall');
    expect(document.documentElement.getAttribute('data-ml-high-contrast')).toBe('true');
    expect(screen.getAllByTestId('vendor-tag').length).toBeGreaterThan(0);
    client.dispose();
  });

  it.each(['comfortable', 'compact', 'dense'] as const)(
    'renders under the %s density with the matching attribute (§4.4)',
    async (density) => {
      seedUiState('indigo-vat', density);
      const client = await renderScreen();

      expect(document.documentElement.getAttribute('data-ml-density')).toBe(density);
      expect(screen.getAllByTestId('vendor-tag').length).toBeGreaterThan(0);
      client.dispose();
    },
  );
});
