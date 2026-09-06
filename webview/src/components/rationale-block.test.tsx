import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NOT_VERIFIED_MARKING, RationaleBlock } from './RationaleBlock';

describe('banned pattern 19 / B12: RationaleBlock marking invariant', () => {
  it('always renders the permanent "not verified" marking', () => {
    render(<RationaleBlock text="I chose the adapter because it was fastest." />);
    expect(screen.getByTestId('rationale-marking')).toHaveTextContent(NOT_VERIFIED_MARKING);
  });

  it('the marking survives empty and hostile input', () => {
    render(<RationaleBlock text={''} />);
    expect(screen.getByTestId('rationale-marking')).toHaveTextContent('not verified');
    expect(screen.getByTestId('rationale-block')).toHaveTextContent('—');
  });

  it('agent prose is rendered as escaped text, never HTML (X-08)', () => {
    render(
      <RationaleBlock text={'<img src=x onerror=alert(1)>plain <b>claim</b>'} />,
    );
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('blockquote b')).toBeNull();
    expect(screen.getByTestId('rationale-block')).toHaveTextContent(
      '<img src=x onerror=alert(1)>plain <b>claim</b>',
    );
  });

  it('strips bidi overrides and control characters from agent prose', () => {
    render(<RationaleBlock text={'safe\u202Eevil'} />);
    const text = screen.getByTestId('rationale-block').textContent ?? '';
    expect(text).not.toContain('\u202E');
    expect(text).toContain('safeevil');
  });
});
