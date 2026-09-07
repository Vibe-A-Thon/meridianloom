/**
 * The FR-M34-04 policy gate — the Meridian governance layer BETWEEN a hosted
 * agent's session/request_permission and the human. Every request is checked
 * BEFORE the vscode prompt:
 *
 *  1. SEC-28 memory (in-memory): a kind this gate already denied is
 *     auto-denied, citing the prior decision — the human is never re-asked
 *     and re-requesting cannot escalate.
 *  2. SEC-28 memory (durable): prior `permission_decision` rejections for
 *     this adapter are looked up in the ledger ONCE per gate instance (a
 *     restarted host still remembers), and auto-deny with the cited
 *     sequence number.
 *  3. Suspension: a suspended adapter is denied everything.
 *  4. Declared needs: a kind the manifest never declared is denied.
 *  5. Policy allow-list (policy/acp-permissions.yaml): a kind not allowed
 *     for the adapter's autonomy state is denied.
 *
 * Only a request passing all five reaches `humanApprover` (the vscode
 * prompt path). Every decision — allow, human answer, policy denial, SEC-28
 * auto-denial — is ledger-recorded via the acp/permissionDecision sidecar
 * RPC before the agent gets its answer. Recording failures are surfaced
 * through `onRecordError`, never swallowed (G3), and never block the
 * decision itself.
 */
import type { AcpPermissionDecision, PermissionApprover } from '../acp/client';
import type { RequestPermissionRequest } from '../acp/protocol';
import type { AdapterManifest, PermissionKind } from './manifest';
import { PERMISSION_KINDS } from './manifest';
import type { AdapterState } from './probation';
import type { AcpPermissionPolicy } from './policy';

/** The sidecar surface the gate needs (the extension's sidecar RPC client). */
export interface PolicyGateSidecar {
  request(method: string, params: unknown): Promise<unknown>;
}

export interface PolicyGateOptions {
  /** The parsed acp-permissions policy (fail-closed parse result is fine). */
  policy: AcpPermissionPolicy;
  /** The adapter's governance manifest — its declared permission needs. */
  adapter: AdapterManifest;
  /** The adapter's current autonomy state (probation/active/suspended). */
  adapterState: AdapterState;
  /** The vscode prompt path; called only when every check passes. */
  humanApprover: PermissionApprover;
  /** Ledger recording + SEC-28 durable memory; absent => decisions still
   *  happen, but every recording failure is surfaced via onRecordError. */
  sidecar?: PolicyGateSidecar;
  /** Recording/lookup failures are reported here (default: console.error). */
  onRecordError?: (message: string) => void;
}

interface PriorDenial {
  kind: PermissionKind;
  /** The base reason, without the "previously denied" prefix. */
  reason: string;
  /** Ledger sequence of the durable record, when known. */
  sequence?: number;
}

interface LedgerDenialRow {
  sequence?: number;
  actionType?: string;
  decision?: string;
  toolKind?: string;
  reworkReason?: string;
}

function kindNamedIn(text: string | undefined, kind: PermissionKind): boolean {
  if (!text) {
    return false;
  }
  // The durable record carries toolKind inside the encrypted detail blob, so
  // ledger.query rows surface the kind via the recorded reason; match on a
  // word boundary ('read' must not match "already").
  return new RegExp(`\\b${kind}\\b`).test(text);
}

/** The ACP wire type allows null/absent kinds; unrecognised ones deny as 'unknown'. */
function normalizeKind(raw: string | null | undefined): PermissionKind {
  return (PERMISSION_KINDS as readonly string[]).includes(raw ?? '')
    ? (raw as PermissionKind)
    : 'unknown';
}

export function createPolicyGate(options: PolicyGateOptions): PermissionApprover {
  const { policy, adapter, adapterState, humanApprover, sidecar, onRecordError } = options;
  const report = onRecordError ?? ((message: string) => console.error(message));
  /** In-memory SEC-28 memory: the base reason for each denied kind. */
  const denied = new Map<PermissionKind, PriorDenial>();
  /** The durable SEC-28 memory, queried from the ledger once per instance. */
  let ledgerDenials: Promise<PriorDenial[]> | undefined;

  const policyVersion = policy.version >= 1 ? `acp-permissions/v${policy.version}` : undefined;

  const record = async (
    request: RequestPermissionRequest,
    kind: PermissionKind,
    outcome: 'selected' | 'cancelled' | 'denied_by_policy',
    extra: { optionId?: string; reason?: string } = {},
  ): Promise<void> => {
    const params: Record<string, unknown> = {
      sessionId: request.sessionId,
      adapterId: adapter.id,
      toolCallId: request.toolCall.toolCallId,
      toolKind: kind,
      outcome,
      ...(extra.optionId !== undefined ? { optionId: extra.optionId } : {}),
      ...(extra.reason !== undefined ? { reason: extra.reason } : {}),
      ...(policyVersion !== undefined ? { policyVersion } : {}),
    };
    if (!sidecar) {
      report(`acp/permissionDecision not recorded (no sidecar): ${JSON.stringify(params)}`);
      return;
    }
    try {
      await sidecar.request('acp/permissionDecision', params);
    } catch (error) {
      report(`acp/permissionDecision recording failed: ${(error as Error).message}`);
    }
  };

  const queryLedgerDenials = (): Promise<PriorDenial[]> => {
    ledgerDenials ??= (async () => {
      if (!sidecar) {
        return [];
      }
      try {
        const result = (await sidecar.request('ledger.query', {
          actorId: adapter.id,
          actionType: 'permission_decision',
          fromSequence: 1,
          toSequence: 10_000,
        })) as { entries?: LedgerDenialRow[] };
        const denials: PriorDenial[] = [];
        for (const row of result.entries ?? []) {
          if (row.actionType !== 'permission_decision' || row.decision !== 'rejected') {
            continue;
          }
          const reason = row.reworkReason ?? 'permission denied by policy';
          const kind = PERMISSION_KINDS.find(
            (candidate) => row.toolKind === candidate || kindNamedIn(reason, candidate),
          );
          if (!kind) {
            continue;
          }
          denials.push({
            kind,
            reason,
            ...(row.sequence !== undefined ? { sequence: row.sequence } : {}),
          });
        }
        return denials;
      } catch (error) {
        report(`ledger.query for SEC-28 prior denials failed: ${(error as Error).message}`);
        return [];
      }
    })();
    return ledgerDenials;
  };

  /** The agent's reject option, per the ACP answer shape; cancel if none. */
  const rejectDecision = (request: RequestPermissionRequest): AcpPermissionDecision => {
    const reject = request.options.find((option) => option.kind.startsWith('reject'));
    return reject
      ? { outcome: 'selected', optionId: reject.optionId }
      : { outcome: 'cancelled' };
  };

  const deny = async (
    request: RequestPermissionRequest,
    kind: PermissionKind,
    citation: string,
    memory: PriorDenial,
  ): Promise<AcpPermissionDecision> => {
    denied.set(kind, memory);
    await record(request, kind, 'denied_by_policy', { reason: citation });
    return rejectDecision(request);
  };

  return async (request, context) => {
    const kind = normalizeKind(request.toolCall.kind);

    // SEC-28 (in-memory): this gate already denied the kind — auto-deny.
    const remembered = denied.get(kind);
    if (remembered) {
      return deny(request, kind, `previously denied: ${remembered.reason}`, remembered);
    }

    // SEC-28 (durable): a restarted host still cites the ledger denial.
    const prior = (await queryLedgerDenials()).find((candidate) => candidate.kind === kind);
    if (prior) {
      const citation =
        prior.sequence !== undefined
          ? `previously denied (decision #${prior.sequence}): ${prior.reason}`
          : `previously denied: ${prior.reason}`;
      return deny(request, kind, citation, prior);
    }

    // FR-M34-04 governance checks, in increasing specificity.
    if (adapterState === 'suspended') {
      return deny(
        request,
        kind,
        `adapter '${adapter.id}' is suspended: every permission is denied while suspended`,
        { kind, reason: `adapter '${adapter.id}' is suspended` },
      );
    }
    if (!adapter.permissions.allow.includes(kind)) {
      return deny(
        request,
        kind,
        `tool kind '${kind}' is not declared in the manifest permissions.allow of adapter '${adapter.id}'`,
        { kind, reason: `tool kind '${kind}' is not declared in the adapter manifest` },
      );
    }
    if (!policy.isAllowed(adapter.id, adapterState, kind)) {
      return deny(
        request,
        kind,
        `${kind} is not in the ${adapterState} allow-list for ${adapter.id}`,
        { kind, reason: `${kind} is not in the ${adapterState} allow-list for ${adapter.id}` },
      );
    }

    // Every check passed — the human decides, and the answer is recorded.
    const decision = await humanApprover(request, context);
    await record(
      request,
      kind,
      decision.outcome,
      decision.outcome === 'selected' ? { optionId: decision.optionId } : {},
    );
    return decision;
  };
}
