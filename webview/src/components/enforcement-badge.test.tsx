import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  EnforcementBadge,
  type ControlDeclaration,
} from './EnforcementBadge';

/**
 * FR-M42-11/12, SEC-32, MV1-T02.
 *
 * The invariant these tests hold: a control cannot reach a screen without
 * its enforcement point, and the word "enforced" never appears unqualified.
 * Both were previously matters of review — two screens carried hand-written
 * prose about their own boundaries — and review is what let the enforcement
 * declaration exist in the sidecar for a release without any surface using it.
 */

function declaration(over: Partial<ControlDeclaration> = {}): ControlDeclaration {
  return {
    control: 'merge_gate',
    enforcementPoint: 'sidecar',
    enforced: true,
    vocabularyVersion: 'm42-1',
    boundaryNote:
      'The verdict is computed in the Meridian sidecar. A developer who never ' +
      'installs Meridian and merges directly at the SCM is not intercepted.',
    ...over,
  };
}

describe('EnforcementBadge: a control always states where it binds', () => {
  it('names the boundary, not just that one exists', () => {
    render(<EnforcementBadge declaration={declaration()} />);
    expect(screen.getByTestId('enforcement-point')).toHaveTextContent(
      'Enforced in Meridian',
    );
    expect(screen.getByTestId('enforcement-badge')).toHaveAttribute(
      'data-enforcement-point',
      'sidecar',
    );
  });

  it('says what the boundary means for someone not using Meridian', () => {
    // The consequence is the part a reader actually needs. "Enforced in the
    // editor" sounds strong until you are told who it does not stop.
    render(
      <EnforcementBadge declaration={declaration({ enforcementPoint: 'editor' })} />,
    );
    expect(screen.getByTestId('enforcement-meaning')).toHaveTextContent(
      'someone not using Meridian is not stopped by it',
    );
  });

  it('renders an advisory control as advisory, never as enforced', () => {
    render(
      <EnforcementBadge
        declaration={declaration({
          enforcementPoint: 'advisory_only',
          enforced: false,
        })}
      />,
    );
    const badge = screen.getByTestId('enforcement-badge');
    expect(badge).toHaveAttribute('data-enforced', 'false');
    expect(screen.getByTestId('enforcement-point')).toHaveTextContent('Advisory only');
    expect(screen.getByTestId('enforcement-meaning')).toHaveTextContent(
      'does not intercept',
    );
  });

  it('carries the boundary into the accessible name', () => {
    // A-09's rule applied here: a screen-reader user must not receive a bare
    // "enforced" either. The name carries the point and its consequence.
    render(<EnforcementBadge declaration={declaration({ enforcementPoint: 'ci' })} />);
    const label = screen.getByTestId('enforcement-badge').getAttribute('aria-label');
    expect(label).toContain('Enforced in CI');
    expect(label).toContain('without Meridian installed');
  });

  it('exposes the full boundary note when asked', () => {
    render(<EnforcementBadge declaration={declaration()} verbose />);
    expect(screen.getByTestId('enforcement-meaning')).toHaveTextContent(
      'not intercepted',
    );
  });
});

describe('SEC-32: "enforced" is never unqualified', () => {
  it.each([
    'editor',
    'extension_host',
    'sidecar',
    'scm',
    'ci',
    'advisory_only',
  ] as const)('%s states its boundary in the label', (point) => {
    // The failure this guards is a badge reading just "Enforced". Every
    // label in the vocabulary must say where, or say it is advisory.
    const { unmount } = render(
      <EnforcementBadge declaration={declaration({ enforcementPoint: point })} />,
    );
    const text = screen.getByTestId('enforcement-point').textContent ?? '';
    expect(text.trim()).not.toBe('Enforced');
    expect(text.length).toBeGreaterThan('Enforced'.length);
    unmount();
  });
});

describe('the invariant: no declaration, no quiet render', () => {
  it('throws in development rather than rendering a control with no boundary', () => {
    // This is the whole point of making it a component. A surface that
    // forgets the declaration fails loudly at the point of the mistake,
    // instead of shipping a control that looks governed and is not.
    expect(() => render(<EnforcementBadge declaration={undefined} />)).toThrow(
      /enforcement point/i,
    );
  });

  it('throws on null as well as undefined', () => {
    // `null` is what an RPC that has not resolved yet hands you, and it is
    // the likelier accident of the two.
    expect(() => render(<EnforcementBadge declaration={null} />)).toThrow(
      /FR-M42-11/,
    );
  });
});
