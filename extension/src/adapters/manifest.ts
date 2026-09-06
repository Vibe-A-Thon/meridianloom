import { parse } from 'yaml';

/**
 * The adapter governance manifest (FR-M34-02, FR-M31-03): an adapter is an
 * ACP agent plus this manifest — Requirements_Final.md §7.9 re-based on ACP
 * (the `acp` launch section replaces the superseded bespoke `protocol` /
 * `entry` / `bridge` fields). The manifest carries Meridian's retained M31
 * governance surfaces as DECLARED data: provenance/vendor tag (X-27),
 * roles it can fill, declared permission needs (FR-M34-04's second check),
 * trainable surfaces (FR-M31-08), and the probation policy reference
 * (FR-M31-07). There is no bespoke agent protocol anywhere — the wire is
 * ACP, the governance is data.
 *
 * Validation is fail-closed (FR-M31-03): an invalid manifest makes the
 * adapter unavailable, listed with every actionable error.
 */

/** ACP session/request_permission tool kinds (@zed-industries/agent-client-protocol). */
export type PermissionKind =
  | 'read'
  | 'edit'
  | 'delete'
  | 'move'
  | 'execute'
  | 'search'
  | 'think'
  | 'unknown'
  | 'other';

export const PERMISSION_KINDS: readonly PermissionKind[] = [
  'read',
  'edit',
  'delete',
  'move',
  'execute',
  'search',
  'think',
  'unknown',
  'other',
];

/** Trainable surfaces an adapter may declare (FR-M31-08). */
export type TrainableSurface = 'policy' | 'rules' | 'memory' | 'skills' | 'calibration';

const TRAINABLE_SURFACES: readonly TrainableSurface[] = [
  'policy',
  'rules',
  'memory',
  'skills',
  'calibration',
];

export type Provenance = 'prebuilt' | 'custom' | 'bridged';
export type AutonomyTier = 'suggest' | 'approve' | 'autonomous';

export interface AdapterManifest {
  id: string;
  version: string;
  provenance: Provenance;
  /** Vendor/provenance tag for X-27 VendorTag rendering. */
  vendor?: string;
  /** Digest pin, required for external sources (SEC-24, FR-M31-10). */
  signature?: string;
  /** How to launch the ACP agent subprocess. */
  acp: {
    command: string;
    args: string[];
    env: Record<string, string>;
  };
  /** Roles this adapter can fill (FR-M31-13: several adapters may share one). */
  roles: string[];
  /** Declared permission needs — what the adapter may ever ask for (FR-M34-04). */
  permissions: {
    allow: PermissionKind[];
  };
  /** FR-M31-08: which surfaces are trainable and which are frozen. */
  learning: {
    trainable: TrainableSurface[];
    frozen: TrainableSurface[];
  };
  governance: {
    /** Target autonomy tier; admission is always `suggest` (FR-M31-07). */
    autonomyTier: AutonomyTier;
    /** FR-M31-07: the probation task set and pass threshold. */
    probation: {
      taskSet?: string;
      passThreshold?: number;
    };
  };
}

export type ManifestValidation =
  | { ok: true; manifest: AdapterManifest }
  | { ok: false; errors: string[]; idHint?: string };

const ID_RE = /^[a-z0-9][a-z0-9-]*$/;
const VERSION_RE = /^\d+\.\d+\.\d+$/;
const PROVENANCES: readonly Provenance[] = ['prebuilt', 'custom', 'bridged'];
const AUTONOMY_TIERS: readonly AutonomyTier[] = ['suggest', 'approve', 'autonomous'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(
  value: unknown,
  field: string,
  errors: string[],
  { nonEmpty = false }: { nonEmpty?: boolean } = {},
): string[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item === '')) {
    errors.push(`${field}: expected a list of non-empty strings`);
    return [];
  }
  if (nonEmpty && value.length === 0) {
    errors.push(`${field}: must declare at least one entry`);
  }
  return value;
}

/** Validate an already-parsed YAML/JSON value. Fail-closed with every error. */
export function validateAdapterManifest(raw: unknown, source: string): ManifestValidation {
  const errors: string[] = [];
  const fail = (): ManifestValidation => ({
    ok: false,
    errors: errors.map((error) => `${source}: ${error}`),
    // Best-effort id for discovery listings when the manifest is broken.
    ...(isRecord(raw) && isRecord(raw.adapter) && typeof raw.adapter.id === 'string'
      ? { idHint: raw.adapter.id }
      : {}),
  });

  if (!isRecord(raw)) {
    return { ok: false, errors: [`${source}: manifest must be a mapping at the top level`] };
  }

  // -- adapter ---------------------------------------------------------------
  const adapter = raw.adapter;
  if (!isRecord(adapter)) {
    errors.push('adapter: missing section (expected `adapter: { id, version, provenance }`)');
  }
  const id = isRecord(adapter) && typeof adapter.id === 'string' ? adapter.id : undefined;
  if (id === undefined || !ID_RE.test(id)) {
    errors.push(
      `adapter.id: '${String(isRecord(adapter) ? adapter.id : undefined)}' is not a valid adapter id ` +
        '(lowercase letters, digits and dashes, e.g. acme-java-developer)',
    );
  }
  const version = isRecord(adapter) && typeof adapter.version === 'string' ? adapter.version : undefined;
  if (version === undefined || !VERSION_RE.test(version)) {
    errors.push(
      `adapter.version: '${String(isRecord(adapter) ? adapter.version : undefined)}' is not a ` +
        'semantic version (e.g. 2.3.0)',
    );
  }
  const provenance = isRecord(adapter) && typeof adapter.provenance === 'string' ? adapter.provenance : undefined;
  if (provenance === undefined || !PROVENANCES.includes(provenance as Provenance)) {
    errors.push(
      `adapter.provenance: '${String(provenance)}' must be one of ${PROVENANCES.join(', ')}`,
    );
  }
  const vendor = isRecord(adapter) && typeof adapter.vendor === 'string' ? adapter.vendor : undefined;
  if (adapter !== undefined && isRecord(adapter) && adapter.vendor !== undefined && vendor === undefined) {
    errors.push('adapter.vendor: expected a string');
  }
  const signature = isRecord(adapter) && typeof adapter.signature === 'string' ? adapter.signature : undefined;
  if (isRecord(adapter) && adapter.signature !== undefined && signature === undefined) {
    errors.push('adapter.signature: expected a string (sha256:… digest pin, SEC-24)');
  }

  // -- acp launch --------------------------------------------------------------
  const acp = raw.acp;
  if (!isRecord(acp) || typeof acp.command !== 'string' || acp.command === '') {
    errors.push('acp.command: missing or empty — the manifest must declare how to launch the ACP agent');
  }
  const acpArgs = stringList(isRecord(acp) ? acp.args : undefined, 'acp.args', errors);
  let acpEnv: Record<string, string> = {};
  if (isRecord(acp) && acp.env !== undefined) {
    if (!isRecord(acp.env) || Object.values(acp.env).some((v) => typeof v !== 'string')) {
      errors.push('acp.env: expected a mapping of string names to string values');
    } else {
      acpEnv = acp.env as Record<string, string>;
    }
  }

  // -- role ----------------------------------------------------------------------
  const role = raw.role;
  if (!isRecord(role)) {
    errors.push('role: missing section (expected `role: { fills: [...] }`)');
  }
  const roles = stringList(isRecord(role) ? role.fills : undefined, 'role.fills', errors, {
    nonEmpty: true,
  });

  // -- permissions (declared needs) ----------------------------------------------
  const permissions = raw.permissions;
  if (!isRecord(permissions)) {
    errors.push('permissions: missing section (expected `permissions: { allow: [...] }`)');
  }
  const allowRaw = stringList(
    isRecord(permissions) ? permissions.allow : undefined,
    'permissions.allow',
    errors,
    { nonEmpty: true },
  );
  const allow = allowRaw.filter((kind): kind is PermissionKind =>
    (PERMISSION_KINDS as readonly string[]).includes(kind),
  );
  for (const kind of allowRaw) {
    if (!(PERMISSION_KINDS as readonly string[]).includes(kind)) {
      errors.push(
        `permissions.allow: '${kind}' is not an ACP tool kind (${PERMISSION_KINDS.join(', ')})`,
      );
    }
  }

  // -- learning (FR-M31-08, declared data) ----------------------------------------
  const learning = isRecord(raw.learning) ? raw.learning : {};
  const trainable = stringList(learning.trainable, 'learning.trainable', errors) as TrainableSurface[];
  const frozen = stringList(learning.frozen, 'learning.frozen', errors) as TrainableSurface[];
  for (const surface of [...trainable, ...frozen]) {
    if (!(TRAINABLE_SURFACES as readonly string[]).includes(surface)) {
      errors.push(
        `learning: '${surface}' is not a trainable surface (${TRAINABLE_SURFACES.join(', ')})`,
      );
    }
  }
  const overlap = trainable.filter((surface) => frozen.includes(surface));
  if (overlap.length > 0) {
    errors.push(
      `learning: surfaces cannot be both trainable and frozen: ${overlap.join(', ')}`,
    );
  }

  // -- governance -------------------------------------------------------------------
  const governance = isRecord(raw.governance) ? raw.governance : {};
  const autonomyRaw =
    governance.autonomy_tier === undefined ? 'suggest' : governance.autonomy_tier;
  if (typeof autonomyRaw !== 'string' || !AUTONOMY_TIERS.includes(autonomyRaw as AutonomyTier)) {
    errors.push(
      `governance.autonomy_tier: '${String(autonomyRaw)}' must be one of ${AUTONOMY_TIERS.join(', ')}`,
    );
  }
  const probation = isRecord(governance.probation) ? governance.probation : {};
  let taskSet: string | undefined;
  if (probation.task_set !== undefined) {
    if (typeof probation.task_set !== 'string' || probation.task_set === '') {
      errors.push('governance.probation.task_set: expected a non-empty string');
    } else {
      taskSet = probation.task_set;
    }
  }
  let passThreshold: number | undefined;
  if (probation.pass_threshold !== undefined) {
    if (
      typeof probation.pass_threshold !== 'number' ||
      probation.pass_threshold < 0 ||
      probation.pass_threshold > 1
    ) {
      errors.push('governance.probation.pass_threshold: expected a number between 0 and 1');
    } else {
      passThreshold = probation.pass_threshold;
    }
  }

  if (errors.length > 0) {
    return fail();
  }
  return {
    ok: true,
    manifest: {
      id: id!,
      version: version!,
      provenance: provenance as Provenance,
      ...(vendor !== undefined ? { vendor } : {}),
      ...(signature !== undefined ? { signature } : {}),
      acp: { command: (acp as Record<string, unknown>).command as string, args: acpArgs, env: acpEnv },
      roles,
      permissions: { allow },
      learning: { trainable, frozen },
      governance: {
        autonomyTier: autonomyRaw as AutonomyTier,
        probation: {
          ...(taskSet !== undefined ? { taskSet } : {}),
          ...(passThreshold !== undefined ? { passThreshold } : {}),
        },
      },
    },
  };
}

/**
 * Parse a manifest.yaml / manifest.yml document and validate it. A YAML
 * syntax error is a validation failure (fail-closed), never an exception —
 * discovery lists the adapter with the parse error.
 */
export function parseAdapterManifest(text: string, source: string): ManifestValidation {
  let raw: unknown;
  try {
    raw = parseYaml(text);
  } catch (error) {
    return {
      ok: false,
      errors: [`${source}: manifest is not valid YAML: ${(error as Error).message.split('\n')[0]}`],
    };
  }
  return validateAdapterManifest(raw, source);
}

/** The spec (§7.9) mandates YAML manifests; `yaml` is the parser. */
function parseYaml(text: string): unknown {
  return parse(text);
}
