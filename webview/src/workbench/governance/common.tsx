import { Children, cloneElement, isValidElement, useId, useRef, useState, type ReactNode } from 'react';
import type { MethodMap, RequestMethod } from '../../../../shared/ts/bus-types';
import type { WebviewRpcClient } from '../../rpc/client';
import type { WorkbenchController } from '../useWorkbench';
import type { ScreenProps } from '../../screens/registry';
import { Dialog } from '../Dialog';
import s from './governance.module.css';

export type GovernanceView = 'gates' | 'approvals' | 'verification' | 'security' | 'pipeline' | 'repositories' | 'trust' | 'calibration' | 'spend';
export type GovernanceProps = Pick<ScreenProps, 'client' | 'ready' | 'workspaceDir' | 'enabledTiers'> & {
  controller: WorkbenchController;
  onNavigate: (route: string) => void;
};
export function useAction(client: WebviewRpcClient) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const inFlight = useRef(false);
  async function run<M extends RequestMethod>(method: M, params: MethodMap[M]['params'], options?: { preserveMessage?: boolean }): Promise<MethodMap[M]['result'] | undefined> {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setBusy(true); setError(undefined); if (!options?.preserveMessage) setMessage(undefined);
    try {
      const result = await client.request(method, params);
      if (result && typeof result === 'object' && (('recorded' in result && result.recorded === false) || ('removed' in result && result.removed === false))) {
        throw new Error('The runtime did not complete this action. Inspect the current state before retrying.');
      }
      return result;
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); return undefined; }
    finally { inFlight.current = false; setBusy(false); }
  }
  return { busy, error, message, run, setError, setMessage };
}
export function Page({ title, eyebrow, description, children, actions }: { title: string; eyebrow: string; description: string; children: ReactNode; actions?: ReactNode }) {
  return <div className={s.page}><header className={s.heading}><div><p className={s.eyebrow}>{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>{actions}</header>{children}</div>;
}
export function Panel({ title, description, children, action }: { title: string; description?: string; children: ReactNode; action?: ReactNode }) {
  return <section className={s.panel}><div className={s.panelHeading}><div><h2>{title}</h2>{description && <p className={s.muted}>{description}</p>}</div>{action}</div>{children}</section>;
}
export function Notice({ children }: { children: ReactNode }) { return <p className={s.notice}>{children}</p>; }
export function Result({ action }: { action: ReturnType<typeof useAction> }) {
  return <>{action.error && <p role="alert" className={s.error}>{action.error} Correct the input or retry the action.</p>}{action.message && <p role="status" className={s.success}>{action.message}</p>}</>;
}
export function QueryFeedback({ query, connected = true }: { query: { status: string; error?: unknown; refresh: () => void }; connected?: boolean }) {
  if (!connected) return <Notice>Connect the workspace runtime to load recorded evidence.</Notice>;
  if (query.status === 'error') return <div role="alert" className={s.error}>{query.error instanceof Error ? query.error.message : String(query.error)} <button onClick={query.refresh}>Retry</button></div>;
  if (query.status === 'loading') return <p role="status">Loading recorded evidence…</p>;
  return null;
}
export function JsonDetail({ title, value }: { title: string; value: unknown }) {
  return <details className={s.details}><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
export function Confirm({ title, description, children, onClose, onConfirm, busy, label = 'Confirm', error }: { title: string; description: string; children?: ReactNode; onClose: () => void; onConfirm: () => void; busy: boolean; label?: string; error?: string }) {
  const [ack, setAck] = useState(false);
  return <Dialog title={title} description={description} onClose={onClose}><div className={s.form}>{children}<label className={s.check}><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />I have reviewed the target and consequences.</label>{error && <p role="alert" className={s.error}>{error}</p>}<div className={s.actions}><button disabled={busy} onClick={onClose}>Cancel</button><button className={s.primary} disabled={!ack || busy} onClick={onConfirm}>{busy ? 'Working…' : label}</button></div></div></Dialog>;
}
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const id = useId();
  return <div className={s.field}><label htmlFor={id}>{label}</label>{Children.map(children, child =>
    isValidElement<{ id?: string; 'aria-describedby'?: string }>(child) && ['input', 'select', 'textarea'].includes(String(child.type))
      ? cloneElement(child, { id, ...(hint ? { 'aria-describedby': `${id}-hint` } : {}) }) : child,
  )}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>;
}
export function parseObject(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Enter a JSON object.');
  return parsed as Record<string, unknown>;
}
export function string(value: unknown) { return typeof value === 'string' ? value : ''; }
export function number(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value : undefined; }
export function money(value: number) { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value); }
export function pct(value: number) { return `${(value * 100).toFixed(1)}%`; }
export function object(value: unknown): Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
export function canGovern(props: GovernanceProps) { return props.ready && props.enabledTiers.includes('governor') && Boolean(props.controller.snapshot?.capabilities.trusted); }
export function GovernanceNotice({ props }: { props: GovernanceProps }) { return !canGovern(props) ? <Notice>Governed actions require a connected, trusted workspace with Governor enabled. Existing local evidence remains available.</Notice> : null; }
