import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PreflightDialog, type Preflight } from './PreflightDialog';

/**
 * FR-M40-03, AC-39, B2, B9 — MV2-T06.
 *
 * The invariant: **a run cannot be confirmed from a preflight that could
 * not have shown what it costs.** An incomplete dialog that still offers
 * "Start" is a consent dialog with a hole in it, and the consent it
 * collects is for something the human never saw.
 */

function preflight(over: Partial<Preflight> = {}): Preflight {
  return {
    runId: 'run_20260913T120000_abcd1234',
    origin: 'ui',
    intent: 'Add an idempotency key to the payment submission endpoint',
    adapters: { Developer: 'acme-java-developer', QA: 'acme-qa' },
    repo: 'payments-service',
    baseBranch: 'main',
    branch: 'meridian/run_20260913T120000_abcd1234',
    worktree: '.meridian/worktrees/run_20260913T120000_abcd1234',
    estimateUsd: 3.1,
    costCeilingUsd: 6.0,
    gates: ['DoR', 'Design', 'DoD', 'Security', 'Review'],
    mode: 'dry_run',
    confirmable: true,
    missing: [],
    ...over,
  };
}

describe('the four questions answered before the button', () => {
  it('shows what, who, where, how much, and where it will stop', () => {
    render(
      <PreflightDialog preflight={preflight()} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByTestId('preflight-intent')).toHaveTextContent('idempotency key');
    expect(screen.getByTestId('preflight-adapters')).toHaveTextContent('Developer');
    expect(screen.getByTestId('preflight-target')).toHaveTextContent('payments-service');
    expect(screen.getByTestId('preflight-estimate')).toHaveTextContent('$3.10');
    expect(screen.getByTestId('preflight-estimate')).toHaveTextContent('$6.00');
    expect(screen.getByTestId('preflight-gates')).toHaveTextContent('Security');
  });

  it('puts the worktree promise on the screen, not in the documentation', () => {
    // It is the product's core safety claim, and the moment a human decides
    // whether to trust it is exactly when they should be reading it.
    render(
      <PreflightDialog preflight={preflight()} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByTestId('preflight-worktree')).toHaveTextContent(
      'your working tree is untouched',
    );
  });

  it('records which door the run came through', () => {
    render(
      <PreflightDialog
        preflight={preflight({ origin: 'chat' })}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('preflight-origin')).toHaveTextContent('chat');
  });

  it('never renders an unknown estimate as a free run', () => {
    // P26 on the surface: `null` is unknown, and "$0.00" would tell a human
    // this costs nothing.
    render(
      <PreflightDialog
        preflight={preflight({ estimateUsd: null, confirmable: false, missing: ['estimate'] })}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const estimate = screen.getByTestId('preflight-estimate').textContent ?? '';
    expect(estimate).toContain('not estimated');
    expect(estimate).not.toContain('$0.00');
  });
});

describe('the consent invariant', () => {
  it('cannot be confirmed while an answer is missing', () => {
    const onConfirm = vi.fn();
    render(
      <PreflightDialog
        preflight={preflight({ confirmable: false, missing: ['estimate', 'gates'] })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const confirm = screen.getByTestId('preflight-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('says which answers are missing, in words rather than field names', () => {
    render(
      <PreflightDialog
        preflight={preflight({ confirmable: false, missing: ['estimate'] })}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('preflight-missing')).toHaveTextContent(
      'the cost estimate and ceiling',
    );
  });

  it('confirms a complete dry run in one action', () => {
    const onConfirm = vi.fn();
    render(
      <PreflightDialog preflight={preflight()} onConfirm={onConfirm} onCancel={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('preflight-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe('B9: a live run takes two deliberate actions', () => {
  it('arms before it confirms', () => {
    const onConfirm = vi.fn();
    render(
      <PreflightDialog
        preflight={preflight({ mode: 'live' })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    // A live run writes to a real repository and spends real money. One
    // click is how that happens by accident.
    const arm = screen.getByTestId('preflight-arm');
    fireEvent.click(arm);
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('preflight-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('a dry run does not take two, because it writes nothing', () => {
    const onConfirm = vi.fn();
    render(
      <PreflightDialog preflight={preflight()} onConfirm={onConfirm} onCancel={vi.fn()} />,
    );
    expect(screen.queryByTestId('preflight-arm')).toBeNull();
    fireEvent.click(screen.getByTestId('preflight-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('an armed live run still refuses when an answer is missing', () => {
    // Arming is not consent to an incomplete preflight.
    const onConfirm = vi.fn();
    render(
      <PreflightDialog
        preflight={preflight({ mode: 'live', confirmable: false, missing: ['gates'] })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('preflight-arm')).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe('B2: four states', () => {
  it('loading says nothing has been created yet', () => {
    render(<PreflightDialog onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('preflight-loading')).toHaveTextContent(
      'Nothing has been created yet',
    );
  });

  it('an error is an alert, not a silent empty dialog', () => {
    render(
      <PreflightDialog
        error="The repository has uncommitted changes on main."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('uncommitted changes');
  });

  it('cancelling tells the reader it created nothing', () => {
    // AC-39 on the surface: the reassurance belongs where the decision is
    // made, not only in the ledger afterwards.
    const onCancel = vi.fn();
    render(
      <PreflightDialog preflight={preflight()} onConfirm={vi.fn()} onCancel={onCancel} />,
    );
    expect(screen.getByTestId('preflight-footnote')).toHaveTextContent(
      'Nothing exists until you confirm',
    );
    fireEvent.click(screen.getByTestId('preflight-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
