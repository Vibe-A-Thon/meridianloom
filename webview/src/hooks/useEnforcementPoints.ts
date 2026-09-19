import type { WebviewRpcClient } from '../rpc/client';
import type { ControlDeclaration } from '../components/EnforcementBadge';
import { useRpcQuery } from './useRpcQuery';

/**
 * FR-M42-11/12, SEC-32 (MV1-T03): every control's effective enforcement
 * point, fetched once per surface.
 *
 * The sidecar returns the *effective* declaration, so a control whose
 * intended point is the SCM reports `sidecar` while no SCM binding is
 * configured — which is every v1 install (D37). The interface therefore
 * never has to know about that downgrade: it renders what it is given, and
 * what it is given is already true.
 *
 * `lookup` returns `undefined` for a control the sidecar does not declare.
 * That is deliberately not a silent default: `EnforcementBadge` refuses to
 * render without a declaration, so an undeclared control fails loudly at
 * the surface rather than appearing governed and unbounded.
 */
export function useEnforcementPoints(
  client: WebviewRpcClient | undefined,
  enabled = true,
) {
  const query = useRpcQuery(
    enabled ? client : undefined,
    'governance/enforcementPoints',
    {},
  );

  const lookup = (control: string): ControlDeclaration | undefined => {
    const record = query.data?.controls?.[control];
    return record as ControlDeclaration | undefined;
  };

  return { ...query, lookup };
}
