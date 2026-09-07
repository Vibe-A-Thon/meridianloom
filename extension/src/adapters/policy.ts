/**
 * The Meridian ACP permission policy (FR-M34-04, SEC-28) — the minimal,
 * D16-style allow-list the ACP host checks BEFORE an agent's
 * session/request_permission reaches the human. The canonical file lives at
 * policy/acp-permissions.yaml in the repository; a workspace overrides it at
 * .meridian/policy/acp-permissions.yaml (first readable file wins).
 *
 * Shape (version 1): `adapters` maps adapter manifest ids to per-state kind
 * lists (`*` is the floor for adapters with no specific entry); `deny` is
 * evaluated before `allow` — a kind on both is denied. Parsing is fail-
 * closed like the manifest validator: any error makes the policy deny
 * everything and surfaces every error, never an exception.
 */
import { parse } from 'yaml';
import { PERMISSION_KINDS, type PermissionKind } from './manifest';
import type { AdapterState } from './probation';

/** The wildcard adapter entry — the default for adapters with no specific entry. */
export const POLICY_STAR = '*';

export interface AcpPermissionPolicy {
  readonly version: number;
  /** Parse/validation errors; a policy carrying any error is fail-closed. */
  readonly errors: readonly string[];
  /** The grantable kinds for an adapter in a state (deny already applied). */
  allows(adapterId: string, state: AdapterState): readonly PermissionKind[];
  isAllowed(adapterId: string, state: AdapterState, kind: PermissionKind): boolean;
}

/** Autonomy states the policy names; `suspended` is not policy-configurable. */
const POLICY_STATES: readonly AdapterState[] = ['probation', 'active'];
const ENTRY_KEYS: readonly string[] = [...POLICY_STATES, 'deny'];

interface AdapterPolicyRule {
  allow: Partial<Record<AdapterState, PermissionKind[]>>;
  deny: PermissionKind[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function kindList(value: unknown, field: string, errors: string[]): PermissionKind[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item === '')) {
    errors.push(`${field}: expected a list of non-empty strings`);
    return [];
  }
  const kinds: PermissionKind[] = [];
  for (const item of value) {
    if ((PERMISSION_KINDS as readonly string[]).includes(item)) {
      kinds.push(item as PermissionKind);
    } else {
      errors.push(`${field}: '${item}' is not an ACP tool kind (${PERMISSION_KINDS.join(', ')})`);
    }
  }
  return kinds;
}

/** Fail-closed policy: nothing is allowed, every call denies quietly. */
function failClosed(version: number, errors: string[]): AcpPermissionPolicy {
  return {
    version,
    errors,
    allows: () => [],
    isAllowed: () => false,
  };
}

/**
 * Parse and validate an acp-permissions policy document. Never throws:
 * YAML syntax errors and schema violations come back as `errors`, and a
 * policy with errors denies every request.
 */
export function parseAcpPermissionPolicy(text: string, source: string): AcpPermissionPolicy {
  let raw: unknown;
  try {
    raw = parse(text);
  } catch (error) {
    return failClosed(0, [
      `${source}: policy is not valid YAML: ${(error as Error).message.split('\n')[0]}`,
    ]);
  }
  if (!isRecord(raw)) {
    return failClosed(0, [`${source}: policy must be a mapping at the top level`]);
  }

  const errors: string[] = [];
  let version = 0;
  if (typeof raw.version === 'number' && Number.isInteger(raw.version) && raw.version >= 1) {
    version = raw.version;
  } else {
    errors.push(`version: expected an integer >= 1, got '${String(raw.version)}'`);
  }

  const rules = new Map<string, AdapterPolicyRule>();
  if (raw.adapters === undefined) {
    errors.push('adapters: missing section (expected `adapters: { <id>: { probation: [...], active: [...] } }`)');
  } else if (!isRecord(raw.adapters)) {
    errors.push('adapters: expected a mapping of adapter id to per-state kind lists');
  } else {
    for (const [adapterId, entry] of Object.entries(raw.adapters)) {
      if (!isRecord(entry)) {
        errors.push(`adapters.${adapterId}: expected a mapping of autonomy state to kind lists`);
        continue;
      }
      const rule: AdapterPolicyRule = { allow: {}, deny: [] };
      for (const [key, value] of Object.entries(entry)) {
        if (!ENTRY_KEYS.includes(key)) {
          errors.push(
            `adapters.${adapterId}.${key}: unknown key (expected ${ENTRY_KEYS.join(', ')})`,
          );
          continue;
        }
        if (key === 'deny') {
          rule.deny = kindList(value, `adapters.${adapterId}.deny`, errors);
        } else {
          rule.allow[key as AdapterState] = kindList(value, `adapters.${adapterId}.${key}`, errors);
        }
      }
      rules.set(adapterId, rule);
    }
  }

  if (errors.length > 0) {
    return failClosed(version, errors.map((error) => `${source}: ${error}`));
  }

  const allows = (adapterId: string, state: AdapterState): readonly PermissionKind[] => {
    const specific = rules.get(adapterId);
    const fallback = rules.get(POLICY_STAR);
    const allow = specific?.allow[state] ?? fallback?.allow[state] ?? [];
    // Deny before allow: a kind on the '*' or the specific deny list is out.
    const denied = new Set<PermissionKind>([...(fallback?.deny ?? []), ...(specific?.deny ?? [])]);
    return allow.filter((kind) => !denied.has(kind));
  };

  return {
    version,
    errors: [],
    allows,
    isAllowed: (adapterId, state, kind) => allows(adapterId, state).includes(kind),
  };
}
