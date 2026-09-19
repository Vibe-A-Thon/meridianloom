import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConfidenceBar } from './ConfidenceBar';

describe('banned pattern 18: ConfidenceBar never renders without calibration', () => {
  it('renders stated confidence and overlaid calibration error together', () => {
    render(<ConfidenceBar confidence={0.8} calibrationError={0.15} calibrationSamples={42} />);
    expect(screen.getByTestId('confidence-stated')).toHaveTextContent('stated 80%');
    expect(screen.getByTestId('confidence-calibration')).toHaveTextContent(
      'calibration error ±15%',
    );
    expect(screen.getByTestId('confidence-calibration')).toHaveTextContent('over 42');
    expect(screen.getByTestId('calibration-band')).toBeInTheDocument();
  });

  it('the calibration band is overlaid on the claim, spanning ±error', () => {
    render(<ConfidenceBar confidence={0.6} calibrationError={0.2} />);
    const band = screen.getByTestId('calibration-band');
    expect(parseFloat(band.style.left)).toBeCloseTo(40, 5);
    expect(parseFloat(band.style.width)).toBeCloseTo(40, 5);
  });

  it('without history the absence is disclosed in words — never a bare claim', () => {
    render(<ConfidenceBar confidence={0.9} />);
    expect(screen.getByTestId('confidence-bar')).toBeInTheDocument();
    expect(screen.getByTestId('confidence-no-calibration')).toHaveTextContent(
      'no calibration history yet',
    );
    expect(screen.queryByTestId('calibration-band')).toBeNull();
  });

  it('clamps out-of-range and non-finite agent-supplied numbers', () => {
    render(<ConfidenceBar confidence={Number.NaN} calibrationError={3} />);
    expect(screen.getByTestId('confidence-stated')).toHaveTextContent('stated 0%');
    expect(screen.getByTestId('confidence-calibration')).toHaveTextContent('±100%');
  });
});
