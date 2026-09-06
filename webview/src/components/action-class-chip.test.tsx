import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ActionClassChip } from './ActionClassChip';
import { TraceSteps, type TraceStepData } from './TraceStep';

describe('banned pattern 25 / E-IN-07: action class is never absent', () => {
  it('the three action classes are shape-distinct, never colour alone', () => {
    const shapes: string[] = [];
    for (const actionClass of ['deterministic', 'assisted', 'generative'] as const) {
      const { unmount } = render(
        <ActionClassChip actionClass={actionClass} whyLlm="x" />,
      );
      shapes.push(
        screen
          .getByTestId('action-class-chip')
          .querySelector('[data-shape]')
          ?.getAttribute('data-shape') ?? '',
      );
      unmount();
    }
    expect(new Set(shapes)).toEqual(
      new Set(['deterministic', 'assisted', 'generative']),
    );
  });

  it('CSS encodes solid / half-filled / hollow squares in the dye tokens', () => {
    const css = readFileSync(path.join(__dirname, 'action-class-chip.module.css'), 'utf8');
    const det = css.split('.shapeDeterministic')[1]?.split('}')[0] ?? '';
    const ass = css.split('.shapeAssisted')[1]?.split('}')[0] ?? '';
    const gen = css.split('.shapeGenerative')[1]?.split('}')[0] ?? '';
    expect(det).toContain('var(--ml-dye-idle)');
    expect(ass).toContain('50%'); /* half-filled */
    expect(gen).toContain('transparent'); /* hollow */
    expect(new Set([det, ass, gen]).size).toBe(3);
  });

  it('why_llm rides on the chip and lands in the accessible name (H5)', () => {
    render(<ActionClassChip actionClass="generative" whyLlm="no deterministic path" />);
    const chip = screen.getByTestId('action-class-chip');
    expect(chip).toHaveAccessibleName('generative — no deterministic path');
    expect(screen.getByTestId('action-class-why')).toHaveTextContent(
      'no deterministic path',
    );
  });

  it('garbage action classes degrade to deterministic, visible and labelled', () => {
    render(
      // Cast: the bus may carry values written before a schema upgrade.
      <ActionClassChip actionClass={'weird' as 'deterministic'} />,
    );
    expect(screen.getByTestId('action-class-chip')).toHaveTextContent('deterministic');
  });

  it('why_llm is sanitised — markup in it renders as text', () => {
    render(
      <ActionClassChip actionClass="assisted" whyLlm={'<script>alert(1)</script>policy'} />,
    );
    expect(document.querySelector('script')).toBeNull();
    expect(screen.getByTestId('action-class-why')).toHaveTextContent(
      '<script>alert(1)</script>policy',
    );
  });
});

describe('TraceStep: every step carries its ActionClassChip (B14)', () => {
  it('renders a chip for every step, whatever the step says', () => {
    const steps: TraceStepData[] = [
      { description: 'parsed the request', actionClass: 'deterministic' },
      { description: 'ranked candidates', actionClass: 'assisted', whyLlm: 'heuristic tie-break' },
      { description: 'drafted the reply', actionClass: 'generative', whyLlm: 'open-ended text' },
    ];
    render(<TraceSteps steps={steps} />);
    const rendered = screen.getAllByTestId('trace-step');
    expect(rendered).toHaveLength(3);
    expect(screen.getAllByTestId('action-class-chip')).toHaveLength(3);
    expect(rendered[0]).toContainElement(screen.getAllByTestId('action-class-chip')[0]!);
    expect(rendered[2]).toContainElement(screen.getAllByTestId('action-class-chip')[2]!);
  });

  it('step descriptions are agent text: escaped, never markup', () => {
    render(
      <TraceSteps
        steps={[
          {
            description: '<img src=x onerror=alert(1)>did the thing',
            actionClass: 'deterministic',
          },
        ]}
      />,
    );
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByTestId('trace-step')).toHaveTextContent(
      '<img src=x onerror=alert(1)>did the thing',
    );
  });
});
