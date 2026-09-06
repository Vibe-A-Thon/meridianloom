import type { ReactNode } from 'react';
import { RpcError } from '../rpc/client';
import styles from './async-state.module.css';

/**
 * §9.3: every screen specifies empty, loading and error states.
 *  - Loading is thread-tension — there is no spinner in this product.
 *  - Errors state what happened and the next action in the product's
 *    voice — never an apology, never "Something went wrong."
 *  - Empty is an invitation, never an apology.
 */

export function LoadingState({ label }: { label: string }) {
  return (
    <div className={styles.state} role="status" data-testid="loading-state">
      <span className={styles.tension} aria-hidden="true">
        <span className={styles.thread} />
        <span className={styles.thread} />
        <span className={styles.thread} />
        <span className={styles.thread} />
      </span>
      <p className={styles.detail}>{label}</p>
    </div>
  );
}

/** Map a structured RPC failure to an honest sentence (X-14). */
export function describeRpcError(error: unknown): { what: string; next: string } {
  if (error instanceof RpcError) {
    if (error.code === -32003) {
      return {
        what: `That capability belongs to a tier this workspace has not enabled. (${error.message})`,
        next: 'Enable the tier in the meridian.tiers setting, or use what the Recorder tier offers.',
      };
    }
    if (error.code === -32004) {
      return {
        what: 'The ledger is not available — no workspace is configured on the sidecar.',
        next: 'Open a folder, then reload the window so the sidecar picks it up.',
      };
    }
    if (error.code === -32010 || error.code === -32011) {
      return {
        what: error.message,
        next: 'Check that the Meridian sidecar is running (the status bar shows its state), then retry.',
      };
    }
    return { what: error.message, next: 'Retry; if it persists, run Meridian: Doctor.' };
  }
  return {
    what: error instanceof Error ? error.message : String(error),
    next: 'Run Meridian: Doctor for a full diagnostic.',
  };
}

export function ErrorState({ error }: { error: unknown }) {
  const { what, next } = describeRpcError(error);
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert" data-testid="error-state">
      <h3 className={styles.title}>This view cannot update right now</h3>
      <p className={styles.detail}>{what}</p>
      <p className={styles.detail}>{next}</p>
    </div>
  );
}

export function EmptyState({
  title,
  invitation,
  children,
}: {
  title: string;
  invitation: string;
  children?: ReactNode;
}) {
  return (
    <div className={`${styles.state} ${styles.empty}`} data-testid="empty-state">
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.detail}>{invitation}</p>
      {children}
    </div>
  );
}
