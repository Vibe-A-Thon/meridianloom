import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { AgentToken, AGENT_TOKEN_SIZES } from './AgentToken';

describe('X-27 / H2 AgentToken invariants', () => {
  it('renders a VendorTag at every size (all sizes are ≥ 20px)', () => {
    for (const size of AGENT_TOKEN_SIZES) {
      const { unmount } = render(
        <AgentToken
          agentId={`agent-${size}`}
          size={size}
          vendor="claude-code"
          confidence="telemetry"
          provenance="custom"
        />,
      );
      expect(screen.getByTestId('agent-token')).toContainElement(
        screen.getByTestId('vendor-tag'),
      );
      unmount();
    }
  });

  it('≥ 28px renders a ProvenanceTag; 20px does not (v2.1 §9.1)', () => {
    const { unmount } = render(
      <AgentToken
        agentId="big"
        size={40}
        vendor="devin"
        confidence="direct"
        provenance="bridged"
      />,
    );
    expect(screen.getByTestId('agent-token')).toContainElement(
      screen.getByTestId('provenance-tag'),
    );
    expect(screen.getByTestId('provenance-tag')).toHaveTextContent('bridged (langgraph)');
    unmount();

    render(
      <AgentToken
        agentId="small"
        size={20}
        vendor="devin"
        confidence="direct"
        provenance="bridged"
      />,
    );
    expect(screen.queryByTestId('provenance-tag')).toBeNull();
  });

  it('CSS pads the hit area to 28px and keeps the token circular (A-03, §4.3)', () => {
    const css = readFileSync(path.join(__dirname, 'agent-token.module.css'), 'utf8');
    expect(css).toMatch(/min-width:\s*28px/);
    expect(css).toMatch(/min-height:\s*28px/);
    expect(css).toMatch(/border-radius:\s*var\(--ml-r-actor\)/);
    expect(css).toMatch(/--ml-r-actor/);
  });

  it('agent identifiers render verbatim (identity, sanitised)', () => {
    render(
      <AgentToken
        agentId={'architect-agent@2.1.0<img src=x onerror=alert(1)>'}
        size={28}
        vendor="meridian"
        confidence="direct"
        provenance="custom"
      />,
    );
    expect(screen.getByText(/architect-agent@2\.1\.0/)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });

  it('the thread pattern is deterministic per agent id (T9 fallback)', () => {
    const { unmount } = render(
      <AgentToken agentId="same-agent" size={28} vendor="meridian" confidence="direct" provenance="prebuilt" />,
    );
    const first = document
      .querySelector('[data-testid="agent-token"] svg')
      ?.innerHTML;
    unmount();
    render(
      <AgentToken agentId="same-agent" size={28} vendor="meridian" confidence="direct" provenance="prebuilt" />,
    );
    expect(document.querySelector('[data-testid="agent-token"] svg')?.innerHTML).toBe(
      first,
    );
  });
});
